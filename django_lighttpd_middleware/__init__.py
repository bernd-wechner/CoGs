'''
Created on 11 Sep.,2017

@author: Bernd Wechner
@status: Beta - works but is rather empirically designed at present 
            (i.e. by trial and error not an intimate understanding of Django's innards)

In deploying a Django project to run under lighttpd and uWSGI, I found all the links on my menus broken.
To cut a long story short, it's because of the way the request URI is split into a script name and path info
by lighttpd which it seems is not the way Django wants it.

It seems someone found this problem in another context:
    https://searchcode.com/codesearch/view/12783344/
    
but what it boils down to centrally is environment variables called SCRIPT_NAME and PATH_INFO 
that Django wants set right. It compares PATH_INFO against the urlpatterns you've specified
and it prefixes all URLs that the url template tag generates with SCRIPT_NAME. Lighttpd doesn't
prepare these well for Django alas. 

A specific example:

http://domain.tld/list/Player

is split into these two variables by Lighttpd:

    SCRIPT_NAME: /list
    PATH_INFO: /Player

and Django wants this:

    SCRIPT_NAME: 
    PATH_INFO: /list/Player

It's possible this is a WSGI issue not a Django issue per se, as there is a related fix in
lighttpd 2 (which is not released at present and I'm using 1.45):

    https://redmine.lighttpd.net/projects/lighttpd2/wiki/Howto_WSGI
    
It seems an odd sort of fix. 


Herein is my fix. I implemented two approaches:

1) the preferred approach, as a Django Middleware implementation
2) the WSGI handler patch, overrides Djangos built in WSGI handle

The latter approach fiddles with the wsgi interface, and the former uses a formal part of the Django API so to speak.

METHOD below can be used to flag to others which method to use.

To use method 1:

in settings.py as the first entry in the MIDDLEWARE tuple, add "django_lighttpd_middleware.LighttpdMiddleware"
use the DEBUG flag below and run uwsgi manually to see its stdout, and you should see the patch work and your URLs 
processed properly. 

To use method 2:

in wsgi.py replace:

    from django.core.wsgi import get_wsgi_application

with

    from django_lighttpd_middleware import get_wsgi_application

and all should be good. Use the DEBUG flag below run uwsgi manually to see its stdout and you should see the patch work.

Closing Note:

There is an interesting discusison here:

    http://uwsgi-docs.readthedocs.io/en/latest/Nginx.html#hosting-multiple-apps-in-the-same-process-aka-managing-script-name-and-path-info
    
of SCRIPT_NAME and PATH_INFO that hints at a possible uwsgi configuration that may fix this too. A third approach.     
'''

#METHOD = "wsgi" 
METHOD = "middleware"

DEBUG = False

from django.urls import set_script_prefix, get_script_prefix
class LighttpdMiddleware(object):
    '''
    A Django MIDDLEWARE class which basically fixes request.path_info after lightttpd munged it ;-)
    Tidies up relevant request.environ and request.META elements as well. 
    '''
    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        if DEBUG:
            print("Lighttpd Middleware Incoming:")
            print("\t{}: {}".format('SCRIPT_NAME', request.environ['SCRIPT_NAME']))
            print("\t{}: {}".format('PATH_INFO', request.environ['PATH_INFO']))
        
        request.path = request.environ.get('SCRIPT_NAME','') + request.environ.get('PATH_INFO','')

        if request.path == '//':
            request.path = '/'

        # By the time a WSGIRequest object is built by Django there is an unclear duplicity between
        # environ and META and for our two important values, attributes. So we try to deck all three 
        # places these are stored. One of the drawbacks of doing this in middleware clearly. Alas.         
        request.path_info = request.path
        request.script_name = ''
        request.environ['PATH_INFO'] = request.path_info
        request.environ['SCRIPT_NAME'] = ''
        request.META['PATH_INFO'] = request.path_info
        request.META['SCRIPT_NAME'] = ''

        # While I think fixing this in middleware is the appropriate thing to do it is not
        # quite as easy as fixing the wsgi interface because middle is called a little later 
        # in the cycle, in fact after the WSGIRequest object that is provided hee as request, 
        # is built, and in its construction Django squirrels away the SCRIP_NAME already in an
        # internal buffer that it later uses to build urls. Grrrr. So we have to ask it to set
        # that internal buffered value as well. 
        set_script_prefix(request.script_name)

        if DEBUG:
            print("Lighttpd Middleware Fixed:")
            print("\t{}: {} and {} and {}".format('SCRIPT_NAME', request.environ['SCRIPT_NAME'], request.script_name, get_script_prefix()))
            print("\t{}: {} and {}".format('PATH_INFO', request.environ['PATH_INFO'], request.path_info))
            
        response = self.get_response(request)

        return response

from django.core.handlers.wsgi import WSGIHandler, WSGIRequest
import django  
class LighttpdWSGIHandler(WSGIHandler):
    '''
    A replacement for the stock Django WSGIHandler which fixes the environ elements PATH_INFO and SCRIPT_NAME
    after lightttpd munged them ;-)
    '''
    def __call__(self, environ, start_response):
        if DEBUG:
            print("Lighttpd WSGI handler Incoming:")
            print("\t{}: {}".format('SCRIPT_NAME',environ['SCRIPT_NAME']))
            print("\t{}: {}".format('PATH_INFO', environ['PATH_INFO']))
         
        environ['PATH_INFO'] = environ.get('SCRIPT_NAME','') + environ.get('PATH_INFO','')
        environ['SCRIPT_NAME'] = ''
                 
        if DEBUG:
            print("Lighttpd WSGI handler Fixed:")
            print("\t{}: {}".format('SCRIPT_NAME', environ['SCRIPT_NAME']))
            print("\t{}: {}".format('PATH_INFO', environ['PATH_INFO']))
 
        response = super().__call__(environ, start_response)
         
        return response
    
def get_wsgi_application():  # @DontTrace
    '''
    A replacement for django.core.wsgi.get_wsgi_application which uses the LighttpdWSGIHandler in place of 
    django.core.handlers.wsgi.WSGIHandler.
    '''
    django.setup()
    return LighttpdWSGIHandler()
