from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.exceptions import ValidationError
import json

from configuracion.models import Moneda, Empresa
from ventas.models import Venta
from .models import Producto, Categoria


def crear_base():
    Moneda.objects.create(tasa_cambio=50)
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
        Moneda.objects.create(tasa_cambio=50)
        self.prod = Producto.objects.create(
            nombre='Agua', precio_usd=2, costo_usd=1,
            stock_actual=5, stock_minimo=3,
        )

    def test_stock_bajo_cuando_igual_al_minimo(self):
        self.prod.stock_actual = 3
        self.assertTrue(self.prod.stock_bajo)

    def test_stock_bajo_cuando_menor_al_minimo(self):
        self.prod.stock_actual = 1
        self.assertTrue(self.prod.stock_bajo)

    def test_stock_no_bajo_cuando_mayor(self):
        self.prod.stock_actual = 10
        self.assertFalse(self.prod.stock_bajo)

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
        Moneda.objects.get_or_create(tasa_cambio=50)
        # Crear una venta que referencie el producto (PROTECT)
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
