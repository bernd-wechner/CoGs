import cProfile, pstats, io
import re, json, pytz
from re import RegexFlag as ref # Specifically to avoid a PyDev Error in the IDE. 
from datetime import datetime, date, timedelta
from collections import OrderedDict

from django_generic_view_extensions.views import LoginViewExtended, TemplateViewExtended, DetailViewExtended, DeleteViewExtended, CreateViewExtended, UpdateViewExtended, ListViewExtended
from django_generic_view_extensions.util import class_from_string
from django_generic_view_extensions.datetime import datetime_format_python_to_PHP, decodeDateTime
from django_generic_view_extensions.options import  list_display_format, object_display_format 
from django_generic_view_extensions.context import add_timezone_context, add_debug_context

from cuser.middleware import CuserMiddleware

from CoGs.logging import log
from .models import Team, Player, Game, League, Location, Session, Rank, Performance, Rating, ALL_LEAGUES, ALL_PLAYERS, ALL_GAMES
from .leaderboards import leaderboard_options, NameSelections, LinkSelections
 
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.formats import localize
from django.utils.timezone import is_aware, make_aware, make_naive, activate, localtime
from django.http import HttpResponse
#from django.http.response import HttpResponseRedirect
from django.urls import reverse, reverse_lazy  #, resolve
from django.contrib.auth.models import User, Group
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.forms.models import ModelChoiceIterator, ModelMultipleChoiceField
from django.conf import settings

from dal import autocomplete

#from numpy import rank

#TODO: Add account security, and test it
#TODO: Once account security is in place a player will be in certain leagues, 
#      restrict some views to info related to those leagues.
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

#===============================================================================
# Form processing specific to CoGs
#===============================================================================

def updated_user_from_form(user, request):
    '''
    Updates a user object in the database (from the Django auth module) with information from the submitted form, specific to CoGs
    '''
    POST = request.POST
    registrars = Group.objects.get(name='registrars')

    # TODO: user names in the auth model can only have letters, numbers and  @/./+/-/_
    # So filter the submitted name_nickname
    user.username = POST['name_nickname'] 
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

