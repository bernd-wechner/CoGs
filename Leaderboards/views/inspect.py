#===============================================================================
# An object inspector
#===============================================================================
from django_rich_views.util import class_from_string
from django_rich_views.render import rich_render


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
    return rich_render(request, 'views/inspector.html', context=c)
