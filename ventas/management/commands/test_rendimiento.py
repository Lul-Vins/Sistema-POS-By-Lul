"""
Comando: python manage.py test_rendimiento
Mide el tiempo de respuesta de todas las URLs de la app usando el cliente
de pruebas de Django (sin red real). Crea datos temporales y los elimina al terminar.
"""

import time
from django.core.management.base import BaseCommand
from django.test import Client, override_settings
from django.contrib.auth.models import User
from django.db import transaction


VERDE   = '\033[92m'
AMARILLO = '\033[93m'
ROJO    = '\033[91m'
GRIS    = '\033[90m'
BOLD    = '\033[1m'
RESET   = '\033[0m'


def color_ms(ms):
    if ms < 80:
        return f'{VERDE}{ms:6.1f} ms{RESET}'
    elif ms < 250:
        return f'{AMARILLO}{ms:6.1f} ms{RESET}'
    else:
        return f'{ROJO}{ms:6.1f} ms{RESET}'


def barra(ms, escala=300):
    bloques = int(ms / escala * 30)
    bloques = min(bloques, 30)
    if ms < 80:
        c = VERDE
    elif ms < 250:
        c = AMARILLO
    else:
        c = ROJO
    return c + '#' * bloques + RESET + '.' * (30 - bloques)