def pre_process_submitted_model(self):
    '''
    When a model form is POSTed, this function is called BEFORE the form is saved.
    
    This intended primarily to make decisions based on the post (and possibly
    the database object being updated) and buildingba kwargs dict to pass to
    the post processor. The pre-processore is called befoe the save and so have 
    privileged access to he database before the save takes place.
    
    It runs before the the form is cleaned so self.form.data is available but not
    self.form.cleaned_data is not. 
    
    self is an instance of CreateViewExtended or UpdateViewExtended.
    
    If it returns a dict that will be used as a kwargs dict into the
    the configured post processor (post_process_submitted_model below).
    '''
    model = self.model._meta.model_name
    
    debug_only = bool(self.form.data.get("debug_rebuild_request", False))
    
    # f"<html><body<p>{title}</p><p>It is now {now}.</p><p><pre>{result}</pre></p></body></html>"    
    html = "<section id='debug'>\n<pre>\n"
    
    def output(message):
        '''Toggle for diagnostic output direction'''
        nonlocal html
        if debug_only:
            m = message.replace('\n', '\n\t')
            html += f"{m}\n"
        else:
            m = message.replace('\n', ' ')
            log.debug(m)
            
    def STR(r):
        '''Quick and dirty preyty-printer for tuples and lists of tuples requests (as the repr defaults suck)'''
        if isinstance(r, list):
            s = '['
            R = r
        else:
            s = ''
            R = [r]
            
        for i, t in enumerate(R):
            s += '('
            for j, e in enumerate(t):
                s += str(e)
                if not j == len(t)-1: s += ', '
            s += ')' 
            if not i == len(R)-1: s += ', '
        if isinstance(r, list): s+= ']'
        return s
    
    # When a session submitted (while it is still in unchanged int he database) we need 
    # to check if the submission changes any rating affecting fields and make note of that
    # so that the post processor can update the ratings with a rebuild request if needed
    if model == 'session':
        output(f"PRE-PROCESSING Session submission.")

        output(f"Using form data:")
        for (key, val) in self.form.data.items():
            output(f"\t{key}:{val}")
        output("\n")
        
        # We need the time, game and players first
        # As this is all we need to know for 
        # both the Create and Update views.

        str_time = self.form.data['date_time']  # Submitted session time
        new_time = parse_datetime(str_time)            # Fails with exception or None if invalid

        # We need a TZ naive version for comparising against naive datetimes.
        if is_aware(new_time):
            nt = make_naive(localtime(new_time, timezone.utc))
        else:
            nt = new_time
            new_time = make_aware(new_time)
        
        str_game = self.form.data['game']       # Submitted game ID
        new_game = Game.objects.get(pk=int(str_game))  # Fails with exception if bad input
        
        # Grab the players and play_weights
        performances = int(self.form.data['Performance-TOTAL_FORMS'])
        new_players = []
        new_weights = []
        for p in range(performances):
            int_player = int(self.form.data[f'Performance-{p}-player'])
            new_players.append(Player.objects.get(pk=int_player))
            str_weight = self.form.data[f'Performance-{p}-partial_play_weighting']
            new_weights.append(float(str_weight))
            
        # Check to see if this is the latest play for each player
        is_latest = True
        for player in new_players:
            rating = Rating.get(player, new_game) 
            if new_time < rating.last_play:
                is_latest = False
                
        # Rebuild nothing by default
        rebuild = None

        # A rebuild of ratings is triggered under any of the following circumstances:
        #
        # 1. It's a new session and any of the players involved have future sessions
        #    recorded already.
        if isinstance(self, CreateViewExtended):
            output(f"New Session")
            if not is_latest:
                return {'rebuild': (new_game, new_time)}

        # or
        #
        # 2. It's an edit to an old session (that is not the latest in that game)
        #    and a rating-changing edit was made.
        #
        # Rating changing edits are:
        #
        # 1. The game changed
        # 2. One or more players were added or removed
        # 3. The play mode changed (team vs. individual)
        # 4. Any players rank is changed
        # 5. Any players weight has changed
        # 6. If the date time is changed such that the prior or next session 
        #    for any player changes (i.e. the order of sessions for any player 
        #    is changed)
        elif isinstance(self, UpdateViewExtended):
            old_session = self.object
            output(f"Editing session {old_session.pk}")

            # If the game was changed we will request a rebuild of both games 
            # regardless of any other considerations. Both their rating trees
            # need rebuilding. 
            if not new_game == old_session.game:
                rebuild = [(old_session.game, old_session.date_time), (new_game, new_time)]
                output(f"\tGame changed. Requesting rebuild of leaderboards: {STR(rebuild)}")
                
            else:
                old_players = old_session.players
                                
                # Divine the play mode
                if 'team_play' in self.form.data:
                    assert 'num_teams' in self.form.data, "Bad form submission, team_play on but no num_teams."
                    new_team_play = True
                else:
                    assert 'num_players' in self.form.data, "Bad form submission, team_play off but no num_players."
                    new_team_play = False
                
                # If the play mode changed rebuild this  games rating tree from 
                # this session on.
                if not new_team_play == old_session.team_play: 
                    rebuild = (old_session.game, min(old_session.date_time, new_time))
                    output(f"\tPlay mode changed from {'team' if old_session.team_play else 'individual'} to {'team' if new_team_play else 'individual'}.\n\tRequesting rebuild of leaderboards: {STR(rebuild)}")
                    
                # If any players were added, remove or changed, rebuild this 
                # games rating tree from this session on.
                elif not set(new_players) == set(old_players):
                    rebuild = (old_session.game, min(old_session.date_time, new_time))
                    output(f"\tPlayers changed from\n\t{STR(set(old_players))} to\n\t{STR(set(new_players))}.\n\tRequesting rebuild of leaderboards: {STR(rebuild)}")
                    
                # Otherwise check for othe rating impacts
                else:
                    output(f"Checking for general rating impacts ....")
                    # Grab the ranks
                    # As no players have be added or deleted and
                    # the play mode has not changed we can feel 
                    # pretty confident that each of the ranks in 
                    # the form has an id (none were DELETED)  
                    ranks = int(self.form.data['Rank-TOTAL_FORMS'])
                    new_ranks = []
                    for r in range(ranks):
                        new_ranks.append(int(self.form.data.get(f'Rank-{r}-rank', None)))

                    # Get a list of old ranks in same order as new_players and hence 
                    # new_ranks (assumes the Rank and Performance formsets have parallel 
                    # sequence numbers, which the form must ensure).
                    old_ranks = [old_session.rank(p).rank for p in new_players]

                    rank_changed = not new_ranks == old_ranks
                    if rank_changed: output(f"\tRanks changed from {old_ranks} to {new_ranks}.")
                            
                    # Check for a session sequence change
                    # If for any player this session moves out of the bounds of prev session  
                    # and following session the sequence changed
                    sequence_changed = False
                    # We can loop over new or old players because if they are not the same
                    # a rebuild is triggered anyhow.
                    for p in new_players:
                        prev_sess = old_session.previous_session(p)
                        foll_sess = old_session.following_session(p)
                        
                        # min and max are TX unaware (naive), and session.date_time is UTC
                        # So we make session.date_time naive for the comparison to come.
                        time_window = (make_naive(prev_sess.date_time) if prev_sess else datetime.min,
                                       make_naive(foll_sess.date_time) if foll_sess else datetime.max)
                        
                        # TODO: Cofirm that timezone handling is right here. 
                        # Easiest way is empircially to find a game that's been played like three time in a row and
                        # move the middle one. 
                        if not time_window[0] < nt < time_window[1]:
                            sequence_changed = True
                            output(f"\tSession sequence changed for {p}.\n\tOld time: {make_naive(old_session.date_time)}\n\tWindow: {STR(time_window)}.\n\tNew time: {nt}")
                            break 
        
                    # Check for a partial play weighting change on any player
                    weight_changed = False
                    for i, p in enumerate(new_players):
                        w = new_weights[i]
                        if not w == old_session.performance(p).partial_play_weighting:
                            weight_changed = True
                            output(f"\tPartial play weighting changed for {p}.\nFrom {old_session.performance(p).partial_play_weighting} to {w}.")
                            break
                        
                    # Determine if a rating impacting change took place.
                    rating_impact = (not new_team_play == old_session.team_play
                                     or rank_changed
                                     or weight_changed
                                     or sequence_changed )
    
                    # If a rating impact has been assess, request a rebuild.
                    if rating_impact: 
                        rebuild = (old_session.game, min(old_session.date_time, new_time))
                        output(f"\tRequesting rebuild of leaderboards:\n\t{STR(rebuild)}.")
                    else:
                        output(f"\tNo rating impact found. No rebuild requested.")
    
            if debug_only:
                html += "</pre>\n</section>\n"
                return {'debug_only': html}
            else:
                return {'rebuild': rebuild}
    
