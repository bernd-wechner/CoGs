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
# Django imports
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.db.models.query import QuerySet
from django.http.response import JsonResponse, HttpResponseRedirect
from django.forms.models import fields_for_model

# 3rd Party package imports (dependencies)
from url_filter.filtersets import ModelFilterSet
from cuser.middleware import CuserMiddleware

# Package imports
from .util import app_from_object, class_from_string
from .html import list_html_output, object_html_output, object_as_html, object_as_table, object_as_ul, object_as_p, object_as_br
from .context import add_model_context, add_format_context, add_filter_context, add_ordering_context
from .options import get_list_display_format, get_object_display_format
from .neighbours import get_neighbour_pks
from .model import collect_rich_object_fields
from .debug import print_debug
from .forms import get_related_forms, get_rich_object_from_forms, save_related_forms


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

    def get_filterset(self):
        FilterSet = type("FilterSet", (ModelFilterSet,), { 
            'Meta': type("Meta", (object,), { 
                'model': self.model 
                })
        })
        
        fs = FilterSet(data=self.request.GET, queryset=self.model.objects.all())
        return fs
    
    def get_ordering(self):
        # TODO: Get from self.request to override thge default
        return getattr(self.model.Meta, 'ordering', None)        
        
    # Add some model identifiers to the context (if 'model' is passed in via the URL)
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        add_model_context(self, context, plural=True)
        add_format_context(self, context)
        add_filter_context(self, context, self.filterset)
        add_ordering_context(self, context, self.ordering)
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        return context

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
        self.ordering = self.get_ordering()
        if len(self.request.GET) > 0:
            fs = self.get_filterset()
            self.filterset = fs
            # self.ordering # FIXME: Default but use URL provided ordering if provided
            
            self.queryset = fs.filter()
        else:
            self.queryset = self.model.objects.all()
            
        self.count = len(self.queryset)

        self.format = get_list_display_format(self.request.GET)
        
        return self.queryset

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

    def get_filterset(self):
        # Build the filterset in use if one is specified in the request
        FilterSet = type("FilterSet", (ModelFilterSet,), { 
            'Meta': type("Meta", (object,), { 
                'model': self.model 
                })
        })

        # Create a mutable copy of the GET params to base a filter on (so we can tweak it)
        get = self.request.GET.copy()
        
        # If pk or id come in via GET, ignore them, use the pk from kwargs above as our reference
        if 'id' in get:
            del get['id']
        if 'pk' in get:
            del get['pk']
        
        fs = FilterSet(data=get, queryset=self.model.objects.all())
        
        return fs

    def get_ordering(self):
        # TODO: Get from self.request to override thge default
        return getattr(self.model.Meta, 'ordering', None)        
    
    # Add some model identifiers to the context (if 'model' is passed in via the URL)
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        if not hasattr(self, 'filterset'):        
            self.filterset = self.get_filterset()
            self.ordering = self.get_ordering()

        add_model_context(self, context, plural=False)
        add_format_context(self, context)
        add_filter_context(self, context, self.filterset)
        add_ordering_context(self, context, self.ordering)
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        return context  
    
    # Fetch the URL specified object, needs the URL parameters "model" and "pk"
    def get_object(self, *args, **kwargs):
        self.model = class_from_string(self, self.kwargs['model'])
        self.pk = self.kwargs['pk']
        
        # Communicate the request user to the models (Django doesn't make this easy, need cuser middleware)
        CuserMiddleware.set_user(self.request.user)

        # Get Neighbour info for the object browser
        self.filterset = self.get_filterset()
        self.ordering = self.get_ordering()
        neighbours = get_neighbour_pks(self.model, self.pk, filterset=self.filterset, ordering=self.ordering)            

        # Add this information to the view (so it's available in the context).
        self.object_browser = neighbours        

        # TODO: Put these into context somehow, and on detail view list them
        #       like "Item n or m" Probably next to the browse arrows, or 
        #       between them, maybe providing a browse widget in the context
        #       which has the two arrows and the counts in between.
        #       could late some time have fast arrows to how 10 forward? Or 
        #       such.
        
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
        
        self.format = get_object_display_format(self.request.GET)
        
        collect_rich_object_fields(self)
        
        return self.obj

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
        add_format_context(self, context)
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
    '''A CreateView which makes the model and the related_objects it defines available to the View so it can render form elements for the related_objects if desired.'''

    # TODO: the form needs to use combo boxes for list select values like Players in a Session. You have to be able to type and find a player with a pattern match so to speak. The list can get very very long you see. 

    def get_context_data(self, *args, **kwargs):
        '''Augments the standard context with model and related model information so that the template in well informed - and can do Javascript wizardry based on this information'''
        print_debug("Getting contex data")
        context = super().get_context_data(*args, **kwargs)
        print_debug("Adding model context")
        add_model_context(self, context, plural=False, title='New')
        print_debug("Adding extra context")
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        print_debug("Got context data")
        return context

    def get_queryset(self, *args, **kwargs):
        print_debug("Getting queryset")
        self.fields = '__all__'
        self.app = app_from_object(self)
        self.model = class_from_string(self, self.kwargs['model'])
        self.queryset = QuerySet(model=self.model)
        
        # Communicate the request user to the models (Django doesn't make this easy, need cuser middleware)
        CuserMiddleware.set_user(self.request.user)
        
        print_debug("Got queryset")
        return self.queryset

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        self.form = form
        self.object = form.instance
        
        # NOTE: At this point form.data has the submitted POST fields.
        # But form.instance seems to be a default instance of the object. form.data not applied,
        # Theory, form.full_clenan() does the mapping somehow? It calls model.clean() which sees populated attribs anyow.
        # full_clean() is initiated by form.add_error ro for.is_valid. 
        
        # FIXME: Check if these forms have instances attached that can be used for validation.
        # DONE: There is an instance but not populated yet with data from form.
        # Which is odd as form.instance is. So it seems to be in get_form() that the mapping 
        # happens?
        # related_forms = get_related_forms(self.model, self.object)
        
        # FIXME:
        # Form errors can be injected here and they appear on the rendered form
        # At this point form.instance has an instance of the model (related forms too?)
        # TODO: Work out how it get that and ask "Can I create instances of all related models?"         
        if form.is_valid() and self.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def is_valid(self):
        # TODO: Here we should run is_valid for all related forms.
        # That runs the clean on each related form.
        # Then run is_valid on the master form and its clean.
        # Nothing is saved here yet but objects may well be 
        # created. We should save them only in form_valid.
        #
        # IDEA: Is_valid triggers clean on the form, but not
        # on related forms. So we need to an explicit full_clean 
        # or clean on the related forms to get an aggregegate 
        # is_valid. 
        #
        # BUT if that's the case what objects are the cleans seeing?
        # Not saved yet?
        # EXPERIMENT, not passing in object but passing in request and follwoing through code
        validation_errors = {}

        # self.model.clean() has been called by Django before we get here
        # This calls clean() on all the related models (as defined by add_related properties)
        related_forms = get_related_forms(self.model, self.request.POST)
        
        # Now build a rich_object from the collected instances for submission to
        # rich_clean. 
        rich_object = get_rich_object_from_forms(self.object, related_forms)
        
        # Now we need to clean the relations. related_forms has objects built by
        # get_related_forms but we need to pass these somehow to self.model.clean_relations()
        # perhaps so in the model we can write the clean up code for the relations.
        # The objects lack PKs here and we have no clear structure for them yet.
        stophere = True 
        
        return True       

    def form_valid(self, form):
        # TODO: Make this atomic (and test). All related models need to be saved as a unit with integrity. 
        #       If there's a bail then don't save anything, i.e don't save partial data.
        
        # TODO: Act on submitted timezone info
        # Arrives at present as self.requst.POST["TZname"] and self.requst.POST["TZoffset"]
        TZname = self.request.POST["TZname"] if "TZname" in self.request.POST else None  
        TZoffset = self.request.POST["TZoffset"] if "TZoffset" in self.request.POST else None  
        
        # TODO: Consider if we should save the master first then related objects 
        # or the other way round or if it should be configurable or if it even matters.
        
        # Hook for pre-processing the form (before the data is saved)
        if callable(getattr(self, 'pre_processor', None)): self.pre_processor()

        # Save this form
        self.object = form.save()
        self.kwargs['pk'] = self.object.pk
        self.success_url = reverse_lazy('view', kwargs=self.kwargs)
        
        # Save related forms
        errors = save_related_forms(self)
        
        # TODO: Make sure UpdateViewExtended does this too. Am experimenting here for now.
        # TODO: Tidy this. Render the errors in the message box on the original form somehow.
        # Basically bounce back to where we were with error messages.
        # This looks neat: http://stackoverflow.com/questions/14647723/django-forms-if-not-valid-show-form-with-error-message  
        if errors:
            return JsonResponse(errors)            
                    
        # Hook for post-processing data (after it's all saved) 
        if callable(getattr(self, 'post_processor', None)): self.post_processor()
        
        return HttpResponseRedirect(self.get_success_url())

