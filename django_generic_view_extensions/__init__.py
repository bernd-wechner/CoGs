'''
Created on 13Jan.,2017

@author: Bernd Wechner
@status: Alpha - works and is in use on a dedicated project. Is not complete, and needs testing for generalities.

Django provides some excellent generic class based views:

    https://docs.djangoproject.com/en/1.10/topics/class-based-views/generic-display/
    
They are excellent for getting a site up and running really quickly from little more than a model specification. 

The admin site of course provides a rather excellent and complete version of generic database administration:

    https://docs.djangoproject.com/en/1.10/ref/contrib/admin/
     
But as at Django 1.10 the built in generic class based views fall somewhat short of complete.

This module provides extensions to the generic class based views, with the specific aim of adding more context
to use in templates and including the forms and field values for related objects.

In summary, the built generic class based views we are extending are from django.views.generic: 

ListView - for listing the objects in a model
DetailView - for examining the details of a specific object (model instance) 
CreateView - for creating new objects
UpdateView - for editing existing objects
DeleteView - for deleting existing objects

The main use of this module is to offer: 

ListViewExtended - for listing the objects in a model
DetailViewExtended - for examining the details of a specific object (model instance) 
CreateViewExtended - for creating new objects
UpdateViewExtended - for editing existing objects
DeleteViewExtended - for deleting existing objects

which can be used in place of the built-ins. They derive directly from them adding some features as follows:

Enrich the context provided to templates. Specifically these elements:

model - the model class (available as view.model as well, but what the heck.
model_name - because it's not easy to reference view.model.__name__ in a template alas.
model_name_plural - because it's handier than referencing view.model._meta.verbose_name_plural
operation - the value of "operation" passed from urlconf (should be "list", "view", "add", "edit" or "delete")
title - a convenient title constructed from the above that can be used in a template 
default_datetime_input_format - the default Django datetime input format as a PHP datetime format string. Very useful for configuring a datetime picker.

DetailViewExtended and DeleteViewExtended 

Django provides a really sweet set of context elements for forms:

form.as_table
form.as_ul
form.as_p

with which you can rapidly render the basic form for a model without further ado in three formats. 

Oddly it does not provide these for detail views. So here we do. Direct reproduction of the form
version only instead of containing HTML form elements it just contains the field contents rendered in
a nice way (using the __str__ representation of Models). These are available as:

view.as_table
view.as_ul
view.as_p

in the context they deliver. 

These views take an optional keyword argument ToManyMode to specify how lists should be rendered for 
fields that are relations to many. The many remote objects have their own __str__ representations which 
can be rich of course and so some control over how lists of these are presented is offered. ToManyMode
can take any of the 3 formats 'table', 'ul', 'p' as per the view itself, that is display the multiple 
values as a table as a bulleted list or as a set of paragraphs. It can be any other string as well in
which case that string is used as a delimiter between values. It can contain  HTML of course, for 
example '<BR>'.  

CreateViewExtended and UpdateViewExtended 

Easily the biggest extension is to include related form information in the context so that
it's easy to create a rich forms that include elements from numerous related forms. 

This is delivered in a context element 'related_forms' which is a rich representation of all the 
related forms you request in a given model. The request is made by including an atttribute 'add_related'
in the model which is a list of field names that identify a relation. This is recursive, that is, 
the related models may also contain an 'add_related' attribute. You can probably crash Django by
creating a closed loop of references if you like - not advised.

The related_forms element contains one entry per related model, being a related form for that model.

For example to illustrate two tiers, if you have a model Family and a family can have Members and 
Pets and when editing family you want access on your form to the fields of Family, Member and Pet.
But let's say Members and Pets can have Issues you're trying to track and you want rich forms that 
let a user enter a family, it smembers pets and issues all at once. 

Well CreateViewExtended and UpdateViewExtended make that easy for you, providing all the form 
elements in the context if you ask for them and also saving the submitted data properly for 
you!

Here's what it might look like:

class Family(models.Model):
    name = models.CharField('Name of the Family', max_length=80)
    add_related = ['members','pets'] # could also read ['Member.family', 'Pet.family']

class Member(models.Model):
    name = models.CharField('Name of the Member', max_length=80)
    family = models.ForeignKey('Family', related_name='members')
    issues = models.ManyToManyField('Issue', related_name='suffering_members')
    add_related = ['issues']

class Pet(models.Model):
    name = models.CharField('Name of the Pet', max_length=80)
    family = models.ForeignKey('Family', related_name='pets')
    issues = models.ManyToManyField('Issue', related_name='suffering_pets')
    add_related = ['issues']

class Issue(models.Model):
    description = models.CharField('Issue', max_length=200)

well mean the context that CreateViewExtended and UpdateViewExtended provide you with
the following possible references:

related_forms.Member.name
related_forms.Member.related_forms.Issue.description
related_forms.Pet.name
related_forms.Pet.related_forms.Issue.description

as the form widgets for those fields respectively.

To build rich forms you need more though so added to the related_form for each model 
are two extra elements management_form and field_data.

management_form is the standard management form Django requires (and you should understand
these to build rich forms). In summary though they are simply little HTML snippets that 
contain four hidden input fields named TOTAL_FORMS, INITIAL_FORMS, MIN_NUM_FORMS, MAX_NUM_FORMS.
Documentation on exactly how these work is meager in the django world, but they are used
by the Django code when submitted form data is processed, and to that end in rich forms you
will need (in Javascript perhaps) to update TOTAL_FORMS in particular to tell Django how many
forms are being submitted. This is a little more complicated than we can cover here, but
note that Django uses the word FORM not in the sense of an HTML FORM (of which you'll probably 
only have one), but for a single model instance that is being submitted.    

In the example above, if you write a form that allows us to create a Family, and specify the
number of members and pets, and issues for each, you'll be submitting a number of members and
pets and a number of issues for each. Djnago expects a strict naming convention on all these
form elements, which embeds a number in the field names and TOTAL_FORMS informs it what
numbers to look for and process. 

TODO: Document the naming convention of Django form elements too.

field_data contains one entry for each field which returns the value of that field with a 
special caveat, the value is complex. If the field is a Django concrete field (not a relation)
then its actual value. If it's a relation then the pk or list of pks (primary keys) of the 
related objects.

related_values of course is only provided by UpdateViewExtended for editing existing 
objects and not by CreateViewExtended.

In the case above these context references are available:

related_forms.Member.management_form   
related_forms.Pet.management_form   
related_forms.Member.related_forms.Issue.management_form   
related_forms.Pet.related_forms.Issue.management_form   
related_forms.Member.field_data.name      # which is a string, the name 
related_forms.Member.field_data.issues    # which is a list of integers, the primary keys of the issues 
related_forms.Pet.field_data.name         # which is a string, the name 
related_forms.Pet.field_data.issues       # which is a list of integers, the primary keys of the issues 
related_forms.Member.related_forms.Issue.field_data.description   # which is a list of strings, the descriptions mapping to related_forms.Member.field_data.issues    
related_forms.Pet.related_forms.Issue.field_data.description      # which is a list of strings, the descriptions mapping to related_forms.Pet.field_data.issues
'''