def post_process_submitted_model(self, rebuild=None):
    '''
    When a model form is POSTed, this function is called AFTER the form is saved.
    
    self is an instance of CreateViewExtended or UpdateViewExtended.

    It will be running inside a transaction and can bail with an IntegrityError if something goes wrong 
    achieving a rollback.
    
    This is executed inside a transaction which is important if it is trying to update 
    a number of models at the same time that are all related. The integrity of relations after 
    the save should be tested and if not passed, then throw an IntegrityError.   
    
    :param rebuild: An optional game, player tuple or list two such tuples nominating ratings rebuilds we should request. 
    '''
    model = self.model._meta.model_name

    if model == 'player':
        # TODO: Need when saving users update the auth model too.
        #       call updated_user_from_form() above 
        pass  
    elif model == 'session':
    # TODO: When saving sessions, need to do a confirmation step first, reporting the impacts.
    #       Editing a session will have to force recalculation of all the rating impacts of sessions
    #       all the participating players were in that were played after the edited session.
    #    A general are you sure? system for edits is worth implementing.
        session = self.object
                      
        log.debug(f"POST-PROCESSING Session {session.pk} submission.")

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

        # manage teams properly, as we handle teams in a special way creating them
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
                num_team_players = int(self.request.POST[f"Team-{t:d}-num_players"])
                num_players += num_team_players
                TeamPlayers.append([])

            # Populate the TeamPlayers record (i.e. work out which players are on the same team)
            player_pool = set()
            for p in range(num_players):
                player = int(self.request.POST[f"Performance-{p:d}-player"])
                
                assert not player in player_pool, "Error: Players in session must be unique"
                player_pool.add(player)                
                
                team_num = int(self.request.POST[f"Performance-{p:d}-team_num"])
                TeamPlayers[team_num].append(player)

            # For each team now, find it, create it , fix it as needed 
            # and associate it with the appropriate Rank just created
            for t in range(num_teams):
                # Get the submitted Team ID if any and if it is supplied 
                # fetch the team so we can provisionally use that (renaming it 
                # if a new name is specified).
                team_id = self.request.POST.get(f"Team-{t:d}-id", None)
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
                
                # Get the appropriate rank object for this team
                rank_id = self.request.POST.get(f"Rank-{t:d}-id", None)
                rank_rank = self.request.POST.get(f"Rank-{t:d}-rank", None)
                rank = session.ranks.get(rank=rank_rank)

                # A rank must have been saved before we got here, either with the POST
                # specified rank_id (for edit forms) or a new ID (for add forms) 
                assert rank, f"Save error: No Rank was saved with the rank {rank_rank}"

                # If a rank_id is specified in the POST it must match that saved 
                # before we got here using that POST specified ID. 
                if (not rank_id is None):
                    assert int(rank_id)==rank.pk, f"Save error: Saved Rank has different ID to submitted form Rank ID! Rank ID {int(rank_id)} was submitted and Rank ID {rank.pk} has the same rank as submitted: {rank_rank}."

                # The name submitted for this team 
                new_name = self.request.POST.get(f"Team-{t:d}-name", None)

                # Find the team object that has these specific players.
                # Filter by count first and filter by players one by one.
                # recall: these filters are lazy, we construct them here 
                # but they do not do anything, are just recorded, and when 
                # needed the SQL is executed. 
                teams = Team.objects.annotate(count=Count('players')).filter(count=len(team_players_post))
                for player in team_players_post:
                    teams = teams.filter(players=player)

                log.debug(f"Team Check: {len(teams)} teams that have these players: {team_players_post}.")

                # If not found, then create a team object with those players and 
                # link it to the rank object and save that.
                if len(teams) == 0 or force_new_team:
                    team = Team.objects.create()

                    for player_id in team_players_post:
                        player = Player.objects.get(id=player_id)
                        team.players.add(player)

                    # If the name changed and is not a placeholder of form "Team n" use it.
                    if new_name and not re.match("^Team \d+$", new_name, ref.IGNORECASE):
                        team.name = new_name

                    team.save()
                    rank.team=team
                    rank.save()
                    log.debug(f"\tCreated new team for {team.players} with name: {team.name}")

                # If one is found, then link it to the approriate rank object and 
                # check its name against the submission (updating if need be)
                elif len(teams) == 1:
                    team = teams[0]

                    # If the name changed and is not a placeholder of form "Team n" save it.
                    if new_name and not re.match("^Team \d+$", new_name, ref.IGNORECASE) and new_name != team.name :
                        log.debug(f"\tRenaming team for {team.players} from {team.name} to {new_name}")
                        team.name = new_name
                        team.save()

                    # If the team is not linked to the rigth rank, fix the rank and save it. 
                    if (rank.team != team):
                        rank.team = team
                        rank.save()
                        log.debug(f"\tPinned team {team.pk} with {team.players} to rank {rank.rank} ID: {rank.pk}")

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
                assert not player in player_pool, "Error: Players in session must be unique. {player} appears twice."
                player_pool.add(player)
                
        # Enforce clean ranking. This MUST happen after Teams are processed above because
        # Team processing fetches ranks based on the POST submitted rank for the team. After 
        # we clean them that relationshop is lost. So we should clean the ranks as last 
        # thing just before calculating TrueSkill impacts.
        
        if settings.DEBUG:
            # Grab a pre snapshot
            rank_debug_pre = {}
            for rank in session.ranks.all():
                rkey = rank.team.pk if team_play else rank.player.pk
                rank_debug_pre[f"{'Team' if team_play else f'Player'} {rkey}"] = rank.rank  
        
            log.debug(f"\tRanks Submitted: {sorted(rank_debug_pre.items(), key=lambda x: x[1])}")
        
        # First collect all the supplied ranks
        rank_values = []
        ranks_by_pk = {}
        for rank in session.ranks.all():
            rank_values.append(rank.rank)
            ranks_by_pk[rank.pk] = rank.rank
        # Then sort them by rank
        rank_values.sort()

        log.debug(f"\tRank values: {rank_values}")
        log.debug(f"\tRanks by PK: {ranks_by_pk}")

        # Build a map of submited ranks to saving ranks
        rank_map = OrderedDict()

        expected = 1
        for rank in rank_values:
            # if it's a new rank process it 
            if not rank in rank_map:
                # If we have the expected value map it to itself
                if rank == expected:
                    rank_map[rank] = rank
                    
                # Else map all tied ranks to the expected value and update the expectation
                else:
                    rank_map[rank] = expected
                    expected += rank_values.count(rank)
            
        log.debug(f"\tRanks Map: {rank_map}")
        
        for From, To in rank_map.items():
            if not From == To:
                pks = [k for k,v in ranks_by_pk.items() if v == From]
                rank_objs = session.ranks.filter(pk__in=pks)
                for rank_obj in rank_objs: 
                    rank_obj.rank = To
                    rank_obj.save()
                    rkey = rank_obj.team.pk if team_play else rank_obj.player.pk
                    log.debug(f"\tMoved {'Team' if team_play else f'Player'} {rkey} from rank {rank} to {rank_obj.rank}.")
                    
        if settings.DEBUG:
            # Grab a pre snapshot
            rank_debug_post = {}
            for rank_obj in session.ranks.all():
                rkey = rank_obj.team.pk if team_play else rank_obj.player.pk
                rank_debug_post[f"{'Team' if team_play else f'Player'} {rkey}"] = rank_obj.rank  

            log.debug(f"\tRanks Submitted: {sorted(rank_debug_pre.items(), key=lambda x: x[1])}")
            log.debug(f"\tRanks Saved    : {sorted(rank_debug_post.items(), key=lambda x: x[1])}")
            
        # TODO: Before we calculate TrueSkillImpacts we need to have a completely validated session!
        #       Any Ranks that come in, may have been repurposed from Indiv to Team or vice versa. 
        #       We need to clean these up. I think this means we just have to recaluclate the trueskill 
        #       impacts but also all subsequent ones involving any of these players if it's an edit!

        # If a rebuild request arrived from the preprocessors honour that
        # It means this submission is known to affect "future" sessions 
        # already in the database. Those future (relative to the submission) 
        # sessions need a ratings rebuild.        
        if rebuild:
            if isinstance(rebuild, tuple):
                Rebuild = [rebuild]
            elif isinstance(rebuild, list):
                Rebuild = rebuild
            else:
                raise NotImplementedError(f"A rebuild request is expected to be a tuple or list, no other format is supported. {type(rebuild)} was submitted.")
            
            for r in Rebuild:
                Rating.rebuild(*r)  
        
        # Otherwise, just update ratings formthis session (this implies it's the latest 
        # session for that game and these player. 
        else:
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
     
    context['league_options'] = html_league_options(self.request.session)
    context['league_widget'] = html_selector(League, "id_leagues_view", 0, ALL_LEAGUES)

    # Make  DAL media available to templates
    context['dal_media'] = str(autocomplete.Select2().media)
    
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
            context['game_individual_play'] = json.dumps(game.individual_play) # Python True/False, JS true/false 
            context['game_team_play'] = json.dumps(game.team_play)
            context['game_min_players'] = game.min_players
            context['game_max_players'] = game.max_players
            context['game_min_players_per_team'] = game.min_players_per_team
            context['game_max_players_per_team'] = game.max_players_per_team    
        else:
            raise ValueError("Session form needs a game even if it's the default game")
            
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
                        
            # We have to lose a leaderboard cache after a login as 
            # privacy settings change and lots of player name fields
            # in particular will be missing data in the cache that
            # is now available to the logged in user. This is 
            # unfortunate and there may be a cheaper way to replenish 
            # the name data than rebuilding the entire leaderboard.
            # TODO: consider cheap means of replenishing name data
            # in a leaderboard chache so that the cache can be preseved 
            # when permissions change (visibility of name data). 
            if "leaderboard_cache" in self.request.session:
                del self.request.session["leaderboard_cache"]
            
            if hasattr(user, 'player') and user.player:
                preferred_league = user.player.league
                                
                if preferred_league:
                    form.request.session["preferred_league"] = preferred_league.pk
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

