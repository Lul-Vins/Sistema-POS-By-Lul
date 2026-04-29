from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.exceptions import ValidationError
from decimal import Decimal
import json

from configuracion.models import Moneda, Empresa
from ventas.models import Venta
from .models import Producto, Categoria


def crear_base():
    moneda = Moneda.objects.first()
    moneda.tasa_cambio = 50
    moneda.save(update_fields=['tasa_cambio'])
    Empresa.objects.create(nombre='Test SA', rif='J123456789')
    cat  = Categoria.objects.create(nombre='Bebidas')
    prod = Producto.objects.create(
        nombre='Agua', precio_usd=1, costo_usd=0.4,
        stock_actual=10, stock_minimo=3, categoria=cat,
    )
    admin = User.objects.create_user('admin_t', password='admin1234', is_staff=True)
    return cat, prod, admin


# ══════════════════════════════════════════════════════════════════
# Modelo Producto — propiedades calculadas
# ══════════════════════════════════════════════════════════════════

class ProductoPropiedadesTests(TestCase):

    def setUp(self):
        moneda = Moneda.objects.first()
        moneda.tasa_cambio = 50
        moneda.save(update_fields=['tasa_cambio'])
        self.prod = Producto.objects.create(
            nombre='Agua', precio_usd=2, costo_usd=1,
            stock_actual=5, stock_minimo=3,
        )

    def test_stock_no_bajo_cuando_igual_al_minimo(self):
        # stock == minimo → NO es bajo (operador estricto <)
        self.prod.stock_actual = 3
        self.assertFalse(self.prod.stock_bajo)

    def test_stock_bajo_cuando_menor_al_minimo(self):
        self.prod.stock_actual = 1
        self.assertTrue(self.prod.stock_bajo)

    def test_stock_no_bajo_cuando_mayor(self):
        self.prod.stock_actual = 10
        self.assertFalse(self.prod.stock_bajo)

    def test_stock_bajo_exactamente_un_punto_debajo(self):
        self.prod.stock_actual = 2  # minimo=3, 2 < 3
        self.assertTrue(self.prod.stock_bajo)

    def test_margen_calculado_correctamente(self):
        # (precio - costo) / precio * 100 = (2-1)/2*100 = 50%
        self.assertEqual(self.prod.margen, 50.0)

    def test_margen_none_sin_costo(self):
        self.prod.costo_usd = None
        self.assertIsNone(self.prod.margen)

    def test_margen_none_con_precio_cero(self):
        self.prod.precio_usd = 0
        self.assertIsNone(self.prod.margen)

    def test_get_precio_bs(self):
        # precio_usd=2, tasa=50 → precio_bs=100
        self.assertEqual(float(self.prod.get_precio_bs()), 100.0)

    def test_get_precio_bs_sin_moneda(self):
        Moneda.objects.all().delete()
        self.assertIsNone(self.prod.get_precio_bs())


# ══════════════════════════════════════════════════════════════════
# Vista guardar_producto
# ══════════════════════════════════════════════════════════════════

class GuardarProductoTests(TestCase):

    def setUp(self):
        self.cat, self.prod, self.admin = crear_base()
        self.client = Client()
        self.client.login(username='admin_t', password='admin1234')
        self.url = reverse('inventario:guardar_producto')

    def _post(self, data):
        return self.client.post(
            self.url,
            data=json.dumps(data),
            content_type='application/json',
        )

    def test_crea_producto_nuevo(self):
        r = self._post({'pk': 0, 'nombre': 'Jugo', 'precio_usd': 2,
                        'stock_actual': 5, 'stock_minimo': 1})
        self.assertTrue(r.json()['ok'])
        self.assertTrue(Producto.objects.filter(nombre='Jugo').exists())

    def test_nombre_obligatorio(self):
        r = self._post({'pk': 0, 'nombre': '', 'precio_usd': 2})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()['ok'])

    def test_precio_obligatorio(self):
        r = self._post({'pk': 0, 'nombre': 'Test', 'precio_usd': ''})
        self.assertEqual(r.status_code, 400)

    def test_precio_negativo_rechazado(self):
        r = self._post({'pk': 0, 'nombre': 'Test', 'precio_usd': -5})
        self.assertEqual(r.status_code, 400)

    def test_precio_cero_rechazado(self):
        r = self._post({'pk': 0, 'nombre': 'Test', 'precio_usd': 0})
        self.assertEqual(r.status_code, 400)

    def test_actualiza_producto_existente(self):
        r = self._post({'pk': self.prod.pk, 'nombre': 'Agua Editada',
                        'precio_usd': 1.5, 'stock_actual': 10, 'stock_minimo': 2})
        self.assertTrue(r.json()['ok'])
        self.prod.refresh_from_db()
        self.assertEqual(self.prod.nombre, 'Agua Editada')


