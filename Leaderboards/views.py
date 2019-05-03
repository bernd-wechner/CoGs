import re
from re import RegexFlag as ref # Specifically to avoid a PyDev Error in the IDE. 
import json
import pytz
import sys
import enum
import cProfile, pstats, io
from datetime import datetime, date, timedelta
#from collections import OrderedDict

from django_generic_view_extensions.views import LoginViewExtended, TemplateViewExtended, DetailViewExtended, DeleteViewExtended, CreateViewExtended, UpdateViewExtended, ListViewExtended
from django_generic_view_extensions.util import  datetime_format_python_to_PHP, class_from_string
from django_generic_view_extensions.options import  list_display_format, object_display_format
from django_generic_view_extensions.debug import print_debug 

from cuser.middleware import CuserMiddleware

from Leaderboards.models import Team, Player, Game, League, Location, Session, Rank, Performance, Rating, ALL_LEAGUES, ALL_PLAYERS, ALL_GAMES, NEVER

#from django import forms
from django.db.models import Count, Q
#from django.db.models.fields import DateField 
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.timezone import localtime, is_aware, make_aware, activate #, get_default_timezone, get_default_timezone_name, get_current_timezone, get_current_timezone_name, make_naive, 
from django.utils.formats import localize
from django.http import HttpResponse
#from django.http.response import HttpResponseRedirect
from django.urls import reverse, reverse_lazy #, resolve
from django.contrib.auth.models import User, Group
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.conf import settings
from django.forms.models import ModelChoiceIterator, ModelMultipleChoiceField

from dal import autocomplete

from numpy import rank

from .models import ALL_LEAGUES
from _collections import OrderedDict

#TODO: Add account security, and test it
#TODO: Once account security is in place a player will be in certain leagues, restrict some views to info related to those leagues.
#TODO: Add testing: https://docs.djangoproject.com/en/1.10/topics/testing/tools/

#===============================================================================
# Some support routines
#===============================================================================

def get_aware_datetime(date_str):
    ret = parse_datetime(date_str)
    if not is_aware(ret):
        ret = make_aware(ret)
    return ret

def is_registrar(user):
    return user.groups.filter(name='registrars').exists()

def fix_time_zone(dt):
    UTC = pytz.timezone('UTC')
    if not dt is None and dt.tzinfo == None:
        return UTC.localize(dt)
    else:
        return dt

#===============================================================================
# Form processing specific to CoGs
#===============================================================================

def updated_user_from_form(user, request):
    '''
    Updates a user object in the database (from the Django auth module) with information from the submitted form, specific to CoGs
    '''
    POST = request.POST
    registrars = Group.objects.get(name='registrars')

    user.username = POST['name_nickname']       # TODO: nicknames can have spaces, does the auth model support usernames with spaces? 
    user.first_name = POST['name_personal']
    user.last_name = POST['name_family']
    user.email = POST['email_address']
    user.is_staff = 'is_staff' in POST
    if 'is_registrar' in POST:
        if not is_registrar(user):
            user.groups.add(registrars)
    else:
        if is_registrar(user):
            registrars.user_set.remove(user)
    user.save

def clean_submitted_data(self):
    '''
    Do stuff before the model is saved
    '''
    model = self.model._meta.model_name

def pre_process_submitted_model(self):
    pass
    
def post_process_submitted_model(self):
    '''
    When a model form is posted, this function will perform model specific updates, based on the model 
    specified in the form (kwargs) as "model"
    
    It will be running inside a transaction and can bail with an IntegrityError if something goes wrong 
    achieving a rollback.
    
    This is executed inside a transaction as a callback from generic_view_extensions CreateViewExtended and UpdateViewExtended,
    so it can throw an Integrity Error to roll back the transaction. This is important if it is trying to update a number of 
    models at the same time that are all related. The integrity of relations after the save should be tested and if not passed,
    then throw an IntegrityError.   
    '''
    model = self.model._meta.model_name

    if model == 'player':
        pass # updated_user_from_form(...) # TODO: Need when saving users update the auth model too.
    elif model == 'session':
    # TODO: When saving sessions, need to do a confirmation step first, reporting the impacts.
    #       Editing a session will have to force recalculation of all the rating impacts of sessions
    #       all the participating players were in that were played after the edited session.
    #    A general are you sure? system for edits is worth implementing.
    
        session = self.object
                      
        team_play = session.team_play
        
        # TESTING NOTES: As Django performance is not 100% clear at this level from docs (we're pretty low)
        # Some empircal testing notes here:
        #
        # 1) Individual play mode submission: the session object here has session.ranks and session.performances populated
        #    This must have have happened when we saved the related forms by passing in an instance to the formset.save 
        #    method. Alas inlineformsets are attrociously documented. Might pay to check this understanding some day. 
        #    Empirclaly seems fine. It is in django_generic_view_extensions.forms.save_related_forms that this is done.
        #    For example:
        #
        #    session.performances.all()    QuerySet: <QuerySet [<Performance: Agnes>, <Performance: Aiden>]>
        #    session.ranks.all()           QuerySet: <QuerySet [<Rank: 1>, <Rank: 2>]>    
        #    session.teams                 OrderedDict: OrderedDict() 
        #
        # 2) team play mode submission: See similar results exemplified by:
        #    session.performances.all()    QuerySet: <QuerySet [<Performance: Agnes>, <Performance: Aiden>, <Performance: Ben>, <Performance: Benjamin>]>
        #    session.ranks.all()           QuerySet: <QuerySet [<Rank: 1>, <Rank: 2>]>    
        #    session.teams                 OrderedDict: OrderedDict([('1', None), ('2', None)]) 

        # TODO: Was in middle of testing saves with Book/Author test model. Where was I up to?

        # TODO: Consider and test under which circumstances Django has saved teams befor geettng here!
        #       And do we want to do anything special in the pre processor? And/or validator?
                     
        # manage teams properly, as we handl teams in a special way creating them
        # on the fly as needed and reusing where player sets match.
        if team_play:
            # Check if a team ID was submitted, then we have a place to start.
            # Get the player list for submitted teams and the name.
            # If the player list submitted doesn't match that recorded, ignore the team ID
            #    and look for a new one thathas those players!
            # If we can't find one, create new team with those players
            # If the name is not blank then update the team name. 
            #    As a safety ignore inadvertently submittted "Team n" names.

            # Work out the total number of players and initialise a TeamPlayers list (with one list per team)
            num_teams = int(self.request.POST["num_teams"])
            num_players = 0
            TeamPlayers = []
            for t in range(num_teams):
                num_team_players = int(self.request.POST["Team-{:d}-num_players".format(t)])
                num_players += num_team_players
                TeamPlayers.append([])

            # Populate the TeamPlayers record (i.e. work out which players are on the same team)
            player_pool = set()
            for p in range(num_players):
                player = int(self.request.POST["Performance-{:d}-player".format(p)])
                
                assert not player in player_pool, "Error: Players in session must be unique"
                player_pool.add(player)                
                
                team_num = int(self.request.POST["Performance-{:d}-team_num".format(p)])
                TeamPlayers[team_num].append(player)

            # For each team now, find it, create it , fix it as needed and associate it with the appropriate Rank just created
            for t in range(num_teams):
                # Get the submitted Team ID if any and if it is supplied 
                # fetch the team so we can provisionally use that (renaming it 
                # if a new name is specified).
                team_id = self.request.POST.get("Team-{:d}-id".format(t), None)
                team = None
                
                # Get Team players that we already extracted from the POST
                team_players_post = TeamPlayers[t]

                # Get the team players according to the database (if we have a team_id!
                team_players_db = []
                if (team_id):                                
                    try:
                        team = Team.objects.get(pk=team_id)
                        team_players_db = team.players.all().values_list('id', flat=True)
                    # If team_id arrives as non-int or the nominated team does not exist, 
                    # either way we have no team and team_id should have been None.
                    except (Team.DoesNotExist or ValueError):
                        team_id = None

                # Check that they are the same, if not, we'll have to create find or 
                # create a new team, i.e. ignore the submitted team (it could have no 
                # refrences left if that happens but we won't delete them simply because 
                # of that (an admin tool for finding and deleting unreferenced objects
                # is a better approach, be they teams or other objects).  
                force_new_team = len(team_players_db) > 0 and set(team_players_post) != set(team_players_db)
                
                # Get the approriate rank object for this team
                rank_id = self.request.POST.get("Rank-{:d}-id".format(t), None)
                rank_rank = self.request.POST.get("Rank-{:d}-rank".format(t), None)
                rank = session.ranks.get(rank=rank_rank)

                # A rank must have been saved before we got here, either with the POST
                # specified rank_id (for edit forms) or a ew ID (for add forms) 
                assert rank, "Save error: No Rank was saved with the rank {}".format(rank_rank)                                            

                # If a rank_id is specified in the POST it must match that saved by
                # django_generic_view_extensions.forms.save_related_forms
                # before we got here using that POST specified ID. 
                if (not rank_id is None):
                    assert int(rank_id)==rank.pk, "Save error: Saved Rank has different ID to submitted form Rank ID!"                                            

                # The name submitted for this team 
                new_name = self.request.POST.get("Team-{:d}-name".format(t), None)

                # Find the team object that has these specific players.
                # Filter by count first and filter by players one by one.
                # recall: these filters are lazy, we construct them here 
                # but the do not do anything, are just recorded, and when 
                # needed converted to SQL and executed. 
                teams = Team.objects.annotate(count=Count('players')).filter(count=len(team_players_post))
                for player in team_players_post:
                    teams = teams.filter(players=player)

                print_debug("Team Check: {} teams that have these players".format(len(teams)))

                # If not found, then create a team object with those players and 
                # link it to the rank object and save that.
                if len(teams) == 0 or force_new_team:
                    team = Team.objects.create()

                    for player_id in team_players_post:
                        player = Player.objects.get(id=player_id)
                        team.players.add(player)

                    if new_name and not re.match("^Team \d+$", new_name, ref.IGNORECASE):
                        team.name = new_name

                    team.save()
                    rank.team=team
                    rank.save()

                # If one is found, then link it to the approriate rank object and 
                # check its name against the submission (updating if need be)
                elif len(teams) == 1:
                    team = teams[0]

                    # If the name changed and is not a placeholder of form "Team n" save it.
                    if new_name and not re.match("^Team \d+$", new_name, ref.IGNORECASE) and new_name != team.name :
                        team.name = new_name
                        team.save()

                    # If the team is not linked to the rigth rank, fix the rank and save it. 
                    if (rank.team != team):
                        rank.team = team
                        rank.save()

                # Weirdness, we can't legally have more than one team with the same set of players in the database
                else:
                    raise ValueError("Database error: More than one team with same players in database.")
                
        # Individual play
        else:
            # Check that all the players are unique, and double up is going to cause issues and isn't 
            # really sesnible (same player coming in two different postions may well be allowe din some 
            # very odd game scenarios but we're not gonig to support that, can of worms and TrueSkill sure
            # as heck doesn't provide a meaningful result for such odd scenarios.
        
            player_pool = set()
            for player in session.players:
                assert not player in player_pool, "Error: Players in session must be unique"
                player_pool.add(player)
                
        # Enforce clean ranking. This MUST happen after Teams are processed above because
        # Team processing fetches ranks based on the POST submitted rank for the team. After 
        # we clean them that relationshop is lost. So we should clean the ranks as last 
        # thing just before calculating TrueSkill impacts.
        
        # First collect all the supplied ranks
        ranks = []
        for rank in session.ranks.all():
            ranks.append(rank.rank)
        # Then sort them by rank
        ranks = sorted(ranks)
        # Now check that they start at 1 and are contiguous
        ranks_good = ranks[0] == 1
        rank_previous = ranks[0]
        for rank in ranks:
            if rank - rank_previous > 1:
                ranks_good = False
            rank_previous = rank
            
        # if the ranks need fixing, fix them (to ensure they start at 1 and are contiguous):
        if not ranks_good:
            if rank[0] != 1:
                rank_obj = session.ranks.get(rank=rank)
                rank_obj.rank = 1
                rank_obj.save()
            
            rank_previous = 1
            for rank in ranks:
                if rank - rank_previous > 1:
                    rank_obj = session.ranks.get(rank=rank)
                    rank_obj.rank = rank_previous + 1
                    rank_obj.save()
                    rank_previous = rank_obj.rank                    
                else:
                    rank_previous = rank                         
       
        # TODO: Before we calculate TrueSkillImpacts we need to hgve a completely validated session!
        #       Any Ranks that come in, may have been repurposed from Indiv to Team or vice versa. 
        #       We need to clean these up. I think this means we just have to recaluclate the trueskill 
        #       impacts but also all subsequent ones involving any of these players if it's an edit!
        
        # Calculate and save the TrueSkill rating impacts to the Performance records
        session.calculate_trueskill_impacts()
        
        # Then update the ratings for all players of this game
        Rating.update(session)
        
        # Now check the integrity of the save. For a sessions, this means that:
        #
        # If it is a team_play session:
        #    The game supports team_play
        #    The ranks all record teams and not players
        #    There is one performance object for each player (accessed through Team).
        # If it is not team_play:
        #    The game supports individua_play
        #    The ranks all record players not teams
        #    There is one performance record for each player/rank
        # The before trueskill values are identical to the after trueskill values for each players 
        #     prior session on same game.
        # The rating for each player at this game has a playcount that is one higher than it was!
        # The rating has recorded the global trueskill settings and the Game trueskill settings reliably.
        #
        # TODO: Do these checks. Then do test of the transaction rollback and error catch by 
        #       simulating an integrity error.  

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

