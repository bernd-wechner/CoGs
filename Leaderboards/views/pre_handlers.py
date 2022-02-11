#===============================================================================
# Handlers called BEFORE certain conditions in the generic views.
#
# These are the COGS specific handlers thatthe generic views call.
#===============================================================================
import re

from re import RegexFlag as ref

from datetime import datetime

from html import escape

from django.conf import settings
from django.urls import reverse_lazy
from django.db.models import Count
from django.contrib.auth.models import Group
from django.utils.timezone import make_naive, localtime
from django.core.exceptions import ObjectDoesNotExist

from django_generic_view_extensions.views import CreateViewExtended, UpdateViewExtended
from django_generic_view_extensions.datetime import time_str

from ..models import Game, Session, Player, Rating, Team, ChangeLog, RATING_REBUILD_TRIGGER

from Site.logging import log


def updated_user_from_form(user, request):
    '''
    Updates a user object in the database (from the Django auth module) with information from the submitted form, specific to CoGs
    '''

    def is_registrar(user):
        return user.groups.filter(name='registrars').exists()

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


def pre_transaction_handler(self):
    '''
    When a model form is POSTed, this function is called
        BEFORE a transaction (to save data) has been opened

    It should return a dict that is unpacked as kwargs passed to
    the pre_save handler, and can thus communicate with it.

    This has access to form.data and form.cleaned_data and is
    intended for making decisions based on the post before we
    start saving.

    Importantly if the dictionary contains a key "debug_only" then
    it's value will be passed to an HttpResponse sent to browser.
    This is a vector for sending debug information to the client
    before a transaction is opened for saving.

    self is an instance of CreateViewExtended or UpdateViewExtended.
    '''
    model = self.model._meta.model_name

    # A special mode which will not actually submit data but retruna diagnostic page to
    # Examine the results of this pre save handler, specifically the request for a rating
    # rebuild it concludes is neeeded (hairy and costly and nice to debug without actually
    # doing a rating rebuild).
    debug_only = bool(self.form.data.get("debug_rebuild_request", False))

    # f"<html><body<p>{title}</p><p>It is now {now}.</p><p><pre>{result}</pre></p></body></html>"
    html = "<section id='debug'>\n<pre>\n"

    def output(message):
        '''Toggle for diagnostic output direction'''
        nonlocal html
        if debug_only:
            # m = message.replace('\n', '\n\t')
            html += f"{message}\n"

        if settings.DEBUG:
            m = message.replace('\n', ' ')
            log.debug(m)

    # Default args to return (irrespective of object model or form type)
    # The following code aims to populate these for feed forward to the
    # pre_save and pre_commit handlers.
    change_summary = None
    rebuild = None
    reason = None

    # When a session submitted (while it is still in unchanged int he database) we need
    # to check if the submission changes any rating affecting fields and make note of that
    # so that the post processor can update the ratings with a rebuild request if needed
    if model == 'session':
        output(f"PRE-PROCESSING Session submission.")
        output("\n")
        output(f"Using form data:")
        for (key, val) in self.form.data.items():
            output(f"\t{key}:{val}")

        # The new session (form form data) is VERY hard to represent as
        # a Django model instance. We represent it as a dict instead.
        # Essentially a translator of form_data (a QuryDict) into a more
        # tractable form.
        new_session = Session.dict_from_form(self.form.data)

        output("\n")
        output("Form data as a Session dict:")
        for (key, val) in new_session.items():
            output(f"\t{key}:{val}")

        # We need the time, game and players first
        # As this is all we need to know for
        # both the Create and Update views.

        new_time = new_session["time"]

        # The time of the session cannot be in the future of course.
        if new_time > localtime():
            # TODO: there's a bug here in the return. It returns players and ranks onto the error form badly.
            # As in they disappear from the returned form.
            # Methinks we want to translate form fields back into Session context as part of bailing
            self.form.add_error("date_time", f"Please choose a time in the past.")
            return None

        # A quick internal to safely get an object from a model and PK
        def safe_get(field, model, pk):
            try:
                return model.objects.get(pk=pk)
            except ObjectDoesNotExist:
                self.form.add_error(field, f"Please choose a valid {field}.")
                return None

        new_game = safe_get("game", Game, new_session["game"])

        new_team_play = new_session["team_play"]

        # Check that players are unique!
        if not len(set(new_session["performers"])) == len(new_session["performers"]):
            # TODO we could list the players that were duplicated if keen.
            self.form.add_error(None, f"Players must be unique.")
            return None

        # Players are identifed by PK in "performers"
        # TOOD: does this field name work?
        new_players = [safe_get("performances__player", Player, pk) for pk in new_session["performers"]]

        # A rebuild of ratings is triggered under any of the following circumstances:
        #
        # A rebuild request goes to the post_processor for the submission (runs after
        # the submisison was saved. It takes the form of a list of sessions to rebuild
        # or a queryset of them,
        # from django.core.exceptions import ObjectDoesNotExist

        # 1. It's a new_session session and any of the players involved have future sessions
        #    recorded already.
        if isinstance(self, CreateViewExtended):
            output("\n")
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
                output(f"Requesting a rebuild of ratings for {len(rebuild)} sessions: {escape(str(rebuild))}")
                output(f"Because: {reason}")
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

            output("\n")
            output(f"Editing session {old_session.pk}")
            J = '\n\t'  # A log message list item joiner

            # Get a delta dict (between form data and the old object
            delta = old_session.dict_delta(self.form.data)
            changed = delta.get("changes", [])

            output("\n")
            output("Submission as a Session delta dict:")
            for (key, val) in delta.items():
                output(f"\t{key}:{val}")

            # Get a change summary (JSONified delta, for saving in a change log)
            change_summary = old_session.__json__(delta=delta)

            old_players = old_session.players

            # Build a list of all players affected by this submission
            all_players = list(set(old_players) | set(new_players))
            output("\n")
            output(f"Old players: {escape(', '.join([str(p) for p in old_players]))}")
            output(f"New players: {escape(', '.join([str(p) for p in new_players]))}")
            output(f"All players: {escape(', '.join([str(p) for p in all_players]))}")
            output("\n")

            # If the game was changed we will request a rebuild of both games
            # regardless of any other considerations. Both their rating trees
            # need rebuilding.
            if "game" in changed:
                # Use sets so that wehn adding the future sessions duplicates are taken care of
                old_sessions = set(old_session.game.future_sessions(old_session.date_time, old_session.players))
                new_sessions = set(new_game.future_sessions(new_time, new_players))
                rebuild = sorted(old_sessions.union(new_sessions), key=lambda s: s.date_time)
                reason = f"Session Edit. Game changed (from {old_session.game.name} to {new_game.name})."

                output(f"Requesting a rebuild of ratings for {len(rebuild)} sessions:{J}{J.join([s.__rich_str__() for s in rebuild])}")
                output(f"Because: {reason}")

            else:
                # Set up some rebuild shorthands
                old_game = old_session.game
                old_time = old_session.date_time_local
                from_time = min(old_time, new_time)

                # If the play mode changed rebuild this games rating tree from this session on.
                if "team_play" in changed:
                    rebuild = old_game.future_sessions(from_time, all_players)
                    reason = f"Session Edit. Play mode changed (from {'Team' if old_session.team_play else 'Individual'} to {'Team' if new_team_play else 'Individual'})."

                    output(f"Requesting a rebuild of ratings for {len(rebuild)} sessions:{J}{J.join([s.__rich_str__() for s in rebuild])}")
                    output(f"Because: {reason}")

                # If any players were added, remove or changed, rebuild this games rating tree from this session on.
                elif "performers" in changed:
                    rebuild = old_game.future_sessions(from_time, all_players)
                    reason = f"Session Edit. Players changed (from {sorted([p.complete_name for p in old_players])} to {sorted([p.complete_name for p in new_players])})."

                    output(f"Requesting a rebuild of ratings for {len(rebuild)} sessions:{J}{J.join([s.__rich_str__() for s in rebuild])}")
                    output(f"Because: {reason}")

                # Otherwise check for other rating impacts
                else:
                    # Check for a change in ranks.
                    # "rankers" lists the PK of rankers in order of their ranking, where the PK is a player PK or a team PK.
                    if "rankers" in changed:
                        rebuild = old_game.future_sessions(from_time, all_players)
                        reason = f"Session Edit. Rankings changed (from {delta['rankers'][0]} to {delta['rankers'][1]})."

                        output(f"Requesting a rebuild of ratings for {len(rebuild)} sessions:{J}{J.join([s.__rich_str__() for s in rebuild])}")
                        output(f"Because: {reason}")
                    else:
                        if "weights" in changed:
                            rebuild = old_game.future_sessions(from_time, all_players)
                            reason = f"Session Edit. Weights changed {delta['weights'][0]} to {delta['weights'][1]})."

                            output(f"Requesting a rebuild of ratings for {len(rebuild)} sessions:{J}{J.join([s.__rich_str__() for s in rebuild])}")
                            output(f"Because: {reason}")
                        else:
                            # Check for a Session sequence change for any player
                            # That is for any player in htis session has it been moved before or after another session they played this game in

                            # Start with an empty set of sessions before we walk the players
                            # Sets simplytake care of duplicate removal for us, so that if more
                            # than one player triggers a rebuild of the same session it is included
                            # only once, we sort the sessions again when done.
                            rebuild = set()
                            reasons = []

                            for p in new_players:
                                prev_sess = old_session.previous_session(p)
                                foll_sess = old_session.following_session(p)

                                # When testing time windows, because datetime.min and datetime.max are naive
                                # we need to use naive times.
                                naive_time = make_naive(new_time)

                                # min and max are TZ unaware (naive), and session.date_time is UTC
                                # So we make session.date_time naive for the comparison to come.
                                time_window = (make_naive(prev_sess.date_time) if prev_sess else datetime.min,
                                               make_naive(foll_sess.date_time) if foll_sess else datetime.max)

                                if not time_window[0] < naive_time < time_window[1]:
                                    sessions = old_game.future_sessions(from_time, all_players)
                                    rebuild.update(sessions)

                                    if naive_time < time_window[0]:
                                        reasons.append(f"Before the previous session for player {p} at {time_str(prev_sess.date_time_local)}.")
                                    else:
                                        reasons.append(f"After the following session for player {p} at {time_str(foll_sess.date_time_local)}.")

                            # The set  of sessions in rebuild may contain the current session
                            # because it has not yet been saved with new_time, it sits in the database
                            # under old_time. from_time is the earlier of new_time and old_time and so
                            # if new_time is earlier than old_time then the the current session (the
                            # one being saved here) will appear in the list (of sessions after from_time).
                            #
                            # It can safely be removed from the list because the current session will
                            # have its ratings updated before a rebuild is triggered and the rebuild
                            # will no longer see this session nor need to (as it's been brought forward).
                            if new_time < old_time:
                                rebuild.discard(old_session)

                            # If we have a rebuild set created an ordered list from it once more
                            rebuild = sorted(rebuild, key=lambda s: s.date_time)

                            if rebuild:
                                reason = f"Session Edit. Session moved from {time_str(old_time)} to {time_str(new_time)}.\n\t" + '\n\t'.join(reasons)

                                output(f"Requesting a rebuild of ratings for {len(rebuild)} sessions:{J}{J.join([s.__rich_str__() for s in rebuild])}")
                                output(f"Because: {reason}")
                            else:
                                output(f"No rating impact found. No rebuild requested.")

    if debug_only:
        html += "</pre>\n</section>\n"
        # When "debug_only" is returned then all other args are ignored and the value
        # of the debug_only field is returned as an HTML response by the caller,
        # the django_generic_view_extensions.views.post_generic handler.
        return {'debug_only': html}

    else:
        # Return the kwargs for the next handler
        return {'change_summary': change_summary, 'rebuild': rebuild, 'reason': reason}