import html
import collections
import functools
from titlecase import titlecase
from types import SimpleNamespace
from time import time

from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.apps import apps
from django.utils import six
from django.utils.safestring import mark_safe
from django.utils.html import conditional_escape
from django.utils.encoding import force_text
from django.core.urlresolvers import reverse_lazy
from django.core.exceptions import ValidationError
from django.db import models, transaction, IntegrityError
#from django.db.models import DEFERRED
from django.db.models.query import QuerySet
from django.forms.models import fields_for_model, inlineformset_factory, modelformset_factory
from django.conf.global_settings import DATETIME_INPUT_FORMATS
from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect

from url_filter.filtersets import ModelFilterSet
from django.http.response import JsonResponse

#===============================================================================
# Helper functions
#===============================================================================

def app_from_object(o):
    '''Given an object returns the name of the Django app that it's declared in'''
    return type(o).__module__.split('.')[0]    

def class_from_string(app_name_or_object, class_name):
    '''
    Given the name of a Django app (or object declared in that Django app) 
    and a string returns the model class with that name.
    '''
    if isinstance(app_name_or_object, str):
        module = apps.get_model(app_name_or_object, class_name)
    else:
        module = apps.get_model(app_from_object(app_name_or_object), class_name)
    return module

def datetime_format_python_to_PHP(python_format_string):
    '''Given a python datetime format string, attempts to convert it to the nearest PHP datetime format string possible.'''
    python2PHP = {"%a": "D", "%a": "D", "%A": "l", "%b": "M", "%B": "F", "%c": "", "%d": "d", "%H": "H", "%I": "h", "%j": "z", "%m": "m", "%M": "i", "%p": "A", "%S": "s", "%U": "", "%w": "w", "%W": "W", "%x": "", "%X": "", "%y": "y", "%Y": "Y", "%Z": "e" }

    php_format_string = python_format_string
    for py, php in python2PHP.items():
        php_format_string = php_format_string.replace(py, php)

    return php_format_string

debug_time_first = None
debug_time_last = None

def print_debug(msg):
    '''
    Prints a timestamped message to stdout with timestamps for tracing.
    '''
    global debug_time_first
    global debug_time_last
    now = time()  # the time in seconds since the epoch as a floating point number.
    if debug_time_first is None:
        debug_time_first = now
    if debug_time_last is None:
        debug_time_last = now
    print("{:f}, {:f} - {}".format(now-debug_time_first, now-debug_time_last, msg))
    debug_time_last = now    

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

    # Some format of fields, flat or list
    flat = 1
    list = 1 << 1

    # The buckets that fields (and pseudo-fields in the case of properties) can fall into
    model = 1 << 2
    internal = 1 << 3
    related = 1 << 4
    properties = 1 << 5

    # Some rendering options
    separated = 1 << 6
    header = 1 << 7

    # Some shorthand formats
    normal = flat | model
    all_model = flat | list | model | internal | properties
    all = flat | list | model | internal | properties | related

# A shorthand for the display format options
odf = object_display_format

def get_object_display_format(request):
    '''
    Standard means of extracting a object display format from a request.
    
    Assumes odf.normal and modifies as per request.
    :param request:
    '''
    ODF = odf.normal
    
    if 'noall' in request or 'none' in request:
        ODF &= ~odf.all
        
    if 'all' in request:
        ODF = odf.all
        
    if 'noflat' in request:
        ODF &= ~odf.flat
    if 'nomodel' in request:
        ODF &= ~odf.model
    if 'nolist' in request:
        ODF &= ~odf.list
    if 'nointernal' in request:
        ODF &= ~odf.internal
    if 'norelated' in request:
        ODF &= ~odf.related
    if 'noproperties' in request:
        ODF &= ~odf.properties    
        
    if 'flat' in request:
        ODF |= odf.flat
    if 'model' in request:
        ODF |= odf.model
    if 'list' in request:
        ODF |= odf.list
    if 'internal' in request:
        ODF |= odf.internal
    if 'related' in request:
        ODF |= odf.related
    if 'properties' in request:
        ODF |= odf.properties
    
    return ODF

class object_list_format():
    '''Format options for objects in the list view.

    brief   - The standard __str__ representation of the object
    verbose - The  __verbose_str__ representation of the object if it exists, else falls back on __str__
    rich    - The  __rich_str__ representation of the object else falls back on __verbose_str__
    detail  - the detail view of the object!
    
    '''

    # Some format of fields, flat or list
    brief = 0
    verbose = 1
    rich = 1 << 1
    detail = 1 << 2

# A shorthand for the list format options
olf = object_list_format

def get_object_list_format(request):
    '''
    Standard means of extracting a object list format from a request.
    
    Assumes olf.brief and modifies as per request.
    :param request:
    '''
    OLF = olf.brief
    
    if 'verbose' in request:
        OLF |= olf.verbose
    if 'rich' in request:
        OLF |= olf.rich
    if 'detail' in request:
        OLF |= ~olf.verbose
    
    return OLF