def html_selector(model, id, default=0, placeholder="", attrs={}):
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

def extra_context_provider(self):
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
    context = {}
    model = getattr(self, "model", None)
    model_name = model._meta.model_name if model else ""
     
    context['league_options'] = html_league_options(self.request.session)
    context['league_widget'] = html_selector(League, "id_leagues_view", 0, ALL_LEAGUES)
    
    if model_name == 'session':
        if "game" in getattr(self, 'initial', {}):
            Default = self.initial["game"]
        else:
            Default = Game()
        
        context['game_individual_play'] = json.dumps(Default.individual_play)
        context['game_team_play'] = json.dumps(Default.team_play)
        context['game_min_players'] = Default.min_players
        context['game_max_players'] = Default.max_players
        context['game_min_players_per_team'] = Default.min_players_per_team
        context['game_max_players_per_team'] = Default.max_players_per_team
        
        # Object overrides the defaults above 
        if hasattr(self, "object"):
            session = self.object
                    
            if session:
                game = session.game
                if game:
                    context['game_individual_play'] = json.dumps(game.individual_play) # Python True/False, JS true/false 
                    context['game_team_play'] = json.dumps(game.team_play)
                    context['game_min_players'] = game.min_players
                    context['game_max_players'] = game.max_players
                    context['game_min_players_per_team'] = game.min_players_per_team
                    context['game_max_players_per_team'] = game.max_players_per_team
    
    return context

def save_league_filters(session, league):
    # We prioritise leagues over league as players have both the leagues they are in
    # and their preferred league, and our filter should match any league they are in
    # Some models only provide league through a relation and hence we need to list 
    # those. Specifically:
    #     Teams through players
    #     Ratings through player
    #     Ranks and Performances through session

    # Set the name of the filter
    F = "league"

    # Set the priority list of fields for this filter
    P = ["leagues", "league", "session__league", "player__leagues", "players__leagues"] 
    
    if "filter" in session:
        if league == 0:
            if F in session["filter"]:
                del session["filter"][F]
        else:
            session["filter"][F] = league 
    else: 
        if league != 0:
            session["filter"] = { F: league }
                
    if len(session["filter"]) == 0:
        del session["filter"]  
    
    if "filter_priorities" in session:
        if league == 0:
            del session["filter_priorities"][F]
        else:
            session["filter_priorities"][F] = P
    else:
        if league != 0:
            session["filter_priorities"] = { F: P }

    if len(session["filter_priorities"]) == 0:
        del session["filter_priorities"]  

    session.save()            

#===============================================================================
# Customize Generic Views for CoGs
#===============================================================================
# TODO: Test that this does validation and what it does on submission errors

class view_Home(TemplateViewExtended):
    template_name = 'CoGs/view_home.html'
    extra_context_provider = extra_context_provider    

class view_Login(LoginViewExtended):
    
    # On Login add a filter to the session for the preferred league
    def form_valid(self, form):
        response = super().form_valid(form)
        
        username = self.request.POST["username"]
        try:
            user = User.objects.get(username=username)
            preferred_league = user.player.league
            
            if preferred_league:
                save_league_filters(form.request.session, preferred_league.pk)
                    
        except user.DoesNotExist:
            pass
        
        return response
                          
class view_Add(LoginRequiredMixin, CreateViewExtended):
    # TODO: Should be atomic with an integrity check on all session, rank, performance, team, player relations.
    template_name = 'CoGs/form_data.html'
    operation = 'add'
    #fields = '__all__'
    extra_context_provider = extra_context_provider
    #pre_processor = clean_submitted_data
    pre_processor = pre_process_submitted_model
    post_processor = post_process_submitted_model

# TODO: Test that this does validation and what it does on submission errors

class view_Edit(LoginRequiredMixin, UpdateViewExtended):
    # TODO: Must be atomic and in such a way that it tests if changes haveintegrity.
    #       notably if a session changes from indiv to team mode say or vice versa,
    #       there is a notable impact on rank objects that could go wrong and we should
    #       check integrity. 
    #       Throw:
    #        https://docs.djangoproject.com/en/1.10/ref/exceptions/#django.db.IntegrityError
    #       if an integrity error is found in such a transaction (or any transaction).
    template_name = 'CoGs/form_data.html'
    operation = 'edit'
    extra_context_provider = extra_context_provider
    #pre_processor = clean_submitted_data
    pre_processor = pre_process_submitted_model
    post_processor = post_process_submitted_model

class view_Delete(LoginRequiredMixin, DeleteViewExtended):
    # TODO: Should be atomic for sesssions as a session delete needs us to delete session, ranks and performances
    # TODO: When deleting a session need to check for ratings that refer to it as last_play or last_win
    #        and fix the reference or delete the rating.
    template_name = 'CoGs/delete_data.html'
    operation = 'delete'
    format = object_display_format()
    extra_context_provider = extra_context_provider

class view_List(ListViewExtended):
    template_name = 'CoGs/list_data.html'
    operation = 'list'
    format = list_display_format()
    extra_context_provider = extra_context_provider

class view_Detail(DetailViewExtended):
    template_name = 'CoGs/view_data.html'
    operation = 'view'
    format = object_display_format()
    extra_context_provider = extra_context_provider

