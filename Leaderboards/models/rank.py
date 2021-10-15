from . import APP

from django.db import models
from django.urls import reverse
from django.apps import apps
from django.core.exceptions import ValidationError

from django_model_admin_fields import AdminModel

from django_generic_view_extensions.util import AssertLog
from django_generic_view_extensions.model import field_render, link_target_url

from ..trueskill_helpers import TrueSkillHelpers  # Helper functions for TrueSkill, based on "Understanding TrueSkill"

class Rank(AdminModel):
    '''
    The record, for a given Session of a Rank (i.e. 1st, 2nd, 3rd etc) for a specified Player or Team.

    Either a player or team is specified, neither or both is a data error.
    Which one, is specified in the Session model where a record is kept of whether this was a Team play session or not (i.e. Individual play)
    '''
    session = models.ForeignKey('Session', verbose_name='Session', related_name='ranks', on_delete=models.CASCADE)  # if the session is deleted, delete this rank
    rank = models.PositiveIntegerField('Rank')  # The rank (in this session) we are recording, as in 1st, 2nd, 3rd etc.
    score = models.IntegerField('Score', default=None, null=True, blank=True)  # What this team scored if the game has team scores.

    # One or the other of these has a value the other should be null (enforce in integrity checks)
    # We coudlof course opt to use a single GenericForeignKey here:
    #    https://docs.djangoproject.com/en/1.10/ref/contrib/contenttypes/#generic-relations
    #    but there are some complexites they introduce that are rather unnatracive as well
    player = models.ForeignKey('Player', verbose_name='Player', blank=True, null=True, related_name='ranks', on_delete=models.SET_NULL)  # If the player is deleted keep this rank
    team = models.ForeignKey('Team', verbose_name='Team', blank=True, null=True, related_name='ranks', on_delete=models.SET_NULL)  # if the team is deleted keep this rank

    add_related = ["player", "team"]  # When adding a Rank, add the related Players or Teams (if needed, or not if already in database)

    @property
    def performance(self):
        '''
        Returns a TrueSkill Performance for this ranking player or team. Uses very TrueSkill specific theory to provide
        a tuple of mean and standard deviation (mu, sigma) that describes TrueSkill Performance prediction.
        '''
        g = self.session.game
        ts = TrueSkillHelpers(tau=g.trueskill_tau, beta=g.trueskill_beta, p=g.trueskill_p)

        return ts.Rank_performance(self, after=False)

    @property
    def performance_after(self):
        '''
        Returns a TrueSkill Performance for this ranking player or team using the ratings the received after this session update.
        Uses very TrueSkil specific theory to provide a tuple of mean and standard deviation (mu, sigma) that describes TrueSkill
        Performance prediction.
        '''
        g = self.session.game
        ts = TrueSkillHelpers(tau=g.trueskill_tau, beta=g.trueskill_beta, p=g.trueskill_p)

        return ts.Rank_performance(self, after=True)

    @property
    def ranker(self) -> object:
        '''
        Returns either a Player or Team, as appropriate for the ranker,
        that is the player or team ranking here
        '''
        if self.session.team_play:
            return self.team
        else:
            return self.player

    @property
    def players(self) -> set:
        '''
        The list of players associated with this rank object (not explicitly at this rank
        as two Rank objects in one session may have the same rank, i.e. a draw may be recorded)

        Players in teams are listed individually.

        Returns a list of one one or more players.
        '''
        Session = apps.get_model(APP, "Session")
        
        session = Session.objects.get(id=self.session.id)
        if session.team_play:
            if self.team is None:
                raise ValueError("Rank '{}' is associated with a team play session but has no team.".format(self.id))
            else:
                # TODO: Test that this returns a clean list and not a QuerySet
                players = set(self.team.players.all())
        else:
            if self.player is None:
                raise ValueError("Rank '{0}' is associated with an individual play session but has no player.".format(self.id))
            else:
                players = {self.player}
        return players

    @property
    def is_part_of_draw(self) -> bool:
        '''
        Returns True or False, indicating whether or not more than one rank object on this session has the same rank
        (i.e. if this rank object is one part of a recorded draw).
        '''
        ranks = Rank.objects.filter(session=self.session, rank=self.rank)
        return len(ranks) > 1

    @property
    def is_victory(self) -> bool:
        '''
        True if this rank records a victory, False if not.
        '''
        return self.rank == 1

    @property
    def is_team_rank(self):
        return self.session.team_play

    @property
    def link_internal(self) -> str:
        return reverse('view', kwargs={"model":self._meta.model.__name__, "pk": self.pk})

    # @property_method
    def check_integrity(self, passthru=True):
        '''
        Perform basic integrity checks on this Rank object.
        '''
        L = AssertLog(passthru)

        pfx = f"Rank Integrity error (id: {self.id}):"

        # Check that one of self.player and self.team has a valid value and the other is None
        L.Assert(not (self.team is None and self.player is None), f"{pfx} No team or player specified!")
        L.Assert(not (not self.team is None and not self.player is None), f"{pfx} Both team and player are specified!")

        if self.team is None:
            L.Assert(not self.session.team_play, f"{pfx} Rank specifies a player while session (ID: {self.session.pk}) specifies team play")
        elif self.player is None:
            L.Assert(self.session.team_play, f"{pfx} Rank specifies a team while session (ID: {self.session.pk}) does not specify team play")

        return L.assertion_failures

    def __unicode__(self):
        return "{}".format(self.rank)

    def __str__(self): return self.__unicode__()

    def __verbose_str__(self):
        if self.session is None:  # Don't crash of the rank is orphaned!
            game = "<no game>"
            ranker = self.player
        else:
            game = self.session.game
            ranker = self.team if self.session.team_play else self.player
        return  u'{} - {} - {}'.format(game, self.rank, ranker)

    def __rich_str__(self, link=None):
        if self.session is None:  # Don't crash of the rank is orphaned!
            game = "<no game>"
            team_play = False
            ranker = field_render(self.player, link)
        else:
            game = field_render(self.session.game, link)
            team_play = self.session.team_play
            ranker = field_render(self.team, link) if team_play else field_render(self.player, link)
        return  u'{} - {} - {}'.format(game, field_render(self.rank, link_target_url(self, link)), ranker)

    def __detail_str__(self, link=None):
        if self.session is None:  # Don't crash of the rank is orphaned!
            game = "<no game>"
            team_play = False
            ranker = field_render(self.player, link)
            mode = "individual"
        else:
            game = field_render(self.session.game, link)
            team_play = self.session.team_play
            ranker = field_render(self.team, link) if team_play else field_render(self.player, link)
            mode = "team" if team_play else "individual"
        return  u'{} - {} - {} ({} play)'.format(game, field_render(self.rank, link_target_url(self, link)), ranker, mode)

    def clean(self):
        # Require that one of self.team and self.player is None
        if self.team is None and self.player is None:
            # FIXME: For now let clean pass with no team if teamplay is selected.
            # This is because the team is not created until post processing (after the clean and save)
            # at present. This should be rethought and perhaps done in pre-processing so as
            # to present teams for the validation (and clean).
            # But because we don't know if it's a team_play session or not, that is,
            # clean is happening before the link to the session is made (self.session_id = None
            # we have to pass this condition always for now.
            # raise ValidationError("No team or player specified in rank {}".format(self.pk))
            pass
        # When editing Rank objects and changing the team_play setting in the associated setting,
        # It can easily be that a team is added and a player remains. Clean up any duplicity on
        # submission.
        if not self.team is None and not self.player is None:
            if not hasattr(self.session, "team_play"):
                raise ValidationError("Both team and player specified in rank {} but it has no associated session so we can't clean it.".format(self.pk))

            if self.session.team_play:
                self.player = None
            else:
                self.team = None

    class Meta(AdminModel.Meta):
        verbose_name = "Rank"
        verbose_name_plural = "Ranks"
        ordering = ['rank']