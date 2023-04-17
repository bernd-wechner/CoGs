from . import APP, MIN_TIME_DELTA, FLOAT_TOLERANCE, MISSING_VALUE, TrueskillSettings

from ..leaderboards.enums import LB_PLAYER_LIST_STYLE, LB_STRUCTURE
from ..leaderboards.player import player_rankings
from ..trueskill_helpers import TrueSkillHelpers  # Helper functions for TrueSkill, based on "Understanding TrueSkill"

from django.db import models, IntegrityError
from django.db.models import Q
from django.conf import settings
from django.apps import apps
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import localize
from django.utils.timezone import localtime
from django.utils.safestring import mark_safe
from django.utils.functional import cached_property
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder

from django_cte import CTEManager

from django_model_admin_fields import AdminModel
from django_cache_memoized import memoized

from django_rich_views import FIELD_LINK_CLASS
from django_rich_views.model import TimeZoneMixIn, NotesMixIn, field_render, link_target_url, safe_get
from django_rich_views.util import AssertLog
from django_rich_views.html import NEVER
from django_rich_views.options import flt, osf
from django_rich_views.datetime import safe_tz, time_str, make_aware
from django_rich_views.decorators import property_method

from timezone_field import TimeZoneField

from typing import Union
from dateutil import parser
from datetime import datetime, timedelta
from collections import OrderedDict

from math import isclose

import trueskill
import json
import re

from Site.logutils import log

from Import.models import Import

def game_duration(session):
    '''
    Return a time delta suggestion for a new session from the last session. That is, just return the
    expected duration of the game in session.

    :param session: A session that identifies the game
    '''
    return session.game.expected_play_time


