from . import APP, RATING_REBUILD_TRIGGER

from ..leaderboards.enums import LB_STRUCTURE, LB_PLAYER_LIST_STYLE
from ..leaderboards.util import immutable
from ..leaderboards.style import restyle_leaderboard
from ..leaderboards.player import player_ratings, player_rankings
from ..leaderboards import augment_with_deltas

from django.db import models
from django.conf import settings
from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder

from django_model_admin_fields import AdminModel

from django_rich_views.util import pythonify
from django_rich_views.decorators import property_method
from django_rich_views.model import safe_get

from relativefilepathfield.fields import RelativeFilePathField

import os
import json

#===============================================================================
# Administrative models
#===============================================================================


class ChangeLog(AdminModel):
    '''
    A model for storing a log of edits to recorded sessions. Any such edit has an immediate impact,
    on a leaderboard (i.e a leaderboard before it happened and a learboard after it happened. These
    are stored here in this model). A log can be written any time a session is added or edited, and the
    Admin fields on the entry record who did that, while the object stores leaderboard snaphots
    before and after (the session, not the edit).

    Such logs can be expired as well (as storing a full before and after leaderboard for ever session
    add or edit adds a lot of data, and has diminishing value when the entries are considered stable.
    This model is mainly for report impacts before a commit linking to a rebuild log if a rating rebuild
    was triggered.

    A session is defined by:
        a game
        a time
        a league
        a location (venue)
        a mode (team or individual depending on what the game supports)
        a list of ranks (one per ranker, being a team or player depending on mode)
        a list of performances (one per performer, being a player).

    A given session has two leaderboard of interest, the state of the game's leaderboard before that
    session was played and after. This is what provides a measure of the impact that session has on a
    leaderboard (the state of the leaderboard before the session is of course its state immediately
    after the previous session of that game. This is porovided by session.leaderboard_impact().

    Given we want to record the impact of that session before and after this logged change we have 2
    such impacts to store (4 leaderboard snapshots). There could be some duplication of data there,
    specifically if the session game and date_time are not rebuild triggering (changed game or date_time
    changed to alter sequence of sessions) then the two before snapshot sin these impacts will be
    identical. In the rather odd case of a logged change that has no impact on the after boards they
    will  be identical too (though hard to imagine a change worth logging that has no impact!).

    TODO: This is a place to store impacts for reporting and presentation for review before
    confirming a commit. That will rely on a transaction manager (in the making) which can hold
    a database transaction open across a few views.

    The idea is that we can store impacts in this model with a key so that they can be calculated,
    saved, and the key passed to a confirmation view where the change can be committed or rolled back.
    '''

    # The session that caused the impact (if it still exists) - if it was deleted it won't be around any more.
    session = models.ForeignKey('Session', verbose_name='Session', related_name='change_logs', null=True, blank=True, on_delete=models.SET_NULL)  # If the session is deleted we may NEED the impact of that!

    # A JSON field that stores a change summary produced by Session.__json__()
    # This should saliently record which fields changed and for those that changed the value before and after the change
    changes = models.TextField(verbose_name='Changes logged for this session', null=True)

    # Any changes to the game a session relates to are centrally important to note because
    # it determines which leaderboards are impacted. session.game of course identifies the
    # game but that is the game the session points to now (and it may have been edited again
    # after this change). An unlikely scenario of course, but if it happens we want to know
    # and so a log is doubly important.
    game_before_change = models.ForeignKey('Game', null=True, blank=True, related_name='session_before_change_logs', on_delete=models.SET_NULL)
    game_after_change = models.ForeignKey('Game', null=True, blank=True, related_name='session_after_change_logs', on_delete=models.SET_NULL)

    # Space to store 2 JSON leaderboard impacts, one before the change and one after
    leaderboard_impact_before_change = models.TextField(verbose_name='Leaderboard impact before the change', null=True)
    leaderboard_impact_after_change = models.TextField(verbose_name='Leaderboard impact after the change', null=True)

    # True if the logged change impacted a leaderboard
    # i.e. if leaderboard_impact_after_change and leaderboard_impact_before_change are identical
    # The impacts can be large JSON strings and this flag registers our expectation that they are the same
    # That is, that no leaderboard impacting change was made. This is also stored in changes above but this
    # is an extract from that for easy querying and filterig of logs that only have impact or not.Which
    # can be useful for expiring logs that have low utility.
    has_impact = models.BooleanField('This change impacted the leaderboard')

    # If this change triggered a rebuild a pointer to the log of that rebuild.
    rebuild_log = models.ForeignKey('RebuildLog', null=True, on_delete=models.SET_NULL, default=None, related_name='change_logs')
    # change_logs points back to here from RebuildLog

    @property_method
    def Leaderboard_impact_before_change(self, unwrap=None):
        '''
        Returns the leaderboard impact before the change unpacked into a Python tuple.

        Note that before and after have two contexts.
            Before and after the change that was logged.
            Before and after the logged session was played.
        We endeavour to be clear at every stage which before and after we're talking about.

        Either as a LB_STRUCTURE.game_wrapped_session_wrapped_player_list with LB_PLAYER_LIST_STYLE.data
        or as a LB_STRUCTURE.player_list with LB_PLAYER_LIST_STYLE.data.

        :param unwrap: If "before" or "after" unwraps the before or after player_list
        '''
        if self.leaderboard_impact_before_change:
            igd = LB_STRUCTURE.game_data_element.value
            isd = LB_STRUCTURE.session_data_element.value
            leaderboard = immutable(json.loads(self.leaderboard_impact_before_change))
            has_before = len(leaderboard[igd]) > 1  # The first session added for a game never has a before board!
            if unwrap == "before":
                return leaderboard[igd][0][isd] if has_before else None
            elif unwrap == "after":
                return leaderboard[igd][1][isd] if has_before else leaderboard[igd][0][isd]
            else:
                return leaderboard
        else:
            return None

    @property_method
    def Leaderboard_impact_after_change(self, unwrap=None):
        '''
        Returns the leaderboard impact after the change unpacked into a Python tuple.

        Note that before and after have two contexts.
            Before and after the change that was logged.
            Before and after the logged session was played.
        We endeavour to be clear at every stage which before and after we're talking about.

        Either as a LB_STRUCTURE.game_wrapped_session_wrapped_player_list with LB_PLAYER_LIST_STYLE.data
        or as a LB_STRUCTURE.player_list with LB_PLAYER_LIST_STYLE.data.

        :param unwrap: If "before" or "after" unwraps the before or after player_list
        '''
        if self.leaderboard_impact_after_change:
            igd = LB_STRUCTURE.game_data_element.value
            isd = LB_STRUCTURE.session_data_element.value
            leaderboard = immutable(json.loads(self.leaderboard_impact_after_change))
            has_before = len(leaderboard[igd]) > 1  # The first session added for a game never has a before board!
            if unwrap == "before":
                return leaderboard[igd][0][isd] if has_before else None
            elif unwrap == "after":
                return leaderboard[igd][1][isd] if has_before else leaderboard[igd][0][isd]
            else:
                return leaderboard
        else:
            return None

    def leaderboard_after(self, game):
        '''
        Returns the leaderboard after session play (in an impact) for the specified game if it is
        in self.Games or identified by "before" or "after" (the change)

        :param game: either a Game instance from self.Games, or "before" or "after"
        '''
        lb_before_change = self.Leaderboard_impact_before_change(unwrap="after")
        lb_after_change = self.Leaderboard_impact_after_change(unwrap="after")

        # We check for the game fter change first (which 99.999% of the time is the same
        # as game before the change anyhow, I mena how often does one enter the game
        # erroneously needing an after edit) becaiuse if the game wasn't changed then
        # it's the after session board after the we want.
        if game == self.game_after_change or game == "after":
            return lb_after_change

        # Only if the game changed, are we interested in checking the before
        # change game as well and if we have that one, we want its leaderboard impact.
        elif game == self.game_before_change or game == "before":
            return lb_before_change
        else:
            return None

    @property
    def Changes(self):
        if self.changes:
            return json.loads(self.changes)
        else:
            return None

    @property
    def Games(self):
        '''
        Returns a tuple of game instances affected by the chnage
        '''
        return (self.game_after_change,) if not self.game_before_change or self.game_after_change == self.game_before_change else (self.game_before_change, self.game_after_change)

    @property
    def submission(self):
        '''
        Returns the submission type that this change log resulted from. This is one of 'create' or 'update' and
        determined implicitly because 'create' log has no game_before_change or leaderboard_impact_before_change
        and the recorded changes (Changes) lacks a 'changes' key.An 'update' submisison will leave all these in
        place. The three conditions should agree.
        '''
        if self.leaderboard_impact_before_change is None:
            return 'create'
        else:
            return 'update'

    @property
    def submission_phrase(self):
        '''
        Same as submission but as a phrase for template use.
        '''
        if self.leaderboard_impact_before_change is None:
            return "a Session submission"
        else:
            return "a Session edit"

    @classmethod
    def create(cls, session=None, change_summary=None, rebuild_log=None):
        '''
        Initial creation of a ChangeLog, with the session provided in its before change state.

        Should be called before a submitted form is saved (so the session is in its before change state).

        All args are optional and can be saved now (at time of creation) or later (at time of update).
        Either way is fine.

        :param session:        A Session object, the change to which we are logging.
        :param change_summary: A JSON log of change_summary, as produced by session.__json__(form_data)
        :param rebuild_log:    An instance of RebuildLog (to link to this ChangeLog)
        '''
        # Instantiate a log
        self = cls()

        if session:
            # The change is an edit to an existing session
            self.session = session

            self.game_before_change = session.game
            # Saves in LB_STRUCTURE. game_wrapped_session_wrapped_player_list with LB_PLAYER_LIST_STYLE.data
            self.leaderboard_impact_before_change = json.dumps(session.leaderboard_impact(LB_PLAYER_LIST_STYLE.data), cls=DjangoJSONEncoder)
        else:
            # The change is a session submission (no session object exists yet, if it's created then self.update() can add it)
            pass

        if isinstance(change_summary, str):
            self.changes = change_summary
            changes = json.loads(change_summary).get("changes", [])
            self.has_impact = 'leaderboard' in changes

        if isinstance(rebuild_log, RebuildLog):
            self.rebuild_log = rebuild_log

        # Return the instance
        return self

    def update(self, session=None, change_summary=None, rebuild_log=None):
        '''
        Update an existing ChangeLog with the after change states.

        Should be called after a submitted form is saved.

        Ideally before it is committed but it matters not the ChangeLog stands
        either way as long as it is saved in the same transaction as the submitted
        form and so commits or rolls back in unison with that save.

        change_summary and rebuild_log are optional and can be saved now (at time of
        update) or earlier (at time of creation). Either way is fine.

        :param session:        A Session object, the change to which we are logging.
        :param change_summary: A JSON log of change_summary, as produced by session.__json__(form_data)
        :param rebuild_log:    An instance of RebuildLog (to link to this ChangeLog)
        '''

        # session need not be supplied if it was at creation time, conversely if it was not
        # Generally if logging a session submission (Create) then we expect to receive it now
        # and if logging a session edit (Update) then we should have the session already (supplied to create() above)
        if session:
            if self.session:
                if not session == self.session:
                    raise ValueError("Attempt to update ChangeLog with session different to the one it was created with.")
            else:
                self.session = session
        else:
            if self.session:
                session = self.session
            else:
                raise ValueError("Attempt to update ChangeLog with no related session.")

        self.game_after_change = session.game
        # Saves in LB_STRUCTURE. game_wrapped_session_wrapped_player_list with LB_PLAYER_LIST_STYLE.data
        self.leaderboard_impact_after_change = json.dumps(session.leaderboard_impact(LB_PLAYER_LIST_STYLE.data), cls=DjangoJSONEncoder)

        if isinstance(change_summary, str):
            self.changes = change_summary
            changes = json.loads(change_summary).get("changes", [])
            self.has_impact = 'leaderboard' in changes

        if isinstance(rebuild_log, RebuildLog):
            self.rebuild_log = rebuild_log

    @classmethod
    def clear(cls):
        '''
        Deletes all logs (use with prudence)
        '''
        cls.objects.all().delete()

    class Meta(AdminModel.Meta):
        verbose_name = "Change Log"
        verbose_name_plural = "Change Logs"


