import cProfile, pstats, io
import re, json, pytz

from re import RegexFlag as ref  # Specifically to avoid a PyDev Error in the IDE.
from datetime import datetime, date, timedelta
from html import escape

from django_generic_view_extensions.views import LoginViewExtended, TemplateViewExtended, DetailViewExtended, DeleteViewExtended, CreateViewExtended, UpdateViewExtended, ListViewExtended
from django_generic_view_extensions.util import class_from_string
from django_generic_view_extensions.datetime import datetime_format_python_to_PHP, decodeDateTime
from django_generic_view_extensions.options import  list_display_format, object_display_format
from django_generic_view_extensions.context import add_timezone_context, add_debug_context

from cuser.middleware import CuserMiddleware

from CoGs.logging import log
from .models import Team, Player, Game, League, Session, Rank, Performance, Rating, ChangeLog, RebuildLog, LEADERBOARD_STYLE, ALL_LEAGUES, ALL_PLAYERS, ALL_GAMES  # , Location
from .leaderboards import leaderboard_options, NameSelections, LinkSelections
from .BGG import BGG

from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.formats import localize
from django.utils.timezone import is_aware, make_aware, make_naive, activate, localtime
from django.http.response import HttpResponse, HttpResponseRedirect  # , JsonResponse
from django.urls import reverse, reverse_lazy  # , resolve
from django.contrib.auth.models import User, Group
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.forms.models import ModelChoiceIterator, ModelMultipleChoiceField
from django.conf import settings

from dal import autocomplete

# from numpy import rank

# TODO: Add account security, and test it
# TODO: Once account security is in place a player will be in certain leagues,
#      restrict some views to info related to those leagues.
# TODO: Add testing: https://docs.djangoproject.com/en/1.10/topics/testing/tools/

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


