'''
Django Generic View Extensions

The Views themselves

Provides:

    ListViewExtended
    DetailViewExtended
    DeleteViewExtended
    CreateViewExtended
    UpdateViewExtended
    
which all derive from the class of the same name less Extended (i.e. the standard Djago Generic Views).

These Extensions aim at providing primarily two things:

1) Support for rich objects (objects which make sense only as a collection of model instances).
2) Generic detail and list in the same ilk as Djangos Generic Form view, providing easy HTML for rapid easy generic rendering.

In the process it also supports Field Privacy and Admin fields though these were spun out as independent packages.  
'''
#Python imports
import datetime

# Django imports
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.views import LoginView

from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.db import connection, transaction
from django.db.models.query import QuerySet
from django.db.utils import IntegrityError
from django.http.response import JsonResponse, HttpResponse, HttpResponseRedirect    
from django.http.request import QueryDict
from django.forms.models import fields_for_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError

# 3rd Party package imports (dependencies)
from url_filter.filtersets import ModelFilterSet
from cuser.middleware import CuserMiddleware

# Package imports
from .util import app_from_object, class_from_string
from .html import list_html_output, object_html_output, object_as_html, object_as_table, object_as_ul, object_as_p, object_as_br
from .context import add_model_context, add_timezone_context, add_format_context, add_filter_context, add_ordering_context, add_debug_context
from .options import get_list_display_format, get_object_display_format
from .neighbours import get_neighbour_pks
from .model import collect_rich_object_fields, inherit_fields
from .debug import print_debug
from .forms import save_related_forms
from .filterset import format_filterset, is_filter_field 

def get_filterset(self):
    FilterSet = type("FilterSet", (ModelFilterSet,), { 
        'Meta': type("Meta", (object,), { 
            'model': self.model 
            })
    })
    
    qs = self.model.objects.all()
    
    qd = QueryDict('', mutable=True)
    
    # Add the GET parameter sunconditionally, a user request overrides
    if hasattr(self.request, 'GET'):
        qd.update(self.request.GET)

    # Use the session stored filter as a fall back, it is expected
    # in session["filter"] as a dictionary of (pseudo) fields and 
    # values. Thatis to say, they are  nominally fields in the model,
    # but don't need to be, as long as they are keys into 
    # session["filter_priorities"] which defines prioritised lists of 
    # fields for that key.    
    session = self.request.session
    if 'filter' in session:
        model = self.model
        
        # the filters we make a copy of as we may be modifying them 
        # based on the filter_priorities, and don't want to modify
        # the session stored filters (our mods are only used for
        # selecting the model field to filter on based on stated
        # priorities).
        filters = session["filter"].copy()
        priorities = session.get("filter_priorities", {})

        # Now if priority lists are supplied we apply them keeping only the highest
        # priority field in any priority list in the list of priorities. 
        for f in session["filter"]:
            if f in priorities:
                p = priorities[f]
                highest = len(p)    # Initial value, one greater than the largest index in the list  
                for i, field in enumerate(reversed(p)):
                    if is_filter_field(model, field):
                        highest = len(p)- i - 1
                        
                # If we found one or more fields in the priority list that are 
                # filterable we must now have the highest priority one, we replace 
                # the pseudo filter field with this field.
                if highest < len(p):
                    F = p[highest]
                    val = filters[f]
                    del filters[f]
                    filters[F] = val

        # Now the GET filters were already to qd, so we throw out any
        # session filters already in there as we provide priority to
        # user specified filters in the GET params over the session 
        # defined fall backs.
        F = filters.copy()
        for f in filters:
            if f in qd:
                del F[f]
         
        qd.update(F)
        
    # TODO: test this with GET params and session filter! 
    fs = FilterSet(data=qd, queryset=qs)  
    
    # get_specs raises an Empty exception if there are no specs, and a ValidationError if a value is illegal  
    try:
        specs = fs.get_specs()
    except:
        specs = []
    
    if len(specs) > 0:
        fs.fields = format_filterset(fs)
        fs.text = format_filterset(fs, as_text=True)
        return fs
    else:
        return None

def get_ordering(self):
    if (self.format.ordering):
        return self.format.ordering.split(',')              
    else:
        return getattr(self.model._meta, 'ordering', None)

class LoginViewExtended(LoginView):
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        add_timezone_context(self, context)
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        form.request.session['timezone'] = form.request.POST['timezone']        
        return response         

