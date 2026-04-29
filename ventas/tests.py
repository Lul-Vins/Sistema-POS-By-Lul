from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
import json

from configuracion.models import Moneda, Empresa
from inventario.models import Producto, Categoria
from .models import Venta, DetalleVenta, ContadorFactura
from .templatetags.pos_extras import formato_cantidad


# ── Fixture compartido ─────────────────────────────────────────────

def crear_escenario_base():
    """Crea Moneda, Empresa, Producto y usuarios admin/cajero."""
    moneda = Moneda.objects.first()
    moneda.tasa_cambio = 50
    moneda.save(update_fields=['tasa_cambio'])
    empresa = Empresa.objects.create(nombre='Test SA', rif='J123456789')
    cat     = Categoria.objects.create(nombre='General')
    prod    = Producto.objects.create(
        nombre='Agua 500ml', precio_usd=1, costo_usd=0.5,
        stock_actual=10, stock_minimo=2, categoria=cat,
    )
    admin  = User.objects.create_user('admin_t',  password='admin1234', is_staff=True)
    cajero = User.objects.create_user('cajero_t', password='caj1234',   is_staff=False)
    return moneda, empresa, prod, admin, cajero


# ══════════════════════════════════════════════════════════════════
# Modelo Venta — lógica de negocio core
# ══════════════════════════════════════════════════════════════════

class CrearDesdeCarritoTests(TestCase):

    def setUp(self):
        self.moneda, _, self.prod, self.admin, _ = crear_escenario_base()

    # ── Camino feliz ───────────────────────────────────────────────

    def test_crea_venta_y_detalle(self):
        carrito = [{'producto': self.prod, 'cantidad': 2}]
        venta   = Venta.crear_desde_carrito(carrito, 'EFECTIVO_BS', vendedor=self.admin)

        self.assertEqual(Venta.objects.count(), 1)
        self.assertEqual(venta.detalles.count(), 1)
        self.assertEqual(venta.estado, 'COMPLETADA')

    def test_descuenta_stock(self):
        carrito = [{'producto': self.prod, 'cantidad': 3}]
        Venta.crear_desde_carrito(carrito, 'EFECTIVO_USD')

        self.prod.refresh_from_db()
        self.assertEqual(self.prod.stock_actual, 7)  # 10 - 3

    def test_totales_correctos(self):
        # precio_usd=1, cantidad=2, tasa=50 → total_usd=2, total_bs=100
        carrito = [{'producto': self.prod, 'cantidad': 2}]
        venta   = Venta.crear_desde_carrito(carrito, 'EFECTIVO_BS')

        self.assertEqual(float(venta.total_usd), 2.0)
        self.assertEqual(float(venta.total_bs),  100.0)

    def test_guarda_vendedor(self):
        carrito = [{'producto': self.prod, 'cantidad': 1}]
        venta   = Venta.crear_desde_carrito(carrito, 'PAGO_MOVIL', vendedor=self.admin)

        self.assertEqual(venta.vendedor, self.admin)

    def test_carrito_multiple_productos(self):
        prod2 = Producto.objects.create(
            nombre='Jugo 1L', precio_usd=2, stock_actual=5, stock_minimo=1,
        )
        carrito = [
            {'producto': self.prod, 'cantidad': 1},
            {'producto': prod2,     'cantidad': 2},
        ]
        venta = Venta.crear_desde_carrito(carrito, 'TRANSFERENCIA')

        # total_usd = 1*1 + 2*2 = 5
        self.assertEqual(float(venta.total_usd), 5.0)
        self.assertEqual(venta.detalles.count(), 2)

    # ── Casos de error — rollback ──────────────────────────────────

    def test_stock_insuficiente_lanza_error(self):
        carrito = [{'producto': self.prod, 'cantidad': 99}]

        with self.assertRaises(ValueError) as ctx:
            Venta.crear_desde_carrito(carrito, 'EFECTIVO_BS')

        self.assertIn('Stock insuficiente', str(ctx.exception))

    def test_stock_insuficiente_no_crea_venta(self):
        carrito = [{'producto': self.prod, 'cantidad': 99}]
        try:
            Venta.crear_desde_carrito(carrito, 'EFECTIVO_BS')
        except ValueError:
            pass

        self.assertEqual(Venta.objects.count(), 0)

    def test_stock_insuficiente_no_modifica_stock(self):
        carrito = [{'producto': self.prod, 'cantidad': 99}]
        try:
            Venta.crear_desde_carrito(carrito, 'EFECTIVO_BS')
        except ValueError:
            pass

        self.prod.refresh_from_db()
        self.assertEqual(self.prod.stock_actual, 10)  # sin cambios

    def test_sin_tasa_lanza_error(self):
        Moneda.objects.all().delete()
        carrito = [{'producto': self.prod, 'cantidad': 1}]

        with self.assertRaises(ValueError):
            Venta.crear_desde_carrito(carrito, 'EFECTIVO_BS')


