"""
Django settings for CoGs project.

Generated by 'django-admin startproject' using Django 1.8.7.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.8/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'b21tutq1vl(af-d*uv85n6c$cfz!@rlhhi30wygqg=qb1+ofaj'

# TODO: Work static files out when deployed. They are working fine under runserver.
#       but the following two directives might be important for deployment.
#       https://docs.djangoproject.com/en/1.11/ref/contrib/staticfiles/
#       
# This is where manage.py collectstatic will look for static files. A tuple of dirs.
STATICFILES_DIRS = (os.path.join(BASE_DIR, "Leaderboards/static/"),)

# This is where manage.py collectstatic will place all the static files
STATIC_ROOT = os.path.join(BASE_DIR, "static/")

# And this is the URL where static files will be expected by django pages
STATIC_URL = "/static/"
    
# The name of the webserver this is running on (used to select deployment settings)
WEBSERVER = "Arachne"

# The SIte ID for the django.contrib.sites app, 
# which just a prerequisite for the django.contrib.flatpages app
# which is used for serving the about page (and any other flat pages).
SITE_ID = 1

import platform
HOSTNAME = platform.node()

ALLOWED_HOSTS = ["127.0.0.1", "arachne.lan", "leaderboard.space"]
if HOSTNAME == WEBSERVER:
    print("Django settings: Web Server")
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'
else:
    print("Django settings: Development Server")
    from CoGs.settings_development import * 

# Application definition

INSTALLED_APPS = (
    'dal',
    'dal_select2',
    'cuser',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.flatpages',
    'django_extensions',
    'Leaderboards'
)

MIDDLEWARE = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'cuser.middleware.CuserMiddleware',
)

if HOSTNAME == WEBSERVER:
    WSGI_APPLICATION = 'CoGs.wsgi.application'
    from django_lighttpd_middleware import METHOD
    if METHOD == "middleware":
        MIDDLEWARE = ('django_lighttpd_middleware.LighttpdMiddleware',) + MIDDLEWARE

ROOT_URLCONF = 'CoGs.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Database
# https://docs.djangoproject.com/en/1.8/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'CoGs',
        'USER': 'CoGs',
        'PASSWORD': 'ManyTeeth',
        'HOST': '127.0.0.1',
        'PORT': '5432',
    }
}

# Internationalization
# https://docs.djangoproject.com/en/1.8/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = False

USE_L10N = False

USE_TZ = True

DATETIME_FORMAT = 'r'

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.8/howto/static-files/

STATIC_URL = '/static/'

LOGIN_URL = '/login/'