class TemplateViewExtended(TemplateView):
    '''
    An extension of the basic TemplateView for a home page on the site say (not related to any model)
    which provides some extra context if desired in a manner compatible with the other Extended Views
    '''
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        add_timezone_context(self, context)
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        return context

class ListViewExtended(ListView):
    # HTML formattters stolen straight form the Django ModelForm class basically.
    # Allowing us to present lists basically with the same flexibility as pre-formattted
    # HTML objects.  
    _html_output = list_html_output
    
    as_table = object_as_table
    as_ul = object_as_ul
    as_p = object_as_p
    as_br = object_as_br
    as_html = object_as_html # Chooses one of the first three based on request parameters

    # Fetch all the objects for this model
    def get_queryset(self, *args, **kwargs):
        self.app = app_from_object(self)
        self.model = class_from_string(self, self.kwargs['model'])

        # Communicate the request user to the models (Django doesn't make this easy, need cuser middleware)
        CuserMiddleware.set_user(self.request.user)
        
        # If the URL has GET parameters (following a ?) then self.request.GET 
        # will contain a dictionary of name: value pairs that FilterSet uses 
        # construct a new filtered queryset. 
        self.filterset = None
        self.format = get_list_display_format(self.request.GET)
        self.ordering = get_ordering(self)
        
        self.queryset = self.model.objects.all()
        if len(self.request.GET) > 0 or len(self.request.session.get("filter", {})) > 0:
            fs = get_filterset(self)
            
            # If there is a filter specified in the URL
            if not fs is None:
                self.filterset = fs
                self.queryset = fs.filter()
            
        if (self.ordering): 
            self.queryset = self.queryset.order_by(*self.ordering)
            
        self.count = len(self.queryset)
        
        return self.queryset

    # Add some model identifiers to the context (if 'model' is passed in via the URL)
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        add_model_context(self, context, plural=True)
        add_timezone_context(self, context)
        add_format_context(self, context)
        add_filter_context(self, context)
        add_ordering_context(self, context)
        add_debug_context(self, context)
        context["total"] =  self.model.objects.all().count        
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        return context


class DetailViewExtended(DetailView):
    '''
    An enhanced DetailView which provides the HTML output methods as_table, as_ul and as_p just like the ModelForm does (defined in BaseForm).
    '''
    # HTML formatters stolen straight form the Django ModelForm class
    # Allowing us to present object detail views  basically with the same flexibility 
    # as pre-formattted HTML objects.  
    _html_output = object_html_output
    
    as_table = object_as_table
    as_ul = object_as_ul
    as_p = object_as_p
    as_br = object_as_br
    as_html = object_as_html # Chooses one of the first three based on request parameters
    
    # Override properties with values passed as arguments from as_view()
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if ('operation' in kwargs):
            self.operation = kwargs['operation']

    # Add some model identifiers to the context (if 'model' is passed in via the URL)
        
    # Fetch the URL specified object, needs the URL parameters "model" and "pk"
    def get_object(self, *args, **kwargs):
        self.model = class_from_string(self, self.kwargs['model'])
        self.pk = self.kwargs['pk']
        
        # Communicate the request user to the models (Django doesn't make this easy, need cuser middleware)
        CuserMiddleware.set_user(self.request.user)

        # Get the ordering
        self.ordering = get_ordering(self)

        # Get Neighbour info for the object browser
        self.filterset = get_filterset(self)
        
        neighbours = get_neighbour_pks(self.model, self.pk, filterset=self.filterset, ordering=self.ordering)            
    
        # Support for incoming next/prior requests via a GET
        if 'next' in self.request.GET or 'prior' in self.request.GET:
            self.ref = get_object_or_404(self.model, pk=self.pk)
            
            # If requesting the next or prior object look for that      
            # FIXME: Totally fails for Ranks, the get dictionary fails when there are ties!
            #        Doesn't generalise well at all. Must find a general way to do this for
            #        arbitrary orders. Still should specify orders in models that create unique 
            #        ordering not reliant on pk break ties. 
            if neighbours:
                if 'next' in self.request.GET and not neighbours[1] is None:
                    self.pk = self.object_browser[1]
                elif 'prior' in self.request.GET and not neighbours[0] is None:
                    self.pk = self.object_browser[0]
                                    
            self.obj = get_object_or_404(self.model, pk=self.pk)
            self.kwargs["pk"] = self.pk                             
        else:
            self.obj = get_object_or_404(self.model, pk=self.pk)

        
        # Add this information to the view (so it's available in the context).
        self.object_browser = neighbours        

        
        self.format = get_object_display_format(self.request.GET)
        
        collect_rich_object_fields(self)
        
        return self.obj

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        add_model_context(self, context, plural=False)
        add_timezone_context(self, context)
        add_format_context(self, context)
        add_filter_context(self, context)
        add_ordering_context(self, context)
        add_debug_context(self, context)
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        return context  

