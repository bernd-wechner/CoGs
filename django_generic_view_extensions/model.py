'''
Django Generic View Extensions

Model Extensions

One aim with these Extensions is to help concentrate model specific configurations in the model declaration.

Of particular note, we add support for a number of attributes that can be used in models to achieve certain outcomes.

add_related, is a way of listing relations without which this model makes no sense.
    
    for example: if you have a models Team and Member, the Team model may have: 
        add_related = 'members'
    assuming Team has a ManyToMany relationship with Member and an attribute "members".
    
    This would request of the CreateViewExtended and UpdateViewExtended that they provide enough form
    info to easily build rich forms (say a Team form, with a list of Member forms under it).
    
    Similarly the DetailViewExtended wants a rich object to display, as defined by the newteork of
    add_related links.     
    
sort_by, is like the Django Meta option "ordering" only it can include properties of the model.

link_internal and link_external, are two attributes (or properties) that can supply a URL (internal or external respectively)

    By internal we mean a link to the DetailView of the object (model instance) that supplies the link_internal.
    
    By external we mean a link to some other site if desired. For example you may have a model Person, and the 
    external link may point to their profile on Facebook or LinkedIn or wherever. We support only one external
    link conveniently for now.
    
__verbose_str_,
__rich_str__,
__detail_str__,    are properties like __str__ that permit a model to supply different degrees of detail.

    This is intended to support the .options and levels of detail in views.
    
    A convention is assumed in which:
    
    __str__             references only model fields (should be fast to provide), contain no HTML and ideally no 
                        newlines (if possible). 
                         
    __verbose_str__     can reference related model fields (can be a little slower), contain no HTML and ideally 
                        no newlines (if possible)
                        
    __rich_str__        like __verbose_str__, but can contain internal HTML markup for a richer presentation.
                        Should have a signature of:
                            def __rich_str__(self,  link=None):
                        and should call on field_render herein passing that link in.
    
    __detail_str__      like __richs_str__, but can span multiple lines.
                        Should have a signature of:
                            def __detail_str__(self,  link=None):
                        and should call on field_render herein passing that link in.
    
TODO: Add __table_str__ which returns a TR, and if an arg is specified or if it's a class method perhaps a header TR 
'''
# Python imports
import html, collections, inspect

# Django imports
from django.utils.safestring import mark_safe
from django.db import models

# Package imports
from . import FIELD_LINK_CLASS, NONE, NOT_SPECIFIED
from .util import isListType, isListValue, isDictionary, safetitle, time_str
from .options import default, flt, osf, odf
from .decorators import is_property_method
from .html import odm_str

summary_methods = ["__str__", "__verbose_str__", "__rich_str__", "__detail_str__"] 

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

def inherit_fields(model):
    '''
    Provides a safe way of testing a given model's inherit_fields attribute by ensuring always 
    a list is provided.
     
    If a model has an attribute named inherit_fields and it is a string that names
    
    1) a field in this model, or
    2) a field in another model in the format model.field
    
    or a list of such strings, then we take this as an instruction to inherit
    the values of those fields form form to form during one login session.
    
    The attribute may be missing, None, or invalid as well, and so to make testing
    easier throughout the generic form processors this function always returns a list,
    empty if no valid add_related is found.
    '''
    
    if not hasattr(model, "inherit_fields"):
        return []
    
    if isinstance(model.inherit_fields, str):
        return [model.inherit_fields]

    if isinstance(model.inherit_fields, list):
        return model.inherit_fields
     
    return [] 

def apply_sort_by(queryset):
    '''
    Sorts a query set by the the fields and properties listed in a sort_by attribute if it's specified.
    This augments the meta option order_by in models because that option cannot respect properties.
    This option though wants a sortable property to be specified and that isn't an object, has to be
    like an int or string or something, specifically a field in the object that is sortable. So usage
    is a tad different to order_by. 
    '''
    model = queryset.model
    if hasattr(model, 'sort_by'):
        try:        
            sort_lambda = "lambda obj: (obj." + ", obj.".join(model.sort_by) +")"
            return sorted(queryset, key=eval(sort_lambda))
        except Exception:
            return queryset
    else:
        return queryset

