"""CoGs URL Configuration"""
from django.conf.urls import include, url
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.contrib.flatpages import views as flat_views
# from django.contrib.staticfiles.storage import staticfiles_storage
# from django.views.generic.base import RedirectView
# from functools import reduce

from Leaderboards import views

# A note on flatpages:
#    These are loaded from the database table django_flatpage (model "Flat pages" in the admin interface
#    They are not loaded from disk files. To wit the about.html file is just a source that has to be 
#    manually copied into that table for now. Be nice to write a loader.

urlpatterns = [
    url(r'^$', views.view_Home.as_view(), name='home'),
    url(r'^about/', flat_views.flatpage, {'url': '/about/'}, name='about'),
    url(r'^admin/', admin.site.urls, name='admin'),
    url(r'^login/$', auth_views.LoginView.as_view(), name='login'),
    url('^logout/$', auth_views.LogoutView.as_view(), name='logout'),    
    
    # Some temporary internal URLS for now ...
    url(r'^fix', views.view_Fix, name='fix'),
    url(r'^unwind', views.view_UnwindToday, name='unwind'),
    url(r'^check', views.view_CheckIntegrity, name='check'),
    url(r'^rebuild', views.view_RebuildRatings, name='rebuild'),

    # Provisional URL (remove in production, a duke nukem way of deleting records)
    url(r'^kill/(?P<model>\w+)/(?P<pk>\d+)$', views.view_Kill, name='kill'),

    # CoGs Generic Views 
    # These expect to receive the following in kwargs 
    # (i.e. passed in via named pattern match in the url as in "(?P<model>\w+)") or as a named argument in as_view()
    #     operation:     which must be one of list, view, add, edit, delete
    #     model:         the name of a model to perform the operation on
    #     pk:            required only for object specific operations, namely view, edit, delete (not list or add) and is the primary key of the object to be operated on
    # any of these that is not derived from the URL can be specified in the view itself of course.
    # Notably: operation.
    #
    # Always specify a name= to the url as this is how that url is referenced in a template.
    # See: https://docs.djangoproject.com/en/1.10/topics/http/urls/#reverse-resolution-of-urls
     
    url(r'^list/(?P<model>\w+)', views.view_List.as_view(), name='list'),
    
    url(r'^view/(?P<model>\w+)/(?P<pk>\d+)$', views.view_Detail.as_view(), name='view'),
    url(r'^add/(?P<model>\w+)$', views.view_Add.as_view(), name='add'),
    url(r'^edit/(?P<model>\w+)/(?P<pk>\d+)$', views.view_Edit.as_view(), name='edit'),
    url(r'^delete/(?P<model>\w+)/(?P<pk>\d+)$', views.view_Delete.as_view(), name='delete'),
   
    # CoGs custom views
    url(r'^leaderboards', views.view_Leaderboards, name='leaderboards'),
    
    # AJAX support (simple URLs for returning information to a webpage via a Javascript fetch)
    # Specific URLS first
    url(r'^json/leaderboards', views.ajax_Leaderboards, name='json_leaderboards'),
    url(r'^json/game/(?P<pk>\d+)$', views.ajax_Game_Properties, name='get_game_props'),
    
    # General patterns next
    url(r'^json/(?P<model>\w+)$', views.ajax_List, name='get_list_html'),
    url(r'^json/(?P<model>\w+)/(?P<pk>\d+)$', views.ajax_Detail, name='get_detail_html'),
     
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
