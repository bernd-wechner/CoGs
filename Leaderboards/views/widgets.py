#===============================================================================
# Widgets used by CoGS views
#===============================================================================
from dal import autocomplete

from django.urls import reverse_lazy
from django.forms.models import ModelChoiceIterator, ModelMultipleChoiceField


def html_selector(model, id, default=0, placeholder="", attrs={}):  # @ReservedAssignment
    '''
    Returns an HTML string for a model selector.
    :param model:    The model to provide a selector widget for
    :param session:  The session dictionary (to look for League filters)
    '''
    url = reverse_lazy('autocomplete_all', kwargs={"model": model.__name__, "field_name": model.selector_field})
    field = ModelMultipleChoiceField(model.objects.all())

    widget = autocomplete.ModelSelect2Multiple(url=url, attrs={**attrs, "class": "multi_selector", "id": id, "data-placeholder": placeholder, "data-theme": "bootstrap"})
    widget.choices = ModelChoiceIterator(field)

    return widget.render(model.__name__, default)
