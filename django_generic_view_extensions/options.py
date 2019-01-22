'''
Django Generic View Extensions

Options Support

The view extensions support a rich suite of options through which the views can be tweaked.

Herein we define a number of classes that act as enums and containers for options, and functions
for extracting them from a provided request object (for URL provision if desired).

The classes have long names and shortcut names provided as follows:

object_summary_format, osf    - selects which __<detail>_str__ method of an object should be used to summarise it.
list_menu_format, lsf         - selects the type of menu to put beside each object in a list view (view, edit, delete)
field_link_target, flt        - either internal or external links or none
object_display_flags, odf     - flags that configure the DetailView of an object, which types of field to show primarily
object_display_modes, odm     - richer configs for DetailView rendering (i.e. not flags)

And two aggregate format object are used:

list_display_format            - which contains all of the above used for defining the format of a ListView
object_display_format          - which contains all of the above used for defining the format of a DetailView
'''

# Python imports
import inspect

# A dictionary of default options. The name of the option and the default attribute.
# TODO: extend to detail views. For now just written for list views 
defaults = { 'object_summary_format': 'brief', 
             'list_menu_format': 'text',
             'field_link_target': 'internal',
             'object_display_flags': 'TODO',
             'object_display_modes': 'as_table',
             'index': False, 
             'key': False,
             'ordering': ''
            }

# The URL parameters that select the defaults above
# This has to tie in with the various get_ methods to follow
# The aim is to make this available in template context so that 
# a view that builds links can avoid putting default values on the URL
urldefaults = { 'object_summary_format': 'brief', 
             'list_menu_format': 'text_menus',
             'field_link_target': 'internal_links',
             'object_display_flags': 'TODO',
             'object_display_modes': 'as_table',
             'index': 'noindex',
             'key': 'nokey'
            }


def default(obj):
    '''
    A shorthand method for getting the default value of one of the option classes
    or if an option is not a class of the option itself.
    '''
    if inspect.isclass(obj):
        return getattr(obj, defaults[obj.__name__])
    elif isinstance(obj, str):
        return defaults[obj]

class object_summary_format():
    '''Format options for objects in the list view.

    4 levels of detail on a single line summary:
        brief   - Should be a minimalist view of the object as small as practical
        verbose - Intended to add some detail but should refer only to local model fields not related fields
        rich    - Intended to use all fields including related objects to build a rich summary, can include HTML
        table   - Same as Rich, but offered as TR element so that it can be used in a table construction (esp. in a ListView)
    
    1 multi-line rich HTML summary format:    
        detail  - A detailed view of the object like rich, only multi-line with HTML formatting
        
    1 AJAX related summary format:
        json - return a JSON summary of the object
    
    1 template related summary format:
        template - the object is rendered simply as "{model.pk}".
                   This is useful internally to exploit a wrapper like field_render
                   The idea is to reserve space in a surrounding string for 
    '''

    # Some formats for summarising objects 
    brief = 1       # Uses __str__ (should access only model local fields)
    verbose = 2     # Uses __verbose_str__ if available else __str__
    rich = 3        # Uses __rich_str__ if available else __verbose_str__ 
    detail = 4      # Uses __detail_str__ if available else __rich_str__
    # TODO: implement a table view which would produce a TR string, with elements in strings, and with a give arg return a header row.:
    # table = 5     # Uses __table_str__ if available else __detail_str__
    # TODO: implement a json format that asks a model to summarise itself in JSON format.
    # json = 6        # Uses __json_str__ if available, else nothing (specifically for AJAX requests)    
    template = 7    # Render the objects value as "{model.pk}" 
    
    #default = brief # The default to use

# A shorthand for the list format options
osf = object_summary_format

def get_object_summary_format(request):
    '''
    Standard means of extracting a object summary format from a request.
    '''
    OSF = default(object_summary_format)
    
    if 'brief' in request:
        OSF = osf.brief
    elif 'verbose' in request:
        OSF = osf.verbose
    elif 'rich' in request:
        OSF = osf.rich
    elif 'detail' in request:
        OSF = osf.detail
    
    return OSF

class list_menu_format():
    '''Format options for the object menu in the list view HTML formats.
    '''

    # TODO: implement text and buttons with CSS classes so that they can be
    #       formatted by style sheets 
    
    # Some formats for summarising objects
    none = 0        # No menu 
    text = 1        # A simple text format
    buttons = 2     # Using HTML buttons
    
    #default = text # The default to use

# A shorthand for the list format options
lmf = list_menu_format

def get_list_menu_format(request):
    '''
    Standard means of extracting a list menu format from a request.
    '''
    LMF = default(list_menu_format)
    
    if 'no_menus' in request:
        LMF = lmf.none
    elif 'text_menus' in request:
        LMF = lmf.text
    elif 'button_menus' in request:
        LMF = lmf.buttons
    
    return LMF