#===============================================================================
# The Leaderboards view. What it's all about!
#===============================================================================

# Define defaults for the view inputs 

class leaderboard_options:
    '''
    Captures the options that can be made available to and be submitted by a web page when
    requesting leaderboards. 
    
    Three key parts in the class:
    
    1) Some enum defintions for selectable options. Defined as lists of 2-tuples. 
        The lists and the enums built fromt hem are useful in code and the 
        context of a Leaderboards page (the lists of 2 tuples for example can
        be used to construct select widgets).
        
        These are CamelCased  
        
    2) The options themselves. They ar elower case words _ seaprated.
    
    3) Methods:
    
        A constructor that can receives a QueryDcit from requst.GET or reuqest.POST
        and build an instance on basis of what is submitted. A default instance if 
        none is supplied.
        
        A JSONifier to supply context with a dict of JSONified options so the options
        can conveniently be used in a template.
    '''
    
    # Some useful enums to use in the options. Really just a way of encapsulating related 
    # types so we can use them in templates to pupulate selectors and receive them from 
    # requests in an orderly way.
    #
    # They are defined as lists of 2-tuples. The first value in each tuple is the name
    # of the enum and typically the value that is used in URLs and in GET and POST 
    # submissions. The second value is the plain text label that can be used on selector
    # on a web page if needed, a more verbose explanation of the selection.    
    NameSelections = OrderedDict((("nick", "nickname"),
                                  ("full", "full name"),
                                  ("complete", "full name (nickname)")))
    
    LinkSelections = OrderedDict((("none", "nowhere"),
                                  ("CoGs", "CoGs Leaderboard Space"),
                                  ("BGG", "boardgamegeek.com")))
    
    # We make enums out of the lists of the lists of 2-tuples above for use in code.       
    NameSelection             = enum.Enum("NameSelection", NameSelections)
    LinkSelection             = enum.Enum("LinkSelection", LinkSelections)

    # Some sets of options categorize with the main aim that we establish which ones
    # are cache safe and which ones not and also have a record of the incoming options 
    # swe wish to support and recognize.
    #
    # Note: many but not all options are attributes of this class. Some, notably the any/all
    #       options that describe how a list should be handled are not. The list is an attribute,
    #       but the 'enabled' attribute captures the option itself.  
    #
    # These options are what we can expect in requests (on URLs via GET requests or in a POST
    # request if supplied to the constructor. 
    
    # Options that we accept that will filter the list of games presented 
    # (i.e. define the subset of all games to return) 
    game_filters = {'games', 
                    'num_games', 
                    'game_leagues_any', 
                    'game_leagues_all', 
                    'game_players_any', 
                    'game_players_all', 
                    'changed_since', 
                    'num_days'}
    
    # Options that we accept that will filter the list of players presented on leaderboards 
    # (i.e. define the subset of all players that have played that game) 
    player_filters = {'players', 
                      'num_players_top', 
                      'num_players_above', 
                      'num_players_below', 
                      'min_plays', 
                      'played_since', 
                      'player_leagues_any', 
                      'player_leagues_all'}
    
    # Options that affect the perspective of a leadeboard view.
    # Really only one, what the effective "now" or "current" view is,
    # that we are looking from. 
    perspective_options = {'as_at'}
    
    # Options that influence evolution presentations. These will be historic 
    # leaderboards that show how a given leaderboard got to where it is, after 
    # each game session recorded for that game which saw a change to the boards.
    evolution_options = {'compare_with', 'compare_back_to'}
    
    # Options that affect how we render leaderboards on screen
    formatting_options = {'highlight_players', 'highlight_changes', 'highlight_selected', 'names', 'links'}
    
    # Options influencing what ancillary or extra information we present with a leaderboard
    info_options = {'details', 'analysis_pre', 'analysis_post'}
    
    # Options impacting the layout of leaderboards on the screen/page
    layout_options = {'cols'}
    
    # ALL the options, a set against whcih we can filter incoming requests to 
    # weed out all the things that don't matter, or to asses if the request is in
    # fact one that includes any leaderboard options or not.
    all_options = game_filters \
                | player_filters \
                | perspective_options \
                | evolution_options \
                | formatting_options \
                | info_options \
                | layout_options

    # leaderboards can take a little while to collate, particulalry over large number sof games
    # it's very noticeable. We waht to cache the boards once created and then differenticate 
    # between options that can be implemeted using an exisitng cache, and those that cannot,
    # that will require the cache be updated in some way.                
    cache_safe_options = player_filters | formatting_options | info_options | layout_options
    cache_affecting_options = all_options - cache_safe_options 
    
    # An option enabler. We want options to have sensible defaults to 
    # populate form fields, but aside from their default values the notion
    # of enabling or disabling the option should be presented on a form 
    # (checkboxes and raduo buttons) and represented here so that the form
    # can initialise those and also the processor knows which of the options 
    # to apply.
    #
    # it is just a set of options, by name, that are enabled, and 
    # anything not in list is not enabled.
    #
    # This only applies to the game selectors, the player selectors
    # and the perspective and evolution options. 
    #
    # The formatting,extra info, and layout options are not enabled 
    # or disabled,they simply are (always in force).
    enabled = {"game_leagues_any", "num_games", "player_leagues_any", "num_players_top"}
    
    # Because not all options require enabling, only some/many
    # we ckeep a set of enabbleable options internally, which
    # the constructor populates, and the method is_enabled() uses
    # intelligently (to return True always for option that don't
    # need enabling and only if enabled for those that do, which 
    # makes checking whether an option is to be applied easy.
    __needs_enabling__ = set()
           
    # Now we defione the attributes that back these options up.
    # NOTE: These attributes are not self-standing so to speak but  
    #       relate to 'enabled' as well, which turns thes on or off  
    #       and/or describes how they are to be used (in the case of  
    #       any/all list imperatives. 
        
    # Options that determine which games to list leaderboards for
    # These defaults are used to populate input elements in a form
    # The form should only resybmit them however if they are selected
    # by an accompanying check box.
    games = []                  # Restrict to specified Games
    num_games = 5               # List only this many games (most popular ones)   
    game_leagues = []           # Restrict to games played by specified Leagues
    game_players = []           # Restrict to games played by specified players
    changed_since = None        # Show only leaderboards that changed since this date
    num_days = 1                # List only games played in the last num_days_gs long session (also used for snapshot defintion) 

    # Options that determing which players are listed in the leadrboards
    # These options, like the game selectors, above provide defaults with which to 
    # populate input elements in a form, but they should be presented with accompanying 
    # checkboxes to select them, and if not selected the option should not be subitted.
    players = []                # A list of players to explicitly display (hide all others - except those, that other options request displayed as well)
    num_players_top = 10        # The number of players at the top of leaderboard to show
    num_players_above = 2       # The number of players above selected players to show on leaderboards
    num_players_below = 2       # The number of players below selected players to show on leaderboards
    min_plays = 2               # The minimum number of times a player has to have played this game to be listed
    played_since = None         # The date since which a player needs to have played this game to be listed
    player_leagues = []         # Restrict to players in specified Leagues

    # A perspective option that asks us to think of "current" not as at now, but as at some other time.
    as_at = None                # Do everything as if it were this time now (pretend it is now as_at)

    # Options that determine which snapshots to present for each selected game (above)
    # A snapshot being the leaderboard immediately after a given session.
    # Only one of these can be respected at a time,    
    # compare_back_to is special, it can take one two types of valu:
    #    a) a datetime, in which case it encodes a datetime back to which we'd like to have snapshots
    #    b) an integer, in which case  it encoudes num_days above basically, the length of the last session loking back from as_at which is used to determine a date_time for the query.
    compare_with = 1            # Compare with this many historic leaderboards
    compare_back_to = None      # Compare all leaderboards back to this date (and the leaderboard that was the latest one then)

    # NOTE: The reamining options are not enabled or disabled they always have a value
    #       i.e. are self enabling. 

    # Options for formatting the contents of a given leaderbaords 
    highlight_players = True    # Highlight the players that played the last session of this game (the one that produced this leaderboard)
    highlight_changes = True    # Highlight changes between historic snapshots
    highlight_selected = True   # Highlight players selected in game_players above

    names = NameSelection.complete.name # Render player names like this
    links = LinkSelection.CoGs.name     # Link games and players to this target

    # Options to include extra info in a leaderboard header
    details = False             # Show session details atop each boards (about the session that produced that board)
    analysis_pre = False        # Show the TrueSkill Pre-session analysis 
    analysis_post = False       # Show the TrueSkill Post-session analysis

    # Options for laying out leaderboards on screen 
    cols = 4                    # Display boards in this many columns (ignored when comparing with historic boards)
    
    # NOT YET IMPLEMENTED
    # Consider: could be a list of players, could be a bool like hightlight_players
    # and use the players list.
    trace = []                  # A list of players to draw trace arrows for from snapshot to snapshot
    
    def is_enabled(self, option):
        '''
        A convenient method to check if an option should be applied, returning True 
        for those that always apply and the enabled status for those that need enabling.
        '''
        return option in self.enabled if option in self.__needs_enabling__ else True
    
    def __enable__(self, option, true_false):
        '''
        An internal method for conveniently enabling or disabling and option based a supplied boolean,
        an operation we do over and over for many options.
        '''
        # Enable or disable the option as requested by true_false
        if true_false:
            self.enabled.add(option)
        else:
            self.enabled.discard(option)
        
    def __init__(self, session={}, request={}):
        '''
        Build a leaderboard options instance populated with options froma request dictionary
        (could be from request.GET or request.POST). If none is specified build with default 
        values, i.e.e do nothing here (defaults are specified in attribute declaratons above) 
        
        :param session: a request.session.filter dictionary that spectified the session default.
                        currently only 'league' is used to populate the options with a default
                        league filter based on session preferences. Is extensible.
                        
        :param request: a request.GET or request.POST dictionary that contains options.
        '''

        def decodeDateTime(dt):
            '''
            decodes a DateTime that was URL encoded. 
            Has to agree with the URL encoding chosen by the Javascript that 
            fetches leaderboards though an AJAX call of course.
            
            The colons are encoded as : - Works on Chrome even though it's 
            a reserved character not encouraged for URL use. 
            
            The space between date and time is encoded as + and so arrives
            as a space. 
            
            A - introducing the timezone passes through unencoded.
            
            A + introducing the timezone arrives here as a space
            
            Just in case : in the URL does cause an issue, up front we'll
            support - which travels undamaged from URL to here, as the 
            hh mm ss separator.
            
            All the while we are using the ISO 8601 format for datetimes,
            or encoded versions of it that we try to decode here.
            
            ref1 and ref 2 are ISO 8601 datetimes with and without timezone
            used do our work here.                         
            '''
            ref1 = "2019-03-01 18:56:16+1100"
            ref2 = "2019-03-01 18:56:16"
            
            # strigs are immutable and we need to listify them to 
            # make character referenced substitutions
            new = list(dt)
            
            if not (len(dt) == len(ref1) or len(dt) == len(ref2)):
                return dt
            
            if len(dt) == len(ref1):
                if dt[-5] == " ":
                    new[-5] = "+"

            if dt[13] == "-":
                new[13] = ":"

            if dt[16] == "-":
                new[16] = ":"

            # The n stringify the list again. 
            return "".join(new)

        # If we have a options submitted then don't use the default 
        # enabled list respect the incoming options instead.
        have_options = False
        for item in request: 
            if item in self.all_options:
                have_options = True 
                break
            
        if have_options:
            self.enabled = set()

        # Keeping the same order as the properties above and recommended for
        # form fields and the JS processor of those field ...
        
        # We start with the Game Selection criteria/filters, namely the
        # the options that determine which games we will present boards 
        # for. Each board being a list of players in order with their
        # rankings.

        # A comma separated list of games if submitted flags a request
        # to show leaderboards for those games only.
        self.__needs_enabling__.add('games')          
        if 'games' in request:        
            games = request['games'].split(",")  

            # Validate the games discarding any invalid ones
            self.games = []
            for game in games:
                if Game.objects.all().filter(pk=game).exists():
                    self.games.append(game)
            
            self.__enable__('games', self.games)

        # A number of games if submitted request that we list no
        # more than that many games (the top games when sorted by
        # some measure of popularity - ideally within the selected 
        # leagues (i.e. global popularity is of no interest to a given 
        # league or leagues) 
        self.__needs_enabling__.add('num_games')          
        if 'num_games' in request and request['num_games'].isdigit():
            self.num_games = int(request["num_games"])
            self.__enable__('num_games', self.num_games)

        # We can acccept leagues in an any or all form but
        # above all we have a fallback to the session specified
        # default filter if neither is specified. We support 
        # specifying an empty valye of either to avoid applying
        # the sessioni default, an explicit rewuest for no
        # league filtering     
        self.__needs_enabling__.add('game_leagues_any')          
        self.__needs_enabling__.add('game_leagues_all')
        preferred_league = None          
        if 'game_leagues_any' in request:
            if request['game_leagues_any']:
                leagues = request['game_leagues_any'].split(",")
            else:
                leagues = None
        elif 'game_leagues_all' in request:
            if request['game_leagues_all']:
                leagues = request['game_leagues_all'].split(",")
            else:
                leagues = None
        elif not request:
            preferred_league = session.get('league', None)
            leagues = [preferred_league] if preferred_league else []
        else:
            leagues = None
            
        if leagues:   
            # Validate the leagues  discarding any invalid ones
            self.game_leagues = []
            for league in leagues:
                if League.objects.all().filter(pk=league).exists():
                    self.game_leagues.append(league)

            # We need to enable one of these for each of the three posible outcomes above,
            # An explicti request for any league, all leagues or a fallback on preferred league.
            self.__enable__('game_leagues_any', self.game_leagues and ('game_leagues_any' in request or preferred_league))
            self.__enable__('game_leagues_all', self.game_leagues and 'game_leagues_all' in request)

        # The filter for players can also arrive in one of two forms
        # and any or all request (both is illegal and one will 
        # perforce be be ignored here). With this list we request
        # to see leaderboards for games play by any of the listed
        # players, or those played by all of the listed players. 
        self.__needs_enabling__.add('game_players_any')          
        self.__needs_enabling__.add('game_players_all')          
        if 'game_players_any' in request:
            players = request['game_players_any'].split(",")
        elif 'game_players_all' in request:
            players = request['game_players_all'].split(",")
        else:
            players = [] # # Must be a a Falsey value

        if players:
            # Validate the players discarding any invalid ones
            self.game_players = []
            for player in players:
                if Player.objects.all().filter(pk=player).exists():
                    self.game_players.append(player)

            self.__enable__('game_players_any', self.game_players and 'game_players_any' in request)
            self.__enable__('game_players_all', self.game_players and 'game_players_all' in request)

        # If a date is submitted (and parses validly) this asks us to list only
        # games that have a recorded play session after that date (exclude games 
        # not played since them).
        self.__needs_enabling__.add('changed_since')          
        if 'changed_since' in request:
            try:
                self.changed_since = fix_time_zone(parser.parse(decodeDateTime(request['changed_since'])))
            except:
                self.changed_since = None # Must be a a Falsey value

            self.__enable__('changed_since', self.changed_since)

        # A request for a session impact presentaton comes in the form 
        # of session_games = num_days, where num bays flags the length 
        # of session to look for. We record it in self.num_days to flag 
        # that this is what we want to the processor. Other filters of 
        # course may impact on this and reduce the number of games, which
        # can in fact be handy if say the games of a long and busy games 
        # event are logged and could produce a large number of boards. 
        # But for an average games night, probably makes little sense 
        # and has little utility. 
        self.__needs_enabling__.add('num_days')          
        if 'num_days' in request and request['num_days'].isdigit():
            self.num_days = int(request["num_days"])
            self.__enable__('num_days', self.num_days)

        # Now we capture the player filters. That is the options that 
        # restrict which players we present on the boards.

        # First we accept a list of players to restrict the list to if desired.
        # If we ask for that we use the player list provided or if it's supplied
        # as an empty value, we take the list from an already supplied source if 
        # possible.
        #
        # TODO: consider:
        #       num_players_top is exempt from this list or not, or is it optional with 
        #       another UI option? Suspect the latter defaulting to expempt.
        self.__needs_enabling__.add('players')          
        if 'players' in request:
            players = request['players']
            
            if players:
                # Convert the csv string to a list 
                players = players.split(",")
                
                # If the list has values...
                if players:
                    # Validate the players discarding any invalid ones
                    self.players = []
                    for player in players:
                        if Player.objects.all().filter(pk=player).exists():
                            self.players.append(player)                                

                self.__enable__('players', self.players)                            

            # If falsey players submitted it's a request to use already submitte game_players 
            elif self.game_players:
                # Already validated list of players
                self.players = self.game_players
                self.__enable__('players', self.players)                            
 
        # Then an option to discard all but the top num_players of each board.
        # Boards can get loooong and this is a very useful option with a useful
        # option and should be defaulted on to some value like 10 or 20 and 
        # the selecting checkbox defaulting to on in the form.
        # TODO: fix form to ensure this ithe case.
        self.__needs_enabling__.add('num_players_top')          
        if 'num_players_top' in request and request['num_players_top'].isdigit():
            self.num_players_top = int(request["num_players_top"])
            self.__enable__('num_players_top', self.num_players_top)                            
       
        # Here we're requesting to provide context to the self.players that
        # are showing on the list. We may want to see a player or two or more 
        # above and/or below them. 
        self.__needs_enabling__.add('num_players_above')          
        if 'num_players_above' in request and request['num_players_above'].isdigit():
            self.num_players_above = int(request["num_players_above"])
            self.__enable__('num_players_above', self.num_players_above)                            

        self.__needs_enabling__.add('num_players_below')          
        if 'num_players_below' in request and request['num_players_below'].isdigit():
            self.num_players_below = int(request["num_players_below"])
            self.__enable__('num_players_below', self.num_players_below)                            
        
        # Now we request to throw away any players that have played this game 
        # less than a minimum value.
        # TODO: Again, does this have priority over num_players_top or does it
        #       have priority. And does it have priority over self.players, 
        #       or vice versa, or are these UI selectable?  
        self.__needs_enabling__.add('min_plays')          
        if 'min_plays' in request and request['min_plays'].isdigit():
            self.min_plays = int(request["min_plays"])
            self.__enable__('min_plays', self.min_plays)                            

        # Now we request to throw away all players who haven't played the game
        # recently enough ... 
        # TODO: Same priority questions compounding!        
        self.__needs_enabling__.add('played_since')          
        if 'played_since' in request:
            try:
                self.played_since = fix_time_zone(parser.parse(decodeDateTime(request['played_since'])))
            except:
                self.played_since = None  # Must be a a Falsey value        

            self.__enable__('played_since', self.played_since)                            
        
        # We support a league filter, as with games, and again with an any or all
        # logical operation requested. We also support reference values to the
        # possibly already supplied game_leagues_any or game_leagues_all.
        #
        # TODO: Again, priority questions. We almost need to be able to drag these
        #       player selectors up and down on the page to prioritise them! Aaargh.
        self.__needs_enabling__.add('player_leagues_any')          
        self.__needs_enabling__.add('player_leagues_all')          
        if 'player_leagues_any' in request:
            if request['player_leagues_any']:
                leagues = request['player_leagues_any'].split(",")
            else:
                leagues = None
        elif 'player_leagues_all' in request:
            if request['player_leagues_all']:
                leagues = request['player_leagues_all'].split(",")
            else:
                leagues = None
        elif not request:
            preferred_league = session.get('league', None)
            leagues = [preferred_league] if preferred_league else []
        else:
            leagues = None
            
        if leagues:
            # Validate the leagues discarding any invalid ones
            self.player_leagues = []
            for league in leagues:
                if League.objects.all().filter(pk=league).exists():
                    self.player_leagues.append(league)

            # We need to enable one of these for each of the three posible outcomes above,
            # An explicti request for any league, all leagues or a fallback on preferred league.
            self.__enable__('player_leagues_any', self.player_leagues and ('player_leagues_any' in request or preferred_league))                            
            self.__enable__('player_leagues_all', self.player_leagues and 'player_leagues_all' in request)                            

        elif self.game_leagues:
            # Already validated list of players
            self.player_leagues = self.game_leagues

            # We need to enable one of these for each of the three posible outcomes above,
            # An explicti request for any league, all leagues or a fallback on preferred league.
            self.__enable__('player_leagues_any', self.player_leagues and ('player_leagues_any' in request or preferred_league))                            
            self.__enable__('player_leagues_all', self.player_leagues and 'player_leagues_all' in request)                            
        
        # Now we capture the persepctive request if it provides a valid datetime
        self.__needs_enabling__.add('as_at')          
        if 'as_at' in request:
            try:
                self.as_at = fix_time_zone(parser.parse(decodeDateTime(request['as_at'])))
            except:
                self.as_at = None  # Must be a a Falsey value
                
            self.__enable__('as_at', self.as_at)                            
                
        # Now the evolution options. These are simpler as we can onjly specify one
        # method of selecting which snapshots to display. Compare_back_to is special
        # beast though as we record it as an int or a datetime. The latter is an explict
        # request back to time, and the former is a num_days request for a session
        # impact presentation where the session is chosed by looking back from the current 
        # leaderboard (latest or as_at) this many days and finding relevant snapshots in that
        # window.
        self.__needs_enabling__.add('compare_with')          
        self.__needs_enabling__.add('compare_back_to')          
        if 'compare_with' in request and request['compare_with'].isdigit():
            self.compare_with = int(request['compare_with'])            
            self.__enable__('compare_with', self.compare_with)                            
            self.__enable__('compare_back_to', False)                            
            
        elif 'compare_back_to' in request:
            if request['compare_back_to'].isdigit():
                self.compare_back_to = int(request['compare_back_to'])
            else:
                try:
                    self.compare_back_to = fix_time_zone(parser.parse(decodeDateTime(request['compare_back_to'])))
                except:
                    self.compare_back_to = None  # Must be a a Falsey value
                    
            self.__enable__('compare_back_to', self.compare_back_to)                            
            self.__enable__('compare_with', False)                            
                    

        # Options to include extra infor in a leaderboard header
        if 'details' in request:
            self.details = json.loads(request['details'].lower()) # A boolean value is parsed
        # else use the default value     
    
        if 'analysis_pre' in request:
            self.analysis_pre = json.loads(request['analysis_pre'].lower()) # A boolean value is parsed     
    
        if 'analysis_post' in request:
            self.analysis_post = json.loads(request['analysis_post'].lower()) # A boolean value is parsed
    
        # Options for formatting the contents of a given leaderbaords 
        if 'highlight_players' in request:
            self.highlight_players = json.loads(request['highlight_players'].lower()) # A boolean value is parsed
             
        if 'highlight_changes' in request:
            self.highlight_changes = json.loads(request['highlight_changes'].lower()) # A boolean value is parsed

        if 'highlight_selected_players' in request:
            self.highlight_selected_players = json.loads(request['highlight_selected_players'].lower()) # A boolean value is parsed
        
        if 'names' in request:
            self.names = self.NameSelection[request['names']]
        
        if 'links' in request: 
            self.links = self.LinkSelection[request['links']]

        # Options for laying out leaderboards on screen 
        if 'cols' in request:
            self.cols = request['cols']

        # YET TO BE IMPLEMENTED OPTIONS
        if 'trace' in request:
            self.trace = request['trace'].split(",")
   
    def as_dict(self):
        '''
        Produces a dictionary of JSONified option values which can be passed to context
        and used in Javascript. 
        '''
        d = {}
        
        # Ignore internal attributes (startng with __) and methods (callable)
        for attr in [a for a in dir(self) if not a.startswith('__')]:
            val = getattr(self, attr)

            # Don't include methods or enums or dicts
            if not callable(val) and not isinstance(val, enum.EnumMeta) and not isinstance(val, OrderedDict):            
                # Format date_times sensibly
                if isinstance(val, datetime):
                    val = val.strftime(settings.DATETIME_INPUT_FORMATS[0])

                # and listify sets (sets don't work in JS)
                elif isinstance(val, set):
                    val = list(val)
                
                d[attr] = val
        
        return d