def display_format(result_type):
    '''
    A decorator for properties which permits specification of a type for use in deciding whether or 
    not to display the property. 
    :param result_type: Expected to be object_display_format.flat or object_display_format.list
    '''
    def decorator(func):
        func.__type = result_type
        return func
    return decorator

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
    if isinstance(obj, list) or isinstance(obj, set) or isinstance(obj, QuerySet):
        lines = []
        multilineval = False
        multiwordval = False
        for item in obj:
            valstr = hstr(item, indent+indent)
            if valstr.count('<br>') > 0:
                multilineval = True
            if valstr.count(' ') > 0:
                multiwordval = True
            lines.append(valstr)
        
        if len(lines) > _flat_list_limit or multilineval or multiwordval:
            text = "[ " + fnl + (nl + indent).join(lines) + " ]"
        else: 
            text = "[ " + ", ".join(lines) + " ]"
    elif isinstance(obj, dict):
        lines = []
        multilineval = False
        multiwordval = False
        for key in obj:
            valstr = hstr(obj[key], indent+indent)
            if valstr.count('<br>') > 0:
                multilineval = True
            if valstr.count(' ') > 0:
                multiwordval = True
            lines.append("{}: {}".format(key, valstr))

        if len(lines) > _flat_list_limit or multilineval or multiwordval:
            text = "{ " + fnl + (nl + indent).join(lines) + " }"
        else: 
            text = "{ " + ", ".join(lines) + " }"
    else:
        text = force_text(str(obj))
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

    for bucket in self.fields_bucketed:
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

def apply_sort_by(queryset):
    '''
    Sorts a query set by the the fields and properties listed in a sort_by attribute if it's sepecified.
    This augments the meta option order_by in models because that option cannot respect properties.
    This option though wants a sortable property to be specified and that isn't an object, has to be
    like an into or string or something, specifically a field in the object that is sortable. So usage
    is a tad different to order_by. 
    '''
    model = queryset.model
    if hasattr(model, 'sort_by'):
        try:        
            sort_lambda = "lambda obj: (obj." + ", obj.".join(model.sort_by) +")"
            return sorted(queryset, key=eval(sort_lambda))
        except Exception as e:
            return queryset
    else:
        return queryset

def pretty_FilterSet(filterset):
    '''
    Returns a pretty formatted string version of a filterset 
    :param filterset:
    '''
    
    operation = {
        "exact" : " = ",
        "iexact" : " = ",
        "contains" : " contains ",
        "icontains" : " contains ",
        "startswith" : " starts with ",
        "istartswith" : " starts with ",
        "endswith" : " ends with ",
        "iendswith" : " ends with ",
        "range" : " is between ",
        "isnull" : " is NULL ",
        "regex" : " matches ",
        "iregex" : " matches ",
        "in" : " is in ",
        "gt" : " > ",
        "gte" : " >= ",
        "lt" : " < ",
        "lte" : " <= ",
#         "year" : "",
#         "month" : "",
#         "day" : "",
#         "week" : "",
#         "week_day" : "",
#         "time" : "",
#         "hour" : "",
#         "minute" : "",
#         "second" : "",
        }

    def concrete_field(model, field_name):
        for field in model._meta.fields:
            if field.attname == field_name:
                return field
        return None
    
    def get_field(components, component, model):
        field_name = components[component]
        field = getattr(model, field_name)
        
        # To Many fields 
        if hasattr(field, "rel"):
            if field.rel.many_to_many:
                field = get_field(components, component+1, field.field.related_model) 
            elif field.rel.one_to_many:
                field = get_field(components, component+1, field.field.model) 
        # To One fields 
        elif hasattr(field, "field"): 
            field = get_field(components, component+1, field.field.related_model)
        else:
            field = concrete_field(model, field_name)
        
        return field
    
    specs = filterset.get_specs()
    pretty_specs = []
    for filter in specs:
        # __year - filter["lookup"] == "year"
        field = get_field(filter.components, 0, filterset.queryset.model)
        if len(filter.components) > 1 and filter.lookup == "exact":
            Os = field.model.objects.filter(**{"{}__{}".format(field.attname, filter.lookup):filter.value})
            O = Os[0] if Os.count() > 0 else None
            field_name = field.model._meta.object_name
            field_value = str(O)
        else:
            field_name = field.verbose_name
            field_value = filter.value
        
        pretty_specs += ["{} {} {}".format(field_name, operation[filter.lookup], field_value)]
    
    return " and ".join(pretty_specs)
  
