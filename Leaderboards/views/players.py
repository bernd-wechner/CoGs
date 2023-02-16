#===============================================================================
# A player viewer and summariser
#===============================================================================
import json, re

from django.http.response import HttpResponse
from django.core.serializers.json import DjangoJSONEncoder

from django_rich_views.render import rich_render, rich_render_to_string

from dal import autocomplete

from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models.callbacks import CustomJS

from ..models import Player


def view_Players(request):
    return rich_render(request, 'views/players.html', context=ajax_Players(request, as_context=True))


def ajax_Players(request, as_context=False):
    '''

    '''
    player_stats = Player.stats()

    context = {"title": "Player Statistics",
               "players": player_stats
               }

    if as_context:
        return context
    else:
        players_table = rich_render_to_string("include/players_table.html", context).strip()
        return HttpResponse(json.dumps((players_table), cls=DjangoJSONEncoder))
