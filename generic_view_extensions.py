'''
This module provides some extensions for generic views, with the specific aim of adding more 'context'
to use in templates, including the forms and field values for related objects.
'''

import html
import collections

from titlecase import titlecase
from django.apps import apps
from django.utils import six
from django.utils.safestring import mark_safe
from django.utils.html import conditional_escape
from django.utils.encoding import force_text
from django.core.urlresolvers import reverse_lazy
from django.views.generic import DetailView, CreateView, UpdateView, DeleteView, ListView
from django.db import models, transaction, IntegrityError
from django.db.models.query import QuerySet
from django.forms.models import fields_for_model, inlineformset_factory, modelformset_factory
from django.conf.global_settings import DATETIME_INPUT_FORMATS
from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect

#===============================================================================
# Helper functions
#===============================================================================

def class_from_string(app, class_name):
    '''Given a string returns the model class with that name.'''
    return apps.get_model(app, class_name)
    
def datetime_format_python_to_PHP(python_format_string):
    '''Given a python datetime format string, attempts to convert it to the nearest PHP datetime format string possible.'''
    python2PHP = {"%a": "D", "%a": "D", "%A": "l", "%b": "M", "%B": "F", "%c": "", "%d": "d", "%H": "H", "%I": "h", "%j": "z", "%m": "m", "%M": "i", "%p": "A", "%S": "s", "%U": "", "%w": "w", "%W": "W", "%x": "", "%X": "", "%y": "y", "%Y": "Y", "%Z": "e" }

    php_format_string = python_format_string
    for py, php in python2PHP.items():
        php_format_string = php_format_string.replace(py, php)

    return php_format_string

#===============================================================================
# Some helper functions for displaying objects (similar to to those Django provides for displaying forms)
#===============================================================================

class object_display_format():
    '''Display format options for objects in the detail view.

    model - The standard model fields normally displayed by Django
    internal - the model fields Django won't normally display (primarily non-editable fields)
    related - The fields in other models that refer to this one via a relationship
    properties - The properties declared in the model (presented as pseudo-fields)

    separated - Asks the detail view to render with a separation between the above categories
    header - By default the model section has no header while the rest do (separations are noly beteen sections).

    normal - The default (=model)
    all_model - All model fields and properties
    all - all of the categories
    '''

    # The buckets that fields (and pseudo-fields in the case of properties) can fall into
    model = 1
    internal = 1 << 1
    related = 1 << 2
    properties = 1 << 3

    # Some rendering options
    separated = 1 << 4
    header = 1 << 5

    # Some shorthand formats
    normal = model
    all_model = model | internal | properties
    all = model | internal | properties | related

# A shorthand for the display format options
odf = object_display_format

def isIterable(obj):
    '''Given an object returns True if it is iterable, False if not.'''
    return not isinstance(obj, str) and isinstance(obj, collections.Iterable)

def safetitle(text):
    '''Given an object returns a title case version of its string representation.'''
    return titlecase(text if isinstance(text, str) else str(text))

_default_indent = '&nbsp;'*2    # An indent to use in hstr() for each nested level of expanded list
_flat_list_limit = 3
def hstr(obj, indent=_default_indent):
    '''Produce an HTML string representation of an object

    Tidies up lists and strings a little from their default str() representations.
    '''
    nl = "<br>"
    fnl = (nl + indent) if not indent == _default_indent else ' '
    if isinstance(obj, list) or isinstance(obj, QuerySet):
        lines = []
        for item in obj:
            lines.append(hstr(item, indent+indent))
        
        if len(lines) > _flat_list_limit:
            text = "[ " + fnl + (nl + indent).join(lines) + " ]"
        else: 
            text = "[ " + ", ".join(lines) + " ]"
    elif isinstance(obj, dict):
        lines = []
        for key in obj:
            lines.append("{}: {}".format(key, hstr(obj[key], indent+indent)))

        if len(lines) > _flat_list_limit:
            text = "{ " + fnl + (nl + indent).join(lines) + " }"
        else: 
            text = "{ " + ", ".join(lines) + " }"
    else:
        text = str(obj)
    return text

