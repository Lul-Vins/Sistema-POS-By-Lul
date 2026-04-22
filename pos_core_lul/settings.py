"""
Django settings para pos_core_lul.
Sistema POS local, offline, multimoneda (USD/Bs) para pequeños comercios.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-ts^crbevk_d(ys5m*)av!#z%5%73+up&85gizccl(9y(omc8b9'

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1']


# --- Apps ---

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Librerías de terceros
    'import_export',
    # Apps del proyecto
    'configuracion',
    'inventario',
    'ventas',
    'reportes',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'pos_core_lul.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'pos_core_lul.wsgi.application'


# --- Base de Datos (SQLite — portabilidad total, sin servidor) ---

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# --- Validación de contraseñas (mínima — sistema local offline) ---

AUTH_PASSWORD_VALIDATORS = []

# --- Auth ---

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'


# --- Internacionalización ---

LANGUAGE_CODE = 'es-ve'

TIME_ZONE = 'America/Caracas'

USE_I18N = True

USE_TZ = True


# --- Archivos estáticos ---

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']


# --- Archivos de media (logos, imágenes de productos) ---

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# --- Clave primaria por defecto ---

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