class field_link_target():
    '''
    Structured generic target selector for links from object fields in diverse views 
    (notably the detail view for objects)
    '''

    # Define some constants that identify modes
    none = 0        # Suppress links altogether
    internal = 1    # Render internal links - uses a models link_internal property which must be defined for this to render.
    external = 2    # Render external links - uses a models link_external property which must be defined for this to render.
    mailto = 3      # Render the field as a mailto link (i.e. assume field is an email address)
    template = 4    # Links to a template value rendered as {link_model_pk} for example {link_Player_23} 

# A shorthand for the field link targets
flt = field_link_target

def get_field_link_target(request):
    '''
    Standard means of extracting a field link target from a request.
    '''
    link = default(field_link_target)
    
    if 'no_links' in request:
        link = flt.none
    elif 'internal_links' in request:
        link = flt.internal
    elif 'external_links' in request:
        link = flt.external
    return link

class object_display_flags():
    '''Display flags for objects in the detail view.

    model - The standard model fields normally displayed by Django
    internal - the model fields Django won't normally display (primarily non-editable fields)
    related - The fields in other models that refer to this one via a relationship
    properties - The properties declared in the model (presented as pseudo-fields)

    _normal - The default
    _all_model - All model fields and properties
    _all - all of the categories
    '''

    # Format of fields, flat or list
    flat = 1            # scalar model fields
    list = 1 << 1       # list type model fields

    # The buckets that fields (and pseudo-fields in the case of properties) can fall into
    model = 1 << 2          # fields specified in model
    internal = 1 << 3       # fields Django adds to the model
    related = 1 << 4        # fields in other models that point here
    properties = 1 << 5     # properties calculated in the model
    methods = 1 << 6        # property_methods calculated in the model
    
    # Some general formatting flags
    separated = 1 << 7       # Separate the buckets above
    header = 1 << 8          # Put a header on the separators
    line = 1 << 9            # Draw a line separating buckets

    # Some shorthand formats
    _normal = separated | header | line | flat | model
    _all_model = _normal | list | internal | properties
    _all = _all_model | related
    
# A shorthand for the display format options
odf = object_display_flags

class object_display_modes():
    '''
    Structured modes for object display in the detail view
    
    We support the standard 3 from Django:
    
    as_table, as_ul and as_p
    
    and add two extensions
    
    as_br - which displays a single object as one paragraph with <br> separating fields.
    as_json - which is intended for AJAX use and will supply a dictionary of field values keyed on name in json format
    '''

    # Define some constants that identify modes
    as_table = 1        # Taken straight from the Django generic forms
    as_ul = 2           # Taken straight from the Django generic forms
    as_p = 3            # Taken straight from the Django generic forms
    as_br = 4           # New here, intended to wrap whole object in P with fields on new lines (BR separated)
    
    # TODO: Implement the JSON support 
    #as_json = 5         # New here, intended to return a given object as a JSON string for AJAX applications
    
    # Provide an accessible default
    #default = as_table
   
    # Define some mode containers for the object
    object = as_table               # How to render the object in a detail view
    list_values = as_ul             # How to render long field values when the object is displayed in a detail view

    # Define some mode containers for related objects
    sum_format = default(object_summary_format) # How to display the summary of related objects
    link = default(field_link_target)           # How to display links if any to related objects     
    
    # Define a threshold for short/long classification
    #
    # To be considered short (and win rights to on-line rendering):
    # A scalar value must contain no line breaks and not be longer than this
    # A list value when rendered as CSV must satisfy same constraint
    char_limit = 80                 # Scalars lower than this with no line breaks are considered short    
    
    # Define an indent to use where indents are need
    # Measured in chars, 
    # where needed will use the ch unit in HTML being the width of a 0 in the current font
    indent = 4                   
    
    # Define the width in chars of bucket separators
    line_width = 90                 # chars. How wide we should draw separator lines formed with em dashes. 
    
# A shorthand for the display format modes
odm = object_display_modes

class list_display_format():
    '''
    Display format options for objects in the list view.
    '''    
    complete = default(object_display_modes)    # Format for the whole list if relevant
    elements = default(object_summary_format)   # Format for the list elements 
    link = default(field_link_target)           # Whether to add links to the display and what kind
    menus = default(list_menu_format)           # Whether and how to display menus against each list item
    index = default('index')                    # A bool with request an index, counting 1, 2, 3, 4 down the list.
    key = default('key')                        # A bool with request the object's primary key to displayed
    ordering = default('ordering')              # The list of fields ot order by if any