# ══════════════════════════════════════════════════════════════════
# Vista procesar_venta
# ══════════════════════════════════════════════════════════════════

class ProcesarVentaViewTests(TestCase):

    def setUp(self):
        self.moneda, self.empresa, self.prod, self.admin, self.cajero = crear_escenario_base()
        self.client = Client()
        self.url    = reverse('pos:procesar_venta')

    def _post(self, carrito, metodo='EFECTIVO_BS'):
        return self.client.post(
            self.url,
            data=json.dumps({'carrito': carrito, 'metodo_pago': metodo}),
            content_type='application/json',
        )

    def test_requiere_login(self):
        r = self._post([{'id': self.prod.id, 'cantidad': 1}])
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login/', r['Location'])

    def test_cajero_puede_vender(self):
        self.client.login(username='cajero_t', password='caj1234')
        r = self._post([{'id': self.prod.id, 'cantidad': 1}])
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['ok'])

    def test_carrito_vacio_retorna_400(self):
        self.client.login(username='cajero_t', password='caj1234')
        r = self._post([])
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()['ok'])

    def test_metodo_invalido_retorna_400(self):
        self.client.login(username='cajero_t', password='caj1234')
        r = self._post([{'id': self.prod.id, 'cantidad': 1}], metodo='BITCOIN')
        self.assertEqual(r.status_code, 400)

    def test_stock_insuficiente_retorna_400(self):
        self.client.login(username='cajero_t', password='caj1234')
        r = self._post([{'id': self.prod.id, 'cantidad': 999}])
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()['ok'])

    def test_stock_insuficiente_no_crea_venta(self):
        self.client.login(username='cajero_t', password='caj1234')
        self._post([{'id': self.prod.id, 'cantidad': 999}])
        self.assertEqual(Venta.objects.count(), 0)

    def test_respuesta_incluye_totales(self):
        self.client.login(username='cajero_t', password='caj1234')
        r    = self._post([{'id': self.prod.id, 'cantidad': 2}])
        data = r.json()
        self.assertIn('total_usd', data)
        self.assertIn('total_bs',  data)
        self.assertEqual(data['total_usd'], 2.0)
        self.assertEqual(data['total_bs'],  100.0)

    def test_asigna_vendedor(self):
        self.client.login(username='cajero_t', password='caj1234')
        self._post([{'id': self.prod.id, 'cantidad': 1}])
        venta = Venta.objects.first()
        self.assertEqual(venta.vendedor.username, 'cajero_t')


# ══════════════════════════════════════════════════════════════════
# Vista anular_venta
# ══════════════════════════════════════════════════════════════════

