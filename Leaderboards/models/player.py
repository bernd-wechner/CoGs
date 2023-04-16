from . import APP, MAX_NAME_LENGTH, ALL_LEAGUES, visibility_options

from ..leaderboards.enums import LB_PLAYER_LIST_STYLE

from Import.models import Import

from tailslide import Median

from django.db import models
from django.db.models import Q, F, Count, Min, Max, Value, FilteredRelation, Case, When, Expression, Value, CharField
from django.db.models.functions import Concat
from django.apps import apps
from django.urls import reverse
from django.contrib import admin
from django.contrib.auth.models import User
from django.utils.functional import cached_property, classproperty
from django.db.models import IntegerField, TextField, ForeignKey, FloatField, DecimalField
from django.db.models.functions import Extract, Greatest
from django.db.models.expressions import Subquery, OuterRef, ExpressionWrapper
from django.contrib.postgres.aggregates import ArrayAgg

from django_cte import CTEManager, With

from django_model_admin_fields import AdminModel

from django_model_privacy_mixin import PrivacyMixIn

from django_rich_views.options import flt
from django_rich_views.decorators import property_method
from django_rich_views.model import field_render, link_target_url, NotesMixIn

from bitfield import BitField
from bitfield.forms import BitFieldCheckboxSelectMultiple


