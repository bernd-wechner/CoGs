"""
WSGI config for CoGs project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/howto/deployment/wsgi/
"""

import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Site.settings")

from django_lighttpd_middleware import METHOD

if METHOD == "middleware":
    from django.core.wsgi import get_wsgi_application
    application = get_wsgi_application()
elif  METHOD == "wsgi":
    from django_lighttpd_middleware import get_wsgi_application
    application = get_wsgi_application()
else:
    raise NotImplementedError("No WSGI application defined.")

