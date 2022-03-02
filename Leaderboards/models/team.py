from . import MAX_NAME_LENGTH

from django.db import models
from django.urls import reverse

from django_model_admin_fields import AdminModel

from django_generic_view_extensions.model import field_render,link_target_url

import html

class Team(AdminModel):
    '''
    A player team, which is defined when a team play game is recorded and needed to properly display a session as it was played,
    and to calculate team based TrueSkill ratings. Teams have no names just a list of players.

    Teams may have names but don't need them.
    '''
    name = models.CharField('Name of the Team (optional)', max_length=MAX_NAME_LENGTH, null=True)
    players = models.ManyToManyField('Player', verbose_name='Players', blank=True, editable=False, related_name='member_of_teams')

    @property
    def games_played(self) -> list:
        games = []
        for r in self.ranks.all():
            game = r.session.game
            if not game in games:
                games.append(game)

        return games

    @property
    def link_internal(self) -> str:
        return reverse('view', kwargs={"model":self._meta.model.__name__, "pk": self.pk})

    add_related = ["players"]

    def __unicode__(self):
        if self.name:
            return self.name
        elif self._state.adding:  # self.players is unavailable
            return "Empty Unsaved Team"
        else:
            return u", ".join([str(p) for p in self.players.all()])

    def __str__(self): return self.__unicode__()

    def __verbose_str__(self):
        name = self.name if self.name else ""
        return name + u" (" + u", ".join([str(p) for p in self.players.all()]) + u")"

    def __rich_str__(self, link=None):
        games = self.games_played
        if len(games) > 2:
            game_str = ", ".join(map(lambda g: field_render(g, link), games[0:1])) + "..."
        elif len(games) > 0:
            game_str = ", ".join(map(lambda g: field_render(g, link), games))
        else:
            game_str = html.escape("<No Game>")

        name = field_render(self.name, link_target_url(self, link)) if self.name else ""
        return name + u" (" + u", ".join([field_render(p, link) for p in self.players.all()]) + u") for " + game_str

    def __detail_str__(self, link=None):
        if self.name:
            detail = field_render(self.name, link_target_url(self, link))
        else:
            detail = html.escape("<Nameless Team>")

        games = self.games_played
        if len(games) > 2:
            game_str = ", ".join(map(lambda g: field_render(g, link), games[0:1])) + "..."
        elif len(games) > 0:
            game_str = ", ".join(map(lambda g: field_render(g, link), games))
        else:
            game_str = html.escape("<no game>")

        detail += " for " + game_str + "<UL>"
        for p in self.players.all():
            detail += "<LI>{}</LI>".format(field_render(p, link))
        detail += "</UL>"
        return detail

    class Meta(AdminModel.Meta):
        verbose_name = "Team"
        verbose_name_plural = "Teams"
