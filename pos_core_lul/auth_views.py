from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.views.decorators.http import require_POST

from configuracion.models import Empresa


def _empresa_ctx():
    return Empresa.objects.first()


def login_view(request):
    if request.user.is_authenticated:
        return redirect('pos:venta')

    empresa       = _empresa_ctx()
    sin_usuarios  = not User.objects.exists()
    error         = None

    if request.method == 'POST':
        accion = request.POST.get('accion', 'login')

        # ── Primer arranque: crear administrador inicial ──────────
        if accion == 'setup' and sin_usuarios:
            nombre    = request.POST.get('nombre', '').strip()
            username  = request.POST.get('username', '').strip()
            password  = request.POST.get('password', '').strip()
            password2 = request.POST.get('password2', '').strip()

            if not nombre or not username or not password:
                error = 'Completa todos los campos.'
            elif password != password2:
                error = 'Las contraseñas no coinciden.'
            elif len(password) < 4:
                error = 'La contraseña debe tener al menos 4 caracteres.'
            elif User.objects.filter(username=username).exists():
                error = 'Ese nombre de usuario ya existe.'
            else:
                partes = nombre.split(' ', 1)
                user = User.objects.create_user(
                    username   = username,
                    password   = password,
                    first_name = partes[0],
                    last_name  = partes[1] if len(partes) > 1 else '',
                    is_staff   = True,
                )
                login(request, user)
                return redirect('pos:venta')

        # ── Login normal ─────────────────────────────────────────
        else:
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '').strip()
            user     = authenticate(request, username=username, password=password)

            if user is None:
                error = 'Usuario o contraseña incorrectos.'
            elif not user.is_active:
                error = 'Esta cuenta está desactivada.'
            else:
                login(request, user)
                next_url = request.GET.get('next', '')
                return redirect(next_url if next_url else 'pos:venta')

    return render(request, 'auth/login.html', {
        'empresa':     empresa,
        'sin_usuarios': sin_usuarios,
        'error':       error,
    })


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')
