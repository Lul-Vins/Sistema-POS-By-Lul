from django.urls import path
from . import views

app_name = 'reportes'

urlpatterns = [
    path('', views.index, name='index'),
    path('anular/<int:pk>/', views.anular_venta, name='anular_venta'),
]
