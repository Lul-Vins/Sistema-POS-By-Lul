from django.contrib import admin
from .models import Venta, DetalleVenta


class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0
    readonly_fields = ('producto', 'cantidad', 'precio_usd_capturado', 'subtotal_usd')
    can_delete = False

    @admin.display(description='Subtotal USD')
    def subtotal_usd(self, obj):
        return f'$ {obj.subtotal_usd:.2f}'


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'total_usd', 'total_bs', 'tasa_aplicada', 'metodo_pago', 'estado')
    list_filter = ('estado', 'metodo_pago', 'fecha')
    readonly_fields = ('fecha', 'total_usd', 'total_bs', 'tasa_aplicada')
    inlines = [DetalleVentaInline]

    def has_add_permission(self, request):
        # Las ventas solo se crean desde el frontend del POS
        return False
