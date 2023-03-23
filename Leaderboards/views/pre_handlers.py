#===============================================================================
# Handlers called BEFORE certain conditions in the generic views.
#
# These are the COGS specific handlers thatthe generic views call.
#===============================================================================
from datetime import datetime
from html import escape
from copy import deepcopy

from django.conf import settings
from django.urls import reverse_lazy
from django.contrib.auth.models import Group
from django.utils.timezone import make_naive, localtime
from django.core.exceptions import ObjectDoesNotExist

from django_rich_views.views import RichCreateView, RichUpdateView
from django_rich_views.datetime import time_str
from django_rich_views.util import isPositiveInt

from ..models import Game, Session, Player, Rating, Team, ChangeLog, RATING_REBUILD_TRIGGER, MISSING_VALUE

from Site.logutils import log


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


def reconcile_ranks(form, session_dict, permit_missing_scores=False):
    '''
    We MUST have ranks to create session. Scores are optional.
    Furthermore Rank scores are needed for determing ranks (if not explicitly provided),
    while Performance scores are used only to calculate rank scores if they are missing.
    Performance scores exist primarily to support the edge case of a game played in teams
    (so one rank per team) which concludes with individual player scores (on performance
    per player).

    The reconciliation is as follows:

    1. If the game.scoring is not None, then require scores and bounce.
         a. There should be an option to override this bounce if valid rankings are provided,
            for two reasons:
              i. While the game is scored, someone may have recorded results without
                 noting them, anbut has rankings and this is all that's needed for
                 updating ratings and leaderboards so it should be accceptable and
                 accepted.
             ii. All legacy sessions (prior to to the introduction of scoring in the
                 site) lack recorded scores. It should be possible if needed to edit
                 such a seshandlersion and submit. An edge case, but a consistency issue as
                 well.
    2. If rank scores are provided:
         a. using the game.scoring method (high wins or low wins) establish
            a ranking.
         b. if ranks were provided, reconcile them with this result, and bail
            with a warning if they don't agree. Ranks should be provided for
            tie breakers. That is, many games which conclude with a score,
            have nuanced tie breaking rules and the onlyw ay to sensibly capture
            those generically across any and all games is by submitting a ranking
            (along with the scores).
    3. If any rank scores were not provided but performance scores were:
         a. Calculate a ranks core as the sum of the related performance scores
            Ranks can map 1 to 1 to performances in most games, but in games played
            in teams they map 1 to n, n being th enumber of team members.

    Use self.form.add_error(None, f"message") to bounce if needed.

    -1 is MISSING_VALUE

    A sample individual play, new session submission:
        'model': 'Session',
        'id': -1,
        'game': 29,
        'time': datetime.datetime(2022, 7, 2, 3, 59, tzinfo = tzoffset(None, 36000)),
        'league': 1,
        'location': 9,
        'team_play': False,
        'ranks': [-1, -1],
        'rankings': [1, 2],
        'rscores': [0, 0],
        'rankers': [1, 66],
        'performances': [-1, -1],
        'pscores': [-1, -1],
        'performers': [1, 66],
        'weights': [1.0, 1.0]

    And a sample team play submission:

        'model': 'Session',
        'id': -1,
        'game': 18,
        'time': datetime.datetime(2022, 7, 2, 3, 59, tzinfo = tzoffset(None, 36000)),
        'league': 1,
        'location': 9,
        'team_play': True,
        'ranks': [-1, -1],
        'rankings': [1, 2],
        'rscores': [0, 0],
        'rankers': [
            [1, 66],
            [13, 70]
        ],
        'performances': [-1, -1, -1, -1],
        'pscores': [-1, -1, -1, -1],
        'performers': [1, 13, 66, 70],
        'weights': [1, 1, 1, 1]

    :param form: The form instance, so we can add form errors if reconciliation failure demands it or add data to secure validation
    :param session_dict:  A Session dictionary as returned by Session.dict_from_form() which is modified in place as needed
    :param pk: Provides a session PK if known
    :param permit_missing_scores: Suprss adding a form error on missing scores
    '''
    game = Game.objects.get(pk=session_dict['game'])
    scoring = Game.ScoringOptions(game.scoring).name
    score_high = "HIGH" in scoring
    team_play = session_dict['team_play']

    if scoring == "NO_SCORES":
        # No reconciliation to do )ranks are validated by standard form validation)
        return
    else:
        players = deepcopy(session_dict['performers'])
        rankers = deepcopy(session_dict.get('rankers', session_dict['performers']))
        rankings = deepcopy(session_dict['rankings'])
        rscores = deepcopy(session_dict['rscores'])
        pscores = deepcopy(session_dict['pscores'])

        valid_rankings = all(isPositiveInt(r) for r in rankings)
        valid_rscores = all(isPositiveInt(s) for s in rscores)

        # Validate the team_play setting
        # The only difference really is that teams can have multiple pscores per rscore.
        # TODO: Do we need to know team_play here at all? Can validation of this happen
        # in form_validation if it's not needed for rank reconciliation?
        # scoring can include:
        #     TEAM
        #     INDIVIDUAL
        #     TEAM_AND_INDIVIDUAL
        if team_play:
            # If TEAM scoring is not supported
            if not "TEAM" in scoring:
                form.add_error(None, "This is a game that does not score teams and so team play sessions can not be recorded. Likely a form or game configuration error.")
                return
        else:
            # If INDIVIDUAL scoring is not supported
            if "TEAM" in scoring and not "INDIVIDUAL" in scoring:
                form.add_error(None, "This is a game that scores teams and so only team play sessions can be recorded. Likely a form or game configuration error.")
                return

        # Only rscores are relevant, but if a session is submitted with
        # valid pscores and invalid rscores, use the pscores. pscores
        # are for informative purposes only and not used for ranking,
        # only for calculating rscores in the absence of them.
        altered = False
        for i, s in enumerate(rscores):
            # rscores and pscores map 1 to n (where n is 1 or more)
            # Build a pscore dict in preparation
            performer_score = {p: s for p, s in zip(players, pscores)}

            # Make the team definitions immutable so they can be used as dict keys
            trankers = [tuple(r) if isinstance(r, list) else (r,) for r in rankers]

            # Now infer any missing rscores from sum of any available pscores
            for i, (ranker, rscore) in enumerate(zip(trankers, rscores)):
                if rscore in (None, MISSING_VALUE):
                    score = 0
                    for player in tuple(ranker):
                        if not performer_score[player] in (None, MISSING_VALUE):
                            score += performer_score[player]
                    if score > 0:
                        rscores[i] = score
                        altered = True

        if altered:
            session_dict['rscores'] = deepcopy(rscores)
            valid_rscores = all(isPositiveInt(s) for s in rscores)

        # First things first, we need rscores for a scoring game
        # (unless we have valid rankings and explicitly permit missing scores)
        if not valid_rscores:
            if not (valid_rankings and permit_missing_scores):
                form.add_error(None, "This is a scoring game. Please enter scores")
                return

        # But if have them, and rankings are not valid we can maybe infer rankings from the rscores
        if valid_rscores and not valid_rankings:
            # Deduce rankings from supplied scores
            ranker_indexes = {}
            score_rankings = [None for r in rankings]
            score_sorted_rankers = sorted(zip(rscores, rankers), reverse=score_high)

            # This handles ties as well and produces tie-gapped ranking
            # as per Leaderboards.models.session.Session.clean_ranks
            prev_s = -1
            for i, (s, r) in enumerate(score_sorted_rankers):
                score_rankings[i] = score_rankings[i - 1] if s == prev_s else i + 1
                ranker_indexes[tuple(r) if isinstance(r, list) else r] = i
                prev_s = s

            # Now re-order the rankings in the original player order again
            all_new_rankings = [score_rankings[ranker_indexes[tuple(r) if isinstance(r, list) else r]] for r in rankers]

            # Patch them into the supplied rankings (only were we were missing rankings)
            new_rankings = [old if isPositiveInt(old) else new for i, (old, new) in enumerate(zip(rankings, all_new_rankings))]
            rankings = deepcopy(new_rankings)

            # And update the session_dict
            valid_rankings = all(isPositiveInt(r) for r in rankings)
            session_dict['rankings'] = deepcopy(rankings)
            if hasattr(form, 'data'):
                form.data = Session.dict_to_form(session_dict, form.data)

        # If we (now) valid rankings and valid rscores were submitted we need them to agree
        if valid_rscores and valid_rankings:
            ranking_sorted_scores = sorted(zip(rankings, rscores))
            score_sorted_rankings = sorted(zip(rankings, rscores), key=lambda rs: rs[1], reverse=score_high)

            # The sortings above detect agreed ordering but fail to detect
            # when one score maps to multiple rankings (which can happen if
            # rankings and scores are supplied). We test for that explicitly.
            one_score_per_rank = True
            rank_scores = {}
            for r, s in ranking_sorted_scores:
                if r in rank_scores:
                    if s != rank_scores[r]:
                        one_score_per_rank = False
                        break
                else:
                    rank_scores[r] = s

            if ranking_sorted_scores != score_sorted_rankings or not one_score_per_rank:
                form.add_error(None, "Submitted rankings and scores do not agree.")
                return

        return