table_separator = "<hr>"  # A separator for the object_display_format lists in the as_table() view
def object_html_output(self, style):
    '''Helper function for outputting HTML. Used by as_table(), as_ul(), as_p().'''
    #TODO: This should really support CSS classes like BaseForm._html_output, so that a class can be specified

    # Define the standard HTML strings for supported style
    if style == 'table':
        normal_row="<tr><th valign='top'>{label:s}</th><td>{value:s}{help_text:s}</td></tr>"
        help_text_html='<br /><span class="helptext">%s</span>'
    elif  style == 'ul':
        normal_row='<li><b>{label:s}:</b> {value:s}{help_text:s}</li>'
        help_text_html=' <span class="helptext">%s</span>'
    elif  style == 'p':
        normal_row='<p><b>{label:s}:</b> {value:s}{help_text:s}</p>'
        help_text_html=' <span class="helptext">%s</span>'

    # Collect output lines in a list
    output = []

    for bucket in [odf.model, odf.internal, odf.related, odf.properties]:
        if self.format & bucket:
            list_label = ('Internal fields' if bucket == odf.internal
                else 'Related fields' if bucket == odf.related
                else 'Properties' if bucket == odf.properties
                else 'Standard fields' if bucket == odf.model and self.format & odf.header
                else None if bucket == odf.model
                else 'Unknown ... [internal error]')
            if list_label and (self.format & odf.separated) and self.fields_bucketed[bucket]:
                label_format = '<div style="float:left;">{}</div>{}' if style == 'table' else '{}'
                row = normal_row.format(
                    label=label_format.format(list_label,table_separator),
                    value=table_separator if style == 'table' else '',
                    help_text='',
                )

                row_format = '{}<ul>' if style == 'ul' else '{}'
                output.append(row_format.format(row))

            for name in self.fields_bucketed[bucket]:
                field = self.fields_bucketed[bucket][name]
                value = field.value

                # If a list is provided it came from a ManyToMany or a OneToMany field (actually a Foreign Key from another model) and we render it according to self.ToManyMode.
                if type(value) is list:
                    if self.ToManyMode == 'p':
                        value = "<p>" + "<br>".join(value) + "</p>"
                    elif self.ToManyMode == 'ul':
                        value = "<ul><li>" + "</li><li>".join(value) + "</li></ul>"
                    elif self.ToManyMode == 'table':
                        value = "<table><tr><td>" + "</td></tr><tr><td>".join(value) + "</td></tr></table>"
                    else:  # just accept the mode itself as a list delimiter in a div
                        value = "<div>" + self.ToManyMode.join(value) + "</div>"

                if hasattr(field, 'label') and field.label:
                    label = conditional_escape(force_text(field.label))
                else:
                    label = ''

                if hasattr(field, 'help_text') and field.help_text:
                    help_text = help_text_html % force_text(field.help_text)
                else:
                    help_text = ''

                label_format = '<div style="padding-left:15px;">{}</div>' if style == 'table' and self.format & odf.separated else '{}'

                row = normal_row.format(
                     label=label_format.format(force_text(label)),
                     value=six.text_type(hstr(value)),
                     help_text=help_text
                 )

                row_format = '<div style="margin-left:15px;">{}</div>' if style == 'p' and self.format & odf.separated else '{}'

                output.append(row_format.format(row))

            if list_label and self.format & odf.separated and style == 'ul':
                output.append('</ul>')

    return mark_safe('\n'.join(output))

def object_as_table(self):
    '''Returns this form rendered as HTML <tr>s -- excluding the <table></table>.'''
    if not hasattr(self, "ToManyMode") or (hasattr(self, "ToManyMode") and self.ToManyMode == None):
        self.ToManyMode = 'table'
    return self._html_output('table')

def object_as_ul(self):
    '''Returns this form rendered as HTML <li>s -- excluding the <ul></ul>.'''
    if not hasattr(self, "ToManyMode") or (hasattr(self, "ToManyMode") and self.ToManyMode == None):
        self.ToManyMode = 'ul'
    return self._html_output('ul')

def object_as_p(self):
    '''Returns this form rendered as HTML <p>s.'''
    if not hasattr(self, "ToManyMode") or (hasattr(self, "ToManyMode") and self.ToManyMode == None):
        self.ToManyMode = 'p'
    return self._html_output('p')

#===============================================================================
# Extend some Django Generic Views
#===============================================================================

class ListViewExtended(ListView):
    # Add some model identifiers to the context (if 'model' is passed in via the URL)
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        add_model_context(self, context, True)
        if hasattr(self, 'extra_context') and callable(self.extra_context): self.extra_context(context)
        return context

    # Fetch all the object for this model (all the tuples in this table)

    def get_queryset(self, *args, **kwargs):
        self.app = type(self).__module__.split('.')[0]
        self.model = class_from_string(self.app, self.kwargs['model'])
        self.queryset = self.model.objects.all()
        self.count = len(self.queryset)
        return self.queryset