def view_Leaderboards(request): 
    '''
    The raison d'etre of the whole site, this view presents the leaderboards. 
    '''
    # Fetch the leaderboards
    leaderboards = ajax_Leaderboards(request, raw=True)   

    session_filter = request.session.get('filter',{})
    tz = pytz.timezone(request.session.get("timezone", "UTC"))
    lo = leaderboard_options(request.GET, session_filter, tz)
    default = leaderboard_options(ufilter=session_filter)
    
    (title, subtitle) = lo.titles()
    
    # selectthe widget defaults
    leagues = lo.game_leagues if lo.game_leagues else request.session.get('filter',{}).get('league', [])
    players = lo.game_players if lo.game_players else lo.players
    games = lo.games
    
    # Get the preferred league id and lable
    pl_id = request.session.get("preferred_league", 0)
    
    if pl_id:
        try:
            pl_lbl = League.objects.values_list('name', flat=True).get(pk=pl_id)
        except League.DoesNotExist:
            pl_lbl = ""
            pl_id = 0
    else:
        pl_lbl = ""
            
    c = {'title': title,
         'subtitle': subtitle,
         
         # For use in Javascript
         'options': json.dumps(lo.as_dict()),         
         'defaults': json.dumps(default.as_dict()),   
         'leaderboards': json.dumps(leaderboards, cls=DjangoJSONEncoder),
         
         # For use in templates
         'leaderboard_options': lo,

         # Dicts for dropdowns
         'name_selections': NameSelections,
         'link_selections': LinkSelections,
         
         # Widgets to use in the form
         'dal_media': autocomplete.Select2().media,
         'widget_leagues': html_selector(League, "leagues", leagues, ALL_LEAGUES),
         'widget_players': html_selector(Player, "players", players, ALL_PLAYERS),
         'widget_games': html_selector(Game, "games", games, ALL_GAMES),
         
         # Time and timezone info
         'now': timezone.now(),        
         'default_datetime_input_format': datetime_format_python_to_PHP(settings.DATETIME_INPUT_FORMATS[0]),

         # The preferred league if any
         'preferred_league': [pl_id, pl_lbl],
         
         # Debug mode
         'debug_mode': request.session.get("debug_mode", False)
         }
    
    add_timezone_context(request, c)
    add_debug_context(request, c)
    
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

    if not settings.USE_LEADERBOARD_CACHE and "leaderboard_cache" in request.session:
        del request.session["leaderboard_cache"]
    
    # Fetch the options submitted (and the defaults)
    session_filter = request.session.get('filter',{})
    tz = pytz.timezone(request.session.get("timezone", "UTC"))
    lo = leaderboard_options(request.GET, session_filter, tz)
    
    # Create a page title, based on the leaderboard options (lo).
    (title, subtitle) = lo.titles()
    
    # Get the cache if available
    #
    # It should contain leaderboard snapshots already produced.
    # Each snapshot is uniquely identified by the session.pk 
    # that it belongs to. And so we can store them in cache in 
    # a dict keyed on session.pk
    lb_cache = request.session.get("leaderboard_cache", {}) if not lo.ignore_cache else {} 
    
    # Fetch the queryset of games that these options specify
    # This is lazy and should not have caused a database hit just return an unevaluated queryset
    # Note: this respect the last event of n days request by constraining to games played
    #       in the specified time frame and at the same location.  
    games = lo.games_queryset()
    
    #######################################################################################################
    ## FOR ALL THE GAMES WE SELECTED build a leaderboard (with any associated snapshots)
    #######################################################################################################
    log.debug(f"Preparing leaderboards for {len(games)} games.")     
    leaderboards = []
    for game in games:
        log.debug(f"Preparing leaderboard for: {game}")     

        # FIXME: Here is a sweet spot. Some or all sessions are available in the
        #        cache already. We need the session only for:
        #
        #  1) it's datetime - cheap
        #  2) to build the three headers
        #     a) session player list     - cheap
        #     b) analisys pre            - expensive
        #     c) analysis post           - expensive
        #
        # We want to know if the session is already in a cached snapshot.
        #
        # FIXME: For that it's best to use PK, so we want to put Session.PK into
        #        the snapshot tuple!        
        
        # Note: the snapshot query does not constrain sessions to the same location as 
        # as does the game query. once we have the games that were played at the event, 
        # we're happy to include all sessions during the event regardless of where. The
        # reason being that we want to see evoluton of the leaderboards during the event
        # even if some people outside of the event are playing it and impacting the board.
        boards = lo.snapshot_queryset(game)
        
        if boards:
            #######################################################################################################
            ## BUILD EACH SNAPSHOT BOARD - from the sessions we recorded in "boards"
            #######################################################################################################
            #
            # From the list of boards (sessions) for this game build Tier2 and Tier 3 in the returned structure 
            # now. That is assemble the actualy leaderbards after each of the collected sessions.
            
            log.debug(f"\tPreparing {len(boards)} boards/snapshots.")     
            
            # We want to build a list of snapshots to add to the leaderboards list
            snapshots = []
            
            # We keep a dictionary of previous ranks for each player by PK so we can can
            # insert them into the leaderboardd, enabling the client to highlight rank 
            # changes from snapshot to snapshot. 
            previous_rank = {}
            
            # For each board/snapshot of this game ...
            # In temporral order so we can construct the "previous rank" 
            # element on the fly, but we're reverse it back when we add the 
            # collected snapshots to the leaderboards list.        
            for board in reversed(boards):
                # IF as_at is now, the first time should be the last session time for the game 
                # and thus should translate to the same as what's in the Rating model. 
                # TODO: Perform an integrity check around that and indeed if it's an ordinary
                #       leaderboard presentation check on performance between asat=time (which 
                #       reads Performance) and asat=None (which reads Rating).
                # TODO: Consider if performance here improves with a prefetch or such noting that
                #       game.play_counts and game.session_list might run faster with one query rather 
                #       than two.
                
                # FIXME: Here is the sweet spot.
                #        From here we build a snapshot tuple. This is what we can find in the cache rather 
                #        than build so it boils down here to getting the snapshot from chache or building 
                #        it. 
                
                log.debug(f"\tBoard/Snapshot for session {board.id} at {localize(localtime(board.date_time))}.")                     

                # First fetch the global (unfiltered) snapshot for this board/session
                if board.pk in lb_cache:
                    full_snapshot = lb_cache[board.pk]
                    log.debug(f"\t\tFound it in cache!")                     
                else:
                    log.debug(f"\t\tBuilding it!")                     
                    full_snapshot = board.leaderboard_snapshot
                    if full_snapshot:
                        lb_cache[board.pk] = full_snapshot

                # TODO, consider not relying on a firm index here, either providing 
                # indexes as an enumeration or using a dict? snapshot would habe 
                # to be turned into a tuple or list of dict values to be inserted into
                # a the leaderboards tuple for this game though. Unless the whole 
                # structure moved more toward dicts (and dicts passed well as JSON 
                # to context and AJAX callers?
                #
                # Alternately make snapshots a class with attrs? What are the 
                # consequences of that for caching, JSONifying to context and 
                # AJAX callers?
                log.debug(f"\tGot the full board/snapshot. It has {len(full_snapshot[8])} players on it.")
                
                # Then filter and annotate it in context of lo
                if full_snapshot:
                    lb = full_snapshot[8]
                    
                    snapshot = lo.apply(full_snapshot)
                    lbf = snapshot[8]

                    log.debug(f"\tGot the filtered/annotated board/snapshot. It has {len(snapshot[8])} players on it.")
            
                    # Counts supplied in the full_snapshot are global and we want to constrain them to
                    # the leagues in question.
                    #
                    # Playcounts are always across all the leagues specified.
                    #   if we filter games on any leagues, the we list games played by any of the leagues
                    #        and play count across all the leagues makes sense.
                    #   if we filter games on all leagues, then list only games played by all the leagues present
                    #        and it still makes sense to list a playcount across all those leagues.
                    
                    counts = game.play_counts(leagues=lo.game_leagues, asat=board.date_time)                    
                    
                    # We add the previous rank if available to each players tuple in the leaderboard
                    if lbf and previous_rank:
                        for p in range(len(lbf)):
                            player_tuple = lbf[p]
                            pk = player_tuple[1]
                            if pk in previous_rank:
                                lbf[p] = player_tuple + (previous_rank[pk],)

                    
                    # snapshot 0 and 1 are the session PK and localized time
                    # snapshot 2 and 3 are the counts we updated with lo.league sensitivity
                    # snapshot 4, 5, 6 and 7 are session players, HTML header and HTML analyis pre and post respectively
                    # snapshot 8 is the leaderboard (a tuple of player tuples
                    # The HTML header and analyses use flex player naming and expect client side to render 
                    # appropriately. See Player.name() for flexi naming standard.
                    snapshot = (snapshot[0:2] 
                             +  (counts['total'], counts['sessions']) 
                             +  snapshot[4:8] 
                             +  (lbf,))
                                    
                    # Clear and rebuild the previouse_rank dictionary with this boards' lb values
                    # We use the wholeleaderboard hear (lb) not the player filtered leaderboard (lbf)
                    previous_rank = {}
                    for p in lb:
                        rank = p[0]
                        pk = p[1]
                        previous_rank[pk] = rank
                        
                    snapshots.append(snapshot)                

            # For this game we now have all the snapshots and we can save a game tuple
            # to the leaderboards list. We must have at least one snapshot, because we
            # ignored all games with 0 recorded sessions already in buiulding our list 
            # games. So if we don't have any something really bizarre has happened/  
            assert len(snapshots) > 0, "Internal error: Game was in list for which no leaderboard snapshot was found. It should not have been in the list."

            # We reverse the snapshots back to newest first oldest last                                
            snapshots.reverse()
            
            # Then build the game tuple with all its snapshots
            leaderboards.append((game.pk, game.BGGid, game.name, snapshots))

    if settings.USE_LEADERBOARD_CACHE:
        request.session["leaderboard_cache"] = lb_cache

    # raw is asked for on a standard page load, when a true AJAX request is underway it's false.
    return leaderboards if raw else HttpResponse(json.dumps((title, subtitle, lo.as_dict(), leaderboards), cls=DjangoJSONEncoder))

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
            log.debug(f"referrer = {request.META.get('HTTP_REFERER')}")
            session_keys = list(request.session.keys())
            for key in session_keys:
                del request.session[key]
            return HttpResponse("<script>window.history.pushState('', '', '/session_cleared');</script>")

        # Check for the timezone
        if "timezone" in request.POST:
            log.debug(f"Timezone = {request.POST['timezone']}")
            request.session['timezone'] = request.POST['timezone']
            activate(request.POST['timezone'])

        if "utcoffset" in request.POST:
            log.debug(f"UTC offset = {request.POST['utcoffset']}")
            request.session['utcoffset'] = request.POST['utcoffset']

        if "location" in request.POST :
            log.debug(f"location = {request.POST['location']}")
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
            log.debug(f"League = {request.POST['league']}")
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

    title = "Database Integrity Check"
    
    assertion_failures = [] # Assertion failures
    
    print("Checking all Performances for internal integrity.", flush=True)
    for P in Performance.objects.all():
        fails = P.check_integrity()

        print(f"Performance {P.id}: {P}. {len(fails)} assertion failures.", flush=True)
        for f in fails:
            print(f"\t{f}", flush=True)
        
        if fails:
            assertion_failures += fails
 
    print("Checking all Ranks for internal integrity.", flush=True)
    for R in Rank.objects.all():
        fails = R.check_integrity()

        print(f"Rank {R.id}: {R}. {len(fails)} assertion failures.", flush=True)
        for f in fails:
            print(f"\t{f}", flush=True)
        
        if fails:
            assertion_failures += fails
     
    print("Checking all Sessions for internal integrity.", flush=True)
    for S in Session.objects.all():
        fails = S.check_integrity(True)
        
        print(f"Session {S.id}: {S}. {len(fails)} assertion failures.", flush=True)
        for f in fails:
            print(f"\t{f}", flush=True)
        
        if fails:
            assertion_failures += fails

    print("Checking all Ratings for internal integrity.", flush=True)
    for R in Rating.objects.all():
        fails = R.check_integrity()

        print(f"Rating {R.id}: {R}. {len(fails)} assertion failures.", flush=True)
        for f in fails:
            print(f"\t{f}", flush=True)
        
        if fails:
            assertion_failures += fails

    now = datetime.now()
    summary = '\n'.join(assertion_failures)
    result = f"<html><body<p>{title}</p><p>It is now {now}.</p><p><pre>{summary}</pre></p></body></html>"

    return HttpResponse(result)