def pre_dispatch_handler(self):
    '''
    This is a simple injection point before the form is built but after which the request kwargs have been
    translated to self.kargs, self.args, and self.app and self.model are available. it is at this pint we
    inject self.unique_model_choice, and optional attribute which can identify fields that will have a DAL
    forward request configured to call a handler of same name on the client side. On the client side this
    code must be used to register the forward handler or DAL will not function as expected.

        function registerForwarder() { yl.registerForwardHandler("MQFN", forward_handler); }
        window.addEventListener("load", registerForwarder);

    where
        MQFN is thhe Model Qualified Field Name (below)
        forward_handler is a JS function that will be called and must return a string (that will
                          be submitted in the GET param `forward`) which for unique model choice
                          support should contain a Comma Separated list of PKs already selcted in
                          the formset. The default ajax_Autocomplete handler for rich models will
                          then respect that adding a filter to query it uses. That support is built
                          into the django_rich_views.

    We need this only because:

        https://github.com/yourlabs/django-autocomplete-light/issues/1312
    '''
    # This line of code will return the MFQNS that this form supports for syntax diagnosis
    # mqfns = self.get_form(return_mqfns=True)
    self.unique_model_choice = ['Performance.player'] if self.model._meta.object_name == "Session" else []


def pre_validation_handler(self):
    '''
    When a model form is POSTed, this function is called
        BEFORE a form validation

    It should return a dict that is unpacked as kwargs passed to
    the pre_transaction_handler, and can thus communicate with it.

    When saving a Session form, the pre_transaction_handler wants
    to see the submitted session in a dict form as per what is produced
    by:
        Leaderboards.models.session.Session.dict_from_form
    That's a handy format for processing here where for Session
    forms we reconcile rankings and scores ahead of the first form
    validation so as to ensure it has valid rankings as best possible.

    That is because the Session can be submitted with scores from
    which ranks must be derived if needed, or with ranks an scores
    in which case they should agree. Any changes to the session should
    be reflect back in self.form.data which is Django validation
    considers. The dict format is our convenience for simpler
    reconciliation and (later pre_transaction handling - where
    for Sessions it aims to determing any rating rebuild requirements).
    '''
    model = self.model._meta.model_name

    if model == 'session':
        # The new session (form form data) is VERY hard to represent as
        # a Django model instance. We represent it as a dict instead.
        # Essentially a translator of form_data (a QueryDict) into a more
        # tractable form. If it's an Edit form we have  apk if it's an Add
        # form we won't, so passa session pk, only if it's available.
        submitted_session = Session.dict_from_form(self.form.data, getattr(self, "pk", None))

        # Ranking information can arrive as ranks, scores or a combination including
        # rank scroees, or performance scores . This all needs reconiliation before
        # we proceed. new_session is modified in place with ranks and scores
        # reconciled and/or updates form.errors with any errors it finds, forcing
        # validation to fail
        reconciled_session = deepcopy(submitted_session)
        # Reconciles the supplied session in situ

        if settings.DEBUG:
            log.debug(f"RANK RECONCILIATION, form provided:")
            for key, value in sorted(self.form.data.items()):
                log.debug(f"\t{key}: {value}")

            log.debug(f"RANK RECONCILIATION, session derived from it:")
            for key, value in sorted(submitted_session.items()):
                log.debug(f"\t{key}: {value}")

        reconcile_ranks(self.form, reconciled_session)

        if settings.DEBUG:
            log.debug(f"RANK RECONCILIATION, reconciled session :")
            for key, value in sorted(reconciled_session.items()):
                log.debug(f"\t{key}: {value}")

            log.debug(f"RANK RECONCILIATION, reconciled form:")
            for key, value in sorted(self.form.data.items()):
                log.debug(f"\t{key}: {value}")

        # Find what the reconciler changed:
        return {'new_session': reconciled_session}


