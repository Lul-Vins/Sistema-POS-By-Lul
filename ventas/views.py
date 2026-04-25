from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Sum, Count
from django.utils import timezone
import json
from datetime import date

from inventario.models import Producto, Categoria
from configuracion.models import Empresa, Moneda
from .models import Venta, DetalleVenta
from pos_core_lul.decorators import login_required, solo_admin


@login_required
def venta(request):
    moneda  = Moneda.objects.first()
    empresa = Empresa.objects.first() or Empresa()
    tasa    = moneda.tasa_cambio if moneda else None

    tasa_vencida = False
    if moneda:
        antigüedad = timezone.now() - moneda.ultima_actualizacion
        tasa_vencida = antigüedad.total_seconds() > 15 * 3600

    categorias = Categoria.objects.order_by('nombre')

    return render(request, 'pos/venta.html', {
        'tasa':             tasa,
        'moneda':           moneda,
        'empresa':          empresa,
        'metodos_pago':     Venta.METODO_PAGO,
        'imprimir_ticket':  empresa.imprimir_ticket if empresa else False,
        'tasa_vencida':     tasa_vencida,
        'categorias':       categorias,
    })


@login_required
def ticket(request, pk):
    venta_obj = get_object_or_404(Venta, pk=pk)
    empresa   = Empresa.objects.first()
    tasa      = venta_obj.tasa_aplicada

    detalles_bs = [
        {
            'nombre':      d.producto.nombre,
            'cantidad':    d.cantidad,
            'precio_bs':   round(d.precio_usd_capturado * tasa, 2),
            'subtotal_bs': round(d.subtotal_usd * tasa, 2),
        }
        for d in venta_obj.detalles.select_related('producto').all()
    ]

    # Normalizar monto_recibido y vuelto a Bs para mostrar en el ticket
    monto_recibido_bs = None
    vuelto_bs         = None
    if venta_obj.monto_recibido is not None:
        if venta_obj.metodo_pago == 'EFECTIVO_BS':
            monto_recibido_bs = venta_obj.monto_recibido
            vuelto_bs         = venta_obj.vuelto
        else:
            monto_recibido_bs = round(venta_obj.monto_recibido * tasa, 2)
            vuelto_bs         = round(venta_obj.vuelto * tasa, 2) if venta_obj.vuelto else 0

    return render(request, 'pos/ticket.html', {
        'venta':              venta_obj,
        'empresa':            empresa,
        'detalles_bs':        detalles_bs,
        'tasa':               tasa,
        'monto_recibido_bs':  monto_recibido_bs,
        'vuelto_bs':          vuelto_bs,
    })


@login_required
@require_POST
def procesar_venta(request):
    try:
        body           = json.loads(request.body)
        carrito        = body.get('carrito', [])
        metodo_pago    = body.get('metodo_pago', '')
        notas          = body.get('notas', '')
        monto_recibido = body.get('monto_recibido')  # None si no es efectivo
        vuelto         = body.get('vuelto')

        empresa = Empresa.objects.first() or Empresa()

        if not carrito:
            return JsonResponse({'ok': False, 'error': 'El carrito está vacío.'}, status=400)

        if metodo_pago not in dict(Venta.METODO_PAGO):
            return JsonResponse({'ok': False, 'error': 'Método de pago inválido.'}, status=400)

        # Construir lista de items para crear_desde_carrito
        items = []
        for item in carrito:
            producto = get_object_or_404(Producto, pk=item['id'], activo=True)
            items.append({'producto': producto, 'cantidad': int(item['cantidad'])})

        venta_obj = Venta.crear_desde_carrito(items, metodo_pago, notas, monto_recibido, vuelto, vendedor=request.user)

        # Impresión automática ESC/POS (fallo nunca cancela la venta)
        ticket_impreso = False
        ticket_error   = None
        if empresa and empresa.imprimir_ticket:
            from .printing import imprimir_ticket
            ticket_impreso, ticket_error = imprimir_ticket(venta_obj, empresa)

        return JsonResponse({
            'ok':             True,
            'venta_id':       venta_obj.id,
            'total_usd':      float(venta_obj.total_usd),
            'total_bs':       float(venta_obj.total_bs),
            'ticket_impreso': ticket_impreso,
            'ticket_error':   ticket_error,
        })

    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': 'Error interno al procesar la venta.'}, status=500)


@login_required
def buscar_productos(request):
    from django.db.models import Q

    q      = request.GET.get('q', '').strip()
    cat_id = request.GET.get('cat', '').strip()

    if len(q) < 2 and not cat_id:
        return JsonResponse({'productos': []})

    qs = Producto.objects.filter(activo=True).select_related('categoria')

    if cat_id:
        qs = qs.filter(categoria_id=cat_id)

    if len(q) >= 2:
        qs = qs.filter(Q(nombre__icontains=q) | Q(codigo_barras=q))

    limite = 30 if len(q) >= 2 else 60
    qs = qs.distinct()[:limite]

    try:
        tasa = Moneda.get_tasa_activa()
    except ValueError:
        tasa = None

    data = []
    for p in qs:
        precio_bs = float(p.precio_usd * tasa) if tasa else None
        data.append({
            'id':        p.id,
            'nombre':    p.nombre,
            'precio_usd': float(p.precio_usd),
            'precio_bs':  round(precio_bs, 2) if precio_bs else None,
            'imagen':    p.imagen.url if p.imagen else None,
            'stock_actual': p.stock_actual,
            'stock_bajo': p.stock_bajo,
        })

    return JsonResponse({'productos': data})


@login_required
def tasa_estado(request):
    """Polling endpoint: devuelve si la tasa está vencida y su valor actual."""
    moneda = Moneda.objects.first()
    if not moneda:
        return JsonResponse({'tasa_vencida': True, 'tasa': None, 'ultima_actualizacion': None})

    antigüedad    = timezone.now() - moneda.ultima_actualizacion
    tasa_vencida  = antigüedad.total_seconds() > 15 * 3600

    return JsonResponse({
        'tasa_vencida':        tasa_vencida,
        'tasa':                float(moneda.tasa_cambio),
        'ultima_actualizacion': moneda.ultima_actualizacion.strftime('%d/%m %H:%M'),
    })


@login_required
def mis_ventas(request):
    fecha_str = request.GET.get('fecha', '')
    try:
        fecha = date.fromisoformat(fecha_str)
    except ValueError:
        fecha = timezone.localdate()

    ventas = (
        Venta.objects
        .filter(vendedor=request.user, fecha__date=fecha)
        .prefetch_related('detalles__producto')
        .order_by('-fecha')
    )

    completadas = ventas.filter(estado='COMPLETADA')
    resumen = completadas.aggregate(
        total_bs=Sum('total_bs'),
        cantidad=Count('id'),
    )

    moneda  = Moneda.objects.first()
    empresa = Empresa.objects.first() or Empresa()

    return render(request, 'pos/mis_ventas.html', {
        'ventas':  ventas,
        'resumen': resumen,
        'fecha':   fecha,
        'tasa':    moneda.tasa_cambio if moneda else None,
        'moneda':  moneda,
        'empresa': empresa,
    })
