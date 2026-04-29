import re
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum
import json
from datetime import date

from configuracion.models import Moneda, Empresa
from inventario.models import Producto
from pos_core_lul.decorators import solo_admin
from .models import Cliente, Fiado, DetalleFiado, PagoFiado


@solo_admin
def index(request):
    clientes = list(
        Cliente.objects
        .prefetch_related('fiados__pagos')
        .order_by('nombre')
    )

    for c in clientes:
        activos = [f for f in c.fiados.all() if f.estado in ('PENDIENTE', 'PARCIAL')]
        c.saldo_total   = sum(
            f.total_usd - sum(p.monto_usd for p in f.pagos.all())
            for f in activos
        )
        c.fiados_activos = len(activos)

    clientes.sort(key=lambda c: c.saldo_total, reverse=True)

    total_deuda  = sum(c.saldo_total for c in clientes)
    con_deuda    = sum(1 for c in clientes if c.saldo_total > 0)

    moneda  = Moneda.objects.first()
    empresa = Empresa.objects.first() or Empresa()

    return render(request, 'fiados/index.html', {
        'clientes':     clientes,
        'total_deuda':  total_deuda,
        'con_deuda':    con_deuda,
        'moneda':       moneda,
        'empresa':      empresa,
        'tasa':         moneda.tasa_cambio if moneda else None,
    })