def get_list_display_format(request):
    '''
    Standard means of extracting a list display format from a request.
    '''

    LDF = list_display_format()
    
    LDF.complete = get_object_display_format(request).mode.object
    LDF.elements = get_object_summary_format(request)    
    LDF.link = get_field_link_target(request)  # Technically already in LDF.complete.mode.link
    LDF.menus = get_list_menu_format(request)
    
    if 'index' in request:
        LDF.index = True
    elif 'noindex' in request:
        LDF.index = False
    else:
        LDF.index = list_display_format().index

    if 'key' in request:
        LDF.key = True
    elif 'nokey' in request:
        LDF.key = False
    else:
        LDF.key = list_display_format().key

    if 'ordering' in request:
        LDF.ordering = request['ordering']
             
    return LDF

class object_display_format():
    '''
    Display format options for objects in the detail view.
    '''

    flags = object_display_flags._normal
    mode = object_display_modes()
    ordering = default('ordering')           # The list of fields the associated list is ordered by (for the browser)

def get_object_display_format(request):
    '''
    Standard means of extracting a object display format from a request.
    '''
    ODF = object_display_format()
    
    # Now allow some shortcut turn offs
    if 'noall' in request or 'none' in request:
        ODF.flags &= ~odf._all
    elif "noall_model" in request or 'none_model' in request:
        ODF.flags &= ~odf._all_model
    elif "nonormal" in request or 'none_normal' in request:
        ODF.flags &= ~odf._normal
        
    # Now allow and turn ons
    if 'all' in request:
        ODF.flags = odf._all
    elif "all_model" in request:
        ODF.flags = odf._all_model
    elif "normal" in request:
        ODF.flags = odf._normal          

    # Then individual turn offs       
    if 'noflat' in request:
        ODF.flags &= ~odf.flat
    if 'nomodel' in request:
        ODF.flags &= ~odf.model
    if 'nolist' in request:
        ODF.flags &= ~odf.list
    if 'nointernal' in request:
        ODF.flags &= ~odf.internal
    if 'norelated' in request:
        ODF.flags &= ~odf.related
    if 'noproperties' in request:
        ODF.flags &= ~odf.properties    
    if 'nomethods' in request:
        ODF.flags &= ~odf.methods

    # And individual turn ons        
    if 'flat' in request:
        ODF.flags |= odf.flat
    if 'model' in request:
        ODF.flags |= odf.model
    if 'list' in request:
        ODF.flags |= odf.list
    if 'internal' in request:
        ODF.flags |= odf.internal
    if 'related' in request:
        ODF.flags |= odf.related
    if 'properties' in request:
        ODF.flags |= odf.properties
    if 'methods' in request:
        ODF.flags |= odf.methods

    # Separations and headers
    if 'noseparated' in request:
        ODF.flags &= ~odf.separated
    if 'noheader' in request:
        ODF.flags  &= ~odf.header
    if 'noline' in request:
        ODF.flags  &= ~odf.line

    if 'separated' in request:
        ODF.flags  |= odf.separated
    if 'header' in request:
        ODF.flags |= odf.header
    if 'line' in request:
        ODF.flags |= odf.line

    # Respect only one of the three HTML object formats
    if 'as_table' in request:
        ODF.mode.object = odm.as_table
    elif 'as_ul' in request:
        ODF.mode.object = odm.as_ul
    elif 'as_p' in request:
        ODF.mode.object = odm.as_p
    elif 'as_br' in request:
        ODF.mode.object = odm.as_br

    # Respect only one of the three HTML list value formats 
    if 'list_values_as_table' in request:
        ODF.mode.list_values = odm.as_table
    elif 'list_values_as_ul' in request:
        ODF.mode.list_values = odm.as_ul
    elif 'list_values_as_p' in request:
        ODF.mode.list_values = odm.as_p
    elif 'list_values_as_br' in request:
        ODF.mode.list_values = odm.as_br

    # We fetch the object summary format explicitly 
    # not via get_object_summary_format because we use 
    # a different request param when displaying objects 
    # (as compared with lists)
    if 'brief_sums' in request:
        ODF.mode.sum_format = osf.brief
    elif 'verbose_sums' in request:
        ODF.mode.sum_format = osf.verbose
    elif 'rich_sums' in request:
        ODF.mode.sum_format = osf.rich        
    elif 'detail_sums' in request:
        ODF.mode.sum_format = osf.detail        

    # Get the field link target from the request
    ODF.mode.link = get_field_link_target(request)

    if 'charlim' in request:
        ODF.mode.char_limit = int(request['charlim']) 

    if 'indent' in request:
        ODF.mode.indent = int(request['indent']) 

    if 'linewidth' in request:
        ODF.mode.line_width = int(request['linewidth']) 

    if 'ordering' in request:
        ODF.ordering = request['ordering']
                     
    return ODF

#===============================================================================
# Some helper PRE tag helper functions 
#===============================================================================
