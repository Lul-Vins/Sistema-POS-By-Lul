from django.urls import path
from . import views

app_name = 'pos'

urlpatterns = [
    path('', views.venta, name='venta'),
    path('buscar/', views.buscar_productos, name='buscar_productos'),
    path('procesar/', views.procesar_venta, name='procesar_venta'),
]
