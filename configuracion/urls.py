from django.urls import path
from . import views

app_name = 'configuracion'

urlpatterns = [
    path('', views.configuracion_index, name='index'),
    path('tasa/actualizar/', views.actualizar_tasa, name='actualizar_tasa'),
    path('impresora/toggle/',    views.toggle_impresora,  name='toggle_impresora'),
    path('impresora/guardar/',   views.guardar_impresora, name='guardar_impresora'),
    path('impresora/listar/',    views.listar_impresoras, name='listar_impresoras'),
    path('impresora/test/',      views.test_impresora,    name='test_impresora'),
]
