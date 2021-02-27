import json, os

from django import template
from django.template.base import Token
from django.template.loader_tags import do_include

from django_generic_view_extensions.model import object_in_list_format
from django_generic_view_extensions.util import numeric_if_possible

register = template.Library()

@register.simple_tag(takes_context=True)
def list_format(context, obj):
    '''
    
    :param context:
    :param obj:
    '''
    return object_in_list_format(obj, context) 

@register.simple_tag()
def get_list(form_data, model, attribute):
    '''
    Given a form.data dictionary whichcontains formset data extract and return a list of the
    values of the attributes in the named model from the forms in that formset. This is used
    when a form with related_forms fails validation and bounces back, we need to pump the formset
    data back into the form, and if the formsets are constructed in Javascript they may like
    lists of values such as produced here.
    
    :param form_data:
    :param model:
    :param attribute:
    '''
    count = int(form_data.get(f"{model}-TOTAL_FORMS", 0))
    
    attr_list = []
    for i in range(count):
        key = f"{model}-{i}-{attribute}"
        val = form_data.get(key, None)
        val = numeric_if_possible(val)
        attr_list.append(val)
            
        #if not attr_list: breakpoint()
    return json.dumps(attr_list)

class IncludeVariant(template.Node):
    '''
    A Template Node that tries to include a template file named as a variant 
    of the file it's included in. That is if it's in a template named:
    
        form_data.html
    
    as:
    
        {% include_variant context_var %}
    
    it will try and include:
    
        form_data_context_var.html
    
    where context_var is a context variable.
    
    For help on custom template tags: 
    https://docs.djangoproject.com/en/3.1/howto/custom-template-tags/#writing-the-compilation-function
    '''
    def __init__(self, parser, token):
        self.parser  = parser
        self.token   = token

    def render(self, context):
        try:
            words = self.token.split_contents()
            variant = context.get(self.token.contents.split()[1], self.token.contents.split()[1])
            path    = context.template_name
            parts   = os.path.splitext(path)
            words[1] = f"'{parts[0]}_{variant}{parts[1]}'"
            self.token.contents = " ".join(words)
            include = do_include(self.parser, self.token)
            return include.render(context)
        except template.TemplateDoesNotExist:
            return ''


@register.tag('include_variant')
def include_variant(parser, token):
    '''
    Include the specified variant on this template but only if it exists.
    
    :param parser:
    :param token:
    '''
    return IncludeVariant(parser, token)

