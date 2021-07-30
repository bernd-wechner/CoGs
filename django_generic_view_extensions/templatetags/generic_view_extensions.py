from os.path import splitext

from django import template
from django.template.loader_tags import do_include
from django.template.base import Token

register = template.Library()


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
        self.parser = parser
        self.token = token

    def render(self, context):
        try:
            words = self.token.split_contents()
            variant = context.get(self.token.contents.split()[1], self.token.contents.split()[1])

            path = context.template_name
            parts = splitext(path)
            words[1] = f"'{parts[0]}_{variant}{parts[1]}'"

            include = do_include(self.parser, Token(self.token.token_type, " ".join(words)))
            return include.render(context)
        except template.TemplateDoesNotExist:
            return ''
        except Exception as e:  # @UnusedVariable
            return f"INCLUDE ERROR: {e}"


@register.tag('include_variant')
def include_variant(parser, token):
    '''
    Include the specified variant on this template but only if it exists.

    :param parser:
    :param token:
    '''
    return IncludeVariant(parser, token)