# ══════════════════════════════════════════════════════════════════
# Vista eliminar_producto
# ══════════════════════════════════════════════════════════════════

class EliminarProductoTests(TestCase):

    def setUp(self):
        self.cat, self.prod, self.admin = crear_base()
        self.client = Client()
        self.client.login(username='admin_t', password='admin1234')

    def test_elimina_producto_sin_ventas(self):
        r = self.client.post(reverse('inventario:eliminar_producto', args=[self.prod.pk]))
        self.assertTrue(r.json()['ok'])
        self.assertFalse(Producto.objects.filter(pk=self.prod.pk).exists())

    def test_producto_con_ventas_se_desactiva_no_elimina(self):
        Venta.crear_desde_carrito(
            [{'producto': self.prod, 'cantidad': 1}], 'EFECTIVO_BS'
        )
        r = self.client.post(reverse('inventario:eliminar_producto', args=[self.prod.pk]))
        data = r.json()
        self.assertTrue(data['ok'])
        self.assertIn('advertencia', data)
        self.prod.refresh_from_db()
        self.assertFalse(self.prod.activo)
        self.assertTrue(Producto.objects.filter(pk=self.prod.pk).exists())


# ══════════════════════════════════════════════════════════════════
# Vista buscar_productos
# ══════════════════════════════════════════════════════════════════

class BuscarProductosTests(TestCase):

    def setUp(self):
        self.cat, self.prod, self.admin = crear_base()
        Producto.objects.create(
            nombre='Jugo de Naranja', precio_usd=2,
            stock_actual=5, stock_minimo=1, activo=True,
        )
        Producto.objects.create(
            nombre='Oculto', precio_usd=3,
            stock_actual=5, stock_minimo=1, activo=False,
        )
        self.client = Client()
        self.client.login(username='admin_t', password='admin1234')
        self.url = reverse('pos:buscar_productos')

    def test_busqueda_por_nombre(self):
        r    = self.client.get(self.url, {'q': 'Jugo'})
        data = r.json()
        self.assertEqual(len(data['productos']), 1)
        self.assertEqual(data['productos'][0]['nombre'], 'Jugo de Naranja')

    def test_no_retorna_inactivos(self):
        r    = self.client.get(self.url, {'q': 'Oculto'})
        data = r.json()
        self.assertEqual(len(data['productos']), 0)

    def test_query_corta_retorna_vacio(self):
        r    = self.client.get(self.url, {'q': 'A'})
        data = r.json()
        self.assertEqual(data['productos'], [])

    def test_respuesta_incluye_stock(self):
        r    = self.client.get(self.url, {'q': 'Agua'})
        prod = r.json()['productos'][0]
        self.assertIn('stock_actual', prod)
        self.assertIn('stock_bajo',   prod)


# ══════════════════════════════════════════════════════════════════
# Lector de código de barras (backend)
# El listener JS envía el código al campo prod-codigo (inventario)
# y al buscador del POS. Estos tests verifican que el backend
# guarda y devuelve el código correctamente.
# ══════════════════════════════════════════════════════════════════

class CodigoBarrasTests(TestCase):

    def setUp(self):
        self.cat, self.prod, self.admin = crear_base()
        self.prod.codigo_barras = '7591000011233'
        self.prod.save(update_fields=['codigo_barras'])
        self.client = Client()
        self.client.login(username='admin_t', password='admin1234')

    # ── Guardar desde inventario ───────────────────────────────

    def test_guarda_codigo_con_producto(self):
        """guardar_producto persiste el codigo_barras en la BD."""
        r = self.client.post(
            reverse('inventario:guardar_producto'),
            data=json.dumps({
                'pk': self.prod.pk, 'nombre': 'Agua',
                'precio_usd': 1, 'codigo_barras': '7591000099999',
            }),
            content_type='application/json',
        )
        self.assertTrue(r.json()['ok'])
        self.prod.refresh_from_db()
        self.assertEqual(self.prod.codigo_barras, '7591000099999')

    def test_codigo_duplicado_rechazado(self):
        """Dos productos no pueden compartir el mismo codigo_barras."""
        # self.prod ya tiene '7591000011233'; intentar crear otro con el mismo
        # código a través de la vista debe devolver error (unique constraint).
        r = self.client.post(
            reverse('inventario:guardar_producto'),
            data=json.dumps({
                'pk': 0, 'nombre': 'Clon',
                'precio_usd': 1, 'codigo_barras': '7591000011233',
            }),
            content_type='application/json',
        )
        self.assertFalse(r.json()['ok'])

    def test_producto_sin_codigo_se_guarda(self):
        """El campo es opcional — puede quedar en blanco."""
        r = self.client.post(
            reverse('inventario:guardar_producto'),
            data=json.dumps({
                'pk': 0, 'nombre': 'Sin Codigo',
                'precio_usd': 1, 'codigo_barras': '',
            }),
            content_type='application/json',
        )
        self.assertTrue(r.json()['ok'])
        self.assertIsNone(Producto.objects.get(nombre='Sin Codigo').codigo_barras)

    # ── Búsqueda desde el POS (lo que dispara el auto-add al carrito) ─

    def test_busqueda_exacta_por_codigo_devuelve_producto(self):
        """El scanner manda el codigo exacto; debe encontrar el producto."""
        r    = self.client.get(reverse('pos:buscar_productos'), {'q': '7591000011233'})
        data = r.json()
        self.assertEqual(len(data['productos']), 1)
        self.assertEqual(data['productos'][0]['nombre'], 'Agua')

    def test_busqueda_codigo_inexistente_devuelve_vacio(self):
        """Código que no existe en BD → lista vacía → no agrega nada al carrito."""
        r    = self.client.get(reverse('pos:buscar_productos'), {'q': '0000000000000'})
        data = r.json()
        self.assertEqual(data['productos'], [])

    def test_busqueda_por_codigo_retorna_exactamente_uno(self):
        """Escanear un código único devuelve 1 solo resultado.
        El listener JS hace auto-add al carrito solo cuando products.length === 1."""
        r    = self.client.get(reverse('pos:buscar_productos'), {'q': '7591000011233'})
        data = r.json()
        self.assertEqual(len(data['productos']), 1)
        self.assertEqual(data['productos'][0]['nombre'], 'Agua')


