"""
Tests para ventas/printing.py — impresión ESC/POS.

La impresora física se sustituye con unittest.mock.patch para que
los tests corran sin hardware. Se verifica:
  - Flujo completo: llamadas al driver en el orden correcto
  - Contenido enviado: encabezado, ítems, totales, pie
  - Casos de error: sin configurar, no instalado, fallo de conexión
  - Función auxiliar _wrap
"""
from unittest.mock import patch, MagicMock, call
from django.test import TestCase
from django.contrib.auth.models import User

from configuracion.models import Moneda, Empresa
from inventario.models import Producto, Categoria
from ventas.models import Venta
from ventas.printing import imprimir_ticket, _wrap


# ── Fixtures ───────────────────────────────────────────────────────

def _empresa(con_impresora=True, **kwargs):
    defaults = dict(
        nombre='Farmacia Central',
        rif='J-12345678-9',
        telefono='0212-5551234',
        direccion='Av. Principal, Local 1',
        nombre_impresora='HP LaserJet' if con_impresora else '',
        imprimir_ticket=con_impresora,
    )
    defaults.update(kwargs)
    return Empresa.objects.create(**defaults)


def _crear_venta(metodo='EFECTIVO_BS', cantidad=2, con_efectivo=False):
    moneda = Moneda.objects.first() or Moneda.objects.create(tasa_cambio=50)
    cat    = Categoria.objects.get_or_create(nombre='Gen')[0]
    prod   = Producto.objects.create(
        nombre='Agua Mineral 500ml', precio_usd=1,
        stock_actual=100, stock_minimo=5, categoria=cat,
    )
    monto_recibido = 5 if con_efectivo else None
    vuelto         = 5 - (1 * cantidad * 50 / 50) if con_efectivo else None  # simplificado
    return Venta.crear_desde_carrito(
        [{'producto': prod, 'cantidad': cantidad}],
        metodo,
        monto_recibido=monto_recibido,
        vuelto=vuelto,
    )


# ══════════════════════════════════════════════════════════════════
# _wrap — función auxiliar pura
# ══════════════════════════════════════════════════════════════════

class WrapTests(TestCase):

    def test_texto_corto_no_parte(self):
        self.assertEqual(_wrap('Hola', 10), ['Hola'])

    def test_texto_exacto_no_parte(self):
        self.assertEqual(_wrap('1234567890', 10), ['1234567890'])

    def test_texto_largo_parte_correctamente(self):
        # 'ABCDEFGHIJKLMN' = 14 chars, ancho=5 → [0:5], [5:10], [10:14]
        resultado = _wrap('ABCDEFGHIJKLMN', 5)
        self.assertEqual(resultado, ['ABCDE', 'FGHIJ', 'KLMN'])

    def test_texto_vacio_retorna_lista_con_string_vacio(self):
        self.assertEqual(_wrap('', 10), [''])

    def test_ancho_42_ticket_real(self):
        """Corte estricto por caracteres — 26 chars exactos por línea."""
        nombre = 'Agua Mineral Natural Premium 1.5L'  # 33 chars
        partes = _wrap(nombre, 26)
        # [0:26] = 'Agua Mineral Natural Premi'  (26 chars)
        # [26:]  = 'um 1.5L'
        self.assertEqual(partes[0], 'Agua Mineral Natural Premi')
        self.assertEqual(partes[1], 'um 1.5L')
        self.assertEqual(len(partes[0]), 26)


# ══════════════════════════════════════════════════════════════════
# Casos de error — sin hardware
# ══════════════════════════════════════════════════════════════════