@solo_admin
def cliente_detail(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    fiados  = list(
        cliente.fiados
        .prefetch_related('detalles__producto', 'pagos__registrado_por')
        .all()
    )

    moneda  = Moneda.objects.first()
    empresa = Empresa.objects.first() or Empresa()
    tasa    = moneda.tasa_cambio if moneda else None
    _D2     = Decimal('0.01')

    for f in fiados:
        pagado_usd       = sum(p.monto_usd for p in f.pagos.all())
        pagado_bs        = sum(p.monto_bs  for p in f.pagos.all())
        f.pagado_calc    = pagado_usd
        f.pagado_bs_calc = pagado_bs
        f.saldo_calc     = max(Decimal('0'), f.total_usd - pagado_usd)
        # Lo que debe pagar HOY en Bs = saldo USD × tasa actual
        f.saldo_bs_hoy   = (f.saldo_calc * tasa).quantize(_D2) if tasa else None
        f.pct_pagado     = min(100, int(pagado_usd / f.total_usd * 100)) if f.total_usd else 100

    activos          = [f for f in fiados if f.estado in ('PENDIENTE', 'PARCIAL')]
    total_fiado_usd  = sum(f.total_usd   for f in fiados if f.estado != 'ANULADO')
    total_pagado_usd = sum(f.pagado_calc for f in fiados if f.estado != 'ANULADO')
    total_pagado_bs  = sum(f.pagado_bs_calc for f in fiados if f.estado != 'ANULADO')
    saldo_pendiente  = max(Decimal('0'), total_fiado_usd - total_pagado_usd)
    # Bs a cobrar hoy por toda la deuda pendiente
    saldo_pendiente_bs_hoy = (saldo_pendiente * tasa).quantize(_D2) if tasa else None

    return render(request, 'fiados/cliente.html', {
        'cliente':               cliente,
        'fiados':                fiados,
        'activos':               activos,
        'total_fiado_usd':       total_fiado_usd,
        'total_pagado_usd':      total_pagado_usd,
        'total_pagado_bs':       total_pagado_bs,
        'saldo_pendiente':       saldo_pendiente,
        'saldo_pendiente_bs_hoy': saldo_pendiente_bs_hoy,
        'metodos_pago':          PagoFiado.METODO_PAGO,
        'moneda':                moneda,
        'empresa':               empresa,
        'tasa':                  tasa,
    })


@solo_admin
@require_POST
def crear_cliente(request):
    try:
        data      = json.loads(request.body)
        nombre    = data.get('nombre', '').strip()
        telefono  = re.sub(r'\D', '', data.get('telefono', '').strip())
        direccion = data.get('direccion', '').strip()
        notas     = data.get('notas', '').strip()
        forzar    = data.get('forzar', False)

        if not nombre:
            return JsonResponse({'ok': False, 'error': 'El nombre es obligatorio.'}, status=400)
        if len(nombre) > 200:
            return JsonResponse({'ok': False, 'error': 'El nombre no puede superar 200 caracteres.'}, status=400)
        if len(telefono) > 20:
            return JsonResponse({'ok': False, 'error': 'El teléfono no puede superar 20 dígitos.'}, status=400)
        if len(direccion) > 300:
            return JsonResponse({'ok': False, 'error': 'La dirección no puede superar 300 caracteres.'}, status=400)
        if len(notas) > 500:
            return JsonResponse({'ok': False, 'error': 'Las notas no pueden superar 500 caracteres.'}, status=400)

        if not forzar and Cliente.objects.filter(nombre__iexact=nombre).exists():
            return JsonResponse({
                'ok':        False,
                'advertencia': True,
                'error':     f'Ya existe un cliente llamado "{nombre}". ¿Deseas crear otro de todas formas?',
            }, status=200)

        cliente = Cliente.objects.create(
            nombre    = nombre,
            telefono  = telefono,
            direccion = direccion,
            notas     = notas,
        )
        return JsonResponse({
            'ok':       True,
            'id':       cliente.id,
            'nombre':   cliente.nombre,
            'telefono': cliente.telefono,
            'url':      f'/fiados/cliente/{cliente.id}/',
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)


@solo_admin
@require_POST
def editar_cliente(request, pk):
    try:
        cliente   = get_object_or_404(Cliente, pk=pk)
        data      = json.loads(request.body)
        nombre    = data.get('nombre', '').strip()
        telefono  = re.sub(r'\D', '', data.get('telefono', '').strip())
        direccion = data.get('direccion', '').strip()
        notas     = data.get('notas', '').strip()

        if not nombre:
            return JsonResponse({'ok': False, 'error': 'El nombre es obligatorio.'}, status=400)
        if len(nombre) > 200:
            return JsonResponse({'ok': False, 'error': 'El nombre no puede superar 200 caracteres.'}, status=400)
        if len(telefono) > 20:
            return JsonResponse({'ok': False, 'error': 'El teléfono no puede superar 20 dígitos.'}, status=400)
        if len(direccion) > 300:
            return JsonResponse({'ok': False, 'error': 'La dirección no puede superar 300 caracteres.'}, status=400)
        if len(notas) > 500:
            return JsonResponse({'ok': False, 'error': 'Las notas no pueden superar 500 caracteres.'}, status=400)

        cliente.nombre    = nombre
        cliente.telefono  = telefono
        cliente.direccion = direccion
        cliente.notas     = notas
        cliente.activo    = bool(data.get('activo', True))
        cliente.save()
        return JsonResponse({'ok': True, 'nombre': cliente.nombre})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)


@solo_admin
@require_POST
def nueva_venta_fiada(request, cliente_pk):
    try:
        cliente     = get_object_or_404(Cliente, pk=cliente_pk, activo=True)
        body        = json.loads(request.body)
        carrito_raw = body.get('carrito', [])
        notas       = body.get('notas', '').strip()

        if not carrito_raw:
            return JsonResponse({'ok': False, 'error': 'El carrito está vacío.'}, status=400)

        items = []
        for item in carrito_raw:
            producto = get_object_or_404(Producto, pk=item['id'], activo=True)
            items.append({'producto': producto, 'cantidad': int(item['cantidad'])})

        fiado = Fiado.crear_desde_carrito(items, cliente, vendedor=request.user, notas=notas)

        return JsonResponse({
            'ok':       True,
            'fiado_id': fiado.id,
            'total_usd': float(fiado.total_usd),
            'total_bs':  float(fiado.total_bs),
        })

    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': 'Error interno al crear el fiado.'}, status=500)


@solo_admin
@require_POST
def registrar_pago(request, fiado_pk):
    try:
        fiado = get_object_or_404(Fiado, pk=fiado_pk)

        if fiado.estado == 'ANULADO':
            return JsonResponse({'ok': False, 'error': 'El fiado está anulado.'}, status=400)
        if fiado.estado == 'PAGADO':
            return JsonResponse({'ok': False, 'error': 'Este fiado ya está saldado.'}, status=400)

        body   = json.loads(request.body)
        metodo = body.get('metodo_pago', '')
        notas  = body.get('notas', '').strip()
        _D2    = Decimal('0.01')

        if metodo not in dict(PagoFiado.METODO_PAGO):
            return JsonResponse({'ok': False, 'error': 'Método de pago inválido.'}, status=400)
        if len(notas) > 200:
            return JsonResponse({'ok': False, 'error': 'Las notas no pueden superar 200 caracteres.'}, status=400)

        moneda = Moneda.objects.first()
        tasa   = moneda.tasa_cambio if moneda else fiado.tasa_aplicada

        # La deuda es en USD (fija). El cliente paga Bs = saldo_usd × tasa_hoy.
        monto_bs_raw = body.get('monto_bs')
        if monto_bs_raw is not None:
            monto_bs  = Decimal(str(monto_bs_raw)).quantize(_D2, rounding=ROUND_HALF_UP)
            if monto_bs <= 0:
                return JsonResponse({'ok': False, 'error': 'El monto debe ser mayor a 0.'}, status=400)

            # Convertir Bs pagados → USD al cambio de HOY
            monto_usd = (monto_bs / tasa).quantize(_D2, rounding=ROUND_HALF_UP)

            saldo_usd = fiado.saldo_usd
            if monto_usd > saldo_usd:
                bs_maximo = (saldo_usd * tasa).quantize(_D2)
                return JsonResponse({
                    'ok': False,
                    'error': f'Excede el saldo. Máximo a pagar hoy: Bs. {bs_maximo} (= ${saldo_usd}).'
                }, status=400)

            # Si cubre el dólar completo, forzar cierre exacto del saldo USD
            if monto_usd >= saldo_usd:
                monto_usd = saldo_usd
        else:
            monto_usd = Decimal(str(body.get('monto_usd', 0))).quantize(_D2)
            if monto_usd <= 0:
                return JsonResponse({'ok': False, 'error': 'El monto debe ser mayor a 0.'}, status=400)
            if monto_usd > fiado.saldo_usd:
                return JsonResponse({
                    'ok': False,
                    'error': f'El monto (${monto_usd}) supera el saldo pendiente (${fiado.saldo_usd:.2f}).'
                }, status=400)
            monto_bs = (monto_usd * tasa).quantize(_D2, rounding=ROUND_HALF_UP)

        PagoFiado.objects.create(
            fiado          = fiado,
            monto_usd      = monto_usd,
            monto_bs       = monto_bs,
            tasa_aplicada  = tasa,
            metodo_pago    = metodo,
            notas          = notas,
            registrado_por = request.user,
        )

        fiado.actualizar_estado()

        return JsonResponse({
            'ok':          True,
            'nuevo_estado': fiado.estado,
            'saldo_usd':   float(fiado.saldo_usd),
        })

    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)


@solo_admin
@require_POST
def anular_fiado(request, pk):
    try:
        fiado = get_object_or_404(Fiado, pk=pk)

        if fiado.estado == 'ANULADO':
            return JsonResponse({'ok': False, 'error': 'Ya está anulado.'}, status=400)
        if fiado.estado == 'PAGADO':
            return JsonResponse({'ok': False, 'error': 'No se puede anular un fiado ya pagado.'}, status=400)

        for detalle in fiado.detalles.select_related('producto'):
            detalle.producto.stock_actual += detalle.cantidad
            detalle.producto.save(update_fields=['stock_actual'])

        fiado.estado = 'ANULADO'
        fiado.save(update_fields=['estado'])

        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)