# ══════════════════════════════════════════════════════════════════
# Productos vendidos por kilo
# ══════════════════════════════════════════════════════════════════

class ProductoKgTests(TestCase):

    def setUp(self):
        moneda = Moneda.objects.first()
        moneda.tasa_cambio = 50
        moneda.save(update_fields=['tasa_cambio'])
        self.admin = User.objects.create_user('admin_t', password='admin1234', is_staff=True)
        self.client = Client()
        self.client.login(username='admin_t', password='admin1234')
        self.url = reverse('inventario:guardar_producto')

    def _post(self, data):
        return self.client.post(
            self.url,
            data=json.dumps(data),
            content_type='application/json',
        )

    def test_crea_producto_kg_con_stock_fraccional(self):
        r = self._post({'pk': 0, 'nombre': 'Carne', 'precio_usd': 5,
                        'stock_actual': 50.4, 'stock_minimo': 1,
                        'vendido_por_peso': 'true'})
        self.assertTrue(r.json()['ok'])
        prod = Producto.objects.get(nombre='Carne')
        self.assertTrue(prod.vendido_por_peso)
        self.assertAlmostEqual(float(prod.stock_actual), 50.4, places=2)

    def test_stock_fraccional_rechazado_en_producto_unidad(self):
        r = self._post({'pk': 0, 'nombre': 'Agua', 'precio_usd': 1,
                        'stock_actual': 5.7, 'stock_minimo': 1,
                        'vendido_por_peso': 'false'})
        self.assertEqual(r.status_code, 400)

    def test_stock_bajo_kg_usa_operador_estricto(self):
        prod = Producto.objects.create(
            nombre='Pollo', precio_usd=4,
            stock_actual=Decimal('1.000'), stock_minimo=Decimal('1.000'),
            vendido_por_peso=True,
        )
        # igual al mínimo → NO es bajo
        self.assertFalse(prod.stock_bajo)
        prod.stock_actual = Decimal('0.999')
        self.assertTrue(prod.stock_bajo)

    def test_stock_display_kg_sin_ceros_finales(self):
        """La vista de inventario formatea el stock kg sin ceros innecesarios."""
        Empresa.objects.create(nombre='Test SA', rif='J001')
        Producto.objects.create(
            nombre='Queso', precio_usd=6,
            stock_actual=Decimal('50.400'), stock_minimo=Decimal('1.000'),
            vendido_por_peso=True,
        )
        r = self.client.get(reverse('inventario:index'))
        self.assertEqual(r.status_code, 200)
        # Debe mostrar "50,4" con coma y sin ceros finales, no "50,400"
        self.assertContains(r, '50,4')

    def test_busqueda_producto_kg_incluye_flag(self):
        """La búsqueda del POS devuelve vendido_por_peso=True para productos kg."""
        Empresa.objects.create(nombre='Test SA', rif='J001')
        Producto.objects.create(
            nombre='Mortadela', precio_usd=3,
            stock_actual=Decimal('10.000'), stock_minimo=Decimal('0.500'),
            vendido_por_peso=True, activo=True,
        )
        r = self.client.get(reverse('pos:buscar_productos'), {'q': 'Mortadela'})
        prod = r.json()['productos'][0]
        self.assertTrue(prod['vendido_por_peso'])
