#===============================================================================
# The leaderboards view
#
# The main reason the site exists at all ;-)
#===============================================================================
import pytz, json

from dal import autocomplete

from django.conf import settings
from django.utils import timezone
from django.utils.formats import localize
from django.utils.timezone import localtime
from django.http.response import HttpResponse
from django.core.serializers.json import DjangoJSONEncoder

from django_rich_views.context import add_rich_context, add_timezone_context, add_debug_context
from django_rich_views.datetime import datetime_format_python_to_PHP
from django_rich_views.render import rich_render

from .widgets import html_selector

from ..models import Player, Game, League, ALL_LEAGUES, ALL_PLAYERS, ALL_GAMES
from ..models.leaderboards import Leaderboard_Cache # import directly for PyDev
from ..leaderboards.options import leaderboard_options
from ..leaderboards.enums import LB_STRUCTURE, LB_PLAYER_LIST_STYLE, NameSelections, LinkSelections
from ..leaderboards.style import restyle_leaderboard
from ..leaderboards.util import immutable
from ..leaderboards import augment_with_deltas

from Site.logutils import log


def view_Leaderboards(request):
    '''
    The raison d'etre of the whole site, this view presents the leaderboards.
    '''
    # Fetch the leaderboards
    # We always request raw (so it's not JSON but Python data
    leaderboards = ajax_Leaderboards(request, as_list=True)

    session_filter = request.session.get('filter', {})
    tz = pytz.timezone(request.session.get("timezone", "UTC"))
    lo = leaderboard_options(request.GET, session_filter, tz)
    default = leaderboard_options(ufilter=session_filter)

    # Apply the selection options (intelligent selectors based on leaderboards content)
    lo.apply_selection_options(leaderboards)

    (title, subtitle) = lo.titles()

    # selectthe widget defaults
    leagues = lo.game_leagues if lo.game_leagues else request.session.get('filter', {}).get('league', [])
    players = lo.game_players if lo.game_players else lo.players
    games = lo.games

    # Get the preferred league id and lable
    pl_id = request.session.get("preferred_league", 0)

    if pl_id:
        try:
            pl_lbl = League.objects.values_list('name', flat=True).get(pk=pl_id)
        except League.DoesNotExist:
            pl_lbl = ""
            pl_id = 0
    else:
        pl_lbl = ""

    c = {'title': title,
         'subtitle': subtitle,

         # For use in Javascript
         'options': json.dumps(lo.as_dict()),
         'defaults': json.dumps(default.as_dict()),
         'leaderboards': json.dumps(leaderboards, cls=DjangoJSONEncoder),

         # For use in templates
         'leaderboard_options': lo,

         # Dicts for dropdowns
         'name_selections': NameSelections,
         'link_selections': LinkSelections,

         # Widgets to use in the form
         'dal_media': autocomplete.Select2().media,
         'widget_leagues': html_selector(League, "leagues", leagues, ALL_LEAGUES, multi=True),
         'widget_players': html_selector(Player, "players", players, ALL_PLAYERS, multi=True),
         'widget_games': html_selector(Game, "games", games, ALL_GAMES, multi=True),

         # Time and timezone info
         'now': timezone.now(),
         'default_datetime_input_format': datetime_format_python_to_PHP(settings.DATETIME_INPUT_FORMATS[0]),

         # The preferred league if any
         'preferred_league': [pl_id, pl_lbl],

         # Debug mode
         'debug_mode': request.session.get("debug_mode", False)
         }

    add_rich_context(request, c)
    add_timezone_context(request, c)
    add_debug_context(request, c)

    return rich_render(request, 'views/leaderboards.html', context=c)


