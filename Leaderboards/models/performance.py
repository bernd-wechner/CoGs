from . import APP, FLOAT_TOLERANCE, TrueskillSettings
from .rank import Rank

from django.db import models
from django.db.models import Q, OuterRef, QuerySet, Subquery
from django.apps import apps
from django.urls import reverse
from django.core.exceptions import ValidationError

from django_cte import CTEManager

from django_model_admin_fields import AdminModel

from django_rich_views.util import AssertLog
from django_rich_views.model import field_render, link_target_url

import trueskill

from math import isclose
from datetime import datetime


class Performance(AdminModel):
    '''
    Each player in each session has a Performance associated with them.

    The only input here is the partial play weighting, which models just that, early departure from the game session before the game is complete.
    But can be used to arbitrarily weight contributions of players to teams as well if desired.

    This model also contains for each session a record of the calculated Trueskill performance of that player, namely trueskill values before
    and after the play (for data redundancy as the after values of one session are the before values of the next for a given player, which can
    also be asserted for data integrity).
    '''
    objects = CTEManager()

    TS = TrueskillSettings()

    session = models.ForeignKey('Session', verbose_name='Session', related_name='performances', on_delete=models.CASCADE)  # If the session is deleted, dlete this performance
    player = models.ForeignKey('Player', verbose_name='Player', related_name='performances', null=True, on_delete=models.SET_NULL)  # if the player is deleted keep this performance

    partial_play_weighting = models.FloatField('Partial Play Weighting (ω)', default=1)

    # What this player scored if the game has scores.
    # These scores are rarely if ever used and not used for ranking bar very indirectly
    # Typically ranks carry a score. But for the particular case of team based play, where
    # there's one rank per team, but the game has inbdividual scores, then we can record them
    # here. If scores are ever needed, rank scores are checked and if absent and performance
    # scores exists a rank score is calculated as the sum of the performance scores at that rank.
    # And so these are fall back, primarily informatic scores in some edge cases only.
    score = models.IntegerField('Score', default=None, null=True, blank=True)

    play_number = models.PositiveIntegerField('The number of this play (for this player at this game)', default=1, editable=False)
    victory_count = models.PositiveIntegerField('The count of victories after this session (for this player at this game)', default=0, editable=False)

    # Although Eta (η) is a simple function of Mu (µ) and Sigma (σ), we store it alongside Mu and Sigma because it is also a function of global settings µ0 and σ0.
    # To protect ourselves against changes to those global settings, or simply to detect them if it should happen, we capture their value at time of rating update in the Eta.
    # The before values are copied from the Rating for that Player/Game combo and the after values are written back to that Rating.
    trueskill_mu_before = models.FloatField('Trueskill Mean (µ) before the session.', default=TS.mu0, editable=False)
    trueskill_sigma_before = models.FloatField('Trueskill Standard Deviation (σ) before the session.', default=TS.sigma0, editable=False)
    trueskill_eta_before = models.FloatField('Trueskill Rating (η) before the session.', default=0, editable=False)

    trueskill_mu_after = models.FloatField('Trueskill Mean (µ) after the session.', default=TS.mu0, editable=False)
    trueskill_sigma_after = models.FloatField('Trueskill Standard Deviation (σ) after the session.', default=TS.sigma0, editable=False)
    trueskill_eta_after = models.FloatField('Trueskill Rating (η) after the session.', default=0, editable=False)

    # Record the global TrueskillSettings mu0, sigma0 and delta with each performance
    # This will allow us to reset ratings to the state they were at after this performance
    # It is an integrity measure as well against changes in these settings while a leaderboard
    # is running, which has significant consequences (suggesting a rebuild of all ratings is in
    # order)
    trueskill_mu0 = models.FloatField('Trueskill Initial Mean (µ)', default=trueskill.MU, editable=False)
    trueskill_sigma0 = models.FloatField('Trueskill Initial Standard Deviation (σ)', default=trueskill.SIGMA, editable=False)
    trueskill_delta = models.FloatField('TrueSkill Delta (δ)', default=trueskill.DELTA, editable=False)

    # Record the game specific Trueskill settings beta, tau and p with each performance.
    # Again for a given game these must be consistent among all ratings and the history of each rating.
    # Any change while managing leaderboards should trigger an update request for ratings relating to this game.
    trueskill_beta = models.FloatField('TrueSkill Skill Factor (ß)', default=trueskill.BETA, editable=False)
    trueskill_tau = models.FloatField('TrueSkill Dynamics Factor (τ)', default=trueskill.TAU, editable=False)
    trueskill_p = models.FloatField('TrueSkill Draw Probability (p)', default=trueskill.DRAW_PROBABILITY, editable=False)

    Game = apps.get_model(APP, "Game", require_ready=False)
    Rank = apps.get_model(APP, "Rank", require_ready=False)
    Rating = apps.get_model(APP, "Rating", require_ready=False)

    @property
    def game(self) -> Game:
        '''
        The game this performance relates to
        '''
        return self.session.game

    @property
    def date_time(self) -> datetime:
        '''
        The game this performance relates to
        '''
        return self.session.date_time

    @property
    def rank(self) -> Rank:
        '''
        The rank of this player in this session. Most certainly a component of a player's
        performance, but not stored in the Performance model because it is associated either
        with a player or whole team depending on the play mode (Individual or Team). So this
        property fetches the rank from the Rank model where it's stored.
        '''
        Rank = apps.get_model(APP, "Rank")

        sfilter = Q(session=self.session)
        ipfilter = Q(player=self.player)
        tpfilter = Q(team__players=self.player)
        rfilter = sfilter & (ipfilter | tpfilter)
        return Rank.objects.filter(rfilter).first()

    @property
    def is_victory(self) -> bool:
        '''
        True if this performance records a victory for the player, False if not.
        '''
        return self.rank == 1

    @property
    def rating(self) -> Rating:
        '''
        Returns the rating object associated with this performance. That is for the same player/game combo.
        '''
        Rating = apps.get_model(APP, "Rating")

        try:
            r = Rating.objects.get(player=self.player, game=self.session.game)
        except Rating.DoesNotExist:
            r = Rating.create(player=self.player, game=self.session.game)
        except Rating.MultipleObjectsReturned:
            raise ValueError("Database error: more than one rating for {} at {}".format(self.player.name_nickname, self.session.game.name))
        return r

    @property
    def previous_play(self) -> 'Performance':
        '''
        Returns the previous performance object that this player played this game in.
        '''
        return self.session.previous_performance(self.player)

    @property
    def previous_win(self) -> 'Performance':
        '''
        Returns the previous performance object that this player played this game in and one in
        '''
        return self.session.previous_victory(self.player)

    @property
    def link_internal(self) -> str:
        return reverse('view', kwargs={"model":self._meta.model.__name__, "pk": self.pk})

    def initialise(self, save=False):
        '''
        Initialises the performance object.

        With the session and player already known,
        finds the previous session that this player played this game in
        and copies the after ratings of the previous performance (for this
        player at this session's game) to the before ratings of this
        performance object for that player.
        '''

        previous = self.session.previous_performance(self.player)

        if previous is None:
            TSS = TrueskillSettings()
            self.play_number = 1
            self.victory_count = 1 if self.session.rank(self.player).rank == 1 else 0
            self.trueskill_mu_before = TSS.mu0
            self.trueskill_sigma_before = TSS.sigma0
            self.trueskill_eta_before = 0

        else:
            self.play_number = previous.play_number + 1
            self.victory_count = previous.victory_count + 1 if self.session.rank(self.player).rank == 1 else previous.victory_count
            self.trueskill_mu_before = previous.trueskill_mu_after
            self.trueskill_sigma_before = previous.trueskill_sigma_after
            self.trueskill_eta_before = previous.trueskill_eta_after

        # Capture the Trueskill settings that are in place now too.
        TS = TrueskillSettings()
        self.trueskill_mu0 = TS.mu0
        self.trueskill_sigma0 = TS.sigma0
        self.trueskill_delta = TS.delta
        self.trueskill_beta = self.session.game.trueskill_beta
        self.trueskill_tau = self.session.game.trueskill_tau
        self.trueskill_p = self.session.game.trueskill_p

        if save:
            self.save()

    def check_integrity(self, passthru=True):
        '''
        Perform basic integrity checks on this Performance object.
        '''
        L = AssertLog(passthru)

        pfx = f"Performance Integrity error (id: {self.id}):"

        # Check that the before values match the after values of the previous play
        performance = self
        previous = self.previous_play

        if previous is None:
            TS = TrueskillSettings()

            trueskill_eta = TS.mu0 - TS.mu0 / TS.sigma0 * TS.sigma0

            L.Assert(isclose(performance.trueskill_mu_before, TS.mu0, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance µ mismatch. Before at {performance.session.date_time} is {performance.trueskill_mu_before} and After on previous at Never is {TS.mu0} (the default)")
            L.Assert(isclose(performance.trueskill_sigma_before, TS.sigma0, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance σ mismatch. Before at {performance.session.date_time} is {performance.trueskill_sigma_before} and After on previous at Never is {TS.sigma0} (the default)")
            L.Assert(isclose(performance.trueskill_eta_before, trueskill_eta, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance η mismatch. Before at {performance.session.date_time} is {performance.trueskill_eta_before} and After on previous at Never is {trueskill_eta} (the default)")
        else:
            L.Assert(isclose(performance.trueskill_mu_before, previous.trueskill_mu_after, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance µ mismatch. Before at {performance.session.date_time} is {performance.trueskill_mu_before} and After on previous at {previous.session.date_time} is {previous.trueskill_mu_after}")
            L.Assert(isclose(performance.trueskill_sigma_before, previous.trueskill_sigma_after, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance σ mismatch. Before at {performance.session.date_time} is {performance.trueskill_sigma_before} and After on previous at {previous.session.date_time} is {previous.trueskill_sigma_after}")
            L.Assert(isclose(performance.trueskill_eta_before, previous.trueskill_eta_after, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance η mismatch. Before at {performance.session.date_time} is {performance.trueskill_eta_before} and After on previous at {previous.session.date_time} is {previous.trueskill_eta_after}")

        # Check that the Trueskill settings are consistent with previous play too
        if previous is None:
            TS = TrueskillSettings()

            L.Assert(isclose(performance.trueskill_mu0, TS.mu0, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance µ0 mismatch. At {performance.session.date_time} is {performance.trueskill_mu0} and previous at Never is {TS.mu0}")
            L.Assert(isclose(performance.trueskill_sigma0, TS.sigma0, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance σ0 mismatch. At {performance.session.date_time} is {performance.trueskill_sigma0} and on previous at Never is {TS.sigma0}")
            L.Assert(isclose(performance.trueskill_delta, TS.delta, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance δ mismatch. At {performance.session.date_time} is {performance.trueskill_delta} and previous at Never is {TS.delta}")
        else:
            L.Assert(isclose(performance.trueskill_mu0, previous.trueskill_mu0, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance µ0 mismatch. At {performance.session.date_time} is {performance.trueskill_mu0} and previous at {previous.session.date_time} is {previous.trueskill_mu0}")
            L.Assert(isclose(performance.trueskill_sigma0, previous.trueskill_sigma0, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance σ0 mismatch. At {performance.session.date_time} is {performance.trueskill_sigma0} and previous at {previous.session.date_time} is {previous.trueskill_sigma0}")
            L.Assert(isclose(performance.trueskill_delta, previous.trueskill_delta, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance δ mismatch. At {performance.session.date_time} is {performance.trueskill_delta} and previous at {previous.session.date_time} is {previous.trueskill_delta}")
            L.Assert(isclose(performance.trueskill_beta, previous.trueskill_beta, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance ß mismatch. At {performance.session.date_time} is {performance.trueskill_beta} and previous at {previous.session.date_time} is {previous.trueskill_beta}")
            L.Assert(isclose(performance.trueskill_tau, previous.trueskill_tau, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance τ mismatch. At {performance.session.date_time} is {performance.trueskill_tau} and previous at {previous.session.date_time} is {previous.trueskill_tau}")
            L.Assert(isclose(performance.trueskill_p, previous.trueskill_p, abs_tol=FLOAT_TOLERANCE), f"{pfx} Performance p mismatch. At {performance.session.date_time} is {performance.trueskill_p} and previous at {previous.session.date_time} is {previous.trueskill_p}")

        # Check that there is an associate Rank
        L.Assert(not self.rank is None, f"{pfx} Has no associated rank!")

        # if self.player.pk == 1 and self.session.game.pk == 29 and self.session.date_time.year == 2021:
            # breakpoint()

        # Check that play number and victory count reflect earlier records
        expected_play_number = self.session.previous_sessions(self.player).count()  # Includes the current sessions
        expected_victory_count = self.session.previous_victories(self.player).count()  # Includes the current session if it's a victory

        L.Assert(self.play_number == expected_play_number, f"{pfx} Play number is wrong. Play number: {self.play_number}, Expected: {expected_play_number}.")
        L.Assert(self.victory_count == expected_victory_count, f"{pfx} Victory count is wrong. Victory count: {self.victory_count}, Expected: {expected_victory_count}.")

        return L.assertion_failures

    def clean(self):
        return  # Disable for now, enable only for testing

        # Find the previous performance for this player at this game and copy
        # the trueskill after values to the trueskill before values in this
        # performance or from initials if no previous.
        previous = self.previous_play

        if previous is None:
            TS = TrueskillSettings()

            self.trueskill_mu_before = TS.mu0
            self.trueskill_sigma_before = TS.sigma0
            self.trueskill_eta_before = 0
        else:
            self.trueskill_mu_before = previous.trueskill_mu_after
            self.trueskill_sigma_before = previous.trueskill_sigma_after
            self.trueskill_eta_before = previous.trueskill_eta_after

        # Catch the Trueskill settings in effect now.
        TS = TrueskillSettings()
        self.trueskill_mu0 = TS.mu0
        self.trueskill_sigma0 = TS.sigma0
        self.trueskill_beta = TS.beta
        self.trueskill_delta = TS.delta
        self.trueskill_tau = self.session.game.trueskill_tau
        self.trueskill_p = self.session.game.trueskill_p

        # If any of these settings have changed since the previous performance (for this player at this game)
        # Then we have an error that demands a rebuild of ratings for this game.
        if not previous is None:
            if self.trueskill_mu0 != previous.trueskill_mu0:
                raise ValidationError("Global Trueskill µ0 has changed (from {} to {}). Either reset the value of rebuild all ratings for game {} ({}) ".format(self.trueskill_mu0, previous.trueskill_mu0, self.session.game.pk, self.session.game))
            if self.trueskill_sigma0 != previous.trueskill_sigma0:
                raise ValidationError("Global Trueskill σ0 has changed (from {} to {}). Either reset the value of rebuild all ratings for game {} ({}) ".format(self.trueskill_sigma0, previous.trueskill_sigma0, self.session.game.pk, self.session.game))
            if self.trueskill_beta != previous.trueskill_beta:
                raise ValidationError("Global Trueskill ß has changed (from {} to {}). Either reset the value of rebuild all ratings for game {} ({}) ".format(self.trueskill_beta, previous.trueskill_beta, self.session.game.pk, self.session.game))
            if self.trueskill_delta != previous.trueskill_delta:
                raise ValidationError("Global Trueskill δ has changed (from {} to {}). Either reset the value of rebuild all ratings for game {} ({}) ".format(self.trueskill_delta, previous.trueskill_delta, self.session.game.pk, self.session.game))
            if self.trueskill_tau != previous.trueskill_tau:
                raise ValidationError("Game Trueskill τ has changed (from {} to {}). Either reset the value of rebuild all ratings for game {} ({}) ".format(self.trueskill_tau, previous.trueskill_tau, self.session.game.pk, self.session.game))
            if self.trueskill_p != previous.trueskill_p:
                raise ValidationError("Game Trueskill p has changed (from {} to {}). Either reset the value of rebuild all ratings for game {} ({}) ".format(self.trueskill_p, previous.trueskill_p, self.session.game.pk, self.session.game))

        # Update the play counters too. We know this form submisison means one more play but we don't necessariuly know if it's
        # a victury yet (as that is stored with an associated Rank which may or may not have been saved yet).
        self.play_number = previous.play_number + 1

        if self.session.rank(self.player):
            self.victory_count = previous.victory_count + 1 if self.session.rank(self.player).rank == 1 else previous.victory_count

        # Trueskill Impact is calculated at the session level not the individual performance level.
        # The trueskill after settings for the performance will be calculated there.
        pass

    intrinsic_relations = None
    sort_by = ['session.date_time', 'rank.rank', 'player.name_nickname']  # Need player to sort ties and team members.

    # It is crucial that Performances for a session are ordered the same as Ranks when a rich form is constructed
    # Each row on a form in a standard session submission has a rank and a performance associated with it and the
    # player for each object must agree.
    @classmethod
    def form_order(cls, performances) -> QuerySet:
        '''
        Form field ordering support for Django Rich Views RelatedFormsets

        if this class method exists, DGVE will call it to order objects when building related forms.

        This returns the performances in order of the players ranking. Must return a QuerySet.

        :param performances:  A QuerySet
        '''
        # Annotate with ranking ('rank' is a method above and clashes, crashing the queryset evaluation)
        sfilter = Q(session=OuterRef('session'))
        ipfilter = Q(player=OuterRef('player'))
        tpfilter = Q(team__players=OuterRef('player'))
        rfilter = sfilter & (ipfilter | tpfilter)
        ranking = Subquery(Rank.objects.filter(rfilter).values('rank'))
        ranked_performances = performances.annotate(ranking=ranking)
        return ranked_performances.order_by('ranking')

    def __unicode__(self):
        return  u'{}'.format(self.player)

    def __str__(self): return self.__unicode__()

    def __verbose_str__(self):
        if self.session is None:  # Don't crash of the performance is orphaned!
            when = "<no time>"
            game = "<no game>"
        else:
            when = self.session.date_time
            game = self.session.game
        performer = self.player
        return  u'{} - {:%d, %b %Y} - {}'.format(game, when, performer)

    def __rich_str__(self, link=None):
        if self.session is None:  # Don't crash of the performance is orphaned!
            when = "<no time>"
            game = "<no game>"
        else:
            when = self.session.date_time
            game = field_render(self.session.game, link)
        performer = field_render(self.player, link)
        performance = "{:.0%} participation, play number {}, {:+.1f} teeth".format(self.partial_play_weighting, self.play_number, self.trueskill_eta_after - self.trueskill_eta_before)
        return  u'{} - {:%d, %b %Y} - {}: {}'.format(game, when, performer, field_render(performance, link_target_url(self, link)))

    def __detail_str__(self, link=None):
        if self.session is None:  # Don't crash of the performance is orphaned!
            when = "<no time>"
            game = "<no game>"
            players = "<no players>"
        else:
            when = self.session.date_time
            game = field_render(self.session.game, link)
            players = len(self.session.players)

        performer = field_render(self.player, link)

        detail = u'{} - {:%a, %-d %b %Y} - {}:<UL>'.format(game, when, performer)
        detail += "<LI>Players: {}</LI>".format(players)
        detail += "<LI>Play number: {}</LI>".format(self.play_number)
        detail += "<LI>Play Weighting: {:.0%}</LI>".format(self.partial_play_weighting)
        detail += "<LI>Trueskill Delta: {:+.1f} teeth</LI>".format(self.trueskill_eta_after - self.trueskill_eta_before)
        detail += "<LI>Victories: {}</LI>".format(self.victory_count)
        detail += "</UL>"
        return detail

    class Meta(AdminModel.Meta):
        verbose_name = "Performance"
        verbose_name_plural = "Performances"
        ordering = ['session', 'player']

