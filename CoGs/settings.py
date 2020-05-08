"""
Django settings for CoGs project.
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os

from tzlocal import get_localzone
from django.conf import global_settings 

# A custom CoGs setting that enables or disables use of the leaderboard cache.
# It's great for performance, but gets in the way of performance tests on uncached
# responses.
USE_LEADERBOARD_CACHE = True

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'b21tutq1vl(af-d*uv85n6c$cfz!@rlhhi30wygqg=qb1+ofaj'

# This is where manage.py collectstatic will place all the static files
STATIC_ROOT = os.path.join(BASE_DIR, "static/")

# And this is the URL where static files will be expected by django pages
STATIC_URL = "/static/"
    
# The name of the webserver this is running on (used to select deployment settings)
WEBSERVERS = ["Arachne".lower(), "Shelob".lower()]

# The Site ID for the django.contrib.sites app, 
# which just a prerequisite for the django.contrib.flatpages app
# which is used for serving the about page (and any other flat pages).
SITE_ID = 1

import platform
HOSTNAME = platform.node().lower()

LIVE_SITE = HOSTNAME in WEBSERVERS

ALLOWED_HOSTS = ["127.0.0.1", "arachne.lan", "shelob.lan", "leaderboard.space"]

if LIVE_SITE:
    print("Django settings: Web Server")
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'
else:
    INTERNAL_IPS = ['127.0.0.1', '192.168.0.11']
    from CoGs.settings_development import * 
    import django # So we have access to the version for reporting
    import sys    # So we have access to python path (that it searches for imports)
    import psutil # So we can access process details
    
    def pinfo():
        pid = os.getpid()
        ppid = os.getppid()
        P = psutil.Process(pid)
        PP = psutil.Process(ppid)
        return {'Me':        f'pid={pid}, name={P.name()}, commandline={P.cmdline()}, started={P.create_time()}', 
                'My Parent': f'pid={ppid}, name={PP.name()}, commandline={PP.cmdline()}, started={PP.create_time()}'}
     
    print("Django settings: Development Server")
    print(f"Django version: {django.__version__}")
    print(f"Django loaded from: {django.__file__}")
    print(f"Using Path: {sys.path}")
    print(f"Process Info: {pinfo()}")
    
#     print(f'DEBUG: current trace function in {os.getpid()}', sys.gettrace())
#     #if not sys.gettrace():
#     def trace_func(frame, event, arg):
#         with open(f"pydev-trace-{os.getpid()}.txt", 'a') as f:
#             print('Context: ', frame.f_code.co_name, '\tFile:', frame.f_code.co_filename, '\tLine:', frame.f_lineno, '\tEvent:', event, file=f)
#         return trace_func
#       
#     sys.settrace(trace_func)
#     print(f'DEBUG: current trace function in {os.getpid()}', sys.gettrace())

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
SESSION_SERIALIZER =  'django.contrib.sessions.serializers.PickleSerializer'

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.8/howto/static-files/

STATIC_URL = '/static/'

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

if LIVE_SITE:
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

# Pass our logger to Django Generic View Extensions
from .logging import log 
import django_generic_view_extensions
django_generic_view_extensions.log = log