def get_leaderboard_titles(lo):
    '''
    Builds page title and subtitle form the leaderboard options supplied
    
    Returns them in a 2-tuple.
    '''
    
    if lo.is_enabled('game_leagues_any') or lo.is_enabled('game_leagues_all'):
        L = League.objects.filter(pk__in=lo.game_leagues)
        La = "any" if lo.is_enabled('game_leagues_any') else "all"
    else:
        L = []
        
    LA = f"{La} of the leagues" if len(L) > 1 else "the league" 

    if lo.is_enabled('game_players_any') or lo.is_enabled('game_players_all'):
        P = Player.objects.filter(pk__in=lo.game_players)
        Pa = "any" if lo.is_enabled('game_players_any') else "all"
    else:
        P = []

    PA = f"{Pa} of the players" if len(P) > 1 else "the player"  
    
    l = ", ".join([l.name for l in L]) 
    p = ", ".join([p.name_nickname for p in P]) 
            
    title = f"Top {lo.num_games} " if lo.is_enabled('num_games') else ""
            
    # Format the page title
    if not P:
        if not L:
            title += "Global Leaderboards"
        else:
            title += f"Leaderboards for {LA} {l}"
    else:
        if not L:
            title += f"Leaderboards for {PA} {p}"
        else:
            title += f"Leaderboards for {PA} {p} in {LA} {l} "        

    subtitle = []
    if lo.is_enabled("as_at"):
        subtitle.append(f"as at {localize(localtime(lo.as_at))}")

    if lo.is_enabled("changed_since"):
        subtitle.append(f"changed after {localize(localtime(lo.changed_since))}")

    if lo.is_enabled("compare_back_to"):
        if isinstance(lo.compare_back_to, int):
            time = f"before the last game session of {lo.compare_back_to} days"
        else:
            time = "that same time" if lo.compare_back_to == lo.changed_since else localize(localtime(lo.compare_back_to))
        subtitle.append(f"compared back to the leaderboard as at {time}")
    elif lo.is_enabled("compare_with"):
        subtitle.append(f"compared up to with {lo.compare_with} prior leaderboards")

    if lo.is_enabled("as_at"):
        subtitle.append(f"compared up to the leaderboard as at {localize(localtime(lo.as_at))}")
        
    return (title, "<BR>".join(subtitle))

