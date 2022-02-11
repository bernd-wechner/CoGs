#===============================================================================
# An object inspector
#===============================================================================
from django.shortcuts import render
from django_generic_view_extensions.util import class_from_string


def view_Inspect(request, model, pk):
    '''
    A special debugging view which simply displays the inspector property of a given model
    object if it's implemented. Intended as a hook into quick inspection of rich objects
    that implement a neat HTML inspector property.
    '''
    m = class_from_string('Leaderboards', model)
    o = m.objects.get(pk=pk)

    result = getattr(o, "inspector", "{} has no 'inspector' property implemented.".format(model))
    c = {"title": "{} Inspector".format(model), "inspector": result}
    return render(request, 'views/inspector.html', context=c)