class ListViewExtended(ListView):
    # Add some model identifiers to the context (if 'model' is passed in via the URL)
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        add_model_context(self, context, plural=True)
        
        # Pass the selected object list format to the context for selective rendering 
        # with the list_format template tag (which renders the object accordingly)
        OLF = get_object_list_format(self.request.GET)
        if OLF & olf.rich:
            context['object_list_format'] = "rich"
        elif OLF & olf.verbose:
            context['object_list_format'] = "verbose" 
        else: 
            context['object_list_format'] = "brief" 

        if hasattr(self, 'extra_context') and callable(self.extra_context): self.extra_context(context)
        return context

    # Fetch all the object for this model (all the tuples in this table)

    def get_queryset(self, *args, **kwargs):
        self.app = app_from_object(self)
        self.model = class_from_string(self, self.kwargs['model'])
        
        # If the URL has GET parameters (following a ?) then self.request.GET 
        # will contain a dictionary of name: value pairs that FilterSet uses 
        # construct a new filtered queryset. 
        if len(self.request.GET) > 0:
            FilterSet = type("FilterSet", (ModelFilterSet,), { 
                'Meta': type("Meta", (object,), { 
                    'model': self.model 
                    })
            })
            
            fs = FilterSet(data=self.request.GET, queryset=self.model.objects.all())
            self.filter = pretty_FilterSet(fs)
            self.queryset = fs.filter()
        else:
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
        self.app = app_from_object(self)
        self.model = class_from_string(self, self.kwargs['model'])
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
        add_model_context(self, context, plural=False)
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
        self.app = app_from_object(self)
        self.model = class_from_string(self, self.kwargs['model'])
        self.pk = self.kwargs['pk']
        self.obj = get_object_or_404(self.model, pk=self.kwargs['pk'])
        self.success_url = reverse_lazy('list', kwargs={'model': self.kwargs['model']})

        add_related_fields_to_detail_view(self)

        return self.obj

    # Add some model identifiers to the context (if 'model' is passed in via the URL)
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        add_model_context(self, context, plural=False, title='Delete')
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

    # TODO: the form needs to use combo boxes for list select values like Players in a Session. You have to be able to type and find a player with a pattern match so to speak. The list can get very very long you see. 

    def get_context_data(self, *args, **kwargs):
        '''Augments the standard context with model and related model information so that the template in well informed - and can do Javascript wizardry based on this information'''
        print_debug("Getting contex data")
        context = super().get_context_data(*args, **kwargs)
        print_debug("Adding model context")
        add_model_context(self, context, plural=False, title='New')
        print_debug("Adding extra context")
        if hasattr(self, 'extra_context') and callable(self.extra_context): self.extra_context(context)
        print_debug("Got context data")
        return context

    def get_queryset(self, *args, **kwargs):
        print_debug("Getting queryset")
        self.fields = '__all__'
        self.app = app_from_object(self)
        self.model = class_from_string(self, self.kwargs['model'])
        self.queryset = QuerySet(model=self.model)
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
        if hasattr(self, 'pre_processor') and callable(self.pre_processor): self.pre_processor()

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
        if hasattr(self, 'post_processor') and callable(self.post_processor): self.post_processor()
        
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
    # FIXME: If I edit a sessions date/time, the leaderboardsare corrupted (extra session is added).

    def get_context_data(self, *args, **kwargs):
        '''Augments the standard context with model and related model information so that the template in well informed - and can do Javascript wizardry based on this information'''
        context = super().get_context_data(*args, **kwargs)
        add_model_context(self, context, plural=False, title='Edit')
        if hasattr(self, 'extra_context') and callable(self.extra_context): self.extra_context(context)
        return context

    def get_object(self, *args, **kwargs):
        '''Fetches the object to edit and augments the standard queryset by passing the model to the view so it can make model based decisions and access model attributes.'''
        self.app = app_from_object(self)
        self.model = class_from_string(self, self.kwargs['model'])
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

    #@transaction.atomic
    def form_valid(self, form):
        # TODO: Make this atomic (and test). All related models need to be saved as a unit with integrity. 
        #       If there's a bail then don't save anything, i.e don't save partial data. 
        
        # Hook for pre-processing the form (before the data is saved)
        if hasattr(self, 'pre_processor') and callable(self.pre_processor): self.pre_processor()

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
        if hasattr(self, 'post_processor') and callable(self.post_processor): self.post_processor()

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
    and self.fields_flat and self.fields_list also contain all the self.fields split into the scalar (flat) values
    and the list values respectively (which are ToMany relations to other models).
    '''
    # Build the list of fields (expects ManyToMany to be set up bi-directionally, in both involved models, i.e. makes no special effort to find them)
    # fields_for_model includes ForeignKey and ManyToMany fields in the model definition

    # Fields are categorized as follows for convenience and layout and performance decisions
    #    flat or list  
    #    model, internal, related or properties
    #
    # By default we will populate self.fields only with flat model fields.
    #
    # if keywords are in the GET request we will add the values of list, internal, related and/or properties.
    # And even turn off list and model if requested.
    
    def is_list(field):
        return hasattr(field,'is_relation') and field.is_relation and (field.one_to_many or field.many_to_many)
    
    def is_property(name):
        return isinstance(getattr(self.model, name), property)

    ODF = get_object_display_format(self.request.GET)    

    all_fields = self.obj._meta.get_fields()                    # All fields

    model_fields = collections.OrderedDict()                    # Editable fields in the model
    internal_fields = collections.OrderedDict()                 # Non-editable fields in the model
    related_fields = collections.OrderedDict()                  # Fields in other models related to this one
    for field in all_fields:
        if (is_list(field) and ODF & odf.list) or (ODF & odf.flat):
            if field.concrete:
                if ODF & odf.model and field.editable and not field.auto_created:
                    model_fields[field.name] = field
                elif ODF & odf.internal:
                    internal_fields[field.name] = field
            elif ODF & odf.related:
                related_fields[field.name] = field

    # TODO: Is the property list or flat? Can't know without evaluating it unless the model confesses.
    # Properties in the model (functions with the @property decorator)
    # FIXME: Currently cannot divine without evaluating the property what type 
    # it will yield. Need to find a way to decorate properties with a type annotation.
    if ODF & odf.properties:
        properties = [name for name in dir(self.model) if is_property(name)]

    # Some bucket for all the fields so we can group them on display (scalars and then lists)
    
    if ODF & odf.flat:
        self.fields_flat = {}                                       # Fields that have scalar values
        if ODF & odf.model:
            self.fields_flat[odf.model] = collections.OrderedDict()
        if ODF & odf.internal:
            self.fields_flat[odf.internal] = collections.OrderedDict()
        if ODF & odf.related:
            self.fields_flat[odf.related] = collections.OrderedDict()
        if ODF & odf.properties:
            self.fields_flat[odf.properties] = collections.OrderedDict()

    if ODF & odf.list:
        self.fields_list = {}                                       # Fields that are list items (have multiple values)
        if ODF & odf.model:
            self.fields_list[odf.model] = collections.OrderedDict()
        if ODF & odf.internal:
            self.fields_list[odf.internal] = collections.OrderedDict()
        if ODF & odf.related:
            self.fields_list[odf.related] = collections.OrderedDict()
        if ODF & odf.properties:
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

        bucket = (odf.model if field.name in model_fields
            else odf.internal if field.name in internal_fields
            else odf.related if field.name in related_fields
            else None)

        if not bucket is None:
            if is_list(field):
                if ODF & odf.list:
                    attname = field.name if hasattr(field,'attname') else field.name+'_set' if field.related_name is None else field.related_name   # If it's a model field it has an attname attribute, else it's a _set atttribute
                    
                    field.label = safetitle(attname.replace('_', ' '))
        
                    ros = apply_sort_by(getattr(self.obj, attname).all())
        
                    if len(ros) == 0:
                        field.value = NONE
                    else:
                        field.value = hstr([str(item) for item in ros])
        
                    self.fields_list[bucket][field.name] = field
            else:
                if ODF & odf.flat:
                    field.label = safetitle(field.verbose_name)
                    field.value = hstr(getattr(self.obj, field.name))
                    if not str(field.value):
                        field.value = NOT_SPECIFIED
                    self.fields_flat[bucket][field.name] = field

    # Capture all the property values
    if ODF & odf.properties:
        for name in properties:
            label = safetitle(name.replace('_', ' '))
            value = getattr(self.obj, name)
            if not str(value):
                value = NOT_SPECIFIED
    
            p = models.Field()
            p.label = label
    
            if isIterable(value):
                if ODF & odf.list:
                    p.value = hstr(value) # conditional_escape(force_text(hstr(value)))
                    self.fields_list[odf.properties][name] = p
            else:
                if ODF & odf.flat:
                    p.value = hstr(value) # conditional_escape(force_text(hstr(value)))
                    self.fields_flat[odf.properties][name] = p

    # Some more buckets to put the fields in so we can separate lists of fields on display
    self.fields = collections.OrderedDict()               # All fields
    self.fields_bucketed = collections.OrderedDict()

    buckets = []    
    if ODF & odf.model:
        self.fields_bucketed[odf.model] = collections.OrderedDict()
        buckets += [odf.model]
    if ODF & odf.internal:
        self.fields_bucketed[odf.internal] = collections.OrderedDict()
        buckets += [odf.internal]
    if ODF & odf.related:
        self.fields_bucketed[odf.related] = collections.OrderedDict()
        buckets += [odf.related]
    if ODF & odf.properties:
        self.fields_bucketed[odf.properties] = collections.OrderedDict()
        buckets += [odf.properties]

    for bucket in buckets:
        passes = []
        if ODF & odf.flat:
            passes += [True]
        if ODF & odf.list:
            passes += [False]
        for Pass in passes:
            field_list = self.fields_flat[bucket] if Pass else self.fields_list[bucket]
            for name, value in field_list.items():
                self.fields_bucketed[bucket][name] = value
                self.fields[name] = value

    pass

def get_form_fields(model):
    '''
    Return a dictionary of fields in a model to be used in form construction and management.
     
    The dictonary is in keyed on the field name with the field as a value.
    
    This is the standard Django fields_for_model but forces inclusion
    of any fields specfied in the add_related attribute of a model and it's PK   
    '''
    # Now collect the fields we want to find the values of (fields_for_model does not return the pk field)
    fields = fields_for_model(model)        

    # fields_for_model doesn't return uneditable fields ...
    # if this model has an add_related attribute and it specifies any uneditable fields then
    # override this objection and add them to the fields list, else they won't be added to the
    # related_forms. You may want for example, to explicitly to add uneditable fields to related_forms 
    # so as to be able to edit them. The reasoning is as follows: editable=False means the field won't
    # appear on the standard form editor for that model, whereas add_related means that the field
    # is offered when it's related to a model so that we can build a custom form editor for that
    # field through its relation if we want. In short we have suppressed its appearance on standard
    # model forms but made it available on related custom built model forms.
    for f in add_related(model):
        if hasattr(model, f) and not f in fields:
            fields[f] = getattr(model, f)
            
    # always include the pk field
    fields[model._meta.pk.name] = getattr(model, model._meta.pk.name)
    
    return fields

def get_formset_from_request(Form_Set, form_data):
    '''
    Given a Form_Set class and data from a request builds a form_set with field_data from the request data 
    if it can and returns it.
    '''
    # A dictionary in  {name: value or list of values}
    field_data = {}
    
    model = Form_Set.model # FIXME: Test this! A guess for now. 
    
    # Get the form fields
    fields = get_form_fields(model)
    
    # Build the formset with the supplied data, which can then be cleaned - see full_clean() below.
    form_set = Form_Set(prefix=model.__name__, data=form_data)

    # If no management form is present will fail with a ValidationError
    # no field_datacan be built in this case
    try:
        has_management_form = hasattr(form_set, 'management_form')
    except ValidationError as e:
        if e.code == "missing_management_form":
            has_management_form = False                         

    # form_data is None for an empty add form, 
    # but is not None if the add form is be re-displayed with errors
    if has_management_form:
        # Clean each form in the the formset. 
        # This leaves cleaned_data in each form of the formset, 
        # which we can use to build field values
        # related_formset.full_clean() works as well, but stops cleaning forms after the first error
        for form in form_set.forms:
            form.full_clean()
        
        # FIXME: At this point we do have:
        #    related_formset.forms.cleaned_data
        # but we also have:
        #    related_formset._errors
        # which complains about "This field is required" for session!
        # At least it's not blocking at present but this needs to 
        # be considered somehow and handled well.

        for field_name in fields:
            field_data[field_name] = []                            
            for form in form_set.forms:
                if field_name in form.cleaned_data:
                    value = form.cleaned_data[field_name]
                    # If the cleaned_data value is a database object, then we only want it's PK in the field_data list.
                    if hasattr(value, 'pk'):
                        value = value.pk
                    field_data[field_name].append(value)
                else:
                    field_data[field_name].append(None)

        # Add the field data as an attribute of the form_set we return
        form_set.field_data = field_data
                                            
    return form_set

def get_formset_from_object(Form_Set, db_object, field):
    '''
    Given a Form_Set cass, a db_object and a field that is a relation, 
    builds a form_set from the db_object if it can and returns it.
    '''
    # A shorthand term
    rm = field.related_model
    
    # Get the form fields
    fields = get_form_fields(rm)

    # A dictionary in  {name: value or list of values}
    field_data = {}
    
    # QuerySet of related objects (used to build a management form), an empty queryset by default
    ros = rm.objects.none() 
    
    # If many objects are related to this one we'll build a list of values for each field_data entry
    if field.one_to_many or field.many_to_many:

        # Get the related objects
        ros = getattr(db_object, field.name).all()

        # Sorted returns a list, but ros must be a queryset for later use in creating the related_form
        # So keep ros untouched and build a sorted list separately
        # sorted_ros is just used here to populate the lists we insert into field_data in the order specified
        sorted_ros = apply_sort_by(ros)

        # For every field in the related objects we add to the (growing) list fo values either:
        #    a value, PK or list-of-PKs 
        # A value if this field has a simple value
        # A PK if the field is a foreign key to another object (then that remote objects PK)
        # A list of PKs if it is field that points to many remote objects (like a OneToMany or ManyToMany) 
        for field_name in fields:
            field_data[field_name] = []                            
            for ro in sorted_ros:
                field_value = getattr(ro,field_name)

                # If it's a single object from another model (it'll have a pk attibute) 
                if hasattr(field_value, 'pk'):
                    # Add the objects primary key to the list
                    field_data[field_name].append(field_value.pk)

                # If it's many objects from another model (it'll have a model attribute)
                elif hasattr(field_value, 'model'):
                    # Add a list of the objects primary keys to the list
                    roros = apply_sort_by(field_value.model.objects.filter(**field_value.core_filters))

                    roro_field_data = []

                    for roro in roros:
                        roro_field_data.append(roro.pk) # build a list of primary keys

                    field_data[field_name].append(roro_field_data)

                # If it's a scalar value
                else:
                    # Add the value to the list
                    field_data[field_name].append(field_value)

    elif field.many_to_one or field.one_to_one:

        # For the one related object unpack its fields into field_data
        if hasattr(db_object, field.attname):
            if getattr(db_object, field.attname) is None:
                field_value = None
            else:
                # Although we know there will be only one ro, we need ros to build related_formset below
                ros = rm.objects.filter(pk=getattr(db_object, field.attname))  # The related object
                ro = ros[0]                                                       # There will only be one

                # Store its remaining field values in field_data
                for field_name in fields:
                    # The value of the field in the related object
                    field_value = getattr(ro, field_name)

                    # If it's a single object from another model (it'll have a primary key field)
                    if hasattr(field_value, 'pk'):
                        # Add the objects primary key to the list
                        field_data[field_name] = field_value.pk

                    # If it's many objects from another model (it'll have a model field)
                    elif hasattr(field_value,"model"):
                        # Put a list of the related objects PKs into field_data
                        rros = field_value.model.objects.filter(**field_value.core_filters)
                        field_data[field_name] = []
                        for rro in rros:
                            field_data[field_name].append(rro.pk)       # build a list of primary keys

                    # For scalar values though we just record the value of the field in field_data
                    else:
                        field_data[field_name] = field_value
    
    # Build the related formset from the related objects (ros)                
    related_formset = Form_Set(prefix=rm.__name__, queryset=ros)
    
    # Add the field data as an attribute of the form_set we return
    related_formset.field_data = field_data
    
    return related_formset

def get_rich_object_from_forms(root_object, related_forms):
    # TODO: This is messy. Consider just building it directly from the form data recursively.
    #       This would mean replicating some of the object creation code in get_related_forms
    #       But we could savvily buuld objects from form data or db_data based on context
    #       eg, Rank from form, player from database.
    #
    #       Define rich object as the:
    #        Session
    #          Ranks
    #            Teams
    #            Players
    #          Performances
    #            Players
    #
    #        Can we infer this from the add_related attribiutes?
    #
    #        Food for thought.
    
    # TODO: How does this generalize toa  formset of sessions say?
    
    # TODO: If model_history is empty then in this model put an attritibute called
    #       complex_object or such which will be a tree of dictionaries of just the object 
    #       instances with the key being the model name, and the value being one or a list
    #       of objects of that model that are releated to the root model.
    #
    #       New ideas:
    #        rich_object
    #        root_object
    #        rich_clean
    #
    #       are these the names we want to go with?
    #
    #       This is akin to the preload concept that I need to explore too (for 
    #        performance enhancement.
    #
    #        The main goal is to have just object instances to walk during a clean to have
    #        and easy way to clean the whole complex_object.
    print_debug("Building rich object for {}".format(root_object._meta.model))

    rich_object = SimpleNamespace()
    rich_object.root = root_object

    print_debug("Added root: {}".format(str(root_object)))
    
    for model, form in related_forms.items():
        print_debug("Checking form: {}".format(str(model)))
        relation = SimpleNamespace()
        relation.objects = []
        setattr(rich_object, model, relation)
        for pk, iform in form.instance_forms.items():
            print_debug("Checking instance form: {}".format(str(pk)))
            relation.objects.append(iform.object)
            print_debug("Added instance: {}".format(str(iform.object)))
            for subrelation in iform:
                print_debug("Checking relation: {}".format(str(subrelation)))
                
        
    pass

def generic_related_form(form_set):
    '''
    Given a Django form_set creates a generic related form which basically an empty form
    with a management form and field_data added so that if it's passed into context received
    by a Django template javascript can be used to build a form_set from this related form.  
    '''
    related_form = form_set.empty_form
    related_form.management_form = form_set.management_form
    
    if hasattr(form_set, 'field_data'):
        related_form.field_data = form_set.field_data
       
    return related_form

#def proforma_objects():    

def get_related_forms(model, form_data=None, db_object=None, model_history=[]):
    '''
    Given a model and optionally a data source from a form or object
    will return all the related forms for that model, tracing relations
    specified in the models add_related property.
    
    if form_data or a db_object are specified will in that order of precedence 
    use them to populate field_data (see below) so that a form can initialise 
    forms with data.

    Returns a list of generic forms each of which is:
        a standard Django empty form for the related model
        a standard Django management form for the related model (just four hidden inputs that report the number of items in a formset really)
        a dictionary of field data, which has for each field a list of values one for each related object (each list is the same length, 1 item for each related object)

        The data source for field_data can be 
            form_data (typically a QueryDict from a request.POST or request.GET) or 
            a database object (being the instance of a Model)
        If no data source is specified, then only the empty and management forms are included, 
        the dictionary of field data is not.
        
    model_history is used to avoid infinite recursion. When calling itself pushes the model onto model_history, and 
    on entering checks if model is in model_history, bailing if so.
    '''    
    assert not model in model_history, "Model Error: You have defined a recursive set of model relations with the model.add_related attribute."
        
    print_debug("Starting get_related_forms({}), history={}".format(model, model_history))

    # A db_object if supplied must be an instance of the specified model     
    if not db_object is None:
        assert isinstance(db_object, model), "Coding Error: db_object must be an instance of the specified model"

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
            # At this point we have a model, and a list of relations (other models that relate to it)
            # For a given relation there with be one or more related objects. If the relation is of the
            # form ToOne there will be one related object. If the relation is of the form ToMany there will 
            # be many related objects. 
            #
            # For this relation we want a "related_form" which we'll provide as a empty_form
            # and if a data_source is provided, to that empty_form we want to add an attribute "field_data" 
            # which has for each field in the empty form a list of values for each instance.
            # For completeness we also add instance_forms to the empty form which is a dictionary of forms
            # keyed on the PK of the indivudal instances (that are listed in field_data) and the value
            # is a form for that instance (essentially the empty_form with values in the fields).
            #
            # The value in field_data might itself be a simple scalar (for ordinary fields), or a PK if 
            # the field is a _to_one relation (a relation pointing to one object of another model, or a list of
            # PKs if the field is a _to_many relation (a relation pointing to many objects in another model).  
            #
            # This is a proxy for a related_formset in a way. The related_form is an empty_form, a pro
            # forma for one form in the formset and field_data contains for each field in the related model a 
            # list of values, one for each form in the formset from which a web page can, in javascript, create
            # the individual forms in the formset with populated values. 
            #
            # To reiterate:
            #
            # There is one field_data for each related model, and it is dictionary which is keyed on the 
            # related model's field name(s). The value will depend on whether the relation is to one or many 
            # other objects (i.e. contain a value or a list). 
            #
            # The field in the related_model can itself be:
            #    a value    - in which case the item added to a field_data list is a value
            #    a relation to one related object - in which case the item added to a field_data list is a PK
            #    a relation to many related objects - in which case the item added to a field_data list is a list of PKs
            #
            # So field_data for a given field could be a list of lists all depending on the relationships.
            #
            # This is recursive, in that the related_form may also be given an atttribute "related_forms" which is
            # a dictionary of related forms in the self same manner for that related model. 
            # 
            # For added convenience, the fields in each related model are also included in field_data.
            # They are included as lists of values (one for each instance) with psuedo field names in form
            # model__field (using django's double underscore convention). This is complicated and a good
            # working example will be useful
            #
            # To include a relation it has to be identified in a model's add_related attribute.
            # Either this object has a field which is specified in its add_related list, or
            # The related model has a field which is specified in add_related (in the format "model.field")
            # The relation will have an atribute named "field" if it's a candidate for the latter. 
            # That "field" in the relation is the field in the related model which points to this one.
            #
            # Examples to elucidate:
            #
            # 1) If we have a Team model and object there is a related model Member which has a field 
            # named "team" which is a ForeignKey field pointing team, then this is many_to_one relationship 
            # (many Members per Team), then the Team model we should have an atttribute add_related = ['Member.team']
            # to request that we include the related form for Member. There is no field in Team for the relationship
            # for us to specify! But if the team field in Member has a related_name ('members' for example) a field of 
            # that name is created in Team and so we also can request the related form with  add_related = ['members'].
            # Both methods are supported here.
            #
            # 2) If on the other hand a Member can be in multiple Teams, then we have a many_to_many relationship. This
            # could be via a ManyToMany field in Team called "members", and if so to include the related form for Member
            # we would specify add_related = ['members'].
            #
            # In case 2) the name of the relation will be 'members' and this is what we can look for in add_related(model)
            # In case 1) the name of the relation will be the related_name that was specified for the team field in Member,
            # and the relation will have a field that is the field in Member that is pointing to Team. In this example
            # a field 'team' that points to Team and so Member.team is also a way to specify this related form if desired.
            
            if ( relation.name in add_related(model)
                or (hasattr(relation, "field") 
                and relation.field.model.__name__ + "." + relation.field.name in add_related(model)) ):
                
                # Build the class for the related formset. The related formset will be an instance of this class 
                Related_Formset = modelformset_factory(relation.related_model, can_delete=False, extra=0, fields=('__all__'), formfield_callback=custom_field_callback)
                related_formset = None # Will be built using either form_data or db_object as a data source 

                # By default, we have no management form. One comes into being if we succeed in
                # populating a formset with form_data or from a db_object.  
                has_management_form = False
                
                # ==============================================================
                # Build the related_formset and field_data for this relation
                
                # Try to use form_data if it's present (it may fail as the form_data may not include
                # a submission for the related model).Note success or failure in found_form_data so 
                # we can look at db_object for field values.
                found_form_data = False
                if not form_data is None:
                    related_formset = get_formset_from_request(Related_Formset, form_data)
                    if hasattr(related_formset, "field_data") and related_formset.field_data:
                        found_form_data = True

                # If no form data was found try and find it in the db_object
                if not found_form_data and not db_object is None:                    
                    related_formset = get_formset_from_object(Related_Formset, db_object, relation)

                # If no management form is present this will fail with a ValidationError
                # Catch this fact here quietly, for compatibility with the 'add' 
                # approach, and ease of saving it later (the management form that is)
                try:
                    has_management_form = hasattr(related_formset, 'management_form')
                except ValidationError as e:
                    if e.code == "missing_management_form":
                        has_management_form = False
                    
                # If we didn't succeed in building a formset from form_data ot a db_object just
                # build one from the model, for the empty_form including a management form,
                if not has_management_form:
                    related_formset = Related_Formset(prefix=relation.related_model.__name__)

                # Build the generic_related_form for this relation and save it
                related_forms[relation.related_model.__name__] = generic_related_form(related_formset)

    # Now check each of the related forms to see if any of them want to add related forms!
    # This could be dangerous if recursive. Relies on sensible configuration of the add_related model fields.
    # TODO: Perhaps keep a history as we recurse to detect loopback
    for rf in related_forms:
        rm = related_forms[rf].Meta.model
            
        print_debug("Processing {}: add_related={}".format(rm, add_related(rm)))
        
        # add generic related forms (with no object) to provide easy access to 
        # the related empty form and field widgets in the context. Instance forms
        # are added later for each related object. 
        related_forms[rf].related_forms = get_related_forms(rm, model_history=model_history+[model])
        
        # add instance_forms for each instance
        if hasattr(related_forms[rf], "field_data") and rm._meta.pk.attname in related_forms[rf].field_data:
            related_forms[rf].instance_forms = {}

            # Ordering is important here as field_data which are lists are in an order and should all be in the same order
            # So we need to observe and respect the order of pk values in field_data when creating instance lists of related values
            pk_list = []                   # Keep an ordered list of the PKs as the dictionary "instance_forms" loses order
            pk_attr = rm._meta.pk.attname  # Get the name of the primary key attribute

            # Create the instance_forms, that is one related_forms object per related instance  
            pk_placeholder = 0
            
            # To loop easily, we need a list of pks 
            # but it may be in field_data as a single pk not a list
            # so build a list if it's not a list.
            pks = related_forms[rf].field_data[pk_attr] if isinstance(related_forms[rf].field_data[pk_attr], list) else [related_forms[rf].field_data[pk_attr]] 
            for pk in pks:
                if pk is None:
                    ph = 'PK_{}'.format(pk_placeholder)
                    pk_placeholder += 1
                else:
                    ph = pk
                pk_list.append(ph)
                                
                print_debug("Processing {}: ph={}".format(rm, ph))
                        
                if not pk is None:
                    o = rm.objects.get(pk=pk)
                else:
                    i = len(pk_list)-1
                    fields = {}
                    for field, values in related_forms[rf].field_data.items():
                        f = rm._meta.get_field(field)
                        if values[i] is None:
                            val = None
                        elif f.is_relation:
                            m = f.related_model
                            if f.one_to_one or f.many_to_one:
                                val = m.objects.get(pk=values[i])
                            elif f.one_to_many or f.many_to_many:
                                # TODO: Test this, could fail, untested code!
                                val = m.objects.filter(pk__in=values[i]) 
                        else:
                            val = values[i]
                            
                        fields[field] = val
                        
                    o = rm(**fields)

                    print_debug("Processing {}: o={}".format(rm, o))
                     
                instance_forms = get_related_forms(rm, form_data=form_data, db_object=o, model_history=model_history+[model])
                instance_forms.object = o

                if not instance_forms is None:               
                    print_debug("Processing {}: Saving instance form for {}".format(rm, ph))
                    related_forms[rf].instance_forms[ph] = instance_forms
                        
        # For ease of use in the template context add field_data for all the instance related fields as well
        if hasattr(related_forms[rf],"instance_forms"):
            for pk in pk_list: # Walk the ordered list of PKs
                for form in related_forms[rf].instance_forms[pk]:
                    if hasattr(related_forms[rf].instance_forms[pk][form], "field_data"):
                        for ro_field in related_forms[rf].instance_forms[pk][form].field_data:
                            ro_field_name = form + "__" + ro_field
                            print_debug("Adding {}".format(ro_field_name))
                            ro_field_value = related_forms[rf].instance_forms[pk][form].field_data[ro_field]
                            if not ro_field_name in related_forms[rf].field_data:
                                related_forms[rf].field_data[ro_field_name] = []
                            related_forms[rf].field_data[ro_field_name].append(ro_field_value)

    print_debug("Done with get_related_forms({})".format(model))
    return related_forms            

def save_related_forms(self):

    #TODO: Implement this! 
    # Docs state: If your formset contains a ManyToManyField, you’ll also need to call formset.save_m2m() to ensure the many-to-many relationships are saved properly.
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
    
    # This code saves properly and can be used in interim.
    # TODO: Review how it fits in with cleaning
    # TODO: Does it handle recursion? forms related to related forms?
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
    
    return False # Return no errors

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
        
        if len(self.request.GET) > 0:
            context["get_params"] = self.request.GET
            if hasattr(self, 'filter'):
                context["query"] = self.filter

        # Check for related models and pass into the context either a related form or related view.
        # Only do this if the model asks us to do so via the add_related attribute.
        if self.operation in ["add", "edit"] and len(add_related(context["model"])) > 0:
            if hasattr(self.request, 'POST') and not self.request.POST is None and len(self.request.POST)>0:
                form_data = self.request.POST
            elif hasattr(self.request, 'GET') and not self.request.GET is None and len(self.request.GET)>0:
                form_data = self.request.GET
            else:
                form_data = None
            
            if hasattr(self, 'object') and isinstance(self.object, context['model']):
                db_object = self.object
            else:
                db_object = None
                  
            related_forms = get_related_forms(context["model"], form_data, db_object)
            context['related_forms'] = related_forms

        if self.operation in ["add", "edit"] and 'form' in context:
            fix_widgets(context['form'])
    else:
        raise ValueError("Internal Error: Views must be provided at least 'model' in kwargs and an 'operation' argument. One or the other was missing. This is a site design error relating to defined urlpatterns which failed to provide on or the other.")

    return context

