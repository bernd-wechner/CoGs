#===============================================================================
# Extended context providers for Django templates
#===============================================================================
import json

from dal import autocomplete

from .widgets import html_selector

from ..models import Game, League, ALL_LEAGUES


def html_league_options(session):
    '''
    Returns a simple string of HTML OPTION tags for use in a SELECT tag in a template
    '''
    leagues = League.objects.all()

    session_filter = session.get("filter", {})
    selected_league = int(session_filter.get("league", 0))

    options = ['<option value="0">Global</option>']  # Reserved ID for global (no league selected).
    for league in leagues:
        selected = " selected" if league.id == selected_league else ""
        options.append(f'<option value="{league.id}"{selected}>{league.name}</option>')
    return "\n".join(options)


def extra_context_provider(self, context={}):
    '''
    Returns a dictionary for extra_context with CoGs specific items

    Specifically The session form when editing existing sessions has a game already known,
    and this game has some key properties that the form wants to know about. Namely:

    individual_play: does this game permit individual play
    team_play: does this game support team play
    min_players: minimum number of players for this game
    max_players: maximum number of players for this game
    min_players_per_team: minimum number of players in a team in this game. Relevant only if team_play supported.
    max_players_per_team: maximum number of players in a team in this game. Relevant only if team_play supported.

    Clearly altering the game should trigger a reload of this metadata for the newly selected game.
    See ajax_Game_Properties below for that.

    Note: self.initial has been populated by the fields specfied in the models inherit_fields
    attribute by this stage, in the generic_form_extensions CreateViewExtended.get_initial()
    '''
    model = getattr(self, "model", None)
    model_name = model._meta.model_name if model else ""

    # Widgets
    context['dal_media'] = autocomplete.Select2().media
    context['league_options'] = html_league_options(self.request.session)  # For a standard select element
    context['league_widget'] = html_selector(League, "id_leagues_view", 0, ALL_LEAGUES)  # For a DAL element

    if model_name == 'session':
        # if an object is provided in self.object use that
        if hasattr(self, "object") and self.object and hasattr(self.object, "game") and self.object.game:
                game = self.object.game

        # Else use the forms initial game, but
        # self.form doesn't exist when we get here,
        # the form is provided in the context however
        elif 'form' in context and "game" in getattr(context['form'], 'initial', {}):
            game = context['form'].initial["game"]

            # initial["game"] could be a Game object or a PK
            if isinstance(game , int):
                try:
                    game = Game.objects.get(pk=game)
                except:
                    game = Game()
        else:
            game = Game()

        if game:
            context['game_individual_play'] = json.dumps(game.individual_play)  # Python True/False, JS true/false
            context['game_team_play'] = json.dumps(game.team_play)
            context['game_scoring'] = Game.ScoringOptions(game.scoring).name
            context['game_min_players'] = game.min_players
            context['game_max_players'] = game.max_players
            context['game_min_players_per_team'] = game.min_players_per_team
            context['game_max_players_per_team'] = game.max_players_per_team
        else:
            raise ValueError("Session form needs a game even if it's the default game")

    return context