def view_Leaderboards(request): 
    '''
    The raison d'etre of the whole site, this view presents the leaderboards. 
    '''
    # Fetch the leaderboards
    leaderboards = ajax_Leaderboards(request, raw=True)   

    session_filter = request.session.get('filter',{})
    lo = leaderboard_options(session_filter, request.GET)    
    default = leaderboard_options(session_filter)
    
    (title, subtitle) = get_leaderboard_titles(lo)
    
    # selectthe widget defaults
    leagues = lo.game_leagues if lo.game_leagues else request.session.get('filter',{}).get('league', [])
    players = lo.game_players if lo.game_players else lo.players
    games = lo.games
    
    c = {'title': title,
         'subtitle': subtitle,
         
         # For use in Javascript
         'options': json.dumps(lo.as_dict()),         
         'defaults': json.dumps(default.as_dict()),   
         'leaderboards': json.dumps(leaderboards, cls=DjangoJSONEncoder),
         
         # For us in templates
         'leaderboard_options': lo,
         
         # Widgets to use in the form
         'widget_leagues': html_selector(League, "leagues", leagues, ALL_LEAGUES),
         'widget_players': html_selector(Player, "players", players, ALL_PLAYERS),
         'widget_games': html_selector(Game, "games", games, ALL_GAMES),
         'widget_media': autocomplete.Select2().media,
         
         # Time and timezone info
         'now': timezone.now(),        
         'default_datetime_input_format': datetime_format_python_to_PHP(settings.DATETIME_INPUT_FORMATS[0])
         }
    
    return render(request, 'CoGs/view_leaderboards.html', context=c)