class DeleteViewExtended(DeleteView):
    '''An enhanced DeleteView which provides the HTML output methods as_table, as_ul and as_p just like the ModelForm does.'''
    # HTML formatters stolen straight form the Django ModelForm class
    _html_output = object_html_output
    as_table = object_as_table
    as_ul = object_as_ul
    as_p = object_as_p
    as_br = object_as_br
    as_html = object_as_html # Chooses one of the first three based on request parameters

    # Override properties with values passed as arguments from as_view()
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if ('operation' in kwargs):
            self.opertion = kwargs['operation']

    # Get the actual object to update
    def get_object(self, *args, **kwargs):
        self.app = app_from_object(self)
        self.model = class_from_string(self, self.kwargs['model'])

        # Communicate the request user to the models (Django doesn't make this easy, need cuser middleware)
        CuserMiddleware.set_user(self.request.user)
        
        self.pk = self.kwargs['pk']
        self.obj = get_object_or_404(self.model, pk=self.kwargs['pk'])
        self.format = get_object_display_format(self.request.GET)
        self.success_url = reverse_lazy('list', kwargs={'model': self.kwargs['model']})
        
        collect_rich_object_fields(self)

        return self.obj

    # Add some model identifiers to the context (if 'model' is passed in via the URL)
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        add_model_context(self, context, plural=False, title='Delete')
        add_timezone_context(self, context)
        add_format_context(self, context)
        add_debug_context(self, context)
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        return context

# TODO: Ranks, Performances  etc. Fix edit forms
# 1. No Creating allowed, only created when a Session is created. Need a way in model to say "no creation"
# 2. On update, some fields are editable, others not (like the name of a team can be changed, but not its members)
#    We currently list only editable fields. We should list uneditable ones as well in the manner of a DetailView.
#
# For Teams: edit Name, list players (which is the add_related for the session form)
# For Ranks: No edits at all, all edited via Sessions
# For Performances: edit Partial Play Weighting only and display Session and Player (no edit).
#
# None of this should be super complicated because intent is to only edit these through 
# Session objects anyhow and the Team, Rank, Perfromance and related objects will not even
# be available on production menues, only for the admin for drilling down and debugging.

