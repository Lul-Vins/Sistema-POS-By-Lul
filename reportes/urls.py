from django.urls import path
from . import views

app_name = 'reportes'

urlpatterns = [
    path('', views.index, name='index'),
    path('anular/<int:pk>/', views.anular_venta, name='anular_venta'),
    path('cierre/', views.cierre_caja, name='cierre_caja'),
    path('guardar-cierre/', views.guardar_cierre, name='guardar_cierre'),
    path('cierre/imprimir/', views.imprimir_cierre, name='imprimir_cierre'),
    path('cierre/cajero/', views.cierre_cajero, name='cierre_cajero'),
]
