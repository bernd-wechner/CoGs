import re
from django import template
from django.utils.safestring import mark_safe
from django_generic_view_extensions import object_in_list_format

register = template.Library()

@register.simple_tag(takes_context=True)
def list_format(context, obj):
    return object_in_list_format(obj, context) 
    