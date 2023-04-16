from . import APP, ALL_LEAGUES, FLOAT_TOLERANCE, MAX_NAME_LENGTH

from ..leaderboards.enums import LB_PLAYER_LIST_STYLE
from ..leaderboards.style import styled_player_list

from Import.models import Import

from django.db import models
from django.db.models import Q, F, Func, Count, Sum, Max, Avg, Subquery, OuterRef
from django.apps import apps
from django.conf import settings
from django.urls import reverse
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned

from django_model_admin_fields import AdminModel

from django_rich_views.decorators import property_method
from django_rich_views.model import field_render, link_target_url, NotesMixIn
from django_rich_views.util import AssertLog
from django_rich_views.queryset import get_SQL
from django_rich_views.filterset import get_filterset

from datetime import timedelta

from crequest.middleware import CrequestMiddleware

import json
import enum
import trueskill

from Site.logutils import log


class Game(AdminModel, NotesMixIn):
    TourneyRules = apps.get_model(APP, "TourneyRules", False)
    League = apps.get_model(APP, "League", False)

    '''A game that Players can be Rated on and which has a Leaderboard (global and per League). Defines Game specific Trueskill settings.'''
    BGGid = models.PositiveIntegerField('BoardGameGeek ID', null=True)  # BGG URL is https://boardgamegeek.com/boardgame/BGGid
    name = models.CharField('Name of the Game', max_length=MAX_NAME_LENGTH)

    # Which play modes the game supports. This will decide the formats the session submission form supports
    individual_play = models.BooleanField('Supports individual play', default=True)
    team_play = models.BooleanField('Supports team play', default=False)

    # Game scoring options
    # Game scores are not used by TrueSkill but can be used for ranking implicitly
    class ScoringOptions(enum.Enum):
        NO_SCORES = 0
        INDIVIDUAL_HIGH_SCORE_WINS = 1
        INDIVIDUAL_LOW_SCORE_WINS = 2
        TEAM_HIGH_SCORE_WINS = 3
        TEAM_LOW_SCORE_WINS = 4
        TEAM_AND_INDIVIDUAL_HIGH_SCORE_WINS = 5
        TEAM_AND_INDIVIDUAL_LOW_SCORE_WINS = 6

    ScoringChoices = (
        (ScoringOptions.NO_SCORES.value, 'No scores'),
        ('Individual Scores', (
            (ScoringOptions.INDIVIDUAL_HIGH_SCORE_WINS.value, 'High Score wins'),
            (ScoringOptions.INDIVIDUAL_LOW_SCORE_WINS.value, 'Low Score wins'),
        )),
        ('Team Scores', (
            (ScoringOptions.TEAM_HIGH_SCORE_WINS.value, 'High score wins'),
            (ScoringOptions.TEAM_LOW_SCORE_WINS.value, 'Low score wins'),
        )),
        ('Team and Individual Scores', (
            (ScoringOptions.TEAM_AND_INDIVIDUAL_HIGH_SCORE_WINS.value, 'High score wins'),
            (ScoringOptions.TEAM_AND_INDIVIDUAL_LOW_SCORE_WINS.value, 'Low score wins'),
        ))
    )
    scoring = models.PositiveSmallIntegerField(choices=ScoringChoices, default=ScoringOptions.NO_SCORES.value, blank=False)

    # Player counts, also inform the session logging form how to render
    min_players = models.PositiveIntegerField('Minimum number of players', default=2)
    max_players = models.PositiveIntegerField('Maximum number of players', default=4)

    min_players_per_team = models.PositiveIntegerField('Minimum number of players in a team', default=2)
    max_players_per_team = models.PositiveIntegerField('Maximum number of players in a team', default=4)

    # Can be used to offer suggested session times in forms when entering a series of results.
    # (i.e. last game time plus this games expected play time).
    expected_play_time = models.DurationField('Expected play time', default=timedelta(minutes=90))

    # Which leagues play this game? A way to keep the game selector focussed on games a given league actually plays.
    leagues = models.ManyToManyField('League', verbose_name='Leagues', blank=True, related_name='games_played', through=League.games.through)

    # Which tourneys (if any) is this game a part of?
    # Not editable: Edit the Tourney to add games, not the game to add it to a Tourney.
    tourneys = models.ManyToManyField('Tourney', verbose_name='Tourneys', editable=False, blank=True, through=TourneyRules)

    # Game specific TrueSkill settings
    # tau: 0- describes the luck element in a game.
    #      0 is a game of pure skill,
    #        there is no upper limit. It is added to sigma after each re-reating (game session recorded)
    # p  : 0-1 describes the probability of a draw. It affects how far the mu of drawn players move toward
    #        each other when a draw is recorded after each rating.
    #      0 means lots
    #      1 means not at all
    trueskill_beta = models.FloatField('TrueSkill Skill Factor (ß)', default=trueskill.BETA)
    trueskill_tau = models.FloatField('TrueSkill Dynamics Factor (τ)', default=trueskill.TAU)
    trueskill_p = models.FloatField('TrueSkill Draw Probability (p)', default=trueskill.DRAW_PROBABILITY)

    # Optionally associate with an import. We call it "source" and if it is null (none)
    # this suggests not imported but entered directly through the UI.
    source = models.ForeignKey(Import, verbose_name='Source', related_name='games', editable=False, null=True, blank=True, on_delete=models.SET_NULL)


    @property
    def global_sessions(self) -> list:
        '''
        Returns a list of sessions that played this game. Across all leagues.
        '''
        return self.session_list()

    @property
    def league_sessions(self) -> dict:
        '''
        Returns a dictionary keyed on league, with a list of sessions that played this game as the value.
        '''
        League = apps.get_model(APP, "League")
        leagues = League.objects.all()
        sl = {}
        sl[ALL_LEAGUES] = self.session_list()
        for league in leagues:
            sl[league] = self.session_list(league)
        return sl

    @property
    def global_plays(self) -> dict:
        return self.play_counts()

    @property
    def league_plays(self) -> dict:
        '''
        Returns a dictionary keyed on league, of:
        the number of plays this game has experienced, as a dictionary containing:
            total: is the sum of all the individual player counts (so a count of total play experiences)
            max: is the largest play count of any player
            average: is the average play count of all players who've played at least once
            players: is a count of players who played this game at least once
            session: is a count of the number of sessions this game has been played
        '''
        League = apps.get_model(APP, "League")
        leagues = League.objects.all()
        pc = {}
        pc[ALL_LEAGUES] = self.play_counts()
        for league in leagues:
            pc[league] = self.play_counts(league)
        return pc

    @property
    def league_leaderboards(self) -> dict:
        '''
        The leaderboards for this game as a dictionary keyed on league
        with the special ALL_LEAGUES holding the global leaderboard.

        Each leaderboard is an ordered list of (player,rating, plays) tuples
        for the league.
        '''
        League = apps.get_model(APP, "League")
        leagues = League.objects.all()
        lb = {}
        lb[ALL_LEAGUES] = self.leaderboard()
        for league in leagues:
            lb[league] = self.leaderboard(league)
        return lb

    @property
    def global_leaderboard(self) -> list:
        '''
        The leaderboard for this game considering all leagues together, as a simple property of the game.

        Returns as an ordered list of (player,rating, plays) tuples

        The leaderboard for a specific league is available through the leaderboard method.
        '''
        return self.leaderboard()

