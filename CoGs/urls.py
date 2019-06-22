"""CoGs URL Configuration"""
from django.urls import path, include
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.contrib.flatpages import views as flat_views

# from django.contrib.staticfiles.storage import staticfiles_storage
# from django.views.generic.base import RedirectView
# from functools import reduce

from django_generic_view_extensions.views import ajax_Autocomplete, ajax_Selector

from Leaderboards import views

# A note on flatpages:
#    These are loaded from the database table django_flatpage (model "Flat pages" in the admin interface
#    They are not loaded from disk files. To wit the about.html file is just a source that has to be 
#    manually copied into that table for now. Be nice to write a loader.

urlpatterns = [
    path(r'', views.view_Home.as_view(), name='home'),
    path(r'about/', flat_views.flatpage, {'url': '/about/'}, name='about'),
    path(r'admin/', admin.site.urls, name='admin'),

    path(r'login/', views.view_Login.as_view(), name='login'),
    path(r'logout/', auth_views.LogoutView.as_view(), name='logout'),    
    
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
     
    path('list/<model>', views.view_List.as_view(), name='list'),
    
    path('view/<model>/<pk>', views.view_Detail.as_view(), name='view'),
    path('add/<model>', views.view_Add.as_view(), name='add'),
    path('edit/<model>/<pk>', views.view_Edit.as_view(), name='edit'),
    path('delete/<model>/<pk>', views.view_Delete.as_view(), name='delete'),
    
    # A special view for database object inspectors where implemented
    path('inspect/<model>/<pk>', views.view_Inspect, name='inspect'),
   
    # CoGs custom views
    path('leaderboards/', views.view_Leaderboards, name='leaderboards'),
    
    # AJAX support (simple URLs for returning information to a webpage via a Javascript fetch)
    # Specific URLS first
    path('json/leaderboards/', views.ajax_Leaderboards, name='json_leaderboards'),
    path('json/game/<pk>', views.ajax_Game_Properties, name='get_game_props'),
    
    # General patterns next
    path('json/<model>', views.ajax_List, name='get_list_html'),
    path('json/<model>/<pk>', views.ajax_Detail, name='get_detail_html'),

    path('post/clientinfo', views.receive_ClientInfo, name='post_client_info'),
    path('post/filter', views.receive_Filter, name='post_filter'),
    path('post/debugmode', views.receive_DebugMode, name='post_debugmode'),

    # An AJAX provider for the django-autocomplete-light widgets. 
    # As we're using a generic view, we need to provide the app name with the model explicitly
    # Views above that come from the Leaderboards app don't need that.
    path('autocomplete/<model>/<field_name>', ajax_Autocomplete.as_view(), {'app': 'Leaderboards'}, name='autocomplete'),
    path('autocomplete/<model>/<field_name>/all', ajax_Autocomplete.as_view(), {'app': 'Leaderboards', 'all': True}, name='autocomplete_all'),
    path('autocomplete/<model>/<field_name>/<field_operation>', ajax_Autocomplete.as_view(), {'app': 'Leaderboards'}, name='autocomplete_flexible'),

    # An AJAX view that is used to return the value of a select option given an id/pk
    # If we create a formset dynamically from supplied IDs the select widget wants to
    # have text to display for that ID too. This isuse exists with django-autocomplete-light
    # widgets becuase they are initially empty until the autocomplete URL above is called to 
    # populate a drop down. It doesn't exist using normal Django select widgets because they
    # are initialised with ALL the options a model offers (not scaleable alas).
    #
    # This URL returns the string for a given PK in a model that a selector should show.
    path('selector/<model>/<pk>', ajax_Selector, {'app': 'Leaderboards'}, name='get_selector'),
    
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Provisional URL (remove in production, a duke nukem way of deleting records)
if not settings.LIVE_SITE:
    import debug_toolbar
    
    urlpatterns += [
        # Some temporary internal URLS for now ...
        path('fix', views.view_Fix, name='fix'),
        path('unwind', views.view_UnwindToday, name='unwind'),
        path('check', views.view_CheckIntegrity, name='check'),
        path('rebuild', views.view_RebuildRatings, name='rebuild'),
        
        path(r'kill/<model>/<pk>', views.view_Kill, name='kill'),
        path('__debug__/', include(debug_toolbar.urls)),
    ]

