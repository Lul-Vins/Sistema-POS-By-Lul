from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import auth_views

urlpatterns = [
    path('admin/',          admin.site.urls),
    path('login/',          auth_views.login_view,  name='login'),
    path('logout/',         auth_views.logout_view, name='logout'),
    path('',                include('ventas.urls')),
    path('inventario/',     include('inventario.urls')),
    path('configuracion/',  include('configuracion.urls')),
    path('reportes/',       include('reportes.urls')),
    path('fiados/',         include('fiados.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
