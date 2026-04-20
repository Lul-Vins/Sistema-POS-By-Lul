from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Sum, Count, Q
from django.utils import timezone
import json
from datetime import date

from ventas.models import Venta, DetalleVenta
from configuracion.models import Empresa, Moneda
from .models import CierreCaja


def index(request):
    fecha_str = request.GET.get('fecha', '')
    try:
        fecha = date.fromisoformat(fecha_str)
    except ValueError:
        fecha = timezone.localdate()

    ventas = (
        Venta.objects
        .filter(fecha__date=fecha)
        .prefetch_related('detalles__producto')
        .order_by('-fecha')
    )

    completadas = ventas.filter(estado='COMPLETADA')
    resumen = completadas.aggregate(
        total_usd=Sum('total_usd'),
        total_bs=Sum('total_bs'),
        cantidad=Count('id'),
    )

    moneda  = Moneda.objects.first()
    empresa = Empresa.objects.first()

    return render(request, 'reportes/index.html', {
        'ventas':   ventas,
        'resumen':  resumen,
        'fecha':    fecha,
        'tasa':     moneda.tasa_cambio if moneda else None,
        'moneda':   moneda,
        'empresa':  empresa,
    })


@require_POST
def anular_venta(request, pk):
    venta = get_object_or_404(Venta, pk=pk)

    if venta.estado == 'ANULADA':
        return JsonResponse({'ok': False, 'error': 'La venta ya está anulada.'}, status=400)

    # Revertir stock
    for detalle in venta.detalles.select_related('producto'):
        detalle.producto.stock_actual += detalle.cantidad
        detalle.producto.save(update_fields=['stock_actual'])

    venta.estado = 'ANULADA'
    venta.save(update_fields=['estado'])

    return JsonResponse({'ok': True})


def cierre_caja(request):
    """Obtiene totales por método de pago del día para el cierre de caja."""
    fecha_str = request.GET.get('fecha', '')
    try:
        fecha = date.fromisoformat(fecha_str)
    except ValueError:
        fecha = timezone.localtime().date()

    # Obtener todas las ventas completadas del día
    ventas_dia = Venta.objects.filter(
        fecha__date=fecha,
        estado='COMPLETADA'
    ).prefetch_related('detalles__producto').order_by('-fecha')

    # Agrupar por método de pago y calcular totales
    resumen_metodos = {}
    for codigo_metodo, nombre_metodo in Venta.METODO_PAGO:
        ventas_metodo = ventas_dia.filter(metodo_pago=codigo_metodo)
        total_usd = sum(float(v.total_usd) for v in ventas_metodo)
        total_bs = sum(float(v.total_bs) for v in ventas_metodo)

        resumen_metodos[codigo_metodo] = {
            'nombre': nombre_metodo,
            'codigo': codigo_metodo,
            'total_usd': total_usd,
            'total_bs': total_bs,
            'cantidad': ventas_metodo.count(),
            'ventas': list(ventas_metodo),
        }

    # Crear lista de métodos con datos (para iterar en template)
    resumen_metodos_lista = list(resumen_metodos.values())

    total_general_usd = sum(m['total_usd'] for m in resumen_metodos_lista)
    total_general_bs  = sum(m['total_bs']  for m in resumen_metodos_lista)
    total_ventas      = sum(m['cantidad']  for m in resumen_metodos_lista)

    # Verificar si ya existe cierre para este día
    cierre_existente = CierreCaja.objects.filter(fecha=fecha).first()

    # Histórico de últimos 10 cierres
    historico = CierreCaja.objects.order_by('-fecha')[:10]

    moneda = Moneda.objects.first()
    empresa = Empresa.objects.first()

    return render(request, 'reportes/cierre_caja.html', {
        'fecha': fecha,
        'resumen_metodos': resumen_metodos,
        'resumen_metodos_lista': resumen_metodos_lista,
        'total_general_usd': total_general_usd,
        'total_general_bs':  total_general_bs,
        'total_ventas':      total_ventas,
        'cierre_existente':  cierre_existente,
        'historico':         historico,
        'moneda':            moneda,
        'empresa':           empresa,
        'tasa':              moneda.tasa_cambio if moneda else None,
    })


