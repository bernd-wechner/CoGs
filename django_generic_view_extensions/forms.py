'''
Django Generic View Extensions

Form extensions

Specifically routines augmenting general form support.

The heavy work of supporitng related forms in rich objects is done
in related_forms. 
'''

def classify_widget(field):
    '''
    Sets the class of a field's widget to be the name of the widget's type, so that
    a template's styling or javascript can do things to all widgets of a given type. 
    '''
    field.widget.attrs["class"] =  type(field).__name__
    return field 

def classify_widgets(form):
    '''
    For each field in a form, will add the type name of the field as a CSS class 
    to the widget so that Javascript in the form can act on the field based on 
    class if needed.
    '''
    for field in form.fields.values():
        classify_widget(field)
    return form