class DetailViewExtended(DetailView):
    '''
    An enhanced DetailView which provides the HTML output methods as_table, as_ul and as_p just like the ModelForm does (defined in BaseForm).
    It takes an optional keyword argument 'ToManyMode' which can be either 'p', 'ul' or 'table' and specifies how to render ManyToMany and OneToMany (actually a ForeignKey form another model) relationships.
    If not specified takes same as the the view itself.
    '''
    # HTML formatters stolen straight form the Django ModelForm class
    _html_output = object_html_output
    as_table = object_as_table
    as_ul = object_as_ul
    as_p = object_as_p
    ToManyMode = None  # 'p', 'ul' or 'table' or a delimiter specified on __init__ - how to render the output of ManyToManyField and OneToMany (ForeignKey fields pointing to this model) relationships

    # Override properties with values passed as arguments from as_view()
    def __init__(self, **kwargs):
        if ('operation' in kwargs):
            self.ToManyMode = kwargs['operation']
        if ('ToManyMode' in kwargs):
            self.ToManyMode = kwargs['ToManyMode']
        if ('format' in kwargs):
            self.format = kwargs['format']
        pass

    # Fetch the URL specified object, needs the URL parameters "model" and "pk"
    def get_object(self, *args, **kwargs):
        self.app = type(self).__module__.split('.')[0]
        self.model = class_from_string(self.app, self.kwargs['model'])
        self.pk = self.kwargs['pk']
        self.obj = get_object_or_404(self.model, pk=self.kwargs['pk'])
        add_related_fields_to_detail_view(self)

#         # TODO: This is just debugging stuff to test trueskill calcs
#         if self.model is Session:
#             session = self.obj
#             impacts = session.calculate_trueskill_impacts()
#             pass

        return self.obj

    # Add some model identifiers to the context (if 'model' is passed in via the URL)
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        add_model_context(self, context, False)
        if hasattr(self, 'extra_context') and callable(self.extra_context): self.extra_context(context)
        return context

class DeleteViewExtended(DeleteView):
    '''An enhanced DeleteView which provides the HTML output methods as_table, as_ul and as_p just like the ModelForm does.'''
    # HTML formatters stolen straight form the Django ModelForm class
    _html_output = object_html_output
    as_table = object_as_table
    as_ul = object_as_ul
    as_p = object_as_p
    ToManyMode = None  # 'p', 'ul' or 'table' or a delimiter - how to render the output of ManyToManyField and OneToMany (ForeignKey fields pointing to this model) relationships

    # Override properties with values passed as arguments from as_view()
    def __init__(self, **kwargs):
        if ('operation' in kwargs):
            self.ToManyMode = kwargs['operation']
        if ('ToManyMode' in kwargs):
            self.ToManyMode = kwargs['ToManyMode']
        if ('format' in kwargs):
            self.format = kwargs['format']
        pass

    # Get the actual object to update
    def get_object(self, *args, **kwargs):
        self.app = type(self).__module__.split('.')[0]
        self.model = class_from_string(self.app, self.kwargs['model'])
        self.pk = self.kwargs['pk']
        self.obj = get_object_or_404(self.model, pk=self.kwargs['pk'])
        self.success_url = reverse_lazy('list', kwargs={'model': self.kwargs['model']})

        add_related_fields_to_detail_view(self)

        return self.obj

    # Add some model identifiers to the context (if 'model' is passed in via the URL)
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        add_model_context(self, context, False, 'Delete')
        if hasattr(self, 'extra_context') and callable(self.extra_context): self.extra_context(context)
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

    def get_context_data(self, *args, **kwargs):
        '''Augments the standard context with model and related model information so that the template in well informed - and can do Javascript wizardry based on this information'''
        context = super().get_context_data(*args, **kwargs)
        add_model_context(self, context, False, 'New')
        if hasattr(self, 'extra_context') and callable(self.extra_context): self.extra_context(context)
        return context

    def get_queryset(self, *args, **kwargs):
        self.fields = '__all__'
        self.app = type(self).__module__.split('.')[0]
        self.model = class_from_string(self.app, self.kwargs['model'])
        self.queryset = QuerySet(model=self.model)
        return self.queryset

    def form_valid(self, form):
        self.object = form.save()
        self.kwargs['pk'] = self.object.pk
        self.success_url = reverse_lazy('view', kwargs=self.kwargs)
        if hasattr(self, 'pre_processor') and callable(self.pre_processor): self.pre_processor()
        save_related_forms(self)
        if hasattr(self, 'post_processor') and callable(self.post_processor): self.post_processor()
        return HttpResponseRedirect(self.get_success_url())

