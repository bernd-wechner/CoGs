#===============================================================================
# A player viewer and summariser
#===============================================================================
import json, re

from django.shortcuts import render
from django.http.response import HttpResponse
from django.template.loader import render_to_string
from django.core.serializers.json import DjangoJSONEncoder

from dal import autocomplete

from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models.callbacks import CustomJS

from ..models import Player


def view_Players(request):
    return render(request, 'views/players.html', context=ajax_Players(request, as_context=True))


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
        players_table = render_to_string("include/players_table.html", context).strip()
        return HttpResponse(json.dumps((players_table), cls=DjangoJSONEncoder))