#     def post(self, request, *args, **kwargs):
#         response = super().post(request, *args, **kwargs)
#         return response

    def form_invalid(self, form):
        """
        If the form is invalid, re-render the context data with the
        data-filled form and errors.
        """
        context = self.get_context_data(form=form)
        
        response = self.render_to_response(context)
        return response

class UpdateViewExtended(UpdateView):
    '''An UpdateView which makes the model and the related_objects it defines available to the View so it can render form elements for the related_objects if desired.'''
    # FIXME: If I edit a sessions date/time, the leaderboards are corrupted (extra session is added).

    def get_context_data(self, *args, **kwargs):
        '''Augments the standard context with model and related model information so that the template in well informed - and can do Javascript wizardry based on this information'''
        context = super().get_context_data(*args, **kwargs)
        add_model_context(self, context, plural=False, title='Edit')
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        return context

    def get_object(self, *args, **kwargs):
        '''Fetches the object to edit and augments the standard queryset by passing the model to the view so it can make model based decisions and access model attributes.'''
        self.app = app_from_object(self)
        self.model = class_from_string(self, self.kwargs['model'])
        self.pk = self.kwargs['pk']
        self.obj = get_object_or_404(self.model, pk=self.kwargs['pk'])
        if callable(getattr(self.obj, 'fields_for_model', None)): 
            self.fields = self.obj.fields_for_model()
        else:           
            self.fields = fields_for_model(self.model)
        self.success_url = reverse_lazy('view', kwargs=self.kwargs)
        
        # Communicate the request user to the models (Django doesn't make this easy, need cuser middleware)
        CuserMiddleware.set_user(self.request.user)
        
        return self.obj

