from . import APP, MAX_NAME_LENGTH

from django.db import models
from django.db.models import Count, Q
from django.apps import apps
from django.urls import reverse

from django_model_admin_fields import AdminModel

from django_rich_views.model import field_render, link_target_url, NotesMixIn

import html


class Team(AdminModel, NotesMixIn):
    '''
    A player team, which is defined when a team play game is recorded and needed to properly display a session as it was played,
    and to calculate team based TrueSkill ratings. Teams have no names just a list of players.

    Teams may have names but don't need them.
    '''
    name = models.CharField('Name of the Team (optional)', max_length=MAX_NAME_LENGTH, null=True)
    players = models.ManyToManyField('Player', verbose_name='Players', blank=True, editable=False, related_name='member_of_teams')

    @property
    def sessions(self):
        Session = apps.get_model(APP, "Session")
        return Session.objects.filter(ranks__team=self)

    @classmethod
    def get(cls, players):
        '''
        Gets all the teams that have these players. Should ALWAYS be 0 or 1 teams.

        Never should there be more than 1 team with a given player set.

        We don't assert that here instead return the queryset for the caller to
        use as desired.

        :param players: The players in the team (in an iterable form)
        '''
        # Find teams with those players and only those players:
        # See: https://stackoverflow.com/a/73485063/4002633
        num_players = len(players)
        teams = cls.objects.alias(
                    num_players=Count('players'),
                    num_matches=Count('players', filter=Q(players__in=players))
                    ).filter(
                        num_players=num_players,
                        num_matches=num_players)

        return teams

    @classmethod
    def exists(cls, players):
        '''
        Returns True if a team exists with the specified players
        :param players: The players in the team (in an iterable form)
        '''
        return cls.get(players).count() > 0

    @classmethod
    def get_create_or_edit(cls, players, name=None, edit=None, debug=False):
        '''
        Get, create or edit a team with the specified players.

        Teams are fundamentally identified by the players in them. To wit, the Team ID is a not
        especially relevant. It can happen the a Session is edited, and the team members changed
        though. And so we have a scheme for recyling Team IDs as needed.

        Teams have a name but this is incidental totheir defintion and not used in defining a
        team, itis just a presentation convenience.

        Essentially there are a few scenarios for calling:

        The basic get or create (no "name" or "edit" provided):
            looks for an existing team witht hose players and returns it if found.
            else creates one.
            If more than one is found, raises and exception. This should never happen.

        The get and rename, or create (a "name" is supplied but no "edit")
            Same as the basic get or create but if a team is found renames it,
            and if a team is created names witht he provided name.

        The edit (an "edit" is provided and maybe a "name")
            the "edit" identifies a team and optionally a rank and/or session
            being edited as team edits most likely occur as part of a
            session edit. So "edit" is a 3-tuple of (team ID, rank ID, session ID)
            where any of these can be None with a fallback behaviour that is robust.

            Ideally we have all three on a session edit as it would submit the
            session, rank and possibly the team IDs as part of the edit.

            Crucially "players" may have changed in the edit (been added, removed,
            completely changed etc.).

            So we first see if there's an existing team with those players. If so
            we can reuse that, and optionally rename it (if a name was provided).
            Then the "edit" team ID is checked to see if it has any other references,
            If not we can delete that team from the system. If a rank ID and/or session
            ID was provided we tolerate one reference to that rank and session, otherwise
            we tolerate only 0 references.

            If the another team found with those players we need to update the session's
            rank to point to the new team! We require during an edit that any nominated
            rank belongs to any nominate session. If it differs from the rank of the team
            we presume the team was assigned to a new rank as part of the edit.

            If players don't change, we might optionally just rename this team if a
            name was provided.

        :param players: An iterable of Player objects
        :param name: optionally a name for the team, will set it if provided.
        :param edit: A tuple of Team ID a Rank Id and a Session ID to flag that this call
                    is part of a session edit (and or all might be None - with a fallback
                    behaviour).
        :param debug: If true does a duplicity check on entry and exit and breaks in the debugger
                      if duplicty found, to faciliate debugging and testing.
        '''
        Session = apps.get_model(APP, "Session")
        Rank = apps.get_model(APP, "Rank")

        if debug:
            teams = cls.get(players)
            if teams.count() > 1:
                breakpoint()

        edit_team_id, edit_rank_id, edit_session_id = (None, None, None)
        edit_team, edit_rank, edit_session = (None, None, None)
        can_kill_edit_team = False

        if edit:
            # We're fussy about edit if it's provided. So we perform a through QA on it, and asert standards
            # that make dealing with edits easier later. The caller must supply an edit tuple that complies
            # with these standards or expect fireworks.
            assert isinstance(edit, (list, tuple)), "Team.get_or_create: edit must be a list or tuple"
            assert len(edit) == 3, "Team.get_or_create: edit must be a list or tuple with three elements (team ID, Rank ID, Session ID)"

            edit_team_id, edit_rank_id, edit_session_id = edit

            # Assert existence of the three IDs and infer any missing ones as best we can
            if edit_team_id:
                assert cls.objects.filter(pk=edit_team_id).exists(), "The first element of edit, if supplied, must be a valid, existing Team ID."
                edit_team = cls.objects.get(pk=edit_team_id)
                references = Rank.objects.filter(team=edit_team)

                if not edit_rank_id and references.count() == 1:
                    edit_rank_id = references.first().id

            if edit_rank_id:
                assert Rank.objects.filter(pk=edit_rank_id).exists(), "The second element of edit, if supplied, must be a valid, existing Rank ID."
                edit_rank = Rank.objects.get(pk=edit_rank_id)

                if edit_team_id:
                    # When submitting team_play session forms and resubmitting, the edit_team is known
                    # but we have lost edit_rank.team, the ranks will have been saved without teams and
                    # the job of finding a team matching the submitted players and managing teams deleegated
                    # to this method here. It is wholly ordinary then for edit_rank.team to be None in that
                    # circumstance but we can assume it was just edit_team for now (we'll be checking players
                    # and deciding what to do below).
                    if edit_rank.team is None:
                        edit_rank.team = edit_team
                        edit_rank.save()
                    # If for any reason edit_rank.team exists, it shoudl really match edit_team.
                    else:
                        assert edit_rank.team == edit_team, "If a Team and Rank ID are supplied then they must be related."
                else:
                    edit_team = edit_rank.team

                if not edit_session_id:
                    edit_session_id = edit_rank.session.id

            if edit_session_id:
                assert Session.objects.filter(pk=edit_session_id).exists(), "The third element of edit, if supplied, must be a valid, existing Session ID."
                edit_session = Session.objects.get(pk=edit_session_id)

            # Assert relations between the three IDs
            if edit_team_id and edit_rank_id:
                assert edit_rank.team == edit_team, "If edit supplies a team and rank they must be related."

            if edit_rank_id and edit_session_id:
                assert edit_rank.session == edit_session, "If edit supplies a rank and session they must be related."

            # Determine if we can kill the edit_team_id (not if we should, only if we can, which is
            # essentially if it has no session references, or if a session
            if edit_team:
                referencing_sessions = Session.objects.filter(ranks__team=edit_team)

                if edit_rank_id or edit_session_id:
                    can_kill_edit_team = len(referencing_sessions) == 1 and referencing_sessions[0].pk == edit_session_id
                else:
                    can_kill_edit_team = len(referencing_sessions) == 0
            else:
                can_kill_edit_team = False

        # Look for an existing team with the supplied players
        # We expect 0 or 1, multiple is an error (shoudl never happen)
        teams = cls.get(players)

        if not teams:
            # If there are no teams with those players and we were provided an edit_team we can use that.
            # This happens because someone wa sediting edit_team and changed the player set. So they are
            # no longer the players in the edit_team. If the edit team can be killed (i.e. has no session
            # references (other than edit_session if provided) then we can simply recycle it and assign the
            # new player set to it.
            if edit_team and can_kill_edit_team:
                team = edit_team
            # Otherwise if there is no edit_team or we can't kill it, create a new team to capture this
            # player set (and posisbly, name)
            else:
                team = cls.objects.create()

            team.players.set(players)
            if name: team.name = name
            team.save()

            # If we are editing a rank add the team to it!
            # That's why we created it after all
            if edit_rank:
                edit_rank.team = team
                edit_rank.player = None
                edit_rank.save()

        elif len(teams) == 1:
            # We have a unique match (team with the specified players)
            existing_team = teams[0]

            # Rename it if requested to
            if name and existing_team.name != name:
                existing_team.name = name
                existing_team.save()

            if edit and existing_team != edit_team:
                # The edit_rank should now point to the existing team.
                if edit_rank:
                    edit_rank.team = existing_team
                    edit_rank.player = None
                    edit_rank.save()

                # The edit_team should be killed if it can be (has no other references)
                if  can_kill_edit_team:
                    edit_team.delete()

            team = existing_team

        else:  # len(teams) > 1
            # This should never happen, because of the way we define teams (bytheir player set) and reuse them!
            raise cls.MultipleObjectsReturned

        if debug:
            teams = cls.get(team.players.all())
            if teams.count() > 1:
                breakpoint()

        return team

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

    intrinsic_relations = ["players"]

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
