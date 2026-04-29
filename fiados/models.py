from django.db import models, transaction
from django.contrib.auth.models import User
from decimal import Decimal, ROUND_HALF_UP
from configuracion.models import Moneda
from inventario.models import Producto

_D2 = Decimal('0.01')


class Cliente(models.Model):
    nombre         = models.CharField(max_length=200)
    telefono       = models.CharField(max_length=20, blank=True)
    direccion      = models.TextField(blank=True)
    notas          = models.TextField(blank=True)
    activo         = models.BooleanField(default=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Cliente'
        verbose_name_plural = 'Clientes'
        ordering            = ['nombre']

    def __str__(self):
        return self.nombre


class Fiado(models.Model):

    ESTADO = [
        ('PENDIENTE', 'Pendiente'),
        ('PARCIAL',   'Pago parcial'),
        ('PAGADO',    'Pagado'),
        ('ANULADO',   'Anulado'),
    ]

    cliente       = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='fiados')
    fecha         = models.DateTimeField(auto_now_add=True)
    total_usd     = models.DecimalField(max_digits=10, decimal_places=2)
    total_bs      = models.DecimalField(max_digits=14, decimal_places=2)
    tasa_aplicada = models.DecimalField(max_digits=12, decimal_places=2)
    estado        = models.CharField(max_length=15, choices=ESTADO, default='PENDIENTE')
    vendedor      = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='fiados_vendidos')
    notas         = models.TextField(blank=True)

    class Meta:
        verbose_name        = 'Fiado'
        verbose_name_plural = 'Fiados'
        ordering            = ['-fecha']

    def __str__(self):
        return f'Fiado #{self.pk} — {self.cliente.nombre}'

    @property
    def monto_pagado_usd(self):
        from django.db.models import Sum
        return self.pagos.aggregate(t=Sum('monto_usd'))['t'] or Decimal('0')

    @property
    def saldo_usd(self):
        return max(Decimal('0'), self.total_usd - self.monto_pagado_usd)

    @property
    def porcentaje_pagado(self):
        if not self.total_usd:
            return 100
        return min(100, int(self.monto_pagado_usd / self.total_usd * 100))

    def actualizar_estado(self):
        """Recalcula el estado en función de los pagos y lo guarda."""
        if self.estado == 'ANULADO':
            return
        pagado = self.monto_pagado_usd
        if pagado <= 0:
            nuevo = 'PENDIENTE'
        elif pagado >= self.total_usd:
            nuevo = 'PAGADO'
        else:
            nuevo = 'PARCIAL'
        self.estado = nuevo
        self.save(update_fields=['estado'])

    @classmethod
    def crear_desde_carrito(cls, carrito, cliente, vendedor=None, notas=''):
        """
        carrito: [{'producto': <Producto>, 'cantidad': int}, ...]
        Descuenta stock y registra el fiado en una transacción atómica.
        """
        with transaction.atomic():
            tasa      = Moneda.get_tasa_activa()
            total_usd = Decimal('0')
            items     = []

            for item in carrito:
                producto = Producto.objects.select_for_update().get(pk=item['producto'].pk)
                cantidad = item['cantidad']

                if producto.stock_actual < cantidad:
                    raise ValueError(
                        f'Stock insuficiente para "{producto.nombre}". '
                        f'Disponible: {producto.stock_actual}, solicitado: {cantidad}.'
                    )

                precio     = producto.precio_usd
                total_usd += precio * cantidad
                items.append((producto, cantidad, precio))

            total_usd = total_usd.quantize(_D2, rounding=ROUND_HALF_UP)
            total_bs  = (total_usd * tasa).quantize(_D2, rounding=ROUND_HALF_UP)

            fiado = cls.objects.create(
                cliente       = cliente,
                total_usd     = total_usd,
                total_bs      = total_bs,
                tasa_aplicada = tasa,
                vendedor      = vendedor,
                notas         = notas,
            )

            for producto, cantidad, precio in items:
                DetalleFiado.objects.create(
                    fiado                = fiado,
                    producto             = producto,
                    cantidad             = cantidad,
                    precio_usd_capturado = precio,
                )
                producto.stock_actual -= cantidad
                producto.save(update_fields=['stock_actual'])

            return fiado


class DetalleFiado(models.Model):
    fiado                = models.ForeignKey(Fiado, on_delete=models.CASCADE, related_name='detalles')
    producto             = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='detalles_fiado')
    cantidad             = models.DecimalField(max_digits=10, decimal_places=3)
    precio_usd_capturado = models.DecimalField(max_digits=10, decimal_places=4)

    class Meta:
        verbose_name        = 'Detalle de fiado'
        verbose_name_plural = 'Detalles de fiado'

    @property
    def precio_bs_capturado(self):
        return self.precio_usd_capturado * self.fiado.tasa_aplicada

    @property
    def subtotal_usd(self):
        return self.precio_usd_capturado * self.cantidad

    @property
    def subtotal_bs(self):
        return self.subtotal_usd * self.fiado.tasa_aplicada


class PagoFiado(models.Model):

    METODO_PAGO = [
        ('EFECTIVO_USD',   'Efectivo USD'),
        ('EFECTIVO_BS',    'Efectivo Bs'),
        ('TRANSFERENCIA',  'Transferencia'),
        ('PAGO_MOVIL',     'Pago Móvil'),
        ('PUNTO_DE_VENTA', 'PdV (Tarjeta)'),
        ('BIOPAGO',        'Biopago'),
    ]

    fiado          = models.ForeignKey(Fiado, on_delete=models.CASCADE, related_name='pagos')
    fecha          = models.DateTimeField(auto_now_add=True)
    monto_usd      = models.DecimalField(max_digits=10, decimal_places=2)
    monto_bs       = models.DecimalField(max_digits=14, decimal_places=2)
    tasa_aplicada  = models.DecimalField(max_digits=12, decimal_places=2)
    metodo_pago    = models.CharField(max_length=20, choices=METODO_PAGO)
    notas          = models.TextField(blank=True)
    registrado_por = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='pagos_fiado')

    class Meta:
        verbose_name        = 'Abono'
        verbose_name_plural = 'Abonos'
        ordering            = ['-fecha']

    def __str__(self):
        return f'Abono ${self.monto_usd} — {self.fiado.cliente.nombre}'