#===============================================================================
# AJAX providers
#===============================================================================

def ajax_Leaderboards(request, raw=False):
    '''
    A view that returns a JSON string representing requested leaderboards.
    
    This is used with raw=True as well by view_Leaderboards to get the leaderboard data,
    not JSON encoded.
    
    Should only validly be called from view_Leaderboards when a view is rendered
    or as an AJAX call when requesting a leaderboard refresh because the player name 
    presentation for example has changed. 
    
    Caution: This does not have any way of adjusting the context that the original 
    view received, so any changes to leaderboard content that warrant an update to 
    the view context (for example to display the nature of a filter) should be coming
    through view_Leaderboards (which delivers context to the page). 
    
    The returned leaderboards are in the following rather general structure of
    lists within lists. Some are tuples in the Python which when JSONified for
    the template become lists (arrays) in Javascript. This data structure is central
    to interaction with the front-end template for leaderboard rendering.
    
    Tier1: A list of four value tuples (game.pk, game.BGGid, game.name, Tier2)
           One tuple per game in the leaderboard presentation that
            
    Tier2: A list of five value tuples (date_time, plays[game], sessions[game], session_detail, Tier3)
           One tuple for each leaderboard snapshot for that game, being basically session details 
           
    Tier3: A list of six value tuples (player.pk, player.BGGname, player.name, rating.trueskill_eta, rating.plays, rating.victories)
           One tuple per player on that leaderboard
    
    Tier1 is the header for a particular game

    Tier2 is a list of leaderboard snapshots as at the date_time. In the default rendering and standard
    view, this should be a list with one entry, and date_time of the last play as the timestamp. That 
    would indicate a structure that presents the leaderboards for now. These could be filtered of course 
    (be a subset of all leaderboards in the database) by whatever filtering the view otherwise supports.
    The play count and session count for that game up to that time are in this tuple too.   
    
    Tier3 is the leaderboard for that game, a list of players with their trueskill ratings in rank order.
    
    Links to games and players in the leaderboard are built in the template, wrapping a player name in
    a link to nothing or a URL based on player.pk or player.BGGname as per the request.
    '''
    
    # Fetch the options submitted (and the defaults)
    session_filter = request.session.get('filter',{})
    lo = leaderboard_options(session_filter, request.GET)

    # Create a page title, based on the leaderboard options (lo).
    (title, subtitle) = get_leaderboard_titles(lo)
          
    #######################################################################################################
    ## CHOOSE THE GAMES we will report leaderboards on
    #######################################################################################################
    #
    # They are used to populate Tier 1 in the leaderboard structure we return
    #
    
    # NOTE: Q objects can be combined with & or | and this affects prioritisation.
    #       Cab we support any such prioritisaations easily?
    
    # Start the query with an ordered list of all games (lazy, only the SQL created)     
    # Sort them by default in descending order of play_count then session_count (measures
    # of popularity in the specified leagues).
    # TODO: implement this any/all decision
    if lo.is_enabled('game_leagues_any'):
        lfilter = Q(sessions__league__pk__in=lo.game_leagues) 
    elif lo.is_enabled('game_leagues_all'): 
        lfilter = Q(sessions__league__pk__in=lo.game_leagues)
    else: 
        lfilter = Q()
    
    # We sort them by a measure of popularity (within the selected leagues)
    #
    # TODO: This is not popularity within the leagues! That is more complicated
    #       we need to filter sessiuons and sessions_performances by leagues. 
    games = (Game.objects.filter(lfilter)
                         .annotate(session_count=Count('sessions',distinct=True))
                         .annotate(play_count=Count('sessions__performances',distinct=True))
                         .order_by('-play_count','-session_count'))

    # Always ignore games with no recorded sessions (yet)
    gfilter = Q(session_count__gt=0)

    # Now build up gfilter based on the game selectors
    if lo.is_enabled('games'):
        gfilter &= Q(pk__in=lo.games)
        
    if lo.is_enabled('changed_since'):
        gfilter &= Q(sessions__date_time__gte=lo.changed_since)

    # TODO implement this any/all decision
    if lo.is_enabled('game_players_any'):
        gfilter &= Q(sessions__performances__player__pk__in=lo.players)
    elif lo.is_enabled('game_players_all'):
        gfilter &= Q(sessions__performances__player__pk__in=lo.players)
        
    if lo.is_enabled('num_days'):
        # We model session impact by selecting games played between 
        # as_at and changed_since as follows

        # Start with a league filter        
        # TODO: implement this any/all decision
        if lo.is_enabled('game_leagues_any'):
            sfilter = Q(league__pk__in=lo.game_leagues) 
        elif lo.is_enabled('game_leagues_all'): 
            sfilter = Q(league__pk__in=lo.game_leagues)
        else: 
            sfilter = Q()
        
        # Respect the perspective request
        if lo.is_enabled('as_at'):
            sfilter &= Q(date_time__lte=lo.as_at)
        
        # Get most recent session these leagues played 
        latest_session = Session.objects.filter(sfilter).order_by("-date_time").first()

        if latest_session:
            date = latest_session.date_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            changed_since = date - timedelta(days=lo.num_days)        

            # Now add to the game a demand that the game's been played (has sessions) since then  
            gfilter &= Q(sessions__date_time__gte=changed_since)        

    # Apply the game selector(s)
    games = games.filter(gfilter).distinct()

    # Slicing has to happen after the filtering (so it's always last oddly). 
    # TODO: Can we get the top n with Q object? Does a slice return a QuerySet?
    #       meaning we could filter before and after the slice? And have to fiddle
    #       to lists of Q objects? 
    if lo.is_enabled('num_games'):
        games = games[:lo.num_games]
    
    #######################################################################################################
    ## FOR ALL THE GAMES WE SELECTED build a leaderboard (with any associated snapshots)
    #######################################################################################################
    print_debug(f"Preparing leaderboards for {len(games)} games.")     
    leaderboards = []
    for game in games:
        print_debug(f"Preparing leaderboard for: {game}")     
        #######################################################################################################
        ## CHOOSE THE SESSIONS (leaderboard snapshots) to report
        #######################################################################################################
        # A snapshot is the leaderboard as it appears after a given game session
        # The default and only standard snapshot is the current leaderboard after the 
        # last session of the game.
        #
        # But this can be altered by:
        #
        # A perspective request:
        #    lo.as_at which asks for the leaderboard as at a given time (not the latest one)
        # 
        # Evolution requests:
        #    lo.EvolutionSelections documents the possible selections
        #       
        # We build a list of sessions after which we wnat the leaderboard snapshots.
        #
        # They are used to populate Tier 2 in the leaderboards structure we return.

        boards = []
        
        # Start our Session filter with sessions for the game in question
        sfilter = Q(game=game)
        
        # Respect the leagues filter 
        # This game may be played by different leagues 
        # and we're not interested in their sessions
        # TODO: implement the ny/all split
        if lo.is_enabled('game_leagues_any'):
            sfilter &= Q(league__pk__in=lo.game_leagues)
        elif lo.is_enabled('game_leagues_all'):
            sfilter &= Q(league__pk__in=lo.game_leagues)

        # Respect the perspective request
        if lo.is_enabled('as_at'):
            sfilter &= Q(date_time__lte=lo.as_at)

        # Then order the session in reverse data_time order and take 
        # the top one, the latest session, as our reference.
        sessions = Session.objects.filter(sfilter).order_by("-date_time")            
        latest_session = sessions.first() if sessions else None
        
        # We need only continue with this game if it has sessions recorded
        if latest_session:
            # And we always wnat that session to display a board
            boards.append(latest_session)
            
            # Now respect the Evolution selection in choosing which historic
            # snapshots to add to the boards for this game.
            compare_back_to = None
            if lo.is_enabled('compare_back_to'):
                # lo.compare_back_to is provided as a valid in or valid datetime by lo's constructor
                if isinstance(lo.compare_back_to, int):
                    # We model this by looking back_to the session just before the one
                    # after num_days before latest session for the game. In short, we
                    # want to find a compare_back_to value that we can use
                    # We acknowedge a games night can go past midnight and consider
                    # 4am the cut off for a new day. 
                    date = latest_session.date_time.replace(hour=4, minute=0, second=0, microsecond=0) + timedelta(days=1)
                    compare_back_to = date - timedelta(days=lo.num_days)                        
                else:
                    compare_back_to = lo.compare_back_to            
                        
            if lo.is_enabled('compare_with'):
                print_debug(f"Comparing with: {lo.compare_with}")     

                if lo.compare_with < sessions.count():
                    back_sessions = sessions[1:lo.compare_with+1]
                else:
                    back_sessions = sessions[1:]
                    
                if back_sessions:
                    # Add them to the boards we want
                    for s in back_sessions: 
                        boards.append(s)
    
            elif compare_back_to:                 
                print_debug(f"Comparing back to: {lo.compare_back_to}")     

                # We get the sessions back to lo.compare_back_to     
                back_sessions = sessions.filter(date_time__gt=compare_back_to, date_time__lt=latest_session.date_time)

                print_debug(f"\tFound {len(back_sessions)} back sessions between {compare_back_to} and {latest_session.date_time}.")     
                
                if back_sessions:
                    # Add them to the boards we want
                    for s in back_sessions: 
                        boards.append(s)
                        
                    # In that list we want to look one back before the earliest one
                    # Becasue it's the leaderboard after that session, that was current
                    # at lo.compare_back_to. 
                    earliest_session = back_sessions.last()
                    back_sessions = sessions.filter(date_time__lt=earliest_session.date_time)
                    
                    if back_sessions:
                        # The one prior to earliest_session will be at top of the list of back_sessions
                        boards.append(back_sessions.first())                        
                elif compare_back_to < latest_session.date_time:
                    # If there are no back sessions we want the one prior to the latest session as 
                    # it represents the current leaderboad before this latest sessionw as played.
                    # But only if the date we're looking "back" to is back from the reference session.
                    back_sessions = sessions.filter(date_time__lt=latest_session.date_time)

                    if back_sessions:
                        # The one prior to earliest_session will be at top of the list of back_sessions
                        boards.append(back_sessions.first())
    
            #######################################################################################################
            ## BUILD EACH SNAPSHOT BOARD - from the sessions we recorded in "boards"
            #######################################################################################################
            #
            # From the list of boards (sessions) for this game build Tier2 and Tier 3 in the returned structure 
            # now. That is assemble the actualy leaderbards after each of the collected sessions.
            
            print_debug(f"\tPreparing {len(boards)} boards.")     
            
            snapshots = []            
            for board in boards:
                # IF as_at is now, the first time should be the last session time for the game 
                # and thus should translate to the same as what's in the Rating model. 
                # TODO: Perform an integrity check around that and indeed if it's an ordinary
                #       leaderboard presentation check on performance between asat=time (which 
                #       reads Performance) and asat=None (which reads Rating).
                # TODO: Consider if performance here improves with a prefetch or such noting that
                #       game.play_counts and game.session_list might run faster with one query rather 
                #       than two.
                
                # Compile the information we need for the header of a leaderboard we present
                time = board.date_time
                time_local = localize(localtime(time))
                
                print_debug(f"\tBoard for session at {time_local}.")                     
                
                players = [p.pk for p in board.players]
                detail = board.leaderboard_header(lo.names)
                analysis = board.leaderboard_analysis(lo.names)
                analysis_after = board.leaderboard_analysis_after(lo.names)
    
                # Now get the leaderboard asat the time of this board.
                # TODO: Check what game.leaderboard does with leagues and that 
                #       it filters players on the leaderboard. And what about the
                #       any/all option, we need that supported.
                lb = game.leaderboard(leagues=lo.player_leagues, asat=time, names=lo.names, indexed=True)
                if not lb is None:
                    # TODO check what game.play_counts does with leagues and that it only returns counts
                    #      of plays by those leagues, but what about our any/all option! We need to 
                    #      support that! 
                    counts = game.play_counts(leagues=lo.game_leagues, asat=time)
                    total = counts['total']
                    sessions = counts['sessions']
                    snapshot = (time_local, total, sessions, players, detail, analysis, analysis_after, lb)
                    snapshots.append(snapshot)
    
            # Technically we MUST have at least one snapshot! If not, it implies that
            if len(snapshots) > 0:                    
                leaderboards.append((game.pk, game.BGGid, game.name, snapshots))

    # raw is asked for on a standard page load, when a true AJAX request is underway it's false.
    return leaderboards if raw else HttpResponse(json.dumps((title, subtitle, lo.as_dict(), leaderboards)))

