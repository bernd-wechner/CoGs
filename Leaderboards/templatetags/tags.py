import re
from django import template

register = template.Library()

@register.simple_tag(takes_context=True)
def list_format(context, value):
    format = context['object_list_format']
    if format == "rich":
        if hasattr(value, "__rich_str__"):
            return value.__rich_str__()
        elif hasattr(value, "__verbose_str__"):
            return value.__verbose_str__()
        else:
            return value.__str__()            
    elif format == "verbose":
        if hasattr(value, "__verbose_str__"):
            return value.__verbose_str__()
        else:
            return value.__str__()            
    else:
        return value.__str__()
