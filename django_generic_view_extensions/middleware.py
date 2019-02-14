'''
Django Generic View Extensions

Middleware classes
'''

# Django imports
from django.utils import timezone
from django.conf import settings

class TimezoneMiddleware(object):
    '''
    A Middleware which activates the session stores timezone if available else the settings
    configured timezeone.
    
    Make to to include it after 'django.contrib.auth.middleware.AuthenticationMiddleware'
    inthe MIDDLEWARE setting as it needs request.user to be available.
    '''
    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        if "django_timezone" in request.session:
            timezone.activate(request.session.get('django_timezone', settings.TIME_ZONE))
        else:        
            timezone.activate(settings.TIME_ZONE) 
            
        return self.get_response(request)