#     def post(self, request, *args, **kwargs):
#         response = super().post(request, *args, **kwargs)
#         return response

class UpdateViewExtended(UpdateView):
    '''An UpdateView which makes the model and the related_objects it defines available to the View so it can render form elements for the related_objects if desired.'''

    def get_context_data(self, *args, **kwargs):
        '''Augments the standard context with model and related model information so that the template in well informed - and can do Javascript wizardry based on this information'''
        context = super().get_context_data(*args, **kwargs)
        add_model_context(self, context, False, 'Edit')
        if hasattr(self, 'extra_context') and callable(self.extra_context): self.extra_context(context)
        return context

    def get_object(self, *args, **kwargs):
        '''Fetches the object to edit and augments the standard queryset by passing the model to the view so it can make model based decisions and access model attributes.'''
        self.app = type(self).__module__.split('.')[0]
        self.model = class_from_string(self.app, self.kwargs['model'])
        self.pk = self.kwargs['pk']
        self.obj = get_object_or_404(self.model, pk=self.kwargs['pk'])
        self.fields = fields_for_model(self.model)
        self.success_url = reverse_lazy('view', kwargs=self.kwargs)
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

    @transaction.atomic
    def form_valid(self, form):
        # TODO: Make this atomic (and test). All related models need to be saved as a unit with integrity. 
        #       If there's a bail then don't save anything, i.e don't save partial data.  
        try:
            with transaction.atomic():
                self.object = form.save()
                self.kwargs['pk'] = self.object.pk
                self.success_url = reverse_lazy('view', kwargs=self.kwargs)
                if hasattr(self, 'pre_processor') and callable(self.pre_processor): self.pre_processor()
                save_related_forms(self)
                if hasattr(self, 'post_processor') and callable(self.post_processor): self.post_processor()
                return HttpResponseRedirect(self.get_success_url())
        except IntegrityError:
            return HttpResponseRedirect(self.get_success_url())                        

#     def post(self, request, *args, **kwargs):
#         response = super().post(request, *args, **kwargs)
#         return response

NONE = html.escape("<None>")
NOT_SPECIFIED = html.escape("<Not specified>")

#===============================================================================
# Functions for collecting and treating related forms
#===============================================================================

def add_related(model):
    '''
    Provides a safe way of testing a given model's add_related attribute by ensuring always 
    a list is provided.
     
    If a model has an attribute named add_related and it is a string that names
    
    1) a field in this model, or
    2) a field in another model in the format model.field
    
    or a list of such strings, then we take this as an instruction to include that
    those fields should be included in forms for the model.
    
    The attribute may be missing, None, or invalid as well, and so to make testing
    easier throughout the generic form processors this function always returns a list,
    empty if no valid add_related is found.
    '''
    
    if not hasattr(model, "add_related"):
        return []
    
    if isinstance(model.add_related, str):
        return [model.add_related]

    if isinstance(model.add_related, list):
        return model.add_related
     
    return [] 
    
