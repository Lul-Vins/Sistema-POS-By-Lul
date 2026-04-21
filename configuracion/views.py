from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
import json
from .models import Empresa, Moneda
from pos_core_lul.decorators import solo_admin, login_required


@solo_admin
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


@solo_admin
def listar_impresoras(request):
    """Devuelve las impresoras instaladas en Windows."""
    try:
        import win32print
        impresoras = [
            p[2] for p in
            win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )
        ]
        predeterminada = win32print.GetDefaultPrinter()
    except Exception:
        impresoras    = []
        predeterminada = ''
    return JsonResponse({'impresoras': impresoras, 'predeterminada': predeterminada})


@solo_admin
@require_POST
def guardar_impresora(request):
    try:
        body   = json.loads(request.body)
        nombre = body.get('nombre', '').strip()
        empresa = Empresa.objects.first()
        if empresa is None:
            return JsonResponse({'ok': False, 'error': 'No hay empresa configurada.'}, status=400)
        empresa.nombre_impresora = nombre
        empresa.save(update_fields=['nombre_impresora'])
        return JsonResponse({'ok': True})
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Error interno.'}, status=500)


@solo_admin
@require_POST
def test_impresora(request):
    try:
        from ventas.printing import imprimir_ticket
        empresa = Empresa.objects.first()
        if not empresa or not empresa.nombre_impresora:
            return JsonResponse({'ok': False, 'error': 'No hay impresora configurada.'}, status=400)

        from escpos.printer import Win32Raw
        p = Win32Raw(empresa.nombre_impresora)
        p.set(align='center', bold=True)
        p.text("--- IMPRESORA LISTA ---\n")
        p.set(bold=False)
        p.text(f"{empresa.nombre}\n")
        p.text("Prueba de impresion OK\n")
        p.ln(3)
        p.cut()
        p.close()
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


@solo_admin
@require_POST
def toggle_impresora(request):
    try:
        body    = json.loads(request.body)
        activado = bool(body.get('activado', False))
        empresa = Empresa.objects.first()
        if empresa is None:
            return JsonResponse({'ok': False, 'error': 'No hay empresa configurada.'}, status=400)
        empresa.imprimir_ticket = activado
        empresa.save(update_fields=['imprimir_ticket'])
        return JsonResponse({'ok': True, 'imprimir_ticket': activado})
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Error interno.'}, status=500)


@solo_admin
@require_POST
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


# ── Gestión de usuarios ───────────────────────────────────────────

@solo_admin
def usuarios_index(request):
    empresa  = Empresa.objects.first()
    moneda   = Moneda.objects.first()
    usuarios = User.objects.order_by('first_name', 'username')
    return render(request, 'configuracion/usuarios.html', {
        'usuarios': usuarios,
        'empresa':  empresa,
        'moneda':   moneda,
        'tasa':     moneda.tasa_cambio if moneda else None,
    })


@solo_admin
@require_POST
def crear_usuario(request):
    try:
        data      = json.loads(request.body)
        nombre    = data.get('nombre', '').strip()
        username  = data.get('username', '').strip()
        password  = data.get('password', '').strip()
        es_admin  = bool(data.get('es_admin', False))

        if not nombre or not username or not password:
            return JsonResponse({'ok': False, 'error': 'Completa todos los campos.'}, status=400)
        if len(password) < 4:
            return JsonResponse({'ok': False, 'error': 'La contraseña debe tener al menos 4 caracteres.'}, status=400)
        if User.objects.filter(username=username).exists():
            return JsonResponse({'ok': False, 'error': 'Ese nombre de usuario ya está en uso.'}, status=400)

        partes = nombre.split(' ', 1)
        user   = User.objects.create_user(
            username   = username,
            password   = password,
            first_name = partes[0],
            last_name  = partes[1] if len(partes) > 1 else '',
            is_staff   = es_admin,
        )
        return JsonResponse({
            'ok':       True,
            'id':       user.id,
            'nombre':   user.get_full_name() or user.username,
            'username': user.username,
            'es_admin': user.is_staff,
            'activo':   user.is_active,
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)


@solo_admin
@require_POST
def editar_usuario(request, pk):
    try:
        user = User.objects.get(pk=pk)
        data = json.loads(request.body)

        nombre   = data.get('nombre', '').strip()
        password = data.get('password', '').strip()
        es_admin = bool(data.get('es_admin', False))
        activo   = bool(data.get('activo', True))

        # No permitir desactivar ni quitar admin al propio usuario
        if user == request.user:
            activo   = True
            es_admin = True

        if nombre:
            partes          = nombre.split(' ', 1)
            user.first_name = partes[0]
            user.last_name  = partes[1] if len(partes) > 1 else ''

        if password:
            if len(password) < 4:
                return JsonResponse({'ok': False, 'error': 'La contraseña debe tener al menos 4 caracteres.'}, status=400)
            user.set_password(password)

        user.is_staff  = es_admin
        user.is_active = activo
        user.save()

        return JsonResponse({
            'ok':       True,
            'id':       user.id,
            'nombre':   user.get_full_name() or user.username,
            'username': user.username,
            'es_admin': user.is_staff,
            'activo':   user.is_active,
        })
    except User.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Usuario no encontrado.'}, status=404)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)
