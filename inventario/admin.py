from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from .models import Categoria, Producto


class ProductoResource(resources.ModelResource):
    class Meta:
        model = Producto
        fields = ('id', 'categoria__nombre', 'nombre', 'codigo_barras', 'precio_usd', 'stock_actual', 'stock_minimo')
        export_order = fields


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)


@admin.register(Producto)
class ProductoAdmin(ImportExportModelAdmin):
    resource_classes = [ProductoResource]
    list_display = ('nombre', 'categoria', 'codigo_barras', 'precio_usd', 'stock_actual', 'stock_bajo', 'activo')
    list_filter = ('categoria', 'activo')
    search_fields = ('nombre', 'codigo_barras')
    list_editable = ('activo',)

    @admin.display(boolean=True, description='Stock bajo')
    def stock_bajo(self, obj):
        return obj.stock_bajo
