from . import APP, MAX_NAME_LENGTH, ALL_LEAGUES

from ..leaderboards import LB_PLAYER_LIST_STYLE

from django.db import models
from django.apps import apps
from django.urls import reverse
from django.core.validators import RegexValidator

from django_model_admin_fields import AdminModel

from django_rich_views.model import field_render, NotesMixIn
from django_rich_views.decorators import property_method


class League(AdminModel, NotesMixIn):
    '''
    A group of Players who are competing at Games which have a Leaderboard of Ratings.

    Leagues operate independently of one another, meaning that
    when Sessions are recorded, only the Locations, Players and Games will appear on selectors.

    All Leagues share the same global and game Trueskill settings, so that a
    meaningful global leaderboard can be reported for any game across all leagues.
    '''
    name = models.CharField('Name of the League', max_length=MAX_NAME_LENGTH, validators=[RegexValidator(regex=f'^{ALL_LEAGUES}$', message=f'{ALL_LEAGUES} is a reserved league name', code='reserved', inverse_match=True)])

    manager = models.ForeignKey('Player', verbose_name='Manager', related_name='leagues_managed', null=True, on_delete=models.SET_NULL)  # if the manager is deletect, keep the league!

    locations = models.ManyToManyField('Location', verbose_name='Locations', blank=True, related_name='leagues_playing_here')
    players = models.ManyToManyField('Player', verbose_name='Players', blank=True, related_name='member_of_leagues')
    games = models.ManyToManyField('Game', verbose_name='Games', blank=True, related_name='played_by_leagues')


    @property
    def link_internal(self) -> str:
        return reverse('view', kwargs={"model":self._meta.model.__name__, "pk": self.pk})

    @property
    def leaderboards(self) -> list:
        '''
        The leaderboards for this league.

        Returns a dictionary of leaderards keyed on game.
        '''
        return self.leaderboard()

    @property_method
    def leaderboard(self, game=None, asat=None, style=LB_PLAYER_LIST_STYLE.none) -> tuple:
        '''
        Return a leaderboard for a specified game or if no game is provided, a dictionary of such
        lists keyed on game.
        '''
        Game = apps.get_model(APP, "Game")

        if game is None:
            lb = {}
            games = Game.objects.filter(leagues=self)
            for game in games:
                lb[game] = self.leaderboard(game)
        else:
            lb = game.leaderboard(leagues=self, asat=asat, style=style)

        return lb

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
                # TODO: It's a bit odd to filter leagues on league. Might consider instead to filter
                #       on related leagues, that is the more complex question, for a selected league,
                #       itself and all leagues that share one or players with this league. These are
                #       conceivably related fields.
                qs = qs.filter(pk=league)

        if query:
            qs = qs.filter(**{f'{cls.selector_field}__istartswith': query})

        return qs

    intrinsic_relations = None

    def __unicode__(self): return getattr(self, self.selector_field)

    def __str__(self): return self.__unicode__()

    def __verbose_str__(self):
        return u"{} (manager: {})".format(self, self.manager)

    def __rich_str__(self, link=None):
        return u"{} (manager: {})".format(field_render(self, link), field_render(self.manager, link))

    def __detail_str__(self, link=None):
        detail = self.__rich_str__(link)
        detail += "<UL>"
        for p in self.players.all():
            detail += "<LI>{}</LI>".format(field_render(p, link))
        detail += "</UL>"
        return detail

    class Meta(AdminModel.Meta):
        verbose_name = "League"
        verbose_name_plural = "Leagues"

        ordering = ['name']
        constraints = [ models.UniqueConstraint(fields=['name'], name='unique_league_name') ]

