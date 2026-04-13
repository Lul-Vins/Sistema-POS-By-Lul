from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
import json
from .models import Moneda


@require_POST
@csrf_protect
def actualizar_tasa(request):
    try:
        body = json.loads(request.body)
        nueva_tasa = body.get('tasa')

        if nueva_tasa is None:
            return JsonResponse({'ok': False, 'error': 'Tasa no proporcionada.'}, status=400)

        nueva_tasa = float(nueva_tasa)
        if nueva_tasa <= 0:
            return JsonResponse({'ok': False, 'error': 'La tasa debe ser mayor a 0.'}, status=400)

        moneda = Moneda.objects.first()
        if moneda is None:
            return JsonResponse({'ok': False, 'error': 'No hay configuración de moneda. Créela desde el admin.'}, status=400)

        moneda.tasa_cambio = nueva_tasa
        moneda.save()

        return JsonResponse({
            'ok': True,
            'tasa': float(moneda.tasa_cambio),
            'ultima_actualizacion': moneda.ultima_actualizacion.strftime('%d/%m/%Y %H:%M'),
        })

    except (ValueError, json.JSONDecodeError):
        return JsonResponse({'ok': False, 'error': 'Valor inválido.'}, status=400)
