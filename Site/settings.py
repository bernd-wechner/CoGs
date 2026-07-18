"""
Django settings for CoGs project.
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os, sys, warnings

from django_run_context import get_run_context

from tzlocal import get_localzone
from dotenv import load_dotenv
from crequest.middleware import CrequestMiddleware

from django.conf import settings, global_settings
from django.core.exceptions import ImproperlyConfigured

# Get the run context
RUN_CONTEXT = get_run_context()

# A custom CoGs setting that enables or disables use of the leaderboard cache.
# It's great for performance, but gets in the way of performance tests on uncached
# responses.
USE_LEADERBOARD_CACHE = True
USE_SESSION_FOR_LEADERBOARD_CACHE = False

USE_BOOTSTRAP = False

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(BASE_DIR, ".env"))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')

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

# We define our own test runner because Djangos default test runner
# only scans apps for a tests folder.  
TEST_RUNNER = 'tests.runner.PostgreSQL_Runner'
TESTING = len(sys.argv) >= 2 and sys.argv[1] == 'test'

if HOSTNAME == PRODUCTION:
    SITE_TITLE = "CoGs Leaderboard Space"
    DEBUG = False
    WARNINGS = False
elif HOSTNAME == SANDBOX:
    SITE_TITLE = "CoGs Leaderboard Sandbox"
    DEBUG = True
    WARNINGS = True
else:
    SITE_TITLE = "CoGs Leaderboard Development"
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
    'mapbox_location_field',
    'markdownfield',
    'django_summernote',
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
    'django_run_context',
    'django_rich_views',
    'django_stats_middleware',
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
# Select the target based on the TESTING flag
DEFAULT_DB = 'testing' if globals().get('TESTING', False) else 'live'
def _db_config_error(is_default: bool, msg: str):
    if is_default:
        raise ImproperlyConfigured(msg)
    else:
        warnings.warn(msg, RuntimeWarning)

def _get_db_config(name_prefix: str, is_default: bool = False):
    config = {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': os.environ.get(f"{name_prefix}_HOST"),
        'PORT': os.environ.get(f"{name_prefix}_PORT"),
        'NAME': os.environ.get(f"{name_prefix}_NAME"),
        'USER': os.environ.get(f"{name_prefix}_USER"),
        'PASSWORD': os.environ.get(f"{name_prefix}_PASSWORD"),
    }

    required_keys = ['HOST', 'PORT', 'NAME', 'USER', 'PASSWORD']
    missing = [k for k in required_keys if not config[k]]

    if missing:
        _db_config_error(is_default, f"Missing or empty database settings for '{name_prefix}': {', '.join(missing)}")
    
    if config['PORT'] and not config['PORT'].isdigit():
        _db_config_error(is_default, f"Invalid PORT for {name_prefix}: {config['PORT']}")
    
    return config

DB_CONFIGS = {
    'live': _get_db_config("DB", is_default=(DEFAULT_DB == 'live')),
    'testing': _get_db_config("TEST_DB", is_default=(DEFAULT_DB == 'testing')),
}

DATABASES = {
    'default': DB_CONFIGS[DEFAULT_DB],
    'live': DB_CONFIGS['live'],
    'testing': DB_CONFIGS['testing'],
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
# The tzlocal package was written by someone to fix that glaring hole!
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
MAPBOX_KEY = os.environ.get('MAPBOX_KEY')

# Use the Pickle Serializer. It comes with a warning when using the cookie backend
# but we're using the default database backend so are safe. Basically if:
#    SESSION_ENGINE == 'django.contrib.sessions.backends.signed_cookies'
# Then this is abad idea. But we have
#    SESSION_ENGINE == 'django.contrib.sessions.backends.db'
# As that is the Django default. That is, the actual session data remains local
# never travels between server and browser or vice versa and a cookie is only
# used to ID a local database stored session.
#
# The PickleSerializer is vulnerable appparently to code injection. That is it
# can execute arbitrary Python code if manipulated to do so. But if we are keeping
# all session data local and all the data is secure, we're good.
#
# We want to use the Pickle Serializer because we want to cache some data
# in the session that includes datetimes that don't serialize with the JSON
# serializer.
#
# In Django 5.0 they deprecated the session pickle serializer. We've reimplemented
# it (stolen it) into django-rich-views.serializers for convenience. 
SESSION_SERIALIZER = 'django_rich_views.serializers.PickleSessionSerializer'
#SESSION_SERIALIZER = 'django.contrib.sessions.serializers.PickleSerializer'

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
         '%(asctime)s.%(msecs).03d  - %(relativeReference)9.4f - %(relativeLast)9.4f - %(process)d - %(thread)d - %(levelname)8s - %(filename)20s:%(lineno)4d - %(funcName)20s - %(message)s'},

         'terse': { 'format': '%(message)s'}        
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


# Add a terse logger for console logging that doesn't need all the details.
LOGGING['handlers']['console_terse'] = {'level': 'DEBUG',
                                        'class': 'logging.StreamHandler',
                                        'stream': sys.stdout,  # Optional but forces text black, without this DEBUG text is red.
                                        'formatter': 'terse'
                                        } 

LOGGING['loggers']['terse_console'] = { 'handlers': ['console_terse'], 'level': os.getenv('DJANGO_LOG_LEVEL', 'DEBUG') } 

# Pass our logger to Django Rich Views
from Site.logutils import log
from logging import DEBUG as loglevel_DEBUG
import logging.config

import django_rich_views.logs
django_rich_views.logs.logger = log

# Include local query extensions (register them with Django)
import Site.query

show_settings = "show_settings" in sys.argv

# Log some config debugs
if DEBUG or TESTING or show_settings:
    import django  # So we have access to the version for reporting
    import psutil  # So we can access process details

    # Unsure why, logging seems not enabled yet at this point, so to be be able to log we need to enable it for DEBUG
    # explicitly and load the config above explicitly. It works outside of settings.py without this, not sure why in here
    # the logger appear unconfigured at this point.
    log.setLevel(loglevel_DEBUG)
    logging.config.dictConfig(LOGGING)
    
    if show_settings:
        log = logging.getLogger("terse_console")

    # Print context only if under runserver
    if RUN_CONTEXT != "not runserver" and not show_settings: print(f"RUN_CONTEXT: {settings.RUN_CONTEXT}")

    # Print runserver context only once, (the reloader reloads this file, so don't dump it there or we see it twice) 
    if not RUN_CONTEXT in ("runserver_reloader", "not runserver") or show_settings:
        def pinfo():
            pid = os.getpid()
            ppid = os.getppid()
            P = psutil.Process(pid)
            PP = psutil.Process(ppid)
            return {'Me': f'pid={pid}, name={P.name()}, commandline={P.cmdline()}, started={P.create_time()}',
                    'My Parent': f'pid={ppid}, name={PP.name()}, commandline={PP.cmdline()}, started={PP.create_time()}'}
        
        log.debug("=======================================================================================")
        log.debug(f"SETTINGS LOADED (in context '{RUN_CONTEXT}' on host: '{HOSTNAME}'):")
        log.debug(f"Django Settings: {'Live' if SITE_IS_LIVE else 'Development'} Server")
        log.debug(f"Django Version: {django.__version__}")
        log.debug(f"Python Version: {sys.version}")

        python_executable_path = sys.executable
        log.debug(f"Python Path: {python_executable_path}")

        # From Python 3.3 onwards:
        #
        # sys.base_prefix
        #
        #     Set during Python startup, before site.py is run, to the same value as prefix. 
        #     If not running in a virtual environment, the values will stay the same; 
        #     if site.py finds that a virtual environment is in use, the values of prefix and exec_prefix 
        #     will be changed to point to the virtual environment, whereas base_prefix and base_exec_prefix 
        #     will remain pointing to the base Python installation (the one which the virtual environment 
        #     was created from).
        #
        # sys.prefix
        #
        #    A string giving the site-specific directory prefix where the platform independent Python files are installed.
        #    On POSIX systems, the default is /usr/local.
        #    Note:
        #        If a virtual environment is in effect, this value will be changed in site.py to point to the virtual environment. 
        #        The value for the Python installation will still be available, via base_prefix.
        #
        # So any difference between them demonstrates a venv is in use. 
        if getattr(sys, 'base_prefix', '') != getattr(sys, 'prefix', ''):
            log.debug(f"Python Venv: {sys.prefix}")
        else:
            log.debug("Python Venv: Not set")

        log.debug(f"Django loaded from: {django.__file__}")
        log.debug(f"Using Path: {sys.path}")
        log.debug(f"Process Info: {pinfo()}")
        log.debug(f"Static root: {STATIC_ROOT}")
        log.debug(f"Static file dirs: {locals().get('STATICFILES_DIRS', globals().get('STATICFILES_DIRS', []))}")
        log.debug(f"Installed apps: {INSTALLED_APPS}")
        log.debug(f"Database: {DATABASES['default']}")
        log.debug(f"Testing: {TESTING}")
        log.debug(f"Debug: {DEBUG}")
        log.debug(f"Run Context: {settings.RUN_CONTEXT}")
        log.debug(f"Command Line: {sys.argv}")
        log.debug(f"Current Directory: {os.path.abspath('.')}")
        log.debug(f"Time Zone: {TIME_ZONE}")


        # print(f'DEBUG: current trace function in {os.getpid()}', sys.gettrace())
        # #if not sys.gettrace():
        # def trace_func(frame, event, arg):
        #     with open(f"pydev-trace-{os.getpid()}.txt", 'a') as f:
        #         print('Context: ', frame.f_code.co_name, '\tFile:', frame.f_code.co_filename, '\tLine:', frame.f_lineno, '\tEvent:', event, file=f)
        #     return trace_func
        #
        # sys.settrace(trace_func)
        # print(f'DEBUG: current trace function in {os.getpid()}', sys.gettrace())
        
        log.debug("=======================================================================================")
        
