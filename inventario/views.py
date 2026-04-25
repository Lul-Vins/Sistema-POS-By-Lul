from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.template.response import TemplateResponse
from django.db.models import Count
import json
import math

from configuracion.models import Empresa, Moneda
from .models import Producto, Categoria
from pos_core_lul.decorators import solo_admin


@solo_admin
def index(request):
    moneda  = Moneda.objects.first()
    empresa = Empresa.objects.first() or Empresa()
    tasa    = moneda.tasa_cambio if moneda else None

    productos  = Producto.objects.select_related('categoria').order_by('nombre')
    categorias = Categoria.objects.order_by('nombre').annotate(num_productos=Count('productos'))

    cats_js = [{'id': c.id, 'nombre': c.nombre, 'num': c.num_productos} for c in categorias]

    return TemplateResponse(request, 'inventario/index.html', {
        'tasa':        tasa,
        'moneda':      moneda,
        'empresa':     empresa,
        'productos':   productos,
        'categorias':  categorias,
        'cats_js':     cats_js,
    })


@solo_admin
@require_POST
def guardar_producto(request):
    """Crea o actualiza un producto. pk=0 significa nuevo."""
    try:
        # Soporta multipart (con imagen) y JSON (sin imagen)
        if request.content_type and 'multipart' in request.content_type:
            data = request.POST
            imagen = request.FILES.get('imagen')
        else:
            data   = json.loads(request.body)
            imagen = None

        pk          = int(data.get('pk', 0))
        nombre      = data.get('nombre', '').strip()
        categoria_id = data.get('categoria_id') or None
        codigo_barras = data.get('codigo_barras', '').strip() or None
        precio_usd  = data.get('precio_usd')
        costo_usd   = data.get('costo_usd') or None
        stock_actual = data.get('stock_actual', 0)
        stock_minimo = data.get('stock_minimo', 5)
        activo       = str(data.get('activo', 'true')).lower() in ('true', '1', 'on')
        alicuota_iva = data.get('alicuota_iva', 'GENERAL')

        if not nombre:
            return JsonResponse({'ok': False, 'error': 'El nombre es obligatorio.'}, status=400)
        if not precio_usd:
            return JsonResponse({'ok': False, 'error': 'El precio es obligatorio.'}, status=400)
        if alicuota_iva not in dict(Producto.ALICUOTA_IVA):
            return JsonResponse({'ok': False, 'error': 'Alícuota IVA inválida.'}, status=400)

        precio_usd   = float(precio_usd)
        costo_usd    = float(costo_usd) if costo_usd else None
        stock_actual = int(stock_actual)
        stock_minimo = int(stock_minimo)

        if math.isnan(precio_usd) or math.isinf(precio_usd) or precio_usd <= 0:
            return JsonResponse({'ok': False, 'error': 'El precio debe ser un número positivo válido.'}, status=400)
        if precio_usd > 999999.99:
            return JsonResponse({'ok': False, 'error': 'El precio está fuera de rango.'}, status=400)
        if costo_usd is not None:
            if math.isnan(costo_usd) or math.isinf(costo_usd) or costo_usd < 0:
                return JsonResponse({'ok': False, 'error': 'El costo debe ser un número positivo válido.'}, status=400)
            if costo_usd > 999999.99:
                return JsonResponse({'ok': False, 'error': 'El costo está fuera de rango.'}, status=400)

        categoria    = Categoria.objects.get(pk=categoria_id) if categoria_id else None

        if pk:
            producto = get_object_or_404(Producto, pk=pk)
        else:
            producto = Producto()

        producto.nombre       = nombre
        producto.categoria    = categoria
        producto.codigo_barras = codigo_barras
        producto.precio_usd   = precio_usd
        producto.costo_usd    = costo_usd
        producto.stock_actual = stock_actual
        producto.stock_minimo = stock_minimo
        producto.activo       = activo
        producto.alicuota_iva = alicuota_iva

        if imagen:
            producto.imagen = imagen

        producto.save()

        return JsonResponse({
            'ok': True,
            'pk': producto.pk,
            'nombre': producto.nombre,
        })

    except Categoria.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Categoría no encontrada.'}, status=400)
    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': 'Error interno al guardar.'}, status=500)


@solo_admin
@require_POST
def eliminar_producto(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    try:
        producto.delete()
        return JsonResponse({'ok': True})
    except Exception:
        # Tiene ventas asociadas (PROTECT) — desactivar en lugar de eliminar
        producto.activo = False
        producto.save(update_fields=['activo'])
        return JsonResponse({
            'ok': True,
            'advertencia': f'"{producto.nombre}" tiene ventas registradas y fue desactivado en lugar de eliminado.',
        })


@solo_admin
@require_GET
def lista_categorias(request):
    cats = list(Categoria.objects.order_by('nombre').values('id', 'nombre'))
    return JsonResponse({'categorias': cats})


@solo_admin
@require_POST
def crear_categoria(request):
    try:
        data   = json.loads(request.body)
        nombre = data.get('nombre', '').strip()
        if not nombre:
            return JsonResponse({'ok': False, 'error': 'El nombre es obligatorio.'}, status=400)
        if Categoria.objects.filter(nombre__iexact=nombre).exists():
            return JsonResponse({'ok': False, 'error': 'Ya existe una categoría con ese nombre.'}, status=400)
        cat = Categoria.objects.create(nombre=nombre)
        return JsonResponse({'ok': True, 'id': cat.id, 'nombre': cat.nombre})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)


@solo_admin
@require_POST
def eliminar_categoria(request, pk):
    try:
        cat          = get_object_or_404(Categoria, pk=pk)
        num_productos = cat.productos.count()
        cat.delete()   # SET_NULL en FK — los productos quedan sin categoría
        return JsonResponse({'ok': True, 'num_productos': num_productos})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)
