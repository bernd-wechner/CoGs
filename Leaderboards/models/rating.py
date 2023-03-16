from . import APP, FLOAT_TOLERANCE, RATING_REBUILD_TRIGGER, TrueskillSettings

from ..leaderboards import LB_PLAYER_LIST_STYLE
from ..models.leaderboards import Leaderboard_Cache

import trueskill

from django.db import models, IntegrityError, DataError
from django.db.models import ExpressionWrapper, Q, F
from django.urls import reverse
from django.apps import apps
from django.conf import settings
from django.utils.timezone import localtime
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned, ValidationError

from django_model_admin_fields import AdminModel

from django_rich_views.util import AssertLog
from django_rich_views.html import NEVER
from django_rich_views.model import TimeZoneMixIn, field_render
from django_rich_views.datetime import safe_tz

from math import isclose
from datetime import timedelta, datetime
from statistics import mean, stdev
from collections import OrderedDict

from timezone_field import TimeZoneField

from Site.logutils import log



class RatingModel(AdminModel, TimeZoneMixIn):
    '''
    A Trueskill rating for a given Player at a give Game.

    This is the ultimate goal of the whole exercise. To record game sessions in order to calculate
    ratings for players and rank them in leaderboards.

    Every player has a rating at every game, though only those deviating from default (i.e. games
    that a player has players) are stored in the database.

    This is an abstract model defining the table structure that us used
    by Rating and BackupRating. The latter being a place to copy Rating
    before a complete rebuild of ratings.

    The preferred way of fetching a Rating is through Player.rating(game) or Game.rating(player).
    '''
    player = models.ForeignKey('Player', verbose_name='Player', related_name='%(class)ss', on_delete=models.CASCADE)  # If the player is deleted delete the raiting
    game = models.ForeignKey('Game', verbose_name='Game', related_name='%(class)ss', on_delete=models.CASCADE)  # If the game is deleted delete the raiting

    plays = models.PositiveIntegerField('Play Count', default=0)
    victories = models.PositiveIntegerField('Victory Count', default=0)

    last_play = models.DateTimeField('Time of Last Play', default=NEVER)
    last_play_tz = TimeZoneField('Time of Last Play, Timezone', default=settings.TIME_ZONE, editable=False)
    last_victory = models.DateTimeField('Time of Last Victory', default=NEVER)
    last_victory_tz = TimeZoneField('Time of Last Victory, Timezone', default=settings.TIME_ZONE, editable=False)

    # Although Eta (η) is a simple function of Mu (µ) and Sigma (σ), we store it alongside Mu and Sigma because it is also a function of global settings µ0 and σ0.
    # To protect ourselves against changes to those global settings, or simply to detect them if it should happen, we capture their value at time of rating update in the Eta.
    # These values before each game session and their new values after a game session are stored with the Session Ranks for integrity and history plotting.
    trueskill_mu = models.FloatField('Trueskill Mean (µ)', default=trueskill.MU, editable=False)
    trueskill_sigma = models.FloatField('Trueskill Standard Deviation (σ)', default=trueskill.SIGMA, editable=False)
    trueskill_eta = models.FloatField('Trueskill Rating (η)', default=trueskill.SIGMA, editable=False)

    # Record the global TrueskillSettings mu0, sigma0 and delta with each rating as an integrity measure.
    # They can be compared against the global settings and and difference can trigger an update request.
    # That is, flag a warning and if they are consistent across all stored ratings suggest TrueskillSettings
    # should be restored (and offer to do so?) or if inconsistent (which is an integrity error) suggest that
    # ratings be globally recalculated
    trueskill_mu0 = models.FloatField('Trueskill Initial Mean (µ)', default=trueskill.MU, editable=False)
    trueskill_sigma0 = models.FloatField('Trueskill Initial Standard Deviation (σ)', default=trueskill.SIGMA, editable=False)
    trueskill_delta = models.FloatField('TrueSkill Delta (δ)', default=trueskill.DELTA)

    # Record the game specific Trueskill settings beta, tau and p with rating as an integrity measure.
    # Again for a given game these must be consistent among all ratings and the history of each rating.
    # And change while managing leaderboards should trigger an update request for ratings relating to this game.
    trueskill_beta = models.FloatField('TrueSkill Skill Factor (ß)', default=trueskill.BETA)
    trueskill_tau = models.FloatField('TrueSkill Dynamics Factor (τ)', default=trueskill.TAU)
    trueskill_p = models.FloatField('TrueSkill Draw Probability (p)', default=trueskill.DRAW_PROBABILITY)

    @property
    def last_play_local(self):
        return self.last_play.astimezone(safe_tz(self.last_play_tz))

    @property
    def last_victory_local(self):
        return self.last_victory.astimezone(safe_tz(self.last_victory_tz))

    def __unicode__(self): return  f'{self.player} - {self.game} - {self.trueskill_eta:.1f} teeth'

    def __str__(self): return self.__unicode__()

    def __verbose_str__(self):
        return  f'{self.player} - {self.game} - {self.trueskill_eta:.1f} teeth, from (µ={self.trueskill_mu:.1f}, σ={self.trueskill_sigma:.1f} after {self.plays} plays)'

    def __rich_str__(self, link=None):
        return  f'{field_render(self.player, link)} - {field_render(self.game, link)} - {self.trueskill_eta:.1f} teeth, from (µ={self.trueskill_mu:.1f}, σ={self.trueskill_sigma:.1f} after {self.plays} plays)'

    def __detail_str__(self, link=None):
        return self.__rich_str__(link)

    class Meta(AdminModel.Meta):
        ordering = ['-trueskill_eta']
        abstract = True


