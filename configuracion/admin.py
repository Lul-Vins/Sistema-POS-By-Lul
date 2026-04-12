from django.contrib import admin
from django.core.exceptions import ValidationError
from django.contrib import messages
from .models import Empresa, Moneda


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'rif', 'telefono')

    def has_add_permission(self, request):
        # Deshabilita el botón "Añadir" si ya existe un registro
        return not Empresa.objects.exists()


@admin.register(Moneda)
class MonedaAdmin(admin.ModelAdmin):
    list_display = ('simbolo', 'tasa_cambio', 'ultima_actualizacion')
    readonly_fields = ('ultima_actualizacion',)

    def has_add_permission(self, request):
        return not Moneda.objects.exists()
