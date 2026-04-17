from django.urls import path
from . import views

app_name = 'configuracion'

urlpatterns = [
    path('', views.configuracion_index, name='index'),
    path('tasa/actualizar/', views.actualizar_tasa, name='actualizar_tasa'),
]
