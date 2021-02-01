import re
from django import template
from django.template.loader_tags import do_include
from django.utils.safestring import mark_safe
from django_generic_view_extensions.model import object_in_list_format

register = template.Library()

@register.simple_tag(takes_context=True)
def list_format(context, obj):
    return object_in_list_format(obj, context) 


class TryInclude(template.Node):
    """
    A Node that instantiates an IncludeNode but wraps its render() in a
    try/except in case the template doesn't exist.
    
    For help on custom template tags: 
    https://docs.djangoproject.com/en/3.1/howto/custom-template-tags/#writing-the-compilation-function
    """
    def __init__(self, parser, token):
        self.include_node = do_include(parser, token)

    def render(self, context):
        try:
            return self.include_node.render(context)
        except template.TemplateDoesNotExist:
            return ''


@register.tag('try_include')
def try_include(parser, token):
    """
    Include the specified template but only if it exists.
    """
    return TryInclude(parser, token)

