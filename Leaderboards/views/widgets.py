#===============================================================================
# Widgets used by CoGS views
#===============================================================================
from dal import autocomplete

from django.urls import reverse_lazy
from django.forms.models import ModelChoiceIterator, ModelMultipleChoiceField


def html_selector(model, id, default=0, placeholder="", multi=False, attrs={}):  # @ReservedAssignment
    '''
    Returns an HTML string for a model selector.
    :param model:        The model to provide a selector widget for
    :param id:           The id of the widget
    :param default:      The default selection supplied (widget's initial condition)
    :param placeholder:  The text that forms the background of the empty widget
    :param attrs:        Any extra attributes to provide the widget with
    '''
    url = reverse_lazy('autocomplete_all', kwargs={"model": model.__name__, "field_name": model.selector_field})
    field = ModelMultipleChoiceField(model.objects.all())

    theme = "default"  # ""bootstrap"

    if multi:
        widget = autocomplete.ModelSelect2Multiple(url=url, attrs={**attrs, "class": "multi_selector", "id": id, "data-placeholder": placeholder, "data-theme": theme})
    else:
        widget = autocomplete.ModelSelect2(url=url, attrs={**attrs, "class": "selector", "id": id, "data-placeholder": placeholder, "data-theme": theme})

    widget.choices = ModelChoiceIterator(field)

    return widget.render(model.__name__, default)
