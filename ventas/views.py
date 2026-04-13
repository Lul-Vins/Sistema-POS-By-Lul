from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
import json

from inventario.models import Producto
from configuracion.models import Empresa, Moneda
from .models import Venta, DetalleVenta


def venta(request):
    moneda  = Moneda.objects.first()
    empresa = Empresa.objects.first()
    tasa    = moneda.tasa_cambio if moneda else None

    return render(request, 'pos/venta.html', {
        'tasa':          tasa,
        'moneda':        moneda,
        'empresa':       empresa,
        'metodos_pago':  Venta.METODO_PAGO,
    })


@require_POST
def procesar_venta(request):
    try:
        body        = json.loads(request.body)
        carrito     = body.get('carrito', [])
        metodo_pago = body.get('metodo_pago', '')
        notas       = body.get('notas', '')

        if not carrito:
            return JsonResponse({'ok': False, 'error': 'El carrito está vacío.'}, status=400)

        if metodo_pago not in dict(Venta.METODO_PAGO):
            return JsonResponse({'ok': False, 'error': 'Método de pago inválido.'}, status=400)

        # Construir lista de items para crear_desde_carrito
        items = []
        for item in carrito:
            producto = get_object_or_404(Producto, pk=item['id'], activo=True)
            items.append({'producto': producto, 'cantidad': int(item['cantidad'])})

        venta_obj = Venta.crear_desde_carrito(items, metodo_pago, notas)

        return JsonResponse({
            'ok':      True,
            'venta_id': venta_obj.id,
            'total_usd': float(venta_obj.total_usd),
            'total_bs':  float(venta_obj.total_bs),
        })

    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': 'Error interno al procesar la venta.'}, status=500)


def buscar_productos(request):
    q = request.GET.get('q', '').strip()

    if len(q) < 2:
        return JsonResponse({'productos': []})

    # Búsqueda por código de barras (exacto) o nombre (icontains)
    qs = Producto.objects.filter(activo=True).select_related('categoria')
    qs = qs.filter(nombre__icontains=q) | qs.filter(codigo_barras=q)
    qs = qs.distinct()[:30]  # máximo 30 resultados

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
            'stock_bajo': p.stock_bajo,
        })

    return JsonResponse({'productos': data})
