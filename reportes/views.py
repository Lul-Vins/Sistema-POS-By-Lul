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
    """Obtiene totales esperados del día para el cierre de caja."""
    fecha_str = request.GET.get('fecha', '')
    try:
        fecha = date.fromisoformat(fecha_str)
    except ValueError:
        fecha = timezone.localdate()

    # Calcular efectivo esperado (solo COMPLETADAS)
    ventas_efectivo = Venta.objects.filter(
        fecha__date=fecha,
        estado='COMPLETADA',
        metodo_pago__in=['EFECTIVO_USD', 'EFECTIVO_BS']
    )

    efectivo_usd_esperado = sum(
        float(v.total_usd) for v in ventas_efectivo if v.metodo_pago == 'EFECTIVO_USD'
    )
    efectivo_bs_esperado = sum(
        float(v.total_bs) for v in ventas_efectivo if v.metodo_pago == 'EFECTIVO_BS'
    )

    # Verificar si ya existe cierre para este día
    cierre_existente = CierreCaja.objects.filter(fecha=fecha).first()

    # Histórico de últimos 10 cierres
    historico = CierreCaja.objects.order_by('-fecha')[:10]

    moneda = Moneda.objects.first()
    empresa = Empresa.objects.first()

    return render(request, 'reportes/cierre_caja.html', {
        'fecha': fecha,
        'efectivo_usd_esperado': efectivo_usd_esperado,
        'efectivo_bs_esperado': efectivo_bs_esperado,
        'cierre_existente': cierre_existente,
        'historico': historico,
        'moneda': moneda,
        'empresa': empresa,
        'tasa': moneda.tasa_cambio if moneda else None,
    })


@require_POST
def guardar_cierre(request):
    """Guarda un cierre de caja."""
    try:
        data = json.loads(request.body)
        fecha_str = data.get('fecha', '')
        fecha = date.fromisoformat(fecha_str)

        efectivo_usd_real = float(data.get('efectivo_usd_real', 0))
        efectivo_bs_real = float(data.get('efectivo_bs_real', 0))
        notas = data.get('notas', '').strip()

        # Calcular esperado
        ventas_efectivo = Venta.objects.filter(
            fecha__date=fecha,
            estado='COMPLETADA',
            metodo_pago__in=['EFECTIVO_USD', 'EFECTIVO_BS']
        )

        efectivo_usd_esperado = sum(
            float(v.total_usd) for v in ventas_efectivo if v.metodo_pago == 'EFECTIVO_USD'
        )
        efectivo_bs_esperado = sum(
            float(v.total_bs) for v in ventas_efectivo if v.metodo_pago == 'EFECTIVO_BS'
        )

        # Calcular diferencias
        diferencia_usd = efectivo_usd_real - efectivo_usd_esperado
        diferencia_bs = efectivo_bs_real - efectivo_bs_esperado

        # Crear o actualizar cierre
        cierre, created = CierreCaja.objects.update_or_create(
            fecha=fecha,
            defaults={
                'efectivo_usd_esperado': efectivo_usd_esperado,
                'efectivo_bs_esperado': efectivo_bs_esperado,
                'efectivo_usd_real': efectivo_usd_real,
                'efectivo_bs_real': efectivo_bs_real,
                'diferencia_usd': diferencia_usd,
                'diferencia_bs': diferencia_bs,
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