def pre_save_handler(self, change_summary=None, rebuild=None, reason=None):
    '''
    When a model form is POSTed, this function is called
        AFTER a transaction has been opened
        BEFORE the form is saved.

    This intended primarily to make decisions based on the the pre_transaction
    handler's conclusions (and the post and existing database object if needed)
    that involve a database save of any sort. That is becauyse this, unlike
    pre_transaction runs inside an opened transaction and so whatever we save
    herein can commit or rollback along with the rest of the save.

    self is an instance of CreateViewExtended or UpdateViewExtended.

    If it returns a dict that will be used as a kwargs dict into the
    the configured post processor (pre_commit_handler below).
    '''
    model = self.model._meta.model_name

    change_log = None
    if model == 'session':
        if isinstance(self, CreateViewExtended):
            # Create a change log, but we don't have a session yet
            # and also no change summary. We provide themw ith the
            # update in the pre_commit handler once the session is
            # saved.
            change_log = ChangeLog.create()
        elif isinstance(self, UpdateViewExtended):
            old_session = self.object
            # Create a ChangeLog with the session now (pre_save status)
            # This captures the eladerboard_impact of the session as it
            # stands now. We need to update it again after saving the
            # session to capture the leaderboard_impact after the change
            # too.
            change_log = ChangeLog.create(old_session, change_summary)

    # Return the kwargs for the next handler
    return {'change_log': change_log, 'rebuild': rebuild, 'reason': reason}