class ImprimirTicketErroresTests(TestCase):

    def setUp(self):
        Moneda.objects.create(tasa_cambio=50)

    def test_impresora_no_configurada(self):
        empresa = _empresa(con_impresora=False)
        venta   = _crear_venta()

        ok, error = imprimir_ticket(venta, empresa)

        self.assertFalse(ok)
        self.assertIn('impresora no configurado', error.lower())

    def test_empresa_sin_atributo_impresora(self):
        """Si empresa.nombre_impresora es cadena vacía → falla limpiamente."""
        empresa = _empresa(con_impresora=False)
        empresa.nombre_impresora = '   '  # solo espacios
        venta = _crear_venta()

        ok, error = imprimir_ticket(venta, empresa)
        self.assertFalse(ok)

    @patch.dict('sys.modules', {'escpos': None, 'escpos.printer': None})
    def test_escpos_no_instalado(self):
        """Si la librería no está, retorna False con mensaje claro."""
        empresa = _empresa()
        venta   = _crear_venta()

        ok, error = imprimir_ticket(venta, empresa)

        self.assertFalse(ok)
        self.assertIn('no instalado', error.lower())

    @patch('escpos.printer.Win32Raw')
    def test_fallo_de_conexion_a_impresora(self, MockWin32Raw):
        """Win32Raw() lanza excepción → retorna (False, mensaje)."""
        MockWin32Raw.side_effect = Exception("Printer not found")
        empresa = _empresa()
        venta   = _crear_venta()

        ok, error = imprimir_ticket(venta, empresa)

        self.assertFalse(ok)
        self.assertIn('No se pudo conectar', error)
        self.assertIn('Printer not found', error)

    @patch('escpos.printer.Win32Raw')
    def test_fallo_durante_impresion_cierra_conexion(self, MockWin32Raw):
        """Si p.text() falla, se llama p.close() igualmente."""
        mock_p = MagicMock()
        mock_p.text.side_effect = Exception("Paper jam")
        MockWin32Raw.return_value = mock_p
        empresa = _empresa()
        venta   = _crear_venta()

        ok, error = imprimir_ticket(venta, empresa)

        self.assertFalse(ok)
        self.assertIn('Paper jam', error)
        mock_p.close.assert_called()  # close() siempre se llama


# ══════════════════════════════════════════════════════════════════
# Flujo exitoso — verificar llamadas al driver
# ══════════════════════════════════════════════════════════════════

class ImprimirTicketExitoTests(TestCase):

    def setUp(self):
        Moneda.objects.create(tasa_cambio=50)
        self.empresa = _empresa()

    @patch('escpos.printer.Win32Raw')
    def test_retorna_true_none_en_exito(self, MockWin32Raw):
        mock_p = MagicMock()
        MockWin32Raw.return_value = mock_p
        venta = _crear_venta()

        ok, error = imprimir_ticket(venta, self.empresa)

        self.assertTrue(ok)
        self.assertIsNone(error)

    @patch('escpos.printer.Win32Raw')
    def test_abre_con_nombre_correcto(self, MockWin32Raw):
        mock_p = MagicMock()
        MockWin32Raw.return_value = mock_p
        venta = _crear_venta()

        imprimir_ticket(venta, self.empresa)

        MockWin32Raw.assert_called_once_with('HP LaserJet')

    @patch('escpos.printer.Win32Raw')
    def test_llama_cut_y_close_al_final(self, MockWin32Raw):
        mock_p = MagicMock()
        MockWin32Raw.return_value = mock_p
        venta = _crear_venta()

        imprimir_ticket(venta, self.empresa)

        mock_p.cut.assert_called_once()
        mock_p.close.assert_called_once()

    @patch('escpos.printer.Win32Raw')
    def test_cut_se_llama_despues_de_ln(self, MockWin32Raw):
        """ln(4) debe llamarse antes del cut — verifica orden."""
        mock_p = MagicMock()
        MockWin32Raw.return_value = mock_p
        venta = _crear_venta()

        imprimir_ticket(venta, self.empresa)

        metodos_llamados = [c[0] for c in mock_p.method_calls]
        idx_ln  = next(i for i, m in enumerate(metodos_llamados) if m == 'ln')
        idx_cut = next(i for i, m in enumerate(metodos_llamados) if m == 'cut')
        self.assertLess(idx_ln, idx_cut, "ln() debe llamarse antes que cut()")


# ══════════════════════════════════════════════════════════════════
# Contenido del ticket
# ══════════════════════════════════════════════════════════════════