def pre_transaction_handler(self, new_session=None):
    '''
    When a model form is POSTed, this function is called
        BEFORE a transaction (to save data) has been opened

    It should return a dict that is unpacked as kwargs passed to
    the pre_save_handler, and can thus communicate with it.

    This has access to form.data and form.cleaned_data and is
    intended for making decisions based on the post before we
    start saving.

    Importantly if the dictionary contains a key "debug_only" then
    it's value will be passed to an HttpResponse sent to browser.
    This is a vector for sending debug information to the client
    before a transaction is opened for saving.

    self is an instance of RichCreateView or RichUpdateView.

    :param new_session: The pre_validation handler should return a new
                        session, i.e. the one in train of being saved,
                        tn the dict format defined by:
                        Leaderboards.models.session.Session.dict_from_form
                        This handler will receive it.
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
        output(f"Session Submission Rebuild Request Determination")
        output("\n")
        output(f"Form data:")
        for (key, val) in self.form.data.items():
            output(f"\t{key}:{val}")

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
        # TODO: does this field name work?
        # TODO: Should we get this from rankers (which is a list of player IDs? or list of playerID lists in team play?
        new_players = [safe_get("performances__player", Player, pk) for pk in new_session["performers"]]

        # A rebuild of ratings is triggered under any of the following circumstances:
        #
        # A rebuild request goes to the post_processor for the submission (runs after
        # the submisison was saved. It takes the form of a list of sessions to rebuild
        # or a queryset of them,
        # from django.core.exceptions import ObjectDoesNotExist

        # 1. It's a new_session session and any of the players involved have future sessions
        #    recorded already.
        if isinstance(self, RichCreateView):
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
        elif isinstance(self, RichUpdateView):
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
        # the django_rich_views.views.post_generic handler.
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
    handler's conclusions (and the post and existing database object - pre any
    alterations to it on the basis of the post, if needed) that involve a database
    save of any sort.

    That is because this, unlike pre_transaction this runs inside an opened
    transaction and so whatever is saved herein can commit or rollback along with
    the rest of the save.

    self is an instance of RichCreateView or RichUpdateView.

    It returns a dict that will be used as a kwargs dict into the
    the configured post processor (pre_commit_handler below).
    '''
    model = self.model._meta.model_name

    change_log = None
    if model == 'session':
        if isinstance(self, RichCreateView):
            # Create a change log, but we don't have a session yet
            # and also no change summary. We provide themw ith the
            # update in the pre_commit handler once the session is
            # saved.
            change_log = ChangeLog.create()
        elif isinstance(self, RichUpdateView):
            old_session = self.object
            # Create a ChangeLog with the session now (pre_save status)
            # This captures the leaderboard_impact of the session as it
            # stands now. We need to update it again after saving the
            # session to capture the leaderboard_impact after the change
            # too.
            change_log = ChangeLog.create(old_session, change_summary)

    # Return the kwargs for the next handler
    return {'change_log': change_log, 'rebuild': rebuild, 'reason': reason}

