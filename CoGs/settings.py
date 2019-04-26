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
from tzlocal import get_localzone
from django.conf import global_settings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'b21tutq1vl(af-d*uv85n6c$cfz!@rlhhi30wygqg=qb1+ofaj'

# This is where manage.py collectstatic will place all the static files
STATIC_ROOT = os.path.join(BASE_DIR, "static/")

# And this is the URL where static files will be expected by django pages
STATIC_URL = "/static/"
    
# The name of the webserver this is running on (used to select deployment settings)
WEBSERVER = "Arachne".lower()

# The Site ID for the django.contrib.sites app, 
# which just a prerequisite for the django.contrib.flatpages app
# which is used for serving the about page (and any other flat pages).
SITE_ID = 1

import platform
HOSTNAME = platform.node().lower()

LIVE_SITE = HOSTNAME == WEBSERVER

ALLOWED_HOSTS = ["127.0.0.1", "arachne.lan", "leaderboard.space", "arachne-nova.lan"]

if LIVE_SITE:
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
    INTERNAL_IPS = ['127.0.0.1', '192.168.0.11']
    import sys
    print("USING PATH: {}".format(sys.path))
    

# Application definition

INSTALLED_APPS = (
    'dal',
    'dal_select2',
    'cuser',
    'timezone_field',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.flatpages',
    'django_extensions',
    'reset_migrations',
    'Leaderboards',
)

MIDDLEWARE = (
    'django_stats_middleware.StatsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django_generic_view_extensions.middleware.TimezoneMiddleware',
    'cuser.middleware.CuserMiddleware',
)

if LIVE_SITE:
    WSGI_APPLICATION = 'CoGs.wsgi.application'
    from django_lighttpd_middleware import METHOD
    if METHOD == "middleware":
        MIDDLEWARE = ('django_lighttpd_middleware.LighttpdMiddleware',) + MIDDLEWARE
# enable the debug toolbar when needed (it slows things down enormously)
# else:
#     INSTALLED_APPS = INSTALLED_APPS + ('debug_toolbar', ) 
#     MIDDLEWARE = MIDDLEWARE + ('debug_toolbar.middleware.DebugToolbarMiddleware',)    

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

ATOMIC_REQUESTS = True

# Internationalization
# https://docs.djangoproject.com/en/1.8/topics/i18n/

LANGUAGE_CODE = 'en-us'

USE_I18N = False

USE_L10N = False

USE_TZ = True

# For some bizarre reason Django has a default TIME_ZONE of America/Chicago
# Also Python makes it very hard to get the system timezone it seems
# The tzlocal package was written by smeone to fix that glaring hole!
# This then is the timezone the webserver thinks it's in!
#
# TIME_ZONE of course should be the time zone the primary audience is in,
# as it's what we'll use before a user logs in and submits their local timezone
# via the login form.
TIME_ZONE = str(get_localzone()) 

DATETIME_FORMAT = 'D, j M Y H:i'

DATETIME_INPUT_FORMATS = ['%Y-%m-%d %H:%M:%S%z'] + global_settings.DATETIME_INPUT_FORMATS 

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.8/howto/static-files/

STATIC_URL = '/static/'

LOGIN_URL = '/login/'

# The default page to redirect to on login. Generally we return you to the page you
# were on when you tried to log in, using the next= URL parameter. This the fallback 
# if one isn't present.
LOGIN_REDIRECT_URL = '/leaderboards/'

