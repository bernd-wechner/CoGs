'''
Django Generic View Extensions

Context Updaters

Functions that add to the context that templates see.
'''
# Django imports
from django.utils.safestring import mark_safe
from django.conf import settings 
from django.utils.timezone import get_current_timezone
from django.views.generic import base
from django.http.request import HttpRequest

# Python imports
import pytz
import sqlparse
from datetime import datetime
#import json

# Package imports
from .util import safetitle
from .datetime import datetime_format_python_to_PHP
from .model import add_related
from .forms import get_related_forms, classify_widgets #, get_inherit_fields
from .options import urldefaults, odf, odm
from .widgets import FilterWidget, OrderingWidget
from .filterset import format_filterset


def add_model_context(view, context, plural, title=False):
    '''
    Add some useful context information to views that reveal information about the model

    Specifically, access to the model, and related forms 
    (forms for models that relate to this one).
    '''
    
    if not isinstance(view, base.View):
        raise ValueError("Internal Error: add_model_context requested with invalid view")
    
    context.update(view.kwargs)
    if 'model' in context and hasattr(view, 'operation'):
        context["model"] = context["view"].model
        context["model_name"] = context["view"].kwargs['model']
        context["model_name_plural"] = context["view"].model._meta.verbose_name_plural
        context["operation"] = view.operation
        context["title"] = (title + ' ' if title else '') + (safetitle(context["model"]._meta.verbose_name_plural) if plural else safetitle(context["model"]._meta.verbose_name))
        context["default_datetime_input_format"] = datetime_format_python_to_PHP(settings.DATETIME_INPUT_FORMATS[0])

        if len(view.request.GET) > 0:
            context["get_params"] = view.request.GET

        if view.operation in ["add", "edit"] and 'form' in context:
            classify_widgets(context['form'])
    else:
        raise ValueError("Internal Error: Views must be provided at least 'model' in kwargs and an 'operation' argument. One or the other was missing. This is a site design error relating to defined urlpatterns which failed to provide on or the other.")

    return context

def add_format_context(view, context):
    '''
    Add some useful context information to views that reveal information about the
    display and formatting options we have for views

    Specifically a dictionary with one item per available setting and a true/false value.
    
    view is generic view object that has a format attribute. As in view.format.
    
    Two types are supported Detail and List views, with different context generate
    for each one.  
    '''
    if not isinstance(view, base.View):
        raise ValueError("Internal Error: add_model_context requested with invalid view")

    if hasattr(view, "operation") and hasattr(view, "format"):
        # List views are simple
        if view.operation == "list":
            context["format"] = view.format
            context["format_default"] = urldefaults
        
        # Detail view support a richer array of options that we handle with more care
        elif view.operation == "view":
            # Detail views will want a dictionary of object_display_format settings to honor 
            # when rendering display options if they opt do so.     
            ODF = {}
            for setting in vars(odf):
                if not setting.startswith("_"): # Skip built-ins '__' and the summary settings '_' 
                    ODF[setting] = (view.format.flags & getattr(odf, setting)) > 0
                
            context['format_flags'] = ODF
        
            # They may also want to know about the shorthand settings that object_display_format supports
            # and because these are defined in the class as _ prefixed settings we can set them and 
            # then test all the settings and build lists of settings each one sets. Thus we can inform
            # the template of this and it need not break DRY by hard coding any assumptions about the
            # object_display_format settings. 
            Shorthand = {}
            for setting in vars(odf):
                if not setting.startswith("__") and setting.startswith("_"):  
                    Shorthand[setting] = []
            
            for SH in Shorthand:
                TestODF = getattr(odf, SH)
                for setting in ODF:
                    if TestODF & getattr(odf, setting):
                        Shorthand[SH].append(setting)
            
            context['format_shorthands'] = Shorthand
        
            # format modes
            ODM = {}
            for setting in vars(odm):
                if not setting.startswith("_") and not setting.startswith("as_"): # Skip built-ins ('__'), private attributes '_' and the enums ('as_') 
                    ODM[setting] =  getattr(view.format.mode, setting)
                 
            context['format_modes'] = ODM
            
#             # enums (so that a template knows the values that the modes can take)
#             ODME = {}  # Object Display Mode Enums
#             for setting in vars(odm):
#                 if setting.startswith("as_"):  
#                     ODME[setting] =  getattr(odm, setting)
#          
#             # Not sure if these are ever useful in a template. But if so, they could be added.
#             ODSE = {}  # Object Display Summary Enums
#             for setting in vars(osf):
#                 if not setting.startswith("_") :  
#                     ODSE[setting] =  getattr(osf, setting)
#                            
#             FE = {} # Format Enums
#             FE['object'] = ODME.copy()
#             FE['list_values'] = ODME.copy()
#             FE['sum_format'] = ODSE.copy()
#                   
#             context['format_enums'] = FE     
    
    return context

