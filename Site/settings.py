"""
Django settings for CoGs project.
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os
import sys

from tzlocal import get_localzone
from crequest.middleware import CrequestMiddleware
from django.conf import global_settings

# A custom CoGs setting that enables or disables use of the leaderboard cache.
# It's great for performance, but gets in the way of performance tests on uncached
# responses.
USE_LEADERBOARD_CACHE = True
USE_SESSION_FOR_LEADERBOARD_CACHE = False

USE_BOOTSTRAP = False

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'b21tutq1vl(af-d*uv85n6c$cfz!@rlhhi30wygqg=qb1+ofaj'

# This is where manage.py collectstatic will place all the static files
STATIC_ROOT = os.path.join(BASE_DIR, "static/")

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/
STATIC_URL = "/static/"

# This is where FileField will store files
MEDIA_ROOT = os.path.join(BASE_DIR, "media/")

# As of Django 3.2 this is needed (was the default prior, needs to be
# explicit now to avoid unwelcome warnings)
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

import platform
HOSTNAME = platform.node().lower()

# The name of the webserver this is running on (used to select deployment settings)
PRODUCTION = "shelob"
SANDBOX = "arachne"

SITE_IS_LIVE = HOSTNAME in [PRODUCTION, SANDBOX]

TESTING = len(sys.argv) >= 2 and sys.argv[1] == 'test'

if HOSTNAME == PRODUCTION:
    SITE_TITLE = "CoGs Leaderboard Space"
    database = "CoGs"
    DEBUG = False
    WARNINGS = False
elif HOSTNAME == SANDBOX:
    SITE_TITLE = "CoGs Leaderboard Sandbox"
    database = "CoGs"
    # database = "CoGs_test"
    DEBUG = True
    WARNINGS = True
else:
    SITE_TITLE = "CoGs Leaderboard Development"
    database = "CoGs"
    # database = "CoGs_test"
    DEBUG = True
    WARNINGS = not TESTING


# Make sure the SITE_TITLE is visible in context
def site_context(request):  # @UnusedVariable
    return {"SITE_TITLE": SITE_TITLE}


ALLOWED_HOSTS = ["127.0.0.1", "arachne.lan", "shelob.lan", "leaderboard.space", "sandbox.leaderboard.space"]

# The CoGs ID for the django.contrib.sites app,
# which just a prerequisite for the django.contrib.flatpages app
# which is used for serving the about page (and any other flat pages).
SITE_ID = 1

if SITE_IS_LIVE:
    print("Django settings: Web Server")
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'
else:
    INTERNAL_IPS = ['127.0.0.1', '192.168.0.11']

# Don't debug when running tests (unless --debug-mode is used to override this.
DEBUG = DEBUG and not TESTING

# Application definition
INSTALLED_APPS = (
    'dal',
    'dal_select2',
    'timezone_field',
    'markdownfield',
    'mapbox_location_field',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.flatpages',
    'django.contrib.humanize',
    # Experiments with two different bootstrap packages
    # Neither work satisfaction currently. And experimenting
    # is deferred for a broader site skinning effort.
    # 'django_bootstrap5',
    # 'crispy_forms',
    'django_extensions',
    'reset_migrations',
    'django_rich_views',
    'Site',
    'Leaderboards',
    'Import'
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
    'django_rich_views.middleware.TimezoneMiddleware',
    'crequest.middleware.CrequestMiddleware',
    'Site.logutils.LoggingMiddleware'  # Just sets the reference time for logging to be at start of the request
)

if SITE_IS_LIVE:
    WSGI_APPLICATION = 'Site.wsgi.application'
    from django_lighttpd_middleware import METHOD
    if METHOD == "middleware":
        MIDDLEWARE = ('django_lighttpd_middleware.LighttpdMiddleware',) + MIDDLEWARE
# enable the debug toolbar when needed (it slows things down enormously)
# else:
#     INSTALLED_APPS = INSTALLED_APPS + ('debug_toolbar',)
#     MIDDLEWARE = MIDDLEWARE + ('debug_toolbar.middleware.DebugToolbarMiddleware',)

ROOT_URLCONF = 'Site.urls'

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
                'Site.settings.site_context'
            ],
        },
    },
]

# Database
# https://docs.djangoproject.com/en/1.8/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': database,
        'USER': 'CoGs',
        'PASSWORD': 'ManyTeeth',
        'HOST': '127.0.0.1',
        'PORT': '5432',
    },
}

# Caching
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.PyMemcacheCache',
        'LOCATION': 'unix:/run/memcached/socket',
        'KEY_PREFIX': "Leaderboards",
        'TIMEOUT': 60 * 60 * 24 * 14  # in seconds (sec2min*min2hr*hr2day*days)
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

# In the flatpickr format:
# https://flatpickr.js.org/formatting/
DATETIME_FORMAT = 'D, j M Y H:i'

DATETIME_INPUT_FORMATS = ['%Y-%m-%d %H:%M:%S %z'] + global_settings.DATETIME_INPUT_FORMATS

# The MapBox key for mapbox_location_field
MAPBOX_KEY = "pk.eyJ1IjoidGh1bWJvbmUiLCJhIjoiY2xlcGt4eThoMGEwdTQybnFjMmhkYzZwdSJ9.8kCxKJg_MUmXlh0uEvsrTw"

# Use the Pickle Serializer. It comes with a warning when using the cookie backend
# but we're using the default database backend so are safe. Basically if:
#    SESSION_ENGINE == 'django.contrib.sessions.backends.signed_cookies'
# Then this is abad idea. But we have
#    SESSION_ENGINE == 'django.contrib.sessions.backends.db'
# As that is the Django default. That is the actual session data remains local
# never travels between server and browser or  vice versa and a cookie is only
# used to ID a local database stored session.
#
# The PickleSerializer is vulnerable appparently to code injection. That is it
# can execut arbitrary Python code if manipulated to do so. But if we are keeping
# all session dfdata local and all the data is secure, we're good.
#
# We wabtr to use the Pickle Serializer because we want to cache some data
# in the session that includes datateims that don't serialize with the JSON
# serializer.
SESSION_SERIALIZER = 'django.contrib.sessions.serializers.PickleSerializer'

# The login URL
LOGIN_URL = '/login/'

# The default page to redirect to on login. Generally we return you to the page you
# were on when you tried to log in, using the next= URL parameter. This the fallback
# if one isn't present.
LOGIN_REDIRECT_URL = '/leaderboards/'

# Configure logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters':
        { 'dev': { 'format':
        '%(prefix)s%(relativeReference)9.4f, %(relativeLast)9.4f, %(filename)20s:%(lineno)4d, %(funcName)20s - %(message)s%(postfix)s'},

         'live': { 'format':
         '%(asctime)s.%(msecs).03d  - %(relativeReference)9.4f - %(relativeLast)9.4f - %(process)d - %(thread)d - %(levelname)8s - %(filename)20s:%(lineno)4d - %(funcName)20s - %(message)s'}
        }
}

if SITE_IS_LIVE:
    # Only meaningful of logging is enabled on the Live site. Setting DEBUG to true here will enable debug logging of course.
    # In future could log requests one by one.
    LOGGING['handlers'] = { 'file': {
                                    'level': 'DEBUG',
                                    'class': 'logging.handlers.TimedRotatingFileHandler',
                                    'filename': '/data/log/CoGs/django.log',
                                    'when': 'midnight',
                                    'formatter': 'live'
                                    }
                           }

    LOGGING['loggers'] = { 'CoGs': { 'handlers': ['file'], 'level': os.getenv('DJANGO_LOG_LEVEL', 'DEBUG') } }
else:
    LOGGING['handlers'] = { 'console': {
                                    'level': 'DEBUG',
                                    'class': 'logging.StreamHandler',
                                    'stream': sys.stdout,  # Optional but forces text black, without this DEBUG text is red.
                                    'formatter': 'dev'
                                    }
                           }

    LOGGING['loggers'] = { 'CoGs': { 'handlers': ['console'], 'level': os.getenv('DJANGO_LOG_LEVEL', 'DEBUG') } }

# Pass our logger to Django Rich Views
from Site.logutils import log
from logging import DEBUG as loglevel_DEBUG
import logging.config

import django_rich_views.logs
django_rich_views.logs.logger = log

# Include local query extensions (register them with Django)
import Site.query

# Log some config debugs
if DEBUG:
    import django  # So we have access to the version for reporting
    import psutil  # So we can access process details

    def pinfo():
        pid = os.getpid()
        ppid = os.getppid()
        P = psutil.Process(pid)
        PP = psutil.Process(ppid)
        return {'Me': f'pid={pid}, name={P.name()}, commandline={P.cmdline()}, started={P.create_time()}',
                'My Parent': f'pid={ppid}, name={PP.name()}, commandline={PP.cmdline()}, started={PP.create_time()}'}

    # Unsure why, byt logging seems not enabled yet at this point, so to be be able to log we need to enable it for DEBUG
    # explicitly and load the config above explicitly. It works outside of settings.py without this, not sure why in herr
    # the logger appear unconfigured at this point.
    log.setLevel(loglevel_DEBUG)
    logging.config.dictConfig(LOGGING)

    log.debug(f"Django settings: {'Live' if SITE_IS_LIVE else 'Development'} Server")
    log.debug(f"Django version: {django.__version__}")
    log.debug(f"Python version: {sys.version}")
    log.debug(f"Django loaded from: {django.__file__}")
    log.debug(f"Using Path: {sys.path}")
    log.debug(f"Process Info: {pinfo()}")
    log.debug(f"Static root: {STATIC_ROOT}")
    log.debug(f"Static file dirs: {locals().get('STATICFILES_DIRS', globals().get('STATICFILES_DIRS', []))}")
    log.debug(f"Installed apps: {INSTALLED_APPS}")
    log.debug(f"Database: {DATABASES['default']}")
    log.debug(f"Testing: {TESTING}")
    log.debug(f"Debug: {DEBUG}")

#     print(f'DEBUG: current trace function in {os.getpid()}', sys.gettrace())
#     #if not sys.gettrace():
#     def trace_func(frame, event, arg):
#         with open(f"pydev-trace-{os.getpid()}.txt", 'a') as f:
#             print('Context: ', frame.f_code.co_name, '\tFile:', frame.f_code.co_filename, '\tLine:', frame.f_lineno, '\tEvent:', event, file=f)
#         return trace_func
#
#     sys.settrace(trace_func)
#     print(f'DEBUG: current trace function in {os.getpid()}', sys.gettrace())