def pre_save_handler(self):
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
    the configured post processor (post_save_pre_commit_handler below).
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
            if settings.DEBUG:
                log.debug(m)

    def STR(r):
        '''Quick and dirty pretty-printer for tuples and lists of tuples requests (as the repr defaults suck)'''
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
                if not j == len(t) - 1: s += ', '
            s += ')'
            if not i == len(R) - 1: s += ', '
        if isinstance(r, list): s += ']'
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
        new_time = parse_datetime(str_time)  # Fails with exception or None if invalid

        # We need a TZ naive version for comparising against naive datetimes.
        if is_aware(new_time):
            nt = make_naive(localtime(new_time, timezone.utc))
        else:
            nt = new_time
            new_time = make_aware(new_time)

        # The time of the session cannot be in the future of course.
        if new_time > localtime():
            # TODO: there's a bug here in the return. It returns players and ranks onto the error form badly.
            # As in the disappear from the returned form.
            # Methinks we want to translate form fields back into Session context as part of bailing
            self.form.add_error("date_time", f"Please choose a time in the past.")
            return None

        str_game = self.form.data['game']  # Submitted game ID
        new_game = Game.objects.get(pk=int(str_game))  # Fails with exception if bad input

        # Grab the players and play_weights
        # And check for player uniqueness now
        performances = int(self.form.data['Performance-TOTAL_FORMS'])
        new_players = []
        new_weights = []
        seen_players = set()
        for p in range(performances):
            str_player = self.form.data[f'Performance-{p}-player']
            try:
                int_player = int(str_player)
                player = Player.objects.get(pk=int_player)
            except:
                self.form.add_error(None, f"Please select a registered player.")
                return None

            # If we have a player dup0licated bail now (form.is_valid will
            # fail after we've added this error)
            if int_player in seen_players:
                # TODO: there's a bug here in the return. It returns players and ranks onto the eroro form badly.
                # Methinks we want to translate form fields back into Session context as part of bailing
                self.form.add_error(None, f"Players must be unique. {player.name()} used more than once.")
                return None

            new_players.append(player)
            str_weight = self.form.data[f'Performance-{p}-partial_play_weighting']
            new_weights.append(float(str_weight))
            seen_players.add(int_player)

        # Rebuild nothing by default
        rebuild = None
        reason = None

        # A rebuild of ratings is triggered under any of the following circumstances:
        #
        # A rebuild request goes to the post_processor for the submission (runs after
        # the submisison was saved. It takes the form of a list of sessions to rebuild
        # or a queryset of them,
        #
        # 1. It's a new session and any of the players involved have future sessions
        #    recorded already.
        if isinstance(self, CreateViewExtended):
            output(f"New Session")

            # Check to see if this is the latest play for each player
            is_latest = True
            for player in new_players:
                rating = Rating.get(player, new_game)
                if new_time < rating.last_play:
                    is_latest = False
                    reason = f"New Session. Not latest session for {player.complete_name} playing {new_game.name} "

            if not is_latest:
                rebuild = new_game.future_sessions(new_time, new_players)
                output(f"\tRequesting a rebuild of ratings for {len(rebuild)} sessions: {escape(str(rebuild))}")
                output(f"\t\tBecause: {reason}")
                return {'rebuild': rebuild, 'reason': reason}
            else:
                output(f"Is the latest session of {new_game} for all of {', '.join([str(p) for p in new_players[:-1]])} and {str(new_players[-1])}")
                return None

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
            old_players = old_session.players

            output(f"Editing session {old_session.pk}")
            J = '\n\t\t'  # A log message list item joiner

            # Build a list of all players affected by this submission
            all_players = list(set(old_players) | set(new_players))
            output(f"\tOld players: {escape(', '.join([str(p) for p in old_players]))}")
            output(f"\tNew players: {escape(', '.join([str(p) for p in new_players]))}")
            output(f"\tAll players: {escape(', '.join([str(p) for p in all_players]))}")

            # If the game was changed we will request a rebuild of both games
            # regardless of any other considerations. Both their rating trees
            # need rebuilding.
            if not new_game == old_session.game:
                old_sessions = old_session.game.future_sessions(old_session.date_time, old_session.players)
                new_sessions = new_game.future_sessions(new_time, new_players)
                rebuild = sorted(old_sessions + new_sessions, key=lambda s: s.date_time)
                reason = f"Session Edit. Game changed (from {old_session.game.name} to {new_game.name}."

                output(f"\tRequesting a rebuild of ratings for {len(rebuild)} sessions:{J}{J.join([s.__rich_str__() for s in rebuild])}")
                output(f"\t\tBecause: {reason}")

            else:
                # Divine the play mode
                if 'team_play' in self.form.data:
                    assert 'num_teams' in self.form.data, "Bad form submission, team_play on but no num_teams."
                    new_team_play = True
                else:
                    assert 'num_players' in self.form.data, "Bad form submission, team_play off but no num_players."
                    new_team_play = False

                # Set up some rebuild shorthands
                old_game = old_session.game
                old_time = old_session.date_time
                from_time = min(old_time, new_time)

                # If the play mode changed rebuild this games rating tree from this session on.
                if not new_team_play == old_session.team_play:
                    rebuild = old_game.future_sessions(from_time, all_players)
                    reason = f"Session Edit. Play mode changed (from {'Team' if old_session.team_play else 'Individual'} to {'Team' if new_team_play else 'Individual'})."

                    output(f"\tRequesting a rebuild of ratings for {len(rebuild)} sessions:{J}{J.join([s.__rich_str__() for s in rebuild])}")
                    output(f"\t\tBecause: {reason}")

                # If any players were added, remove or changed, rebuild this games rating tree from this session on.
                elif not set(new_players) == set(old_players):
                    rebuild = old_game.future_sessions(from_time, all_players)
                    reason = f"Session Edit. Players changed (from {sorted([p.complete_name for p in old_players])} to {sorted([p.complete_name for p in new_players])})."

                    output(f"\tRequesting a rebuild of ratings for {len(rebuild)} sessions:{J}{J.join([s.__rich_str__() for s in rebuild])}")
                    output(f"\t\tBecause: {reason}")

                # Otherwise check for other rating impacts
                else:
                    # Check for a change in ranks

                    # As no players have been added or deleted and
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

                    if not new_ranks == old_ranks:
                        rebuild = old_game.future_sessions(from_time, all_players)
                        reason = f"Session Edit. Ranks changed (from {old_ranks} to {new_ranks})."

                        output(f"\tRequesting a rebuild of ratings for {len(rebuild)} sessions:{J}{J.join([s.__rich_str__() for s in rebuild])}")
                        output(f"\t\tBecause: {reason}")
                    else:
                        # Check for a partial play weighting change on any player
                        old_weights = [old_session.performance(p).partial_play_weighting for p in new_players]

                        if not new_weights == old_weights:
                            rebuild = old_game.future_sessions(from_time, all_players)
                            reason = f"Session Edit. Weights changed (from {old_weights} to {new_weights})."

                            output(f"\tRequesting a rebuild of ratings for {len(rebuild)} sessions:{J}{J.join([s.__rich_str__() for s in rebuild])}")
                            output(f"\t\tBecause: {reason}")
                        else:
                            # Check for a Session sequence change for any player
                            for p in new_players:
                                prev_sess = old_session.previous_session(p)
                                foll_sess = old_session.following_session(p)

                                # min and max are TZ unaware (naive), and session.date_time is UTC
                                # So we make session.date_time naive for the comparison to come.
                                time_window = (make_naive(prev_sess.date_time) if prev_sess else datetime.min,
                                               make_naive(foll_sess.date_time) if foll_sess else datetime.max)

                                if not time_window[0] < nt < time_window[1]:
                                    rebuild = old_game.future_sessions(from_time, all_players)

                                    # The list of sessions in rebuild may contain the current session
                                    # because it has not yet been saved with new_time, it sits in the database
                                    # under old_time. from_time is the earlier of new_time and old_time and so
                                    # if new_time is earlier than old_time then the the current session (the
                                    # one being saved here) will appear in the list.
                                    #
                                    # It can safely be removed from the list because the current session will
                                    # have its ratings updated before a rebuild is triggered and the rebuild
                                    # will no longer see this session nor need to (as it's been brought forward).
                                    if new_time < old_time:
                                        for i, s in enumerate(rebuild):
                                            if s.pk == old_session.pk:
                                                rebuild.pop(i)
                                                break

                                    if nt < time_window[0]:
                                        reason = f"Session Edit. Sequence changed (session moved to {new_time}, before {prev_sess.date_time_local} when {p.complete_name} also played {new_game.name})."
                                    else:
                                        reason = f"Session Edit. Sequence changed (session moved to {new_time}, after {foll_sess.date_time_local} when {p.complete_name} also played {new_game.name})."

                                    output(f"\tRequesting a rebuild of ratings for {len(rebuild)} sessions:{J}{J.join([s.__rich_str__() for s in rebuild])}")
                                    output(f"\t\tBecause: {reason}")
                                else:
                                    output(f"\tNo rating impact found. No rebuild requested.")

        if debug_only:
            html += "</pre>\n</section>\n"
            return {'debug_only': html}
        elif rebuild:
            # Return the kwargs for the next handler
            return {'rebuild': rebuild, 'reason': reason}
        else:
            return None