class Player(AdminModel, PrivacyMixIn, NotesMixIn):
    '''
    A player who is presumably collecting Ratings on Games and participating in leaderboards in one or more Leagues.

    Players can be Registrars, meaning they are permitted to record session results, or Staff meaning they can access the admin site.
    '''
    objects = CTEManager()

    Team = apps.get_model(APP, "Team", False)
    League = apps.get_model(APP, "League", False)

    # Basic Player fields
    name_nickname = models.CharField('Nickname', max_length=MAX_NAME_LENGTH, unique=True)
    name_personal = models.CharField('Personal Name', max_length=MAX_NAME_LENGTH)
    name_family = models.CharField('Family Name', max_length=MAX_NAME_LENGTH)

    email_address = models.EmailField('Email Address', blank=True, null=True)
    BGGname = models.CharField('BoardGameGeek Name', max_length=MAX_NAME_LENGTH, default='', blank=True, null=True)  # BGG URL is https://boardgamegeek.com/user/BGGname

    # Privilege fields
    is_registrar = models.BooleanField('Authorised to record session results?', default=False)
    is_staff = models.BooleanField('Authorised to access the admin site?', default=False)

    # Membership fields
    teams = models.ManyToManyField('Team', through=Team.players.through, verbose_name='Teams', editable=False, related_name='players_in_team')  # Don't edit teams always inferred from Session submissions
    leagues = models.ManyToManyField('League', through=League.players.through, verbose_name='Leagues', blank=True, related_name='players_in_league')

    # A default or preferred league for each player. Optional. Can be used to customise views.
    league = models.ForeignKey(League, verbose_name='Preferred League', related_name="preferred_league_of", blank=True, null=True, default=None, on_delete=models.SET_NULL)

    # account
    user = models.OneToOneField(User, verbose_name='Username', related_name='player', blank=True, null=True, default=None, on_delete=models.SET_NULL)

    # PrivacyMixIn `visibility_` atttributes to configure visibility of possibly "private" fields
    visibility_name_nickname = BitField(visibility_options, verbose_name='Nickname Visibility', default=('all',), blank=True)
    visibility_name_personal = BitField(visibility_options, verbose_name='Personal Name Visibility', default=('all',), blank=True)
    visibility_name_family = BitField(visibility_options, verbose_name='Family Name Visibility', default=('share_leagues',), blank=True)
    visibility_email_address = BitField(visibility_options, verbose_name='Email Address Visibility', default=('share_leagues', 'share_teams'), blank=True)
    visibility_BGGname = BitField(visibility_options, verbose_name='BoardGameGeek Name Visibility', default=('share_leagues', 'share_teams'), blank=True)

    # Optionally associate with an import. We call it "source" and if it is null (none)
    # this suggests not imported but entered directly through the UI.
    source = models.ForeignKey(Import, verbose_name='Source', related_name='players', editable=False, null=True, on_delete=models.SET_NULL)


    @cached_property
    def owner(self) -> User:
        return self.user

    @cached_property
    def full_name(self) -> str:
        return f"{self.name_personal} {self.name_family}"

    @classproperty
    def Full_name(cls) -> Expression:  # For use in annotations and filters @NoSelf
        return Concat('name_personal', Value(' '), 'name_family', output_field=CharField())

    @cached_property
    def complete_name(self) -> str:
        return f"{self.name_personal} {self.name_family} ({self.name_nickname})"

    @classproperty
    def Complete_name(cls) -> Expression:  # For use in annotations and filters @NoSelf
        return Concat('name_personal', Value(' '), 'name_family', Value(' ('), 'name_nickname', Value(')'), output_field=CharField())

    @cached_property
    def games_played(self) -> list:
        '''
        Returns all the games that that this player has played
        '''
        Game = apps.get_model(APP, "Game", False)
        games = Game.objects.filter((Q(sessions__ranks__player=self) | Q(sessions__ranks__team__players=self))).distinct()
        return None if (games is None or games.count() == 0) else games

    @cached_property
    def games_won(self) -> list:
        '''
        Returns all the games that that this player has won
        '''
        Game = apps.get_model(APP, "Game")
        games = Game.objects.filter(Q(sessions__ranks__rank=1) & (Q(sessions__ranks__player=self) | Q(sessions__ranks__team__players=self))).distinct()
        return None if (games is None or games.count() == 0) else games

    @property_method
    def last_play(self, game=None) -> object:
        '''
        For a given game returns the session that represents the last time this player played that game.
        '''
        Session = apps.get_model(APP, "Session")
        sFilter = (Q(ranks__player=self) | Q(ranks__team__players=self))
        if game:
            sFilter &= Q(game=game)

        plays = Session.objects.filter(sFilter).order_by('-date_time')

        return None if (plays is None or plays.count() == 0) else plays[0]

    @property_method
    def last_win(self, game=None) -> object:
        '''
        For a given game returns the session that represents the last time this player won that game.
        '''
        Session = apps.get_model(APP, "Session")
        sFilter = Q(ranks__rank=1) & (Q(ranks__player=self) | Q(ranks__team__players=self))
        if game:
            sFilter &= Q(game=game)

        plays = Session.objects.filter(sFilter).order_by('-date_time')

        return None if (plays is None or plays.count() == 0) else plays[0]

    @cached_property
    def last_plays(self) -> list:
        '''
        Returns the session of last play for each game played.
        '''
        sessions = {}
        played = [] if self.games_played is None else self.games_played
        for game in played:
            sessions[game] = self.last_play(game)
        return sessions

    @cached_property
    def last_wins(self) -> list:
        '''
        Returns the session of last play for each game won.
        '''
        sessions = {}
        played = [] if self.games_played is None else self.games_played
        for game in played:
            lw = self.last_win(game)
            if not lw is None:
                sessions[game] = self.last_win(game)
        return sessions

    @property_method
    def sessions_played(self, game=None) -> object:
        '''
        For a given game returns all the sessions this player played that game.
        '''
        Session = apps.get_model(APP, "Session")
        sFilter = (Q(ranks__player=self) | Q(ranks__team__players=self))
        if game:
            sFilter &= Q(game=game)

        plays = Session.objects.filter(sFilter).order_by('-date_time')

        return None if (plays is None or plays.count() == 0) else plays

    @cached_property
    def leaderboard_positions(self) -> list:
        '''
        Returns a dictionary of leagues, each value being a dictionary of games with a
        value that is the leaderboard position this player holds on that league for
        that game.
        '''
        positions = {}

        played = [] if self.games_played is None else self.games_played

        # Include a GLOBAL league only if this player is in more than one league, else
        # Global is identical to their one league anyhow.
        multiple_leagues = self.leagues.all().count() > 1
        if multiple_leagues:
            positions[ALL_LEAGUES] = {}
            for game in played:
                positions[ALL_LEAGUES][game] = self.leaderboard_position(game)

        for league in self.leagues.all():
            positions[league] = {}
            for game in played:
                positions[league][game] = self.leaderboard_position(game, league)

        return positions

    @cached_property
    def leaderboards_winning(self) -> list:
        '''
        Returns a dictionary of leagues, each value being a list of games this player
        is winning the leaderboard on.
        '''
        result = {}

        played = [] if self.games_played is None else self.games_played

        # Include a GLOBAL league only if this player is in more than one league, else
        # Global is identical to their one league anyhow.
        multiple_leagues = self.leagues.all().count() > 1
        if multiple_leagues:
            result[ALL_LEAGUES] = []
            for game in played:
                if self.is_at_top_of_leaderboard(game):
                    result[ALL_LEAGUES].append(game)

        for league in self.leagues.all():
            result[league] = []
            for game in played:
                if self.is_at_top_of_leaderboard(game, league):
                    result[league].append(game)

        return result

    @cached_property
    def link_internal(self) -> str:
        return reverse('view', kwargs={"model":self._meta.model.__name__, "pk": self.pk})

    @cached_property
    def link_external(self) -> str:
        if self.BGGname and not 'BGGname' in self.hidden:
            return "https://boardgamegeek.com/user/{}".format(self.BGGname)
        else:
            return None

    @property
    def name_template(self):
        '''
        Can be used in HTML to anchor the position of a player name, that can then
        be replaced by a rendered name. Templates are used for storing data so that
        the privacy of players is not compromised by storing such data, and can be
        managed at time of rendering the stored HTMl. Particularly relevant to cached
        leaderboards (which contain HTML elements when session wrapped)
        '''
        return fr'{{Player\.{self.pk}}}'

    @property
    def name_variants(self):
        '''
        Returns a tuple of the name name variants supported with privacy rules applied.
        '''
        return (self.name_nickname, self.full_name , self.complete_name)

    @property
    def name_options(self):
        '''
        Returns a string enclosed { } containing first the Pk of the player and then
        the name options. These are inthe order fo the optioins defined in
        Leaderboards.leaderboards.enums.NameSelections, an enum that can index
        into this list to get the name in the selected format.

        This can be used with self.name_template. That is, instances in an HTML template
        of self.name_template can be replaced by this at render time.

        The reason this is done at render time si that such templates cna be cached globally
        (in Leaderboard_Cache) and so only self.name_templates shoudl be stored, and when
        the cache is retriend, they should be replaced pre-flight to the client with this
        string, so the client side can render the template dynamically.
        '''
        return "{" + f"{self.pk}" + ",".join([v for v in self.name_variants]) + "}"

    def name(self, style="full"):
        '''
        Renders the players name in a nominated style
        :param style: Supports "nick", "full", "complete", "flexi", "template"

        flexi is a special request to return {pk, nick, full, complete}
        empowering the caller to choose the name style later. This is
        ideally to allow a client to choose rendering in Javascript
        rather than fixing the rendering at server side.

        template is another special request, to provide a PK containing template that
        can be replaced with a rendered name when rendering takes place. That can
        happen client side especially when flexis delivered (which has the Privacy
        constraints applied already to all variants it supplies, and so the relevant
        one can be chosed client side and applied by subbing htis template out.
        '''
        # TODO: flexi has to use a delimeter that cannot be in a name and that should be enforced (names
        #       have them escaped currently using comma, but names can still have commas!
        return (self.name_nickname if style == "nick"
           else self.full_name if style == "full"
           else self.complete_name if style == "complete"
           else self.name_options if style == "flexi"
           else self.name_template if style == "template"
           else "Anonymous")

    def rating(self, game):
        '''
        Returns the Trueskill rating for this player at the specified game
        '''
        from django_rich_views.queryset import print_SQL
        Rating = apps.get_model(APP, "Rating")
        try:
            r = Rating.objects.get(player=self, game=game)
        except Rating.DoesNotExist:
            r = Rating.create(player=self, game=game)
        except Rating.MultipleObjectsReturned:
            raise ValueError("Database error: more than one rating for {} at {}".format(self.name_nickname, game.name))
        return r

    def leaderboard_position(self, game, leagues=[]):
        lb = game.leaderboard(leagues, style=LB_PLAYER_LIST_STYLE.data)
        for pos, entry in enumerate(lb):
            if entry[0] == self.pk:
                return pos + 1  # pos is 0 based, leaderboard positions are 1 based

    def is_at_top_of_leaderboard(self, game, leagues=[]):
        return self.leaderboard_position(game, leagues) == 1

    @classmethod
    def stats(cls, leagues=ALL_LEAGUES):
        '''
        Prepare a QuerySet containing the stats needed by the players view.

        !    NickName
        Number of (implicit) events they have attended
        !    Number of game leaderboards they are on
        Number of boards they are topping
        Number of boards they are in the top N
        !    Number of game sessions they have recorded
        !    First recorded session time
        !    Last recorded session time
        !    Session/unit_time (how often they played)
        !    First game they played
        !    Last game they played
        !    Game they've played most of (most recent as tie breaker)
        !    Mean sessions per game (repeat play measure)
        !    Largest game played (player count)
        !    Smallest game played (player count)
        Median session size (player count)

        :param cls: Our class (so we can build a queryset on it to return)
        '''
        Player = cls
        Session = apps.get_model(APP, "Session")
        Performance = apps.get_model(APP, "Performance")
        Game = apps.get_model(APP, "Game")
        Event = apps.get_model(APP, "Event")

        qs = Player.objects.all()
        if not leagues == ALL_LEAGUES:
            qs = qs.filter(leagues__in=leagues)

        # from django_rich_views.queryset import print_SQL

        # Get first and last game
        performances = Performance.objects.filter(player=OuterRef('pk'))
        first_performance = performances.order_by('session__date_time')[:1]
        last_performance = performances.order_by('-session__date_time')[:1]

        first_game_pk = Subquery(first_performance.values('session__game__pk'))
        first_game = Subquery(first_performance.values('session__game__name'))

        last_game_pk = Subquery(last_performance.values('session__game__pk'))
        last_game = Subquery(last_performance.values('session__game__name'))

        # Get most played game
        game_count = Count('performances__session__game', distinct=True)
        game_list = ArrayAgg('performances__session__game', distinct=True)

        games = Game.objects.filter(sessions__performances__player__pk=OuterRef('pk'))
        games = games.annotate(play_count=Count('pk'), last_play=Max('sessions__date_time'))
        most_played = games.order_by('-play_count', '-last_play')[:1]

        most_played_pk = Subquery(most_played.values('pk'))
        most_played_name = Subquery(most_played.values('name'))
        most_played_count = Subquery(most_played.values('play_count'))

        # Get the length of the play history (tenure)
        tenure = Greatest(Extract((Max('performances__session__date_time') - Min('performances__session__date_time')), 'days') , 1)
        rpm = ExpressionWrapper(Count('performances') / tenure * Case(When(tenure__gt=30, then=30), default=1), output_field=FloatField())

        # Double up on OuterRef so that we get the player pk not the session pk in the sessions resolution
        session_pks = Session.objects.filter(performances__player=OuterRef(OuterRef('pk'))).values('pk')
        sessions = Session.objects.filter(pk__in=session_pks).annotate(num_players=Count('performances'))
        smallest_session = sessions.values('num_players').order_by('num_players')[:1]
        largest_session = sessions.values('num_players').order_by('-num_players')[:1]

        # Median will need a CTE Alas I think. Median cannot act on an aggregate or subquery etc. It can act ona  column on a SEelct FROM as an aggregate.
        # mqs = qs.alias(session=Subquery(sessions)).annotate(median=Median('session__num_players'))
        # print_SQL(mqs)

        # This accepts filters and these msut be taken from the request
        # events = Event.implicit()
        # player_events = events.filter(players__in=OuterRef('pk'))

        qs = qs.annotate(
                session_count=Count('performances'),
                first_session_time=Min('performances__session__date_time'),
                last_session_time=Max('performances__session__date_time'),
                first_game_pk=first_game_pk,
                first_game=first_game,
                last_game_pk=last_game_pk,
                last_game=last_game,
                game_count=game_count,
                game_list=game_list,
                most_played_pk=most_played_pk,
                most_played=most_played_name,
                most_played_count=most_played_count,
                tenure=tenure,
                results_per_month=rpm,
                smallest_session=smallest_session,
                largest_session=largest_session,
                # median_session=median_session
                # events=Subquery(player_events.values('event').annotate(Count('event')), output_field=IntegerField())
                ).values(
                    'pk',
                    'name_nickname',
                    'session_count',
                    'game_count',
                    'game_list',
                    'first_session_time',
                    'last_session_time',
                    'first_game_pk',
                    'first_game',
                    'last_game_pk',
                    'last_game',
                    'most_played_pk',
                    'most_played',
                    'most_played_count',
                    'tenure',
                    'results_per_month',
                    'smallest_session',
                    'largest_session',
                    # 'median_session'
                    # 'events'
                    ).order_by('-session_count')

        # print_SQL(qs)
        return qs

    selector_field = "name_nickname"

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
                # TODO: Should really respect s['filter_priorities'] as the list view does.
                qs = qs.filter(leagues=league)

        if query:
            qs = qs.filter(**{f'{cls.selector_field}__icontains': query})

        qs = qs.annotate(play_count=Count('performances')).order_by("-play_count")

        return qs

    intrinsic_relations = None

    def __unicode__(self): return getattr(self, self.selector_field)

    def __str__(self): return self.__unicode__()

    def __verbose_str__(self):
        return u'{} {} ({})'.format(self.name_personal, self.name_family, self.name_nickname)

    def __rich_str__(self, link=None):
        return u'{} - {}'.format(field_render(self.__verbose_str__(), link_target_url(self, link)), field_render(self.email_address, link if link == flt.none else flt.mailto))

    def __detail_str__(self, link=None):
        detail = self.__rich_str__(link)

        lps = self.leaderboard_positions

        detail += "<BR>Leaderboard positions:<UL>"
        for league in lps:
            detail += "<LI>in League: {}</LI><UL>".format(field_render(league, link))
            for game in lps[league]:
                detail += "<LI>{}: {}</LI>".format(field_render(game, link), lps[league][game])
            detail += "</UL>"
        detail += "</UL>"

        return detail

    # TODO: clean() method to force test that player is in a league!
    class Meta(AdminModel.Meta):
        verbose_name = "Player"
        verbose_name_plural = "Players"
        ordering = ['name_nickname']


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    formfield_overrides = { BitField: {'widget': BitFieldCheckboxSelectMultiple}, }