class RebuildLog(AdminModel):
    '''
    A log of rating rebuilds.

    Kept for two reasons:

    1) Performance measure. Rebuild can be slow and we'd like to know how slow.
    2) Security. To see who rebuilt what when

    Unlike change logs these should be persisted

    When we make any changes to any recorded game Session that is NOT the latest game session (for
    that game and all the players playing in that game session) then it has an impact on the
    leaderboards for that game that is distinct from it's own immediate impact. To clarify:

    When any session is changed it has an immediate impact which is how it alters the leaderboard
    from the immediately prior played session of that game.

    If there are future sessions relative to the session just changed then it also has an impact on
    the current leaderboard. The immediate impact above is not the current leaderboard (because
    other session of that game are in its future) and so the impact on the current leaderboard is
    also useful to see.

    This is true whether a session is added, or altered (in any one of many ratings impacting
    ways: players change, ranks change, game changes etc)or deleted.

    We'd like to show these impacts for any edit before they are committed.

    The current leaderboard impacts are tricky as the current leaderboards could be changing
    while we're reviewing our commit for example (other user submitting results).
    '''

    # AdminModel provides created_by and created_on that record who performed the rebuild when.

    ratings = models.PositiveIntegerField('Number of Ratings Built')
    duration = models.DurationField('Duration of Rebuild', null=True)

    # Record what triggered this rating rebuild. the sessin and reason can provide supporting detail.
    trigger = models.PositiveSmallIntegerField(choices=RATING_REBUILD_TRIGGER.choices.value, default=RATING_REBUILD_TRIGGER.user_request.value, blank=False)

    # The session that triggered the rebuild (if any)
    # Note if any change_logs exist they also identify a session.
    # Note: for the SESSION_DELETE trigger clearly the session no longer exists and cannot be identified (unless we keep trash)
    session = models.ForeignKey('Session', verbose_name='Session', related_name='rebuild_logs', null=True, blank=True, on_delete=models.SET_NULL)
    reason = models.TextField('Reason for Rebuild')

    # A record of the arguments of the rebuild request. These can be null. See Rating.rebuild() which
    # can rebuild all the ratings, or all the ratings for a specific game, or all the ratings from
    # a given time, or the ratings from a given time for a specific game or for a specific list of sessions.
    game = models.ForeignKey('Game', null=True, blank=True, related_name='rating_rebuild_requests', on_delete=models.CASCADE)  # If a game is deleted and this was a game specific log, we can delete it
    date_time_from = models.DateTimeField('Game', null=True, blank=True)
    sessions = models.ManyToManyField('Session', blank=True, related_name='rating_rebuild_requests')

    # We'd like to store JSON leaderboard impact of the rebuild. As the rebuild can cover the whole database this
    # can be large beyond simple database storage, and so we should use fileystem storage!
    rebuild_log_dir = "logs/rating_rebuilds"
    leaderboards_before_rebuild = RelativeFilePathField(path=rebuild_log_dir, null=True, blank=True)
    leaderboards_after_rebuild = RelativeFilePathField(path=rebuild_log_dir, null=True, blank=True)

    @property
    def leaderboards_before(self) -> dict:
        log_file = os.path.join(settings.BASE_DIR, self.leaderboards_before_rebuild)
        try:
            with open(log_file, 'r') as f:
                leaderboards = json.load(f)
        except:
            leaderboards = {}

        return pythonify(leaderboards)

    @property
    def leaderboards_after(self) -> dict:
        log_file = os.path.join(settings.BASE_DIR, self.leaderboards_after_rebuild)
        try:
            with open(log_file, 'r') as f:
                leaderboards = json.load(f)
        except:
            leaderboards = {}

        return pythonify(leaderboards)

    @property
    def games(self):
        '''
        Returns a tuple of game PKs affected by the rebuild
        '''
        return tuple(self.leaderboards_before.keys())

    @property
    def Games(self):
        '''
        Returns a tuple of game instances affected by the rebuild
        '''
        Game = apps.get_model(APP, "Game")
        return tuple([safe_get(Game, pk) for pk in self.games])

    @property
    def player_rating_impact(self) -> dict:
        '''
        Returns a dict of dicts keyed on game then player (whose ratings were affected by by this rebuild).
        '''
        Player = apps.get_model(APP, "Player")

        # Game.pk keyed dicts of player lists in data style
        before = self.leaderboards_before
        after = self.leaderboards_after

        deltas = {}
        for g in self.Games:
            deltas[g] = {}
            old = player_ratings(before[g.pk], structure=LB_STRUCTURE.player_list, style=LB_PLAYER_LIST_STYLE.data)
            new = player_ratings(after[g.pk], structure=LB_STRUCTURE.player_list, style=LB_PLAYER_LIST_STYLE.data)

            for p in old:
                if not new[p] == old[p]:
                    delta = new[p] - old[p]
                    P = safe_get(Player, p)
                    deltas[g][P] = delta

        return deltas

    @property
    def player_ranking_impact(self) -> dict:
        '''
        Returns a dict of dicts keyed on game then player (whose rankings were affected by by this rebuild).
        '''
        Player = apps.get_model(APP, "Player")

        # Game.pk keyed dicts of player lists in data style
        before = self.leaderboards_before
        after = self.leaderboards_after

        deltas = {}
        for g in self.Games:
            deltas[g] = {}
            old = player_rankings(before[g.pk], structure=LB_STRUCTURE.player_list, style=LB_PLAYER_LIST_STYLE.data)
            new = player_rankings(after[g.pk], structure=LB_STRUCTURE.player_list, style=LB_PLAYER_LIST_STYLE.data)

            for p in old:
                if not new[p] == old[p]:
                    delta = new[p] - old[p]
                    P = safe_get(Player, p)
                    deltas[g][P] = delta

        return deltas

    def save_leaderboards(self, games, context):
        '''
        Saves leaderboards (in the "data" style) to a disk file and points the context appropriate FileField to it.

        :param games:    A set or list of one or more games
        :param context:  "before" or "after"
        '''
        Rating = apps.get_model(APP, "Rating")

        if not context in ["before", "after"]:
            raise ValueError(f"RebuildLog.save_leaderboards() context must be 'before' or 'after' but '{context}' was provided.")

        leaderboards = Rating.leaderboards(games, style=LB_PLAYER_LIST_STYLE.data)  # dict of boards keyed on game.pk
        content = json.dumps(leaderboards, indent='\t', cls=DjangoJSONEncoder)

        abs_directory = os.path.join(settings.BASE_DIR, self.rebuild_log_dir)
        filename = f"{self.created_on_local:%Y-%m-%d-%H-%M-%S}-{self.created_by.username}-{self.pk}-{context}.json"
        abs_filename = os.path.join(abs_directory, filename)
        rel_filename = os.path.join(self.rebuild_log_dir, filename)

        # Ensure the directory exists
        os.makedirs(abs_directory, exist_ok=True)

        with open(abs_filename, 'w') as f:
            f.write(content)

        if context == "before":
            self.leaderboards_before_rebuild = rel_filename
        elif context == "after":
            self.leaderboards_after_rebuild = rel_filename

    def leaderboard_before(self, game, wrap=True):
        '''
        Returns the leaderboard for a game as it was before this Rebuild (which was logged).

        Returns LB_STRUCTURE.game_wrapped_player_list with LB_PLAYER_LIST_STYLE.rich
        or LB_STRUCTURE.player_list with LB_PLAYER_LIST_STYLE.data.

        :param game: an instance of Game
        :param wrap: If true, a game wrapped rich player list, else a naked data player list
        '''
        leaderboards = self.leaderboards_before  # dict keyed on game.pk
        player_list = tuple(leaderboards.get(game.pk, []))

        if player_list:
            if wrap:
                structure = LB_STRUCTURE.player_list
                style = LB_PLAYER_LIST_STYLE.rich
                rich_player_list = restyle_leaderboard(player_list, structure=structure, style=style)
                wrapped_game_board = game.wrapped_leaderboard(rich_player_list)
                return immutable(wrapped_game_board)
            else:
                return immutable(player_list)
        else:
            return None

    def leaderboard_after(self, game, wrap=True):
        '''
        Returns the leaderboard for a game as it was after this Rebuild (which was logged).

        Returns LB_STRUCTURE.game_wrapped_player_list with LB_PLAYER_LIST_STYLE.rich
        or LB_STRUCTURE.player_list with LB_PLAYER_LIST_STYLE.data.

        :param game: an instance of Game
        :param wrap: If true, a game wrapped rich player list, else a naked data player list
        '''
        leaderboards = self.leaderboards_after  # dict keyed on game.pk
        player_list = leaderboards.get(game.pk, [])

        if player_list:
            if wrap:
                structure = LB_STRUCTURE.player_list
                style = LB_PLAYER_LIST_STYLE.rich
                rich_player_list = restyle_leaderboard(player_list, structure=structure, style=style)
                wrapped_game_board = game.wrapped_leaderboard(rich_player_list)
                return immutable(wrapped_game_board)
            else:
                return immutable(player_list)
        else:
            return None

    def leaderboard_impact(self, game):
        '''
        Returns leaderboard_after and leaderboard_before as two boards under one game wrapper.

        :param game: an instance of Game
        '''
        after = self.leaderboards_after
        before = self.leaderboards_before

        if after and before:
            after_board = tuple(after.get(game.pk, []))
            before_board = tuple(before.get(game.pk, []))

            structure = LB_STRUCTURE.player_list
            style = LB_PLAYER_LIST_STYLE.rich
            rich_after = restyle_leaderboard(after_board, structure=structure, style=style)
            rich_before = restyle_leaderboard(before_board, structure, style=style)
            rich_after = augment_with_deltas(rich_after, rich_before, structure=structure)

            return game.wrapped_leaderboard([rich_after, rich_before], snap=True)
        else:
            return None

    @property
    def leaderboards_impact(self) -> dict:
        '''
        Returns a Game PK keyed dict of leaderboard impacts (of the rebuild)
        '''
        impacts = {}
        for game in self.Games:
            impacts[game.pk] = self.leaderboard_impact(game)
        return impacts

    @classmethod
    def clear(cls):
        '''
        Deletes all logs (use with prudence)
        '''
        cls.objects.all().delete()

    class Meta(AdminModel.Meta):
        verbose_name = "Rebuild Log"
        verbose_name_plural = "Rebuild Logs"