class Rating(RatingModel):
    '''
    This is the actual repository of ratings that describe leaderboards.

    Its partner BackupRating stores a backup (form before the last rebuild)
    '''

    @property
    def last_performance(self) -> 'Performance':
        '''
        Returns the latest performance object that this player played this game in.
        '''
        game = self.game
        player = self.player
        Session = apps.get_model(APP, "Session")

        plays = Session.objects.filter(Q(game=game) & (Q(ranks__player=player) | Q(ranks__team__players=player))).order_by('-date_time')

        return None if (plays is None or plays.count() == 0) else plays[0].performance(player)

    @property
    def last_winning_performance(self) -> 'Performance':
        '''
        Returns the latest performance object that this player played this game in and won.
        '''
        game = self.game
        player = self.player
        Session = apps.get_model(APP, "Session")

        wins = Session.objects.filter(Q(game=game) & Q(ranks__rank=1) & (Q(ranks__player=player) | Q(ranks__team__players=player))).order_by('-date_time')

        return None if (wins is None or wins.count() == 0) else wins[0].performance(player)

    @property
    def link_internal(self) -> str:
        return reverse('view', kwargs={"model":self._meta.model.__name__, "pk": self.pk})

    def reset(self, session=None):
        '''
        Given a session, resets this rating object to what it was after this session.

        If no session is specified us the last played session (of that player at that game)

        Allows for a rewind of the rating to what it was at some time in past, so that
        it can be rebuilt from that point onward if desired, and/or can be used to ensure
        that all the rating related data is up to date (as of last session). Remembering
        that Rating is just a rapid access version of what is stored in Performance
        objects (each rating sits in one Performance object somewhere, being the latest
        Performance for a given player at a given game.

        :param session: A Session object (optional)
        '''
        Session = apps.get_model(APP, "Session")

        if not isinstance(session, Session):
            session = self.player.last_play(self.game)

        if session:
            performance = session.performance(self.player)

            self.plays = performance.play_number
            self.victories = performance.victory_count

            self.last_play = session.date_time

            if performance.is_victory:
                self.last_victory = session.date_time
            else:
                last_victory = session.previous_victory(performance.player)
                self.last_victory = NEVER if last_victory is None else last_victory.session.date_time

            self.trueskill_mu = performance.trueskill_mu_after
            self.trueskill_sigma = performance.trueskill_sigma_after
            self.trueskill_eta = performance.trueskill_eta_after

            self.trueskill_mu0 = performance.trueskill_mu0
            self.trueskill_sigma0 = performance.trueskill_sigma0
            self.trueskill_beta = performance.trueskill_beta
            self.trueskill_delta = performance.trueskill_delta

            self.trueskill_tau = performance.trueskill_tau
            self.trueskill_p = performance.trueskill_p
        else:
            # If we have no session it means this player never played this game
            # So we just create new rating (get does that if no rating exists).
            Rating.get(self.player, self.game)

    @classmethod
    def create(cls, player, game, mu=None, sigma=None):
        '''
        Create a new Rating for player at game, with specified mu and sigma.

        An explicit method, rather than override of __init__ which is called
        whenever and object is instantiated which can be when creating a new
        Rating or when fetching an old one from tthe database. So not appropriate
        to override it for new Ratings.
        '''

        TS = TrueskillSettings()

        trueskill_mu = TS.mu0 if mu == None else mu
        trueskill_sigma = TS.sigma0 if sigma == None else sigma

        self = cls(player=player,
                    game=game,
                    plays=0,
                    victories=0,
                    last_play=NEVER,
                    last_victory=NEVER,
                    trueskill_mu=trueskill_mu,
                    trueskill_sigma=trueskill_sigma,
                    trueskill_eta=trueskill_mu - TS.mu0 / TS.sigma0 * trueskill_sigma,  # µ − (µ0 ÷ σ0) × σ
                    trueskill_mu0=TS.mu0,
                    trueskill_sigma0=TS.sigma0,
                    trueskill_beta=game.trueskill_beta,
                    trueskill_delta=TS.delta,
                    trueskill_tau=game.trueskill_tau,
                    trueskill_p=game.trueskill_p
                    )
        return self

    @classmethod
    def get(cls, player, game):
        '''
        Fetch (or create fromd efaults) the rating for a given player at a game
        and perform some quick data integrity checks in the process.

        :param player: a Player object
        :param game:   a Game object
        '''
        TS = TrueskillSettings()

        try:
            r = Rating.objects.get(player=player, game=game)
        except ObjectDoesNotExist:
            r = Rating.create(player=player, game=game)
        except MultipleObjectsReturned:
            raise IntegrityError("Integrity error: more than one rating for {} at {}".format(player.name_nickname, game.name))

        if not (isclose(r.trueskill_mu0, TS.mu0, abs_tol=FLOAT_TOLERANCE)
         and isclose(r.trueskill_sigma0, TS.sigma0, abs_tol=FLOAT_TOLERANCE)
         and isclose(r.trueskill_delta, TS.delta, abs_tol=FLOAT_TOLERANCE)
         and isclose(r.trueskill_beta, game.trueskill_beta, abs_tol=FLOAT_TOLERANCE)
         and isclose(r.trueskill_tau, game.trueskill_tau, abs_tol=FLOAT_TOLERANCE)
         and isclose(r.trueskill_p, game.trueskill_p, abs_tol=FLOAT_TOLERANCE)):
            SettingsWere = "µ0: {}, σ0: {}, ß: {}, δ: {}, τ: {}, p: {}".format(r.trueskill_mu0, r.trueskill_sigma0, r.trueskill_delta, r.trueskill_beta, r.trueskill_tau, r.trueskill_p)
            SettingsAre = "µ0: {}, σ0: {}, ß: {}, δ: {}, τ: {}, p: {}".format(TS.mu0, TS.sigma0, TS.delta, game.trueskill_beta, game.trueskill_tau, game.trueskill_p)
            raise DataError("Data error: A trueskill setting has changed since the last rating was saved. They were ({}) and now are ({})".format(SettingsWere, SettingsAre))
            # TODO: Issue warning to the registrar more cleanly than this
            # Email admins with notification and suggested action (fixing settings or rebuilding ratings).
            # If only game specific settings changed on that game is impacted of course.
            # If global settings are changed all ratings are affected.

        return r

    @classmethod
    def leaderboards(cls, games, style=LB_PLAYER_LIST_STYLE.none) -> dict:
        '''
        returns Game.leaderboard(style) for each game supplied in a dict keyed on game.pk

        Specifically to support Rating.rebuild really. Game handles the leaderboard
        presentations otherwise.

        :param games: a list of QuerySet of Game instances
        '''
        return {g.pk: g.leaderboard(style=style) for g in games}

    @classmethod
    def update(cls, session):
        '''
        Update the ratings for all the players of a given session.

        :param session:   A Session object
        '''
        TS = TrueskillSettings()

        # Check to see if this is the latest play for each player
        # And capture the current rating for each player (which we will update)
        is_latest = {}
        player_rating = {}
        for performance in session.performances.all():
            rating = Rating.get(performance.player, session.game)  # Create a new rating if needed
            player_rating[performance.player] = rating
            is_latest[performance.player] = session.date_time >= rating.last_play