class AnularVentaTests(TestCase):

    def setUp(self):
        self.moneda, _, self.prod, self.admin, self.cajero = crear_escenario_base()
        self.client = Client()
        self.client.login(username='admin_t', password='admin1234')

        carrito    = [{'producto': self.prod, 'cantidad': 3}]
        self.venta = Venta.crear_desde_carrito(carrito, 'EFECTIVO_BS', vendedor=self.admin)

    def _anular(self, pk):
        return self.client.post(reverse('reportes:anular_venta', args=[pk]))

    def test_anula_correctamente(self):
        r = self._anular(self.venta.pk)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['ok'])
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.estado, 'ANULADA')

    def test_revierte_stock(self):
        self._anular(self.venta.pk)
        self.prod.refresh_from_db()
        self.assertEqual(self.prod.stock_actual, 10)  # vuelve al original

    def test_anular_dos_veces_retorna_400(self):
        self._anular(self.venta.pk)
        r = self._anular(self.venta.pk)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()['ok'])

    def test_cajero_no_puede_anular(self):
        self.client.logout()
        self.client.login(username='cajero_t', password='caj1234')
        r = self._anular(self.venta.pk)
        self.assertEqual(r.status_code, 302)


# ══════════════════════════════════════════════════════════════════
# Vista tasa_estado (polling)
# ══════════════════════════════════════════════════════════════════

class TasaEstadoTests(TestCase):

    def setUp(self):
        self.moneda, _, _, _, self.cajero = crear_escenario_base()
        self.client = Client()
        self.client.login(username='cajero_t', password='caj1234')
        self.url = reverse('pos:tasa_estado')

    def test_requiere_login(self):
        self.client.logout()
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)

    def test_tasa_fresca_no_vencida(self):
        r    = self.client.get(self.url)
        data = r.json()
        self.assertFalse(data['tasa_vencida'])
        self.assertEqual(data['tasa'], 50.0)

    def test_tasa_vencida_cuando_supera_15h(self):
        momento_viejo = timezone.now() - timezone.timedelta(hours=16)
        Moneda.objects.filter(pk=self.moneda.pk).update(ultima_actualizacion=momento_viejo)

        r    = self.client.get(self.url)
        data = r.json()
        self.assertTrue(data['tasa_vencida'])

    def test_limite_exacto_15h_no_vencida(self):
        momento = timezone.now() - timezone.timedelta(hours=14, minutes=59)
        Moneda.objects.filter(pk=self.moneda.pk).update(ultima_actualizacion=momento)

        r    = self.client.get(self.url)
        data = r.json()
        self.assertFalse(data['tasa_vencida'])

    def test_sin_moneda_retorna_vencida(self):
        Moneda.objects.all().delete()
        r    = self.client.get(self.url)
        data = r.json()
        self.assertTrue(data['tasa_vencida'])
        self.assertIsNone(data['tasa'])


# ══════════════════════════════════════════════════════════════════
# Número correlativo de factura (SENIAT)
# ══════════════════════════════════════════════════════════════════

class NumeroCorrelativoTests(TestCase):

    def setUp(self):
        self.moneda, _, self.prod, self.admin, _ = crear_escenario_base()

    def _venta(self):
        return Venta.crear_desde_carrito(
            [{'producto': self.prod, 'cantidad': 1}], 'EFECTIVO_BS'
        )

    def test_primera_venta_tiene_numero_1(self):
        venta = self._venta()
        self.assertEqual(venta.numero_factura, 1)

    def test_segunda_venta_tiene_numero_2(self):
        self._venta()
        venta2 = self._venta()
        self.assertEqual(venta2.numero_factura, 2)

    def test_numeros_son_consecutivos(self):
        ventas = [self._venta() for _ in range(5)]
        numeros = [v.numero_factura for v in ventas]
        self.assertEqual(numeros, [1, 2, 3, 4, 5])

    def test_formato_ocho_digitos(self):
        venta = self._venta()
        self.assertEqual(venta.numero_fmt, '00000001')

    def test_formato_con_numero_alto(self):
        ContadorFactura.objects.create(ultimo_numero=999)
        venta = self._venta()
        self.assertEqual(venta.numero_fmt, '00001000')

    def test_numero_factura_es_unico(self):
        v1 = self._venta()
        v2 = self._venta()
        self.assertNotEqual(v1.numero_factura, v2.numero_factura)

    def test_rollback_no_consume_numero(self):
        """Si la venta falla (stock insuficiente), el número no se asigna."""
        try:
            Venta.crear_desde_carrito(
                [{'producto': self.prod, 'cantidad': 999}], 'EFECTIVO_BS'
            )
        except ValueError:
            pass
        contador = ContadorFactura.objects.first()
        self.assertIsNone(contador)

    def test_numero_fmt_sin_numero_factura(self):
        """Ventas antiguas sin numero_factura muestran #pk como fallback."""
        venta = self._venta()
        venta.numero_factura = None
        self.assertIn('#', venta.numero_fmt)


