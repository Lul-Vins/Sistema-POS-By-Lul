from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
import json
from .models import Empresa, Moneda


def configuracion_index(request):
    empresa = Empresa.objects.first()
    moneda = Moneda.objects.first()

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        rif = 'J' + request.POST.get('rif', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        direccion = request.POST.get('direccion', '').strip()
        limpiar_logo = request.POST.get('limpiar_logo') == '1'

        if not nombre or not rif:
            messages.error(request, 'El nombre y el RIF son obligatorios.')
            return render(request, 'configuracion/index.html', {
                'empresa': empresa,
                'moneda': moneda,
                'tasa': moneda.tasa_cambio if moneda else None,
                'post_data': request.POST,
            })

        if empresa:
            empresa.nombre = nombre
            empresa.rif = rif
            empresa.telefono = telefono
            empresa.direccion = direccion

            if limpiar_logo and empresa.logo:
                empresa.logo.delete(save=False)
                empresa.logo = None
            elif 'logo' in request.FILES:
                if empresa.logo:
                    empresa.logo.delete(save=False)
                empresa.logo = request.FILES['logo']

            empresa.save()
        else:
            empresa = Empresa(nombre=nombre, rif=rif, telefono=telefono, direccion=direccion)
            if 'logo' in request.FILES:
                empresa.logo = request.FILES['logo']
            empresa.save()

        messages.success(request, 'Configuración guardada correctamente.')
        return redirect('configuracion:index')

    return render(request, 'configuracion/index.html', {
        'empresa': empresa,
        'moneda': moneda,
        'tasa': moneda.tasa_cambio if moneda else None,
    })


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