def link_target_url(obj, link_target=None):
    '''
    Given an object returns the url linking to that object as defined in the model methods.
    :param obj:            an object, being an instance of a Django model which has link methods
    :param link_target:    a field_link_target that selects which link method to use
    '''
    url = ""
    
    if link_target is None:
        link_target = default(flt)
    
    if link_target == flt.internal and hasattr(obj, "link_internal"):
        url = obj.link_internal
    elif link_target == flt.external and hasattr(obj, "link_external"):
        url = obj.link_external
    
    return url

def field_render(field, link_target=None, sum_format=None):
    '''
    Given a field attempts to render it as text to use in a view. Tries to do two things:
    
    1) Wrap it in an HTML Anchor tag if requested to. Choosing the appropriate URL to use as specified by link_target.
    2) Convert the field to text using a method selected by sum_format. 
     
    :param field: The contents of a field that we want to wrap in a link. This could be a text scalar value 
    or an object. If it's a scalar value we do no wrapping and just return it unchanged. If it's an object 
    we check and honor the specified link_target and sum_format as best possible. 
     
    :param link_target: a field_link_target which tells us what to link to. 
    The object must provide properties that return a URL for this purpose.
     
    :param sum_format: an object_summary_format which tells us which string representation to use. The 
    object should provide methods that return a string for each possible format, if not, there's a 
    fall back trickle down to the basic str() function.

    detail and rich summaries are expected to contain HTML code including links so they need to know the link_target 
    and cannot be wrapped in an Anchor tag and must be marked safe
    
    verbose and brief summaries are expected to be free of HTML so can be wrapped in an Anchor tag and don't
    need to be marked safe.
    '''
    if link_target is None:
        link_target = default(flt)
    
    if sum_format is None:
        sum_format = default(osf)
    
    tgt = None
    
    if link_target == flt.mailto:
        tgt = f"mailto:{field}" 
    elif isinstance(link_target, str) and link_target:
        tgt = link_target
    elif link_target == flt.internal and hasattr(field, "link_internal"):
        tgt = field.link_internal
    elif link_target == flt.external and hasattr(field, "link_external"):
        tgt = field.link_external

    fmt = sum_format
    txt = None        
    if fmt == osf.detail:
        if callable(getattr(field, '__detail_str__', None)):
            tgt = None
            txt = field.__detail_str__(link_target)
        else:
            fmt = osf.rich
        
    if fmt == osf.rich:
        if callable(getattr(field, '__rich_str__', None)):
            tgt = None
            txt = field.__rich_str__(link_target)
        else:
            fmt = osf.verbose
        
    if fmt == osf.verbose:
        if callable(getattr(field, '__verbose_str__', None)):
            txt = html.escape(field.__verbose_str__())
        else:
            fmt = osf.brief

    if fmt == osf.brief:
        if callable(getattr(field, '__str__', None)):
            txt = html.escape(field.__str__())
        else:
            if isinstance(field, models.DateTimeField):
                txt = time_str(field)
            else:
                txt = str(field)

    if fmt == osf.template:
        if hasattr(field, 'pk'):
            txt = f"{{{field._meta.model.__name__}.{field.pk}}}"
        else:
            txt = "{field_value}"            
            raise ValueError("Internal error, template format not supported for field.")

    if link_target == flt.template:
        tgt = "{{link.{}.{}.{}}}".format(FIELD_LINK_CLASS, field._meta.model.__name__, field.pk)
        return  mark_safe(u'{}{}{}'.format(tgt, txt, '{link_end}')) # Provides enough info for a template to build the link below.           
    elif tgt is None:
        return mark_safe(txt)
    else:
        return  mark_safe(u'<A href="{}" class="{}">{}</A>'.format(tgt, FIELD_LINK_CLASS, txt))            

def object_in_list_format(obj, context):
    '''
    For use in a template tag which can simply pass the object (from the context item object_list) 
    and context here and this will produce a string (marked safe as needed) for rendering respecting
    the requests that came in via the context. 
    :param obj:        an object, probably from the object_list in a context provided to a list view template 
    :param context:    the context provided to the view (from which we can extract the formatting requests)
    '''
    # we expect an instance list_display_format in the context element "format" 
    fmt = context['format'].elements
    flt = context['format'].link
    
    return field_render(obj, flt, fmt)