# ══════════════════════════════════════════════════════════════════
# Decoradores de autenticación
# ══════════════════════════════════════════════════════════════════

class DecoradoresTests(TestCase):

    def setUp(self):
        crear_escenario_base()
        self.client = Client()

    def test_sin_login_redirige_a_login(self):
        r = self.client.get(reverse('pos:venta'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login/', r['Location'])

    def test_cajero_puede_ver_pos(self):
        self.client.login(username='cajero_t', password='caj1234')
        r = self.client.get(reverse('pos:venta'))
        self.assertEqual(r.status_code, 200)

    def test_cajero_no_accede_a_inventario(self):
        self.client.login(username='cajero_t', password='caj1234')
        r = self.client.get(reverse('inventario:index'))
        self.assertRedirects(r, reverse('pos:venta'), fetch_redirect_response=False)

    def test_cajero_no_accede_a_reportes(self):
        self.client.login(username='cajero_t', password='caj1234')
        r = self.client.get(reverse('reportes:index'))
        self.assertRedirects(r, reverse('pos:venta'), fetch_redirect_response=False)

    def test_admin_accede_a_inventario(self):
        self.client.login(username='admin_t', password='admin1234')
        r = self.client.get(reverse('inventario:index'))
        self.assertEqual(r.status_code, 200)

    def test_admin_accede_a_reportes(self):
        self.client.login(username='admin_t', password='admin1234')
        r = self.client.get(reverse('reportes:index'))
        self.assertEqual(r.status_code, 200)


# ══════════════════════════════════════════════════════════════════
# Filtro formato_cantidad (templatetag pos_extras)
# ══════════════════════════════════════════════════════════════════

class FormatoCantidadTests(TestCase):

    def test_menos_de_un_kg_muestra_gramos(self):
        self.assertEqual(formato_cantidad(Decimal('0.300'), True), '300 gr')

    def test_gramos_pequeños(self):
        self.assertEqual(formato_cantidad(Decimal('0.050'), True), '50 gr')

    def test_exactamente_un_kg(self):
        self.assertEqual(formato_cantidad(Decimal('1.000'), True), '1 kg')

    def test_kg_con_decimal(self):
        self.assertEqual(formato_cantidad(Decimal('1.500'), True), '1,5 kg')

    def test_kg_grande(self):
        self.assertEqual(formato_cantidad(Decimal('50.444'), True), '50,444 kg')

    def test_sin_ceros_innecesarios(self):
        self.assertEqual(formato_cantidad(Decimal('50.400'), True), '50,4 kg')

    def test_producto_por_unidad_retorna_entero(self):
        self.assertEqual(formato_cantidad(Decimal('2.000'), False), '2')

    def test_producto_unidad_cantidad_mayor(self):
        self.assertEqual(formato_cantidad(Decimal('15.000'), False), '15')


# ══════════════════════════════════════════════════════════════════
# Ventas con productos por kilo
# ══════════════════════════════════════════════════════════════════

class VentaKgTests(TestCase):

    def setUp(self):
        self.moneda, _, _, self.admin, self.cajero = crear_escenario_base()
        self.prod_kg = Producto.objects.create(
            nombre='Carne', precio_usd=5,
            stock_actual=Decimal('10.000'), stock_minimo=Decimal('1.000'),
            vendido_por_peso=True,
        )
        self.client = Client()
        self.client.login(username='cajero_t', password='caj1234')

    def test_venta_kg_descuenta_stock_decimal(self):
        carrito = [{'producto': self.prod_kg, 'cantidad': Decimal('0.300')}]
        Venta.crear_desde_carrito(carrito, 'EFECTIVO_BS')
        self.prod_kg.refresh_from_db()
        self.assertEqual(self.prod_kg.stock_actual, Decimal('9.700'))

    def test_venta_kg_via_vista(self):
        r = self.client.post(
            reverse('pos:procesar_venta'),
            data=json.dumps({
                'carrito': [{'id': self.prod_kg.id, 'cantidad': 0.5}],
                'metodo_pago': 'EFECTIVO_BS',
            }),
            content_type='application/json',
        )
        self.assertTrue(r.json()['ok'])
        self.prod_kg.refresh_from_db()
        self.assertAlmostEqual(float(self.prod_kg.stock_actual), 9.5, places=2)

    def test_stock_insuficiente_kg(self):
        carrito = [{'producto': self.prod_kg, 'cantidad': Decimal('999.000')}]
        with self.assertRaises(ValueError):
            Venta.crear_desde_carrito(carrito, 'EFECTIVO_BS')

    def test_detalle_venta_cantidad_decimal_guardada(self):
        carrito = [{'producto': self.prod_kg, 'cantidad': Decimal('1.250')}]
        venta = Venta.crear_desde_carrito(carrito, 'EFECTIVO_BS')
        detalle = venta.detalles.first()
        self.assertEqual(detalle.cantidad, Decimal('1.250'))


# ══════════════════════════════════════════════════════════════════
# Validación de inputs en procesar_venta
# ══════════════════════════════════════════════════════════════════

class ValidacionProcesarVentaTests(TestCase):

    def setUp(self):
        self.moneda, self.empresa, self.prod, self.admin, self.cajero = crear_escenario_base()
        self.client = Client()
        self.client.login(username='cajero_t', password='caj1234')
        self.url = reverse('pos:procesar_venta')

    def _post(self, data):
        return self.client.post(
            self.url,
            data=json.dumps(data),
            content_type='application/json',
        )

    def test_notas_demasiado_largas_rechazadas(self):
        r = self._post({
            'carrito': [{'id': self.prod.id, 'cantidad': 1}],
            'metodo_pago': 'EFECTIVO_BS',
            'notas': 'x' * 501,
        })
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()['ok'])

    def test_notas_en_limite_aceptadas(self):
        r = self._post({
            'carrito': [{'id': self.prod.id, 'cantidad': 1}],
            'metodo_pago': 'EFECTIVO_BS',
            'notas': 'x' * 500,
        })
        self.assertTrue(r.json()['ok'])

    def test_monto_recibido_negativo_rechazado(self):
        r = self._post({
            'carrito': [{'id': self.prod.id, 'cantidad': 1}],
            'metodo_pago': 'EFECTIVO_BS',
            'monto_recibido': -5,
        })
        self.assertEqual(r.status_code, 400)

    def test_monto_recibido_excesivo_rechazado(self):
        r = self._post({
            'carrito': [{'id': self.prod.id, 'cantidad': 1}],
            'metodo_pago': 'EFECTIVO_BS',
            'monto_recibido': 10_000_000,
        })
        self.assertEqual(r.status_code, 400)

    def test_monto_recibido_valido_aceptado(self):
        r = self._post({
            'carrito': [{'id': self.prod.id, 'cantidad': 1}],
            'metodo_pago': 'EFECTIVO_BS',
            'monto_recibido': 100,
        })
        self.assertTrue(r.json()['ok'])