class ContenidoTicketTests(TestCase):

    def setUp(self):
        Moneda.objects.create(tasa_cambio=50)
        self.empresa = _empresa()

    def _textos_enviados(self, MockWin32Raw):
        """Extrae todos los strings enviados con p.text(...)."""
        mock_p = MockWin32Raw.return_value
        return [
            args[0]
            for name, args, kwargs in mock_p.mock_calls
            if name == 'text' and args
        ]

    @patch('escpos.printer.Win32Raw')
    def test_encabezado_incluye_nombre_empresa(self, MockWin32Raw):
        venta   = _crear_venta()
        imprimir_ticket(venta, self.empresa)
        textos  = self._textos_enviados(MockWin32Raw)
        combinado = ''.join(textos)
        self.assertIn('Farmacia Central', combinado)

    @patch('escpos.printer.Win32Raw')
    def test_encabezado_incluye_rif(self, MockWin32Raw):
        venta  = _crear_venta()
        imprimir_ticket(venta, self.empresa)
        textos = self._textos_enviados(MockWin32Raw)
        combinado = ''.join(textos)
        self.assertIn('J-12345678-9', combinado)

    @patch('escpos.printer.Win32Raw')
    def test_encabezado_incluye_telefono(self, MockWin32Raw):
        venta  = _crear_venta()
        imprimir_ticket(venta, self.empresa)
        textos = self._textos_enviados(MockWin32Raw)
        combinado = ''.join(textos)
        self.assertIn('0212-5551234', combinado)

    @patch('escpos.printer.Win32Raw')
    def test_ticket_incluye_nombre_producto(self, MockWin32Raw):
        venta  = _crear_venta()
        imprimir_ticket(venta, self.empresa)
        textos = self._textos_enviados(MockWin32Raw)
        combinado = ''.join(textos)
        self.assertIn('Agua Mineral 500ml', combinado)

    @patch('escpos.printer.Win32Raw')
    def test_ticket_incluye_total_en_bs(self, MockWin32Raw):
        """precio_usd=1, cantidad=2, tasa=50 → total_bs=100.00"""
        venta  = _crear_venta(cantidad=2)
        imprimir_ticket(venta, self.empresa)
        textos = self._textos_enviados(MockWin32Raw)
        combinado = ''.join(textos)
        self.assertIn('100.00', combinado)

    @patch('escpos.printer.Win32Raw')
    def test_ticket_incluye_tasa_bcv(self, MockWin32Raw):
        venta  = _crear_venta()
        imprimir_ticket(venta, self.empresa)
        textos = self._textos_enviados(MockWin32Raw)
        combinado = ''.join(textos)
        self.assertIn('Tasa BCV', combinado)
        self.assertIn('50.00', combinado)

    @patch('escpos.printer.Win32Raw')
    def test_ticket_incluye_metodo_pago(self, MockWin32Raw):
        venta  = _crear_venta(metodo='PAGO_MOVIL')
        imprimir_ticket(venta, self.empresa)
        textos = self._textos_enviados(MockWin32Raw)
        combinado = ''.join(textos)
        self.assertIn('Pago M', combinado)  # "Pago Móvil"

    @patch('escpos.printer.Win32Raw')
    def test_ticket_incluye_gracias(self, MockWin32Raw):
        venta  = _crear_venta()
        imprimir_ticket(venta, self.empresa)
        textos = self._textos_enviados(MockWin32Raw)
        combinado = ''.join(textos)
        self.assertIn('Gracias', combinado)

    @patch('escpos.printer.Win32Raw')
    def test_efectivo_bs_muestra_recibido_y_vuelto(self, MockWin32Raw):
        """Con pago en efectivo Bs, imprime líneas de recibido y vuelto."""
        venta  = _crear_venta(metodo='EFECTIVO_BS', con_efectivo=True)
        imprimir_ticket(venta, self.empresa)
        textos = self._textos_enviados(MockWin32Raw)
        combinado = ''.join(textos)
        self.assertIn('Recibido', combinado)
        self.assertIn('Vuelto',   combinado)

    @patch('escpos.printer.Win32Raw')
    def test_sin_efectivo_no_muestra_recibido(self, MockWin32Raw):
        """Con pago por transferencia, no hay líneas de recibido/vuelto."""
        venta  = _crear_venta(metodo='TRANSFERENCIA', con_efectivo=False)
        imprimir_ticket(venta, self.empresa)
        textos = self._textos_enviados(MockWin32Raw)
        combinado = ''.join(textos)
        self.assertNotIn('Recibido', combinado)

    @patch('escpos.printer.Win32Raw')
    def test_notas_se_imprimen_cuando_existen(self, MockWin32Raw):
        venta       = _crear_venta()
        venta.notas = 'Sin cebolla por favor'
        venta.save(update_fields=['notas'])
        imprimir_ticket(venta, self.empresa)
        textos = self._textos_enviados(MockWin32Raw)
        combinado = ''.join(textos)
        self.assertIn('Sin cebolla por favor', combinado)

    @patch('escpos.printer.Win32Raw')
    def test_nombre_empresa_largo_se_trunca(self, MockWin32Raw):
        """Nombre > 21 chars se trunca para no romper el doble ancho."""
        empresa_larga = Empresa(
            nombre='Supermercado El Gran Rey de Venezuela',
            rif='J-000',
            nombre_impresora='HP',
        )
        venta = _crear_venta()
        imprimir_ticket(venta, empresa_larga)
        mock_p = MockWin32Raw.return_value
        textos = [
            args[0]
            for name, args, kwargs in mock_p.mock_calls
            if name == 'text' and args
        ]
        # El primer texto debe ser máximo 22 chars (21 + \n)
        primer_texto = textos[0].strip()
        self.assertLessEqual(len(primer_texto), 21)
