"""
Tests funcionales para la app fiados.
Cubre modelos, vistas y la lógica de abonos.

Ejecutar con:
    python manage.py test fiados -v 2
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
import json

from configuracion.models import Moneda, Empresa
from inventario.models import Producto, Categoria
from .models import Cliente, Fiado, DetalleFiado, PagoFiado


# ── helpers ──────────────────────────────────────────────────────────

def _post_json(client, url, data):
    return client.post(url, json.dumps(data), content_type='application/json')


def _crear_base():
    """
    Crea el escenario mínimo: moneda (tasa=50), empresa, admin,
    dos productos (unidad + kg), y un cliente.
    """
    moneda = Moneda.objects.first()
    if moneda:
        moneda.tasa_cambio = Decimal('50.00')
        moneda.save(update_fields=['tasa_cambio'])
    else:
        moneda = Moneda.objects.create(tasa_cambio=Decimal('50.00'))

    Empresa.objects.create(nombre='Test SA', rif='J123456789')

    cat   = Categoria.objects.create(nombre='General')
    admin = User.objects.create_user('admin_t', password='admin1234', is_staff=True)

    prod_ud = Producto.objects.create(
        nombre='Leche 1L', precio_usd=Decimal('2.00'),
        costo_usd=Decimal('1.50'), stock_actual=20, stock_minimo=5,
        categoria=cat, vendido_por_peso=False,
    )
    prod_kg = Producto.objects.create(
        nombre='Queso Blanco', precio_usd=Decimal('4.00'),
        costo_usd=Decimal('3.00'), stock_actual=Decimal('10.000'), stock_minimo=1,
        categoria=cat, vendido_por_peso=True,
    )
    cliente = Cliente.objects.create(nombre='Juan Pérez', telefono='04141234567')

    return moneda, admin, prod_ud, prod_kg, cliente


# ══════════════════════════════════════════════════════════════════
# Modelo Fiado — lógica de negocio
# ══════════════════════════════════════════════════════════════════

class FiadoModelTests(TestCase):

    def setUp(self):
        self.moneda, self.admin, self.prod_ud, self.prod_kg, self.cliente = _crear_base()

    # ── crear_desde_carrito ────────────────────────────────────────

    def test_crea_fiado_y_detalles(self):
        items = [{'producto': self.prod_ud, 'cantidad': Decimal('2')}]
        fiado = Fiado.crear_desde_carrito(items, self.cliente, vendedor=self.admin)

        self.assertEqual(Fiado.objects.count(), 1)
        self.assertEqual(fiado.detalles.count(), 1)
        self.assertEqual(fiado.estado, 'PENDIENTE')
        self.assertEqual(fiado.cliente, self.cliente)

    def test_totales_correctos_unidad(self):
        # precio=2.00, cant=3, tasa=50 → usd=6, bs=300
        items = [{'producto': self.prod_ud, 'cantidad': Decimal('3')}]
        fiado = Fiado.crear_desde_carrito(items, self.cliente)

        self.assertEqual(float(fiado.total_usd), 6.00)
        self.assertEqual(float(fiado.total_bs),  300.00)

    def test_descuenta_stock_unidades(self):
        items = [{'producto': self.prod_ud, 'cantidad': Decimal('5')}]
        Fiado.crear_desde_carrito(items, self.cliente)

        self.prod_ud.refresh_from_db()
        self.assertEqual(self.prod_ud.stock_actual, 15)  # 20 - 5

    def test_kg_usa_cantidad_decimal(self):
        """El carrito de kg debe preservar decimales (no truncar a int)."""
        items = [{'producto': self.prod_kg, 'cantidad': Decimal('1.350')}]
        fiado = Fiado.crear_desde_carrito(items, self.cliente)

        detalle = fiado.detalles.first()
        self.assertEqual(detalle.cantidad, Decimal('1.350'))

    def test_descuenta_stock_kg_decimal(self):
        items = [{'producto': self.prod_kg, 'cantidad': Decimal('2.500')}]
        Fiado.crear_desde_carrito(items, self.cliente)

        self.prod_kg.refresh_from_db()
        self.assertEqual(self.prod_kg.stock_actual, Decimal('7.500'))  # 10 - 2.5

    def test_stock_insuficiente_lanza_error(self):
        items = [{'producto': self.prod_ud, 'cantidad': Decimal('999')}]
        with self.assertRaises(ValueError) as ctx:
            Fiado.crear_desde_carrito(items, self.cliente)
        self.assertIn('insuficiente', str(ctx.exception).lower())

    def test_stock_insuficiente_no_descuenta(self):
        """Si el stock falla, el stock no debe modificarse (atomic)."""
        items = [{'producto': self.prod_ud, 'cantidad': Decimal('999')}]
        try:
            Fiado.crear_desde_carrito(items, self.cliente)
        except ValueError:
            pass
        self.prod_ud.refresh_from_db()
        self.assertEqual(self.prod_ud.stock_actual, 20)

    # ── saldo_usd y actualizar_estado ─────────────────────────────

    def test_saldo_usd_inicial_igual_a_total(self):
        items = [{'producto': self.prod_ud, 'cantidad': Decimal('1')}]
        fiado = Fiado.crear_desde_carrito(items, self.cliente)

        self.assertEqual(fiado.saldo_usd, fiado.total_usd)

    def test_actualizar_estado_parcial(self):
        items = [{'producto': self.prod_ud, 'cantidad': Decimal('4')}]
        fiado = Fiado.crear_desde_carrito(items, self.cliente)  # total=8 USD

        PagoFiado.objects.create(
            fiado=fiado, monto_usd=Decimal('3.00'), monto_bs=Decimal('150.00'),
            tasa_aplicada=Decimal('50.00'), metodo_pago='EFECTIVO_USD',
        )
        fiado.actualizar_estado()
        self.assertEqual(fiado.estado, 'PARCIAL')
        self.assertEqual(fiado.saldo_usd, Decimal('5.00'))

    def test_actualizar_estado_pagado(self):
        items = [{'producto': self.prod_ud, 'cantidad': Decimal('2')}]
        fiado = Fiado.crear_desde_carrito(items, self.cliente)  # total=4 USD

        PagoFiado.objects.create(
            fiado=fiado, monto_usd=Decimal('4.00'), monto_bs=Decimal('200.00'),
            tasa_aplicada=Decimal('50.00'), metodo_pago='EFECTIVO_USD',
        )
        fiado.actualizar_estado()
        self.assertEqual(fiado.estado, 'PAGADO')
        self.assertEqual(fiado.saldo_usd, Decimal('0'))

    def test_actualizar_estado_anulado_no_cambia(self):
        items = [{'producto': self.prod_ud, 'cantidad': Decimal('1')}]
        fiado = Fiado.crear_desde_carrito(items, self.cliente)
        fiado.estado = 'ANULADO'
        fiado.save(update_fields=['estado'])

        fiado.actualizar_estado()
        fiado.refresh_from_db()
        self.assertEqual(fiado.estado, 'ANULADO')


# ══════════════════════════════════════════════════════════════════
# Vista registrar_pago
# ══════════════════════════════════════════════════════════════════

class RegistrarPagoTests(TestCase):

    def setUp(self):
        self.moneda, self.admin, self.prod_ud, self.prod_kg, self.cliente = _crear_base()
        self.client = Client()
        self.client.login(username='admin_t', password='admin1234')

        items = [{'producto': self.prod_ud, 'cantidad': Decimal('4')}]
        self.fiado = Fiado.crear_desde_carrito(items, self.cliente, vendedor=self.admin)
        # total_usd = 8.00, total_bs = 400.00

    def _url(self):
        return reverse('fiados:registrar_pago', args=[self.fiado.pk])

    # ── Pagos en USD ───────────────────────────────────────────────

    def test_pago_usd_crea_pagofiado(self):
        r = _post_json(self.client, self._url(), {
            'monto_usd': 3.00,
            'metodo_pago': 'EFECTIVO_USD',
        })
        self.assertTrue(r.json()['ok'])
        self.assertEqual(PagoFiado.objects.count(), 1)

    def test_pago_usd_estado_parcial(self):
        _post_json(self.client, self._url(), {'monto_usd': 3.00, 'metodo_pago': 'EFECTIVO_USD'})
        self.fiado.refresh_from_db()
        self.assertEqual(self.fiado.estado, 'PARCIAL')

    def test_pago_usd_total_marca_pagado(self):
        _post_json(self.client, self._url(), {'monto_usd': 8.00, 'metodo_pago': 'EFECTIVO_USD'})
        self.fiado.refresh_from_db()
        self.assertEqual(self.fiado.estado, 'PAGADO')

    def test_pago_usd_excede_saldo_rechazado(self):
        r = _post_json(self.client, self._url(), {'monto_usd': 9.00, 'metodo_pago': 'EFECTIVO_USD'})
        data = r.json()
        self.assertFalse(data['ok'])
        self.assertIn('saldo', data['error'].lower())
        self.assertEqual(PagoFiado.objects.count(), 0)

    def test_pago_usd_cero_rechazado(self):
        r = _post_json(self.client, self._url(), {'monto_usd': 0, 'metodo_pago': 'EFECTIVO_USD'})
        self.assertFalse(r.json()['ok'])

    # ── Pagos en Bs ────────────────────────────────────────────────

    def test_pago_bs_convierte_a_usd(self):
        """Bs. 100 / tasa 50 = $2 USD."""
        r = _post_json(self.client, self._url(), {
            'monto_bs': 100.00,
            'metodo_pago': 'EFECTIVO_BS',
        })
        self.assertTrue(r.json()['ok'])
        pago = PagoFiado.objects.first()
        self.assertEqual(float(pago.monto_usd), 2.00)
        self.assertEqual(float(pago.monto_bs),  100.00)

    def test_pago_bs_exacto_cierra_saldo(self):
        """Pago en Bs que cubre exactamente el saldo USD debe marcar PAGADO."""
        # saldo = $8 → en Bs = 8 × 50 = 400
        r = _post_json(self.client, self._url(), {
            'monto_bs': 400.00,
            'metodo_pago': 'EFECTIVO_BS',
        })
        self.assertTrue(r.json()['ok'])
        self.fiado.refresh_from_db()
        self.assertEqual(self.fiado.estado, 'PAGADO')

    def test_pago_bs_excede_saldo_rechazado(self):
        r = _post_json(self.client, self._url(), {
            'monto_bs': 9999.00,
            'metodo_pago': 'EFECTIVO_BS',
        })
        self.assertFalse(r.json()['ok'])
        self.assertEqual(PagoFiado.objects.count(), 0)

    # ── Métodos digitales ──────────────────────────────────────────

    def test_pago_transferencia_ok(self):
        r = _post_json(self.client, self._url(), {
            'monto_usd': 4.00,
            'metodo_pago': 'TRANSFERENCIA',
        })
        self.assertTrue(r.json()['ok'])
        pago = PagoFiado.objects.first()
        self.assertEqual(pago.metodo_pago, 'TRANSFERENCIA')

    def test_pago_pago_movil_ok(self):
        r = _post_json(self.client, self._url(), {
            'monto_bs': 200.00,
            'metodo_pago': 'PAGO_MOVIL',
        })
        self.assertTrue(r.json()['ok'])

    def test_metodo_pago_invalido_rechazado(self):
        r = _post_json(self.client, self._url(), {
            'monto_usd': 2.00,
            'metodo_pago': 'CRIPTO',
        })
        self.assertFalse(r.json()['ok'])
        self.assertIn('método', r.json()['error'].lower())

    # ── Restricciones de estado ────────────────────────────────────

    def test_fiado_anulado_rechaza_pago(self):
        self.fiado.estado = 'ANULADO'
        self.fiado.save(update_fields=['estado'])

        r = _post_json(self.client, self._url(), {'monto_usd': 2.00, 'metodo_pago': 'EFECTIVO_USD'})
        self.assertFalse(r.json()['ok'])
        self.assertIn('anulado', r.json()['error'].lower())

    def test_fiado_ya_pagado_rechaza_pago(self):
        self.fiado.estado = 'PAGADO'
        self.fiado.save(update_fields=['estado'])

        r = _post_json(self.client, self._url(), {'monto_usd': 2.00, 'metodo_pago': 'EFECTIVO_USD'})
        self.assertFalse(r.json()['ok'])
        self.assertIn('saldado', r.json()['error'].lower())

    # ── Acceso ────────────────────────────────────────────────────

    def test_cajero_sin_acceso(self):
        cajero = User.objects.create_user('cajero_t', password='caj1234', is_staff=False)
        c = Client()
        c.login(username='cajero_t', password='caj1234')
        r = _post_json(c, self._url(), {'monto_usd': 1.00, 'metodo_pago': 'EFECTIVO_USD'})
        self.assertNotEqual(r.status_code, 200)


# ══════════════════════════════════════════════════════════════════
# Vista anular_fiado
# ══════════════════════════════════════════════════════════════════

class AnularFiadoTests(TestCase):

    def setUp(self):
        _, self.admin, self.prod_ud, _, self.cliente = _crear_base()
        self.client = Client()
        self.client.login(username='admin_t', password='admin1234')

        items = [{'producto': self.prod_ud, 'cantidad': Decimal('3')}]
        self.fiado = Fiado.crear_desde_carrito(items, self.cliente)
        # stock queda en 17 después de crear el fiado

    def _url(self):
        return reverse('fiados:anular', args=[self.fiado.pk])

    def test_anular_revierte_stock(self):
        _post_json(self.client, self._url(), {})
        self.prod_ud.refresh_from_db()
        self.assertEqual(self.prod_ud.stock_actual, 20)  # 17 + 3

    def test_anular_marca_estado_anulado(self):
        r = _post_json(self.client, self._url(), {})
        self.assertTrue(r.json()['ok'])
        self.fiado.refresh_from_db()
        self.assertEqual(self.fiado.estado, 'ANULADO')

    def test_anular_ya_anulado_rechazado(self):
        self.fiado.estado = 'ANULADO'
        self.fiado.save(update_fields=['estado'])

        r = _post_json(self.client, self._url(), {})
        self.assertFalse(r.json()['ok'])

    def test_anular_pagado_rechazado(self):
        self.fiado.estado = 'PAGADO'
        self.fiado.save(update_fields=['estado'])

        r = _post_json(self.client, self._url(), {})
        self.assertFalse(r.json()['ok'])
        self.assertIn('pagado', r.json()['error'].lower())

    def test_anular_no_deja_pagos_huerfanos(self):
        """Los pagos existentes no se eliminan al anular (auditoría)."""
        PagoFiado.objects.create(
            fiado=self.fiado, monto_usd=Decimal('1.00'), monto_bs=Decimal('50.00'),
            tasa_aplicada=Decimal('50.00'), metodo_pago='EFECTIVO_USD',
        )
        _post_json(self.client, self._url(), {})
        self.assertEqual(PagoFiado.objects.count(), 1)


# ══════════════════════════════════════════════════════════════════
# Vista nueva_venta_fiada
# ══════════════════════════════════════════════════════════════════

class NuevaVentaFiadaTests(TestCase):

    def setUp(self):
        _, self.admin, self.prod_ud, self.prod_kg, self.cliente = _crear_base()
        self.client = Client()
        self.client.login(username='admin_t', password='admin1234')

    def _url(self):
        return reverse('fiados:nueva_venta', args=[self.cliente.pk])

    def test_venta_ud_crea_fiado(self):
        r = _post_json(self.client, self._url(), {
            'carrito': [{'id': self.prod_ud.pk, 'cantidad': 2}],
        })
        self.assertTrue(r.json()['ok'])
        self.assertEqual(Fiado.objects.count(), 1)

    def test_venta_kg_preserva_decimal(self):
        """La cantidad de kg no debe truncarse a entero."""
        r = _post_json(self.client, self._url(), {
            'carrito': [{'id': self.prod_kg.pk, 'cantidad': 1.750}],
        })
        self.assertTrue(r.json()['ok'])
        detalle = DetalleFiado.objects.first()
        self.assertEqual(detalle.cantidad, Decimal('1.750'))

    def test_venta_kg_descuenta_stock_decimal(self):
        _post_json(self.client, self._url(), {
            'carrito': [{'id': self.prod_kg.pk, 'cantidad': 2.500}],
        })
        self.prod_kg.refresh_from_db()
        self.assertEqual(self.prod_kg.stock_actual, Decimal('7.500'))

    def test_carrito_vacio_rechazado(self):
        r = _post_json(self.client, self._url(), {'carrito': []})
        self.assertFalse(r.json()['ok'])
        self.assertIn('vacío', r.json()['error'])

    def test_stock_insuficiente_rechazado(self):
        r = _post_json(self.client, self._url(), {
            'carrito': [{'id': self.prod_ud.pk, 'cantidad': 999}],
        })
        self.assertFalse(r.json()['ok'])

    def test_cliente_inactivo_rechazado(self):
        """El view captura Http404 como Exception → 500; lo importante es que no crea fiado."""
        self.cliente.activo = False
        self.cliente.save(update_fields=['activo'])

        r = _post_json(self.client, self._url(), {
            'carrito': [{'id': self.prod_ud.pk, 'cantidad': 1}],
        })
        self.assertNotEqual(r.status_code, 200)
        self.assertEqual(Fiado.objects.count(), 0)

    def test_notas_se_guardan(self):
        r = _post_json(self.client, self._url(), {
            'carrito': [{'id': self.prod_ud.pk, 'cantidad': 1}],
            'notas': 'Paga el viernes',
        })
        self.assertTrue(r.json()['ok'])
        fiado = Fiado.objects.first()
        self.assertEqual(fiado.notas, 'Paga el viernes')

    def test_total_usd_y_bs_en_respuesta(self):
        r = _post_json(self.client, self._url(), {
            'carrito': [{'id': self.prod_ud.pk, 'cantidad': 2}],
        })
        data = r.json()
        self.assertIn('total_usd', data)
        self.assertIn('total_bs',  data)
        self.assertAlmostEqual(data['total_usd'], 4.00)   # 2 × $2
        self.assertAlmostEqual(data['total_bs'],  200.00)  # 4 × 50