class CreateViewExtended(CreateView):
    '''
    A CreateView which makes the model and the related_objects it defines available 
    to the View so it can render form elements for the related_objects if desired.
    
    On a GET request get_context_data() is called to augment the context data for the form render,
    then get_initial() is called for initial values of the form fields.
    
    On a POST request post() is called to validate the submission and save it if good
    or bounce back with a rerender of the form with errors listed.
    
    Both sequences need to defined these:
        self.model
        self.fields
        
    So we do it in get_context_data() and in post() as our two entry points.
    
    Both call get_queryset() in order to obtain the model from the returned queryset, if it's not
    defined in self.model. And so we could define self.model and self.fields in one place. But it 
    is a little odd and confusing to think of get_queryset() for a CreaetView, so here we avoid 
    that convenience and confusions.
    
    NOTE: We do also includ a form_valid() override. This is important because in the standard
    Django post/form_valid pair, post does not save, form_valid does. If we defer to the Django 
    form_valid it goes and saves the form again. This doesn't create a new copy on creates as it
    happens as by that point self.instance already has a PK thanks to the save here in post() but
    it is an unnecessary repeat save all the same.
    '''

    # TODO: the form needs to use combo boxes for list select values like Players in a Session. You have to be able to type and find a player with a pattern match so to speak. The list can get very very long you see. 

    def get_context_data(self, *args, **kwargs):
        '''Augments the standard context with model and related model information so that the template in well informed - and can do Javascript wizardry based on this information'''

        # We need to set self.model here 
        self.app = app_from_object(self)
        self.model = class_from_string(self, self.kwargs['model'])
        if not hasattr(self, 'fields') or self.fields == None:
            self.fields = '__all__'

        # Communicate the request user to the models (Django doesn't make this easy, need cuser middleware)
        CuserMiddleware.set_user(self.request.user)

        # Note that the super.get_context_data initialises the form with get_initial
        context = super().get_context_data(*args, **kwargs)

        # Now add some context extensions ....
        add_model_context(self, context, plural=False, title='New')
        add_timezone_context(self, context)
        add_debug_context(self, context)
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        return context

    def get_initial(self):
        '''
        Returns a dictionary of values keyed on model field names that are used to populated the form widgets
        with initial values.
        '''
        initial = super().get_initial()
        
        try:
            # TODO: Consider geting the last object created by the logged in user instead of the last object created
            last = self.model.objects.latest()
        except ObjectDoesNotExist:
            last = None
            
        for field_name in inherit_fields(self.model):
            field_value = getattr(last, field_name)
            if (isinstance(field_value, datetime.datetime)):
                initial[field_name] = field_value + getattr(self.model, "inherit_time_delta", datetime.timedelta(0))
            else:
                initial[field_name] = field_value
        
        # Set the view property so context handlers (below) can see it
        self.initial = initial
            
        return initial 

    def post(self, request, *args, **kwargs):
        if self.request.POST.get("debug_post_data", "off") == "on":
            html = "<table>"   
            for key in sorted(self.request.POST):
                html += "<tr><td>{}:</td><td>{}</td></tr>".format(key, self.request.POST[key])
            html += "</table>"         
            return HttpResponse(html)        
        
        # The self.object atttribute MUST exist and be None in a CreateView. 
        self.model = class_from_string(self, self.kwargs['model'])
        self.object = None
        if not hasattr(self, 'fields') or self.fields == None:
            self.fields = '__all__'
        
        # Get the form
        self.form = self.get_form()     

        # Hook for pre-processing the form (before the data is saved)
        if callable(getattr(self, 'pre_processor', None)): self.pre_processor()
       
        print_debug(f"Connection vendor: {connection.vendor}")
        if connection.vendor == 'postgresql':
            print_debug(f"Is_valid? {self.form.data}")
            if self.form.is_valid():
                try:
                    print_debug(f"Open a transaction")
                    with transaction.atomic():
                        self.object = self.form.save()
                        
                        kwargs = self.kwargs
                        kwargs['pk'] = self.object.pk
                        self.success_url = reverse_lazy('view', kwargs=kwargs)
                        
                        save_related_forms(self)
                        print_debug(f"Saved the form and related forms.")
                        
                        if (hasattr(self.object, 'clean_relations') and callable(self.object.clean_relations)):
                            self.object.clean_relations()
         
                        print_debug(f"Cleaned the relations.")
                except (IntegrityError, ValidationError) as e:
                    # TODO: Report INtergityErrors too
                    # TODO: if error_dict refers to a non field this crashes, find what the criterion
                    #       in add_error is and then if it's a field tat doesn't match this criteron 
                    #       do somethings sensible. We may be able to attach errors to the formsets too!
                    for field, errors in e.error_dict.items():
                        for error in errors:
                            self.form.add_error(field, error)
                    return self.form_invalid(self.form)

                # Hook for post-processing data (after it's all saved) 
                if callable(getattr(self, 'post_processor', None)): self.post_processor()
                                          
                return self.form_valid(self.form)
            else:
                return self.form_invalid(self.form)
           
        else:
            if self.form.is_valid():
                self.object = self.form.save()
                save_related_forms(self)

                # Hook for post-processing data (after it's all saved) 
                if callable(getattr(self, 'post_processor', None)): self.post_processor()
                
                return self.form_valid(self.form)
            else:
                return self.form_invalid(self.form)
             
    def form_valid(self, form):
        """If the form is valid, redirect to the supplied URL."""
        return HttpResponseRedirect(self.get_success_url())

#     def form_invalid(self, form):
#         """
#         If the form is invalid, re-render the context data with the
#         data-filled form and errors.
#         """
#         context = self.get_context_data(form=form)        
#         response = self.render_to_response(context)
#         return response