#         log.debug(f"Update rating for session {session.id}: {session}.")
#         log.debug(f"Is latest session of {session.game} for {[k for (k,v) in is_latest.items() if v]}")
#         log.debug(f"Is not latest session of {session.game} for {[k for (k,v) in is_latest.items() if not v]}")

        # Trickle admin bypass down
        if cls.__bypass_admin__:
            session.__bypass_admin__ = True

        # Get the session impact (records results in database Performance objects)
        # This updates the Performance objects associated with that session.
        impact = session.calculate_trueskill_impacts()

        # Invalidate any cache that may exist for this session
        # Any dwonstream dependent sessions will be covered by
        # the calling rebuildder - this method only handles this
        # specific indivual session.
        Leaderboard_Cache.invalidate(session)

        # Update the rating for this player/game combo
        # So this regardless of the sessions status as latest for any players
        # Here is not where we make that call and this method is called by rebuild()
        # which is itself called by a function that decides on the consequence
        # of so doing (whether a rebuild is needed because of future sessions,
        # relative this one).
        for player in impact:
            # Update the rating of course, only if this session is the latest in that game for this player
            # If it's not, a rebuild shoudl be triggered anyhow and the last session to update ratings during
            # that rebuild will be the latest.
            if is_latest[player]:
                r = player_rating[player]

                # Record the new rating data
                r.trueskill_mu = impact[player]["after"]["mu"]
                r.trueskill_sigma = impact[player]["after"]["sigma"]
                r.trueskill_eta = r.trueskill_mu - TS.mu0 / TS.sigma0 * r.trueskill_sigma  # µ − (µ0 ÷ σ0) × σ

                # Record the TruesSkill settings used to get them
                r.trueskill_mu0 = TS.mu0
                r.trueskill_sigma0 = TS.sigma0
                r.trueskill_delta = TS.delta
                r.trueskill_beta = session.game.trueskill_beta
                r.trueskill_tau = session.game.trueskill_tau
                r.trueskill_p = session.game.trueskill_p

                # Record the context of the rating
                r.plays = impact[player]["plays"]
                r.victories = impact[player]["victories"]

                r.last_play = session.date_time
                if session.performance(player).is_victory:
                    r.last_victory = session.date_time
                # else leave r.last_victory unchanged

                # Trickle admin bypass down
                if cls.__bypass_admin__:
                    r.__bypass_admin__ = True

                r.save()

    @classmethod
    def rebuild(cls, Game=None, From=None, Sessions=None, Reason=None, Trigger=None, Session=None):
        '''
        Rebuild the ratings for a specific game from a specific time.

        Returns a RebuildLog instance (with an html attribute if not triggered by a session)

        If neither Game nor From nor Sessions are specified, rebuilds ALL ratings
        If both Game and From specified rebuilds ratings only for that game for sessions from that datetime
        If only Game is specified, rebuilds all ratings for that game
        If only From is specified rebuilds ratings for all games from that datetime
        If only Sessions is specified rebuilds only the nominated Sessions

        :param Game:     A Game object
        :param From:     A datetime
        :param Sessions: A list of Session objects or a QuerySet of Sessions.
        :param Reason:   A string, to log as a reason for the rebuild
        :param Trigger:  A RATING_REBUILD_TRIGGER value
        :param Session:  A Session object if an edit (create or update) of a session triggered this rebuild
        '''
        SessionModel = apps.get_model(APP, "Session")

        # If ever performed keep a record of duration overall and per
        # session to permit a cost estimate should it happen again.
        # On a large database this could be a costly exercise, causing
        # some down time to the server (must either lock server to do
        # this as we cannot have new ratings being created while
        # rebuilding or we could have the update method above check
        # if a rebuild is underway and if so schedule an update ro
        RebuildLog = apps.get_model(APP, "RebuildLog")

        # Bypass admin fields updates for a rating rebuild
        cls.__bypass_admin__ = True

        # First we collect the sessions that need rebuilding, they are either
        # explicity provided or implied by specifying a Game and/or From time.
        if Sessions:
            assert not Game and not From, "Invalid ratings rebuild requested."
            sessions = sorted(Sessions, key=lambda s: s.date_time)
            first_session = sessions[0]
        elif not Game and not From:
            if settings.DEBUG:
                log.debug(f"Rebuilding ALL leaderboard ratings.")

            sessions = SessionModel.objects.all().order_by('date_time')
            first_session = sessions.first()
        else:
            if settings.DEBUG:
                log.debug(f"Rebuilding leaderboard ratings for {getattr(Game, 'name', None)} from {From}")

            sfilterg = Q(game=Game) if Game else Q()
            sfilterf = Q(date_time__gte=From) if isinstance(From, datetime) else Q()

            sessions = SessionModel.objects.filter(sfilterg & sfilterf).order_by('date_time')
            first_session = sessions.first()

        affected_games = set([s.game for s in sessions])
        if settings.DEBUG:
            log.debug(f"{len(sessions)} Sessions to process, affecting {len(affected_games)} games.")

        # If Game isn't specified, and a list of Sessions is, then if the sessions all relate
        # to the same game log that game.
        if not Game and len(affected_games) == 1:
            Game = list(affected_games)[0]

        # We prepare a Rebuild Log entry
        rlog = RebuildLog(game=Game,
                          date_time_from=first_session.date_time_local,
                          ratings=len(sessions),
                          reason=Reason)

        # Record what triggered the rebuild
        if not Trigger is None:
            rlog.trigger = Trigger.value
            if not Session is None:
                rlog.session = Session

        # Need to save it to get a PK before we can attach the sessions set to the log entry.
        rlog.save()
        rlog.sessions.set(sessions)

        # Start the timer
        start = localtime()

        # Now save the leaderboards for all affected games.
        rlog.save_leaderboards(affected_games, "before")

        # Delete all BackupRating objects
        BackupRating.reset()

        # Traverse sessions in chronological order (order_by is the time of the session) and update ratings from each session
        ratings_to_reset = set()  # Use a set to avoid duplicity
        backedup = set()
        for s in sessions:
            # Backup a rating only the first time we encounter it
            # Ratings apply to a player/game pair and we want a backup
            # of the rating before this rebuild process starts to
            # compare the final ratings to. We only want to backup
            # ratings that are being updated though hence first time
            # see a player/game pair in the rebuild process, nab a
            # backup.
            for p in s.performances.all():
                rkey = (p.player, s.game)
                if not rkey in backedup:
                    try:
                        rating = Rating.get(p.player, s.game)
                        BackupRating.clone(rating)
                    except:
                        # Ignore errors, We just won't record that rating as backedup.
                        pass
                    else:
                        backedup.add(rkey)

            cls.update(s)
            for p in s.players:
                ratings_to_reset.add((p, s.game))  # Collect a set of player, game tuples.

        # After having updated all the sessions we need to ensure
        # that the Rating objects are up to date.
        for rating in ratings_to_reset:
            if settings.DEBUG:
                log.debug(f"Resetting rating for {rating}")
            r = Rating.get(*rating)  # Unpack the tuple to player, game
            r.reset()  # Sets the rating to that after the ast played session in that game/player that the rating is for
            r.save()

        # Desist from bypassing admin field updates
        cls.__bypass_admin__ = False

        # Now save the leaderboards for all affected games again!.
        rlog.save_leaderboards(affected_games, "after")

        # Stop the timer and record the duration
        end = localtime()
        rlog.duration = end - start

        # And save the complete Rebuild Log entry
        rlog.save()

        if Trigger == RATING_REBUILD_TRIGGER.user_request:
            if settings.DEBUG:
                log.debug("Generating HTML diff.")

            # Add an html attribute to rlog (not a database field) so that the caller can render a report.
            rlog.html = BackupRating.html_diff()

        if settings.DEBUG:
            log.debug("Done.")

        return rlog

    @classmethod
    def estimate_rebuild_cost(cls, n=1):
        '''
        Uses the rebuild logs to estimate the cost of rebuilding.

        :param n: the number of sessions we'll rebuild ratings for.
        '''
        RebuildLog = apps.get_model(APP, "RebuildLog")

        Cost = ExpressionWrapper(F('duration') / F('ratings'), output_field=models.DurationField())
        Costs = RebuildLog.objects.all().annotate(cost=Cost).values_list('cost', flat=True)

        if Costs:
            costs = [c.total_seconds() for c in Costs]
            mean_cost = mean(costs)
            nstdev_cost = stdev(costs) / mean_cost

            cost_estimate = timedelta(seconds=n * mean_cost)  # The predicted cost of prebuilding n sessions
            cost_variance = timedelta(seconds=nstdev_cost)  # The coeeficient of variance (0 to 1)

            return cost_estimate, cost_variance
        else:
            return None

    def check_integrity(self, passthru=True):
        '''
        Perform integrity check on this rating record
        '''
        L = AssertLog(passthru)

        pfx = f"Rating Integrity error (id: {self.id}):"

        # Check for uniqueness
        same = Rating.objects.filter(player=self.player, game=self.game)
        L.Assert(same.count() <= 1, f"{pfx} Duplicate rating entries for player: {self.player} and game: {self.game}. Dupes are {[s.id for s in same]}")

        # Check that rating matches last performance
        last_play = self.last_performance
        last_win = self.last_winning_performance

        L.Assert(not last_play is None, f"{pfx} Has no Last Play!")

        if last_play:
            L.Assert(isclose(self.trueskill_mu, last_play.trueskill_mu_after, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance µ mismatch. Rating has {self.trueskill_mu} Last Play has {last_play.trueskill_mu_after}.")
            L.Assert(isclose(self.trueskill_sigma, last_play.trueskill_sigma_after, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance σ mismatch. Rating has {self.trueskill_sigma} Last Play has {last_play.trueskill_sigma_after}.")
            L.Assert(isclose(self.trueskill_eta, last_play.trueskill_eta_after, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance η mismatch. Rating has {self.trueskill_eta} Last Play has {last_play.trueskill_eta_after}.")

            L.Assert(isclose(self.trueskill_mu0, last_play.trueskill_mu0, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance µ0 mismatch. Rating has {self.trueskill_mu0} Last Play has {last_play.trueskill_mu0}.")
            L.Assert(isclose(self.trueskill_sigma0, last_play.trueskill_sigma0, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance σ0 mismatch. Rating has {self.trueskill_sigma0} Last Play has {last_play.trueskill_sigma0}.")
            L.Assert(isclose(self.trueskill_delta, last_play.trueskill_delta, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance δ mismatch. Rating has {self.trueskill_delta} Last Play has {last_play.trueskill_delta}.")

            L.Assert(isclose(self.trueskill_tau, last_play.trueskill_tau, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance τ mismatch. Rating has {self.trueskill_tau} Last Play has {last_play.trueskill_tau}.")
            L.Assert(isclose(self.trueskill_p, last_play.trueskill_p, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance p mismatch. Rating has {self.trueskill_p} Last Play has {last_play.trueskill_p}.")

            # Check that the play and victory counts reflect what Performance says
            L.Assert(self.plays == last_play.play_number, f"{pfx} Play count mismatch. Rating has {self.plays} Last play has {last_play.play_number}.")
            L.Assert(self.victories == last_play.victory_count, f"{pfx} Victory count mismatch. Rating has {self.victories} Last play has {last_play.victory_count}.")

            # Check that last_play and last_victory dates are accurate reflections on Performance records
            L.Assert(self.last_play == last_play.session.date_time, f"{pfx} Last play mismatch. Rating has {self.last_play} Last play has {last_play.session.date_time}.")

        if last_win:
            L.Assert(self.last_victory == last_win.session.date_time, f"{pfx} Last victory mismatch. Rating has {self.last_victory} Last victory has {last_win.session.date_time}.")
        else:
            L.Assert(self.last_victory == NEVER, f"{pfx} Last victory mismatch. Rating has {self.last_victory} when expecting the NEVER value of {NEVER}.")

        return L.assertion_failures

    def clean(self):
        # TODO: diagnose when this is called. What can we assume about session cleans? And what not?
        # This rating must be unique
        same = Rating.objects.filter(player=self.player, game=self.game)

        if same.count() > 1:
            raise ValidationError("Duplicate ratings found for player: {} and game: {}".format(self.player, self.game))

        # Rating should match the last performance
        # TODO: When do we land here? And how do we sync with self.update?

    class Meta(AdminModel.Meta):
        ordering = ['-trueskill_eta']
        verbose_name = "Rating"
        verbose_name_plural = "Ratings"


class BackupRating(RatingModel):
    '''
    A simple container for a complete backup of Rating.

    Used when doing a rebuild of ratings so as to have the previous copy on hand, and to be able to
    compare to see what the impact of the rebuild was. This can be very relevant if rebuilding because of
    a change to TrueSkill settings for example, when tuning the settings for particular games.

    # TODO: Put an option on the leaderboards view to see the Backup leaderboards, and another to show a comparison
    '''

    @classmethod
    def reset(cls):
        '''
        Deletes all backup ratings
        '''
        cls.objects.all().delete()

    @classmethod
    def clone(cls, rating):
        '''
        Clones a rating into the Backup model (database table)

        :param rating: A Rating object
        '''
        try:
            backup = cls.objects.get(player=rating.player, game=rating.game)
        except ObjectDoesNotExist:
            backup = cls()

        for field in rating._meta.fields:
            if not field.primary_key:
                setattr(backup, field.name, getattr(rating, field.name))

        backup.save()

    @classmethod
    def diff(cls, show_unchanged=True):
        '''
        Returns an a dictionary summarising differences between current ratings and
        backed up ratings. It is an ordered dictionary keyed on the tuple of player id
        and game id containing a 9 tuple of the old, diff and new values for the three
        rating measures (eta, mu, sigma)

        :param show_unchanged: Include ratings that didn't change.
        '''
        diffs = OrderedDict()
        for r in cls.objects.all().order_by('game', '-trueskill_eta'):
            R = Rating.get(r.player, r.game)

            diff_eta = R.trueskill_eta - r.trueskill_eta
            diff_mu = R.trueskill_mu - r.trueskill_mu
            diff_sigma = R.trueskill_sigma - r.trueskill_sigma

            if (show_unchanged
                or abs(diff_eta) > FLOAT_TOLERANCE
                or abs(diff_mu) > FLOAT_TOLERANCE
                or abs(diff_sigma) > FLOAT_TOLERANCE):
                diffs[(r.player.pk, r.game.pk)] = (r.trueskill_eta, r.trueskill_mu, r.trueskill_sigma,
                                                   diff_eta, diff_mu, diff_sigma,
                                                   R.trueskill_eta, R.trueskill_mu, R.trueskill_sigma)

        return diffs

    @classmethod
    def html_diff(cls, show_unchanged=True):
        '''
        Returns an HTML table (string) summarising differences between current ratings and
        backed up ratings.

        :param show_unchanged: Include ratings that didn't change.
        '''
        sign = lambda a: '-' if a < 0 else '+'

        diffs = cls.diff(show_unchanged)

        html = "<TABLE>"
        html += "<TR>"
        html += "<TH>Game</TH>"
        html += "<TH>Player</TH>"
        html += "<TH>Rating (η)</TH>"
        html += "<TH>Mean (µ)</TH>"
        html += "<TH>Standard Deviation(µ)</TH>"
        html += "</TR>"
        for r in cls.objects.all().order_by('game', '-trueskill_eta'):
            (old_eta, old_mu, old_sigma,
             diff_eta, diff_mu, diff_sigma,
             new_eta, new_mu, new_sigma) = diffs[(r.player.pk, r.game.pk)]

            eqn_eta = f"{old_eta:.4f} {sign(diff_eta)} {abs(diff_eta):.4f} = {new_eta:.4f}"
            eqn_mu = f"{old_mu:.4f} {sign(diff_mu)} {abs(diff_mu):.4f} = {new_mu:.4f}"
            eqn_sigma = f"{old_sigma:.4f} {sign(diff_sigma)} {abs(diff_sigma):.4f} = {new_sigma:.4f}"

            if (show_unchanged
                or abs(diff_eta) > FLOAT_TOLERANCE
                or abs(diff_mu) > FLOAT_TOLERANCE
                or abs(diff_sigma) > FLOAT_TOLERANCE):
                html += "<TR>"
                html += f"<TD>{r.game.name}</TD>"
                html += f"<TD>{r.player.name()}</TD>"
                html += f"<TD>{eqn_eta}</TD>"
                html += f"<TD>{eqn_mu}</TD>"
                html += f"<TD>{eqn_sigma}</TD>"
                html += "</TR>"
        html += "</TABLE>"

        return html