def imprimir_cierre(request):
    fecha_str = request.GET.get('fecha', '')
    try:
        fecha = date.fromisoformat(fecha_str)
    except ValueError:
        fecha = timezone.localdate()

    ventas_dia = (
        Venta.objects
        .filter(fecha__date=fecha, estado='COMPLETADA')
        .prefetch_related('detalles__producto')
        .order_by('fecha')
    )

    resumen_metodos = []
    for codigo_metodo, nombre_metodo in Venta.METODO_PAGO:
        ventas_metodo = [v for v in ventas_dia if v.metodo_pago == codigo_metodo]
        if not ventas_metodo:
            continue
        total_usd = sum(float(v.total_usd) for v in ventas_metodo)
        total_bs  = sum(float(v.total_bs)  for v in ventas_metodo)
        resumen_metodos.append({
            'nombre':    nombre_metodo,
            'codigo':    codigo_metodo,
            'total_usd': total_usd,
            'total_bs':  total_bs,
            'cantidad':  len(ventas_metodo),
            'ventas':    ventas_metodo,
        })

    total_general_usd = sum(m['total_usd'] for m in resumen_metodos)
    total_general_bs  = sum(m['total_bs']  for m in resumen_metodos)
    total_ventas      = sum(m['cantidad']  for m in resumen_metodos)

    moneda  = Moneda.objects.first()
    empresa = Empresa.objects.first()
    cierre  = CierreCaja.objects.filter(fecha=fecha).first()

    return render(request, 'reportes/cierre_caja_print.html', {
        'fecha':             fecha,
        'resumen_metodos':   resumen_metodos,
        'total_general_usd': total_general_usd,
        'total_general_bs':  total_general_bs,
        'total_ventas':      total_ventas,
        'moneda':            moneda,
        'empresa':           empresa,
        'tasa':              moneda.tasa_cambio if moneda else None,
        'cierre':            cierre,
    })


@require_POST
def guardar_cierre(request):
    """Guarda un cierre de caja con desglose por método de pago."""
    try:
        data = json.loads(request.body)
        fecha_str = data.get('fecha', '')
        fecha = date.fromisoformat(fecha_str)
        notas = data.get('notas', '').strip()

        ventas_dia = Venta.objects.filter(fecha__date=fecha, estado='COMPLETADA')

        totales_usd = {}
        totales_bs = {}
        for codigo_metodo, _ in Venta.METODO_PAGO:
            qs = ventas_dia.filter(metodo_pago=codigo_metodo)
            totales_usd[codigo_metodo] = sum(float(v.total_usd) for v in qs)
            totales_bs[codigo_metodo] = sum(float(v.total_bs) for v in qs)

        efectivo_usd = totales_usd.get('EFECTIVO_USD', 0)
        efectivo_bs = totales_bs.get('EFECTIVO_BS', 0)

        cierre, created = CierreCaja.objects.update_or_create(
            fecha=fecha,
            defaults={
                'efectivo_usd_esperado': efectivo_usd,
                'efectivo_bs_esperado': efectivo_bs,
                'efectivo_usd_real': efectivo_usd,
                'efectivo_bs_real': efectivo_bs,
                'diferencia_usd': 0,
                'diferencia_bs': 0,
                'punto_de_venta_total': totales_usd.get('PUNTO_DE_VENTA', 0),
                'biopago_total': totales_usd.get('BIOPAGO', 0),
                'transferencia_total': totales_usd.get('TRANSFERENCIA', 0),
                'pago_movil_total': totales_usd.get('PAGO_MOVIL', 0),
                'mixto_total': totales_usd.get('MIXTO', 0),
                'notas': notas,
            }
        )

        return JsonResponse({
            'ok': True,
            'cierre_id': cierre.id,
            'accion': 'creado' if created else 'actualizado',
        })

    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': 'Error interno al guardar.'}, status=500)
