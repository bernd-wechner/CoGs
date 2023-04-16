#===============================================================================
# AJAX handlers
#
# For returning JSON data about objects, intended for use by client side
# JavaScript.
#
# The leaderboards ajax handler is in leaderboards.py as it is the most
# complicated specialist AJAX handler and he bulk of the leaaderboards view
# code.
#===============================================================================
import json

from django.urls import reverse
from django.http.response import HttpResponse

from .generic import view_List, view_Detail

from ..models import Game
from ..BGG import BGG


def ajax_List(request, model):
    '''
    Support AJAX rendering of lists of objects on the list view.

    To achieve this we instantiate a view_List and fetch its queryset then emit its html view.
    '''
    view = view_List()
    view.request = request
    view.kwargs = {'model':model}
    view.get_queryset()

    view_url = reverse("list", kwargs={"model":view.model.__name__})
    json_url = reverse("get_list_html", kwargs={"model":view.model.__name__})
    html = view.as_html()

    response = {'view_URL':view_url, 'json_URL':json_url, 'HTML':html}

    return HttpResponse(json.dumps(response))


def ajax_Detail(request, model, pk):
    '''
    Support AJAX rendering of objects on the detail view.

    To achieve this we instantiate a view_Detail and fetch the object then emit its html view.
    '''
    view = view_Detail()
    view.request = request
    view.kwargs = {'model':model, 'pk': pk}

    view.get_object()

    view_url = reverse("view", kwargs={"model":view.model.__name__, "pk": view.obj.pk})
    json_url = reverse("get_detail_html", kwargs={"model":view.model.__name__, "pk": view.obj.pk})
    html = view.as_html()

    response = {'view_URL':view_url, 'json_URL':json_url, 'HTML':html}

    # Add object browser details if available. Should be added by RichDetailView
    if hasattr(view, 'object_browser'):
        response['object_browser'] = view.object_browser

        if view.object_browser[0]:
            response['json_URL_prior'] = reverse("get_detail_html", kwargs={"model":view.model.__name__, "pk": view.object_browser[0]})
        else:
            response['json_URL_prior'] = response['json_URL']

        if view.object_browser[1]:
            response['json_URL_next'] = reverse("get_detail_html", kwargs={"model":view.model.__name__, "pk": view.object_browser[1]})
        else:
            response['json_URL_next'] = response['json_URL']

    return HttpResponse(json.dumps(response))


def ajax_Game_Properties(request, pk):
    '''
    A view that returns the basic game properties needed by the Session form to make sensible rendering decisions.
    '''
    game = Game.objects.get(pk=pk)

    props = {'individual_play': game.individual_play,
             'team_play': game.team_play,
             'scoring': Game.ScoringOptions(game.scoring).name,
             'min_players': game.min_players,
             'max_players': game.max_players,
             'min_players_per_team': game.min_players_per_team,
             'max_players_per_team': game.max_players_per_team
             }

    return HttpResponse(json.dumps(props))


def ajax_BGG_Game_Properties(request, pk):
    '''
    A view that returns basic game properties from BGG.

    This is needed because BGG don't support CORS. That means modern browsers cannot
    fetch data from their API in Javascript. And BGG don't seem to care or want to fix that:

    https://boardgamegeek.com/thread/2268761/cors-security-issue-using-xmlapi
    https://boardgamegeek.com/thread/1304818/cross-origin-resource-sharing-cors

    So we have to fetch the data from the CoGS server and supply it to the browser from
    the same origin. Given our API is using JSON not XML, we provide it in JSON to the
    browser.

    The main use case here is that the browser can request BGG data to poopulate form
    fields when submitting a new game. Use case:

    1. User enters a BGG ID
    2. User clicks a fetch button
    3. Form is poulated by data from BGG
    '''
    bgg = BGG(pk)
    return HttpResponse(json.dumps(bgg))