def view_RebuildRatings(request):
    CuserMiddleware.set_user(request.user)
    
    if 'game' in request.GET and request.GET['game'].isdigit():
        try:
            game = Game.objects.get(pk=request.GET['game'])
        except Game.DoesNotExist:
            game = None
    else:
        game = None
             
    if 'from' in request.GET:
        try:
            From = decodeDateTime(request.GET['from'])
        except:
            From = None 
    else:
        From = None
    
    html = rebuild_ratings(game, From)
    
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

def rebuild_play_and_victory_counts():
    '''
    Performance objects contain play and victory counts which are therer for efficiency.
    But if they ever go awry, they can be rebuild from recorded session data and this
    function does that across the whole database.
    '''
    sessions = Session.objects.all().order_by('date_time')
    
    print(f"Rebuilding perfomance play and victory counts for {sessions.count()} sessions.", flush=True)

    for session in sessions:
        for performance in session.performances.all():
            if performance.pk == 900:
                print("Gotcha.", flush=True)
            
            previous_performance = performance.previous_play

            if previous_performance:
                performance.play_number = previous_performance.play_number + 1
                performance.victory_count = previous_performance.victory_count + 1 if performance.is_victory else previous_performance.victory_count
            else:
                performance.play_number = 1
                performance.victory_count = 1 if performance.is_victory else 0
            
            performance.__bypass_admin__ = True
            performance.save()
            print(f"Fixed performance {performance.id} in session {session.id} having play_number {performance.play_number} and victory_count {performance.victory_count} for {performance.player} at game {performance.game}.", flush=True)
            
    print("Done.", flush=True)
    