# TODO: When
#    <input type="checkbox" value="on" id="id_Team-0-DELETE" name="Team-0-DELETE" style="display: none;">
# is received. Test that Teams are deleted only if they have no other session references, elklse not deleted
# I suspect standard Django form handling will not be smart enough here and we need to do something
# pre-save or pre-commit or...
#
# 1, Check what the -DELETE currently does (test)
# 2. Fix if necessary


def pre_commit_handler(self, change_log=None, rebuild=None, reason=None):
    '''
    When a model form is POSTed, this function is called AFTER the form is saved.

    self is an instance of RichCreateView or RichUpdateView.

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

        # Determine the submission mode
        if isinstance(self, RichCreateView):
            submission = "create"
        elif isinstance(self, RichUpdateView):
            submission = "update"
        else:
            raise ValueError("Pre commit handler called from unsupported class.")

        team_play = session.team_play

        # TESTING NOTES: As Django performance is not 100% clear at this level from docs.
        # Some empirical testing notes here:
        #
        # 1) Individual play mode submission: the session object here has session.ranks and session.performances populated
        #    This must have have happened when we saved the related forms by passing in an instance to the formset.save
        #    method. Alas inlineformsets are attrociously documented. Might pay to check this understanding some day.
        #    Empirically seems fine. It is in django_rich_views.forms.save_related_forms that this is done.
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
            num_teams = int(self.form.data["num_teams"])
            num_players = 0
            TeamPlayers = []
            for t in range(num_teams):
                num_team_players = int(self.form.data[f"Team-{t:d}-num_players"])
                num_players += num_team_players
                TeamPlayers.append([])

            # Now populate the (thus far, empty) TeamPlayers list for each team
            # (i.e. work out which players are on the same team)
            player_pool = set()
            for p in range(num_players):
                player = int(self.form.data[f"Performance-{p:d}-player"])

                assert not player in player_pool, "Error: Players in session must be unique"
                player_pool.add(player)

                team_num = int(self.form.data[f"Performance-{p:d}-team_num"])
                TeamPlayers[team_num].append(player)

            # For each team now, find it, create it , fix it as needed
            # and associate it with the appropriate Rank just created
            for t in range(num_teams):
                # Get Team players that we already extracted from the POST
                team_players_posted = TeamPlayers[t]

                # Get the submitted Team ID if any and if it is supplied
                # fetch the team so we can provisionally use that (renaming it
                # if a new name is specified).
                team_id = self.form.data.get(f"Team-{t:d}-id", None)

                # The name submitted for this team if any
                team_name = self.form.data.get(f"Team-{t:d}-name", None)

                # Get the appropriate rank object for this team
                rank_rank = self.form.data.get(f"Rank-{t:d}-rank", None)
                rank_id = self.form.data.get(f"Rank-{t:d}-id", None)
                if not rank_id:
                    if session.ranks.filter(rank=rank_rank).exists():
                        rank_id = session.ranks.get(rank=rank_rank).id
                    elif submission == "create":
                        breakpoint()
                        # Prior version cays the rank must exist to have landed here.
                        # What went wrong? Diagnose. Set DEBUG in relate_for save and check.
                        print("debug here")

                # Submit the edit (to the database)
                Team.get_create_or_edit(team_players_posted, team_name, edit=(team_id, rank_id, session.id))

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

            if submission == "create":
                trigger = RATING_REBUILD_TRIGGER.session_add
            elif submission == "update":
                trigger = RATING_REBUILD_TRIGGER.session_edit
            else:
                raise ValueError("Pre commit handler called from unsupported class.")

            # This performs a rating rebuild, saves a RebuildLog and returns it
            rebuild_log = Rating.rebuild(Sessions=rebuild, Reason=reason, Trigger=trigger, Session=session)
        else:
            rebuild_log = None

        if change_log:
            if submission == "create":
                # The change summary will be just a JSON representation of the session we just created (saved)
                # changes will be none.
                # TODO: We could consider calling it a change from nothing, listng all fields in changes, and making all tuples
                # with a None as first entry. Not sure of the benefits of this is beyond consistency ....
                change_summary = session.__json__()

                # Update the ChangeLog with this change_summary it could not be
                # saved earlier in the pre_save handler as there was no session
                # yet to save as a change_summary.
                change_log.update(session, change_summary, rebuild_log)
            elif submission == "update":
                # Update the ChangeLog (change_summary was saved in the pre_save handler.
                # If we compare the form with the saved session now, there will be no changes
                # to log. and we lose the record of changes already recorded.
                change_log.update(session, rebuild_log=rebuild_log)
            else:
                raise ValueError("Pre commit handler called from unsupported class.")

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
            get_params = f"?submission={submission}&changed={change_log.pk}"

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
