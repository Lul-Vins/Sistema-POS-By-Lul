from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse
import json

from .models import Empresa, Moneda


# ══════════════════════════════════════════════════════════════════
# Modelos Singleton
# ══════════════════════════════════════════════════════════════════

class EmpresaSingletonTests(TestCase):

    def test_crea_primera_empresa(self):
        e = Empresa.objects.create(nombre='Mi Tienda', rif='J123')
        self.assertEqual(e.nombre, 'Mi Tienda')

    def test_segunda_empresa_lanza_error(self):
        Empresa.objects.create(nombre='Primera', rif='J001')
        with self.assertRaises(ValidationError):
            Empresa.objects.create(nombre='Segunda', rif='J002')

    def test_actualizar_empresa_existente_no_lanza_error(self):
        e = Empresa.objects.create(nombre='Tienda', rif='J001')
        e.nombre = 'Tienda Actualizada'
        e.save()  # no debe lanzar error
        self.assertEqual(Empresa.objects.count(), 1)


class MonedaSingletonTests(TestCase):

    def test_crea_primera_moneda(self):
        m = Moneda.objects.create(tasa_cambio=50)
        self.assertEqual(float(m.tasa_cambio), 50.0)

    def test_segunda_moneda_lanza_error(self):
        Moneda.objects.create(tasa_cambio=50)
        with self.assertRaises(ValidationError):
            Moneda.objects.create(tasa_cambio=60)

    def test_get_tasa_activa_retorna_valor(self):
        Moneda.objects.create(tasa_cambio=75.50)
        tasa = Moneda.get_tasa_activa()
        self.assertEqual(float(tasa), 75.50)

    def test_get_tasa_activa_sin_moneda_lanza_error(self):
        with self.assertRaises(ValueError) as ctx:
            Moneda.get_tasa_activa()
        self.assertIn('tasa de cambio', str(ctx.exception).lower())


# ══════════════════════════════════════════════════════════════════
# Vista actualizar_tasa
# ══════════════════════════════════════════════════════════════════

class ActualizarTasaTests(TestCase):

    def setUp(self):
        self.moneda = Moneda.objects.create(tasa_cambio=50)
        Empresa.objects.create(nombre='Test', rif='J001')
        self.admin = User.objects.create_user('admin_t', password='admin1234', is_staff=True)
        self.client = Client()
        self.client.login(username='admin_t', password='admin1234')
        self.url = reverse('configuracion:actualizar_tasa')

    def _post(self, tasa):
        return self.client.post(
            self.url,
            data=json.dumps({'tasa': tasa}),
            content_type='application/json',
        )

    def test_actualiza_tasa_correctamente(self):
        r = self._post(75.0)
        self.assertTrue(r.json()['ok'])
        self.moneda.refresh_from_db()
        self.assertEqual(float(self.moneda.tasa_cambio), 75.0)

    def test_tasa_cero_rechazada(self):
        r = self._post(0)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()['ok'])

    def test_tasa_negativa_rechazada(self):
        r = self._post(-10)
        self.assertEqual(r.status_code, 400)

    def test_sin_tasa_en_body_rechazado(self):
        r = self._post(None)
        self.assertEqual(r.status_code, 400)

    def test_respuesta_incluye_nueva_tasa(self):
        r    = self._post(80.0)
        data = r.json()
        self.assertIn('tasa', data)
        self.assertEqual(data['tasa'], 80.0)


# ══════════════════════════════════════════════════════════════════
# Gestión de usuarios
# ══════════════════════════════════════════════════════════════════

class CrearUsuarioTests(TestCase):

    def setUp(self):
        Empresa.objects.create(nombre='Test', rif='J001')
        Moneda.objects.create(tasa_cambio=50)
        self.admin = User.objects.create_user('admin_t', password='admin1234', is_staff=True)
        self.client = Client()
        self.client.login(username='admin_t', password='admin1234')
        self.url = reverse('configuracion:crear_usuario')

    def _post(self, data):
        return self.client.post(
            self.url,
            data=json.dumps(data),
            content_type='application/json',
        )

    def test_crea_cajero(self):
        r = self._post({'nombre': 'Juan Pérez', 'username': 'juan',
                        'password': 'abc123', 'es_admin': False})
        self.assertTrue(r.json()['ok'])
        user = User.objects.get(username='juan')
        self.assertFalse(user.is_staff)

    def test_crea_admin(self):
        r = self._post({'nombre': 'Ana Admin', 'username': 'ana',
                        'password': 'abc123', 'es_admin': True})
        self.assertTrue(r.json()['ok'])
        self.assertTrue(User.objects.get(username='ana').is_staff)

    def test_password_corta_rechazada(self):
        r = self._post({'nombre': 'X', 'username': 'x', 'password': '12', 'es_admin': False})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()['ok'])

    def test_username_duplicado_rechazado(self):
        self._post({'nombre': 'Juan', 'username': 'juan', 'password': 'abc123', 'es_admin': False})
        r = self._post({'nombre': 'Juan2', 'username': 'juan', 'password': 'abc123', 'es_admin': False})
        self.assertEqual(r.status_code, 400)

    def test_campos_vacios_rechazados(self):
        r = self._post({'nombre': '', 'username': '', 'password': '', 'es_admin': False})
        self.assertEqual(r.status_code, 400)
