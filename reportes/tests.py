"""
Tests de rendimiento con volumen alto de datos.
Crea 3000 productos y varias ventas para medir tiempos de respuesta.
"""
import time
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from configuracion.models import Moneda, Empresa
from inventario.models import Producto, Categoria
from ventas.models import Venta


# ── helpers ────────────────────────────────────────────────────────

def _fmt(segundos):
    return f"{segundos * 1000:.1f} ms"

def _umbral(segundos, limite_ms, nombre):
    icono = "OK" if segundos * 1000 <= limite_ms else "LENTO"
    print(f"    [{icono}] {nombre}: {_fmt(segundos)}  (limite {limite_ms} ms)")
    return segundos * 1000 <= limite_ms


# ══════════════════════════════════════════════════════════════════
# Setup compartido: 3000 productos + ventas
# ══════════════════════════════════════════════════════════════════

class RendimientoBase(TestCase):

    @classmethod
    def setUpTestData(cls):
        """
        Corre una sola vez para toda la clase (no se repite por test).
        bulk_create inserta los 3000 productos en una sola query.
        """
        print("\n")
        print("=" * 60)
        print("  SETUP: creando 3000 productos + ventas...")
        print("=" * 60)

        cls.moneda  = Moneda.objects.create(tasa_cambio=50)
        cls.empresa = Empresa.objects.create(nombre='Test Perf SA', rif='J999')
        cls.cat     = Categoria.objects.create(nombre='General')
        cls.admin   = User.objects.create_user('admin_p',  password='admin1234', is_staff=True)
        cls.cajero  = User.objects.create_user('cajero_p', password='caj1234',   is_staff=False)

        # ── 3000 productos con bulk_create ─────────────────────────
        t0 = time.time()
        productos = [
            Producto(
                nombre=f'Producto {i:04d}',
                precio_usd=round(0.50 + (i % 50) * 0.10, 2),
                costo_usd=round(0.25 + (i % 30) * 0.05, 2),
                stock_actual=max(1, (i % 40)),
                stock_minimo=5,
                categoria=cls.cat,
                activo=True,
            )
            for i in range(1, 3001)
        ]
        cls.todos_los_productos = Producto.objects.bulk_create(productos)
        t1 = time.time()
        print(f"  bulk_create 3000 productos : {_fmt(t1 - t0)}")

        # ── 50 ventas distribuidas entre admin y cajero ────────────
        t0 = time.time()
        vendedores = [cls.admin, cls.cajero]
        metodos    = ['EFECTIVO_BS', 'EFECTIVO_USD', 'PAGO_MOVIL', 'TRANSFERENCIA', 'PUNTO_DE_VENTA']
        cls.ventas_creadas = []

        for i, prod in enumerate(cls.todos_los_productos[:50]):
            vendedor = vendedores[i % 2]
            metodo   = metodos[i % len(metodos)]
            venta = Venta.crear_desde_carrito(
                [{'producto': prod, 'cantidad': 1}],
                metodo,
                vendedor=vendedor,
            )
            cls.ventas_creadas.append(venta)

        t1 = time.time()
        print(f"  crear 50 ventas            : {_fmt(t1 - t0)}")
        print(f"  Total productos en BD      : {Producto.objects.count()}")
        print(f"  Total ventas en BD         : {Venta.objects.count()}")
        print("=" * 60)


# ══════════════════════════════════════════════════════════════════
# Tests de rendimiento de vistas
# ══════════════════════════════════════════════════════════════════