#     @property
#     def global_leaderboard2(self) -> dict:
#         '''
#         Should be same as global_leaderboards but by another means. A test of the query only
#         '''
#         leagues = list(League.objects.all().values_list('pk', flat=True))
#         return self.leaderboard(leagues)

    @property
    def link_internal(self) -> str:
        return reverse('view', kwargs={"model":self._meta.model.__name__, "pk": self.pk})

    @property
    def link_external(self) -> list:
        if self.BGGid:
            return "https://boardgamegeek.com/boardgame/{}".format(self.BGGid)
        else:
            return None

    @property
    def last_session(self):
        Session = apps.get_model(APP, "Session")
        return Session.objects.filter(game=self).order_by('-date_time').first()

    @property_method
    def last_performances(self, leagues=[], players=[], asat=None) -> object:
        '''
        Returns the last performances at this game (optionally as at a given date time) for
        a player or all players in specified leagues or all players in all leagues (if no
        leagues specified).

        Returns a Performance queryset.

        :param leagues:The league or leagues to consider when finding the last_performances. All leagues considered if none specified.
        :param player: The player or players to consider when finding the last_performances. All players considered if none specified.
        :param asat: Optionally, the last performance as at this date/time
        '''
        Performance = apps.get_model(APP, "Performance")

        pfilter = Q(session__game=self)
        if leagues:
            pfilter &= Q(player__leagues__in=leagues)
        if players:
            pfilter &= Q(player__in=players)
        if not asat is None:
            pfilter &= Q(session__date_time__lte=asat)

        # Aggregate for max date_time for a given player. That is we want one Performance
        # per player, the one with the greatest date_time (that is before asat if specified)
        #
        # This seems to work, but I cannot find solid documentation on this kind of behaviour.
        #
        # it uses a subquery that references outer query.
        pfilter &= Q(session__pk=Subquery(
                        (Performance.objects
                            .filter(Q(player=OuterRef('player')) & pfilter)
                            .values('session__pk')
                            .order_by('-session__date_time')[:1]
                        ), output_field=models.PositiveBigIntegerField()))

        Ps = Performance.objects.filter(pfilter).order_by('-trueskill_eta_after')

        if settings.DEBUG:
            log.debug(f"Fetching latest performances for game '{self.name}' as at {asat} for leagues ({leagues}) and players ({players})")
            log.debug(f"SQL: {get_SQL(Ps)}")

        return Ps

    @property_method
    def session_list(self, leagues=[], asat=None, broad=False) -> list:
        '''
        Returns a list of sessions that played this game. Useful for counting or traversing.

        Such a list is returned for the specified league or leagues or for all leagues if
        none are specified.

        Optionally can provide the list of sessions played as at a given date time.

        :param leagues: Returns sessions played considering the specified league or leagues or all leagues if none is specified.
        :param asat: Optionally returns the sessions played as at a given date
        :param broad: A basic session list is of sessions in any of the specified leagues. A broad one is a list of all sessions that contai players in any of the specified lists.
        '''
        League = apps.get_model(APP, "League")
        Session = apps.get_model(APP, "Session")

        # If a single league was provided make a list with one entry.
        if not isinstance(leagues, list):
            if leagues:
                leagues = [leagues]
            else:
                leagues = []

        # We can accept leagues as League instances or PKs but want a PK list for the queries.
        for l in range(0, len(leagues)):
            if isinstance(leagues[l], League):
                leagues[l] = leagues[l].pk
            elif not ((isinstance(leagues[l], str) and leagues[l].isdigit()) or isinstance(leagues[l], int)):
                raise ValueError(f"Unexpected league: {leagues[l]}.")

        if asat is None:
            if leagues:
                if broad:
                    return Session.objects.filter(game=self, performances__player__leagues__in=leagues).distinct()
                else:
                    return Session.objects.filter(game=self, league__in=leagues)
            else:
                return Session.objects.filter(game=self)
        else:
            if leagues:
                if broad:
                    return Session.objects.filter(game=self, performances__player__leagues__in=leagues, date_time__lte=asat).distinct()
                else:
                    return Session.objects.filter(game=self, league__in=leagues, date_time__lte=asat)
            else:
                return Session.objects.filter(game=self, date_time__lte=asat)

    @property_method
    def play_counts(self, leagues=[], asat=None, broad=False) -> dict:
        '''
        Returns the number of plays this game has experienced, as a dictionary containing:
            total:    is the sum of all the individual player counts (so a count of total play experiences)
            max:      is the largest play count of any player
            average:  is the average play count of all players who've played at least once
            players:  is a count of players who played this game at least once
            sessions: is a count of the number of sessions this game has been played

        leagues can be a single league (a pk) or a list of leagues (pks).
        We always return the playcount across all the listed leagues.

        If no leagues are specified returns the play_counts for all leagues.

        Optionally can provide the count of plays as at a given date time as well.

        :param leagues: Returns playcounts considering the specified league or leagues or all leagues if none is specified.
        :param asat: Optionally returns the play counts as at a given date
        :param broad: basic play counts are for all sessions in any of the provided leagues, broad play counts include all sessions played in by members of an of the specified leagues,
        '''
        League = apps.get_model(APP, "League")
        Session = apps.get_model(APP, "Session")
        Performance = apps.get_model(APP, "Performance")
        Rating = apps.get_model(APP, "Rating")

        # If a single league was provided make a list with one entry.
        if not isinstance(leagues, list):
            if leagues:
                leagues = [leagues]
            else:
                leagues = []

        # We can accept leagues as League instances or PKs but want a PK list for the queries.
        for l in range(0, len(leagues)):
            if isinstance(leagues[l], League):
                leagues[l] = leagues[l].pk
            elif not ((isinstance(leagues[l], str) and leagues[l].isdigit()) or isinstance(leagues[l], int)):
                raise ValueError(f"Unexpected league: {leagues[l]}.")

        if leagues:
            sfilter = Q(game=self)
            if not asat is None:
                sfilter &= Q(date_time__lte=asat)

            if broad:
                lfilter = Q()
                for league in leagues:
                    lfilter |= Q(performances__player__leagues=league)
            else:
                lfilter = Q(league__in=leagues)

            sessions = Session.objects.filter(sfilter & lfilter)
            performances = Performance.objects.filter(session__in=sessions, player__leagues__in=leagues)
        else:
            performances = self.last_performances(asat=asat)

        # The play_number of the last performance is the play count at that time.
        # play_number of a performance is the number of its play (for its player at its game)
        # performances are the last performance in this game for each player.
        pc = performances.aggregate(total=Sum('play_number'), max=Max('play_number'), average=Avg('play_number'), players=Count('play_number'))
        for key in pc:
            if pc[key] is None:
                pc[key] = 0

        pc['sessions'] = self.session_list(leagues, asat=asat, broad=broad).count()

        return pc

    @property_method
    def leaderboard(self, leagues=[], asat=None, names="nick", style=LB_PLAYER_LIST_STYLE.simple, data=None) -> tuple:
        '''
        Return a a player list.

        The structure is described by LB_STRUCTURE.player_list

        This is an ordered tuple of tuples (one per player) that represents the leaderboard for
        specified leagues, or for all leagues if None is specified. As at a given date/time if
        such is specified, else, as at now (latest or current, leaderboard) source from the current
        database or the list provided in the data argument.

        :param leagues:   Show only players in any of these leagues if specified, else in any league (a single league or a list of leagues)
        :param asat:      Show the leaderboard as it was at this time rather than now, if specified
        :param names:     Specifies how names should be rendered in the leaderboard, one of the Player.name() options.
        :param style      The style of leaderboard to return, a LB_PLAYER_LIST_STYLE value
                          LB_PLAYER_LIST_STYLE.rich is special in that it will ignore league filtering and name formatting
                          providing rich data sufficent for the recipient to do that (choose what leagues to present and
                          how to present names.
        :param data:      Optionally this can provide a leaderboard in the style LEADERBOARD.data to use as source rather
                          than the database as a source of data! This is for restyling leaderboard data that has been saved
                          in the data style.
        '''
        League = apps.get_model(APP, "League")
        Rating = apps.get_model(APP, "Rating")
        Performance = apps.get_model(APP, "Performance")

        # If a single league was provided make a list with one entry.
        if not isinstance(leagues, list):
            if leagues:
                leagues = [leagues]
            else:
                leagues = []

        if settings.DEBUG:
            log.debug(f"\t\tBuilding leaderboard for {self.name} as at {asat}.")

        # Assure itegrity of arguments
        if asat and data:
            raise ValueError(f"Game.leaderboards: Expected either asat or data and not both. I got {asat=} and {data=}.")

        if style == LB_PLAYER_LIST_STYLE.rich:
            # The rich syle contains extra info which allows the recipient to choose the name format (all name styles are included)
            if names != "nick":  # The default value
                raise ValueError(f"Game.leaderboards requested in rich style. Expected no names submitted but got: {names}")
            # The rich syle contains extra info which allows the recipient to filter on league (each player has their leagues identified in the board)
            if leagues:
                raise ValueError(f"Game.leaderboards requested in rich style. Expected no leagues submitted but got: {leagues}")

        # We can accept leagues as League instances or PKs but want a PK list for the queries.
        if leagues:
            for l in range(0, len(leagues)):
                if isinstance(leagues[l], League):
                    leagues[l] = leagues[l].pk
                elif not ((isinstance(leagues[l], str) and leagues[l].isdigit()) or isinstance(leagues[l], int)):
                    raise ValueError(f"Unexpected league: {leagues[l]}.")

            if settings.DEBUG:
                log.debug(f"\t\tValidated leagues")

        if data:
            if isinstance(data, str):
                ratings = json.loads(data)
            else:
                ratings = data
        elif asat:
            # Build leaderboard as at a given time as specified
            # Can't use the Ratings model as that stores current ratings. Instead use the Performance
            # model which records ratings after every game session and the sessions have a date/time
            # so the information can be extracted therefrom. These are returned in order -eta as well
            # so in the right order for a leaderboard (descending skill rating)
            ratings = self.last_performances(leagues=leagues, asat=asat)
        else:
            # We only want ratings from this game
            lb_filter = Q(game=self)

            # If leagues are specified we don't want to see people from other leagues
            # on this leaderboard, only players from the nominated leagues.
            if leagues:
                # TODO: FIXME: This is bold. player__leagues is a set, and leagues is a set
                # Does this yield the intersection or not? Requires a test!
                lb_filter = lb_filter & Q(player__leagues__in=leagues)

            ratings = Rating.objects.filter(lb_filter).order_by('-trueskill_eta').distinct()

        if settings.DEBUG:
            log.debug(f"\t\tBuilt ratings queryset.")

        # Now build a leaderboard from all the ratings for players (in this league) at this game.
        lb = []
        for r in ratings:
            # r may be a Rating object or a Performance object. They both have a player
            # but other metadata is specific. So we fetch them based on their accessibility
            if isinstance(r, Rating):
                player = r.player
                player_pk = player.pk
                trueskill_eta = r.trueskill_eta
                trueskill_mu = r.trueskill_mu
                trueskill_sigma = r.trueskill_sigma
                plays = r.plays
                victories = r.victories
                last_play = r.last_play_local
            elif isinstance(r, Performance):
                player = r.player
                player_pk = player.pk
                trueskill_eta = r.trueskill_eta_after
                trueskill_mu = r.trueskill_mu_after
                trueskill_sigma = r.trueskill_sigma_after
                plays = r.play_number
                victories = r.victory_count
                last_play = r.session.date_time_local
            elif isinstance(r, tuple) or isinstance(r, list):
                # Unpack the data tuple (as defined below where LB_PLAYER_LIST_STYLE.data tuples are created).
                player_pk, trueskill_eta, trueskill_mu, trueskill_sigma, plays, victories = r
                # TODO: consider the consequences of this choice of last_play in the rebuild log reporting.
                last_play = self.last_session.date_time_local
            else:
                raise ValueError(f"Progamming error in Game.leaderboard(). Unextected rating type: {type(r)}.")

            player_tuple = (player_pk, trueskill_eta, trueskill_mu, trueskill_sigma, plays, victories, last_play)
            lb.append(player_tuple)

        if settings.DEBUG:
            log.debug(f"\t\tBuilt leaderboard.")


        return None if len(lb) == 0 else styled_player_list(lb, style=style, names=names)

    @property_method
    def wrapped_leaderboard(self, leaderboard=None, snap=False, has_reference=False, has_baseline=False, leagues=[], asat=None, names="nick", style=LB_PLAYER_LIST_STYLE.simple, data=None) -> tuple:
        '''
        Returns a leaderboard (either a single board or a list of session snapshots) wrapped
        in a game propery header.

        The structure is decribed as
            LB_STRUCTURE.game_wrapped_player_list or
            LB_STRUCTURE.game_wrapped_session_wrapped_player_list

            depending on the stucturer of the supplied leaderboard which is either a board or a list o snapshots with structure:

            LB_STRUCTURE.player_list

            or a list of snapshots with structure:

            LB_STRUCTURE.session_wrapped_player_list

        A central defintion of the first tier of a the AJAX leaderboard view,
        a game header, which wraps a data delivery, the data being a
        leaderboard or list of leaderboard snapshots as defined in:

            Game.leaderboard
            Session.leaderboard_snapshot

        A game wrapper contains:
            0 game.pk,
            1 game.BGGid
            2 game.name
            3 total number of plays
            4 total number sessions played
            5 A flag, True if data is a list, false if it is only a single value.
                The value is either a player_list (game_wrapped_player_list)
                or a session_wrapped_player_list (game_wrapped_session_wrapped_player_list)
            6 A flag, True if a reference snapshot is included
            7 A flag, True if a baseline snapshot is included
            8 data (a playerlist or a session snapshot - session wrapped player list)

            Leaderboards.leaderboards.enums.LB_STRUCTURE provides pointers into this structure.
                They must reflect what is produced here.

        :param leaderboard:   a leaderboard or a single board (snap == False) or a list (snap=True) of boards
                                where a board can be session_wrapped (game_wrapped_session_wrapped_player_list)
                                or not (game_wrapped_player_list).
        :param snap:          if leaderboard is a list of snapshots, true, if leaderboard is a single leaderboard, false
        :param has_reference: a game wrapper flag to add, informs user that there's a reference snapshot included
        :param has_baseline:  a game wrapper flag to add, informs user that there's a baseline snapshot included
        :param hide_baseline: if snap is True, then if the last snapshot is a baseline that should be hidden this is true, else False
        :param leagues:       self.leaderboard argument passed through
        :param asat:          self.leaderboard argument passed through
        :param names:         self.leaderboard argument passed through
        :param style:         self.leaderboard argument passed through
        :param data:          self.leaderboard argument passed through
        '''
        if leaderboard is None:
            leaderboard = self.leaderboard(leagues, asat, names, style, data)
            snap = False

        # Permit submission of an empty tuple () to return an empty tuple.
        if leaderboard:
            counts = self.play_counts()

            # TODO: Respect styles. Importantly .data should be minimalist and reconstructable.
            # none might mean no wrapper
            # data drops the BGGid and name
            # rating and ratings map to simple
            # simple and rich are as currently implemented.
            return (self.pk, self.BGGid, self.name, counts['total'], counts['sessions'], snap, has_reference, has_baseline, leaderboard)
        else:
            return ()

    def rating(self, player, asat=None):
        '''
        Returns the Trueskill rating for this player at the specified game
        '''
        Rating = apps.get_model(APP, "Rating")

        if asat is None:
            try:
                r = Rating.objects.get(player=player, game=self)
            except ObjectDoesNotExist:
                r = Rating.create(player=player, game=self)
            except MultipleObjectsReturned:
                raise ValueError("Database error: more than one rating for {} at {}".format(player.name_nickname, self.name))
            return r
        else:
            # Use the Performance model (and time stamped associated sessions) to construct
            # a rating object as at a specific date/time
            # TODO: Implement
            pass

    def future_sessions(self, asat, players=None) -> list:
        '''
        Returns a list of sessions ordered by date_time that are in future from
        the perspective of asat for the players provided, or for everyone if None.

        This is needed for rebuilding ratings when a historic game session
        detail changes.

        Returns a list not a QuerySet because there is a tree of future influence
        that a QuerySet cannot represent. The basic tree begins with all sessions
        in the future that one of this session's players particpated in. Each of
        those sessions though can rope in new players who add branches to the tree.

        :param asat:       a datetime from which persepective the "future" is.
        :param players:    a QuerySet of Players or a list of Players.
        '''
        Session = apps.get_model(APP, "Session")

        # We want session in the future only of course
        dfilter = Q(date_time__gt=asat)

        # We want only sessions for this game
        gfilter = Q(game=self)

        # For each player we find all future sessions playing this game
        pfilter = Q(performances__player__in=players) if players else Q()

        # Combine the filters
        filters = dfilter & gfilter & pfilter

        future_sessions = Session.objects.filter(filters).distinct().order_by('date_time')

        sessions_so_far = list(future_sessions)

        # If no players were provided we already have ALL the future sessions of this game
        # If we specified some players, then we only have those that involved those players
        # We need recursively to examine that list because any player not in our list who
        # appears in a session with one these players has a whole future tree of influence
        # themselves.
        if players and future_sessions.count() > 0:
            # The new future sessions may involve new players which
            # requires that we scan them for new future sessions too
            for session in future_sessions:
                # session._get_future_sessions looks for new sessions (excluding sessions_so_far)
                # If it find any it adds them to sessions_so far and returns the complete list.
                new_sessions_so_far = session._get_future_sessions(sessions_so_far)

                # The returned list is bigger if any were added, else same size.
                # If it's bigger, sort it bu data_time and use that for the time
                # round the loop (of future_sessions)
                if len(new_sessions_so_far) > len(sessions_so_far):
                    sessions_so_far = sorted(new_sessions_so_far, key=lambda s: s.date_time)

        # After examining all future sessions, sessions_so_far is the complete list
        return sessions_so_far

    selector_field = "name"

    @classmethod
    def selector_queryset(cls, query="", session={}, all=False):
        '''
        Provides a queryset for ModelChoiceFields (select widgets) that ask for it.

        :param cls: Our class (so we can build a queryset on it to return)
        :param query: A simple string being a query that is submitted (typically typed into a django-autcomplete-light ModelSelect2 or ModelSelect2Multiple widget)
        :param session: The request session (if there's a filter recorded there we honor it)
        :param all: Requests to ignore any default league filtering
        '''
        qs = cls.objects.all()

        if not all:
            league = session.get('filter', {}).get('league', None)
            if league:
                qs = qs.filter(leagues=league)

        if query:
            # TODO: Should really respect s['filter_priorities'] as the list view does.
            qs = qs.filter(**{f'{cls.selector_field}__icontains': query})

        qs = qs.annotate(play_count=Count('sessions')).order_by("-play_count")

        return qs

    intrinsic_relations = None

    def request_sessions(self):
        '''
        We include a session count in string representations, but want it to reflect any filters
        in place for the current request, notably a league filter!
        '''
        request = CrequestMiddleware.get_request()
        sessions = self.sessions.all()

        fs = get_filterset(request, self.sessions.model)
        if fs:
            specs = fs.get_specs()
            if specs:
                sfilter = Q()
                filters = ["__".join(spec.components) for spec in specs]
                values = [spec.value for spec in specs]
                for f, v in zip(filters, values):
                    sfilter &= Q(**{f: v})
                sessions = sessions.filter(sfilter)

        return sessions

    def __unicode__(self): return getattr(self, self.selector_field)

    def __str__(self): return self.__unicode__()

    def __verbose_str__(self):
        sessions = self.request_sessions()
        return f'{self.name} ({len(sessions)} sessions recorded, {self.min_players}-{self.max_players} players)'

    def __rich_str__(self, link=None):
        name = field_render(self.name, link_target_url(self, link))
        pmin = self.min_players
        pmax = self.max_players
        beta = self.trueskill_beta
        tau = self.trueskill_tau * 100
        p = int(self.trueskill_p * 100)
        sessions = self.request_sessions()
        return f'{name} (({len(sessions)} sessions recorded, {pmin}-{pmax} players), Skill factor: {beta:0.2f}, Draw probability: {p:d}%, Skill dynamics factor: {tau:0.2f}'

    def __detail_str__(self, link=None):
        detail = self.__rich_str__(link)

        plays = self.league_plays

        detail += "<BR>Play counts:<UL>"
        for league in plays:
            if league == ALL_LEAGUES:
                # Don't show the global count if there's only one league!
                if len(plays) > 2:
                    league_str = "across all leagues."
                else:
                    league_str = ""
            else:
                league_str = f"in League: {field_render(league, link)}"

            if league_str:
                detail += f"<LI>{plays[league]['sessions']} plays and {plays[league]['players']} players {league_str}</LI>"
        detail += "</UL>"

        return detail

    def check_integrity(self, passthru=True):
        '''
        Perform integrity check on this Game record
        '''
        Session = apps.get_model(APP, "Session")
        Team = apps.get_model(APP, "Team")
        Performance = apps.get_model(APP, "Performance")

        L = AssertLog(passthru)

        pfx = f"Game Integrity error (id: {self.id}):"

        # Check that it has all leagues registered that played it
        leagues_played = set(Session.objects.filter(game=self).values_list('league'))
        leagues_registered = set(self.leagues.all().values_list('pk'))
        L.Assert(leagues_played == leagues_registered, f"{pfx} Played in leagues: {leagues_played}, registered with leagues: {leagues_registered}")

        # Check that only allowed play modes were played
        if not self.individual_play:
            individual_plays = Session.objects.filter(game=self, team_play=False).values_list('pk')
            L.Assert(not individual_plays, f"{pfx} Only team play allowed but these sessions recorded with individual play: {individual_plays}")

        if not self.team_play:
            team_plays = Session.objects.filter(game=self, team_play=True).values_list('pk')
            L.Assert(not team_plays, f"{pfx} Only individual play allowed but these sessions recorded with team play: {team_plays}")

        # Check player counts within limits
        sessions = Session.objects.annotate(player_count=Count('performances')).filter(game=self)
        too_few = sessions.filter(player_count__lt=self.min_players).values_list('pk')
        L.Assert(not too_few, f"{pfx} Too few players in these sessions: {too_few}")

        too_many = sessions.filter(player_count__gt=self.max_players).values_list('pk')
        L.Assert(not too_many, f"{pfx} Too many players in these sessions: {too_many}")

        # Check team sizes within limits
        if self.team_play:
            teams = Team.objects.annotate(player_count=Count('players')).filter(ranks__session__game=self)

            too_few = teams.filter(player_count__lt=self.min_players_per_team).values_list('pk')
            L.Assert(not too_few, f"{pfx} Too few players in these teams: {too_few}")

            too_many = teams.filter(player_count__gt=self.max_players_per_team).values_list('pk')
            L.Assert(not too_many, f"{pfx} Too many players in these teams: {too_many}")

        # Check all trueskill parameters are consistent with recorded session performances
        performances = (Performance.objects.filter(session__game=self).
            annotate(diff_beta=Func(F('trueskill_beta') - self.trueskill_beta, function='ABS')).
            annotate(diff_tau=Func(F('trueskill_tau') - self.trueskill_tau, function='ABS')).
            annotate(diff_p=Func(F('trueskill_p') - self.trueskill_p, function='ABS')))

        wrong_betas = performances.filter(diff_beta__gt=FLOAT_TOLERANCE).values_list('pk')
        L.Assert(not wrong_betas, f"{pfx} Incorrect Betas recorded on Performances: {wrong_betas}")

        wrong_taus = performances.filter(diff_tau__gt=FLOAT_TOLERANCE).values_list('pk')
        L.Assert(not wrong_taus, f"{pfx} Incorrect Taus recorded on Performances: {wrong_taus}")

        wrong_ps = performances.filter(diff_p__gt=FLOAT_TOLERANCE).values_list('pk')
        L.Assert(not wrong_ps, f"{pfx} Incorrect ps recorded on Performances: {wrong_ps}")

        return L.assertion_failures

    class Meta(AdminModel.Meta):
        verbose_name = "Game"
        verbose_name_plural = "Games"
        ordering = ['name']
        constraints = [ models.UniqueConstraint(fields=['name'], name='unique_game_name') ]