def ajax_Game_Properties(request, pk):
    '''
    A view that returns the basic game properties needed by the Session form to make sensible rendering decisions.
    '''
    game = Game.objects.get(pk=pk)
    
    props = {'individual_play': game.individual_play, 
             'team_play': game.team_play,
             'min_players': game.min_players,
             'max_players': game.max_players,
             'min_players_per_team': game.min_players_per_team,
             'max_players_per_team': game.max_players_per_team
             }
      
    return HttpResponse(json.dumps(props))

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
    
    view_url = reverse("view", kwargs={"model":view.model.__name__,"pk": view.obj.pk})
    json_url = reverse("get_detail_html", kwargs={"model":view.model.__name__,"pk": view.obj.pk})
    html = view.as_html()
    
    response = {'view_URL':view_url, 'json_URL':json_url, 'HTML':html}

    # Add object browser details if available. Should be added by DetailViewExtended    
    if hasattr(view, 'object_browser'):
        response['object_browser'] = view.object_browser
        
        if view.object_browser[0]:
            response['json_URL_prior'] = reverse("get_detail_html", kwargs={"model":view.model.__name__,"pk": view.object_browser[0]})
        else:
            response['json_URL_prior'] = response['json_URL']
             
        if view.object_browser[1]:
            response['json_URL_next'] = reverse("get_detail_html", kwargs={"model":view.model.__name__,"pk": view.object_browser[1]})
        else:
            response['json_URL_next'] = response['json_URL']
     
    return HttpResponse(json.dumps(response))

#===============================================================================
# Some POST information receivers
#===============================================================================

def receive_ClientInfo(request):
    '''
    A view that returns (presents) nothing, is not a view per se, but much rather just
    accepts POST data and acts on it. This is specifically for receiving client 
    information via an XMLHttpRequest bound to the DOMContentLoaded event on site
    pages which asynchonously and silently in the background on a page load, posts
    the client information here.
    
    The main aim and r'aison d'etre for this whole scheme is to divine the users 
    timezone as quickly and easily as we can, when they first surf in, to whatever
    URL. Of course that first page load will take place with an unknown timezone,
    but subsequent to it we'll know their timezone.
    
    Implemented as well, just for the heck of it are acceptors for UTC offset, and
    geolocation, that HTML5 makes available, which can be used in logging site visits.
    '''
    if (request.POST):
        if "clear_session" in request.POST:
            print_debug(f"referrer = {request.META.get('HTTP_REFERER')}")
            session_keys = list(request.session.keys())
            for key in session_keys:
                del request.session[key]
            return HttpResponse("<script>window.history.pushState('', '', '/session_cleared');</script>")

        # Check for the timezone
        if "timezone" in request.POST:
            print_debug(f"Timezone = {request.POST['timezone']}")
            request.session['timezone'] = request.POST['timezone']
            activate(request.POST['timezone'])

        if "utcoffset" in request.POST:
            print_debug(f"UTC offset = {request.POST['utcoffset']}")
            request.session['utcoffset'] = request.POST['utcoffset']

        if "location" in request.POST :
            print_debug(f"location = {request.POST['location']}")
            request.session['location'] = request.POST['location']
            
    return HttpResponse()

def receive_Filter(request):
    '''
    A view that returns (presents) nothing, is not a view per se, but much rather just
    accepts POST data and acts on it. This is specifically for receiving filter 
    information via an XMLHttpRequest.
    
    The main aim and r'aison d'etre for this whole scheme is to provide a way to 
    submit view filters for recording in the session. 
    '''
    if (request.POST):
        # Check for league
        if "league" in request.POST:            
            print_debug(f"League = {request.POST['league']}")
            save_league_filters(request.session, int(request.POST.get("league", 0)))
           
    return HttpResponse()

def receive_DebugMode(request):
    '''
    A view that returns (presents) nothing, is not a view per se, but much rather just
    accepts POST data and acts on it. This is specifically for receiving a debug mode
    flag via an XMLHttpRequest when debug mode is changed.
    '''
    if (request.POST):
        # Check for league
        if "debug_mode" in request.POST:            
            request.session["debug_mode"] = True if request.POST.get("debug_mode", "false") == 'true' else False
           
    return HttpResponse()

#===============================================================================
# Some general function based views
#===============================================================================

def view_About(request):
    '''
    Displays the About page (static HTML wrapped in our base template
    '''
    return

#===============================================================================
# Special sneaky fixerupper and diagnostic views for testing code snippets
#===============================================================================

def view_Inspect(request, model, pk): 
    '''
    A special debugging view which simply displays the inspector property of a given model 
    object if it's implemented. Intended as a hook into quick inspection of rich objects 
    that implement a neat HTML inspector property.
    '''
    CuserMiddleware.set_user(request.user)

    m = class_from_string('Leaderboards', model)
    o = m.objects.get(pk=pk)
    
    result = getattr(o, "inspector", "{} has no 'inspector' property implemented.".format(model))   
    c = {"title": "{} Inspector".format(model), "inspector": result}
    return render(request, 'CoGs/view_inspector.html', context=c)

#===============================================================================
# Some Developement tools (Should not be on the production site)
#===============================================================================

def view_CheckIntegrity(request):
    '''
    Check integrity of database
    
    The check_integrity routines on some models all work with assertions 
    and raise exceptions when integrity errors are found. So this will bail 
    on the first error, and outputs will be on the console not sent to the 
    browser.
    
    All needs some serious tidy up for a productions site.    
    '''
    CuserMiddleware.set_user(request.user)
    
    print("Checking all Performances for internal integrity.", flush=True)
    for P in Performance.objects.all():
        print("Performance: {}".format(P), flush=True)
        P.check_integrity()

    print("Checking all Ranks for internal integrity.", flush=True)
    for R in Rank.objects.all():
        print("Rank: {}".format(R), flush=True)
        R.check_integrity()
    
    print("Checking all Sessions for internal integrity.", flush=True)
    for S in Session.objects.all():
        print("Session: {}".format(S), flush=True)
        S.check_integrity()

    print("Checking all Ratings for internal integrity.", flush=True)
    for R in Rating.objects.all():
        print("Rating: {}".format(R), flush=True)
        R.check_integrity()

    return HttpResponse("Passed All Integrity Tests")

