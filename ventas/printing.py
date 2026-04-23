"""
Impresión directa ESC/POS para impresoras térmicas de 80 mm.
Usa Win32Raw (python-escpos + pywin32) — solo Windows, impresora local/compartida.
"""

ANCHO = 42  # columnas seguras para 80 mm, font A


def _wrap(texto, ancho):
    """Parte un texto en líneas de `ancho` caracteres."""
    return [texto[i:i+ancho] for i in range(0, len(texto), ancho)] or ['']


def imprimir_ticket(venta, empresa):
    """
    Envía el ticket de la venta a la impresora térmica configurada.
    Retorna (True, None) si tuvo éxito, (False, str_error) si falló.
    El fallo NO debe interrumpir el flujo de venta — llamar dentro de try/except externo.
    """
    try:
        from escpos.printer import Win32Raw
    except ImportError:
        return False, "python-escpos no instalado."

    nombre_impresora = (getattr(empresa, 'nombre_impresora', '') or '').strip()
    if not nombre_impresora:
        return False, "Nombre de impresora no configurado."

    try:
        p = Win32Raw(nombre_impresora)
    except Exception as e:
        return False, f"No se pudo conectar a '{nombre_impresora}': {e}"

    try:
        sep  = "-" * ANCHO + "\n"
        tasa = venta.tasa_aplicada

        # ── Encabezado empresa ────────────────────────────────────
        p.set(align='center', bold=True, double_width=True, double_height=True)
        nombre_empresa = (empresa.nombre if empresa and empresa.nombre else "Mi Empresa")
        p.text(nombre_empresa[:21] + "\n")  # max ~21 chars a doble ancho

        p.set(align='center', bold=False, double_width=False, double_height=False)
        if empresa and empresa.rif:
            p.text(f"RIF: {empresa.rif}\n")
        if empresa and empresa.telefono:
            p.text(f"Tel: {empresa.telefono}\n")
        if empresa and empresa.direccion:
            for linea in _wrap(empresa.direccion, ANCHO):
                p.text(linea + "\n")

        p.set(align='left')
        p.text(sep)

        # ── Datos del ticket ──────────────────────────────────────
        from django.utils import timezone as tz
        fecha_local = tz.localtime(venta.fecha)
        p.text(f"Factura N: {venta.numero_fmt}  {fecha_local.strftime('%d/%m/%Y %H:%M')}\n")
        p.text(f"N Control: {venta.numero_control_fmt}\n")
        p.text(f"Metodo: {venta.get_metodo_pago_display()}\n")
        p.text(sep)

        # ── Ítems ────────────────────────────────────────────────
        COL_NOMBRE = 26
        COL_CANT   = 4
        COL_TOTAL  = ANCHO - COL_NOMBRE - COL_CANT - 2

        p.set(bold=True)
        cabecera = f"{'Descripcion':<{COL_NOMBRE}} {'Cant':>{COL_CANT}} {'Total':>{COL_TOTAL}}\n"
        p.text(cabecera)
        p.set(bold=False)
        p.text(sep)

        for d in venta.detalles.select_related('producto').all():
            subtotal_bs = round(float(d.subtotal_usd) * float(tasa), 2)
            subtotal_str = f"{subtotal_bs:.2f}"
            nombre = d.producto.nombre

            # Primera línea con cantidad y total
            primera = f"{nombre[:COL_NOMBRE]:<{COL_NOMBRE}} {d.cantidad:>{COL_CANT}} {subtotal_str:>{COL_TOTAL}}\n"
            p.text(primera)

            # Si el nombre es largo, continuar en líneas siguientes
            for linea in _wrap(nombre[COL_NOMBRE:], COL_NOMBRE):
                p.text(f"  {linea}\n")

        p.text(sep)

        # ── Total ────────────────────────────────────────────────
        total_str = f"Bs. {float(venta.total_bs):.2f}"
        p.set(align='right', bold=True, double_height=True)
        p.text(f"TOTAL: {total_str}\n")
        p.set(align='left', bold=False, double_height=False)

        p.text(sep)

        # ── Desglose fiscal SENIAT ────────────────────────────────
        if float(venta.monto_exento_bs) > 0:
            p.text(f"{'Monto Exento:':<16} Bs. {float(venta.monto_exento_bs):.2f}\n")
        if float(venta.base_imponible_bs) > 0:
            p.text(f"{'Base Impon.:':<16} Bs. {float(venta.base_imponible_bs):.2f}\n")
            p.text(f"{'Monto IVA:':<16} Bs. {float(venta.iva_bs):.2f}\n")

        p.text(sep)

        # ── Desglose de pago ──────────────────────────────────────
        p.text(f"{'Tasa BCV:':<16} Bs. {float(tasa):.2f}\n")

        if venta.monto_recibido is not None:
            if venta.metodo_pago == 'EFECTIVO_BS':
                recibido_bs = float(venta.monto_recibido)
                vuelto_bs   = float(venta.vuelto or 0)
            else:
                recibido_bs = round(float(venta.monto_recibido) * float(tasa), 2)
                vuelto_bs   = round(float(venta.vuelto or 0) * float(tasa), 2)
            p.text(f"{'Recibido:':<16} Bs. {recibido_bs:.2f}\n")
            p.text(f"{'Vuelto:':<16} Bs. {vuelto_bs:.2f}\n")

        if venta.notas:
            p.text(sep)
            p.text("Nota: " + venta.notas[:ANCHO - 6] + "\n")

        p.text(sep)

        # ── Pie ──────────────────────────────────────────────────
        p.set(align='center', bold=True)
        p.text("Gracias por su compra!\n")
        p.set(align='center', bold=False)
        p.text(nombre_empresa + "\n")

        p.ln(4)
        p.cut()
        p.close()
        return True, None

    except Exception as e:
        try:
            p.close()
        except Exception:
            pass
        return False, str(e)
