'''
Django Rich Views

Form extensions

Specifically routines augmenting general form support.

The heavy work of supporitng related forms in rich objects is done
in related_forms.
'''
import re


def classify_widget(field):
    '''
    Sets the class of a field's widget to be the name of the widget's type, so that
    a template's styling or javascript can do things to all widgets of a given type.
    '''
    classes = re.split(r'\s+', field.widget.attrs.get("class", ""))
    add_classes = ["form_control", type(field).__name__]
    field.widget.attrs["class"] = " ".join(classes + add_classes).strip()
    return field


def classify_widgets(form):
    '''
    For each field in a form, will add the type name of the field as a CSS class
    to the widget so that Javascript in the form can act on the field based on
    class if needed.
    '''
    for field in form.fields.values():
        classify_widget(field)

    if hasattr(form, 'related_forms'):
        for related_form in form.related_forms.values():
            classify_widgets(related_form)

    return form
