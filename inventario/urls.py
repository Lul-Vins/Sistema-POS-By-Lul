from django.urls import path
from . import views

app_name = 'inventario'

urlpatterns = [
    path('', views.index, name='index'),
    path('guardar/', views.guardar_producto, name='guardar_producto'),
    path('eliminar/<int:pk>/', views.eliminar_producto, name='eliminar_producto'),
    path('categorias/', views.lista_categorias, name='lista_categorias'),
    path('categorias/crear/', views.crear_categoria, name='crear_categoria'),
    path('categorias/eliminar/<int:pk>/', views.eliminar_categoria, name='eliminar_categoria'),
]