class UpdateViewExtended(UpdateView):
    '''
    An UpdateView which makes the model and the related_objects it defines available to the View so it can render form elements for the related_objects if desired.
    
    Note: This is almost identical to the CreateViewExtended class above bar one line, where we set self.object! 
          Which is precisely how Django differentiates a Create from an Update!
          
          Aside from that though we define get_object() in place of get_initial().
          
          Unlike the CreateView on a GET request Django calls get_object() first then get_context_data().
          And on a POST request it just calls post(). So we set up self.model and self.object in 
          get_object() for GET requests and post() for POST requests. 
    '''
    
    def get_object(self, *args, **kwargs):
        '''Fetches the object to edit and augments the standard queryset by passing the model to the view so it can make model based decisions and access model attributes.'''
        self.pk = self.kwargs['pk']
        self.model = class_from_string(self, self.kwargs['model'])
        self.obj = get_object_or_404(self.model, pk=self.kwargs['pk'])
        
        if not hasattr(self, 'fields') or self.fields == None:
            self.fields = '__all__'
            
        if callable(getattr(self.obj, 'fields_for_model', None)): 
            self.fields = self.obj.fields_for_model()
        else:           
            self.fields = fields_for_model(self.model)
            
        self.success_url = reverse_lazy('view', kwargs=self.kwargs)
         
        # Communicate the request user to the models (Django doesn't make this easy, need cuser middleware)
        CuserMiddleware.set_user(self.request.user)
         
        return self.obj    

    def get_context_data(self, *args, **kwargs):
        '''Augments the standard context with model and related model information so that the template in well informed - and can do Javascript wizardry based on this information'''
        # Note that the super.get_context_data initialises the form with get_initial
        context = super().get_context_data(*args, **kwargs)

        # Now add some context extensions ....
        add_model_context(self, context, plural=False, title='New')
        add_timezone_context(self, context)
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        return context

    def post(self, request, *args, **kwargs):
        if self.request.POST.get("debug_post_data", "off") == "on":
            html = "<table>"   
            for key in sorted(self.request.POST):
                html += "<tr><td>{}:</td><td>{}</td></tr>".format(key, self.request.POST[key])
            html += "</table>"         
            return HttpResponse(html)        

        # The self.object atttribute MUST exist and be None in a CreateView. 
        self.model = class_from_string(self, self.kwargs['model'])
        self.object = self.get_object()
        if not hasattr(self, 'fields') or self.fields == None:
            self.fields = '__all__'
                
        # Get the form
        self.form = self.get_form()     

        # Hook for pre-processing the form (before the data is saved)
        if callable(getattr(self, 'pre_processor', None)): self.pre_processor()
       
        print_debug(f"Connection vendor: {connection.vendor}")
        if connection.vendor == 'postgresql':
            print_debug(f"Is_valid? {self.form.data}")
            if self.form.is_valid():
                try:
                    print_debug(f"Open a transaction")
                    with transaction.atomic():
                        print_debug("Saving form from POST request containing:")
                        for (key, val) in sorted(self.request.POST.items()):
                            print_debug(f"\t{key}: {val}")
                        
                        self.object = self.form.save()
                        print_debug(f"Saved object: {self.object._meta.object_name} {self.object.pk}.")                        
                        
                        kwargs = self.kwargs
                        kwargs['pk'] = self.object.pk
                        self.success_url = reverse_lazy('view', kwargs=kwargs)
                        
                        print_debug(f"Saving the related forms.")
                        save_related_forms(self)
                        print_debug(f"Saved the related forms.")
                        
                        if (hasattr(self.object, 'clean_relations') and callable(self.object.clean_relations)):
                            self.object.clean_relations()
         
                        print_debug(f"Cleaned the relations.")
                except (IntegrityError, ValidationError) as e:
                    # TODO: Report INtergityErrors too
                    # TODO: if error_dict refers to a non field this crashes, find what the criterion
                    #       in add_error is and then if it's a field tat doesn't match this criteron 
                    #       do somethings sensible. We may be able to attach errors to the formsets too!
                    for field, errors in e.error_dict.items():
                        for error in errors:
                            self.form.add_error(field, error)
                    return self.form_invalid(self.form)

                # Hook for post-processing data (after it's all saved) 
                if callable(getattr(self, 'post_processor', None)): self.post_processor()
                                          
                return self.form_valid(self.form)
            else:
                return self.form_invalid(self.form)
           
        else:
            if self.form.is_valid():
                self.object = self.form.save()
                save_related_forms(self)
                
                # Hook for post-processing data (after it's all saved) 
                if callable(getattr(self, 'post_processor', None)): self.post_processor()
                
                return self.form_valid(self.form)
            else:
                return self.form_invalid(self.form)
             

    def form_valid(self, form):
        """If the form is valid, redirect to the supplied URL."""
        return HttpResponseRedirect(self.get_success_url())