def collect_rich_object_fields(self):
    '''
    Passed a view instance (a detail view or delete view is expected, but any view could call this) 
    which has an object already (self.obj) (so after or in get_object), will define self.fields with 
    a dictionary of fields that a renderer can walk through later.
    
    Additionally self.fields_bucketed is a copy of self.fields in the buckets specified in object_display_format
    and self.fields_flat and self.fields_list also contain all the self.fields split into the scalar (flat) values
    and the list values respectively (which are ToMany relations to other models).
    
    Expects ManyToMany relationships to be set up bi-directionally, in both involved models, 
    i.e. makes no special effort to find the reverse relationships and if they are not set up 
    bi-directionally may miss the indirect, or reverse relationship).
    
    Converts foreign keys to the string representation of that related object using the level of
    detail specified self.format and respecting privacy settings where applicable (values are 
    obtained through odm_str where privacy constraints are checked. 
    '''
    # Build the list of fields 
    # fields_for_model includes ForeignKey and ManyToMany fields in the model definition

    # Fields are categorized as follows for convenience and layout and performance decisions
    #    flat or list  
    #    model, internal, related or properties
    #
    # By default we will populate self.fields only with flat model fields.
    
    def is_list(field):
        return hasattr(field,'is_relation') and field.is_relation and (field.one_to_many or field.many_to_many)
    
    def is_property(name):
        return isinstance(getattr(self.model, name), property)
    
    def is_bitfield(field):
        return type(field).__name__=="BitField"

    ODF = self.format.flags

    all_fields = self.obj._meta.get_fields()                    # All fields

    model_fields = collections.OrderedDict()                    # Editable fields in the model
    internal_fields = collections.OrderedDict()                 # Non-editable fields in the model
    related_fields = collections.OrderedDict()                  # Fields in other models related to this one
    
    # Categorize all fields into one of the three buckets above (model, internal, related)
    for field in all_fields:
        if (is_list(field) and ODF & odf.list) or (not is_list(field) and ODF & odf.flat):
            if field.is_relation:
                if ODF & odf.related:
                    related_fields[field.name] = field
            else: 
                if ODF & odf.model and field.editable and not field.auto_created:
                    model_fields[field.name] = field
                elif ODF & odf.internal:
                    internal_fields[field.name] = field

    # List properties, but respect the format request (list and flat selectors)  
    properties = []
    if ODF & odf.properties:
        for name in dir(self.model):
            if is_property(name):
                # Function annotations appear in Python 3.6. In 3.5 and earlier they aren't present.
                # Use the annotations provided on model properties to classify properties and include 
                # them based on the classification. The classification is for list and flat respecting 
                # the object_display_flags selected. That is all we need here.
                if hasattr(getattr(self.model,name).fget, "__annotations__"):
                    annotations = getattr(self.model,name).fget.__annotations__
                    if "return" in annotations:
                        return_type = annotations["return"]
                        if (isListType(return_type) and ODF & odf.list) or (not isListType(return_type) and ODF & odf.flat):
                            properties.append(name)
                    else:
                        properties.append(name)
                else:
                    properties.append(name)

    # List properties_methods, but respect the format request (list and flat selectors)  
    # Look for property_methods (those decorated with property_method and having defaults for all parameters)
    property_methods = []
    if ODF & odf.methods:
        for method in inspect.getmembers(self.obj, predicate=is_property_method):
            name = method[0]
            if hasattr(getattr(self.model,name), "__annotations__"):
                annotations = getattr(self.model,name).__annotations__
                if "return" in annotations:
                    return_type = annotations["return"]
                    if (isListType(return_type) and ODF & odf.list) or (not isListType(return_type) and ODF & odf.flat):
                        property_methods.append(name)
                else:
                    property_methods.append(name)

    # List summaries (these are always flat) 
    summaries = []
    if ODF & odf.summaries:
        for summary in summary_methods:
            if hasattr(self.model, summary) and callable(getattr(self.model, summary)):
                summaries.append(summary)

    # Define some (empty) buckets for all the fields so we can group them on 
    # display (by model, internal, related, property, scalars and lists)
    if ODF & odf.flat:
        self.fields_flat = {}                                       # Fields that have scalar values
        self.all_fields_flat = collections.OrderedDict()
        if ODF & odf.model:
            self.fields_flat[odf.model] = collections.OrderedDict()
        if ODF & odf.internal:
            self.fields_flat[odf.internal] = collections.OrderedDict()
        if ODF & odf.related:
            self.fields_flat[odf.related] = collections.OrderedDict()
        if ODF & odf.properties:
            self.fields_flat[odf.properties] = collections.OrderedDict()
        if ODF & odf.methods:
            self.fields_flat[odf.methods] = collections.OrderedDict()
        if ODF & odf.summaries:
            self.fields_flat[odf.summaries] = collections.OrderedDict()

    if ODF & odf.list:
        self.fields_list = {}                                       # Fields that are list items (have multiple values)
        self.all_fields_list = collections.OrderedDict()
        if ODF & odf.model:
            self.fields_list[odf.model] = collections.OrderedDict()
        if ODF & odf.internal:
            self.fields_list[odf.internal] = collections.OrderedDict()
        if ODF & odf.related:
            self.fields_list[odf.related] = collections.OrderedDict()
        if ODF & odf.properties:
            self.fields_list[odf.properties] = collections.OrderedDict()
        if ODF & odf.methods:
            self.fields_list[odf.methods] = collections.OrderedDict()
        if ODF & odf.summaries:
            self.fields_list[odf.summaries] = collections.OrderedDict()

    # For all fields we've collected set the value and label properly
    # Problem is that relationship fields are by default listed by primary keys (pk)
    # and we want to fetch the actual string representation of that reference an save 
    # that not the pk. The question is which string (see object_list_format() for the
    # types of string we support).
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
                    
                    field.is_list = True
                    field.label = safetitle(attname.replace('_', ' '))
        
                    ros = apply_sort_by(getattr(self.obj, attname).all())
        
                    if len(ros) > 0:
                        field.value = [odm_str(item, self.format.mode) for item in ros]
                    else:
                        field.value = NONE
        
                    self.fields_list[bucket][field.name] = field
            elif is_bitfield(field):
                if ODF & odf.flat:
                    flags = []
                    for f in field.flags:
                        bit = getattr(getattr(self.obj, field.name), f)
                        if bit.is_set:
                            flags.append(getattr(self.obj, field.name).get_label(f))
                    field.is_list = False
                    field.label = safetitle(field.verbose_name)
                    
                    if len(flags) > 0:
                        field.value = odm_str(", ".join(flags), self.format.mode)
                    else:
                        field.value = NONE
                                    
                    self.fields_flat[bucket][field.name] = field
            else:
                if ODF & odf.flat:
                    field.is_list = False
                    field.label = safetitle(field.verbose_name)
                    
                    field.value = odm_str(getattr(self.obj, field.name), self.format.mode)
                    if not str(field.value):
                        field.value = NOT_SPECIFIED
                        
                    self.fields_flat[bucket][field.name] = field

    # Capture all the property, property_method and summary values as needed (these are not fields)
    if ODF & odf.properties or ODF & odf.methods or ODF & odf.summaries:
        names = []
        if ODF & odf.properties:
            names += properties
        if ODF & odf.methods:
            names += property_methods
        if ODF & odf.summaries:
            names += summaries
            
        for name in names:
            label = safetitle(name.replace('_', ' '))
            
            # property_methods and summaries are functions, and properties are attributes
            # so we have to fetch their values appropriately 
            if name in property_methods:
                value = getattr(self.obj, name)()
                bucket = odf.methods
            elif name in summaries:
                value = getattr(self.obj, name)()
                bucket = odf.summaries
            else:
                value = getattr(self.obj, name)
                bucket = odf.properties
                
            if not str(value):
                value = NOT_SPECIFIED
    
            p = models.Field()
            p.label = label
    
            if isListValue(value):
                if ODF & odf.list:
                    p.is_list = True
                    
                    if len(value) == 0:
                        p.value = NONE
                    elif isDictionary(value):
                        # Value becomes Key: Value
                        p.value = ["{}: {}".format(odm_str(k, self.format.mode), odm_str(v, self.format.mode)) for k, v in dict.items(value)] 
                    else:
                        p.value = [odm_str(val, self.format.mode) for val in list(value)] 
                    self.fields_list[bucket][name] = p
            else:
                if ODF & odf.flat:
                    p.is_list = False
                    p.value = odm_str(value, self.format.mode, True) 
                    self.fields_flat[bucket][name] = p
        
    # Some more buckets to put the fields in so we can separate lists of fields on display
    self.fields = collections.OrderedDict()               # All fields
    self.fields_bucketed = collections.OrderedDict()

    buckets = []    
    if ODF & odf.summaries: # Put Summaries at top if they are requested
        self.fields_bucketed[odf.summaries] = collections.OrderedDict()
        buckets += [odf.summaries]
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
    if ODF & odf.methods:
        self.fields_bucketed[odf.methods] = collections.OrderedDict()
        buckets += [odf.methods]

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
