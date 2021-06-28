import re, json as JSON
from django import template

from django_generic_view_extensions.util import DjangoObjectJSONEncoder
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def to_name(value):
    return value.__name__


@register.filter
def json(value):
    return mark_safe(JSON.dumps(value, cls=DjangoObjectJSONEncoder))


@register.filter
def value(bound_field, value):
    """
    Takes a bound field and sets the value attribute on that field to the specified value.
    """
    if hasattr(bound_field, "field") and hasattr(bound_field.field, "widget"):
        bound_field.field.widget.attrs['value'] = value
    return bound_field


@register.filter
def index(indexable, i):
    return indexable[i]


@register.filter
def NoneToNull(value):
    """
    Replaces all "None" elements in a list with a null.
    Returns a list with the results.
    """

    def none_to_null(obj):
        """
        Returns an object untouched unless it is None then returns null
        """
        if obj is None:
            return "null"
        else:
            return str(obj)

    return "[" + ", ".join([none_to_null(obj) for obj in value]) + "]"


@register.filter
def ToArray(value):
    return list(value)


@register.filter
def QuoteValues(value):
    """
    Replaces all strings in a list with a quoted copy.
    Returns a list with the results.
    """

    def quote_values(obj):
        """
        Returns an object as a value in quotes
        """
        if isinstance(obj, list):
            return map(quote_values, obj)
        elif isinstance(obj, str):
            return '"' + obj + '"'
        elif obj is None:
            return "null"
        else:
            return str(obj)

    return "[" + ", ".join([quote_values(obj) for obj in value]) + "]"


@register.filter
def add_attributes(field, css):
    attrs = {}
    definition = css.split(',')

    for d in definition:
        if ':' not in d:
            attrs['class'] = d
        else:
            t, v = d.split(':')
            attrs[t] = v

    return field.as_widget(attrs=attrs)


@register.filter
def verbose(value):
    if hasattr(value, "__verbose_str__"):
        return value.__verbose_str__()
    else:
        return value.__str__()


@register.filter
def checked(value, compare=None):
    if compare is None:
        if value:
            return "checked"
        else:
            return ""
    else:
        if value == compare:
            return "checked"
        else:
            return ""


@register.filter
def fallback(value, fallback):
    if value:
        return value
    else:
        return fallback