class Command(BaseCommand):
    help = 'Test de rendimiento de todas las URLs de la app'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repeticiones', '-r', type=int, default=5,
            help='Número de repeticiones por URL (default: 5)'
        )
        parser.add_argument(
            '--umbral', '-u', type=float, default=300,
            help='Umbral en ms para marcar como lento (default: 300)'
        )

    def handle(self, *args, **options):
        repeticiones = options['repeticiones']
        umbral_lento = options['umbral']

        self.stdout.write(f'\n{BOLD}== TEST DE RENDIMIENTO -- POS Core =={RESET}')
        self.stdout.write(f'{GRIS}  {repeticiones} repeticiones por URL - umbral lento: {umbral_lento} ms{RESET}\n')

        # ── Crear datos temporales en una transacción que luego revertimos ──
        resultados = []

        with override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1']):
            with transaction.atomic():
                savepoint = transaction.savepoint()
                try:
                    datos = self._crear_datos_prueba()
                    client_admin  = Client()
                    client_cajero = Client()
                    client_admin.force_login(datos['admin'])
                    client_cajero.force_login(datos['cajero'])

                    urls = self._construir_urls(datos)

                    for seccion, lista in urls:
                        self.stdout.write(f'\n  {BOLD}{seccion}{RESET}')
                        self.stdout.write(f'  {"URL":<45} {"Rol":<8} {"Promedio":>10}  {"Min":>8}  {"Max":>8}  Barra')
                        self.stdout.write(f'  {"-"*105}')

                        for etiqueta, url, rol in lista:
                            cli = client_admin if rol == 'admin' else client_cajero
                            tiempos = []

                            for _ in range(repeticiones):
                                t0 = time.perf_counter()
                                resp = cli.get(url, follow=False)
                                t1 = time.perf_counter()
                                tiempos.append((t1 - t0) * 1000)

                            promedio = sum(tiempos) / len(tiempos)
                            minimo   = min(tiempos)
                            maximo   = max(tiempos)
                            status   = resp.status_code
                            status_str = f'{VERDE}{status}{RESET}' if status in (200, 302) else f'{ROJO}{status}{RESET}'

                            resultados.append({
                                'url': etiqueta,
                                'promedio': promedio,
                                'status': status,
                            })

                            self.stdout.write(
                                f'  {etiqueta:<45} {GRIS}{rol:<8}{RESET} '
                                f'{color_ms(promedio)}  '
                                f'{GRIS}{minimo:6.1f} ms{RESET}  '
                                f'{GRIS}{maximo:6.1f} ms{RESET}  '
                                f'{barra(promedio)}  [{status_str}]'
                            )

                finally:
                    transaction.savepoint_rollback(savepoint)

        # ── Resumen ───────────────────────────────────────────────────────
        self.stdout.write(f'\n{BOLD}== RESUMEN =={RESET}')

        ok      = [r for r in resultados if r['status'] in (200, 302)]
        lentos  = [r for r in ok if r['promedio'] >= umbral_lento]
        rapidos = [r for r in ok if r['promedio'] < 80]
        errores = [r for r in resultados if r['status'] not in (200, 302)]

        if resultados:
            prom_total = sum(r['promedio'] for r in ok) / len(ok) if ok else 0
            self.stdout.write(f'  URLs probadas  : {len(resultados)}')
            self.stdout.write(f'  Promedio global: {color_ms(prom_total)}')
            self.stdout.write(f'  {VERDE}Rapidas (<80ms){RESET}  : {len(rapidos)}')
            self.stdout.write(f'  {ROJO}Lentas (>={umbral_lento}ms){RESET}: {len(lentos)}')
            if errores:
                self.stdout.write(f'  {ROJO}Errores HTTP{RESET}   : {len(errores)}')
                for e in errores:
                    self.stdout.write(f'    - {e["url"]} -> {e["status"]}')

        if lentos:
            self.stdout.write(f'\n  {BOLD}URLs mas lentas:{RESET}')
            for r in sorted(lentos, key=lambda x: x['promedio'], reverse=True):
                self.stdout.write(f'    - {r["url"]:<45} {color_ms(r["promedio"])}')

        self.stdout.write('')

    # ────────────────────────────────────────────────────────────────────
    def _crear_datos_prueba(self):
        from configuracion.models import Empresa, Moneda
        from inventario.models import Producto, Categoria
        from ventas.models import Venta, DetalleVenta
        from fiados.models import Cliente, Fiado, DetalleFiado

        admin = User.objects.create_user(
            username='_perf_admin', password='test', is_staff=True, is_superuser=True,
            first_name='Perf', last_name='Admin',
        )
        cajero = User.objects.create_user(
            username='_perf_cajero', password='test', is_staff=False,
        )

        # Empresa y moneda si no existen
        if not Empresa.objects.exists():
            Empresa.objects.create(nombre='Test SA', rif='J000000000')
        moneda = Moneda.objects.first()
        if not moneda:
            moneda = Moneda.objects.create(simbolo='Bs', tasa_cambio=36)

        cat = Categoria.objects.create(nombre='_PerfCat')
        prod = Producto.objects.create(
            nombre='_PerfProducto', precio_usd='5.00',
            stock_actual=100, stock_minimo=5, categoria=cat,
        )

        # Venta para ticket
        venta = Venta.objects.create(
            vendedor=cajero, total_usd='5.00', total_bs='180.00',
            tasa_aplicada=36, metodo_pago='EFECTIVO_BS',
        )
        DetalleVenta.objects.create(
            venta=venta, producto=prod, cantidad=1,
            precio_usd_capturado='5.00',
        )

        # Cliente y fiado para fiados
        cliente = Cliente.objects.create(nombre='_PerfCliente')
        fiado = Fiado.objects.create(
            cliente=cliente, total_usd='5.00', total_bs='180.00',
            tasa_aplicada=36, vendedor=admin,
        )
        DetalleFiado.objects.create(
            fiado=fiado, producto=prod, cantidad=1,
            precio_usd_capturado='5.00',
        )

        return {
            'admin':   admin,
            'cajero':  cajero,
            'venta_pk': venta.pk,
            'cliente_pk': cliente.pk,
        }

    def _construir_urls(self, d):
        vp  = d['venta_pk']
        cp  = d['cliente_pk']

        return [
            ('VENTAS', [
                ('/ (punto de venta)',            '/',                     'admin'),
                ('/buscar/?q=perf',               '/buscar/?q=perf',       'cajero'),
                ('/mis-ventas/',                  '/mis-ventas/',          'cajero'),
                (f'/ticket/{vp}/',                f'/ticket/{vp}/',        'cajero'),
                ('/tasa-estado/',                 '/tasa-estado/',         'cajero'),
            ]),
            ('INVENTARIO', [
                ('/inventario/',                  '/inventario/',          'admin'),
                ('/inventario/categorias/',       '/inventario/categorias/', 'admin'),
            ]),
            ('REPORTES', [
                ('/reportes/',                    '/reportes/',            'admin'),
                ('/reportes/cierre/',             '/reportes/cierre/',     'admin'),
                ('/reportes/cierre/cajero/',      '/reportes/cierre/cajero/', 'cajero'),
            ]),
            ('CONFIGURACIÓN', [
                ('/configuracion/',               '/configuracion/',       'admin'),
                ('/configuracion/usuarios/',      '/configuracion/usuarios/', 'admin'),
                ('/configuracion/impresora/listar/', '/configuracion/impresora/listar/', 'admin'),
            ]),
            ('FIADOS', [
                ('/fiados/',                      '/fiados/',              'admin'),
                (f'/fiados/cliente/{cp}/',        f'/fiados/cliente/{cp}/', 'admin'),
            ]),
        ]