from django.apps import apps
def view_Fix(request):

    rebuild_play_and_victory_counts()
    
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

    # Found a Performance corruption that needed fixing, a play_number was wrong
    # Quick rebuild of them all!


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
#     sessions = Session.objects.all()
#     
#     activate('Australia/Hobart')
# 
#     # Did this on dev database. Seems to have worked a charm.
#     for session in sessions:
#         dt_raw = session.date_time
#         dt_local = localtime(dt_raw)
#         error = dt_local.tzinfo._utcoffset
#         dt_new = dt_raw - error
#         dt_new_local = localtime(dt_new)
#         log.debug(f"Session: {session.pk}    Raw: {dt_raw}    Local:{dt_local}    Error:{error}  New:{dt_new}    New Local:{dt_new_local}")
#         session.date_time = dt_new_local
#         session.save()
#         
#     # The rating model has two DateTimeFields that are wrong in the same way, but thee can be fixed by rebuilding ratings.
#     pass  
#         
#     # Now for every model that we have that derives from AdminModel we need to updated we have two fields:
#     #     created_on
#     #     last_edited_on
#     # That we need to tweak the same way.
#     
#     # We can do this by looping all our models and checking for those fields.  
#     models = apps.get_app_config('Leaderboards').get_models()
#     for model in models:
#         if hasattr(model, 'created_on') or hasattr(model, 'last_edited_on'):
#             for obj in model.objects.all():
#                 if hasattr(obj, 'created_on'): 
#                     dt_raw = obj.created_on
#                     dt_local = localtime(dt_raw)
#                     error = dt_local.tzinfo._utcoffset
#                     dt_new = dt_raw - error
#                     dt_new_local = localtime(dt_new)
#                     log.debug(f"{model._meta.object_name}: {obj.pk}    created    Raw: {dt_raw}    Local:{dt_local}    Error:{error}  New:{dt_new}    New Local:{dt_new_local}")
#                     obj.created_on = dt_new_local 
# 
#                 if hasattr(obj, 'last_edited_on'): 
#                     dt_raw = obj.last_edited_on
#                     dt_local = localtime(dt_raw)
#                     error = dt_local.tzinfo._utcoffset
#                     dt_new = dt_raw - error
#                     dt_new_local = localtime(dt_new)
#                     log.debug(f"{model._meta.object_name}: {obj.pk}    edited     Raw: {dt_raw}    Local:{dt_local}    Error:{error}  New:{dt_new}    New Local:{dt_new_local}")
#                     obj.last_edited_on = dt_new_local
#                 
#                 obj.save()
        