def add_related_fields_to_detail_view(self):
    '''
    Passed a detail view instance which has an object already (self.obj) (so after or in get_object),
    will define self.fields with a dictionary of fields that a renderer can walk through later.

    Additionally self.fields_bucketed is a copy of self.fields in the buckets specified in object_display_format
    and self.fields_flat and selef.fields_list also contain all the self.fields split into teh scalar (flat) values
    and the list values respectively (which are ToMany relations to other models).
    '''
    # Build the list of fields (expects ManyToMany to be set up bi-directionally, in both involved models, i.e. makes no special effort to find them)
    # fields_for_model includes ForeignKey and ManyToMany fields in the model definition

    all_fields = self.obj._meta.get_fields()                    # All fields

    model_fields = collections.OrderedDict()                    # Editable fields in the model
    internal_fields = collections.OrderedDict()                 # Non-editable fields in the model
    related_fields = collections.OrderedDict()                  # Fields in other models related to this one
    for field in all_fields:
        if field.concrete:
            if field.editable and not field.auto_created:
                model_fields[field.name] = field
            else:
                internal_fields[field.name] = field
        else:
            related_fields[field.name] = field

    properties = [name for name in dir(self.model) if isinstance(getattr(self.model, name), property)]                      # Properties in the model (functions with the @property decorator)

    # Some bucket for all the fields so we can group them on display (scalars and then lists)
    self.fields_flat = {}                                       # Fields that have scalar values
    self.fields_flat[odf.model] = collections.OrderedDict()
    self.fields_flat[odf.internal] = collections.OrderedDict()
    self.fields_flat[odf.related] = collections.OrderedDict()
    self.fields_flat[odf.properties] = collections.OrderedDict()

    self.fields_list = {}                                       # Fields that are list items (have multiple values)
    self.fields_list[odf.model] = collections.OrderedDict()
    self.fields_list[odf.internal] = collections.OrderedDict()
    self.fields_list[odf.related] = collections.OrderedDict()
    self.fields_list[odf.properties] = collections.OrderedDict()

    # For all fields we've collected set the value and label properly
    # Problem is that relationship fields are by default listed by primary keys (pk)
    # and we want to fetch the actual string representation of that reference
    for field in all_fields:
        # All fields in other models that point to this one should have an is_relation flag

        # These are the field types we can expect:
        #    flat
        #        simple:            a simple database field in this model
        #        many_to_one:       this is a ForeignKey field pointing to another model
        #        one_to_one:        this is a OneToOneField
        #    list:
        #        many_to_many:      this is a ManyToManyField, so this object could be pointing at many making a list of items
        #        one_to_many        this is an _set field (i.e. has a ForeignKey in another model pointing to this model and this field is the RelatedManager)
        #
        # We want to build a fields dictionaries here with field values
        # There are two types of field_value we'd like to report in the result:
        #    flat values:    fields_flat contains these
        #                            if the field is scalar, just its value
        #                            if the field is a relation (a foreign object) its string representation
        #    list values:    fields_list contains these
        #                            if the field is a relation to many objects, a list of their string representations
        #
        # We also build fields_model and fields_other
        #
        # TODO fields_other needs to split into fields_model_internal and fields_other_related
        # or some such, so that a full_separated list can group the the detail view can list :
        #     scalar internal but not editable fields
        #     list internal but not editable fields
        #     relations from other models, grouped by model they come from (which seems the default)

        bucket = (odf.model if field.name in model_fields
            else odf.internal if field.name in internal_fields
            else odf.related if field.name in related_fields
            else None)

        if bucket == None:
            raise ValueError("Internal error: Poor field bucketing")

        if hasattr(field,'is_relation') and field.is_relation and (field.one_to_many or field.many_to_many):
            attname = field.name if hasattr(field,'attname') else field.name+'_set' if field.related_name is None else field.related_name   # If it's a model field it has an attname attribute, else it's a _set atttribute
            
            field.label = safetitle(attname.replace('_', ' '))

            ros = getattr(self.obj, attname).all()
            
            try: # Just in case the sort fails, fall back on unsorted    
                if hasattr(ros.model, 'sort_by'):
                    sort_lambda = "lambda obj: (obj." + ", obj.".join(ros.model.sort_by) +")"
                    ros = sorted(ros, key=eval(sort_lambda))
            except:
                pass

            if len(ros) == 0:
                field.value = NONE
            else:
                field.value = hstr([str(item) for item in ros])

            self.fields_list[bucket][field.name] = field
        else:
            field.label = safetitle(field.verbose_name)
            field.value = hstr(getattr(self.obj, field.name))
            if not str(field.value):
                field.value = NOT_SPECIFIED
            self.fields_flat[bucket][field.name] = field

    # Capture all the property values
    for name in properties:
            label = safetitle(name.replace('_', ' '))
            value = getattr(self.obj, name)
            if not str(value):
                value = NOT_SPECIFIED

            p = models.Field()
            p.label = label

            if isIterable(value):
                p.value = hstr(value) # conditional_escape(force_text(hstr(value)))
                self.fields_list[odf.properties][name] = p
            else:
                p.value = hstr(value) # conditional_escape(force_text(hstr(value)))
                self.fields_flat[odf.properties][name] = p

    # Some more buckets to put the fields in so we can separate lists of fields on display
    self.fields = collections.OrderedDict()               # All fields
    self.fields_bucketed = {}
    self.fields_bucketed[odf.model] = collections.OrderedDict()
    self.fields_bucketed[odf.internal] = collections.OrderedDict()
    self.fields_bucketed[odf.related] = collections.OrderedDict()
    self.fields_bucketed[odf.properties] = collections.OrderedDict()

    for bucket in [odf.model, odf.internal, odf.related, odf.properties]:
        for Pass in [True, False]:
            field_list = self.fields_flat[bucket] if Pass else self.fields_list[bucket]
            for name, value in field_list.items():
                self.fields_bucketed[bucket][name] = value
                self.fields[name] = value

    pass