def ajax_Leaderboards(request, as_list=False, include_baseline=True):
    '''
    A view that returns a JSON string representing requested leaderboards.

    This is used with as_list=True as well by view_Leaderboards to get the leaderboard data,
    not JSON encoded.

    Should only validly be called from view_Leaderboards when a view is rendered
    or as an AJAX call when requesting a leaderboard refresh because the player name
    presentation for example has changed.

    Caution: This does not have any way of adjusting the context that the original
    view received, so any changes to leaderboard content that warrant an update to
    the view context (for example to display the nature of a filter) should be coming
    through view_Leaderboards (which delivers context to the page).

    The returned leaderboards are in the following rather general structure of
    lists within lists. Some are tuples in the Python which when JSONified for
    the template become lists (arrays) in Javascript. This data structure is central
    to interaction with the front-end template for leaderboard rendering.

    Tier1: A list of four value tuples (game.pk, game.BGGid, game.name, Tier2)
           One tuple per game in the leaderboard presentation that

    Tier2: A list of five value tuples (date_time, plays[game], sessions[game], session_detail, Tier3)
           One tuple for each leaderboard snapshot for that game, being basically session details

    Tier3: A list of six value tuples (player.pk, player.BGGname, player.name, rating.trueskill_eta, rating.plays, rating.victories)
           One tuple per player on that leaderboard

    Tier1 is the header for a particular game

    Tier2 is a list of leaderboard snapshots as at the date_time. In the default rendering and standard
    view, this should be a list with one entry, and date_time of the last play as the timestamp. That
    would indicate a structure that presents the leaderboards for now. These could be filtered of course
    (be a subset of all leaderboards in the database) by whatever filtering the view otherwise supports.
    The play count and session count for that game up to that time are in this tuple too.

    Tier3 is the leaderboard for that game, a list of players with their trueskill ratings in rank order.

    Links to games and players in the leaderboard are built in the template, wrapping a player name in
    a link to nothing or a URL based on player.pk or player.BGGname as per the request.


    2023 April
    Timing trials with the global cache loading all 133 current leaderboards, page load time for:
        http://127.0.0.1:8000/leaderboards?no_defaults
        No cache debugging: 98s
        No cache no debugging: 86s
        Cache debugging: 23s
        Cache no debugging: 17s
    Tested using runserver on the development machine. Might perform slightly better in production.
    '''

    # Fetch the options submitted (and the defaults)
    session_filter = request.session.get('filter', {})
    tz = pytz.timezone(request.session.get("timezone", "UTC"))
    lo = leaderboard_options(request.GET, session_filter, tz)

    # Create a page title, based on the leaderboard options (lo).
    (title, subtitle) = lo.titles()

    use_cache = settings.USE_LEADERBOARD_CACHE and not lo.ignore_cache
    # Use the session as a leaderboard cache
    # Else use the Leaderboard_Cache model
    # The session support is legacy, global model based support was added later.
    # it is preferred as it means the first load of a leaderboard view benefits
    # from cache whcih was not the case when using session to cche them.
    use_session_cache = use_cache and settings.USE_SESSION_FOR_LEADERBOARD_CACHE

    # The Session based Leaderboard Cache - delete if not being used
    if not use_session_cache and "leaderboard_cache" in request.session:
        del request.session["leaderboard_cache"]

    # If the Session based cached exists it contains all boards that have been displayed once)
    # We fetch the cahce up front.
    if use_session_cache:
        # Get the cache if available
        #
        # It should contain leaderboard snapshots already produced.
        # Each snapshot is uniquely identified by the session.pk
        # that it belongs to. And so we can store them in cache in
        # a dict keyed on session.pk
        lb_cache = request.session.get("leaderboard_cache", {}) if not lo.ignore_cache else {}

    # Fetch the queryset of games that these options specify
    # This is lazy and should not have caused a database hit just return an unevaluated queryset
    # Note: this respect the last event of n days request by constraining to games played
    #       in the specified time frame and at the same location.
    games = lo.games_queryset()

    #######################################################################################################
    # # FOR ALL THE GAMES WE SELECTED build a leaderboard (with any associated snapshots)
    #######################################################################################################
    if settings.DEBUG:
        log.debug(f"Preparing leaderboards for {len(games)} games.")

    leaderboards = []
    for game in games:
        if settings.DEBUG:
            log.debug(f"Preparing leaderboard for: {game}")

        # FIXME: Here is a sweet spot. Some or all sessions are available in the
        #        cache already. We need the session only for:
        #
        #  1) it's datetime - cheap
        #  2) to build the three headers
        #     a) session player list     - cheap
        #     b) analysis pre            - expensive
        #     c) analysis post           - expensive
        #
        # We want to know if the session is already in a cached snapshot.

        # Note: the snapshot query intentionally does not constrain sessions to the same
        # location as does the game query. Once we have the games that were played at
        # the event, we're happy to include all sessions during the event regardless of
        # where. The reason being that we want to see evolution of the leaderboards during
        # the event even if some people outside of the event are playing it and impacting
        # the board.
        (boards, has_reference, has_baseline) = lo.snapshot_queryset(game, include_baseline=include_baseline)

        # boards are Session instances (the board after a session, or alternately the session played to produce this board)
        if boards:
            #######################################################################################################
            # # BUILD EACH SNAPSHOT BOARD - from the sessions we recorded in "boards"
            #######################################################################################################
            #
            # From the list of boards (sessions) for this game build Tier2 and Tier 3 in the returned structure
            # now. That is assemble the actualy leaderbards after each of the collected sessions.

            if settings.DEBUG:
                log.debug(f"\tPreparing {len(boards)} boards/snapshots.")

            # We want to build a list of snapshots to add to the leaderboards list
            snapshots = []

            # We keep a baseline snapshot (the rpevious one) for augfmenting snapshots with
            # (it adds a rank_delat entry, change in rank from the baseline)
            baseline = None

            # For each board/snapshot of this game ...
            # In temporal order so we can construct the "previous rank"
            # element on the fly, but we're reverse it back when we add the
            # collected snapshots to the leaderboards list.
            for board in reversed(boards):
                # If as_at is now, the first time should be the last session time for the game
                # and thus should translate to the same as what's in the Rating model.
                #
                # TODO: Perform an integrity check around that and indeed if it's an ordinary
                #       leaderboard presentation check on performance between asat=time (which
                #       reads Performance) and asat=None (which reads Rating).
                #
                # TODO: Consider if performance here improves with a prefetch or such noting that
                #       game.play_counts and game.session_list might run faster with one query rather
                #       than two.

                if settings.DEBUG:
                    log.debug(f"\tBoard/Snapshot for session {board.id} at {localize(localtime(board.date_time))}.")

                if use_cache:
                    ##################################################################################################
                    # Caching support
                    if use_session_cache:
                        # Session based cache:
                        # First fetch the global (unfiltered) snapshot for this board/session
                        if board.pk in lb_cache:
                            full_snapshot = lb_cache[board.pk]
                            if settings.DEBUG:
                                log.debug(f"\t\tFound it in cache!")
                        else:
                            if settings.DEBUG:
                                log.debug(f"\t\tBuilding it!")
                            full_snapshot = board.leaderboard_snapshot(style=LB_PLAYER_LIST_STYLE.data)
                            if full_snapshot:
                                lb_cache[board.pk] = full_snapshot
                    else:
                        # Global cache:
                        try:
                            full_snapshot = immutable(Leaderboard_Cache.objects.get(session=board).board)
                            # TODO: This should now be de-temlated and richified
                            if settings.DEBUG:
                                log.debug(f"\t\tFound it in cache!")
                        except Leaderboard_Cache.DoesNotExist:
                            if settings.DEBUG:
                                log.debug(f"\t\tBuilding it!")
                            full_snapshot = board.leaderboard_snapshot(style=LB_PLAYER_LIST_STYLE.data)
                            if full_snapshot:
                                lb_cache = Leaderboard_Cache(session=board, board=full_snapshot)
                                lb_cache.save()
                else:
                    if settings.DEBUG:
                        log.debug(f"\t\tBuilding it! (caching is disabled)")
                    full_snapshot = board.leaderboard_snapshot(style=LB_PLAYER_LIST_STYLE.data)

                # Restyle the full snapshot to LB_PLAYER_LIST_STYLE.rich for rendering
                # Client side know the appropriate name expansion for a template.
                #    it knows of (and is sent) the
                #        Leaderboards.leaderboards.options.leaderboard_options.names
                #    which can take on one of the values from:
                #        Leaderboards.leaderboards.enums.NameSelections
                # TODO: confirm this arrives in templated not flexi name_styling. Should write a test and assert>
                full_snapshot = restyle_leaderboard(full_snapshot, structure=LB_STRUCTURE.session_wrapped_player_list, style=LB_PLAYER_LIST_STYLE.rich)

                if settings.DEBUG:
                    log.debug(f"\tGot the full board/snapshot. It has {len(full_snapshot[LB_STRUCTURE.session_data_element.value])} players on it.")

                # Then filter and annotate it in context of lo
                if full_snapshot:
                    # Augmment the snapshot with the delta from baseline if we have one
                    if baseline:
                        full_snapshot = augment_with_deltas(full_snapshot, baseline, LB_STRUCTURE.session_wrapped_player_list)

                    snapshot = lo.apply(full_snapshot)
                    lbf = snapshot[LB_STRUCTURE.session_data_element.value]  # A player-filtered version of leaderboard

                    if settings.DEBUG:
                        log.debug(f"\tGot the filtered/annotated board/snapshot. It has {len(snapshot[8])} players on it.")

                    # Counts supplied in the full_snapshot are global and we want to constrain them to
                    # the leagues in question.
                    #
                    # We have three options:
                    #
                    # in-league:    show only snapshots played in the specified leagues
                    # cross-league  show snapshots played by any players in the selected leagues
                    # global        show all snapshots
                    if lo.leagues:
                        if lo.show_cross_league_snaps:
                            counts = game.play_counts(leagues=lo.leagues, asat=board.date_time, broad=True)
                        else:
                            counts = game.play_counts(leagues=lo.leagues, asat=board.date_time)

                        plays = counts['total']
                        sessions = counts['sessions']
                    else:
                        counts = game.play_counts(asat=board.date_time)
                        plays = counts['total']
                        sessions = counts['sessions']

                    # snapshot 0 and 1 are the session PK and localized time
                    # snapshot 2 and 3 are the counts we updated with lo.league sensitivity
                    # snapshot 4, 5, 6 and 7 are session players, HTML header and HTML analyis pre and post respectively
                    # snapshot 8 is the leaderboard (a tuple of player tuples)
                    # The HTML header and analyses use flexi player naming and expect client side to render
                    # appropriately. See Player.name() for flexi naming standards.
                    snapshot = (snapshot[0:2]
                             +(plays, sessions)
                             +snapshot[4:8]
                             +(lbf,))

                    # Store the baseline for next iteration (for delta augmentation)
                    baseline = full_snapshot

                    snapshots.append(snapshot)

            # For this game we now have all the snapshots and we can save a game tuple
            # to the leaderboards list. We must have at least one snapshot, because we
            # ignored all games with 0 recorded sessions already in buiulding our list
            # games. So if we don't have any something really bizarre has happened/
            assert len(snapshots) > 0, "Internal error: Game was in list for which no leaderboard snapshot was found. It should not have been in the list."

            # We reverse the snapshots back to newest first oldest last
            snapshots.reverse()

            # Then build the game tuple with all its snapshots
            leaderboards.append(game.wrapped_leaderboard(snapshots, snap=True, has_reference=has_reference, has_baseline=has_baseline))

    if use_session_cache:
        request.session["leaderboard_cache"] = lb_cache

    if settings.DEBUG:
        log.debug(f"Supplying {len(leaderboards)} leaderboards as {'a python object' if as_list else 'as a JSON string'}.")

    # Last, but not least, Apply the selection options
    lo.apply_selection_options(leaderboards)

    # as_list is asked for on a standard page load, when a true AJAX request is underway it's false.
    return leaderboards if as_list else HttpResponse(json.dumps((title, subtitle, lo.as_dict(), leaderboards), cls=DjangoJSONEncoder))
