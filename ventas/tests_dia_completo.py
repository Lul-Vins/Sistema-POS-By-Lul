"""
Simulacion de un dia completo de operacion del POS.

Cubre desde la primera instalacion hasta el cierre de caja, pasando por
todas las funcionalidades: configuracion, inventario, ventas con cada
metodo de pago, fiados, reportes y cierre de caja.

Ejecutar con:
    python manage.py test ventas.tests_dia_completo -v 2
"""
from decimal import Decimal
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
import json

from configuracion.models import Empresa, Moneda
from inventario.models import Producto, Categoria
from ventas.models import Venta, DetalleVenta, ContadorFactura, ContadorControl
from reportes.models import CierreCaja
from fiados.models import Cliente, Fiado, DetalleFiado, PagoFiado


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers compartidos
# ─────────────────────────────────────────────────────────────────────────────

def _post_json(client, url, data):
    return client.post(url, json.dumps(data), content_type='application/json')


def _crear_escenario_base():
    """
    Crea el estado minimo que necesitan la mayoria de tests:
    usuarios, moneda, empresa, categorias y productos.
    Retorna un dict con todas las referencias.
    """
    admin = User.objects.create_user('admin', password='1234', is_staff=True,
                                     first_name='Carlos', last_name='Admin')
    cajero = User.objects.create_user('cajero', password='4321', is_staff=False,
                                      first_name='Luis', last_name='Cajero')

    # La migracion 0004 ya crea una Moneda con tasa=1.00 — la actualizamos.
    moneda = Moneda.objects.first()
    if moneda:
        moneda.tasa_cambio = Decimal('36.50')
        moneda.save(update_fields=['tasa_cambio'])
    else:
        moneda = Moneda.objects.create(tasa_cambio=Decimal('36.50'))

    empresa = Empresa.objects.create(nombre='Abasto El Progreso', rif='J-123456789')

    cat_lacteos  = Categoria.objects.create(nombre='Lacteos')
    cat_bebidas  = Categoria.objects.create(nombre='Bebidas')
    cat_limpieza = Categoria.objects.create(nombre='Limpieza')
    cat_snacks   = Categoria.objects.create(nombre='Snacks')

    # precio_usd es precio al publico ya CON iva incluido
    leche = Producto.objects.create(
        nombre='Leche Larga Vida 1L', categoria=cat_lacteos,
        codigo_barras='7591001000001', precio_usd=Decimal('2.50'),
        costo_usd=Decimal('1.80'), stock_actual=50, stock_minimo=10,
        alicuota_iva='EXENTO',
    )
    refresco = Producto.objects.create(
        nombre='Refresco Cola 500ml', categoria=cat_bebidas,
        codigo_barras='7591001000002', precio_usd=Decimal('1.16'),
        stock_actual=30, stock_minimo=5, alicuota_iva='GENERAL',
    )
    jabon = Producto.objects.create(
        nombre='Jabon de Tocador 100g', categoria=cat_limpieza,
        codigo_barras='7591001000003', precio_usd=Decimal('3.24'),
        stock_actual=15, stock_minimo=3, alicuota_iva='REDUCIDA',
    )
    agua = Producto.objects.create(
        nombre='Agua Mineral 600ml', categoria=cat_bebidas,
        codigo_barras='7591001000004', precio_usd=Decimal('0.75'),
        stock_actual=100, stock_minimo=20, alicuota_iva='EXENTO',
    )
    papas = Producto.objects.create(
        nombre='Papas Fritas 45g', categoria=cat_snacks,
        codigo_barras='7591001000005', precio_usd=Decimal('2.32'),
        stock_actual=20, stock_minimo=5, alicuota_iva='GENERAL',
    )

    return {
        'admin': admin, 'cajero': cajero,
        'moneda': moneda, 'empresa': empresa,
        'cat_lacteos': cat_lacteos, 'cat_bebidas': cat_bebidas,
        'cat_limpieza': cat_limpieza, 'cat_snacks': cat_snacks,
        'leche': leche, 'refresco': refresco, 'jabon': jabon,
        'agua': agua, 'papas': papas,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  FASE 1 — Primera instalacion: Configuracion
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(ALLOWED_HOSTS=['testserver'])
class PrimeraConfiguracionTest(TestCase):
    """
    Simula la primera configuracion del sistema: empresa, tasa BCV y usuarios.
    Un admin recibe el PC, abre la app por primera vez y configura todo.
    """

    def setUp(self):
        self.admin = User.objects.create_user('admin', password='1234', is_staff=True)
        self.c = Client()
        self.c.login(username='admin', password='1234')

    # ── Empresa ──────────────────────────────────────────────────────────────

    def test_c01_pagina_configuracion_accesible(self):
        """El admin puede ver la pagina de configuracion."""
        resp = self.c.get(reverse('configuracion:index'))
        self.assertEqual(resp.status_code, 200)

    def test_c02_guardar_datos_empresa(self):
        """Se guardan nombre, RIF, telefono y direccion de la empresa."""
        resp = self.c.post(reverse('configuracion:index'), {
            'nombre':    'Abasto El Progreso',
            'rif':       '123456789',
            'telefono':  '0414-1234567',
            'direccion': 'Calle Principal, Local 3',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        empresa = Empresa.objects.first()
        self.assertIsNotNone(empresa)
        self.assertEqual(empresa.nombre, 'Abasto El Progreso')
        self.assertIn('123456789', empresa.rif)

    def test_c03_empresa_requiere_nombre(self):
        """Si falta el nombre, no se guarda y vuelve el formulario con error."""
        resp = self.c.post(reverse('configuracion:index'), {'nombre': '', 'rif': '123'})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Empresa.objects.exists())

    # ── Tasa de cambio ───────────────────────────────────────────────────────

    def test_c04_configurar_tasa_cambio(self):
        """El admin actualiza la tasa BCV desde la pantalla de configuracion."""
        # La migracion 0004 ya crea una Moneda con tasa=1.00, no hace falta crear otra.
        resp = _post_json(self.c, reverse('configuracion:actualizar_tasa'), {'tasa': 36.50})
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(float(data['tasa']), 36.50)
        self.assertEqual(float(Moneda.objects.first().tasa_cambio), 36.50)

    def test_c05_tasa_cero_rechazada(self):
        """Una tasa de 0 o negativa debe ser rechazada."""
        resp = _post_json(self.c, reverse('configuracion:actualizar_tasa'), {'tasa': 0})
        self.assertFalse(resp.json()['ok'])

    def test_c06_tasa_requiere_moneda_configurada(self):
        """Si no existe Moneda, el endpoint devuelve error (no crea una)."""
        Moneda.objects.all().delete()   # eliminar la creada por la migracion
        resp = _post_json(self.c, reverse('configuracion:actualizar_tasa'), {'tasa': 36.50})
        self.assertFalse(resp.json()['ok'])

    def test_c07_tasa_estado_polling(self):
        """El endpoint de polling indica si la tasa esta vencida."""
        # Actualizar la tasa a 36.50 primero (la migracion la deja en 1.00)
        _post_json(self.c, reverse('configuracion:actualizar_tasa'), {'tasa': 36.50})
        resp = self.c.get(reverse('pos:tasa_estado'))
        data = resp.json()
        self.assertIn('tasa_vencida', data)
        self.assertEqual(float(data['tasa']), 36.50)

    # ── Gestion de usuarios ──────────────────────────────────────────────────

    def test_c08_crear_usuario_cajero(self):
        """El admin crea un usuario cajero (sin privilegios de admin)."""
        resp = _post_json(self.c, reverse('configuracion:crear_usuario'), {
            'nombre':   'Luis Sanchez',
            'username': 'cajero1',
            'password': 'clave123',
            'es_admin': False,
        })
        data = resp.json()
        self.assertTrue(data['ok'])
        u = User.objects.get(username='cajero1')
        self.assertFalse(u.is_staff)

    def test_c09_crear_usuario_admin_secundario(self):
        """Se puede crear un segundo administrador."""
        resp = _post_json(self.c, reverse('configuracion:crear_usuario'), {
            'nombre':   'Maria Torres',
            'username': 'admin2',
            'password': 'clave123',
            'es_admin': True,
        })
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertTrue(User.objects.get(username='admin2').is_staff)

    def test_c10_usuario_duplicado_rechazado(self):
        """No se puede crear dos usuarios con el mismo username."""
        payload = {'nombre': 'A', 'username': 'admin', 'password': '1234', 'es_admin': False}
        resp = _post_json(self.c, reverse('configuracion:crear_usuario'), payload)
        self.assertFalse(resp.json()['ok'])

    def test_c11_contrasena_muy_corta_rechazada(self):
        """Contrasenas de menos de 4 caracteres se rechazan."""
        resp = _post_json(self.c, reverse('configuracion:crear_usuario'), {
            'nombre': 'X', 'username': 'x1', 'password': '12', 'es_admin': False,
        })
        self.assertFalse(resp.json()['ok'])

    def test_c12_cajero_no_accede_a_configuracion(self):
        """Un cajero sin is_staff es redirigido al POS si intenta entrar a configuracion."""
        cajero = User.objects.create_user('cajero', password='4321', is_staff=False)
        c2 = Client()
        c2.login(username='cajero', password='4321')
        resp = c2.get(reverse('configuracion:index'))
        self.assertEqual(resp.status_code, 302)


# ─────────────────────────────────────────────────────────────────────────────
#  FASE 2 — Inventario: Categorias y productos
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(ALLOWED_HOSTS=['testserver'])
class InventarioSetupTest(TestCase):
    """
    El admin carga el catalogo de productos antes de abrir el negocio:
    crea categorias, crea productos con distintas alicuotas de IVA,
    verifica busquedas y deteccion de stock bajo.
    """

    def setUp(self):
        sc = _crear_escenario_base()
        self.admin  = sc['admin']
        self.cajero = sc['cajero']
        self.leche  = sc['leche']
        self.refresco = sc['refresco']
        self.cat_bebidas = sc['cat_bebidas']
        self.c = Client()
        self.c.login(username='admin', password='1234')

    # ── Categorias ───────────────────────────────────────────────────────────

    def test_i01_crear_categoria(self):
        """Se puede crear una nueva categoria via AJAX."""
        resp = _post_json(self.c, reverse('inventario:crear_categoria'), {'nombre': 'Granos'})
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertTrue(Categoria.objects.filter(nombre='Granos').exists())

    def test_i02_categoria_duplicada_rechazada(self):
        """No se permite crear dos categorias con el mismo nombre (case-insensitive)."""
        _post_json(self.c, reverse('inventario:crear_categoria'), {'nombre': 'Granos'})
        resp = _post_json(self.c, reverse('inventario:crear_categoria'), {'nombre': 'granos'})
        self.assertFalse(resp.json()['ok'])

    def test_i03_eliminar_categoria_limpia_productos(self):
        """Eliminar una categoria deja los productos de esa categoria sin categoria (SET_NULL)."""
        resp = _post_json(self.c, reverse('inventario:eliminar_categoria',
                                          kwargs={'pk': self.cat_bebidas.pk}), {})
        self.assertTrue(resp.json()['ok'])
        self.refresco.refresh_from_db()
        self.assertIsNone(self.refresco.categoria)

    def test_i04_listar_categorias_retorna_json(self):
        """GET /inventario/categorias/ devuelve la lista de categorias en JSON."""
        resp = self.c.get(reverse('inventario:lista_categorias'))
        data = resp.json()
        nombres = [c['nombre'] for c in data['categorias']]
        self.assertIn('Bebidas', nombres)

    # ── Productos ────────────────────────────────────────────────────────────

    def test_i05_crear_producto_exento(self):
        """Se puede crear un producto con alicuota EXENTO."""
        resp = _post_json(self.c, reverse('inventario:guardar_producto'), {
            'pk': 0, 'nombre': 'Arroz Blanco 1kg', 'precio_usd': '1.50',
            'stock_actual': 100, 'stock_minimo': 20, 'alicuota_iva': 'EXENTO',
        })
        self.assertTrue(resp.json()['ok'])
        p = Producto.objects.get(nombre='Arroz Blanco 1kg')
        self.assertEqual(p.alicuota_iva, 'EXENTO')

    def test_i06_crear_producto_iva_general(self):
        """Se puede crear un producto con alicuota GENERAL (16%)."""
        resp = _post_json(self.c, reverse('inventario:guardar_producto'), {
            'pk': 0, 'nombre': 'Galletas Surtidas', 'precio_usd': '1.16',
            'stock_actual': 50, 'alicuota_iva': 'GENERAL',
        })
        self.assertTrue(resp.json()['ok'])
        self.assertEqual(Producto.objects.get(nombre='Galletas Surtidas').alicuota_iva, 'GENERAL')

    def test_i07_crear_producto_iva_reducida(self):
        """Se puede crear un producto con alicuota REDUCIDA (8%)."""
        resp = _post_json(self.c, reverse('inventario:guardar_producto'), {
            'pk': 0, 'nombre': 'Detergente 250g', 'precio_usd': '3.24',
            'stock_actual': 25, 'alicuota_iva': 'REDUCIDA',
        })
        self.assertTrue(resp.json()['ok'])

    def test_i08_editar_producto_existente(self):
        """Se puede actualizar el precio y stock de un producto existente."""
        resp = _post_json(self.c, reverse('inventario:guardar_producto'), {
            'pk': self.leche.pk, 'nombre': 'Leche Larga Vida 1L',
            'precio_usd': '2.75', 'stock_actual': 60, 'alicuota_iva': 'EXENTO',
        })
        self.assertTrue(resp.json()['ok'])
        self.leche.refresh_from_db()
        self.assertEqual(self.leche.precio_usd, Decimal('2.75'))
        self.assertEqual(self.leche.stock_actual, 60)

    def test_i09_precio_cero_rechazado(self):
        """Un precio de 0 o negativo es rechazado."""
        resp = _post_json(self.c, reverse('inventario:guardar_producto'), {
            'pk': 0, 'nombre': 'Producto Malo', 'precio_usd': '0', 'stock_actual': 10,
        })
        self.assertFalse(resp.json()['ok'])

    def test_i10_alicuota_invalida_rechazada(self):
        """Una alicuota que no sea GENERAL/REDUCIDA/EXENTO es rechazada."""
        resp = _post_json(self.c, reverse('inventario:guardar_producto'), {
            'pk': 0, 'nombre': 'Prod X', 'precio_usd': '1.00',
            'stock_actual': 5, 'alicuota_iva': 'ESPECIAL',
        })
        self.assertFalse(resp.json()['ok'])

    # ── Busqueda y filtros ───────────────────────────────────────────────────

    def test_i11_buscar_por_nombre(self):
        """La busqueda retorna productos cuyo nombre contiene el termino."""
        resp = self.c.get(reverse('pos:buscar_productos'), {'q': 'Leche'})
        data = resp.json()
        nombres = [p['nombre'] for p in data['productos']]
        self.assertIn('Leche Larga Vida 1L', nombres)

    def test_i12_buscar_por_codigo_barras_exacto(self):
        """Buscar por codigo de barras exacto retorna el producto correcto."""
        resp = self.c.get(reverse('pos:buscar_productos'), {'q': '7591001000001'})
        data = resp.json()
        self.assertEqual(len(data['productos']), 1)
        self.assertEqual(data['productos'][0]['nombre'], 'Leche Larga Vida 1L')

    def test_i13_filtrar_por_categoria(self):
        """Filtrar por cat_id retorna solo los productos de esa categoria."""
        resp = self.c.get(reverse('pos:buscar_productos'),
                          {'cat': self.cat_bebidas.pk})
        data = resp.json()
        nombres = [p['nombre'] for p in data['productos']]
        self.assertIn('Refresco Cola 500ml', nombres)
        self.assertNotIn('Leche Larga Vida 1L', nombres)

    def test_i14_busqueda_corta_sin_cat_retorna_vacio(self):
        """Una busqueda de menos de 2 caracteres sin categoria retorna lista vacia."""
        resp = self.c.get(reverse('pos:buscar_productos'), {'q': 'L'})
        self.assertEqual(resp.json()['productos'], [])

    def test_i15_stock_bajo_detectado_en_producto(self):
        """La propiedad stock_bajo es True cuando stock_actual < stock_minimo (operador estricto)."""
        producto_bajo = Producto.objects.create(
            nombre='Producto bajo', precio_usd='1.00',
            stock_actual=3, stock_minimo=5,
        )
        self.assertTrue(producto_bajo.stock_bajo)
        producto_ok = Producto.objects.create(
            nombre='Producto ok', precio_usd='1.00',
            stock_actual=10, stock_minimo=5,
        )
        self.assertFalse(producto_ok.stock_bajo)

    def test_i16_eliminar_producto_sin_ventas(self):
        """Un producto sin ventas puede eliminarse directamente."""
        nuevo = Producto.objects.create(nombre='Eliminar esto', precio_usd='1.00', stock_actual=0)
        resp = self.c.post(reverse('inventario:eliminar_producto', kwargs={'pk': nuevo.pk}))
        self.assertTrue(resp.json()['ok'])
        self.assertFalse(Producto.objects.filter(pk=nuevo.pk).exists())

    def test_i17_cajero_no_accede_al_inventario(self):
        """Un cajero no puede acceder a la pantalla de inventario."""
        c2 = Client()
        c2.login(username='cajero', password='4321')
        resp = c2.get(reverse('inventario:index'))
        self.assertEqual(resp.status_code, 302)


# ─────────────────────────────────────────────────────────────────────────────
#  FASE 3 — Ventas: todos los metodos de pago
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(ALLOWED_HOSTS=['testserver'])
class VentasDelDiaTest(TestCase):
    """
    El cajero abre el negocio y realiza ventas con todos los metodos de pago.
    Se verifica el descuento de stock, el desglose fiscal (IVA SENIAT)
    y la numeracion correlativa de facturas.
    """

    def setUp(self):
        sc = _crear_escenario_base()
        self.admin   = sc['admin']
        self.cajero  = sc['cajero']
        self.moneda  = sc['moneda']
        self.leche   = sc['leche']
        self.refresco = sc['refresco']
        self.jabon   = sc['jabon']
        self.agua    = sc['agua']
        self.papas   = sc['papas']
        # El cajero hace las ventas
        self.c = Client()
        self.c.login(username='cajero', password='4321')
        self.url_procesar = reverse('pos:procesar_venta')
        self.url_pos      = reverse('pos:venta')

    def _venta(self, carrito, metodo_pago, monto_recibido=None, vuelto=None, notas=''):
        """Shortcut para procesar una venta via HTTP."""
        return _post_json(self.c, self.url_procesar, {
            'carrito':        carrito,
            'metodo_pago':    metodo_pago,
            'notas':          notas,
            'monto_recibido': monto_recibido,
            'vuelto':         vuelto,
        })

    # ── POS accesible ────────────────────────────────────────────────────────

    def test_v01_cajero_ve_pantalla_pos(self):
        """El cajero puede abrir la pantalla del POS."""
        resp = self.c.get(self.url_pos)
        self.assertEqual(resp.status_code, 200)

    # ── Metodos de pago ──────────────────────────────────────────────────────

    def test_v02_venta_efectivo_usd(self):
        """Venta pagada en dolares en efectivo — se registra correctamente."""
        resp = self._venta(
            [{'id': self.leche.pk, 'cantidad': 2}],
            'EFECTIVO_USD', monto_recibido=5.00, vuelto=0.00,
        )
        data = resp.json()
        self.assertTrue(data['ok'])
        venta = Venta.objects.get(pk=data['venta_id'])
        self.assertEqual(venta.metodo_pago, 'EFECTIVO_USD')
        self.assertEqual(venta.total_usd, Decimal('5.00'))   # 2.50 x 2

    def test_v03_venta_efectivo_bs_con_vuelto(self):
        """Venta en bolivares con vuelto — se almacenan monto_recibido y vuelto."""
        total_bs = float(Decimal('1.16') * Decimal('36.50'))  # 42.34
        resp = self._venta(
            [{'id': self.refresco.pk, 'cantidad': 1}],
            'EFECTIVO_BS', monto_recibido=50.00, vuelto=round(50.00 - total_bs, 2),
        )
        data = resp.json()
        self.assertTrue(data['ok'])
        venta = Venta.objects.get(pk=data['venta_id'])
        self.assertEqual(venta.metodo_pago, 'EFECTIVO_BS')
        self.assertIsNotNone(venta.monto_recibido)
        self.assertIsNotNone(venta.vuelto)

    def test_v04_venta_transferencia(self):
        """Venta por transferencia bancaria."""
        resp = self._venta([{'id': self.jabon.pk, 'cantidad': 1}], 'TRANSFERENCIA')
        self.assertTrue(resp.json()['ok'])
        self.assertEqual(Venta.objects.last().metodo_pago, 'TRANSFERENCIA')

    def test_v05_venta_pago_movil(self):
        """Venta por Pago Movil."""
        resp = self._venta([{'id': self.agua.pk, 'cantidad': 5}], 'PAGO_MOVIL')
        self.assertTrue(resp.json()['ok'])
        self.assertEqual(Venta.objects.last().metodo_pago, 'PAGO_MOVIL')

    def test_v06_venta_punto_de_venta_tarjeta(self):
        """Venta con punto de venta (tarjeta debito/credito)."""
        resp = self._venta([{'id': self.papas.pk, 'cantidad': 2}], 'PUNTO_DE_VENTA')
        self.assertTrue(resp.json()['ok'])

    def test_v07_venta_biopago(self):
        """Venta con Biopago (biometrico)."""
        resp = self._venta([{'id': self.leche.pk, 'cantidad': 1}], 'BIOPAGO')
        self.assertTrue(resp.json()['ok'])

    def test_v08_venta_pago_mixto(self):
        """Venta con metodo mixto (parte en USD, parte en Bs)."""
        resp = self._venta(
            [{'id': self.refresco.pk, 'cantidad': 1},
             {'id': self.jabon.pk,    'cantidad': 1}],
            'MIXTO',
        )
        self.assertTrue(resp.json()['ok'])

    # ── Stock ────────────────────────────────────────────────────────────────

    def test_v09_venta_descuenta_stock(self):
        """El stock del producto disminuye exactamente en la cantidad vendida."""
        stock_antes = self.leche.stock_actual
        resp = self._venta([{'id': self.leche.pk, 'cantidad': 3}], 'EFECTIVO_USD')
        self.assertTrue(resp.json()['ok'])
        self.leche.refresh_from_db()
        self.assertEqual(self.leche.stock_actual, stock_antes - 3)

    def test_v10_venta_rechazada_sin_stock(self):
        """Si el stock es insuficiente, la venta se rechaza con error claro."""
        self.papas.stock_actual = 1
        self.papas.save()
        resp = self._venta([{'id': self.papas.pk, 'cantidad': 5}], 'EFECTIVO_USD')
        data = resp.json()
        self.assertFalse(data['ok'])
        self.assertIn('Stock insuficiente', data['error'])
        # No se creo ninguna venta
        self.assertFalse(Venta.objects.filter(
            detalles__producto=self.papas).exists())

    def test_v11_carrito_vacio_rechazado(self):
        """No se puede procesar una venta con el carrito vacio."""
        resp = self._venta([], 'EFECTIVO_USD')
        self.assertFalse(resp.json()['ok'])

    def test_v12_metodo_pago_invalido_rechazado(self):
        """Un metodo de pago que no existe en METODO_PAGO es rechazado."""
        resp = self._venta([{'id': self.leche.pk, 'cantidad': 1}], 'BITCOIN')
        self.assertFalse(resp.json()['ok'])

    # ── Numeracion SENIAT ────────────────────────────────────────────────────

    def test_v13_numero_factura_correlativo(self):
        """Las facturas se numeran correlativamente sin saltos."""
        ContadorFactura.objects.all().delete()
        self._venta([{'id': self.leche.pk, 'cantidad': 1}], 'EFECTIVO_USD')
        self._venta([{'id': self.agua.pk,  'cantidad': 1}], 'PAGO_MOVIL')
        nums = list(Venta.objects.order_by('numero_factura').values_list('numero_factura', flat=True))
        self.assertEqual(nums[0] + 1, nums[1])

    def test_v14_numero_control_correlativo(self):
        """Los numeros de control SENIAT son correlativos e independientes de la factura."""
        ContadorControl.objects.all().delete()
        self._venta([{'id': self.leche.pk, 'cantidad': 1}], 'TRANSFERENCIA')
        self._venta([{'id': self.agua.pk,  'cantidad': 1}], 'TRANSFERENCIA')
        controles = list(Venta.objects.order_by('numero_control').values_list('numero_control', flat=True))
        self.assertEqual(controles[0] + 1, controles[1])

    # ── Desglose fiscal IVA ──────────────────────────────────────────────────

    def test_v15_iva_general_desglosado_correctamente(self):
        """
        Producto GENERAL precio=1.16 USD.
        base = 1.16/1.16 = 1.00, iva = 0.16.
        """
        resp = self._venta([{'id': self.refresco.pk, 'cantidad': 1}], 'EFECTIVO_USD')
        venta = Venta.objects.get(pk=resp.json()['venta_id'])
        self.assertEqual(venta.base_imponible_usd, Decimal('1.00'))
        self.assertEqual(venta.iva_usd, Decimal('0.16'))
        self.assertEqual(venta.monto_exento_usd, Decimal('0.00'))

    def test_v16_producto_exento_no_genera_iva(self):
        """Productos EXENTO no suman base_imponible ni iva."""
        resp = self._venta([{'id': self.leche.pk, 'cantidad': 2}], 'EFECTIVO_USD')
        venta = Venta.objects.get(pk=resp.json()['venta_id'])
        self.assertEqual(venta.iva_usd, Decimal('0.00'))
        self.assertEqual(venta.base_imponible_usd, Decimal('0.00'))
        self.assertEqual(venta.monto_exento_usd, Decimal('5.00'))

    def test_v17_carrito_mixto_iva_correcto(self):
        """
        Carrito con un producto EXENTO y uno GENERAL:
        exento = 2.50, base = 1.00, iva = 0.16, total = 3.66.
        """
        resp = self._venta(
            [{'id': self.leche.pk,    'cantidad': 1},   # exento 2.50
             {'id': self.refresco.pk, 'cantidad': 1}],  # general 1.16
            'EFECTIVO_USD',
        )
        venta = Venta.objects.get(pk=resp.json()['venta_id'])
        self.assertEqual(venta.total_usd, Decimal('3.66'))
        self.assertEqual(venta.monto_exento_usd, Decimal('2.50'))
        self.assertEqual(venta.base_imponible_usd, Decimal('1.00'))
        self.assertEqual(venta.iva_usd, Decimal('0.16'))

    def test_v18_total_bs_calculado_con_tasa(self):
        """total_bs = total_usd * tasa_aplicada al momento de la venta."""
        resp = self._venta([{'id': self.refresco.pk, 'cantidad': 1}], 'EFECTIVO_USD')
        venta = Venta.objects.get(pk=resp.json()['venta_id'])
        esperado = (venta.total_usd * venta.tasa_aplicada).quantize(Decimal('0.01'))
        self.assertEqual(venta.total_bs, esperado)

    # ── Ticket ───────────────────────────────────────────────────────────────

    def test_v19_ticket_accesible_despues_de_venta(self):
        """El ticket de una venta se puede ver en /ticket/<pk>/."""
        resp = self._venta([{'id': self.agua.pk, 'cantidad': 1}], 'EFECTIVO_USD')
        venta_id = resp.json()['venta_id']
        resp2 = self.c.get(reverse('pos:ticket', kwargs={'pk': venta_id}))
        self.assertEqual(resp2.status_code, 200)

    # ── Mis ventas ───────────────────────────────────────────────────────────

    def test_v20_cajero_ve_sus_propias_ventas(self):
        """El cajero puede ver el resumen de sus ventas del dia."""
        self._venta([{'id': self.leche.pk, 'cantidad': 1}], 'EFECTIVO_USD')
        resp = self.c.get(reverse('pos:mis_ventas'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Leche')


# ─────────────────────────────────────────────────────────────────────────────
#  FASE 4 — Fiados: ventas a credito
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(ALLOWED_HOSTS=['testserver'])
class FiadosTest(TestCase):
    """
    Un cliente frecuente se lleva productos a credito (fiado).
    Se registran pagos parciales y total, y se verifica el estado del fiado.
    """

    def setUp(self):
        sc = _crear_escenario_base()
        self.admin  = sc['admin']
        self.moneda = sc['moneda']
        self.leche  = sc['leche']
        self.agua   = sc['agua']
        self.papas  = sc['papas']
        self.c = Client()
        self.c.login(username='admin', password='1234')

    def _crear_cliente(self, nombre='Pedro Perez', telefono='0414-9999999'):
        resp = _post_json(self.c, reverse('fiados:crear_cliente'), {
            'nombre': nombre, 'telefono': telefono,
        })
        return resp.json(), Cliente.objects.get(nombre=nombre)

    def _crear_fiado(self, cliente, carrito, notas=''):
        return _post_json(self.c,
            reverse('fiados:nueva_venta', kwargs={'cliente_pk': cliente.pk}),
            {'carrito': carrito, 'notas': notas},
        )

    # ── Clientes ─────────────────────────────────────────────────────────────

    def test_f01_crear_cliente(self):
        """Se puede crear un cliente de fiado con nombre y telefono."""
        data, cliente = self._crear_cliente()
        self.assertTrue(data['ok'])
        self.assertEqual(cliente.nombre, 'Pedro Perez')

    def test_f02_cliente_requiere_nombre(self):
        """No se puede crear un cliente sin nombre."""
        resp = _post_json(self.c, reverse('fiados:crear_cliente'), {'nombre': ''})
        self.assertFalse(resp.json()['ok'])

    def test_f03_editar_cliente(self):
        """Se puede actualizar el telefono. Guiones se normalizan a solo dígitos."""
        _, cliente = self._crear_cliente()
        resp = _post_json(self.c,
            reverse('fiados:editar_cliente', kwargs={'pk': cliente.pk}),
            {'nombre': 'Pedro Perez', 'telefono': '0416-1111111'},
        )
        self.assertTrue(resp.json()['ok'])
        cliente.refresh_from_db()
        self.assertEqual(cliente.telefono, '04161111111')

    # ── Venta fiada y stock ──────────────────────────────────────────────────

    def test_f04_fiado_crea_deuda_correcta(self):
        """El total del fiado es la suma de los productos del carrito."""
        _, cliente = self._crear_cliente()
        resp = self._crear_fiado(cliente, [{'id': self.agua.pk, 'cantidad': 10}])
        data = resp.json()
        self.assertTrue(data['ok'])
        # 0.75 x 10 = 7.50
        self.assertAlmostEqual(data['total_usd'], 7.50)

    def test_f05_fiado_descuenta_stock(self):
        """Crear un fiado descuenta el stock del producto."""
        stock_antes = self.agua.stock_actual
        _, cliente = self._crear_cliente()
        self._crear_fiado(cliente, [{'id': self.agua.pk, 'cantidad': 10}])
        self.agua.refresh_from_db()
        self.assertEqual(self.agua.stock_actual, stock_antes - 10)

    def test_f06_fiado_estado_inicial_pendiente(self):
        """Un fiado recien creado tiene estado PENDIENTE."""
        _, cliente = self._crear_cliente()
        self._crear_fiado(cliente, [{'id': self.leche.pk, 'cantidad': 2}])
        fiado = Fiado.objects.filter(cliente=cliente).first()
        self.assertEqual(fiado.estado, 'PENDIENTE')

    def test_f07_fiado_sin_stock_rechazado(self):
        """No se puede fiado si no hay stock suficiente."""
        self.papas.stock_actual = 1
        self.papas.save()
        _, cliente = self._crear_cliente()
        resp = self._crear_fiado(cliente, [{'id': self.papas.pk, 'cantidad': 5}])
        self.assertFalse(resp.json()['ok'])

    # ── Pagos parciales y totales ────────────────────────────────────────────

    def test_f08_pago_parcial_cambia_estado_a_parcial(self):
        """Un pago que cubre menos del 100% cambia el estado a PARCIAL."""
        _, cliente = self._crear_cliente()
        self._crear_fiado(cliente, [{'id': self.leche.pk, 'cantidad': 4}])
        fiado = Fiado.objects.filter(cliente=cliente).first()
        # total = 2.50 x 4 = 10.00 USD
        # pagar la mitad en Bs = 5 USD x 36.50 = 182.50 Bs
        resp = _post_json(self.c,
            reverse('fiados:registrar_pago', kwargs={'fiado_pk': fiado.pk}),
            {'metodo_pago': 'PAGO_MOVIL', 'monto_bs': 182.50},
        )
        data = resp.json()
        self.assertTrue(data['ok'])
        fiado.refresh_from_db()
        self.assertEqual(fiado.estado, 'PARCIAL')
        self.assertAlmostEqual(float(fiado.saldo_usd), 5.00, places=1)

    def test_f09_pago_total_cambia_estado_a_pagado(self):
        """Al pagar el saldo completo, el fiado pasa a PAGADO."""
        _, cliente = self._crear_cliente()
        self._crear_fiado(cliente, [{'id': self.agua.pk, 'cantidad': 4}])
        fiado = Fiado.objects.filter(cliente=cliente).first()
        # total = 0.75 x 4 = 3.00 USD = 109.50 Bs
        resp = _post_json(self.c,
            reverse('fiados:registrar_pago', kwargs={'fiado_pk': fiado.pk}),
            {'metodo_pago': 'EFECTIVO_BS', 'monto_bs': 109.50},
        )
        self.assertTrue(resp.json()['ok'])
        fiado.refresh_from_db()
        self.assertEqual(fiado.estado, 'PAGADO')
        self.assertEqual(fiado.saldo_usd, Decimal('0.00'))

    def test_f10_pago_en_usd(self):
        """Se puede registrar un pago directo en USD."""
        _, cliente = self._crear_cliente()
        self._crear_fiado(cliente, [{'id': self.leche.pk, 'cantidad': 2}])
        fiado = Fiado.objects.filter(cliente=cliente).first()
        # total = 5.00 USD
        resp = _post_json(self.c,
            reverse('fiados:registrar_pago', kwargs={'fiado_pk': fiado.pk}),
            {'metodo_pago': 'EFECTIVO_USD', 'monto_usd': 5.00},
        )
        self.assertTrue(resp.json()['ok'])
        fiado.refresh_from_db()
        self.assertEqual(fiado.estado, 'PAGADO')

    def test_f11_pago_excede_saldo_rechazado(self):
        """No se puede pagar mas del saldo pendiente."""
        _, cliente = self._crear_cliente()
        self._crear_fiado(cliente, [{'id': self.agua.pk, 'cantidad': 2}])
        fiado = Fiado.objects.filter(cliente=cliente).first()
        # saldo = 1.50 USD; intentar pagar 5.00 USD
        resp = _post_json(self.c,
            reverse('fiados:registrar_pago', kwargs={'fiado_pk': fiado.pk}),
            {'metodo_pago': 'EFECTIVO_USD', 'monto_usd': 5.00},
        )
        self.assertFalse(resp.json()['ok'])

    def test_f12_fiado_pagado_no_acepta_mas_pagos(self):
        """Un fiado con estado PAGADO rechaza nuevos pagos."""
        _, cliente = self._crear_cliente()
        self._crear_fiado(cliente, [{'id': self.agua.pk, 'cantidad': 1}])
        fiado = Fiado.objects.filter(cliente=cliente).first()
        # Pagar en su totalidad
        _post_json(self.c, reverse('fiados:registrar_pago', kwargs={'fiado_pk': fiado.pk}),
                   {'metodo_pago': 'EFECTIVO_USD', 'monto_usd': 0.75})
        # Intentar un segundo pago
        resp = _post_json(self.c, reverse('fiados:registrar_pago', kwargs={'fiado_pk': fiado.pk}),
                          {'metodo_pago': 'EFECTIVO_USD', 'monto_usd': 0.75})
        self.assertFalse(resp.json()['ok'])

    # ── Anulacion de fiado ───────────────────────────────────────────────────

    def test_f13_anular_fiado_pendiente_restaura_stock(self):
        """Anular un fiado devuelve el stock al inventario."""
        stock_antes = self.agua.stock_actual
        _, cliente = self._crear_cliente()
        self._crear_fiado(cliente, [{'id': self.agua.pk, 'cantidad': 8}])
        fiado = Fiado.objects.filter(cliente=cliente).first()
        resp = self.c.post(reverse('fiados:anular', kwargs={'pk': fiado.pk}))
        self.assertTrue(resp.json()['ok'])
        self.agua.refresh_from_db()
        self.assertEqual(self.agua.stock_actual, stock_antes)
        fiado.refresh_from_db()
        self.assertEqual(fiado.estado, 'ANULADO')

    def test_f14_fiado_pagado_no_se_puede_anular(self):
        """Un fiado completamente pagado no puede anularse."""
        _, cliente = self._crear_cliente()
        self._crear_fiado(cliente, [{'id': self.agua.pk, 'cantidad': 1}])
        fiado = Fiado.objects.filter(cliente=cliente).first()
        fiado.estado = 'PAGADO'
        fiado.save()
        resp = self.c.post(reverse('fiados:anular', kwargs={'pk': fiado.pk}))
        self.assertFalse(resp.json()['ok'])

    def test_f15_fiado_ya_anulado_no_se_anula_dos_veces(self):
        """No se puede anular un fiado que ya esta ANULADO."""
        _, cliente = self._crear_cliente()
        self._crear_fiado(cliente, [{'id': self.agua.pk, 'cantidad': 1}])
        fiado = Fiado.objects.filter(cliente=cliente).first()
        self.c.post(reverse('fiados:anular', kwargs={'pk': fiado.pk}))
        resp = self.c.post(reverse('fiados:anular', kwargs={'pk': fiado.pk}))
        self.assertFalse(resp.json()['ok'])

    def test_f16_detalle_cliente_muestra_saldo_actualizado(self):
        """La pagina de detalle del cliente muestra los fiados correctamente."""
        _, cliente = self._crear_cliente()
        self._crear_fiado(cliente, [{'id': self.leche.pk, 'cantidad': 1}])
        resp = self.c.get(reverse('fiados:cliente', kwargs={'pk': cliente.pk}))
        self.assertEqual(resp.status_code, 200)


# ─────────────────────────────────────────────────────────────────────────────
#  FASE 5 — Reportes y cierre de caja
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(ALLOWED_HOSTS=['testserver'])
class ReportesYCierreCajaTest(TestCase):
    """
    Al final del dia el admin revisa el reporte, anula una venta erronea
    y realiza el cierre de caja con el desglose por metodo de pago.
    El cajero hace su propio cierre de turno.
    """

    def setUp(self):
        sc = _crear_escenario_base()
        self.admin   = sc['admin']
        self.cajero  = sc['cajero']
        self.moneda  = sc['moneda']
        self.leche   = sc['leche']
        self.refresco = sc['refresco']
        self.jabon   = sc['jabon']
        self.agua    = sc['agua']
        self.papas   = sc['papas']

        # Crear varias ventas del dia usando el modelo directamente
        carrito_leche    = [{'producto': self.leche,    'cantidad': 2}]
        carrito_refresco = [{'producto': self.refresco, 'cantidad': 3}]
        carrito_jabon    = [{'producto': self.jabon,    'cantidad': 1}]
        carrito_agua     = [{'producto': self.agua,     'cantidad': 5}]

        self.v_efectivo_usd  = Venta.crear_desde_carrito(
            carrito_leche, 'EFECTIVO_USD', vendedor=self.cajero)
        self.v_transferencia = Venta.crear_desde_carrito(
            carrito_refresco, 'TRANSFERENCIA', vendedor=self.cajero)
        self.v_pago_movil    = Venta.crear_desde_carrito(
            carrito_jabon, 'PAGO_MOVIL', vendedor=self.cajero)
        self.v_punto_venta   = Venta.crear_desde_carrito(
            carrito_agua, 'PUNTO_DE_VENTA', vendedor=self.admin)

        self.c = Client()
        self.c.login(username='admin', password='1234')
        self.c_cajero = Client()
        self.c_cajero.login(username='cajero', password='4321')

    def _fecha_hoy(self):
        return timezone.localdate().isoformat()

    # ── Reporte diario ───────────────────────────────────────────────────────

    def test_r01_reporte_diario_accesible(self):
        """El admin puede ver el reporte de ventas del dia."""
        resp = self.c.get(reverse('reportes:index'))
        self.assertEqual(resp.status_code, 200)

    def test_r02_reporte_muestra_ventas_del_dia(self):
        """El reporte lista las ventas completadas de hoy."""
        resp = self.c.get(reverse('reportes:index'))
        self.assertContains(resp, 'Leche')

    def test_r03_cajero_no_accede_al_reporte_admin(self):
        """El cajero no puede ver el reporte de administrador."""
        resp = self.c_cajero.get(reverse('reportes:index'))
        self.assertEqual(resp.status_code, 302)

    # ── Anulacion de venta ───────────────────────────────────────────────────

    def test_r04_anular_venta_cambia_estado(self):
        """Anular una venta la marca como ANULADA."""
        resp = self.c.post(reverse('reportes:anular_venta',
                                   kwargs={'pk': self.v_transferencia.pk}))
        self.assertTrue(resp.json()['ok'])
        self.v_transferencia.refresh_from_db()
        self.assertEqual(self.v_transferencia.estado, 'ANULADA')

    def test_r05_anular_venta_restaura_stock(self):
        """Al anular una venta el stock de los productos vuelve al nivel anterior."""
        # Refrescar desde la BD porque setUp ya creo ventas que descontaron stock.
        self.refresco.refresh_from_db()
        stock_antes = self.refresco.stock_actual
        self.c.post(reverse('reportes:anular_venta',
                             kwargs={'pk': self.v_transferencia.pk}))
        self.refresco.refresh_from_db()
        # La venta tenia 3 refrescos: stock debe aumentar 3
        self.assertEqual(self.refresco.stock_actual, stock_antes + 3)

    def test_r06_anular_venta_ya_anulada_rechazado(self):
        """No se puede anular una venta que ya fue anulada."""
        self.c.post(reverse('reportes:anular_venta',
                             kwargs={'pk': self.v_pago_movil.pk}))
        resp = self.c.post(reverse('reportes:anular_venta',
                                   kwargs={'pk': self.v_pago_movil.pk}))
        self.assertFalse(resp.json()['ok'])

    def test_r07_venta_anulada_no_aparece_en_totales(self):
        """Una venta anulada no se incluye en el total del reporte."""
        self.c.post(reverse('reportes:anular_venta',
                             kwargs={'pk': self.v_transferencia.pk}))
        completadas = Venta.objects.filter(
            fecha__date=timezone.localdate(), estado='COMPLETADA')
        pks = list(completadas.values_list('pk', flat=True))
        self.assertNotIn(self.v_transferencia.pk, pks)

    # ── Cierre cajero ────────────────────────────────────────────────────────

    def test_r08_cajero_ve_su_cierre_de_turno(self):
        """El cajero puede acceder a su propio cierre de turno."""
        resp = self.c_cajero.get(reverse('reportes:cierre_cajero'))
        self.assertEqual(resp.status_code, 200)

    def test_r09_cierre_cajero_solo_sus_ventas(self):
        """El cierre de cajero solo incluye las ventas del usuario autenticado."""
        resp = self.c_cajero.get(reverse('reportes:cierre_cajero'))
        # La v_punto_venta es del admin, no debe aparecer en el cierre del cajero
        self.assertNotContains(resp, 'PdV')

    # ── Cierre de caja admin ─────────────────────────────────────────────────

    def test_r10_pagina_cierre_caja_accesible(self):
        """El admin puede ver la pagina de cierre de caja."""
        resp = self.c.get(reverse('reportes:cierre_caja'))
        self.assertEqual(resp.status_code, 200)

    def test_r11_guardar_cierre_caja_crea_registro(self):
        """Al guardar el cierre de caja se crea un registro en CierreCaja."""
        resp = _post_json(self.c, reverse('reportes:guardar_cierre'), {
            'fecha': self._fecha_hoy(),
            'notas': 'Cierre sin novedades',
        })
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertTrue(CierreCaja.objects.filter(
            fecha=timezone.localdate()).exists())

    def test_r12_guardar_cierre_calcula_totales_por_metodo(self):
        """El cierre calcula el total en USD para cada metodo de pago."""
        _post_json(self.c, reverse('reportes:guardar_cierre'),
                   {'fecha': self._fecha_hoy(), 'notas': ''})
        cierre = CierreCaja.objects.get(fecha=timezone.localdate())
        # Hubo 1 venta TRANSFERENCIA, 1 PAGO_MOVIL, 1 PUNTO_DE_VENTA
        self.assertGreater(float(cierre.transferencia_total), 0)
        self.assertGreater(float(cierre.pago_movil_total),    0)
        self.assertGreater(float(cierre.punto_de_venta_total), 0)

    def test_r13_guardar_cierre_dos_veces_actualiza(self):
        """Guardar el cierre dos veces actualiza el registro existente (upsert)."""
        _post_json(self.c, reverse('reportes:guardar_cierre'),
                   {'fecha': self._fecha_hoy(), 'notas': 'Primera vez'})
        resp = _post_json(self.c, reverse('reportes:guardar_cierre'),
                          {'fecha': self._fecha_hoy(), 'notas': 'Segunda vez'})
        self.assertEqual(resp.json()['accion'], 'actualizado')
        self.assertEqual(CierreCaja.objects.filter(
            fecha=timezone.localdate()).count(), 1)

    def test_r14_efectivo_usd_esperado_en_cierre(self):
        """El cierre registra el efectivo USD esperado segun las ventas del dia."""
        _post_json(self.c, reverse('reportes:guardar_cierre'),
                   {'fecha': self._fecha_hoy(), 'notas': ''})
        cierre = CierreCaja.objects.get(fecha=timezone.localdate())
        # v_efectivo_usd: leche x2 = 5.00 USD
        self.assertEqual(float(cierre.efectivo_usd_esperado), 5.00)

    def test_r15_imprimir_cierre_accesible(self):
        """La vista de impresion del cierre devuelve 200."""
        resp = self.c.get(reverse('reportes:imprimir_cierre'),
                          {'fecha': self._fecha_hoy()})
        self.assertEqual(resp.status_code, 200)


# ─────────────────────────────────────────────────────────────────────────────
#  INTEGRACION — Dia completo narrativo
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(ALLOWED_HOSTS=['testserver'])
class DiaCompletoNarrativoTest(TestCase):
    """
    Prueba de integracion de extremo a extremo.

    Simula un dia real de operacion desde cero:
      1. Primera configuracion del negocio.
      2. El admin carga el catalogo de productos.
      3. El cajero realiza ventas durante la manana.
      4. Un cliente pide productos a credito (fiado).
      5. El cliente paga parte de su deuda por la tarde.
      6. Se anula una venta equivocada.
      7. El cajero hace su cierre de turno.
      8. El admin hace el cierre de caja del dia.
    """

    def test_dia_completo(self):
        # ── 1. Primera configuracion ─────────────────────────────────────────
        admin  = User.objects.create_user('admin', password='1234', is_staff=True,
                                          first_name='Carlos')
        cajero = User.objects.create_user('cajero', password='4321', is_staff=False,
                                          first_name='Luis')

        moneda = Moneda.objects.first()
        if moneda:
            moneda.tasa_cambio = Decimal('36.50')
            moneda.save(update_fields=['tasa_cambio'])
        else:
            moneda = Moneda.objects.create(tasa_cambio=Decimal('36.50'))
        empresa = Empresa.objects.create(nombre='Abasto El Progreso', rif='J-12345678-9')

        c_admin  = Client()
        c_cajero = Client()
        self.assertTrue(c_admin.login(username='admin',   password='1234'))
        self.assertTrue(c_cajero.login(username='cajero', password='4321'))

        # Verificar que el admin ve configuracion y el cajero no
        self.assertEqual(c_admin.get(reverse('configuracion:index')).status_code, 200)
        self.assertEqual(c_cajero.get(reverse('configuracion:index')).status_code, 302)

        # ── 2. Cargar catalogo ───────────────────────────────────────────────
        cat_alimentos = Categoria.objects.create(nombre='Alimentos')
        cat_bebidas   = Categoria.objects.create(nombre='Bebidas')
        cat_limpieza  = Categoria.objects.create(nombre='Limpieza')

        leche    = Producto.objects.create(nombre='Leche 1L', categoria=cat_alimentos,
                                           precio_usd=Decimal('2.50'), stock_actual=50,
                                           stock_minimo=10, alicuota_iva='EXENTO')
        refresco = Producto.objects.create(nombre='Refresco 500ml', categoria=cat_bebidas,
                                           precio_usd=Decimal('1.16'), stock_actual=30,
                                           stock_minimo=5,  alicuota_iva='GENERAL')
        jabon    = Producto.objects.create(nombre='Jabon', categoria=cat_limpieza,
                                           precio_usd=Decimal('3.24'), stock_actual=15,
                                           stock_minimo=3,  alicuota_iva='REDUCIDA')
        agua     = Producto.objects.create(nombre='Agua 600ml', categoria=cat_bebidas,
                                           precio_usd=Decimal('0.75'), stock_actual=80,
                                           stock_minimo=20, alicuota_iva='EXENTO')

        # El cajero puede buscar productos
        resp = c_cajero.get(reverse('pos:buscar_productos'), {'q': 'Leche'})
        self.assertIn('Leche 1L', [p['nombre'] for p in resp.json()['productos']])

        # ── 3. Manana: ventas del cajero ─────────────────────────────────────
        def procesar(carrito, metodo, monto_recibido=None, vuelto=None):
            return _post_json(c_cajero, reverse('pos:procesar_venta'), {
                'carrito':        carrito,
                'metodo_pago':    metodo,
                'monto_recibido': monto_recibido,
                'vuelto':         vuelto,
                'notas':          '',
            })

        # Venta 1: Leche x2 efectivo USD
        r1 = procesar([{'id': leche.pk, 'cantidad': 2}], 'EFECTIVO_USD',
                      monto_recibido=10.00, vuelto=5.00)
        self.assertTrue(r1.json()['ok'], r1.json().get('error'))
        v1 = Venta.objects.get(pk=r1.json()['venta_id'])
        self.assertEqual(v1.total_usd, Decimal('5.00'))

        # Venta 2: Refresco x3 transferencia
        r2 = procesar([{'id': refresco.pk, 'cantidad': 3}], 'TRANSFERENCIA')
        self.assertTrue(r2.json()['ok'])
        v2 = Venta.objects.get(pk=r2.json()['venta_id'])
        # base = 3.00, iva = 0.48, total = 3.48
        self.assertEqual(v2.total_usd, Decimal('3.48'))
        self.assertEqual(v2.iva_usd, Decimal('0.48'))

        # Venta 3: Jabon x1 pago movil
        r3 = procesar([{'id': jabon.pk, 'cantidad': 1}], 'PAGO_MOVIL')
        self.assertTrue(r3.json()['ok'])
        v3 = Venta.objects.get(pk=r3.json()['venta_id'])
        # Jabon 3.24 REDUCIDA 8%: base = 3.00, iva = 0.24
        self.assertEqual(v3.base_imponible_usd, Decimal('3.00'))

        # Venta 4: Agua x5 punto de venta (el cajero)
        r4 = procesar([{'id': agua.pk, 'cantidad': 5}], 'PUNTO_DE_VENTA')
        self.assertTrue(r4.json()['ok'])

        # Intento de venta sin stock (debe fallar)
        agua.stock_actual = 2
        agua.save()
        r_fail = procesar([{'id': agua.pk, 'cantidad': 10}], 'EFECTIVO_USD')
        self.assertFalse(r_fail.json()['ok'])

        # Verificar stock de leche descontado
        leche.refresh_from_db()
        self.assertEqual(leche.stock_actual, 48)  # 50 - 2

        # ── 4. Cliente pide a credito ────────────────────────────────────────
        r_cli = _post_json(c_admin, reverse('fiados:crear_cliente'), {
            'nombre': 'Pedro Perez', 'telefono': '0414-9999999',
        })
        self.assertTrue(r_cli.json()['ok'])
        cliente = Cliente.objects.get(nombre='Pedro Perez')

        # Pedro se lleva 4 leches a credito
        r_fiado = _post_json(c_admin,
            reverse('fiados:nueva_venta', kwargs={'cliente_pk': cliente.pk}),
            {'carrito': [{'id': leche.pk, 'cantidad': 4}], 'notas': 'Para la semana'},
        )
        self.assertTrue(r_fiado.json()['ok'])
        fiado = Fiado.objects.filter(cliente=cliente).first()
        self.assertEqual(fiado.estado, 'PENDIENTE')
        self.assertEqual(fiado.total_usd, Decimal('10.00'))  # 2.50 x 4
        leche.refresh_from_db()
        self.assertEqual(leche.stock_actual, 44)  # 48 - 4

        # ── 5. Pedro paga la mitad por la tarde ──────────────────────────────
        # saldo = 10.00 USD, paga 5.00 USD en bolivares = 182.50 Bs
        r_pago = _post_json(c_admin,
            reverse('fiados:registrar_pago', kwargs={'fiado_pk': fiado.pk}),
            {'metodo_pago': 'PAGO_MOVIL', 'monto_bs': 182.50},
        )
        self.assertTrue(r_pago.json()['ok'])
        fiado.refresh_from_db()
        self.assertEqual(fiado.estado, 'PARCIAL')
        self.assertAlmostEqual(float(fiado.saldo_usd), 5.00, places=1)

        # ── 6. Anular venta equivocada (v3 — jabon) ──────────────────────────
        jabon.refresh_from_db()   # v3 ya desconto stock en BD
        stock_jabon_antes = jabon.stock_actual
        r_anular = c_admin.post(reverse('reportes:anular_venta', kwargs={'pk': v3.pk}))
        self.assertTrue(r_anular.json()['ok'])
        v3.refresh_from_db()
        self.assertEqual(v3.estado, 'ANULADA')
        jabon.refresh_from_db()
        self.assertEqual(jabon.stock_actual, stock_jabon_antes + 1)  # stock restaurado

        # ── 7. Cierre de turno del cajero ────────────────────────────────────
        resp_cajero_cierre = c_cajero.get(reverse('reportes:cierre_cajero'))
        self.assertEqual(resp_cajero_cierre.status_code, 200)

        # ── 8. Cierre de caja del admin ──────────────────────────────────────
        hoy = timezone.localdate().isoformat()
        r_cierre = _post_json(c_admin, reverse('reportes:guardar_cierre'), {
            'fecha': hoy, 'notas': 'Dia sin novedades. Pedro pago la mitad.',
        })
        data_cierre = r_cierre.json()
        self.assertTrue(data_cierre['ok'])
        self.assertEqual(data_cierre['accion'], 'creado')

        cierre = CierreCaja.objects.get(fecha=timezone.localdate())
        # Ventas completadas: v1 (EFECTIVO_USD), v2 (TRANSFERENCIA), v4 (PUNTO_DE_VENTA)
        # v3 fue anulada — no debe sumar
        self.assertEqual(float(cierre.efectivo_usd_esperado), 5.00)    # v1
        self.assertGreater(float(cierre.transferencia_total),  0)       # v2
        self.assertGreater(float(cierre.punto_de_venta_total), 0)       # v4
        self.assertEqual(float(cierre.pago_movil_total),       0.0)    # v3 fue anulada

        # Verificar impresion del cierre accesible
        r_imp = c_admin.get(reverse('reportes:imprimir_cierre'), {'fecha': hoy})
        self.assertEqual(r_imp.status_code, 200)