#     def get_form(self, form_class):
#         '''Augments the standard generated form by adding widget attributes specified in the model'''
#         form = super().get_form(form_class)   # Jumps to FormMixinBase.get_form_with_form_class
#         # Line above instantiates a form from the form_class which lands in BaseModelForm.__init__
#         # That in turn lands in BaseForm.__init__ which is where the instance gains the "fields" attribute
#         # "forms" here has tjhe "fields" attribute for Session which it gained in line above somewhere.
#         if hasattr(self.model,'widget_attrs'):
#             for field,attr in self.model.widget_attrs.items():
#                 for attr_name,attr_value in attr.items():
#                     form.fields[field].widget.attrs.update({attr_name:attr_value})
#         return form

    #@transaction.atomic
    def form_valid(self, form):
        # TODO: Make this atomic (and test). All related models need to be saved as a unit with integrity. 
        #       If there's a bail then don't save anything, i.e don't save partial data. 
        
        # Hook for pre-processing the form (before the data is saved)
        if callable(getattr(self, 'pre_processor', None)): self.pre_processor()

        # Save this form
        self.object = form.save()
        self.kwargs['pk'] = self.object.pk
        self.success_url = reverse_lazy('view', kwargs=self.kwargs)
        
        # Save related forms
        errors = save_related_forms(self)
        
        # TODO: Make sure UpdateViewExtended does this too. Am experimenting here for now.
        # TODO: Tidy this. Render the errors in the message box on the original form somehow.
        # Basically bounce back to where we were with error messages.
        # This looks neat: http://stackoverflow.com/questions/14647723/django-forms-if-not-valid-show-form-with-error-message  
        if errors:
            return JsonResponse(errors)            
                    
        # Hook for post-processing data (after it's all saved) 
        if callable(getattr(self, 'post_processor')): self.post_processor()

        return HttpResponseRedirect(self.get_success_url())
         
#         try:
#             with transaction.atomic():
#                 self.object = form.save()
#                 self.kwargs['pk'] = self.object.pk
#                 self.success_url = reverse_lazy('view', kwargs=self.kwargs)
#                 if hasattr(self, 'pre_processor') and callable(self.pre_processor): self.pre_processor()
#                 save_related_forms(self)
#                 if hasattr(self, 'post_processor') and callable(self.post_processor): self.post_processor()
#                 return HttpResponseRedirect(self.get_success_url())
#         except IntegrityError:
#             return HttpResponseRedirect(self.get_success_url())                        

#     def post(self, request, *args, **kwargs):
#         response = super().post(request, *args, **kwargs)
#         return response