def get_related_forms(model, operation, obj=None):
    '''
    Given a model, an operation and object on that model (abstract eg, User, edit, Bob)
    will return all the related forms useful for that operation (with that object) on that model.

    Returns a list of forms each of which is:
        a standard Django empty form for the related model
        a standard Django management form for the related model (just four hidden inputs that report the number of items in a formset really)
        a dictionary of field values, which has for each field a list of values one for each related object (each list is the same length, 1 item for each related object)

        If not object is specified, then only the empty and management forms are included, the dictionary of field values is not.
    '''
    related_forms = collections.OrderedDict()

    relations = [f for f in model._meta.get_fields() if (f.is_relation)]

    if len(relations) > 0:
        for relation in relations:

            # These are the relations we can expect:
            #     many_to_many:  this is a ManyToManyField
            #     many_to_one:   this is a ForeignKey field
            #     one_to_many    this is an _set field (i.e. has a ForeignKey in another model pointing to this model and this field is the RelatedManager)
            #     one_to_one:    this is a OneToOneField
            #
            # At this point we have an object, and a list of relations (other models that relate to it)
            # For a given relation there with be one or more related objects. If the relation is of the
            # form ToOne there will be one related object. If the relation is of the form ToMany there will 
            # be many related objects. 
            #
            # For this relation we want a "related_form" and in that form we want to build a "field_values" 
            # dictionary which is keyed on related objects the field name(s). The value will depend on 
            # whether the relation is to one or many other objects (i.e. contain a value or a list). 
            #
            # The field in the related_model can itself be:
            #    a value    - in which case the item added to a field_values list is a value
            #    a relation to one related object - in which case the item added to a field_values list is a PK
            #    a relation to many related objects - in which case the item added to a field_values list is a list of PKs
            #
            # So field_values could be a list of lists all depending on the relationships. 
            #
            # To include a relation it has to be identified in a model's add_related attribute.
            # Either this obect has a field which is specified in its add_related list, or
            # The related model has a field which is specified in add_related (in the format "model.field")
            # The relation will have an atribute named "field" if it's a candidate for the latter.  
            if ( relation.name in add_related(model)
                or (hasattr(relation, "field") 
                and relation.field.model.__name__ + "." + relation.field.name in add_related(model)) ):
                op = operation

                # TODO: Can any other operation land here? 
                #        If so, is this if in the right place? 
                #        What does a detail view wnat here for example?
                if op in ['add', 'edit']:
                    # First thing, let's get the field_values of all related objects
                    field_values = {}   # A dictionary in  {name: list of values}
                    ros = None          # QuerySet of related objects (used to build the management form)

                    if not obj is None:
                        # Now fetch related object values to make them easily available for form initialization
                        # For fields where there are many values compile a list of those values
                        fields = fields_for_model(relation.related_model)        # The fields in the related model

                        # fields_for_model doesn't return uneditable fields ...
                        # if this model has an add_related attribute and it specifies any uneditable fields then
                        # override this objection and add them to the fields list, else they won't be added to the
                        # related_forms. You may want explicitly to add uneditable fields to related_forms so as
                        # to be able to edit them. The reasoning is as follows: editable=False means the field won't
                        # appear on the standard form editor for that model, whereas add_related means that the field
                        # is offered when it's related to a model so that we can build a custom form editor for that
                        # field through its relation if we want. In short we have suppressed its appearance on standard
                        # model forms but made it available on related custom built model forms.
                        for f in add_related(relation.related_model):
                            if hasattr(relation.related_model, f) and not f in fields:
                                fields[f] = getattr(relation.related_model, f)

                        # If many objects are related to this one we'll build a list of values for each field_values entry
                        if relation.one_to_many or relation.many_to_many:

                            # Get the related objects, method varies for many_to_many and one_to_many
                            if relation.many_to_many:
                                ros = getattr(obj, relation.name).all()
                            else:
                                ros = relation.related_model.objects.filter(**{relation.field.name: obj.pk})

                            # Sorted returns a list, but ros must be a queryset for later use in created the related_form
                            # So keep ros untouched and build a sorted list separately
                            # sorted_rows is just used here to populate the lists we insert into field_values in the order specified
                            sorted_ros = ros
                            if hasattr(relation.related_model, 'sort_by'):
                                sort_lambda = "lambda obj: (obj." + ", obj.".join(relation.related_model.sort_by) +")"
                                sorted_ros = sorted(ros, key=eval(sort_lambda))

                            pk_name = relation.related_model._meta.pk.name                   # Name of the primary key
                            for field_name in fields:
                                field_values[field_name] = []                   # empty list
                            field_values[pk_name] = []

                            # For every related object, we add a value, PK or list-of-PKs to the growing lists in field_values
                            # A value if this field has a simple value
                            # A PK if the field isa foreign key to another object (then that remote objects PK)
                            # A list of PKs if it is field that points to many remote objects (like a OneToMany or ManyToMany) 
                            for ro in sorted_ros:
                                for field_name in field_values:
                                    field_value = getattr(ro,field_name)

                                    # If it's a single object from another model (it'll have a primary key field)
                                    if hasattr(field_value, 'pk'):
                                        # Add the objects primary key to the list
                                        field_values[field_name].append(field_value.pk)

                                    # If it's many objects from another model (it'll have a model field)
                                    elif hasattr(field_value, 'model'):
                                        # Add a list of the objects primary keys to the list
                                        roros = field_value.model.objects.filter(**field_value.core_filters)

                                        if hasattr(field_value.model, 'sort_by'):
                                            sort_lambda = "lambda obj: (obj." + ", obj.".join(field_value.model.sort_by) +")"
                                            roros = sorted(roros, key=eval(sort_lambda))

                                        roro_field_values = []

                                        for roro in roros:
                                            roro_field_values.append(roro.pk)       # build a list of primary keys

                                        field_values[field_name].append(roro_field_values)

                                    # If it's a scalar value
                                    else:
                                        # Add the value to the list
                                        field_values[field_name].append(field_value)

                        elif relation.many_to_one or relation.one_to_one:

                            # For the one related object unpack its fields into field_values
                            if hasattr(obj, relation.attname) and getattr(obj, relation.attname) is not None:
                                ros = relation.related_model.objects.filter(pk=getattr(obj, relation.attname))  # The related object
                                ro = ros[0]                                                                     # There will only be one
                                pk_name = ro._meta.model._meta.pk.name                                          # Name of the primary key

                                # Store its PK in field_values
                                field_values[pk_name] = getattr(ro, pk_name)

                                # Store its remaining field values in field_values
                                for field_name in fields:
                                    # The value of the field in the related object
                                    field_value = getattr(ro, field_name)

                                    # If it's a single object from another model (it'll have a primary key field)
                                    if hasattr(field_value, 'pk'):
                                        # Add the objects primary key to the list
                                        field_values[field_name].append(field_value.pk)

                                    # If it's many objects from another model (it'll have a model field)
                                    elif hasattr(field_value,"model"):
                                        # Put a list of the related objects PKs into field_values
                                        ros = field_value.model.objects.filter(**field_value.core_filters)
                                        field_values[field_name] = []
                                        for ro in ros:
                                            field_values[field_name].append(ro.pk)       # build a list of primary keys

                                    # For scalar values though we just record the value of the field in field_values
                                    else:
                                        field_values[field_name] = field_value

                    # Now that we know about the related objects if any we can build the related forms
                    # Django can build us an empty form for the related model
                    # TODO: Must add fk_name=  for case where related model has more than one fk back to this model apparently. No such case I think in CoGs
                    Related_Formset = modelformset_factory(relation.related_model, can_delete=False, extra=0, fields=('__all__'), formfield_callback=custom_field_callback)
                    related_formset = Related_Formset(prefix=relation.related_model.__name__, queryset=ros)

                    # Build the related_form for this relation
                    related_name = relation.related_model.__name__
                    related_forms[related_name] = related_formset.empty_form
                    related_forms[related_name].field_values = field_values
                    related_forms[related_name].management_form = related_formset.management_form

    # Now check each of the related forms to see if any of them want to add related forms!
    # This could be dangerous if recursive. Relies on desible configuration of the add_related model fields.
    for rf in related_forms:
        rm = related_forms[rf].Meta.model

        if len(add_related(rm)) > 0:
            # add generic related forms (with no object) to provide easy access to the related empty form and field widgets in the context
            related_forms[rf].related_forms = get_related_forms(rm, operation)

            # add instance_forms for each instance
            if hasattr(related_forms[rf], "field_values") and rm._meta.pk.attname in related_forms[rf].field_values:
                related_forms[rf].instance_forms = {}

                # Ordering is important here as field_values which are lists are in an order and should all be in the same order
                # So we need to observe and respect the order of pk values in field_values when creating instance lists of related values
                pk_list = []                   # Keep an ordered list of the PKs as the dictionary "instance_forms" loses order
                pk_attr = rm._meta.pk.attname  # Get the name of the primary key attribute
                if isinstance(related_forms[rf].field_values[pk_attr], list):
                    for pk in related_forms[rf].field_values[pk_attr]:
                        o = rm.objects.get(pk=pk)
                        related_forms[rf].instance_forms[pk] = get_related_forms(rm, operation, o)
                        pk_list.append(pk)
                else:
                    pk = related_forms[rf].field_values[pk_attr]
                    o = rm.objects.get(pk=pk)
                    related_forms[rf].instance_forms[pk] = get_related_forms(rm, operation, o)
                    pk_list.append(pk)

                # At this point pk_list has one pk if there was one instance of the related model and is a list if there was more than one

                # For ease of use in the template context add field_values for all the instance related fields as well
                if hasattr(related_forms[rf],"instance_forms"):
                    for pk in pk_list: # Walk the ordered list of PKs
                        for form in related_forms[rf].instance_forms[pk]:
                            for ro_field in related_forms[rf].instance_forms[pk][form].field_values:
                                ro_field_name = form + "_" + ro_field
                                ro_field_value = related_forms[rf].instance_forms[pk][form].field_values[ro_field]
                                if not ro_field_name in related_forms[rf].field_values:
                                    related_forms[rf].field_values[ro_field_name] = []
                                related_forms[rf].field_values[ro_field_name].append(ro_field_value)


    return related_forms

