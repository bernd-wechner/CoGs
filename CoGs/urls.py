"""CoGs URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.8/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Add an import:  from blog import urls as blog_urls
    2. Add a URL to urlpatterns:  url(r'^blog/', include(blog_urls))
"""
from django.conf.urls import include, url
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.storage import staticfiles_storage
from django.views.generic.base import RedirectView
from functools import reduce

from Leaderboards import views
from django_generic_view_extensions import odf

urlpatterns = [
    # Examples:
    # url(r'^$', 'DjangoTest.views.home', name='home'),     name is used for reverse Url resolution as in <a href="{% url 'home' %}">
    # url(r'^blog/', include('blog.urls')),
    # url(r'^favicon.ico$', RedirectView.as_view(url=staticfiles_storage.url('favicon.ico'), permanent=False), name="favicon" ),

    url(r'^$', views.index, name='index'),
    url(r'^admin/', include(admin.site.urls), name='admin'),
    
    # Some temporary internal URLS for now ...
    url(r'^fix', views.view_Fix, name='fix'),
    url(r'^check', views.view_CheckIntegrity, name='check'),
    url(r'^rebuild', views.view_RebuildRatings, name='rebuild'),

    # CoGs Generic Views 
    # These expect to receive the following in kwargs 
    # (i.e. passed in via named pattern match in the url as in "(?P<model>\w+)") or as a named argument in as_view()
    #     operation:     which must be one of list, view, add, edit, delete
    #     model:         the name of a model to perform the operation on
    #     pk:            required only for object specific operations, namely view, edit, delete (not list or add) and is the primary key of the object to be operated on
    # any of these that is not derived from the URL can be sepecified in the view itself of course.
    # Notably: operation.
    #
    # Always specify a name= to the url as this is how that url is referenced in a template.
    # See: https://docs.djangoproject.com/en/1.10/topics/http/urls/#reverse-resolution-of-urls
     
    url(r'^list/(?P<model>\w+)', views.view_List.as_view(), name='list'),
    
    url(r'^view/(?P<model>\w+)/(?P<pk>\d+)$', views.view_Detail.as_view(ToManyMode="<br>", format=odf.all|odf.separated|odf.header), name='view'),
    url(r'^add/(?P<model>\w+)$', views.view_Add.as_view(), name='add'),
    url(r'^edit/(?P<model>\w+)/(?P<pk>\d+)$', views.view_Edit.as_view(), name='edit'),
    url(r'^delete/(?P<model>\w+)/(?P<pk>\d+)$', views.view_Delete.as_view(ToManyMode="<br>", format=odf.all|odf.separated|odf.header), name='delete'),
   
    # CoGs custom views
    url(r'^leaderboards$', views.view_Leaderboards, name='leaderboards'),
    
    # AJAX support (simple URLs for returning information to a webpage via a Javascript fetch)
    url(r'^game/(?P<pk>\d+)$', views.ajax_Game_Properties, name='get_game_props'),
     
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Static file server for Development ONLY
# See https://docs.djangoproject.com/en/1.8/howto/static-files/
