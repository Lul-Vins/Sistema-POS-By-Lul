from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Sum, Count
from django.utils import timezone
import json
from datetime import date

from ventas.models import Venta, DetalleVenta
from configuracion.models import Empresa, Moneda


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