def save_related_forms(self):
    #TODO: Docs state: If your formset contains a ManyToManyField, you’ll also need to call formset.save_m2m() to ensure the many-to-many relationships are saved properly.
    #        What does that mean?
    #
    # Very helpful page:
    #   https://docs.djangoproject.com/en/dev/topics/forms/modelforms/#id1
    #
    # TODO: Consider how this works if:
    #
    # 1. There is a foreignkey in the related model pointing here: OneToMany
    # 2. There is a foreignkey here to another model: ManyToOne
    # 3. This is a ManyToMany relationship
    #
    # In each case how are the table links saved properly?
    #
    # In case 1: the related formset is instantiation with the original object passed as an istance. That is how Django knows which object the related formset relates to.
    # Case 2 and 3 uncertain at present. Think about it.

    # TODO: Can we access a list of all the inital forms in formset?
    # So we can see if the submission contains them all and if not take action?

    related_forms = get_related_forms(self.model, self.operation, self.object)
    for name,form in related_forms.items():
        model = self.model                  # The model being saved
        obj = self.object                   # The object created when it was saved
        related_model = form._meta.model    # The related model to save

        Related_Formset = inlineformset_factory(model, related_model, can_delete=False, extra=0, fields=('__all__'))
        related_formset = Related_Formset(self.request.POST, self.request.FILES, instance=obj, prefix=name)

        if related_formset.is_valid():
            related_formset.save()
        else:
            # TODO: Report errors cleanly on new edit form
            # Errors are in related_formset.errors
            raise ValueError("Invalid Data")