def pre_commit_handler(self, change_log=None, rebuild=None, reason=None):
    '''
    When a model form is POSTed, this function is called AFTER the form is saved.

    self is an instance of CreateViewExtended or UpdateViewExtended.

    It will be running inside a transaction and can bail with an IntegrityError if something goes wrong
    achieving a rollback.

    This is executed inside a transaction which is important if it is trying to update
    a number of models at the same time that are all related. The integrity of relations after
    the save should be tested and if not passed, then throw an IntegrityError.

    :param changes: A JSON string which records changes being committed.
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
        # Some empirical testing notes here:
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

        # FIXME: Remove form access from here and access the form data from "change_log.changes" which is a dir that holds it.
        #        That way we're not duplicating form interpretation again.

        # manage teams properly, as we handle teams in a special way creating them
        # on the fly as needed and reusing where player sets match.
        # This applies to Create and Update submissions
        if team_play:
            # Check if a team ID was submitted, then we have a place to start.
            # Get the player list for submitted teams and the name.
            # If the player list submitted doesn't match that recorded, ignore the team ID
            #    and look for a new one that has those players!
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

            # Populate the TeamPlayers record for each team (i.e. work out which players are on the same team)
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

            if isinstance(self, CreateViewExtended):
                trigger = RATING_REBUILD_TRIGGER.session_add
            elif isinstance(self, UpdateViewExtended):
                trigger = RATING_REBUILD_TRIGGER.session_edit
            else:
                raise ValueError("Pre commit handler called from unsupported class.")

            # This performs a rating rebuild, saves a RebuildLog and returns it
            rebuild_log = Rating.rebuild(Sessions=rebuild, Reason=reason, Trigger=trigger, Session=session)
        else:
            rebuild_log = None

        if change_log:
            if isinstance(self, CreateViewExtended):
                # The change summary will be just a JSON representation of the session we just created (saved)
                # changes will be none.
                # TODO: We could consider calling it  ahcnage fomrnothing, lisitng all fields in changes, and making all tuples with a None as first entry.
                # Not sure of the benefits of this is beyond concistency ....
                change_summary = session.__json__()

                # Update the ChangeLog with this change_summary it could not be
                # saved earlier in the pre_save handler as there was no session to
                # compare with.
                change_log.update(session, change_summary, rebuild_log)
            else:
                # Update the ChangeLog (change_summary was saved in the pre_save handler.
                # If we compare the form with the saved session now, there will be no changes
                # to log. and we lose the record of changes already recorded.
                change_log.update(session, rebuild_log=rebuild_log)

            change_log.save()

        # Now check the integrity of the save. For a sessions, this means that:
        #
        # If it is a team_play session:
        #    The game supports team_play
        #    The ranks all record teams and not players
        #    There is one performance object for each player (accessed through Team).
        # If it is not team_play:
        #    The game supports individual_play
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
        if change_log:
            get_params = f"?changed={change_log.pk}"

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
                log.debug(f"\tIs the latest session of {g} for all of {', '.join([p.name() for p in session.players])}")

        return post_kwargs
    else:
        return None