def post_save_pre_commit_handler(self, rebuild=None, reason=None):
    '''
    When a model form is POSTed, this function is called AFTER the form is saved.

    self is an instance of CreateViewExtended or UpdateViewExtended.

    It will be running inside a transaction and can bail with an IntegrityError if something goes wrong
    achieving a rollback.

    This is executed inside a transaction which is important if it is trying to update
    a number of models at the same time that are all related. The integrity of relations after
    the save should be tested and if not passed, then throw an IntegrityError.

    :param rebuild: A list of sessions to rebuild.
    :param reason: A string. The reason for a rebuild if any is provided.
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

        if settings.DEBUG:
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
                    assert int(rank_id) == rank.pk, f"Save error: Saved Rank has different ID to submitted form Rank ID! Rank ID {int(rank_id)} was submitted and Rank ID {rank.pk} has the same rank as submitted: {rank_rank}."

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

                if settings.DEBUG:
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
                    rank.team = team
                    rank.save()

                    if settings.DEBUG:
                        log.debug(f"\tCreated new team for {team.players} with name: {team.name}")

                # If one is found, then link it to the approriate rank object and
                # check its name against the submission (updating if need be)
                elif len(teams) == 1:
                    team = teams[0]

                    # If the name changed and is not a placeholder of form "Team n" save it.
                    if new_name and not re.match("^Team \d+$", new_name, ref.IGNORECASE) and new_name != team.name:
                        if settings.DEBUG:
                            log.debug(f"\tRenaming team for {team.players} from {team.name} to {new_name}")

                        team.name = new_name
                        team.save()

                    # If the team is not linked to the rigth rank, fix the rank and save it.
                    if (rank.team != team):
                        rank.team = team
                        rank.save()

                        if settings.DEBUG:
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
        session.clean_ranks()

        # update ratings on the saved session.
        Rating.update(session)

        # If a rebuild request arrived from the preprocessors honour that
        # It means this submission is known to affect "future" sessions
        # already in the database. Those future (relative to the submission)
        # sessions need a ratings rebuild.
        if rebuild:
            J = '\n\t\t'  # A log message list item joiner
            if settings.DEBUG:
                log.debug(f"A ratings rebuild has been requested for {len(rebuild)} sessions:{J}{J.join([s.__rich_str__() for s in rebuild])}")

            # This saves a RebuildLog entry and a ChangeLog entry
            clog = Rating.rebuild(Sessions=rebuild, Reason=reason, Trigger=session)

        # If not rebuild for edits only, save a Change Log entry
        elif isinstance(self, UpdateViewExtended):
            clog = ChangeLog.create(session)
            clog.save()
        else:
            clog = None

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

        # If there was a change logged (and/or a rebuild triggered)
        get_params = ""
        if clog:
            get_params = f"?changed={clog.pk}"

        self.success_url = reverse_lazy('impact', kwargs={'model': 'Session', 'pk': session.pk}) + get_params

        # No args to pass to the next handler
        return None


def pre_delete_handler(self):
    '''
    Before deleting am object this is called. It can return a kwargs dict that is passed to
    the post delete handler after the object is deleted.
    '''
    model = self.model._meta.model_name

    if model == 'session':
        # Before deleting a session capture everything we need to know about it for the post delete handler
        session = self.object

        # The session won't exist after it's deleted, so grab everythinhg the post delete handler
        # wants to know about a session to do its work.
        post_kwargs = {'pk': session.pk, 'game': session.game, 'players': session.players, 'victors': session.victors}

        g = session.game
        dt = session.date_time

        if settings.DEBUG:
            log.debug(f"Deleting Session {session.pk}:")

        # Check to see if this is the latest play for each player
        is_latest = True
        for p in session.players:
            r = Rating.get(p, g)
            if dt < r.last_play:
                is_latest = False

        # Request no ratings rebuild by default
        rebuild = None

        # A rebuild of ratings is triggered if we're deleting a session that is not
        # the latest session in that game for all its players. All future sessions
        # for those players need a ratings rebuild
        if not is_latest:
            rebuild = g.future_sessions(dt, session.players)
            if settings.DEBUG:
                log.debug(f"\tRequesting a rebuild of ratings for {len(rebuild)} sessions: {str(rebuild)}")
            post_kwargs['rebuild'] = rebuild
        else:
            if settings.DEBUG:
                log.debug(f"\tIs the latest session of {g} for all of {', '.join(session.players)}")

        return post_kwargs
    else:
        return None


def post_delete_handler(self, pk=None, game=None, players=None, victors=None, rebuild=None):
    '''
    After deleting an object this is called (before the transaction is committed, so raising an
    exception can force a rollback on the delete.

    :param players:    a set of players that were in a session being deleted
    :param victors:    a set of victors in the session being deleted
    :param rebuild:    a list of sessions to rebuild ratings for if a session is being deleted
    '''
    model = self.model._meta.model_name

    if model == 'session':
        # Execute a requested rebuild
        if rebuild:
            reason = f"Session {pk} was deleted."
            Rating.rebuild(Sessions=rebuild, Reason=reason)
        else:
            # A rebuld of ratings finsihes with updated ratings)
            # If we have no rebuild (by implication we just deleted
            # the last session in that games tree for those players)
            # and so we need to update the ratings ourselves.
            for p in players:
                r = Rating.get(p, game)
                r.reset()
                r.save()


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


def html_selector(model, id, default=0, placeholder="", attrs={}):  # @ReservedAssignment
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
            context['game_individual_play'] = json.dumps(game.individual_play)  # Python True/False, JS true/false
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
    # fields = '__all__'
    extra_context_provider = extra_context_provider
    pre_save = pre_save_handler
    pre_commit = post_save_pre_commit_handler
    #
    # TODO The success URL should go a new page, an impact view which
    # shows the impact of the added board. Here's a JSON URL that gets it:
    # http://127.0.0.1:8000/json/leaderboards/?no_defaults&games_ex=29&player_leagues_any=1&as_at=2021-01-16+13-30-00+0000&links=BGG&details=true&analysis_pre=true&analysis_post=true&show_delta=true&ignore_cache
    # Do this in Add and Edit.
    #
    # TODO: Once that's done a second board which shows the impact on the latest leaderboards (if this
    # add or edit was not latest) Appropriate headers and all, the latest board impact would be not
    # compared to the previous session temporally but to the ratings backup taken before a rebuild
    # was tricggered. To wit the BackupRating has a diff method but Game.leaderboard I think
    # needs to be able to build one from Rating or BackupRating and the ajax view be able to make
    # a request for a games leaderboard lastest from Rating or BackupRating from whcih it can build a
    # Leaderboard with Rank Deltas.


class view_Edit(LoginRequiredMixin, UpdateViewExtended):
    # TODO: Must be atomic and in such a way that it tests if changes have integrity.
    #       notably if a session changes from indiv to team mode say or vice versa,
    #       there is a notable impact on rank objects that could go wrong and we should
    #       check integrity.
    #       Throw:
    #        https://docs.djangoproject.com/en/1.10/ref/exceptions/#django.db.IntegrityError
    #       if an integrity error is found in such a transaction (or any transaction).
    template_name = 'CoGs/form_data.html'
    operation = 'edit'
    extra_context_provider = extra_context_provider
    pre_save = pre_save_handler
    pre_commit = post_save_pre_commit_handler


class view_Delete(LoginRequiredMixin, DeleteViewExtended):
    # TODO: When deleting a session need to check for ratings that refer to it as last_play or last_win
    #        and fix the reference or delete the rating.
    template_name = 'CoGs/delete_data.html'
    operation = 'delete'
    format = object_display_format()
    extra_context_provider = extra_context_provider
    pre_delete = pre_delete_handler
    post_delete = post_delete_handler


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
# Success URL views
#===============================================================================


def view_Impact(request, model, pk):
    '''
    A view to show the impact of submitting a session.

    :param request:    A Django request object
    :param model:      The name of a model (only 'session' supported at present)
    :param pk:         The Primary key of the object of model (i.e of the session)
    '''
    CuserMiddleware.set_user(request.user)

    m = class_from_string('Leaderboards', model)
    o = m.objects.get(pk=pk)

    if model == "Session":
        # TODO: on creating new session we don't save a Changelog. We can however pass the impact
        # via a session variable, and of course also compare against latest board too, they are always available.

        # TODO: If not is_latest )future_sessions.length > 0) add also a before and after view of latest ratings.

        snapshot_after = o.leaderboard_snapshot
        snapshot_before = None
        baseline = None

        op = o.previous_session()
        if op:
            snapshot_before = op.leaderboard_snapshot
            snapshot_after = augment_with_deltas(snapshot_after, snapshot_before)

            opp = op.previous_session()

            if opp:
                baseline = o.previous_session().leaderboard_snapshot
                snapshot_before = augment_with_deltas(snapshot_before, baseline)

        snapshots = [snapshot_after]
        if snapshot_before: snapshots += [snapshot_before]
        if baseline: snapshots += [baseline]

        islatest = o.is_latest
        isfirst = o.is_first

        if not islatest:
            latest = o.game.leaderboard(style=LEADERBOARD_STYLE.rich)
        else:
            latest = ()

        try:
            changed = request.GET.get("changed", None)

            # If no change is provided in the GET params try and get the last logged change for this session.
            if not changed:
                changed = ChangeLog.objects.filter(session=o).order_by("-created_on").first().pk

            clog = ChangeLog.objects.get(pk=int(changed))
        except:
            clog = None

        # TODO: Include more info for the template to report How many players ratings were affected.
        c = {"model": m,
             "model_name": model,
             "model_name_plural": m._meta.verbose_name_plural,
             "object_id": o.id,
             "game": o.game,
             "date_time": o.date_time,
             "is_latest": islatest,
             "is_first": isfirst,
             "diagnose": len(snapshot_after) > 9,  # Snapshot tuples have 9 elements, or 10 if a diagnosis board is included
             "leaderboard": json.dumps(o.game.wrapped_leaderboard(latest, snap=False), cls=DjangoJSONEncoder),
             "leaderboard_snapshots": json.dumps(o.game.wrapped_leaderboard(snapshots, snap=True), cls=DjangoJSONEncoder),
             "changed": clog}

        return render(request, 'CoGs/view_session_impact.html', context=c)
    else:
        return HttpResponseRedirect(reverse_lazy('view', kwargs={'model':model, 'pk':pk}))

#===============================================================================
# The Leaderboards view. What it's all about!
#===============================================================================

# Define defaults for the view inputs


def view_Leaderboards(request):
    '''
    The raison d'etre of the whole site, this view presents the leaderboards.
    '''
    # Fetch the leaderboards
    # We always request raw (so it's not JSON but Python data
    leaderboards = ajax_Leaderboards(request, raw=True)

    session_filter = request.session.get('filter', {})
    tz = pytz.timezone(request.session.get("timezone", "UTC"))
    lo = leaderboard_options(request.GET, session_filter, tz)
    default = leaderboard_options(ufilter=session_filter)

    (title, subtitle) = lo.titles()

    # selectthe widget defaults
    leagues = lo.game_leagues if lo.game_leagues else request.session.get('filter', {}).get('league', [])
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


def augment_with_deltas(snapshot, baseline):
    '''
    Given a leaderboard snapshot and a baseline to compare it against, will
    augment the snapshot with a delta measure.

    A leaderboard snapshot is a list of tuples with a contents defined
    by Game.leaderboard

    :param snapshot:    a leaderboard snapshot
    :param baseline:    a leaderboard snapshot to compare with
    '''

    # Extract the leaderboards from the snapshot and baseline.
    ilb = 8
    lb_snapshot = list(snapshot[ilb])
    lb_baseline = baseline[ilb]

    previous_rank = {}
    # The 8th element of a nsapshot tuple has the leaderboard!
    for p in lb_baseline:
        rank = p[0]
        pk = p[1]
        previous_rank[pk] = rank

    for r, p in enumerate(lb_snapshot):
        rank = p[0]
        pk = p[1]
        if pk in previous_rank:
            lb_snapshot[r] = p + (previous_rank[pk],)

    # Use a list as tuple is not mutable
    augmented_snapshot = list(snapshot)
    augmented_snapshot[ilb] = lb_snapshot

    # Back tot uple with frozen result
    return tuple(augmented_snapshot)


def ajax_Leaderboards(request, raw=False, baseline=True):
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
    session_filter = request.session.get('filter', {})
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
    # # FOR ALL THE GAMES WE SELECTED build a leaderboard (with any associated snapshots)
    #######################################################################################################
    if settings.DEBUG:
        log.debug(f"Preparing leaderboards for {len(games)} games.")

    leaderboards = []
    for game in games:
        if settings.DEBUG:
            log.debug(f"Preparing leaderboard for: {game}")

        # FIXME: Here is a sweet spot. Some or all sessions are available in the
        #        cache already. We need the session only for:
        #
        #  1) it's datetime - cheap
        #  2) to build the three headers
        #     a) session player list     - cheap
        #     b) analysis pre            - expensive
        #     c) analysis post           - expensive
        #
        # We want to know if the session is already in a cached snapshot.

        # Note: the snapshot query does not constrain sessions to the same location as
        # as does the game query. once we have the games that were played at the event,
        # we're happy to include all sessions during the event regardless of where. The
        # reason being that we want to see evoluton of the leaderboards during the event
        # even if some people outside of the event are playing it and impacting the board.
        boards = lo.snapshot_queryset(game, baseline)

        if boards:
            #######################################################################################################
            # # BUILD EACH SNAPSHOT BOARD - from the sessions we recorded in "boards"
            #######################################################################################################
            #
            # From the list of boards (sessions) for this game build Tier2 and Tier 3 in the returned structure
            # now. That is assemble the actualy leaderbards after each of the collected sessions.

            if settings.DEBUG:
                log.debug(f"\tPreparing {len(boards)} boards/snapshots.")

            # We want to build a list of snapshots to add to the leaderboards list
            snapshots = []

            # We keep a baseline snapshot (the rpevious one) for augfmenting snapshots with
            # (it adds a rank_delat entry, change in rank from the baseline)
            baseline = None

            # For each board/snapshot of this game ...
            # In temporal order so we can construct the "previous rank"
            # element on the fly, but we're reverse it back when we add the
            # collected snapshots to the leaderboards list.
            for board in reversed(boards):
                # If as_at is now, the first time should be the last session time for the game
                # and thus should translate to the same as what's in the Rating model.
                #
                # TODO: Perform an integrity check around that and indeed if it's an ordinary
                #       leaderboard presentation check on performance between asat=time (which
                #       reads Performance) and asat=None (which reads Rating).
                #
                # TODO: Consider if performance here improves with a prefetch or such noting that
                #       game.play_counts and game.session_list might run faster with one query rather
                #       than two.

                if settings.DEBUG:
                    log.debug(f"\tBoard/Snapshot for session {board.id} at {localize(localtime(board.date_time))}.")

                # First fetch the global (unfiltered) snapshot for this board/session
                if board.pk in lb_cache:
                    full_snapshot = lb_cache[board.pk]
                    if settings.DEBUG:
                        log.debug(f"\t\tFound it in cache!")

                else:
                    if settings.DEBUG:
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
                if settings.DEBUG:
                    log.debug(f"\tGot the full board/snapshot. It has {len(full_snapshot[8])} players on it.")

                # Then filter and annotate it in context of lo
                if full_snapshot:
                    # lb = full_snapshot[8]

                    snapshot = lo.apply(full_snapshot)
                    lbf = snapshot[8]

                    if settings.DEBUG:
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

                    # snapshot 0 and 1 are the session PK and localized time
                    # snapshot 2 and 3 are the counts we updated with lo.league sensitivity
                    # snapshot 4, 5, 6 and 7 are session players, HTML header and HTML analyis pre and post respectively
                    # snapshot 8 is the leaderboard (a tuple of player tuples)
                    # The HTML header and analyses use flexi player naming and expect client side to render
                    # appropriately. See Player.name() for flexi naming standards.
                    snapshot = (snapshot[0:2]
                             +(counts['total'], counts['sessions'])
                             +snapshot[4:8]
                             +(lbf,))

                    # Augmment the snapshot with the delta from baseline if we have one
                    if baseline:
                        snapshot = augment_with_deltas(snapshot, baseline)

                    # Store the baseline for next iteration
                    baseline = snapshot

                    snapshots.append(snapshot)

            # For this game we now have all the snapshots and we can save a game tuple
            # to the leaderboards list. We must have at least one snapshot, because we
            # ignored all games with 0 recorded sessions already in buiulding our list
            # games. So if we don't have any something really bizarre has happened/
            assert len(snapshots) > 0, "Internal error: Game was in list for which no leaderboard snapshot was found. It should not have been in the list."

            # We reverse the snapshots back to newest first oldest last
            snapshots.reverse()

            # Then build the game tuple with all its snapshots
            leaderboards.append(game.wrapped_leaderboard(snapshots, snap=True))

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


def ajax_BGG_Game_Properties(request, pk):
    '''
    A view that returns basic game properties from BGG.

    This is neded because BGG don't support CORS. That means modern browsers cannot
    fetch data from their API in Javascript. And BGG don't seem to care or want tof ix that.:

    https://boardgamegeek.com/thread/2268761/cors-security-issue-using-xmlapi
    https://boardgamegeek.com/thread/1304818/cross-origin-resource-sharing-cors

    So we have to fech the data from the CoGS server and supply it to the browser from
    the same origin. Givcen our API is using JSON not XML, we provide it in JSON to the
    browser.

    The main use casehere is thatthe browser can request BGG data to poopulate form
    fields when submitting a new game. Use case:

    1. User enters a BGG ID
    2. User clicks a fetch button
    3. Form is poulated by data from BGG
    '''
    bgg = BGG(pk)
    return HttpResponse(json.dumps(bgg))


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

    # Add object browser details if available. Should be added by DetailViewExtended
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
            if settings.DEBUG:
                log.debug(f"referrer = {request.META.get('HTTP_REFERER')}")
            session_keys = list(request.session.keys())
            for key in session_keys:
                del request.session[key]
            return HttpResponse("<script>window.history.pushState('', '', '/session_cleared');</script>")

        # Check for the timezone
        if "timezone" in request.POST:
            if settings.DEBUG:
                log.debug(f"Timezone = {request.POST['timezone']}")
            request.session['timezone'] = request.POST['timezone']
            activate(request.POST['timezone'])

        if "utcoffset" in request.POST:
            if settings.DEBUG:
                log.debug(f"UTC offset = {request.POST['utcoffset']}")
            request.session['utcoffset'] = request.POST['utcoffset']

        if "location" in request.POST:
            if settings.DEBUG:
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
            if settings.DEBUG:
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

    def rich(obj):
        return obj.__rich_str__(link=False)

    CuserMiddleware.set_user(request.user)

    title = "Database Integrity Check"

    assertion_failures = []  # Assertion failures

    models = ['Game', 'Performance', 'Rank', 'Session', 'Rating']

    do_all = True
    for model in models:
        if model in request.GET:
            do_all = False
            break

    if do_all or 'Game' in request.GET:
        print("Checking all Games for internal integrity.", flush=True)
        for G in Game.objects.all():
            fails = G.check_integrity()

            print(f"Game {G.id}: {rich(G)}. {len(fails)} assertion failures.", flush=True)
            for f in fails:
                print(f"\t{f}", flush=True)

            if fails:
                assertion_failures += fails

    if do_all or 'Performance' in request.GET:
        print("Checking all Performances for internal integrity.", flush=True)
        for P in Performance.objects.all().order_by('-pk'):
            fails = P.check_integrity()

            print(f"Performance {P.id}: {rich(P)}. {len(fails)} assertion failures.", flush=True)
            for f in fails:
                print(f"\t{f}", flush=True)

            if fails:
                assertion_failures += fails

    if do_all or 'Rank' in request.GET:
        print("Checking all Ranks for internal integrity.", flush=True)

        for R in Rank.objects.all():
            fails = R.check_integrity()

            print(f"Rank {R.id}: {rich(R)}. {len(fails)} assertion failures.", flush=True)
            for f in fails:
                print(f"\t{f}", flush=True)

            if fails:
                assertion_failures += fails

    if do_all or 'Session' in request.GET:
        print("Checking all Sessions for internal integrity.", flush=True)
        for S in Session.objects.all():
            fails = S.check_integrity(True)

            print(f"Session {S.id}: {rich(S)}. {len(fails)} assertion failures.", flush=True)
            for f in fails:
                print(f"\t{f}", flush=True)

            if fails:
                assertion_failures += fails

    if do_all or 'Rating' in request.GET:
        rfilter = Q()
        try:
            if 'game' in request.GET:
                rfilter &= Q(game__pk=int(request.GET['game']))
        except:
            pass

        try:
            if 'player' in request.GET:
                rfilter &= Q(player__pk=int(request.GET['player']))
        except:
            pass

        print("Checking Ratings for internal integrity.", flush=True)
        for R in Rating.objects.all().filter(rfilter).order_by('last_play'):
            fails = R.check_integrity()

            print(f"Rating {R.id}: {rich(R)}. {len(fails)} assertion failures.", flush=True)
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

    reason = "Explicitly requested rebuild"

    if 'game' in request.GET and request.GET['game'].isdigit():
        try:
            game = Game.objects.get(pk=request.GET['game'])
            reason += f" for {game.name} (id: {game.id})"
        except Game.DoesNotExist:
            game = None
    else:
        game = None

    if 'from' in request.GET:
        try:
            From = decodeDateTime(request.GET['from'])
            reason += f" from {From}"
        except:
            From = None
    else:
        From = None

    if 'reason' in request.GET:
        reason = request.GET['reason']
    else:
        reason += "."

    html = rebuild_ratings(game, From, reason)

    return HttpResponse(html)


def view_UnwindToday(request):
    '''
    A simple view that deletes all sessions (and associated ranks and performances) created today. Used when testing.
    Dangerous if run on a live database on same day as data was entered clearly. Testing view only.
    '''
    CuserMiddleware.set_user(request.user)

    unwind_to = date.today()  # - timedelta(days=1)

    performances = Performance.objects.filter(created_on__gte=unwind_to)
    performances.delete()

    ranks = Rank.objects.filter(created_on__gte=unwind_to)
    ranks.delete()

    sessions = Session.objects.filter(created_on__gte=unwind_to)
    sessions.delete()

    ratings = Rating.objects.filter(created_on__gte=unwind_to)
    ratings.delete()

    # Now for all ratings remaining we have to reset last_play (if test sessions updated that).
    ratings = Rating.objects.filter(Q(last_play__gte=unwind_to) | Q(last_victory__gte=unwind_to))
    for r in ratings:
        r.reset()

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


# from django.apps import apps
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

    # html = force_unique_session_times()
    # html = rebuild_ratings()
    # html = import_sessions()

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


def rebuild_ratings(Game=None, From=None, Reason=None):
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
    result = Rating.rebuild(Game=Game, From=From, Reason=Reason)
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
        if len(coincident_sessions) > 1:
            offset = 1
            for sess in coincident_sessions:
                sess.date_time = sess.date_time + timedelta(seconds=offset)
                sess.save()
                result += "Added {} to {}\n".format(offset, sess)
                offset += 1

    now = datetime.now()

    return "<html><body<p>{0}</p><p>It is now {1}.</p><p><pre>{2}</pre></p></body></html>".format(title, now, result)
