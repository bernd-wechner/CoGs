from . import APP

from django.db import models
from django.db.models import Count
from django.apps import apps
from django.urls import reverse

from django_model_admin_fields import AdminModel

from django_rich_views.model import field_render, link_target_url, NotesMixIn

DEFAULT_TOURNEY_MIN_PLAYS = 2
DEFAULT_TOURNEY_WEIGHT = 1
DEFAULT_TOURNEY_ALLOWED_IMBALANCE = 0.5


class TourneyRules(AdminModel):
    '''
    A custom Through table for Tourney-Games that specifies the rules that apply to a given game in a given tourney
    especially the a weight for each game and a minimim play count for each game.

    The weight is used in building an aggregate rating by summing weighted mus, and summming weighted sigmas.

    Weights should be normalised in such an application.
    '''
    tourney = models.ForeignKey('Tourney', related_name="rules", on_delete=models.CASCADE)  # If the tourney is deleted delete this rule
    game = models.ForeignKey('Game', on_delete=models.CASCADE)  # If the game is deleted delete this rule

    # Require a minimum number of plays inhtis game to rank the tourney
    min_plays = models.PositiveIntegerField('Minimum number of plays to rank in tourney', default=DEFAULT_TOURNEY_MIN_PLAYS)

    # Skill weight for this game (shoudl be normalised across all games in thee tourney when used)
    weight = models.FloatField('The weighting of this games contribution to a Tourney rating', default=DEFAULT_TOURNEY_WEIGHT)

    @property
    def link_internal(self) -> str:
        return reverse('view', kwargs={"model":self._meta.model.__name__, "pk": self.pk})

    def __unicode__(self):
        return f'{self.tourney.name} - {self.game.name}'

    def __str__(self): return self.__unicode__()

    def __verbose_str__(self):
        return f'{self.tourney.name} - {self.game.name}: min_plays={self.min_plays}, weight={self.weight}'

    def __rich_str__(self, link=None):
        tourney_name = field_render(self.tourney.name, link_target_url(self.tourney, link))
        game_name = field_render(self.game.name, link_target_url(self.game, link))
        return f'{tourney_name} - {game_name}: min_plays={self.min_plays}, weight={self.weight}'

    def __detail_str__(self, link=None):
        return self.__rich_str__(link)

    class Meta(AdminModel.Meta):
        verbose_name = "Rule"
        verbose_name_plural = "Rules"


class Tourney(AdminModel, NotesMixIn):
    '''A Tourney is simply a group of games that can present a shared leaderboard according to specified weights.'''
    name = models.CharField('Name of the Tourney', max_length=200)
    games = models.ManyToManyField('Game', verbose_name='Games', through=TourneyRules)

    # Require a certain play balance among the tourney games.
    # This is the coefficient of variation between play counts (for all game sin the tourney by a given player)
    # 0 requires that all games be played the same number of times.
    # 1 is extremely tolerant, allowing the the mean value between them
    #    for a two game tourney allows all play imbalance
    #    for a many game tourney not quite guaranteed (outliers may be excluded still)
    # See: https://en.wikipedia.org/wiki/Coefficient_of_variation
    allowed_imbalance = models.FloatField('Maximum play count imbalance to rank in tourney', default=DEFAULT_TOURNEY_ALLOWED_IMBALANCE)

    @property
    def players(self) -> set:
        '''
        Return a QuerySet of players who qualify for this tournament.
        '''
        Performance = apps.get_model(APP, "Performance")
        Player = apps.get_model(APP, "Player")

        # First collect the tourney rules
        min_plays = {}
        for r in self.rules.all():
            min_plays[r.game] = r.min_plays

        # Collect a list of player sets (one that meats each rule)
        players = []
        for g in self.games.all():
            if g in min_plays:
                players.append(set(Performance.objects.filter(session__game=g).order_by().values_list('player').annotate(playcount=Count('player')).filter(playcount__gte=min_plays[g]).values_list('player', flat=True)))

        # Find the intersection
        players = set.intersection(*players)

        # Get the players
        return Player.objects.filter(pk__in=players)

    def gameplays_needed(self, player) -> dict:
        '''
        For a given player returns a dict keyed on Game which has an integer count stating the number
        of times they need to play those games to qualify for this tourney.

        :param player: an instance of Player
        '''
        pass

    @property
    def link_internal(self) -> str:
        return reverse('view', kwargs={"model":self._meta.model.__name__, "pk": self.pk})

    def __unicode__(self):
        return self.name

    def __str__(self): return self.__unicode__()

    def __verbose_str__(self):
        games = ", ".join([g.name for g in self.games.all()])
        return f'{self.name} - {games}'

    def __rich_str__(self, link=None):
        name = field_render(self.name, link_target_url(self, link))
        games = ", ".join([field_render(g.name, link_target_url(g, link)) for g in self.games.all()])
        return f'{name} - {games}'

    def __detail_str__(self, link=None):
        rules = {}
        for r in self.rules.all():
            rules[r.game] = r

        game_detail = {}
        for g in self.games.all():
            if g in rules:
                game_detail[g] = field_render(g.name, link_target_url(g, link)) + f": min_plays={rules[g].min_plays}, weight={rules[g].weight}"
            else:
                game_detail[g] = field_render(g.name, link_target_url(g, link)) + "Error: rules are missing!"

        name = field_render(self.name, link_target_url(self, link))
        games = "</li><li>".join([game_detail[g] for g in self.games.all()])
        games = f"<ul><li>{games}</li></ul"
        return f'{name}:{games}'

    class Meta(AdminModel.Meta):
        verbose_name = "Tourney"
        verbose_name_plural = "Tourneys"
        ordering = ['name']
        constraints = [ models.UniqueConstraint(fields=['name'], name='unique_tourney_name') ]