class RendimientoVistasTests(RendimientoBase):

    def setUp(self):
        self.client = Client()

    # ── Inventario ─────────────────────────────────────────────────

    def test_inventario_carga_3000_productos(self):
        """Página de inventario con 3000 productos debe cargar en < 2 s."""
        print("\n")
        self.client.login(username='admin_p', password='admin1234')

        t0 = time.time()
        r  = self.client.get(reverse('inventario:index'))
        t1 = time.time()

        self.assertEqual(r.status_code, 200)
        ok = _umbral(t1 - t0, 2000, 'inventario:index con 3000 productos')
        self.assertTrue(ok, f"Inventario tardó {_fmt(t1-t0)}, supera 2000 ms")

    # ── Búsqueda AJAX ──────────────────────────────────────────────

    def test_buscar_por_nombre_generico(self):
        """Búsqueda 'Producto 01' debe responder en < 300 ms."""
        self.client.login(username='cajero_p', password='caj1234')

        t0 = time.time()
        r  = self.client.get(reverse('pos:buscar_productos'), {'q': 'Producto 01'})
        t1 = time.time()

        self.assertEqual(r.status_code, 200)
        resultados = r.json()['productos']
        print(f"\n    Resultados para 'Producto 01': {len(resultados)}")
        ok = _umbral(t1 - t0, 300, 'buscar_productos icontains')
        self.assertTrue(ok, f"Búsqueda tardó {_fmt(t1-t0)}, supera 300 ms")

    def test_buscar_sin_resultados(self):
        """Búsqueda que no matchea nada también debe ser rápida."""
        self.client.login(username='cajero_p', password='caj1234')

        t0 = time.time()
        r  = self.client.get(reverse('pos:buscar_productos'), {'q': 'xyzabc999'})
        t1 = time.time()

        self.assertEqual(r.json()['productos'], [])
        ok = _umbral(t1 - t0, 200, 'buscar_productos sin resultados')
        self.assertTrue(ok)

    # ── POS venta ──────────────────────────────────────────────────

    def test_pos_venta_carga(self):
        """La pantalla del POS debe cargar en < 500 ms sin importar inventario."""
        self.client.login(username='cajero_p', password='caj1234')

        t0 = time.time()
        r  = self.client.get(reverse('pos:venta'))
        t1 = time.time()

        self.assertEqual(r.status_code, 200)
        ok = _umbral(t1 - t0, 500, 'pos:venta (no carga productos, solo HTML)')
        self.assertTrue(ok)

    # ── Reportes ───────────────────────────────────────────────────

    def test_reportes_index_con_ventas(self):
        """Reporte del día con 50 ventas debe cargar en < 1 s."""
        self.client.login(username='admin_p', password='admin1234')

        t0 = time.time()
        r  = self.client.get(reverse('reportes:index'))
        t1 = time.time()

        self.assertEqual(r.status_code, 200)
        ok = _umbral(t1 - t0, 1000, 'reportes:index con 50 ventas')
        self.assertTrue(ok)

    def test_cierre_caja_con_ventas(self):
        """Cierre de caja con 50 ventas debe cargar en < 1 s."""
        self.client.login(username='admin_p', password='admin1234')

        t0 = time.time()
        r  = self.client.get(reverse('reportes:cierre_caja'))
        t1 = time.time()

        self.assertEqual(r.status_code, 200)
        ok = _umbral(t1 - t0, 1000, 'reportes:cierre_caja con 50 ventas')
        self.assertTrue(ok)

    def test_mis_ventas_cajero(self):
        """Mis ventas del cajero (25 ventas suyas) debe cargar en < 500 ms."""
        self.client.login(username='cajero_p', password='caj1234')

        t0 = time.time()
        r  = self.client.get(reverse('pos:mis_ventas'))
        t1 = time.time()

        self.assertEqual(r.status_code, 200)
        ok = _umbral(t1 - t0, 500, 'pos:mis_ventas cajero con 25 ventas')
        self.assertTrue(ok)

    def test_cierre_cajero(self):
        """Cierre de turno del cajero debe cargar en < 500 ms."""
        self.client.login(username='cajero_p', password='caj1234')

        t0 = time.time()
        r  = self.client.get(reverse('reportes:cierre_cajero'))
        t1 = time.time()

        self.assertEqual(r.status_code, 200)
        ok = _umbral(t1 - t0, 500, 'reportes:cierre_cajero con 25 ventas')
        self.assertTrue(ok)

    # ── Polling ────────────────────────────────────────────────────

    def test_polling_tasa_estado(self):
        """El endpoint de polling debe responder en < 50 ms (1 query)."""
        self.client.login(username='cajero_p', password='caj1234')

        # Calentar
        self.client.get(reverse('pos:tasa_estado'))

        tiempos = []
        for _ in range(5):
            t0 = time.time()
            r  = self.client.get(reverse('pos:tasa_estado'))
            tiempos.append(time.time() - t0)

        promedio = sum(tiempos) / len(tiempos)
        print(f"\n    tasa_estado promedio 5 llamadas: {_fmt(promedio)}")
        self.assertEqual(r.status_code, 200)
        ok = _umbral(promedio, 50, 'pos:tasa_estado promedio')
        self.assertTrue(ok)


# ══════════════════════════════════════════════════════════════════
# Tests de lógica con volumen
# ══════════════════════════════════════════════════════════════════

class RendimientoLogicaTests(RendimientoBase):

    def test_venta_carrito_10_items(self):
        """Procesar venta con 10 productos distintos debe tomar < 500 ms."""
        # Consultar BD en lugar de usar la lista en memoria (stock puede haber cambiado)
        # Saltamos los primeros 100 para evitar los que el setup ya vendió
        prods_disponibles = list(
            Producto.objects.filter(stock_actual__gte=1).order_by('id')[100:110]
        )
        carrito = [{'producto': p, 'cantidad': 1} for p in prods_disponibles]

        t0    = time.time()
        venta = Venta.crear_desde_carrito(carrito, 'EFECTIVO_BS', vendedor=self.cajero)
        t1    = time.time()

        print(f"\n")
        ok = _umbral(t1 - t0, 500, 'crear_desde_carrito con 10 items')
        self.assertIsNotNone(venta.pk)
        self.assertEqual(venta.detalles.count(), 10)
        self.assertTrue(ok)

    def test_anular_venta_revierte_stock(self):
        """Anular venta con 10 items en < 300 ms."""
        prods = [p for p in self.todos_los_productos if p.stock_actual >= 1][100:110]
        carrito = [{'producto': p, 'cantidad': 1} for p in prods]
        venta   = Venta.crear_desde_carrito(carrito, 'PAGO_MOVIL', vendedor=self.admin)

        client = Client()
        client.login(username='admin_p', password='admin1234')

        t0 = time.time()
        r  = client.post(reverse('reportes:anular_venta', args=[venta.pk]))
        t1 = time.time()

        print(f"\n")
        ok = _umbral(t1 - t0, 300, 'anular_venta con 10 detalles')
        self.assertTrue(r.json()['ok'])
        self.assertTrue(ok)
