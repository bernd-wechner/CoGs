'''
Django Generic View Extensions

Context Updaters

Functions that add to the context that templates see.
'''
# Django imports
from django.utils.safestring import mark_safe
from django.conf.global_settings import DATETIME_INPUT_FORMATS

# Package imports
from .util import safetitle, datetime_format_python_to_PHP
from .model import add_related
from .forms import get_related_forms, classify_widgets
from .options import odf, odm
from .widgets import FilterWidget, OrderingWidget
from .filterset import format_filterset


def add_model_context(view, context, plural, title=False):
    '''
    Add some useful context information to views that reveal information about the model

    Specifically, access to the model, and related forms 
    (forms for models that relate to this one).
    '''
    context.update(view.kwargs)
    if 'model' in context and hasattr(view, 'operation'):
        context["model"] = context["view"].model
        context["model_name"] = context["view"].kwargs['model']
        context["model_name_plural"] = context["view"].model._meta.verbose_name_plural
        context["operation"] = view.operation
        context["title"] = (title + ' ' if title else '') + (safetitle(context["model"]._meta.verbose_name_plural) if plural else safetitle(context["model"]._meta.verbose_name))
        context["default_datetime_input_format"] = datetime_format_python_to_PHP(DATETIME_INPUT_FORMATS[0])
        
        if len(view.request.GET) > 0:
            context["get_params"] = view.request.GET

        # Check for related models and pass into the context either a related form or related view.
        # Only do this if the model asks us to do so via the add_related attribute.
        if view.operation in ["add", "edit"] and len(add_related(context["model"])) > 0:
            if hasattr(view.request, 'POST') and not view.request.POST is None and len(view.request.POST)>0:
                form_data = view.request.POST
            elif hasattr(view.request, 'GET') and not view.request.GET is None and len(view.request.GET)>0:
                form_data = view.request.GET
            else:
                form_data = None
            
            if hasattr(view, 'object') and isinstance(view.object, context['model']):
                db_object = view.object
            else:
                db_object = None
                  
            related_forms = get_related_forms(context["model"], form_data, db_object)
            context['related_forms'] = related_forms

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

    if hasattr(view, "operation") and hasattr(view, "format"):
        # List views are simple
        if view.operation == "list":
            context["format"] = view.format
        
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

def add_filter_context(view, context, filterset):
    '''
    List and Detail views accept filters via the url (see url_filter). Both these views can do AJAX 
    based refreshes and so want to know the filter criteria that came in. They could suck this out
    in Javascript of course, but for completeness let's add it to the context
    
    List view clearly, the filter determines what is listed
    Detail view, only the neighbours for browsing (prior and next) are impacted   
    :param view:
    :param context:
    '''
    context['widget_filters'] = FilterWidget(model=view.model, choices=view.request.GET)
    
    if hasattr(view, 'filterset') and not view.filterset is None:
        context["txt_filters"] = mark_safe(format_filterset(view.filterset, as_text=True))        
        context["filters"] = mark_safe(format_filterset(view.filterset, as_text=False))
        print(context["filters"])        

def add_ordering_context(view, context, ordering):
    '''
    List and Detail views respond to ordering via the url. Both these views can do AJAX 
    based refreshes and so want to know the filter criteria that came in. They could suck 
    this out in Javascript of course, but for completeness let's add it to the context
    
    List view clearly. the order of the listed objects.
    Detail view, only the neighbours for browsing (prior and next) are impacted.  
    :param view:
    :param context:
    '''
    
    context['widget_ordering'] = OrderingWidget(model=view.model, choices=view.request.GET.get('ordering', None))
    
    if hasattr(view, 'ordering') and not view.ordering is None:
        context["ordering"] = view.ordering        

