'''
Django Generic View Extensions

Filterset extensions

django-url-filter is a great package that parses GET parameters into Django filter arguments. 

    http://django-url-filter.readthedocs.io/en/latest/

Alas it does not have a nice way to pretty print the filter for reporting it on views, 
nor for extracting the filter options cleanly for reconstructing a URL or QuerySet.
'''
# Django imports
from django.utils.safestring import mark_safe

operation_text = {
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
    # Date modifiers, probably not relevant in filters? If so may need some special handling.
    #         "date" : "__date",
    #         "year" : "__year",
    #         "quarter" : "__quarter",
    #         "month" : "__month",
    #         "day" : "__day",
    #         "week" : "__week",
    #         "week_day" : "__weekday",
    #         "time" : "__time",
    #         "hour" : "__hour",
    #         "minute" : "__minute",
    #         "second" : "__second",
    }    

def format_filterset(filterset, as_text=False):
    '''
    Returns a list of filter criteria that can be used in a URL construction 
    or if as_text is True a pretty formatted string version of same.
     
    :param filterset:   A filterset as produced by url_filter
    :param as_text:     Returns a list if False, or a formatted string if True 
    '''
        
    def get_field(components, component, model):
        '''
        Gets a field give the components of a filterset sepcification.  
        :param components: A list of components
        :param component:  An index into that list identifying the component to consider
        :param model:      The model in which the identified component is expected to be a field 
        '''
        def model_field(model, field_name):
            for field in model._meta.fields:
                if field.attname == field_name:
                    return field
            return None
        
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
            
        # local model field
        else:
            field = model_field(model, field_name)
        
        return field
    
    result = []

    try:
        # get_specs raises an Empty exception if there are no specs, and a ValidationError if a value is illegal  
        specs = filterset.get_specs()
        
        for spec in specs:
            field = get_field(spec.components, 0, filterset.queryset.model)
            if len(spec.components) > 1 and spec.lookup == "exact":
                Os = field.model.objects.filter(**{"{}__{}".format(field.attname, spec.lookup):spec.value})
                O = Os[0] if Os.count() > 0 else None
                
                if as_text:
                    if field.primary_key:
                        field_name = field.model._meta.object_name
                        field_value = str(O)
                    else:
                        field_name = "{} {}".format(field.model._meta.object_name, spec.components[-1])
                        field_value = spec.value
                else:
                    if field.primary_key:
                        field_name = "__".join(spec.components[:-1])
                        field_value = O.pk
                    else:
                        field_name = "__".join(spec.components)
                        field_value = spec.value
            else:
                field_name = field.verbose_name
                field_value = spec.value
            
            if as_text and spec.lookup in operation_text:
                op = operation_text[spec.lookup]
            elif spec.lookup != "exact":
                op = "__{}=".format(spec.lookup)
            else:
                op = "="
            
            result += ["{}{}{}".format(field_name, op, field_value)]

        if as_text:
            result = mark_safe(" <b>and</b> ".join(result))
            
        return result
    except:
        return "" if as_text else []
        