def custom_field_callback(field):
    '''A place from which to deliver a customised formfield for a given field'''
    return field.formfield()

def fix_widgets(form):
    '''
        For each field in a form, will add the type name of the field as a CSS class to the widget so that
        Javascript in the form can act on the field based on class if needed.
    '''
    for field in form.fields.values():
        field.widget.attrs["class"] =  type(field).__name__
    return form

def add_model_context(self, context, plural, title=False):
    '''
    Add some useful context information to views.

    Specifically, access to the model, and related forms 
    (forms for models that relate to this one).
    '''
    context.update(self.kwargs)
    if 'model' in context and hasattr(self, 'operation'):
        context["model"] = context["view"].model
        context["model_name"] = context["view"].kwargs['model']
        context["model_name_plural"] = context["view"].model._meta.verbose_name_plural
        context["operation"] = self.operation
        context["title"] = (title + ' ' if title else '') + (safetitle(context["model"]._meta.verbose_name_plural) if plural else safetitle(context["model"]._meta.verbose_name))
        context["default_datetime_input_format"] = datetime_format_python_to_PHP(DATETIME_INPUT_FORMATS[0])

        # Check for related models and pass into the context either a related form or related view.
        # Only do this if the model asks us to do so via the add_related attribute.
        if self.operation in ["add", "edit", "detail", "view"] and len(add_related(context["model"])) > 0:
            related_forms = get_related_forms(context["model"], self.operation, self.object)
            context['related_forms'] = related_forms

        if self.operation in ["add", "edit"] and 'form' in context:
            fix_widgets(context['form'])
    else:
        raise ValueError("Internal Error: Views must be provided at least 'model' in kwargs and an 'operation' argument. One or the other was missing. This is a site design error relating to defined urlpatterns which failed to provide on or the other.")

    return context
