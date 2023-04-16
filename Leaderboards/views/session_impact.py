#===============================================================================
# A session impact view
#===============================================================================
from django.conf import settings
from django.urls import reverse_lazy
from django.core.exceptions import ObjectDoesNotExist
from django.http.response import HttpResponseRedirect

from django_rich_views.util import class_from_string
from django_rich_views.datetime import time_str
from django_rich_views.render import rich_render

from ..models import ChangeLog, RebuildLog, RATING_REBUILD_TRIGGER
from ..leaderboards.style import restyle_leaderboard
from ..leaderboards.enums import LB_PLAYER_LIST_STYLE, LB_STRUCTURE
from ..leaderboards.util import pk_keys
from ..leaderboards import augment_with_deltas, leaderboard_changed

from Site.logutils import log


def view_Impact(request, model, pk):
    '''
    A view to show the impact of submitting a session.

    Use cases:
        Submission feedback for:
            A session has been added and no rating rebuild was triggered
            A session was added and a rating rebuild was triggered (i.e. it was not the latest session for for that game and all players in it)
            A session was edited and no rating rebuild was triggered
            A session was edited and a rating rebiild was triggered
        A later check on the impact of that session, it may be that:
            The session has one or more change logs (it has been added, and edited, one or more times - such loghs are not guranteed to hang around for ever)
            The session triggered a rebuild one or more times.

            The context of the view can be either:
                based on ther last change log found if any, or
                neutral (not change log found for reference)

    :param request:    A Django request object
    :param model:      The name of a model (only 'session' supported at present)
    :param pk:         The Primary key of the object of model (i.e of the session)
    '''
    m = class_from_string('Leaderboards', model)
    o = m.objects.get(pk=pk)

    if model == "Session":
        # The object is a session
        session = o

        if settings.DEBUG:
            log.debug(f"Impact View for session {session.pk}: {session}")

        # First decide the context of the view. Either a specific change log is specified as a get parameter,
        # or the identified session's latest change log is used if available or none if none are available.
        submission = request.GET.get("submission", None)  # create or update or None
        clog = rlog = None
        changed = request.GET.get("changed", None)  # PK of a ChangeLog

        if changed:
            try:
                clog = ChangeLog.objects.get(pk=int(changed))

                if settings.DEBUG:
                    log.debug(f"\tfetched specified logged change: {clog}")
            except ObjectDoesNotExist:
                clog = None

        if not clog:
            clogs = ChangeLog.objects.filter(session=o)

            if clogs:
                clog = clogs.order_by("-created_on").first()

                if settings.DEBUG:
                    log.debug(f"\tfetched last logged change: {clog}")

        # Find a rebuild log if there is one associated
        if clog:
            if clog.rebuild_log:
                rlog = clog.rebuild_log

                if settings.DEBUG:
                    log.debug(f"\tfetched specified logged rebuild: {rlog}")
            else:
                rlog = None
        else:
            rlogs = RebuildLog.objects.filter(session=o)

            if rlogs:
                rlog = rlogs.order_by("-created_on").first()

                if settings.DEBUG:
                    log.debug(f"\tfetched last logged rebuild: {rlog}")

        # RebuildLogs may be more sticky than ChangeLogs (i.e. expire less frequently)
        # and if so we may have found an rlog and no clog yet, and technically there
        # should not be one (or we'd have found it above!). For completeness in this
        # case we'll check and if debugging report.
        if rlog and not clog:
            clogs = rlog.change_logs.all()
            if clogs:
                clog = clogs.first()

                if settings.DEBUG:
                    log.debug(f"\tUnexpected oddity, found rlog but not clog, yet the rlog identifies {clogs.count()} clog(s) and we're using: {clog}")

        # a changelog stores two impacts each with two snapshots.
        if clog:
            # If a changelog is available they record  two of these
            impact_after_change = clog.Leaderboard_impact_after_change()
            impact_before_change = clog.Leaderboard_impact_before_change()

            # Restyle the saved (.data style) boards to the renderbale (.rich) style
            structure = LB_STRUCTURE.game_wrapped_session_wrapped_player_list
            style = LB_PLAYER_LIST_STYLE.rich
            impact_after_change = restyle_leaderboard(impact_after_change, structure=structure, style=style)
            if impact_before_change:
                impact_before_change = restyle_leaderboard(impact_before_change, structure=structure, style=style)

            # Augment the impacts after with deltas
            impact_after_change = augment_with_deltas(impact_after_change)
            if impact_before_change:
                impact_before_change = augment_with_deltas(impact_before_change)

            # TODO: Consider a way to use session.player_ranking_impact in the report
            # This is a list of players and how their ratings moved +/-
            # There's a before, after, and latest version of this just like leaderboard impacts.
            # Can be derived from the leaderboards and so needs to be a ChangeLog method not a
            # Session method!
        else:
            # An rlog cannot help us here. it contains no record of snapshot before and after
            # (only records of the global leaderboard before and after a rebuild - a different thing altogether).
            # But, lacking a clog we can always report on the current database state.
            impact_after_change = session.leaderboard_impact()
            impact_before_change = None

        # These are properties of the current session and hence relevant only in the post submission feedback scenario where
        # TOOD: Not even that simple.
        #      On a multiuser system it could happen that two edits to a session are submitted one hot on the tail of the other by different people
        #      Submission feedback therefore needs a snapshot of the session that was saved not what is actually now in the database.
        #      We have to pass that in here somehow. That is hard for a complete session object, very hard, and so maybe we do that only for
        #      the session game and datetime (which is all we've used up to this point. Then we don't use methods but compare dates against first
        #      and last in database.
        islatest = session.is_latest
        isfirst = session.is_first

        # impacts contain two leaderboards. But if a diagnostic board is appended they contain 3.
        includes_diagnostic = len(impact_after_change[LB_STRUCTURE.game_data_element.value]) == 3

        # Get the list of games impacted by the change
        games = rlog.Games if rlog else clog.Games if clog else session.game

        if settings.DEBUG:
            log.debug(f"\t{islatest=}, {isfirst=}, {includes_diagnostic=}, {games=}, {rlog=}, {clog=}")

        # If there was a leaderboard rebuild get the before and after boards
        if rlog:
            impact_rebuild = rlog.leaderboards_impact
            player_rating_impacts_of_rebuild = pk_keys(rlog.player_rating_impact)
            player_ranking_impacts_of_rebuild = pk_keys(rlog.player_ranking_impact)

            # Build a PK to name dict for all playes with affected ratings
            players_with_ratings_affected_by_rebuild = {}
            for game, players in rlog.player_rating_impact.items():
                for player in players:
                    players_with_ratings_affected_by_rebuild[player.pk] = player.full_name

            # Build a PK to name dict for all playes with affected rankings
            players_with_rankings_affected_by_rebuild = {}
            for game, players in rlog.player_ranking_impact.items():
                for player in players:
                    players_with_rankings_affected_by_rebuild[player.pk] = player.full_name

        change_log_is_dated = {}
        rebuild_log_is_dated = {}
        latest_game_boards_now = {}
        for game in games:
            # Get the latest leaderboard for this game
            latest_game_boards_now[game.pk] = game.wrapped_leaderboard(style=LB_PLAYER_LIST_STYLE.rich)

            reference = game.leaderboard(style=LB_PLAYER_LIST_STYLE.data)

            if clog and game in clog.Games:
                # Compare to data style player lists to see if the leaderboard after the session
                # in this change is the same as the current latest leaderboard. If it isn't then
                # we're looking at a dated rebuild, as in stuff has happened since it happened.
                # Not dated is for the feedback immediately after a rebuild, before it's committed!
                change_log_is_dated[game.pk] = clog.leaderboard_after(game) != reference

            if rlog:
                # Compare to data style player lists to see if the leaderboard after this rebuild
                # is the same as the current latest leaderboards. If it isn't then we're looking
                # at a dated rebuild, as in stuff has happened since it happened. Not dated is
                # for the feedback immediately after a rebuild, before it's committed!
                rebuild_log_is_dated[game.pk] = leaderboard_changed(rlog.leaderboard_after(game, wrap=False), reference)

        c = {"model": m,
             "model_name": model,
             "model_name_plural": m._meta.verbose_name_plural,
             "object_id": pk,
             "date_time": session.date_time_local,  # Time of the edited session
             "submission": submission,
             "is_latest": islatest,  # The edited/submitted session is the latest in that game
             "is_first": isfirst,  # The edited/submitted session is the first in that game
             "game": session.game,
             "games": games,
             "latest_game_boards_now": latest_game_boards_now,
             }

        if clog:
            c.update({"change_log": clog,
                      "change_date_time": time_str(clog.created_on),
                      "change_log_is_dated": change_log_is_dated,  # The current leaderboard after a change is NOT the current leaderboard (it has changed since)
                      "changes": clog.Changes.get("changes", {}),
                      "lb_impact_after_change": impact_after_change,
                      "lb_impact_before_change": impact_before_change,
                      "includes_diagnostic": includes_diagnostic  # A diagnostic board is included in lb_impact_after_change as a third board.
                      })

        if rlog:
            c.update({"rebuild_log": rlog,
                      "rebuild_date_time": time_str(rlog.created_on),
                      "rebuild_log_is_dated": rebuild_log_is_dated,  # The current leaderboard after a rebuild is NOT the current leaderboard (it has changed since)
                      "rebuild_trigger": RATING_REBUILD_TRIGGER.labels.value[rlog.trigger],
                      "lb_impact_rebuild": impact_rebuild,
                      "player_rating_impacts_of_rebuild": player_rating_impacts_of_rebuild,
                      "player_ranking_impacts_of_rebuild": player_ranking_impacts_of_rebuild,
                      "players_with_ratings_affected_by_rebuild": players_with_ratings_affected_by_rebuild,
                      "players_with_rankings_affected_by_rebuild": players_with_rankings_affected_by_rebuild,
                      })

        return rich_render(request, 'views/session_impact.html', context=c)
    else:
        return HttpResponseRedirect(reverse_lazy('view', kwargs={'model':model, 'pk':pk}))

