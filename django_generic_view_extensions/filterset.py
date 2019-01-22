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
    
    specs = filterset.get_specs()
    
    result = []
    
    for spec in specs:
        field = get_field(spec.components, 0, filterset.queryset.model)
        if len(spec.components) > 1 and spec.lookup == "exact":
            Os = field.model.objects.filter(**{"{}__{}".format(field.attname, spec.lookup):spec.value})
            O = Os[0] if Os.count() > 0 else None
            
            # TODO: Consider whether the premise here holds true. We have assumed that
            #       spec.components contains a list of items the last of which is not only
            #       a model field but its pk. This almost certainly isn't always true, to 
            #       which for example if we filter in ranks__player=n we end up with 
            #       spec.components=['rank','player','id'].
            #
            #       Thing is a filter on ranks__player__nickname is probably legal and will
            #       probably produce spec.components=['rank','player','name_nickname']
            #       in which case field_name assignments below break down, in both cases
            #       as_text and not.
            #
            #       For now I have parked this as I have to get the whole filter/ordering
            #       selection on list and detail views working first. Then can come back to
            #       look at this. 
            if as_text:
                field_name = field.model._meta.object_name
                field_value = str(O)
            else:
                field_name = "__".join(spec.components[:-1])
                field_value = O.pk
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
