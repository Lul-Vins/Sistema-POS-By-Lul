from django.urls import path
from . import views

app_name = 'fiados'

urlpatterns = [
    path('',                              views.index,            name='index'),
    path('cliente/<int:pk>/',             views.cliente_detail,   name='cliente'),
    path('cliente/crear/',                views.crear_cliente,    name='crear_cliente'),
    path('cliente/<int:pk>/editar/',      views.editar_cliente,   name='editar_cliente'),
    path('cliente/<int:cliente_pk>/venta/', views.nueva_venta_fiada, name='nueva_venta'),
    path('pago/<int:fiado_pk>/',          views.registrar_pago,   name='registrar_pago'),
    path('anular/<int:pk>/',              views.anular_fiado,     name='anular'),
]