def add_filter_context(view, context):
    '''
    List and Detail views accept filters via the url (see url_filter). Both these views can do AJAX 
    based refreshes and so want to know the filter criteria that came in. They could suck this out
    in Javascript of course, but for completeness let's add it to the context
    
    List view clearly, the filter determines what is listed
    Detail view, only the neighbours for browsing (prior and next) are impacted   
    '''
    if not isinstance(view, base.View):
        raise ValueError("Internal Error: add_model_context requested with invalid view")

    context['widget_filters'] = FilterWidget(model=view.model, choices=view.request.GET)
    
    # Default empty value so templates can include Javascript "var filters    = {{filters}};" without issue.
    context["filters"] = mark_safe('""')  
    
    if hasattr(view, 'filterset') and not view.filterset is None:
        context["filters"] = format_filterset(view.filterset, as_text=False)
        context["filters_text"] = mark_safe(format_filterset(view.filterset, as_text=True))
        context["filters_data"] = view.filterset.data
        
        specs = view.filterset.get_specs()
        filters_specs = {}
        for spec in specs:
            op = spec.lookup
            key = "__".join(spec.components) + "__" + op
            val = spec.value
            filters_specs[key] = val
            
        context["filters_specs"] = filters_specs        
        context["filters_query"] = sqlparse.format(str(view.filterset.filter().query), reindent=True, keyword_case='upper')        
        
    return context

def add_ordering_context(view, context):
    '''
    List and Detail views respond to ordering via the url. Both these views can do AJAX 
    based refreshes and so want to know the filter criteria that came in. They could suck 
    this out in Javascript of course, but for completeness let's add it to the context
    
    List view clearly. the order of the listed objects.
    Detail view, only the neighbours for browsing (prior and next) are impacted.  
    :param view:
    :param context:
    '''
    if not isinstance(view, base.View):
        raise ValueError("Internal Error: add_model_context requested with invalid view")

    context['widget_ordering'] = OrderingWidget(model=view.model, choices=view.request.GET.get('ordering', None))
    
    if hasattr(view, 'ordering') and not view.ordering is None:
        context["ordering"] = view.ordering
    else:   
        context["ordering"] = ""

    if hasattr(view.model._meta, 'ordering'):
        context["ordering_default"] = "ordering=" + ",".join(view.model._meta.ordering)        
    else:   
        context["ordering_default"] = ""
        
    return context

def add_timezone_context(view_request, context):
    '''
    Add some useful timezone information to the context. Timezone can be determined at login,
    is stored as a session variable and passed by views into context using this function.
    
    :param view_request: Must be either django.views.generic.base.View (or a derived class) 
                         or django.http.request.HttpRequest (or rerived class) which provides
                         a django session object. In a class based view this can be "self" and
                         in a function based view it can be the request. 
                         
    :param context:     The context dictionary to augment. It is added to (i.e. the context
                        passed in is changed/augmented, and the augmented result is returned as 
                        well. 
    '''
    
    if isinstance(view_request, base.View):
        request = view_request.request
    elif isinstance(view_request, HttpRequest):
        request = view_request
    else:
        raise ValueError("Internal Error: add_time_context requested with invalid view/request")
    
    context['timezones'] = pytz.common_timezones
    
    #naive_now = make_naive(datetime.now(get_localzone()))
    naive_now = datetime.now()

    dt = naive_now
    context['naive_datetime'] = str(dt)
    context['naive_timezone'] = None
    context['naive_utcoffset'] = None

    tz = pytz.timezone(request.session.get("timezone", "UTC"))
    dt = tz.localize(naive_now)
    context['session_datetime'] = str(dt)
    context['session_timezone'] = str(dt.tzinfo)
    context['session_utcoffset'] = dt.tzinfo._utcoffset
    
    active_tz = get_current_timezone()
    active_dt = active_tz.localize(naive_now)
    context['active_datetime'] = str(active_dt)
    context['active_timezone'] = str(active_dt.tzinfo)
    context['active_utcoffset'] = active_dt.tzinfo._utcoffset
    
    django_tz = pytz.timezone(settings.TIME_ZONE)
    django_dt = django_tz.localize(naive_now)
    context['django_datetime'] = str(django_dt)
    context['django_timezone'] = str(django_dt.tzinfo)
    context['django_utcoffset'] = django_dt.tzinfo._utcoffset
    
    return context

def add_debug_context(view_request, context):
    '''
    A hook to add debug into the context when requested by the session debug flag.
    '''
    if isinstance(view_request, base.View):
        request = view_request.request
    elif isinstance(view_request, HttpRequest):
        request = view_request
    else:
        raise ValueError("Internal Error: add_time_context requested with invalid view/request")

    context['debug_mode'] = request.session.get("debug_mode", False)
    
    return context
