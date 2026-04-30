"""
Tests funcionales para cierre de caja con abonos de fiados.

Cubre:
  - cierre_caja: contexto incluye abonos del día
  - guardar_cierre: totales incluyen abonos
  - imprimir_cierre: contexto de impresión incluye abonos
  - Umbral de tasa vencida (26 h)

Ejecutar con:
    python manage.py test reportes.tests_cierre -v 2
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
import json

from configuracion.models import Moneda, Empresa
from inventario.models import Producto, Categoria
from ventas.models import Venta
from fiados.models import Cliente, Fiado, PagoFiado
from reportes.models import CierreCaja


# ── helpers ──────────────────────────────────────────────────────────

def _post_json(client, url, data):
    return client.post(url, json.dumps(data), content_type='application/json')


def _crear_base():
    """
    Moneda (tasa=50), empresa, admin, un producto, un cliente fiado.
    La moneda ya existe por la migración 0004; la actualizamos.
    """
    moneda = Moneda.objects.first()
    if moneda:
        moneda.tasa_cambio = Decimal('50.00')
        moneda.save(update_fields=['tasa_cambio'])
    else:
        moneda = Moneda.objects.create(tasa_cambio=Decimal('50.00'))

    empresa = Empresa.objects.create(nombre='Test Cierre SA', rif='J000000001')
    cat     = Categoria.objects.create(nombre='General')
    admin   = User.objects.create_user('admin_t', password='admin1234', is_staff=True)

    prod = Producto.objects.create(
        nombre='Leche 1L', precio_usd=Decimal('2.00'),
        costo_usd=Decimal('1.50'), stock_actual=50, stock_minimo=5,
        categoria=cat,
    )
    cliente = Cliente.objects.create(nombre='Pedro Pérez')
    return moneda, admin, prod, cliente


def _crear_venta(prod, admin, metodo, cantidad=2):
    """Crea una venta completada del día."""
    return Venta.crear_desde_carrito(
        [{'producto': prod, 'cantidad': cantidad}],
        metodo,
        vendedor=admin,
    )


def _crear_fiado_con_pago(prod, cliente, admin, cant_fiada, monto_pago_usd, metodo):
    """Crea un fiado y registra un abono."""
    items = [{'producto': prod, 'cantidad': Decimal(str(cant_fiada))}]
    fiado = Fiado.crear_desde_carrito(items, cliente, vendedor=admin)
    tasa  = Moneda.objects.first().tasa_cambio
    pago  = PagoFiado.objects.create(
        fiado         = fiado,
        monto_usd     = Decimal(str(monto_pago_usd)),
        monto_bs      = Decimal(str(monto_pago_usd)) * tasa,
        tasa_aplicada = tasa,
        metodo_pago   = metodo,
        registrado_por= admin,
    )
    fiado.actualizar_estado()
    return fiado, pago


# ══════════════════════════════════════════════════════════════════
# Vista cierre_caja — contexto con abonos
# ══════════════════════════════════════════════════════════════════

class CierreCajaContextoTests(TestCase):

    def setUp(self):
        self.moneda, self.admin, self.prod, self.cliente = _crear_base()
        self.client = Client()
        self.client.login(username='admin_t', password='admin1234')
        self.url = reverse('reportes:cierre_caja')

    # ── Sin abonos ─────────────────────────────────────────────────

    def test_sin_abonos_lista_vacia(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['resumen_abonos_lista'], [])

    def test_sin_abonos_grand_total_igual_ventas(self):
        _crear_venta(self.prod, self.admin, 'EFECTIVO_USD', 2)
        r = self.client.get(self.url)
        ctx = r.context
        self.assertAlmostEqual(ctx['gran_total_usd'], ctx['total_general_usd'])
        self.assertAlmostEqual(ctx['gran_total_bs'],  ctx['total_general_bs'])

    def test_sin_datos_responde_ok(self):
        """El cierre no debe explotar si no hay ventas ni abonos."""
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['total_general_usd'], 0)
        self.assertEqual(r.context['total_abonos_usd'],  0)
        self.assertEqual(r.context['gran_total_usd'],    0)

    # ── Con abonos ─────────────────────────────────────────────────

    def test_abono_aparece_en_contexto(self):
        _crear_fiado_con_pago(self.prod, self.cliente, self.admin, 3, 2.00, 'EFECTIVO_USD')
        r = self.client.get(self.url)
        self.assertEqual(r.context['total_abonos_count'], 1)
        self.assertAlmostEqual(r.context['total_abonos_usd'], 2.00)

    def test_abono_bs_suma_correctamente(self):
        # pago $3 × tasa 50 = Bs 150
        _crear_fiado_con_pago(self.prod, self.cliente, self.admin, 4, 3.00, 'EFECTIVO_BS')
        r = self.client.get(self.url)
        self.assertAlmostEqual(r.context['total_abonos_bs'], 150.00)

    def test_gran_total_suma_ventas_y_abonos(self):
        # Venta: 2 × $2 = $4
        _crear_venta(self.prod, self.admin, 'EFECTIVO_USD', 2)
        # Abono: $3
        _crear_fiado_con_pago(self.prod, self.cliente, self.admin, 4, 3.00, 'EFECTIVO_USD')

        r = self.client.get(self.url)
        ctx = r.context
        self.assertAlmostEqual(ctx['total_general_usd'], 4.00)
        self.assertAlmostEqual(ctx['total_abonos_usd'],  3.00)
        self.assertAlmostEqual(ctx['gran_total_usd'],    7.00)

    def test_abonos_agrupados_por_metodo(self):
        """Abonos en distintos métodos deben generar entradas separadas."""
        _crear_fiado_con_pago(self.prod, self.cliente, self.admin, 4, 2.00, 'EFECTIVO_USD')
        c2 = Cliente.objects.create(nombre='María López')
        _crear_fiado_con_pago(self.prod, c2, self.admin, 4, 1.00, 'TRANSFERENCIA')

        r = self.client.get(self.url)
        codigos = {m['codigo'] for m in r.context['resumen_abonos_lista']}
        self.assertIn('EFECTIVO_USD',  codigos)
        self.assertIn('TRANSFERENCIA', codigos)
        self.assertEqual(len(codigos), 2)

    def test_abono_mismo_metodo_se_agrupa(self):
        """Dos abonos en el mismo método deben sumar en una sola entrada."""
        c2 = Cliente.objects.create(nombre='Ana Gómez')
        _crear_fiado_con_pago(self.prod, self.cliente, self.admin, 5, 2.00, 'PAGO_MOVIL')
        _crear_fiado_con_pago(self.prod, c2,           self.admin, 5, 3.00, 'PAGO_MOVIL')

        r = self.client.get(self.url)
        metodos = r.context['resumen_abonos_lista']
        movil   = next((m for m in metodos if m['codigo'] == 'PAGO_MOVIL'), None)
        self.assertIsNotNone(movil)
        self.assertAlmostEqual(movil['total_usd'], 5.00)
        self.assertEqual(movil['cantidad'], 2)

    def test_abono_contiene_datos_pago(self):
        """Cada abono en el acordeón debe exponer el PagoFiado correcto."""
        _, pago = _crear_fiado_con_pago(
            self.prod, self.cliente, self.admin, 3, 2.50, 'PUNTO_DE_VENTA'
        )
        r = self.client.get(self.url)
        metodos = r.context['resumen_abonos_lista']
        pdv     = next(m for m in metodos if m['codigo'] == 'PUNTO_DE_VENTA')
        self.assertEqual(pdv['pagos'][0].pk, pago.pk)

    # ── Abonos de otro día no aparecen ────────────────────────────

    def test_abono_de_otro_dia_no_aparece(self):
        _, pago = _crear_fiado_con_pago(
            self.prod, self.cliente, self.admin, 3, 2.00, 'EFECTIVO_USD'
        )
        # Retrofechar el pago a ayer
        ayer = timezone.now() - timezone.timedelta(days=1)
        PagoFiado.objects.filter(pk=pago.pk).update(fecha=ayer)

        r = self.client.get(self.url)
        self.assertEqual(r.context['resumen_abonos_lista'], [])
        self.assertEqual(r.context['total_abonos_count'],   0)

    def test_venta_de_otro_dia_no_aparece_en_abonos(self):
        """Pagos de fiados de otro día no deben contaminar el cierre de hoy."""
        _, pago = _crear_fiado_con_pago(
            self.prod, self.cliente, self.admin, 4, 5.00, 'TRANSFERENCIA'
        )
        manana = timezone.now() + timezone.timedelta(days=1)
        PagoFiado.objects.filter(pk=pago.pk).update(fecha=manana)

        r = self.client.get(self.url)
        self.assertEqual(r.context['total_abonos_usd'], 0)


# ══════════════════════════════════════════════════════════════════
# Vista guardar_cierre — totales con abonos
# ══════════════════════════════════════════════════════════════════

class GuardarCierreConAbonosTests(TestCase):

    def setUp(self):
        self.moneda, self.admin, self.prod, self.cliente = _crear_base()
        self.client = Client()
        self.client.login(username='admin_t', password='admin1234')
        self.url  = reverse('reportes:guardar_cierre')
        self.fecha = timezone.localdate().isoformat()

    def _guardar(self, notas=''):
        return _post_json(self.client, self.url, {'fecha': self.fecha, 'notas': notas})

    # ── Sin abonos ─────────────────────────────────────────────────

    def test_sin_datos_crea_cierre_en_cero(self):
        r = self._guardar()
        self.assertTrue(r.json()['ok'])
        c = CierreCaja.objects.get(fecha=self.fecha)
        self.assertEqual(float(c.efectivo_usd_esperado), 0.0)

    def test_venta_efectivo_usd_sin_abono(self):
        _crear_venta(self.prod, self.admin, 'EFECTIVO_USD', 2)  # $4
        self._guardar()
        c = CierreCaja.objects.get(fecha=self.fecha)
        self.assertAlmostEqual(float(c.efectivo_usd_esperado), 4.00)

    # ── Abono efectivo USD suma al campo efectivo_usd ─────────────

    def test_abono_efectivo_usd_suma_a_efectivo(self):
        _crear_venta(self.prod, self.admin, 'EFECTIVO_USD', 2)          # venta $4
        _crear_fiado_con_pago(self.prod, self.cliente, self.admin, 5, 3.00, 'EFECTIVO_USD')  # abono $3
        self._guardar()

        c = CierreCaja.objects.get(fecha=self.fecha)
        self.assertAlmostEqual(float(c.efectivo_usd_esperado), 7.00)  # 4 + 3

    # ── Abono efectivo Bs suma al campo efectivo_bs ────────────────

    def test_abono_efectivo_bs_suma_a_efectivo_bs(self):
        # Abono de $2 en Bs → Bs 100 (tasa 50)
        _crear_fiado_con_pago(self.prod, self.cliente, self.admin, 5, 2.00, 'EFECTIVO_BS')
        self._guardar()

        c = CierreCaja.objects.get(fecha=self.fecha)
        # efectivo_bs_esperado en el modelo es la suma de total_bs de ventas EFECTIVO_BS + abono Bs
        self.assertAlmostEqual(float(c.efectivo_bs_esperado), 100.00)

    # ── Abono digital suma al método correspondiente ───────────────

    def test_abono_transferencia_suma_a_transferencia_total(self):
        _crear_fiado_con_pago(self.prod, self.cliente, self.admin, 5, 4.00, 'TRANSFERENCIA')
        self._guardar()
        c = CierreCaja.objects.get(fecha=self.fecha)
        self.assertAlmostEqual(float(c.transferencia_total), 4.00)

    def test_abono_pago_movil_suma_a_pago_movil_total(self):
        _crear_fiado_con_pago(self.prod, self.cliente, self.admin, 5, 1.50, 'PAGO_MOVIL')
        self._guardar()
        c = CierreCaja.objects.get(fecha=self.fecha)
        self.assertAlmostEqual(float(c.pago_movil_total), 1.50)

    def test_abono_punto_de_venta_suma_a_pdv(self):
        _crear_venta(self.prod, self.admin, 'PUNTO_DE_VENTA', 1)          # venta $2
        _crear_fiado_con_pago(self.prod, self.cliente, self.admin, 5, 3.00, 'PUNTO_DE_VENTA')  # abono $3
        self._guardar()
        c = CierreCaja.objects.get(fecha=self.fecha)
        self.assertAlmostEqual(float(c.punto_de_venta_total), 5.00)  # 2 + 3

    # ── update_or_create funciona con abonos ──────────────────────

    def test_guardar_dos_veces_actualiza(self):
        _crear_fiado_con_pago(self.prod, self.cliente, self.admin, 5, 2.00, 'EFECTIVO_USD')
        self._guardar()
        self._guardar(notas='Segunda vez')
        self.assertEqual(CierreCaja.objects.filter(fecha=self.fecha).count(), 1)
        c = CierreCaja.objects.get(fecha=self.fecha)
        self.assertEqual(c.notas, 'Segunda vez')

    def test_guardar_requiere_admin(self):
        cajero = User.objects.create_user('cajero_t', password='caj1234', is_staff=False)
        c = Client()
        c.login(username='cajero_t', password='caj1234')
        r = _post_json(c, self.url, {'fecha': self.fecha})
        self.assertNotEqual(r.status_code, 200)


# ══════════════════════════════════════════════════════════════════
# Vista imprimir_cierre — contexto de impresión incluye abonos
# ══════════════════════════════════════════════════════════════════

class ImprimirCierreTests(TestCase):

    def setUp(self):
        _, self.admin, self.prod, self.cliente = _crear_base()
        self.client = Client()
        self.client.login(username='admin_t', password='admin1234')
        self.url = reverse('reportes:imprimir_cierre')

    def test_sin_abonos_lista_vacia(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['resumen_abonos'], [])

    def test_abono_aparece_en_contexto_print(self):
        _crear_fiado_con_pago(self.prod, self.cliente, self.admin, 3, 2.00, 'EFECTIVO_USD')
        r = self.client.get(self.url)
        self.assertEqual(len(r.context['resumen_abonos']), 1)
        self.assertAlmostEqual(r.context['total_abonos_usd'], 2.00)

    def test_gran_total_en_contexto_print(self):
        _crear_venta(self.prod, self.admin, 'EFECTIVO_USD', 2)          # $4
        _crear_fiado_con_pago(self.prod, self.cliente, self.admin, 5, 3.00, 'PAGO_MOVIL')  # $3
        r = self.client.get(self.url)
        self.assertAlmostEqual(r.context['gran_total_usd'], 7.00)


# ══════════════════════════════════════════════════════════════════
# Umbral de tasa vencida — 26 horas (corregido desde 15 h)
# ══════════════════════════════════════════════════════════════════

class TasaVencidaUmbralTests(TestCase):

    def setUp(self):
        self.moneda = Moneda.objects.first()
        if not self.moneda:
            self.moneda = Moneda.objects.create(tasa_cambio=Decimal('50.00'))
        Empresa.objects.create(nombre='Test', rif='J001')
        admin = User.objects.create_user('admin_t', password='admin1234', is_staff=True)
        self.client = Client()
        self.client.login(username='admin_t', password='admin1234')

    def _set_edad(self, horas):
        momento = timezone.now() - timezone.timedelta(hours=horas)
        Moneda.objects.filter(pk=self.moneda.pk).update(ultima_actualizacion=momento)

    # ── Polling endpoint ───────────────────────────────────────────

    def test_tasa_fresca_no_vencida(self):
        r = self.client.get(reverse('pos:tasa_estado'))
        self.assertFalse(r.json()['tasa_vencida'])

    def test_25h_no_vencida(self):
        """Con 25 horas de antigüedad la tasa aún no debe estar vencida."""
        self._set_edad(25)
        r = self.client.get(reverse('pos:tasa_estado'))
        self.assertFalse(r.json()['tasa_vencida'])

    def test_27h_vencida(self):
        """Con 27 horas de antigüedad la tasa debe marcarse como vencida."""
        self._set_edad(27)
        r = self.client.get(reverse('pos:tasa_estado'))
        self.assertTrue(r.json()['tasa_vencida'])

    def test_limite_exacto_26h_vencida(self):
        """En exactamente 26 horas + 1 segundo ya está vencida."""
        momento = timezone.now() - timezone.timedelta(hours=26, seconds=1)
        Moneda.objects.filter(pk=self.moneda.pk).update(ultima_actualizacion=momento)
        r = self.client.get(reverse('pos:tasa_estado'))
        self.assertTrue(r.json()['tasa_vencida'])

    def test_25h59min_no_vencida(self):
        """A 25h59m aún está dentro del umbral."""
        momento = timezone.now() - timezone.timedelta(hours=25, minutes=59)
        Moneda.objects.filter(pk=self.moneda.pk).update(ultima_actualizacion=momento)
        r = self.client.get(reverse('pos:tasa_estado'))
        self.assertFalse(r.json()['tasa_vencida'])

    # ── Vista de venta (render inicial) ───────────────────────────

    def test_pos_venta_25h_no_bloqueado(self):
        self._set_edad(25)
        r = self.client.get(reverse('pos:venta'))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.context['tasa_vencida'])

    def test_pos_venta_27h_bloqueado(self):
        self._set_edad(27)
        r = self.client.get(reverse('pos:venta'))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context['tasa_vencida'])