def view_RebuildRatings(request):
    CuserMiddleware.set_user(request.user)
    html = rebuild_ratings()
    return HttpResponse(html)

def view_UnwindToday(request):
    '''
    A simple view that deletes all sessions (and associated ranks and performances) created today. Used when testing. 
    Dangerous if run on a live database on same day as data was entered clearly. Testing view only.
    '''
    CuserMiddleware.set_user(request.user)
    
    unwind_to = date.today() # - timedelta(days=1)
    
    performances = Performance.objects.filter(created_on__gte=unwind_to)
    performances.delete()
    
    ranks = Rank.objects.filter(created_on__gte=unwind_to)
    ranks.delete()

    sessions = Session.objects.filter(created_on__gte=unwind_to)
    sessions.delete()
    
    ratings = Rating.objects.filter(created_on__gte=unwind_to)
    ratings.delete()
    
    # Now for all ratings remaining we have to reset last_play (if test sessions updated that).
    ratings = Rating.objects.filter(Q(last_play__gte=unwind_to)|Q(last_victory__gte=unwind_to))
    for r in ratings:
        r.recalculate_last_play_and_victory()

    html = "Success"
    
    return HttpResponse(html)

from django.apps import apps
def view_Fix(request):

# DONE: Used this to create Performance objects for existing Rank objects
#     sessions = Session.objects.all()
#
#     for session in sessions:
#         ranks = Rank.objects.filter(session=session.id)
#         for rank in ranks:
#             performance = Performance()
#             performance.session = rank.session
#             performance.player = rank.player
#             performance.save()

# Test the rank property of the Performance model
#     table = '<table border=1><tr><th>Performance</th><th>Rank</th></tr>'
#     performances = Performance.objects.all()
#     for performance in performances:
#         table = table + '<tr><td>' + str(performance.id) + '</td><td>' + str(performance.rank) + '</td></tr>'
#     table = table + '</table>'

    #html = force_unique_session_times()
    #html = rebuild_ratings()
    #html = import_sessions()
    
    #=============================================================================
    # Datetime fix up
    # We want to walk through every Session and fix the datetime so it's right
    # Subsequent to this we want to walk through every model and fix the Created and Modified datetime as well
    
    # Session times
    sessions = Session.objects.all()
    
    activate('Australia/Hobart')

    # Did this on dev database. Seems to have worked a charm.
    for session in sessions:
        dt_raw = session.date_time
        dt_local = localtime(dt_raw)
        error = dt_local.tzinfo._utcoffset
        dt_new = dt_raw - error
        dt_new_local = localtime(dt_new)
        print_debug(f"Session: {session.pk}    Raw: {dt_raw}    Local:{dt_local}    Error:{error}  New:{dt_new}    New Local:{dt_new_local}")
        session.date_time = dt_new_local
        session.save()
        
    # The rating model has two DateTimeFields that are wrong in the same way, but thee can be fixed by rebuilding ratings.
    pass  
        
    # Now for every model that we have that derives from AdminModel we need to updated we have two fields:
    #     created_on
    #     last_edited_on
    # That we need to tweak the same way.
    
    # We can do this by looping all our models and checking for those fields.  
    models = apps.get_app_config('Leaderboards').get_models()
    for model in models:
        if hasattr(model, 'created_on') or hasattr(model, 'last_edited_on'):
            for obj in model.objects.all():
                if hasattr(obj, 'created_on'): 
                    dt_raw = obj.created_on
                    dt_local = localtime(dt_raw)
                    error = dt_local.tzinfo._utcoffset
                    dt_new = dt_raw - error
                    dt_new_local = localtime(dt_new)
                    print_debug(f"{model._meta.object_name}: {obj.pk}    created    Raw: {dt_raw}    Local:{dt_local}    Error:{error}  New:{dt_new}    New Local:{dt_new_local}")
                    obj.created_on = dt_new_local 

                if hasattr(obj, 'last_edited_on'): 
                    dt_raw = obj.last_edited_on
                    dt_local = localtime(dt_raw)
                    error = dt_local.tzinfo._utcoffset
                    dt_new = dt_raw - error
                    dt_new_local = localtime(dt_new)
                    print_debug(f"{model._meta.object_name}: {obj.pk}    edited     Raw: {dt_raw}    Local:{dt_local}    Error:{error}  New:{dt_new}    New Local:{dt_new_local}")
                    obj.last_edited_on = dt_new_local
                
                obj.save()
        
#     for session in sessions:
#         dt_raw = session.date_time
#         dt_local = localtime(dt_raw)
#         dt_naive = make_naive(dt_local)
#         ctz = get_current_timezone()
#         print_debug(f"dt_raw: {dt_raw}    ctz;{ctz}    dt_local:{dt_local}    dt_naive:{dt_naive}")        
    
    html = "Success"
    
    return HttpResponse(html)

def view_Kill(request, model, pk):
    CuserMiddleware.set_user(request.user)

    m = class_from_string('Leaderboards', model)
    o = m.objects.get(pk=pk)
    o.delete()
    
    html = "Success"
    
    return HttpResponse(html)

import csv
from dateutil import parser
from django_generic_view_extensions.html import fmt_str

def import_sessions():
    title = "Import CoGs scoresheet"
    
    result = ""
    sessions = []
    with open('/home/bernd/workspace/CoGs/Seed Data/CoGs Scoresheet - Session Log.csv', newline='') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',', quotechar='"')
        for row in reader:
            date_time = parser.parse(row["Date"])
            game = row["Game"].strip()
            ranks = {
                row["1st place"].strip(): 1,
                row["2nd place"].strip(): 2,
                row["3rd place"].strip(): 3,
                row["4th place"].strip(): 4,
                row["5th place"].strip(): 5,
                row["6th place"].strip(): 6,
                row["7th place"].strip(): 7
                }
            
            tie_ranks = {}
            for r in ranks:
                if ',' in r:
                    rank = ranks[r]
                    players = r.split(',')
                    for p in players:
                        tie_ranks[p.strip()] = rank
                else:
                    tie_ranks[r] = ranks[r]
                    
            session = (date_time, game, tie_ranks)
            sessions.append(session)

    # Make sure a Game and Player object exists for each game and player
    missing_players = []
    missing_games = []
    for s in sessions:
        g = s[1]
        try:
            Game.objects.get(name=g)
        except Game.DoesNotExist:
            if g and not g in missing_games:
                missing_games.append(g)
        except Game.MultipleObjectsReturned:
            result += "{} exists more than once\n".format(g)
        
        for p in s[2]:
            try:
                Player.objects.get(name_nickname=p)
            except Player.DoesNotExist:
                if p and not p in missing_players:
                    missing_players.append(p)
            except Player.MultipleObjectsReturned:
                result += "{} exists more than once\n".format(p)
            
    if len(missing_games) == 0 and len(missing_players) == 0:
        result += fmt_str(sessions)
        
        Session.objects.all().delete()
        Rank.objects.all().delete()
        Performance.objects.all().delete()
        Rating.objects.all().delete()
        Team.objects.all().delete()
        
        for s in sessions:
            session = Session()
            session.date_time = s[0]
            session.game = Game.objects.get(name=s[1])
            session.league = League.objects.get(name='Hobart')
            session.location = Location.objects.get(name='The Big Blue House')
            session.save()
            
            for p in s[2]:
                if p:
                    rank = Rank()
                    rank.session = session
                    rank.rank = s[2][p]
                    rank.player = Player.objects.get(name_nickname=p)
                    rank.save()
    
                    performance = Performance()
                    performance.session = session
                    performance.player = rank.player
                    performance.save()
                            
            Rating.update(session)
    else:
        result += "Missing Games:\n{}\n".format(fmt_str(missing_games))
        result += "Missing Players:\n{}\n".format(fmt_str(missing_players))
            
    now = datetime.now()
            
    return "<html><body<p>{0}</p><p>It is now {1}.</p><p><pre>{2}</pre></p></body></html>".format(title, now, result)

def rebuild_ratings():
    activate(settings.TIME_ZONE)

    title = "Rebuild of all ratings"
    pr = cProfile.Profile()
    pr.enable()
    
    Rating.rebuild_all()
    pr.disable()
    
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats()
    result = s.getvalue()
        
    now = datetime.now()

    return "<html><body<p>{0}</p><p>It is now {1}.</p><p><pre>{2}</pre></p></body></html>".format(title, now, result)

def force_unique_session_times():
    '''
    A quick hack to scan through all sessions and ensure none have the same session time
    # TODO: Enforce this when adding or editing sessions because Trueskill is temporal
    # TODO: Technically two game sessions can gave the same time, just not two session involving the same game and a common player. 
    #       This is because the Trueskill for that player at that game needs to have temporally ordered game sessions
    '''
 
    title = "Forced Unique Session Times"
    result = ""
   
    sessions = Session.objects.all().order_by('date_time')
    for s in sessions:
        coincident_sessions = Session.objects.filter(date_time=s.date_time)
        if len(coincident_sessions)>1:
            offset = 1
            for sess in coincident_sessions:
                sess.date_time = sess.date_time + timedelta(seconds=offset)
                sess.save()
                result += "Added {} to {}\n".format(offset, sess)
                offset += 1 

    now = datetime.now()

    return "<html><body<p>{0}</p><p>It is now {1}.</p><p><pre>{2}</pre></p></body></html>".format(title, now, result)      
