from django.shortcuts import render
from django.http import JsonResponse
from inventario.models import Producto
from configuracion.models import Empresa, Moneda


def venta(request):
    moneda  = Moneda.objects.first()
    empresa = Empresa.objects.first()
    tasa    = moneda.tasa_cambio if moneda else None

    return render(request, 'pos/venta.html', {
        'tasa':    tasa,
        'moneda':  moneda,
        'empresa': empresa,
    })


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
