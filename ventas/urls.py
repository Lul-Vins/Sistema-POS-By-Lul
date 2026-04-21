from django.urls import path
from . import views

app_name = 'pos'

urlpatterns = [
    path('', views.venta, name='venta'),
    path('buscar/', views.buscar_productos, name='buscar_productos'),
    path('procesar/', views.procesar_venta, name='procesar_venta'),
    path('ticket/<int:pk>/', views.ticket, name='ticket'),
    path('mis-ventas/', views.mis_ventas, name='mis_ventas'),
    path('tasa-estado/', views.tasa_estado, name='tasa_estado'),
]