#     for session in sessions:
#         dt_raw = session.date_time
#         dt_local = localtime(dt_raw)
#         dt_naive = make_naive(dt_local)
#         ctz = get_current_timezone()
#         log.debug(f"dt_raw: {dt_raw}    ctz;{ctz}    dt_local:{dt_local}    dt_naive:{dt_naive}")        
    
    html = "Success"
    
    return HttpResponse(html)

def view_Kill(request, model, pk):
    CuserMiddleware.set_user(request.user)

    m = class_from_string('Leaderboards', model)
    o = m.objects.get(pk=pk)
    o.delete()
    
    html = "Success"
    
    return HttpResponse(html)

def rebuild_ratings(Game=None, From=None):
    activate(settings.TIME_ZONE)

    title = "Rebuild of ratings"
    if not Game and not From:
        title = "Rebuild of ALL ratings"
    else:
        if Game:
            title += f" for {Game.name}" 
        if From:
            title += f" from {From}" 
        
    pr = cProfile.Profile()
    pr.enable()
    result = Rating.rebuild(Game, From)
    pr.disable()
    
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats()
    result += s.getvalue()
        
    now = datetime.now()

    return f"<html><body<p>{title}</p><p>It is now {now}.</p><p><pre>{result}</pre></p></body></html>"

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
