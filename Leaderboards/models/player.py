from . import APP, MAX_NAME_LENGTH, ALL_LEAGUES

from ..leaderboards import LB_PLAYER_LIST_STYLE

from django.db import models
from django.db.models import Q, Count
from django.apps import apps
from django.urls import reverse
from django.contrib import admin
from django.contrib.auth.models import User

from django_model_admin_fields import AdminModel

from django_model_privacy_mixin import PrivacyMixIn

from django_generic_view_extensions.options import flt
from django_generic_view_extensions.decorators import property_method
from django_generic_view_extensions.model import field_render, link_target_url

from bitfield import BitField
from bitfield.forms import BitFieldCheckboxSelectMultiple

class Player(PrivacyMixIn, AdminModel):
    '''
    A player who is presumably collecting Ratings on Games and participating in leaderboards in one or more Leagues.

    Players can be Registrars, meaning they are permitted to record session results, or Staff meaning they can access the admin site.
    '''
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

    # Privacy control (interfaces with django_model_privacy_mixin)
    visibility = (
        ('all', 'Everyone'),
        ('share_leagues', 'League Members'),
        ('share_teams', 'Team Members'),
        ('all_is_registrar', 'Registrars'),
        ('all_is_staff', 'Staff'),
    )

    visibility_name_nickname = BitField(visibility, verbose_name='Nickname Visibility', default=('all',), blank=True)
    visibility_name_personal = BitField(visibility, verbose_name='Personal Name Visibility', default=('all',), blank=True)
    visibility_name_family = BitField(visibility, verbose_name='Family Name Visibility', default=('share_leagues',), blank=True)
    visibility_email_address = BitField(visibility, verbose_name='Email Address Visibility', default=('share_leagues', 'share_teams'), blank=True)
    visibility_BGGname = BitField(visibility, verbose_name='BoardGameGeek Name Visibility', default=('share_leagues', 'share_teams'), blank=True)

    @property
    def owner(self) -> User:
        return self.user

    @property
    def full_name(self) -> str:
        return "{} {}".format(self.name_personal, self.name_family)

    @property
    def complete_name(self) -> str:
        return "{} {} ({})".format(self.name_personal, self.name_family, self.name_nickname)

    @property
    def games_played(self) -> list:
        '''
        Returns all the games that that this player has played
        '''
        Game = apps.get_model(APP, "Game", False)
        games = Game.objects.filter((Q(sessions__ranks__player=self) | Q(sessions__ranks__team__players=self))).distinct()
        return None if (games is None or games.count() == 0) else games

    @property
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

    @property
    def last_plays(self) -> list:
        '''
        Returns the session of last play for each game played.
        '''
        sessions = {}
        played = [] if self.games_played is None else self.games_played
        for game in played:
            sessions[game] = self.last_play(game)
        return sessions

    @property
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

    @property
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

    @property
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
                if self.is_at_top_of_leaderbard(game):
                    result[ALL_LEAGUES].append(game)

        for league in self.leagues.all():
            result[league] = []
            for game in played:
                if self.is_at_top_of_leaderbard(game, league):
                    result[league].append(game)

        return result

    @property
    def link_internal(self) -> str:
        return reverse('view', kwargs={"model":self._meta.model.__name__, "pk": self.pk})

    @property
    def link_external(self) -> str:
        if self.BGGname and not 'BGGname' in self.hidden:
            return "https://boardgamegeek.com/user/{}".format(self.BGGname)
        else:
            return None

    def name(self, style="full"):
        '''
        Renders the players name in a nominated style
        :param style: Supports "nick", "full", "complete", "flexi"

        flexi is a special request to return {pk, nick, full, complete}
        empowering the caller to choose the name style later. This is
        ideally to allow a client to choose rendering in Javascript
        rather than fixing the rendering at server side.
        '''
        # TODO: flexi has to use a delimeter that cannot be in a name and that should be enforced (names have them escaped
        #       currently using comma, but names can stil have commas!
        return (self.name_nickname if style == "nick"
           else self.full_name if style == "full"
           else self.complete_name if style == "complete"
           else f"{{{self.pk},{self.name_nickname},{self.full_name},{self.complete_name}}}" if style == "flexi"
           else "Anonymous")

    def rating(self, game):
        '''
        Returns the Trueskill rating for this player at the specified game
        '''
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

    def is_at_top_of_leaderbard(self, game, leagues=[]):
        return self.leaderboard_position(game, leagues) == 1

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
            qs = qs.filter(**{f'{cls.selector_field}__istartswith': query})

        qs = qs.annotate(play_count=Count('performances')).order_by("-play_count")

        return qs

    add_related = None

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