class Session(AdminModel, TimeZoneMixIn, NotesMixIn):
    '''
    The record, with results (Ranks), of a particular Game being played competitively.
    '''
    objects = CTEManager()

    game = models.ForeignKey('Game', verbose_name='Game', related_name='sessions', null=True, on_delete=models.SET_NULL)  # If the game is deleted keep the session.

    # Note: date_time initial has an inherited delta below (inherit_fields and inherit_time_delta)
    date_time = models.DateTimeField('Time', default=timezone.now)
    date_time_tz = TimeZoneField('Timezone', default=settings.TIME_ZONE, editable=False)

    league = models.ForeignKey('League', verbose_name='League', related_name='sessions', null=True, on_delete=models.SET_NULL)  # If the league is deleted keep the session
    location = models.ForeignKey('Location', verbose_name='Location', related_name='sessions', null=True, on_delete=models.SET_NULL)  # If the location is deleted keep the session

    # The game must support team play if this is true,
    # and conversely, it must support individual play if this false.
    team_play = models.BooleanField('Team Play', default=False)  # By default games are played by individuals, if true, this session was played by teams

    # Optionally associate with an import. We call it "source" and if it is null (none)
    # this suggests not imported but entered directly through the UI.
    source = models.ForeignKey(Import, verbose_name='Source', related_name='sessions', editable=False, null=True, blank=True, on_delete=models.SET_NULL)

    # Foreign Keys that for part of a rich session object
    # ranks = ForeignKey from Rank (one rank per player or team depending on mode)
    # performances = ForeignKey from Performance (one performance per player)

    # A note on session player records:
    #  Players are stored in two distinct places/contexts:
    #    1) In the Performance model - which records each players TrueSkill performance in this session
    #    2) in the Rank model - which records each player or teams rank (placement in the results)
    #
    # The simpler list of players in a sessions is in the Performance model where each player in each session has performance recorded.
    #
    # A less direct record of the players in a  sessionis in the Rank model,
    #     either one player per Rank (in an Individual play session) or one Team per rank (in a Team play session)
    #     This is because ranks are associated with players in individual play mode but teams in Team play mode,
    #     while performance is always tracked by player.

    # TODO: consider if we can filter on properties or specify annotations somehow to filter on them
    filter_options = ['date_time__gt', 'date_time__lt', 'game']
    order_options = ['date_time', 'game', 'league']

    # Two equivalent ways of specifying the related forms that django-generic-view-extensions supports:
    # Am testing the new simpler way now leaving it in place for a while to see if any issues arise.
    # intrinsic_relations = ["Rank.session", "Performance.session"]  # When adding a session, add the related Rank and Performance objects
    intrinsic_relations = ["ranks", "performances"]  # When adding a session, add the related Rank and Performance objects

    # Specify which fields to inherit from entry to entry when creating a string of objects
    inherit_fields = ["date_time", "league", "location", "game"]
    inherit_time_delta = game_duration  # A callable (function) that is supplies with the previous session

    @property
    def date_time_local(self):
        return self.date_time.astimezone(safe_tz(self.date_time_tz))

    @property
    def num_competitors(self) -> int:
        '''
        Returns an integer count of the number of competitors in this game session,
        i.e. number of players in a single-player mode or number of teams in team player mode
        '''
        if self.team_play:
            return len(self.teams)
        else:
            return len(self.players)

    @property
    def str_competitors(self) -> str:
        '''
        Returns a simple string to append to a number which represents the "competitors"
        That is, "team", "teams", "player", or "players" as appropriate. A 1 player
        game is a solo game clearly.
        '''
        n = self.num_competitors
        if self.team_play:
            if n == 1:
                return "team"
            else:
                return "teams"
        else:
            if n == 1:
                return "player"
            else:
                return "players"

    def _ranked_players(self, as_string, link=None) -> Union[dict, str]:
        '''
        Internal factory for ranked_players and str_ranked_players.

        Returns an OrderedDict (keyed on rank) of the players in the session.
        or a CSV string summaring same.

        The value of the dict is a player. The key is "rank.tie_index.team_index"

        :param as_string:  Return a CSV string, else a dict with a compound key
        :param link:    Wrap player names in links according to the provided style.
        '''
        Rank = apps.get_model(APP, "Rank")

        if as_string:
            players = []  # Build list to join later
        else:
            players = OrderedDict()

        ranks = Rank.objects.filter(session=self.id)

        # A quick loop through to check for ties as they will demand some
        # special handling when we collect the list of players into the
        # keyed (by rank) dictionary.
        tie_counts = OrderedDict()
        in_rank_id = OrderedDict()
        for rank in ranks:
            # rank is the rank object, rank.rank is the integer rank (1, 2, 3).
            if rank.rank in tie_counts:
                tie_counts[rank.rank] += 1
                in_rank_id[rank.rank] = 1
            else:
                tie_counts[rank.rank] = 1

        if as_string:
            at_rank = None  # For keeping track of a rank during tie (which see multple rank objects at the same ranking)
            team_separator = "+"
            tie_separator = "/"

        for rank in ranks:
            # rank is the rank object, rank.rank is the integer rank (1, 2, 3).
            if self.team_play:
                if as_string and rank.rank != at_rank and len(players) > 0 and isinstance(players[-1], list):  # The tie-list is complete so we can stringify it
                    tie_members = players.pop()
                    players.append(tie_separator.join(tie_members))
                    at_rank = None

                if tie_counts[rank.rank] > 1:
                    if as_string:
                        team_members = team_separator.join([field_render(player.name_nickname, link_target_url(player, link)) for player in rank.players])

                        if rank.rank == at_rank:
                            players[-1].append(team_members)
                        else:
                            players.append([team_members])
                            at_rank = rank.rank
                    else:
                        for pid, player in enumerate(rank.players):
                            players[f"{rank.rank}.{in_rank_id[rank.rank]}.{pid}"] = player
                        in_rank_id[rank.rank] += 1
                else:
                    if as_string:
                        team_members = team_separator.join([field_render(player.name_nickname, link_target_url(player, link)) for player in rank.players])
                        players.append(team_members)
                    else:
                        pid = 1
                        for player in rank.players:
                            players[f"{rank.rank}.{pid}"] = player
                            pid += 1
            else:
                # The players can be listed (indexed) in rank order.
                # When there are multiple players at the same rank (ties)
                # We use a decimal format of rank.person to ensure that
                # the sorting remains more or less sensible.
                if as_string and rank.rank != at_rank and len(players) > 0 and isinstance(players[-1], list):  # The tie-list is complete so we can stringify it
                    tie_members = players.pop()
                    players.append(tie_separator.join(tie_members))
                    at_rank = None

                if tie_counts[rank.rank] > 1:  # There is a tie!
                    if as_string:
                        name = field_render(rank.player.name_nickname, link_target_url(rank.player, link))
                        if rank.rank == at_rank:
                            players[-1].append(name)
                        else:
                            players.append([name])
                            at_rank = rank.rank
                    else:
                        players[f"{rank.rank}.{in_rank_id[rank.rank]}"] = rank.player
                        in_rank_id[rank.rank] += 1
                else:  # There is no tie
                    if as_string:
                        name = field_render(rank.player.name_nickname, link_target_url(rank.player, link))
                        players.append(name)
                    else:
                        players[f"{rank.rank}"] = rank.player

        if as_string and isinstance(players[-1], list):  # The tie-list is complete so we can stringify it
            tie_members = players.pop()
            players.append(tie_separator.join(tie_members))

        return ", ".join(players) if as_string else players

    @property
    def ranked_players(self) -> dict:
        '''
        Returns a dict of players with the key storing rank information in form:

        rank.tie_index.team_index
        '''
        return self._ranked_players(False)

    @property_method
    def str_ranked_players(self, link=flt.internal) -> str:
        '''
        Returns a list of players (as a CSV string) in rank order (with team members and ties annotated)
        '''
        return self._ranked_players(True, link)

    @property
    def players(self) -> set:
        '''
        Returns an unordered set of the players in the session, with no guaranteed
        order. Useful for traversing a list of all players in a session
        irrespective of the structure of teams or otherwise.

        '''
        Performance = apps.get_model(APP, "Performance")

        players = set()
        performances = Performance.objects.filter(session=self.pk)

        for performance in performances:
            players.add(performance.player)

        return players

    @property
    def ranked_teams(self) -> dict:
        '''
        Returns an OrderedDict (keyed on rank) of the teams in the session.
        The value is a list of players (in team play sessions)
        Returns an empty dictionary for Individual play sessions

        Note ties have the same rank, so the key has a .index appended,
        to form a unique key. Only the key digits up to the . represent
        the true rank, the full key permits sorting and inique storage
        in a dictionary.
        '''
        Rank = apps.get_model(APP, "Rank")

        teams = OrderedDict()
        if self.team_play:
            ranks = Rank.objects.filter(session=self.id)

            # a quick loop through to check for ties as they will demand some
            # special handling when we collect the list of players into the
            # keyed (by rank) dictionary.
            rank_counts = OrderedDict()
            rank_id = OrderedDict()
            for rank in ranks:
                # rank is the rank object, rank.rank is the integer rank (1, 2, 3).
                if rank.rank in rank_counts:
                    rank_counts[rank.rank] += 1
                    rank_id[rank.rank] = 1
                else:
                    rank_counts[rank.rank] = 1

            for rank in ranks:
                # The players can be listed (indexed) in rank order.
                # When there are multiple players at the same rank (ties)
                # We use a decimal format of rank.person to ensure that
                # the sorting remains more or less sensible.
                if rank_counts[rank.rank] > 1:
                    teams["{}.{}".format(rank.rank, rank_id[rank.rank])] = rank.team
                    rank_id[rank.rank] += 1
                else:
                    teams["{}".format(rank.rank)] = rank.team
        return teams

    @property
    def teams(self) -> set:
        '''
        Returns an unordered set of the teams in the session, with no guaranteed
        order. Useful for traversing a list of all teams in a session
        irrespective of the ranking.

        '''
        Rank = apps.get_model(APP, "Rank")

        teams = set()

        if self.team_play:
            ranks = Rank.objects.filter(session=self.pk)

            for rank in ranks:
                teams.add(rank.team)

            return teams
        else:
            return None

    @property
    def victors(self) -> set:
        '''
        Returns the victors, a set of players or teams. Plural because of possible draws.
        '''
        Rank = apps.get_model(APP, "Rank")

        victors = set()
        ranks = Rank.objects.filter(session=self.id)

        for rank in ranks:
            # rank is the rank object, rank.rank is the integer rank (1, 2, 3).
            if self.team_play:
                if rank.rank == 1:
                    victors.add(rank.team)
            else:
                if rank.rank == 1:
                    victors.add(rank.player)
        return victors

    @property
    def trueskill_impacts(self) -> dict:
        '''
        Returns the recorded trueskill impacts of this session.
        Does not (re)calculate them, reads the recorded Performance records
        '''
        players_left = self.players

        impact = OrderedDict()
        for performance in self.performances.all():
            if performance.player in players_left:
                players_left.discard(performance.player)
            else:
                raise IntegrityError("Integrity error: Session has a player performance without a matching rank. Session id: {}, Performance id: {}".format(self.id, performance.id))

            impact[performance.player] = OrderedDict([
                ('plays', performance.play_number),
                ('victories', performance.victory_count),
                ('last_play', performance.session.date_time),
                ('last_victory', performance.session.date_time if performance.is_victory else performance.rating.last_victory),
                ('delta', OrderedDict([
                            ('mu', performance.trueskill_mu_after - performance.trueskill_mu_before),
                            ('sigma', performance.trueskill_sigma_after - performance.trueskill_sigma_before),
                            ('eta', performance.trueskill_eta_after - performance.trueskill_eta_before)
                            ])),
                ('after', OrderedDict([
                            ('mu', performance.trueskill_mu_after),
                            ('sigma', performance.trueskill_sigma_after),
                            ('eta', performance.trueskill_eta_after)
                            ])),
                ('before', OrderedDict([
                            ('mu', performance.trueskill_mu_before),
                            ('sigma', performance.trueskill_sigma_before),
                            ('eta', performance.trueskill_eta_before)
                            ]))
            ])

        assert len(players_left) == 0, "Integrity error: Session has ranked players without a matching performance. Session id: {}, Players: {}".format(self.id, players_left)

        return impact

    @property
    def trueskill_code(self) -> str:
        '''
        A debugging property that prints python code that will replicate this trueskill calculation
        So that this specific trueksill calculation might be diagnosed and debugged in isolation.
        '''
        TSS = TrueskillSettings()
        OldRatingGroups, Weights, Ranking = self.build_trueskill_data()

        code = []
        code.append("<pre>#!/usr/bin/python3")
        code.append("import trueskill")
        code.append("mu0 = {}".format(TSS.mu0))
        code.append("sigma0 = {}".format(TSS.sigma0))
        code.append("delta = {}".format(TSS.delta))
        code.append("beta = {}".format(self.game.trueskill_beta))
        code.append("tau = {}".format(self.game.trueskill_tau))
        code.append("p = {}".format(self.game.trueskill_p))
        code.append("TS = trueskill.TrueSkill(mu=mu0, sigma=sigma0, beta=beta, tau=tau, draw_probability=p)")
        code.append("oldRGs = {}".format(str(OldRatingGroups)))
        code.append("Weights = {}".format(str(Weights)))
        code.append("Ranking = {}".format(str(Ranking)))
        code.append("newRGs = TS.rate(oldRGs, Ranking, Weights, delta)")
        code.append("print(newRGs)")
        code.append("</pre>")
        return "\n".join(code)

    def _get_future_sessions(self, sessions_so_far):
        '''
        Internal support for the future_session property, this is a recursive method
        that takes a list of sessions found so far so as to avoid duplicating any
        sessions in the search.

        Why recursion? Because future sessions is an influence tree where each
        node branches a multiple of times. Consider agame that involves four
        playes P1, P2, P3, P4. We can get all future session in this game that
        any of these four players played in with a simple query. BUT in all
        those sessions they maybe (probably) played with otehr people. So say
        theres a futre session between P1, P2, P5 and P6? Well we need to find
        all the future sessions in this game that involve P1, P2, P5 or P6! So
        essentially future sessions fromt he simpe query can drag in new players
        which form new influence trees.

        The premise in building this tree is that it is is far more efficient than
        reacuaulating Trueskill ratings on them all. Thus finding a count helps us
        estimate the cost of performing a rebuild.

        sessions_so_far: A list of sessions found so far, that is augmented and returned
        '''
        # We want session in the future only of course
        dfilter = Q(date_time__gt=self.date_time)

        # We want only sessions for this sessions game
        gfilter = Q(game=self.game)

        # For each player we find all future sessions playing this game
        pfilter = Q(performances__player__in=self.players)

        # Combine the filters
        filters = dfilter & gfilter & pfilter

        # Get the list of PKs to exclude
        exclude_pks = list(map(lambda s: s.pk, sessions_so_far))

        new_future_sessions = Session.objects.filter(filters).exclude(pk__in=exclude_pks).distinct().order_by('date_time')

        if new_future_sessions.count() > 0:
            # augment sessions_so far
            sessions_so_far += list(new_future_sessions)

            # The new future sessions may involve new players which
            # requires that we scan them for new future sessions too
            for session in new_future_sessions:
                new_sessions_so_far = session._get_future_sessions(sessions_so_far)

                if len(new_sessions_so_far) > len(sessions_so_far):
                    sessions_so_far = sorted(new_sessions_so_far, key=lambda s: s.date_time)

        return sessions_so_far

    @property
    def future_sessions(self) -> list:
        '''
        Returns the sessions ordered by date_time that are in the future relative to this session
        that involve this game and any of the players in this session, or players in those sessions.

        Namely every session that needs to be re-evaluated because this one has been inserted before
        it, or edited in some way.
        '''
        return self._get_future_sessions([])

    @property
    def link_internal(self) -> str:
        return reverse('view', kwargs={"model":self._meta.model.__name__, "pk": self.pk})

    @property_method
    def actual_ranking(self, as_ranks=False) -> tuple:
        '''
        Returns a 2-tuple of:

        The first entry: either:
            a tuple of rankers (Players, Teams, or tuple of same for ties)
            a tuple of ranks (Ranks)
        in the actual recorded order as the first element.

        The second entry: the probability associated with that observation based on skills of
        players in the session.

        :param as_ranks: return Ranks, else Players/Teams
        '''
        g = self.game
        ts = TrueSkillHelpers(tau=g.trueskill_tau, beta=g.trueskill_beta, p=g.trueskill_p)
        return ts.Actual_ranking(self, as_ranks=as_ranks)

    @property_method
    def predicted_ranking(self, with_performances=False) -> tuple:
        '''
        Returns a tuple of rankers (Players, teams, or tuple of same for ties) in the predicted
        order (based on skills entering the session) as the first element in a tuple.

        The second is the probability associated with that prediction based on skills of
        players in the session.

        :param with_performances: If True, returns a 3-tuple including the a tuple of expected
                                  performances as the last item, with a 1 to 1 mapping with the
                                  first element (the tuple of rankers).
        '''
        g = self.game
        ts = TrueSkillHelpers(tau=g.trueskill_tau, beta=g.trueskill_beta, p=g.trueskill_p)
        return ts.Predicted_ranking(self, with_performances=with_performances)

    @property_method
    def predicted_ranking_after(self, with_performances=False) -> tuple:
        '''
        Returns a tuple of rankers (Players, teams, or tuple of same for ties) in the predicted
        order (using skills updated on the basis of the actual results) as the first element in a tuple.

        The second is the probability associated with that prediction based on skills of
        players in the session.

        :param with_performances: If True, returns a 3-tuple including the a tuple of expected
                                  performances as the last item, with a 1 to 1 mapping with the
                                  first element (the tuple of rankers).
        '''
        g = self.game
        ts = TrueSkillHelpers(tau=g.trueskill_tau, beta=g.trueskill_beta, p=g.trueskill_p)
        return ts.Predicted_ranking(self, with_performances=with_performances, after=True)

    @property
    def relationships(self) -> set:
        '''
        Returns a list of tuples containing player or team pairs representing
        each ranker (contestant) relationship in the game.

        Tuples always ordered (victor, loser) except on draws in which case arbitrary.
        '''
        ranks = self.ranks.all()
        relationships = set()
        # Not the most efficient walk but a single game has a comparatively small
        # number of rankers (players or teams ranking) and efficiency not a drama
        # More efficient would be not rewalk walked ground (i.e second loop only has
        # to go from outer loop index up to end.
        for rank1 in ranks:
            for rank2 in ranks:
                if rank1 != rank2:
                    relationship = (rank1.ranker, rank2.ranker) if rank1.rank < rank2.rank else (rank2.ranker, rank1.ranker)
                    if not relationship in relationships:
                        relationships.add(relationship)

        return relationships

    @property
    def player_relationships(self) -> set:
        '''
        Returns a list of tuples containing player pairs representing each player relationship
        in the game. Sale as self.relationships() in individual play mode, differs onl in team
        mode in that it find all the player relationships and ignores team relationships.

        Tuples always ordered (victor, loser) except on draws in which case arbitrary.
        '''
        performances = self.performances.all()
        relationships = set()
        # Not the most efficient walk but a single game has a comparatively small
        # number of rankers (players or teams ranking) and efficiency not a drama
        # More efficient would be not rewalk walked ground (i.e second loop only has
        # to go from outer loop index up to end.
        for performance1 in performances:
            for performance2 in performances:
                # Only need relationships where 1 beats 2 or there's a draw
                if performance1.rank.rank <= performance2.rank.rank and performance1.player != performance2.player:
                    relationship = (performance1.player, performance2.player)
                    back_relationship = (performance2.player, performance1.player)
                    if not back_relationship in relationships:
                        relationships.add(relationship)

        return relationships

    def _prediction_quality(self, after=False) -> int:
        '''
        Returns a measure of the prediction quality that TrueSkill rankings
        provided. A number from 0 to 1. 0 being got it all wrong, 1 being got
        it all right.
        '''

        def dictify(ordered_rankers):
            '''
            Given a list of rankers in order will return a dictionary keyed on ranker with rank based on that order.
            '''
            rank_dict = {}
            r = 1
            for rank, rankers in enumerate(ordered_rankers):
                # Get a list of tied rankers (list of 1 if no tie) so we can handle ti as a list here-on in
                if isinstance(rankers, (list, tuple)):
                    tied_rankers = rankers
                else:
                    tied_rankers = [rankers]

                for ranker in tied_rankers:
                    rank_dict[ranker] = rank

            return rank_dict

        actual_rank = dictify(self.actual_ranking()[0])
        predicted_rank = dictify(self.predicted_ranking_after()[0]) if after else dictify(self.predicted_ranking()[0])
        total = 0
        right = 0
        for relationship in self.relationships:
            ranker1 = relationship[0]
            ranker2 = relationship[1]
            real_result = actual_rank[ranker1] < actual_rank[ranker2]
            pred_result = predicted_rank[ranker1] < predicted_rank[ranker2]
            total += 1
            if pred_result == real_result:
                right += 1

        return right / total if total > 0 else 0

    @property
    def prediction_quality(self) -> int:
        return self._prediction_quality()

    @property
    def prediction_quality_after(self) -> int:
        return self._prediction_quality(True)

    @property
    def inspector(self) -> str:
        '''
        Returns a safe HTML string reporting the structure of a session for prurposes
        of rapid and easy debugging of any database integrity issues. Many other
        properties and methods make assumptions about session integrity and if these fail
        they bomb. The aim here is that this is robust and just reports the database
        objects related and their basic properties with PKs in a nice HTML div that
        can be popped onto any page or on a spearate "inspector" page if desired.
        '''
        Team = apps.get_model(APP, "Team")
        Rank = apps.get_model(APP, "Rank")

        # A TootlTip Format string
        ttf = "<div class='tooltip'>{}<span class='tooltiptext'>{}</span></div>"

        html = "<div id='session_inspector' class='inspector'>"
        html += "<table>"
        html += f"<tr><th>pk:</th><td>{self.pk}</td></tr>"
        html += f"<tr><th>date_time:</th><td>{self.date_time}</td></tr>"
        html += f"<tr><th>league:</th><td>{self.league.pk}: {self.league.name}</td></tr>"
        html += f"<tr><th>location:</th><td>{self.location.pk}: {self.location.name}</td></tr>"
        html += f"<tr><th>game:</th><td>{self.game.pk}: {self.game.name}</td></tr>"
        html += f"<tr><th>team_play:</th><td>{self.team_play}</td></tr>"

        pid = ttf.format("pid", "Performance ID - the primary key of a Performance object")
        rid = ttf.format("rid", "Rank ID - the primary key of a Rank object")
        tid = ttf.format("tid", "Ream ID - the primary key of a Team object")

        html += "<tr><th>{}</th><td><table>".format(ttf.format("Integrity:", "Every player in the game must have an associated performance, rank and if relevant, team object"))

        for performance in self.performances.all():
            html += "<tr>"
            html += f"<th>player:</th><td>{performance.player.pk}</td><td>{performance.player.full_name}</td>"
            html += f"<th>{pid}:</th><td>{performance.pk}</td>"

            rank = None
            team = None
            if self.team_play:
                ranks = Rank.objects.filter(session=self)
                for r in ranks:
                    if not r.team is None:  # Play it safe in case of database integrity issue
                        try:
                            t = Team.objects.get(pk=r.team.pk)
                        except Team.DoesNotExist:
                            t = None

                        players = t.players.all() if not t is None else []

                        if performance.player in players:
                            rank = r.pk
                            team = t.pk
            else:
                try:
                    rank = Rank.objects.get(session=self, player=performance.player).pk
                    html += f"<th>{rid}:</th><td>{rank}</td>"
                except Rank.DoesNotExist:
                    rank = None
                    html += f"<th>{rid}:</th><td>{rank}</td>"
                except Rank.MultipleObjectsReturned:
                    ranks = Rank.objects.filter(session=self, player=performance.player)
                    html += f"<th>{rid}:</th><td>{[rank.pk for rank in ranks]}</td>"

            html += f"<th>{tid}:</th><td>{team}</td>" if self.team_play else ""
            html += "</tr>"
        html += "</table></td></tr>"

        html += "<tr><th>ranks:</th><td><ol start=0>"
        for rank in self.ranks.all():
            html += "<li><table>"
            html += f"<tr><th>pk:</th><td>{rank.pk}</td></tr>"
            html += f"<tr><th>rank:</th><td>{rank.rank}</td></tr>"
            html += f"<tr><th>player:</th><td>{rank.player.pk if rank.player else None}</td><td>{rank.player.full_name if rank.player else None}</td></tr>"
            html += f"<tr><th>team:</th><td>{rank.team.pk if rank.team else None}</td><td>{rank.team.name if rank.team else ''}</td></tr>"
            if (rank.team):
                for player in rank.team.players.all():
                    html += f"<tr><th></th><td>{player.pk}</td><td>{player.full_name}</td></tr>"
            html += "</table></li>"
        html += "</ol></td></tr>"

        html += "<tr><th>performances:</th><td><ol start=0>"
        for performance in self.performances.all():
            html += "<li><table>"
            html += f"<tr><th>pk:</th><td>{performance.pk}</td></tr>"
            html += f"<tr><th>player:</th><td>{performance.player.pk}</td><td>{performance.player.full_name}</td></tr>"
            html += f"<tr><th>weight:</th><td>{performance.partial_play_weighting}</td></tr>"
            html += f"<tr><th>play_number:</th><td>{performance.play_number}</td>"
            html += f"<th>victory_count:</th><td>{performance.victory_count}</td></tr>"
            html += f"<tr><th>mu_before:</th><td>{performance.trueskill_mu_before}</td>"
            html += f"<th>mu_after:</th><td>{performance.trueskill_mu_after}</td></tr>"
            html += f"<tr><th>sigma_before:</th><td>{performance.trueskill_sigma_before}</td>"
            html += f"<th>sigma_after:</th><td>{performance.trueskill_sigma_after}</td></tr>"
            html += f"<tr><th>eta_before:</th><td>{performance.trueskill_eta_before}</td>"
            html += f"<th>eta_after:</th><td>{performance.trueskill_eta_after}</td></tr>"
            html += "</table></li>"
        html += "</ol></td></tr>"
        html += "</table>"
        html += "</div>"

        return html

    def leaderboard(self, leagues=[], asat=None, names="nick", style=LB_PLAYER_LIST_STYLE.rich, data=None):
        '''
        Returns the leaderboard for this session's game as at a given time, in the form of
        LB_STRUCTURE.player_list

        Primarily to support self.leaderboard_before() and self.leaderboard_after()

        This cannot be easily session_wrapped becasue of the as_at argument that defers to
        Game.leaderboard which has no session for context.

        :param leagues:      Game.leaderboards argument passed through
        :param asat:         Game.leaderboard argument passed through
        :param names:        Game.leaderboard argument passed through
        :param style:        Game.leaderboard argument passed through
        :param data:         Game.leaderboard argument passed through
        '''
        if not asat:
            asat = self.date_time

        return self.game.leaderboard(leagues, asat, names, style, data)

    @property_method
    def leaderboard_before(self, style=LB_PLAYER_LIST_STYLE.rich, wrap=False) -> tuple:
        '''
        Returns the leaderboard as it was immediately before this session, in the form of
        LB_STRUCTURE.player_list

        :param style: an LB_PLAYER_LIST_STYLE to use.
        :param wrap:  if true puts the previous sessions session wrapper around the leaderboard.
        '''
        session = self.previous_session()
        player_list = self.leaderboard(asat=self.date_time - MIN_TIME_DELTA, style=style)

        if player_list:
            if wrap:
                leaderboard = session.wrapped_leaderboard(player_list)
            else:
                leaderboard = player_list
        else:
            leaderboard = None

        return leaderboard

    @property_method
    def leaderboard_after(self, style=LB_PLAYER_LIST_STYLE.rich, wrap=False) -> tuple:
        '''
        Returns the leaderboard as it was immediately after this session, in the form of
        LB_STRUCTURE.player_list

        :param style: an LB_PLAYER_LIST_STYLE to use.
        :param wrap:  if true puts this sessions session wrapper around the leaderboard.
        '''
        session = self
        player_list = self.leaderboard(asat=self.date_time, style=style)

        if wrap:
            leaderboard = session.wrapped_leaderboard(player_list)
        else:
            leaderboard = player_list

        return leaderboard

    @property_method
    def wrapped_leaderboard(self, leaderboard=None, leagues=[], asat=None, names="nick", style=LB_PLAYER_LIST_STYLE.simple, data=None) -> tuple:
        '''
        Given a leaderboard with structure
            LB_STRUCTURE.player_list
        will wrap it in this session's data to return a board with structure
            LB_STRUCTURE.session_wrapped_player_list

        A session wrapper contains:
            # Session metadata
            0 session.pk,
            1 session.date_time (in local time),
            2 session.game.play_counts()['total'],
            3 session.game.play_counts()['sessions'],

            # Player details
            4 session.players() (as a list of pks),

            # Some HTML analytic headers
            5 session.leaderboard_header(),
            6 session.leaderboard_analysis(),
            7 session.leaderboard_analysis_after(),

            # The leaderboard(s)
            8 game.leaderboard(asat)  # leaderboard after this game sessions

            Leaderboards.leaderboards.enums.LB_STRUCTURE provides pointers into this structure.
                They must reflect what is produced here.

        :param leaderboard:
        :param leagues:      self.leaderboard argument passed through
        :param asat:         self.leaderboard argument passed through
        :param names:        self.leaderboard argument passed through
        :param style:        self.leaderboard argument passed through
        :param data:         self.leaderboard argument passed through
        '''
        if leaderboard is None:
            leaderboard = self.leaderboard(leagues, asat, names, style, data)

        if asat is None:
            asat = self.date_time

        # Get the play counts as at asat
        counts = self.game.play_counts(asat=asat)

        # Two standard use cases exist:
        #     prep for render:    name_style is "flexi". The client can adjust links, name styles and performance displays on the fly without a server round trip
        #     prep for storage    name_style is "template". We don't want to include any of the name variants in data as the session wrapped leaderboard containing
        #                         these rankers may be saved in JSON format either with change logs or in the laderboard cache and we want player name privace
        #                         constrained to render time.
        #     We conclude which to use by  the style. `data` style is for storage and `rich` is for render
        name_style = "template" if style == LB_PLAYER_LIST_STYLE.data else "flexi"

        # These HTML headers are al; 2-tuples in the form (html, data)
        # where the data provides rendering data, in particular, player
        # link, name and performance data, so the rendered can dynamically
        # render the leaderboard headers in response to choces made by the
        # end user while viewing, The 'leaderboard' - an ordered list of
        # players) in the rich player list style, is a tuple of similar data
        # for each player on the leaderboard. The HTML headers include players
        # and so provide their own data for that.
        #
        # In practice all three of the HTML headers currently only list the
        # players in this session so their data elements actually replicate
        # each other. THe flexibility is retained in case of other HTML
        # headers that may be impelmented in future that might include other
        # players (hard to imagine any but we maintain a flexible approach here
        # in case).
        html_headers = (
                self.leaderboard_header(name_style=name_style),
                self.leaderboard_analysis(name_style=name_style),
                self.leaderboard_analysis_after(name_style=name_style),
            )

        # TODO: We want to add for each player in the session name expansions
        #       this is the list provided by
        # Build the snapshot tuple
        return (self.pk,                                # 0
                localize(localtime(self.date_time)),    # 1
                counts['total'],                        # 2
                counts['sessions'],                     # 3
                [p.pk for p in self.players],           # 4
                *html_headers,                          # 5,6,7 unpacked into this session wrapping tuple
                leaderboard)                            # 8

    @property_method
    def leaderboard_snapshot(self, style=LB_PLAYER_LIST_STYLE.simple) -> tuple:
        '''
        Prepares a leaderboard snapshot for passing to a view for rendering.

        The structure is decribed as LB_STRUCTURE.session_wrapped_player_list

        That is: the leaderboard in this game as it stood just after this session was played.

        Such snapshots are often delivered to the client inside a game wrapper as well.
        '''
        if settings.DEBUG:
            log.debug(f"\t\t\tBuilding leaderboard snapshot for {self.pk} with style '{style.name}'")

        leaderboard = self.leaderboard_after(style=style)  # returns LB_STRUCTURE.player_list
        snapshot = self.wrapped_leaderboard(leaderboard)

        return snapshot

    @property_method
    def leaderboard_impact(self, style=LB_PLAYER_LIST_STYLE.rich) -> tuple:
        '''
        Returns a game_wrapped_session_wrapped pair of player_lists representing the leaderboard
        for this session game as it stood before the session was played, and after it was played.

        :param style: The LB_PLAYER_LIST_STYLE to use in the returned boards (player lists).
        '''
        before = self.leaderboard_before(style=style, wrap=True)  # session wrapped
        after = self.leaderboard_after(style=style, wrap=True)  # session wrapped

        # Append the latest only for diagnostics if it's expected to be same and isn't! So we have the two to compare diagnostically!
        # if this is the latest sesion, then the latest leaderbouard shoudl be the same as this session's snapshot!
        if self.is_latest:
            player_list = self.game.leaderboard(style=style)  # returns LB_STRUCTURE.player_list

            # Session wrap it for consistency of structure (even though teh session wrapper is faux, meaning
            # the latest board for this game is not from this session if it's not the same as this session after board)
            latest = self.wrapped_leaderboard(player_list)

            # The first element in the wrapped leaderbaord is the session ID
            include_latest = not after[0] == latest[0]

            if include_latest:
                raise ValidationError("A surprising internal error. Likely a coding bug. A diagnostic board was attached to the impact summary.")
        else:
            include_latest = False

        # Build the tuple of session wrapped boards
        sw_boards = [after]
        if before: sw_boards.append(before)
        if include_latest: sw_boards.append(latest)

        return self.game.wrapped_leaderboard(sw_boards, snap=True, has_baseline=include_latest)

    @property
    def player_ranking_impact(self) -> dict:
        '''
        Returns a dict keyed on player (whose ratings were affected by by this rebuild) whose value is their rank change on the leaderboard.
        '''
        Player = apps.get_model(APP, "Player")

        before = self.leaderboard_before(style=LB_PLAYER_LIST_STYLE.data, wrap=False)  # NOT session wrapped
        after = self.leaderboard_after(style=LB_PLAYER_LIST_STYLE.data, wrap=False)  # NOT session wrapped

        deltas = {}
        old = player_rankings(before, structure=LB_STRUCTURE.player_list) if before else None
        new = player_rankings(after, structure=LB_STRUCTURE.player_list)

        for p in new:
            _old = old.get(p, len(new)) if old else len(new)
            if not new[p] == _old:
                delta = new[p] - _old
                P = safe_get(Player, p)
                deltas[P] = delta

        return deltas

    def _html_rankers_ol(self, ordered_ranks_or_rankers, expected_performance, name_style, ol_style="margin-left: 8ch;"):
        '''
        Internal OL factory for list of rankers on a session.

        Two standard use cases exist:
            prep for render:    name_style is "flexi". The client can adjust links, name styles and performance displays on the fly without a server round trip
            prep for storage    name_style is "template". We don't want to include any of the name variants in data as the session wrapped leaderboard containing
                                these rankers may be saved in JSON format either with change logs or in the laderboard cache and we want player name privace
                                constrained to render time.

        :param ordered_ranks_or_rankers: An ordered list of Player/Team objects (or lists of them for ties)
                                         or Ranks objects (or lists of them for ties).
        :param expected_performance:     Name of Rank property that supplies a Predicted Performance summary as a (mu, sigma) tuple, or a (mu, sigma) tuple
        :param name_style:               The style in which to render names
        :param ol_style:                 A style to apply to the OL if any
        '''
        Player = apps.get_model(APP, "Player")
        Team = apps.get_model(APP, "Team")
        Rank = apps.get_model(APP, "Rank")
        Game = apps.get_model(APP, "Game")

        if settings.DEBUG:
            log.debug(f"\tBuilding rankers list: {name_style=} {'for render' if name_style=='flexi' else 'for storage' if name_style=='template' else ''}")

        def expected_performance_val(i, co_ranker, expected_performance):
            # TODO: Confirm that if the rank is for team it returns the team's expected performance and
            #       if the expected_performances are supplied as a tuple or list that if for a team that
            #       they reflect the team expected performance.
            if isinstance(co_ranker, Rank) and hasattr(co_ranker, expected_performance):
                return getattr(co_ranker, expected_performance)[0] # (Extract mu from a (mu, sigma) tuple
            elif isinstance(expected_performance, (tuple, list)) and i < len(expected_performance) and i >= 0:
                return expected_performance[i]
            else:
                return None

        scoring = Game.ScoringOptions(self.game.scoring).name

        # data captures a list of options for template substituton.
        # A list of (PK, BGGname, anno, peranno) where anno and peranno are
        # a basic annotation and a performance inclusive annotation
        # respectively.
        data = [] # (PK, BGGname, anno, peranno) elements

        if ol_style:
            detail = f'<OL style="{ol_style}">'
        else:
            detail = '<OL>'

        # Build a list of rankers (or tied ranker lists) - We can receive ranks or rankers so extract the rankers
        # We also want to capture scores and any expected_performance if available, which are only available if
        # Ranks are passed in, as they are properties of Rank.
        rankers_scores_perfs = []
        for i, R_or_r in enumerate(ordered_ranks_or_rankers):
            if isinstance(R_or_r, (list, tuple)):
                # R_or_r is a list of ranks, players or teams who tied (co-rankers)
                # Each one is a rank with score or not
                rankers_scores_perfs.append([(co_ranker.ranker,
                                              co_ranker.score,
                                              expected_performance_val(i, co_ranker, expected_performance),
                                              ) if isinstance(co_ranker, Rank) else (
                                                  co_ranker,
                                                  None,
                                                  expected_performance_val(i, co_ranker, expected_performance)) for co_ranker in R_or_r])
            else:
                # R_or_r is a single rank, player or team who tied (co-rankers)
                # For consistency with tied ranks, create a one entry list (tied with self ;-).
                # For rendering a string at this rank, that is all we need
                rankers_scores_perfs.append([(R_or_r.ranker,
                                              R_or_r.score,
                                              expected_performance_val(i, R_or_r, expected_performance),
                                              ) if isinstance(R_or_r, Rank) else (
                                                  R_or_r,
                                                  None,
                                                  expected_performance_val(i, R_or_r, expected_performance))])

        rankers = OrderedDict()
        for row, co_rankers in enumerate(rankers_scores_perfs):
            co_rankers_html = []
            for (ranker, score, eperf) in co_rankers:
                # We support two levels of ranker annotation in these lists
                #
                # Basic - or "anno"
                # Basic plus an expected performance indicator - or "peranno"
                delim = ", "

                # Don't report invalid scores if they exist.
                # If the ranker is a team the game bmust support team scoring
                # If the ranker is a player it must supprot individual scoring
                # This should never happen really.
                if not ((isinstance(ranker, Team) and "TEAM" in scoring) or (isinstance(ranker, Player) and "INDIVIDUAL" in scoring)):
                    score = None

                tt = ("<div class='tooltip'><span class='tooltiptext' style='width: 600%;'>", "</span>", "</div>")
                if score and eperf:
                    anno = f" ({tt[0]}Score{tt[1]}{score}{tt[2]})"
                    peranno = f" ({tt[0]}Score{delim}Expected performance (teeth){tt[1]}{score}{delim}{eperf:.1f}{tt[2]})"
                elif score:
                    anno = peranno = f" ({tt[0]}Score{tt[1]}{score}{tt[2]})"
                elif eperf:
                    anno = ""
                    peranno = f" ({tt[0]}Expected performance (teeth){tt[1]}{eperf:.1f}{tt[2]})"
                else:
                    anno = peranno = None

                # We add a template {anno} to end of each player so a template can replace it with anno or peranno
                # based on the selected options (leaderboard_options.show_performances)
                PK = ranker.pk
                if isinstance(ranker, Team):
                    # TODO: confirm that team rendering does not leak and private member data
                    # Teams we can render with the default verbose format (that lists the members as well as the team name if available)
                    ranker_str = field_render(ranker, flt.template, osf.verbose) + f"{{anno.{row}}}"
                    BGG = None # No BGGname for a team
                    data.append((PK, BGG, anno, peranno)) # TODO check the peranno is in fact the expected team performance! it probably isn't.

                elif isinstance(ranker, Player):
                    # Render the field first as a template which has:
                    # {Player.PK} in place of the player's name, and a
                    # {link.klass.model.pk}  .. {link_end} wrapper around anything that needs a link
                    ranker_str = field_render(ranker , flt.template, osf.template) + f"{{anno.{row}}}"

                    # Add a (PK, BGGid) tuple to the data list that provides a PK to BGGid map for a the leaderboard template view
                    BGG = None if (ranker.BGGname is None or len(ranker.BGGname) == 0 or ranker.BGGname.isspace()) else ranker.BGGname
                    data.append((PK, BGG, anno, peranno))

                co_rankers_html.append(ranker_str)

            conjuntion = "<BR>" if len(co_rankers_html) > 3 else ", "
            rankers[row] = conjuntion.join(co_rankers_html)

        for row, co_rankers in rankers.items():
            detail += f'<LI value={row+1}>{co_rankers}</LI>'

        detail += '</OL>'

        return (detail, data)

    def leaderboard_header(self, name_style="flexi"):
        '''
        Returns a HTML header that can be used on leaderboards.

        It includes the ranked list of performers in that session.

        This comes in two parts, a template, and ancillary data.

        The template is HTML with placeholders for the ancillary data.

        This permits a leaderboard view to render the template altering how
        the template is rendered.  The ancillary data is for now just the
        pk and BGG name of the rankers in that session which allows the
        template to link names to this site or to BGG as it desires.

        :param name_style: what style to render names with
        '''
        (ordered_ranks, probability) = self.actual_ranking(as_ranks=True)

        detail = f"<b>Results after: <a href='{link_target_url(self)}' class='{FIELD_LINK_CLASS}'>{time_str(self.date_time)}</a></b><br><br>"

        (ol, data) = self._html_rankers_ol(ordered_ranks, "performance", name_style)

        detail += ol

        detail += f"This result was deemed {probability:0.1%} likely."

        return (mark_safe(detail), data)

    def leaderboard_analysis(self, name_style="flexi"):
        '''
        Returns a HTML header that can be used on leaderboards.

        It includes an analysis of the session.

        This comes in two parts, a template, and ancillary data.

        The template is HTML with placeholders for the ancillary data.

        This permits a leaderboard view to render the template altering how
        the template is rendered.  The ancillary data is for now just the
        pk and BGG name of the ranker in that session which allows the
        template to link names to this site or to BGG as it desires.

        Format is as follows:

        1) An ordered list of players as the prediction
        2) A confidence in the prediction (a measure of probability)
        3) A quality measure of that prediction

        :param name_style: Must be supplied
        '''
        (ordered_rankers, confidence, expected_performances) = self.predicted_ranking(with_performances=True)
        quality = self.prediction_quality

        tip_sure = "<span class='tooltiptext' style='width: 500%;'>Given the expected performance of players, the probability that this predicted ranking would happen.</span>"
        tip_accu = "<span class='tooltiptext' style='width: 300%;'>Compared with the actual result, what percentage of relationships panned out as expected performances predicted.</span>"
        detail = f"Predicted ranking <b>before</b> this session,<br><div class='tooltip'>{confidence:.0%} sure{tip_sure}</div>, <div class='tooltip'>{quality:.0%} accurate{tip_accu}</div>: <br><br>"
        (ol, data) = self._html_rankers_ol(ordered_rankers, expected_performances, name_style)

        detail += ol

        return (mark_safe(detail), data)

    def leaderboard_analysis_after(self, name_style="flexi"):
        '''
        Returns a HTML header that can be used on leaderboards.

        It includes an analysis of the session updates.

        This comes in two parts, a template, and ancillary data.

        The template is HTML with placeholders for the ancillary data.

        This permits a leaderboard view to render the template altering how
        the template is rendered.  The ancillary data is for now just the
        pk and BGG name of the ranker in that session which allows the
        template to link names to this site or to BGG as it desires.

        Format is as follows:

        1) An ordered list of players as the prediction
        2) A confidence in the prediction (some measure of probability)
        3) A quality measure of that prediction

        :param name_style: Must be supplied
        '''
        (ordered_rankers, confidence, expected_performances) = self.predicted_ranking_after(with_performances=True)
        quality = self.prediction_quality_after

        tip_sure = "<span class='tooltiptext' style='width: 500%;'>Given the expected performance of players, the probability that this predicted ranking would happen.</span>"
        tip_accu = "<span class='tooltiptext' style='width: 300%;'>Compared with the actual result, what percentage of relationships panned out as expected performances predicted.</span>"
        detail = f"Predicted ranking <b>after</b> this session,<br><div class='tooltip'>{confidence:.0%} sure{tip_sure}</div>, <div class='tooltip'>{quality:.0%} accurate{tip_accu}</div>: <br><br>"
        (ol, data) = self._html_rankers_ol(ordered_rankers, expected_performances, name_style)
        detail += ol

        return (mark_safe(detail), data)

    def previous_sessions(self, player=None):
        '''
        Returns all the previous sessions that the nominate player played this game in.

        Always includes the current session as the first item (previous_sessions[0]).

        :param player: A Player object. Optional, all previous this game was played in if not provided.
        '''
        # TODO: Test thoroughly. Tricky Query.
        time_limit = self.date_time

        # Get the list of previous sessions including the current session! So the list must be at least length 1 (the current session).
        # The list is sorted in descending date_time order, so that the first entry is the current sessions.
        sfilter = Q(date_time__lte=time_limit) & Q(game=self.game)
        if player:
            sfilter = sfilter & Q(performances__player=player)

        prev_sessions = Session.objects.filter(sfilter).distinct().order_by('-date_time')

        return prev_sessions

    def previous_session(self, player=None):
        '''
        Returns the previous session that the nominate player played this game in.
        Or None if no such session exists.

        :param player: A Player object. Optional, returns the last session this game was played if not provided.
        '''
        prev_sessions = self.previous_sessions(player)

        if len(prev_sessions) < 2:
            assert len(prev_sessions) == 1, f"Database error: Current session not in previous sessions list, session={self.pk}, player={player.pk}, {len(prev_sessions)=}."
            assert prev_sessions[0] == self, f"Database error: Current session not in previous sessions list, session={self.pk}, player={player.pk}, {prev_sessions=}."
            prev_session = None
        else:
            prev_session = prev_sessions[1]

            if not prev_sessions[0].id == self.id: breakpoint()

            if not prev_session.date_time < self.date_time:
                breakpoint()

            assert prev_sessions[0].id == self.id, f"Query error: current session is not at start of previous sessions list for session={self.pk}, first previous session={prev_sessions[0].id}, player={player.pk}"
            assert prev_session.date_time < self.date_time, f"Database error: Two sessions with identical time, session={self.pk}, previous session={prev_session.pk}, player={player.pk}"

        return prev_session

    def following_sessions(self, player=None):
        '''
        Returns all the following sessions that the nominate player played (will play?) this game in.

        Always includes the current session as the first item (previous_sessions[0]).

        :param player: A Player object. Optional, all following sessions this game was played in if not provided.
        '''
        # TODO: Test thoroughly. Tricky Query.
        time_limit = self.date_time

        # Get the list of previous sessions including the current session! So the list must be at least length 1 (the current session).
        # The list is sorted in descending date_time order, so that the first entry is the current sessions.
        sfilter = Q(date_time__gte=time_limit) & Q(game=self.game)
        if player:
            sfilter = sfilter & (Q(ranks__player=player) | Q(ranks__team__players=player))

        foll_sessions = Session.objects.filter(sfilter).order_by('date_time')

        return foll_sessions

    def following_session(self, player=None):
        '''
        Returns the following session that the nominate player played this game in.
        Or None if no such session exists.

        :param player: A Player object. Optional, returns the last session this game was played if not provided.
        '''
        foll_sessions = self.following_sessions(player)

        if len(foll_sessions) < 2:
            assert len(foll_sessions) == 1, f"Database error: Current session not in following sessions list, session={self.pk}, player={player.pk}, {len(foll_sessions)=}."
            assert foll_sessions[0] == self, f"Database error: Current session not in following sessions list, session={self.pk}, player={player.pk}, {foll_sessions=}."
            foll_session = None
        else:
            foll_session = foll_sessions[1]
            assert foll_sessions[0].date_time == self.date_time, f"Query error: current session not in following sessions list of following sessions for session={self.pk}, player={player.pk}"
            assert foll_session.date_time > self.date_time, f"Database error: Two sessions with identical time, session={self.pk}, previous session={foll_session.pk}, player={player.pk}"

        return foll_session

    @property
    def is_latest(self):
        '''
        True if this is the latest session in this game for all the players who played it. That is modifying it
        would (probably) not trigger any rebuilds (clear exceptions would be if a new player was added, who does
        have a future session,  or the date_time of the session is changed to be earlier than another session in
        this game with one or more of these players, or if the game is chnaged). Basically only true if it is
        currently the latest session for all htese players in this game. Can easily change if the session is
        edited, or for that matter another one is (moved after this one for example)
        '''
        Rating = apps.get_model(APP, "Rating")

        is_latest = {}
        for performance in self.performances.all():
            rating = Rating.get(performance.player, self.game)  # Creates a new rating if needed
            is_latest[performance.player] = self.date_time == rating.last_play
            assert not self.date_time > rating.last_play, "Rating last_play seems out of sync."

        return all(is_latest.values())

    @property
    def is_first(self):
        '''
        True if this is the first session in this game (so it has no previous session).
        '''
        first = Session.objects.filter(game=self.game).order_by('date_time').first()
        is_first = self == first
        return is_first

    def previous_victories(self, player):
        '''
        Returns all the previous sessions that the nominate player played this game in that this player won
        Or None if no such session exists.

        :param player: a Player object. Required, as the previous_vitory of any player is just previous_session().
        '''
        # TODO: Test thoroughly. Tricky Query.
        time_limit = self.date_time

        # Get the list of previous sessions including the current session! So the list must be at least length 1 (the current session).
        # The list is sorted in descening date_time order, so that the first entry is the current sessions.
        sfilter = Q(date_time__lte=time_limit) & Q(game=self.game) & Q(ranks__rank=1)
        sfilter = sfilter & (Q(ranks__player=player) | Q(ranks__team__players=player))
        prev_sessions = Session.objects.filter(sfilter).order_by('-date_time')

        return prev_sessions

    def rank(self, ranker):
        '''
        Returns the Rank object for the nominated ranker in this session

        :param ranker: Is a Player or Team object.
        '''
        Player = apps.get_model(APP, "Player")
        Team = apps.get_model(APP, "Team")

        if isinstance(ranker, Player):
            if self.team_play:
                ranks = self.ranks.filter(team__players=ranker)
            else:
                ranks = self.ranks.filter(player=ranker)
        elif isinstance(ranker, Team):
            ranks = self.ranks.filter(team=ranker)

        # 2 or more ranks for this player is a database integrity failure. Something serious got broken.
        assert len(ranks) < 2, "Database error: {} Ranks objects in database for session={}, ranker={}".format(len(ranks), self.pk, ranker.pk)

        # Could be called before rank objects for a session submission were saved, In which case nicely indicate so with None.
        return ranks[0] if len(ranks) == 1 else None

    def performance(self, player):
        '''
        Returns the Performance object for the nominated player in this session
        '''
        assert player != None, f"Coding error: Cannot fetch the performance of 'no player'. Session pk: {self.pk}"
        performances = self.performances.filter(player=player)
        assert len(performances) == 1, f"Database error: {len(performances)} Performance objects in database for session={self.pk}, player={player.pk} sql={performances.query}"
        return performances[0]

    def previous_performance(self, player):
        '''
        Returns the previous Performance object for the nominate player in the game of this session
        '''
        prev_session = self.previous_session(player)
        return None if prev_session is None else prev_session.performance(player)

    def previous_victory(self, player):
        '''
        Returns the last Performance object for the nominate player in the game of this session that was victory
        '''
        # TODO: Test thoroughly. Tricky Query.
        time_limit = self.date_time

        # Get the list of previous sessions including the current session! So the list must be at least length 1 (the current session).
        # The list is sorted in descening date_time order, so that the first entry is the current sessions.
        prev_victory = Session.objects.filter(Q(date_time__lte=time_limit) & Q(game=self.game) & Q(ranks__rank=1) & (Q(ranks__player=player) | Q(ranks__team__players=player))).order_by('-date_time')
        return None if (prev_victory is None or prev_victory.count() == 0) else prev_victory[0].performance(player)

    def clean_ranks(self):
        '''
        Ranks can be submitted any which way, all that matters is that they can order the players
        and identify ties. For consistency though in the database we can enforce clean rankings.

        Two strategies are possible, strictly sequential,or sequential with tie gaps. To illustrate
        with a 6 player game and a tie for 2nd place:

        sequential:  1, 2, 2, 3, 4, 5
        tie gapped:  1, 2, 2, 4, 5, 6

        This cleaner will create tie gapped ranks.
        '''
        if settings.DEBUG:
            # Grab a pre snapshot
            rank_debug_pre = {}
            for rank in self.ranks.all():
                rkey = rank.team.pk if self.team_play else rank.player.pk
                rank_debug_pre[f"{'Team' if self.team_play else f'Player'} {rkey}"] = rank.rank

            log.debug(f"\tRanks Before: {sorted(rank_debug_pre.items(), key=lambda x: x[1])}")

        # First collect all the supplied ranks
        rank_values = []
        ranks_by_pk = {}
        for rank in self.ranks.all():
            rank_values.append(rank.rank)
            ranks_by_pk[rank.pk] = rank.rank
        # Then sort them by rank
        rank_values.sort()

        if settings.DEBUG:
            log.debug(f"\tRank values: {rank_values}")
            log.debug(f"\tRanks by PK: {ranks_by_pk}")

        # Build a map of submited ranks to saving ranks
        rank_map = OrderedDict()

        if settings.DEBUG:
            log.debug(f"\tBuilding rank map")
        expected = 1
        for rank in rank_values:
            # if it's a new rank process it
            if not rank in rank_map:
                # If we have the expected value map it to itself
                if rank == expected:
                    rank_map[rank] = rank
                    expected += 1
                    if settings.DEBUG:
                        log.debug(f"\t\tRank {rank} is as expected.")

                # Else map all tied ranks to the expected value and update the expectation
                else:
                    if settings.DEBUG:
                        log.debug(f"\t\tRank {rank} is expected at {expected}.")
                    rank_map[rank] = expected
                    expected += rank_values.count(rank)
                    if settings.DEBUG:
                        log.debug(f"\t\t\tMoved {rank_values.count(rank)} {'teams' if self.team_play else f'players'} to the expected rank and the new expectation is {expected}.")

        if settings.DEBUG:
            log.debug(f"\tRanks Map: {rank_map}")

        for From, To in rank_map.items():
            if not From == To:
                pks = [k for k, v in ranks_by_pk.items() if v == From]
                rank_objs = self.ranks.filter(pk__in=pks)
                for rank_obj in rank_objs:
                    rank_obj.rank = To
                    rank_obj.save()
                    rkey = rank_obj.team.pk if self.team_play else rank_obj.player.pk
                    if settings.DEBUG:
                        log.debug(f"\tMoved {'Team' if self.team_play else f'Player'} {rkey} from rank {rank} to {rank_obj.rank}.")

        if settings.DEBUG:
            # Grab a pre snapshot
            rank_debug_post = {}
            for rank_obj in self.ranks.all():
                rkey = rank_obj.team.pk if self.team_play else rank_obj.player.pk
                rank_debug_post[f"{'Team' if self.team_play else f'Player'} {rkey}"] = rank_obj.rank

            log.debug(f"\tRanks Before : {sorted(rank_debug_pre.items(), key=lambda x: x[1])}")
            log.debug(f"\tRanks Cleaned: {sorted(rank_debug_post.items(), key=lambda x: x[1])}")

    def build_trueskill_data(self, save=False):
        '''Builds a the data structures needed by trueskill.rate

        if save is True, will initialise Performance objects for each player too.

         A RatingGroup is list of dictionaries, one dictionary for each team
            keyed on the team name or ID containing a trueskill Rating object for that team
         In single player mode we simply supply teams of 1, so each dictionary has only one member
             and can be keyed on player name or ID.
         A trueskill Rating is just a trueskill mu and sigma pair (actually a Gaussian object with a mu and sigma).

        Weights is a dictionary, keyed on a player identifier with a weight as a value
            The weights are 0 to 1, 0 meaning no play and 1 meaning full time play.
            The player identifier is is a tuple which has two values (RatingsGroup index, Key into that RatingsGroup dictionary)

        Ranking list is a list of ranks (1, 2, 3 for first, second, third etc) that maps item
            for item into RatingGroup. Ties are indicated by repeating a given rank.
         '''
        RGs = []
        Weights = {}
        Ranking = []

        if self.team_play:
            for rank, team in self.ranked_teams.items():
                RG = {}
                RGs.append(RG)
                for player in team.players.all():
                    performance = self.performance(player)
                    if self.__bypass_admin__:
                        performance.__bypass_admin__ = True
                    performance.initialise(save)
                    RG[player.pk] = trueskill.Rating(mu=performance.trueskill_mu_before, sigma=performance.trueskill_sigma_before)
                    Weights[(len(RGs) - 1, player.pk)] = performance.partial_play_weighting
                Ranking.append(int(rank.split('.')[0]))
        else:
            for rank, player in self.ranked_players.items():
                performance = self.performance(player)
                if self.__bypass_admin__:
                    performance.__bypass_admin__ = True
                performance.initialise(save)
                RGs.append({player.pk: trueskill.Rating(mu=performance.trueskill_mu_before, sigma=performance.trueskill_sigma_before)})
                Weights[(len(RGs) - 1, player.pk)] = performance.partial_play_weighting
                Ranking.append(int(rank.split('.')[0]))
        return RGs, Weights, Ranking

    def calculate_trueskill_impacts(self):
        '''
        Given the rankings associated with this session (i.e. assuming they are recorded)
        and the trueskill measures for each player before the session will, calculate (and
        record against this session) on their basis the new trueskill measures.

        Saves the impacts to the database in the form of Performance objects and returns a
        summary of impacts.

        Does not update ratings in the database.
        '''
        Player = apps.get_model(APP, "Player")
        Performance = apps.get_model(APP, "Performance")

        TSS = TrueskillSettings()
        TS = trueskill.TrueSkill(mu=TSS.mu0, sigma=TSS.sigma0, beta=self.game.trueskill_beta, tau=self.game.trueskill_tau, draw_probability=self.game.trueskill_p)

        def RecordPerformance(rating_groups):
            '''
            Given a rating_groups structure from trueskill.rate will distribute the results to the Performance objects

            The Trueskill impacts are extracted from the rating_groups recorded in Performance objects.

            Ratings are not updated here. These are used to update ratings elsewhere.
            '''
            for t in rating_groups:
                for p in t:
                    player = Player.objects.get(pk=p)

                    performances = Performance.objects.filter(session=self, player=player)
                    assert len(performances) == 1, "Database error: {} Performance objects in database for session={}, player={}".format(len(performances), self.pk, player.pk)
                    performance = performances[0]

                    mu = t[p].mu
                    sigma = t[p].sigma

                    performance.trueskill_mu_after = mu
                    performance.trueskill_sigma_after = sigma
                    performance.trueskill_eta_after = mu - TSS.mu0 / TSS.sigma0 * sigma  # µ − (µ0 ÷ σ0) × σ

                    # eta_before was saved when the performance ws initialised from the previous performance.
                    # We recalculate it now as an integrity check against global TrueSkill settings change.
                    # A change in eta_before suggests one of the global values TSS.mu0 or TSS.sigma0 has changed
                    # and that is a conditon that needs handling. In theory it should force a complete rebuild
                    # of the ratings. For now, just throw an exception.
                    # TODO: Handle changes in TSS.mu0 or TSS.sigma0 cleanly. Namely:
                    #    trigger a neat warning to the registrar (person saving a session now)
                    #    inform admins by email, with suggested action (rebuild ratings from scratch or reset TSS.mu0 and TSS.sigma0
                    previous_trueskill_eta_before = performance.trueskill_eta_before
                    performance.trueskill_eta_before = performance.trueskill_mu_before - TSS.mu0 / TSS.sigma0 * performance.trueskill_sigma_before
                    assert isclose(performance.trueskill_eta_before, previous_trueskill_eta_before, abs_tol=FLOAT_TOLERANCE), "Integrity error: suspiscious change in a TrueSkill rating."

                    if self.__bypass_admin__:
                        performance.__bypass_admin__ = True

                    performance.save()
            return

        # Trueskill Library has moderate internal docs. Much better docs here:
        #    http://trueskill.org/
        # For our sanity to be clear here:
        #
        # RatingsGroup is a list each item of which is a dictionary,
        #    keyed on player ID with a rating object as its value
        #    teams are supported by this list, that is each item in RatingsGroup
        #    is a logical player or team represented by a dicitonary of players.
        #    With individual players the team simply has one item in the dictionary.
        #    Teams with more than one player have all the players in this dictionary.
        #
        # Ranking is a list of rankings. Each list item maps into a RatingsGroup list item
        #    so the 0th value in Rank maps to the 0th value in RatingsGroup
        #    and the 1st value in Rank maps to the 0th value in RatingsGroup etc.
        #    Each item in this list is a numeric (int) ranking.
        #    Ties are recorded with the same ranking value. Equal 1 for example.
        #    The value of the rankings is relevant only for sorting, that is ordering the
        #    objects in the RatingsGroup list (and supporting ties).
        #
        # Weights is a dictionary, keyed on a player identifier with a weight as a value
        #    The weights are 0 to 1, 0 meaning no play and 1 meaning full time play.
        #    The player identifier is is a tuple which has two values (RatingsGroup index, Key into that RatingsGroup dictionary)

        OldRatingGroups, Weights, Ranking = self.build_trueskill_data(save=True)
        NewRatingGroups = TS.rate(OldRatingGroups, Ranking, Weights, TSS.delta)
        RecordPerformance(NewRatingGroups)

        return self.trueskill_impacts

    # @memoized("event_detail({self.pk},{link})")
    # @memoized()
    @memoized
    def event_detail(self, link=flt.internal):
        '''
        A simple string representation of the session used in event summaries.

        We're interested in the game, and the ranked players, mainly.

        :param self:
        '''
        return f'{field_render(self.game, self.link_internal)}: {self.str_ranked_players(link)}'

    def __unicode__(self):
        return f'{time_str(self.date_time)} - {self.game}'

    def __str__(self): return self.__unicode__()

    def __verbose_str__(self):
        return f'{time_str(self.date_time)} - {self.league} - {self.location} - {self.game}'

    def __rich_str__(self, link=None):
        url_view_self = reverse('view', kwargs={'model': self._meta.model_name, 'pk': self.pk}) if link == flt.internal else None

        if self.team_play:
            victors = []
            for t in self.victors:
                if t.name is None:
                    victors += ["(" + ", ".join([field_render(p.name_nickname, link_target_url(p, link)) for p in t.players.all()]) + ")"]
                else:
                    victors += [field_render(t.name, link_target_url(t, link))]
        else:
            victors = [field_render(p.name_nickname, link_target_url(p, link)) for p in self.victors]

        try:
            V = ", ".join(victors)
            # venue = f"- {field_render(self.location, link)}"
            T = time_str(self.date_time)
            if url_view_self:
                T = f"<a href='{url_view_self}' class='field_link'>{T}</a>"

            return (f'{T} - {field_render(self.game, link)} - {self.num_competitors} {self.str_competitors} ({self.str_ranked_players()}) - {V} won')
        except:
            pass

    def __detail_str__(self, link=None):
        url_view_self = reverse('view', kwargs={'model': self._meta.model_name, 'pk': self.pk}) if link == flt.internal else None

        T = time_str(self.date_time)
        if url_view_self:
            T = f"<a href='{url_view_self}' class='field_link'>{T}</a>"

        detail = T + "<br>"
        detail += field_render(self.game, link) + "<br>"
        detail += u'<OL>'

        rankers = OrderedDict()
        for r in self.ranks.all():
            if self.team_play:
                ranker = field_render(r.team, link)
            else:
                ranker = field_render(r.player, link)

            if r.rank in rankers:
                rankers[r.rank].append(ranker)
            else:
                rankers[r.rank] = [ranker]

        for rank in rankers:
            detail += u'<LI value={}>{}</LI>'.format(rank, ", ".join(rankers[rank]))

        detail += u'</OL>'
        return detail

    @property
    def dict_from_object(self):
        '''
        Returns a dictionary that represents this object (so that it can be serialized).

        Django has an internal function
            django.forms.models.model_to_dict()
        that does similar but is far more generic returning a dict of model fields only,
        in the case of this model: game, date_time, league, location and team_play.

        In support of rich objects we need to customise this dict really to include
        related information as we have here. This dict defines a Session instance for
        example where model_to_dict() fails to.
        '''
        # Get rank related lists
        ranks = [r.pk for r in self.ranks.all().order_by("rank")]
        rankings = [r.rank for r in self.ranks.all().order_by("rank")]
        rscores = [r.score for r in self.ranks.all().order_by("rank")]

        # Get perfroamnce related lists
        performances = [p.pk for p in self.performances.all().order_by("player__pk")]
        performers = [p.player.pk for p in self.performances.all().order_by("player__pk")]
        pscores = [p.score for p in self.performances.all().order_by("player__pk")]
        weights = [p.partial_play_weighting for p in self.performances.all().order_by("player__pk")]

        # Build lists of rankers
        # rankers is a list player IDs or a list of lists of player IDs
        # Teams are represented a lists of player IDs
        if self.team_play:
            rankers = [[p.pk for p in r.team.players.all().order_by("pk")] for r in self.ranks.all().order_by("rank")]
        else:
            rankers = [r.player.pk for r in self.ranks.all().order_by("rank")]

        # Createa serializeable form of the (rich) object
        session_dict = {"model": self._meta.model.__name__,  # the model name
                        # Session atttributes
                        "id": self.pk,  # a session ID
                        "game": self.game.pk,  # a Game ID
                        "time": self.date_time_local,  # a datetime
                        "league": self.league.pk,  # a league ID
                        "location": self.location.pk,  # a location ID
                        "team_play": self.team_play,  # a booolean flag
                        # Rank atttributes
                        "ranks": ranks,  # a list of Rank IDs
                        "rankings": rankings,  # a list of rankings (postive ints)
                        "rscores": rscores,  # a list of rank scores (positive ints)
                        "rankers": rankers,  # a list player ID or lists of player IDs (teams)
                        # Performance atttributes
                        "performances": performances,  # A list of performance IDs
                        "pscores": pscores,  # A list performance scores (positive ints)
                        "performers": performers,  # A list of performers (player IDs)
                        "weights": weights}  # A list of weights (positive floats 0-1)

        # DB object values can be None.
        # For consistency with dict_from_form (below) we replace all instances of None
        # with MISSING_VALUE (which is what is used there for HTML compatibility).
        for field in session_dict:
            if session_dict[field] is None:
                session_dict[field] = MISSING_VALUE
            elif isinstance(session_dict[field], list):
                for i, val in enumerate(session_dict[field]):
                    if val is None:
                        session_dict[field][i] = MISSING_VALUE

        return session_dict

    @classmethod
    def dict_from_form(cls, form_data, pk=None):
        '''
        Returns a dictionary that represents the form data supplied.

        This centralises form parsing for this model and provides a
        dict that compares with dict_from_object() above to facilitate
        change detection on form submissions.

        For reference this is a sample submission of form_data:

            'game': ['29'],
            'date_time': ['2022-07-02 03:59:00 +10:00'],
            'initial-date_time': ['2022-07-02 03:59:00'],
            'league': ['1'],
            'location': ['9'],
            'Rank-TOTAL_FORMS': ['2'],
            'Rank-INITIAL_FORMS': ['0'],
            'Rank-MIN_NUM_FORMS': ['0'],
            'Rank-MAX_NUM_FORMS': ['1000'],
            'Performance-TOTAL_FORMS': ['2'],
            'Performance-INITIAL_FORMS': ['0'],
            'Performance-MIN_NUM_FORMS': ['0'],
            'Performance-MAX_NUM_FORMS': ['1000'],
            'num_players': ['2'],
            'Rank-0-rank': ['1'],
            'Rank-0-score': ['0'],
            'Performance-0-player': ['1'],
            'Rank-0-player': ['1'],
            'Performance-0-partial_play_weighting': ['1'],
            'Rank-1-rank': ['2'],
            'Rank-1-score': ['0'],
            'Performance-1-player': ['66'],
            'Rank-1-player': ['66'],
            'Performance-1-partial_play_weighting': ['1']

        And this is a sample for team_play (a 4 playergame  in two teams of two):

            'game': ['18'],
            'date_time': ['2022-07-02 03:59:00 +10:00'],
            'initial-date_time': ['2022-07-02 03:59:00'],
            'league': ['1'],
            'location': ['9'],
            'team_play': ['on'],
            'Rank-TOTAL_FORMS': ['2'],
            'Rank-INITIAL_FORMS': ['0'],
            'Rank-MIN_NUM_FORMS': ['0'],
            'Rank-MAX_NUM_FORMS': ['1000'],
            'Team-TOTAL_FORMS': ['2'],
            'Team-INITIAL_FORMS': ['0'],
            'Team-MIN_NUM_FORMS': ['0'],
            'Team-MAX_NUM_FORMS': ['1000'],
            'Performance-TOTAL_FORMS': ['4'],
            'Performance-INITIAL_FORMS': ['0'],
            'Performance-MIN_NUM_FORMS': ['0'],
            'Performance-MAX_NUM_FORMS': ['1000'],
            'num_teams': ['2'],
            'Rank-0-rank': ['1'],
            'Rank-0-score': ['0'],
            'Team-0-num_players': ['2'],
            'Performance-0-player': ['1'],
            'Performance-0-team_num': ['0'],
            'Performance-0-score': [''],
            'Performance-0-partial_play_weighting': ['1'],
            'Performance-1-player': ['66'],
            'Performance-1-team_num': ['0'],
            'Performance-1-score': [''],
            'Performance-1-partial_play_weighting': ['1'],
            'Rank-1-rank': ['2'],
            'Rank-1-score': ['0'],
            'Team-1-num_players': ['2'],
            'Performance-2-player': ['13'],
            'Performance-2-team_num': ['1'],
            'Performance-2-score': [''],
            'Performance-2-partial_play_weighting': ['1'],
            'Performance-3-player': ['70'],
            'Performance-3-team_num': ['1'],
            'Performance-3-score': [''],
            'Performance-3-partial_play_weighting': ['1']

        :param form_data: A Django QueryDict representing a form submission
        :param pk: Optionally a Primary Key to add to the dict
        '''

        def int_or_MISSING(data, key):
            try:
                # If key is absent or data[key] is not a valid int this
                # will raise an exception and MISSING_VALUE is returned
                return int(data[key])
            except:
                return MISSING_VALUE

        def float_or_MISSING(data, key):
            try:
                # If key is absent or data[key] is not a valid int this
                # will raise an exception and MISSING_VALUE is returned
                return float(data[key])
            except:
                return MISSING_VALUE

        # Copy the form_data (if it's a Qury dict it's immutable and we want to clean it)
        data = form_data.copy()

        # Forms do not submit the object id.
        # That's standard for Django model forms.
        # As the ID is not an editable field, when creating
        # an object it's not needed and when editing a object
        # it's not mutable and generally comunicated vie the
        # URL match
        if not 'id' in data:
            data['id'] = f"{pk if pk else MISSING_VALUE}"

        # Extract the session attributes from the form
        session = int(data.get("id"))
        game = int(data.get("game", MISSING_VALUE))
        time = make_aware(parser.parse(data.get("date_time", NEVER)))
        league = int(data.get("league", MISSING_VALUE))
        location = int(data.get("location", MISSING_VALUE))
        team_play = 'team_play' in data

        # We expect the ranks and performances to arrive in Django formsets
        # The forms in the formsets are not in any guaranteed order so we collect
        # data first and then sort it. (by rank)

        num_ranks = int(data.get('Rank-TOTAL_FORMS', 0))
        num_performances = int(data.get('Performance-TOTAL_FORMS', 0))

        # These may include -DELETE requests. For the purposes
        # of dict generation we want to ignore those.
        for r in range(num_ranks):
            if f"Rank-{r}-DELETE" in data:
                num_ranks -= 1

        for p in range(num_performances):
            if f"Performance-{p}-DELETE" in data:
                num_performances -= 1

        # We want to convert strings to ints where sensible.
        for r in range(num_ranks):
            for key in [f'Rank-{r}-id',
                        f'Rank-{r}-rank',
                        f'Rank-{r}-score',
                        f'Rank-{r}-player']:
                data[key] = int_or_MISSING(data, key)

        for p in range(num_performances):
            for key in [f'Performance-{p}-id',
                        f'Performance-{p}-score',
                        f'Performance-{p}-player',
                        f'Performance-{p}-team_num']:
                data[key] = int_or_MISSING(data, key)
            for key in [f'Performance-{p}-partial_play_weighting']:
                data[key] = float_or_MISSING(data, key)

        # For team_play we build a list of player IDs for each rank
        # In individual play each rank is just one player ID
        if team_play:
            rank_players = {}
            for p in range(num_performances):
                rank = data[f'Performance-{p}-team_num']
                player = data[f'Performance-{p}-player']
                if rank in rank_players:
                    rank_players[rank].append(player)
                else:
                    rank_players[rank] = [player]

        rank_data = sorted([(data[f'Rank-{r}-id'],  # ranks
                             data[f'Rank-{r}-rank'],  # rankings
                             data[f'Rank-{r}-score'],  # rscores
                             rank_players[r] if team_play else data[f'Rank-{r}-player']  # rankers
                            ) for r in range(num_ranks)], key=lambda e: e[1])  # Sorted by int(rank)

        performance_data = sorted([(data[f'Performance-{p}-id'],  # performance
                                    data[f'Performance-{p}-score'],  # pscores
                                    data[f'Performance-{p}-player'],  # performers
                                    data[f'Performance-{p}-partial_play_weighting']  # weights
                                    ) for p in range(num_performances)], key=lambda e: e[2])  # Sorted by int(player ID)

        return { "model": cls.__name__,  # the model name
                 # Session atttributes
                 "id": session,  # a session ID
                 "game": game,  # a Game ID
                 "time": time,  # a datetime
                 "league": league,  # a league ID
                 "location": location,  # a location ID
                 "team_play": team_play,  # a booolean flag
                  # Rank atttributes
                 "ranks": [r[0] for r in rank_data],  # a list of Rank IDs
                 "rankings": [r[1] for r in rank_data],  # a list of rankings (postive ints)
                 "rscores": [r[2] for r in rank_data],  # a list of rank scores (positive ints)
                 "rankers": [r[3] for r in rank_data],  # a list player ID or lists of player IDs (teams)
                 # Performance atttributes
                 "performances": [p[0] for p in performance_data],  # A list of performance IDs
                 "pscores": [p[1] for p in performance_data],  # A list of performers (player IDs)
                 "performers": [p[2] for p in performance_data],  # A list performance scores (positive ints)
                 "weights": [p[3] for p in performance_data]}  # A list of weights (positive floats 0-1)

    @classmethod
    def dict_to_form(cls, session_dict, form_data):
        '''
        The reverse for dict from form. Put here once more to centralise the
        Form intelligence and avoid it's being implemented elsewhere. We want to
        take a session_dict as created by dict_from_form and update the supplied form.

        This is mostly needed for pre_validation form processing which might
        need to change the form to pass validation.

        The known use case to date, is in rank/score reconciliation, in which
        A form can submit scores without ranks and based on the games scoring
        rule can generate ranks. This reconciliation is performed on session_dicts
        and if it's update rankings it wants to reflect that back in the form.

        But the reconciliation method does not want to know about the form field
        names and rules. It is dict only. So it calls this method to update the
        form

        :param session_dict: A session dict as produced by dict_form_form above
        :param form_data: Form data (which is altered to conform to session_dict
        '''
        data = form_data.copy()  # ensure we have mutable data

        team_play = session_dict['team_play']

        # Session attributes
        data['game'] = str(session_dict['game'])
        data['date_time'] = str(session_dict['time'])
        data['league'] = str(session_dict['league'])
        data['location'] = str(session_dict['location'])
        if team_play: data['team_play'] = 'on'

        # Rank attributes
        ranks = session_dict['ranks']
        rankings = session_dict['rankings']
        rscores = session_dict['rscores']
        rankers = session_dict['rankers']
        if team_play:
            data['num_teams'] = str(len(ranks))
        else:
            data['num_players'] = str(len(ranks))

        for i, r in enumerate(ranks):
            # Any of these can be missing
            if not r in (None, MISSING_VALUE): data[f'Rank-{i}-id'] = str(r)
            if not rankings[i] in (None, MISSING_VALUE): data[f'Rank-{i}-rank'] = str(rankings[i])
            if not rscores[i] in (None, MISSING_VALUE): data[f'Rank-{i}-score'] = str(rscores[i])

        # None of these can be missing
        if team_play:
            k = 0
            for i, t in enumerate(rankers):
                for j, p in enumerate(t):  # @UnusedVariable
                    data[f'Rank-{k}-player'] = str(p)
                    data[f'Rank-{k}-team_num'] = str(t)
                    k += 1
        else:
            for i, p in enumerate(rankers):
                data[f'Rank-{i}-player'] = str(p)

        data[f'Rank-TOTAL_FORMS'] = str(len(rankers))

        # Performance attributes
        performances = session_dict['performances']
        pscores = session_dict['pscores']
        performers = session_dict['performers']
        weights = session_dict['weights']

        for i, p in enumerate(performances):
            # Optional fields
            if not p in (None, MISSING_VALUE): data[f'Performance-{i}-id'] = str(p)
            if not pscores[i] in (None, MISSING_VALUE): data[f'Performance-{i}-score'] = str(pscores[i])
            # Required fields
            data[f'Performance-{i}-player'] = str(performers[i])
            data[f'Performance-{i}-partial_play_weighting'] = str(weights[i])

        data[f'Performance-TOTAL_FORMS'] = str(len(performers))

        # Pass the modified form data back
        return data

    @property_method
    def dict_delta(self, form_data=None, pk=None):
        '''
        Given form data (a QueryDict) will return a dict that merges
        dict_from_object and dict_from_form respectively into one delta
        dict that captures a summary of changes.

        If no form_data is supplied just returns dict_from_object.

        A note on IDs:
            dict_from_object always contains a session ID and database
                objects have an ID.
            dict_from_form is not guranteed to have one, in fact it's
                doesn't by default (one can be supplied), because when
                editing database objects the ID is not an editable field,
                and the model form does not include it, instead it is
                communicated vie the URL match generally not through the
                posted form data.
            As such a diff, ignores an ID change if the form data is
            missing an ID it is ignored for delta change sumaries.

        Warning:
            pk MUST be provided if a delta between an edit form and the object
            (before edit is applied) is wanted.

            If pk is not provided and form_data is supplied we assume, the
            form data to be from an Add/Create form not from an Update/Edit
            form.

            If a caller wishes to compare an edit proposal and fails to supply
            a PK, thechange summary may erroneoulsy report "crreated" when
            "changed" is more appropriate to the context. Supplying a PK is
            the way in which a claler mmakrs the form_data as a Update not an
            Add.

        :param form_data: A Django QueryDict representing a form submission
        :param pk: Optionally a Primary Key to add to the form_data_dict
        '''
        from_object = self.dict_from_object
        result = from_object.copy()

        # Find what changed and take note of it (replaceing the data bvalue with two-tuple and adding the key to the changed set)
        changes = []

        if form_data:
            # dict_from_form is a class method so it is available when no model instance is.
            from_form = self._meta.model.dict_from_form(form_data, pk)

            def check(key):
                if from_form[key] != from_object[key]:
                    # If the form fails to specifiy an Id we assume it refers to
                    # this instance and don't note the absence as a change, as this
                    # is a standard situation with model forms.
                    if not (key == 'id' and from_form[key] == MISSING_VALUE):
                        changes.append(key)
                    result[key] = (from_object[key], from_form[key])

            for key in result:
                check(key)

            # Record whether changes were seen in any fields
            # If form_data is provided and no session ID then we assume this is a comparison
            # with a Creation/Add form and the object is what was produced after the creation.
            # Edit/Update forms will provide form_data. BUT form data won't include and id
            # UNLESS it's suplied to thiosmethod via the pk arghument (dict_from_form needs one
            # and will add it to the dict if provided). Failing that even Edit/Update form data
            # won't have a 'id' field and "created" may be a misleading summary. We thus rely
            # on edit change dtectors to provide a PK.
            if changes and from_form.get('id', MISSING_VALUE) == MISSING_VALUE:
                changes.insert(0, "created")
            elif changes:
                changes.insert(0, "changed")
            else:
                changes.insert(0, "unchanged")

            # Some changes are expected to have no impact on leaderboards (for example different location
            # and league - as boards are global and leagues only used for filtering views). Other changes
            # impact the leaderboard. If any of those change we add a psudo_field "leaderboard" in changes.
            cause_leaderboard_change = ["game", "team_play", "rankers", "rankings", "performers", "weights"]
            for change in changes:
                if change in cause_leaderboard_change:
                    changes.insert(0, "leaderboard")
                    break

            # The date_time is a little trickier as it can change as long as the immediately preceding session stays
            # the same. If that changes, because this date_time change brings it before the existing one puts anotehr
            # session there (by pushing this session past another) then it will change the leaderboard_before and
            # hence the leaderboard_after. We can't know this from the delta but we can divine it from this session.

            result["changes"] = tuple(changes)

        # Called with no form data when the object is created. No change is expected.
        else:
            changes.insert(0, "created")

        return result

    def __json__(self, form_data=None, delta=None):
        '''
        A basic JSON serializer

        If form data is supplied willl build a change description by replacing each changed
        value with a 2-tuple containing the object value and recording which values changed
        (and are now 2-tuples) in the "changes" element.

        :param form_data: optionally submitted form data. A Django QueryDict.
        :param delta: a self.dict_delta if it's already been produced which is used in place of form_data and simply JSONified.
        '''
        if not delta:
            delta = self.dict_delta(form_data)

        return json.dumps(delta, cls=DjangoJSONEncoder)

    def check_integrity(self, passthru=True):
        '''
        It should be impossible for a session to go wrong if implemented securely and atomically.

        But all the same it's a complex object and database integrity failures can cause a lot of headaches,
        so this is a centralised integrity check for a given session so that a walk through sessions can find
        and identify issues easily.
        '''
        L = AssertLog(passthru)

        pfx = f"Session Integrity error (id: {self.id}):"

        # Check all the fields
        for field in ['date_time', 'league', 'location', 'game', 'team_play']:
            L.Assert(getattr(self, field, None) != None, f"{pfx} Must have {field}.")

        # Check that the play mode is supported by the game
        L.Assert(not self.team_play or self.game.team_play, f"{pfx} Recorded with team play, but Game (ID: {self.game.id}) does not support that!")
        L.Assert(self.team_play or self.game.individual_play, f"{pfx} Recorded with individual play, but Game (ID: {self.game.id}) does not support that!")

        # Check that the date_time is in the past! It makes no sense to have future sessions recorded!
        L.Assert(self.date_time <= datetime.now(tz=self.date_time_tz), f"{pfx} Session is in future! Recorded sessions must be in the past!")

        # Collect the ranks and check rank fields
        rank_values = []
        L.Assert(self.ranks.count() > 0, f"{pfx}  Has no ranks.")

        for rank in self.ranks.all():
            for field in ['session', 'rank']:
                L.Assert(getattr(rank, field, None) != None, f"{pfx}  Rank {rank.rank} (id: {rank.id}) must have {field}.")

            if self.team_play:
                L.Assert(getattr(rank, 'team', None) != None, f"{pfx}  Rank {rank.rank} (id: {rank.id}) must have team.")
            else:
                L.Assert(getattr(rank, 'player', None) != None, f"{pfx}  Rank {rank.rank} (id: {rank.id}) must have player.")

            rank_values.append(rank.rank)

        # Check that we have a victor
        L.Assert(1 in rank_values, f"{pfx}  Must have a victor (rank=1).")

        # Check that ranks are contiguous
        last_rank_val = 0
        rank_values.sort()
        rank_list = ', '.join([str(r) for r in rank_values])
        skip = 0
        # Supports both odered ranking and tie-gap ordered ranking
        # As an example of a six player game:
        # ordered:         1, 2, 2, 3, 4, 5
        # tie-gap ordered: 1, 2, 2, 4, 5, 6
        for rank in rank_values:
            L.Assert(rank == last_rank_val or rank == last_rank_val + 1 or rank == last_rank_val + 1 + skip, f"{pfx} Ranks must be consecutive. Found rank {rank} following rank {last_rank_val} in ranks {rank_list}. Expected it at {last_rank_val}, {last_rank_val+1} or {last_rank_val+1+skip}.")

            if rank == last_rank_val:
                skip += 1
            else:
                skip = 0
                last_rank_val = rank

        # Collect all the players (respecting the mode of play team/individual)
        players = set()
        if self.team_play:
            for rank in self.ranks.all():
                L.Assert(getattr(rank, 'team', None) != None, f"{pfx} Rank {rank.rank} (id:{rank.id}) has no team.")
                L.Assert(getattr(rank.team, 'players', 0), f"{pfx} Rank {rank.rank} (id:{rank.id}) has a team (id:{rank.team.id}) with no players.")

                # Check that the number of players is allowed by the game
                num_players = len(rank.team.players.all())
                L.Assert(num_players >= self.game.min_players_per_team, f"{pfx} Too few players in team (game: {self.game.id}, team: {rank.team.id}, players: {num_players}, min: {self.game.min_players_per_team}).")
                L.Assert(num_players <= self.game.max_players_per_team, f"{pfx} Too many players in team (game: {self.game.id}, team: {rank.team.id}, players: {num_players}, max: {self.game.max_players_per_team}).")

                for player in rank.team.players.all():
                    L.Assert(player, f"{pfx} Rank {rank.rank} (id: {rank.id}) has a team (id: {rank.team.id}) with an invalid player.")
                    players.add(player)
        else:
            for rank in self.ranks.all():
                L.Assert(rank.player, f"{pfx} Rank {rank.rank} (id: {rank.id}) has no player.")
                players.add(rank.player)

        # Check that the number of players is allowed by the game
        L.Assert(len(players) >= self.game.min_players, f"{pfx} Too few players (game: {self.game.id}, players: {len(players)}).")
        L.Assert(len(players) <= self.game.max_players, f"{pfx} Too many players (game: {self.game.id}, players: {len(players)}).")

        # Check that there's a performance obejct for each player and only one for each player
        for performance in self.performances.all():
            for field in ['session', 'player', 'partial_play_weighting', 'play_number', 'victory_count']:
                L.Assert(getattr(performance, field, None) != None, f"{pfx} Performance {performance.play_number} (id:{performance.id}) has no {field}.")

            L.Assert(performance.player in players, f"{pfx} Performance {performance.play_number} (id:{performance.id}) refers to a player that was not ranked: {performance.player}.")
            players.discard(performance.player)

        L.Assert(len(players) == 0, f"{pfx} Ranked players that lack a performance: {players}.")

        # Check that for each performance object the _before ratings are same as _after retings in the previous performance
        for performance in self.performances.all():
            previous = self.previous_performance(performance.player)
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

        return L.assertion_failures

    def clean(self):
        '''
        Clean is called by Django before form_valid is called for the form. It affords a place and way for us to
        Check that everything is in order before proceding to the form_valid method that should save.
        '''
        # Check that the number of players is allowed by the game
        # This is called before the ranks are saved and hence fails always!
        # The bounce also loses the player selections (and maybe more form the Performance widgets?
        # FIXME: While bouncing, see what we can do to conserve the form, state!
        # FIXME: Fix the bounce, namely work out how to test the related objects in the right order of events

        # FIXME: When we land here no ranks or performances are saved, and
        # self.players finds no related ranks.
        # Does this mean we need to do an is_valid and if so, save on the
        # ranks and performances first? But if the session is not saved they
        # too will have dramas with order.
        #
        # Maybe it's hard with clean (which is presave) to do the necessary
        # relation tests? Is this an application for an atomic save, which
        # can be performed on all the forms with minimal clean, then
        # subsequently an integrity check (or clean) on the enseble and
        # if failed, then roll back?

        # For now bypass the clean to do a test
        return

        players = self.players
        nplayers = len(players)
        if nplayers < self.game.min_players:
            raise ValidationError("Session {} has fewer players ({}) than game {} demands ({}).".format(self.pk, nplayers, self.game.pk, self.game.min_players))
        if nplayers > self.game.max_players:
            raise ValidationError("Session {} has more players ({}) than game {} permits ({}).".format(self.pk, nplayers, self.game.pk, self.game.max_players))

        # Ensure the play mode is compatible with the game being played. Form should have enforced this,
        # but we ensure it here.
        if (self.team_play and not self.game.team_play):
            raise ValidationError("Session {} specifies team play when game {} does not support it.".format(self.pk, self.game.pk))

        if (not self.team_play and not self.game.individual_play):
            raise ValidationError("Session {} specifies individual play when game {} does not support it.".format(self.pk, self.game.pk))

        # Ensure the time of the session does not clash. We need for this game and for any of these players for
        # session time to be unique so that when TruesKill ratings are calculated the session times for all
        # affected players have a clear order. Unrelated sessions that don't involve the same game or any of
        # this sessions players can have an identical time and this won't affect the ratings.

        # Now force a unique time for this game and these players
        # We just keep adding a millisecond to the time while there are coincident sessions
        while True:
            dfilter = Q(date_time=self.date_time)
            gfilter = Q(game=self.game)

            pfilter = Q()
            for player in players:
                pfilter |= Q(performances__player=player)

            sfilter = dfilter & gfilter & pfilter

            coincident_sessions = Session.objects.filter(sfilter).exclude(pk=self.pk)

            if coincident_sessions.count() > 0:
                self.date_time += MIN_TIME_DELTA
            else:
                break

        # Collect the ranks and check rank fields
        rank_values = []

        if self.ranks.count() == 0:
            raise ValidationError("Session {} has no ranks.".format(self.id))

        for rank in self.ranks.all():
            rank_values.append(rank.rank)

        # Check that we have a victor
        if not 1 in rank_values:
            raise ValidationError("Session {} has no victor (rank = 1).".format(self.id))

        # Check that ranks are contiguous
        last_rank_val = 0
        rank_values.sort()
        for rank in rank_values:
            if not (rank == last_rank_val or rank == last_rank_val + 1):
                raise ValidationError("Session {} has a gap in ranks (between {} and {})".format(self.id), last_rank_val, rank)
            last_rank_val = rank

    def clean_relations(self):
        pass
#         errors = {
#             "date_time": ["Bad DateTime"],
#             "league": ["Bad League", "No not really"],
#             NON_FIELD_ERRORS: ["One error", "Two errors"]
#             }
#         raise ValidationError(errors)

    class Meta(AdminModel.Meta):
        verbose_name = "Session"
        verbose_name_plural = "Sessions"
        get_latest_by = ["date_time"]
        ordering = ['-date_time']

