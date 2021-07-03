# Python imports
import enum, json, numbers

from collections import OrderedDict
from datetime import datetime, timedelta

# Django imports
from django.conf import settings
from django.db.models import Q, ExpressionWrapper, DateTimeField, IntegerField, Count, Subquery, OuterRef, F  # , Window
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.serializers.json import DjangoJSONEncoder
# from django.db.models.functions import Lag
from django.utils.formats import localize
from django.utils.timezone import localtime
# from django.db.models.base import ModelBase
from django.db.models import Model

if settings.DEBUG:
    from django.db import connection

# Django generic view extension imports
from django_generic_view_extensions.datetime import fix_time_zone, UTC
from django_generic_view_extensions.queryset import top, get_SQL
from django_generic_view_extensions.datetime import decodeDateTime

# Local imports
# models imports from this module. To avoid a circular import error we need to import models into its own namespace.
# which means accessing a model is then models.Model
from CoGs.logging import log
from . import models

# Some useful enums to use in the options. Really just a way of encapsulating related
# types so we can use them in templates to pupulate selectors and receive them from
# requests in an orderly way.
#
# They are defined as lists of 2-tuples. The first value in each tuple is the name
# of the enum and typically the value that is used in URLs and in GET and POST
# submissions. The second value is the plain text label that can be used on selector
# on a web page if needed, a more verbose explanation of the selection.
NameSelections = OrderedDict((("nick", "nickname"),
                              ("full", "full name"),
                              ("complete", "full name (nickname)")))

LinkSelections = OrderedDict((("none", "nowhere"),
                              ("CoGs", "CoGs Leaderboard Space"),
                              ("BGG", "boardgamegeek.com")))

# We make enums out of the lists of the lists of 2-tuples above for use in code.
NameSelection = enum.Enum("NameSelection", NameSelections)
LinkSelection = enum.Enum("LinkSelection", LinkSelections)


#===============================================================================
# A structured approach to presenting leaderboards
#
# The central purpose of all these models is the storing of data for and
# presentation of leaderboards.
#===============================================================================
class LB_PLAYER_LIST_STYLE(enum.Enum):
    none = 0  # An ordered list of names
    data = 1  # An ordered list of tuples (playerid, rating, mu, sigma, plays, wins) - For a data store (can recreate any other style from this)
    rating = 2  # An ordered list of tuples (name, rating)
    ratings = 3  # An ordered list of tuples (name, rating, mu, sigma)
    simple = 4  # An ordered list of tuples (name, rating, mu, sigma, plays, wins)
    rich = 5  # simple plus lots more player info for rendering rich leaderboards (name in all formats, league ids for the player)


class LB_STRUCTURE(enum.Enum):
    '''
    Leaderboards are passed around in a few different structures. We can use this enum to describe a given
    structure to inform a function (that supports it) where to find the juice, the player list.
    '''
    player_list = 0  # A simple list of player tuples
    session_wrapped_player_list = 1  # A session tuple containing an player_list as an element
    game_wrapped_player_list = 2  # A game tuple containing an player_list as an element
    game_wrapped_session_wrapped_player_list = 3  # A session tuple containing an session_wrapped_player_list as an element

    # This is defined by what Game.wrapped_leaderboard() produces
    game_data_element = 7  # In a game wrapper, which element caries the data (either session wrapper, or player_list)

    # This is defined by what Session.leaderboard_snapshot() produces
    session_data_element = 8  # In a session wrapper, which element contains the player_list


# As leaderboards are lists of players, possibly in a session wrapper (list) in a game wrapper (list)
# A couple fo one liners that makes a nested tree of tuples mutable (converts them all to lists)
# and vice versa, so we can lock leadeboards and unlock them explicitly if an edit is targetted.
def mutable(e):
    return list(map(mutable, e)) if isinstance(e, (list, tuple)) else e


def immutable(e):
    return tuple(map(immutable, e)) if isinstance(e, (list, tuple)) else e


def pk_keys(o):

    def pk(x): return x.pk if isinstance(x, Model) else x

    return {pk(k): pk_keys(v) for k, v in o.items()} if isinstance(o, dict) else o


def is_number(s):
    '''
    A simple test on a string to see if it's a number or not, for float values
    notably leaderboard_options.num_days and compare_back_to. Which can both come
    in as float values.
    '''
    try:
        float(s)
        return True
    except ValueError:
        return False


class leaderboard_options:
    '''
    Captures the options that can be made available to and be submitted by a web page when
    requesting leaderboards.

    Three key parts in the class:

    1) Some enum defintions for selectable options. Defined as lists of 2-tuples.
        The lists and the enums built fromt hem are useful in code and the
        context of a Leaderboards page (the lists of 2 tuples for example can
        be used to construct select widgets).

        These are CamelCased

    2) The options themselves. They ar elower case words _ seaprated.

    3) Methods:

        A constructor that can receives a QueryDcit from requst.GET or reuqest.POST
        and build an instance on basis of what is submitted. A default instance if
        none is supplied.

        A JSONifier to supply context with a dict of JSONified options so the options
        can conveniently be used in a template.
    '''

    # Some sets of options categorize with the main aim that we establish which ones
    # are cache safe and which ones not and also have a record of the incoming options
    # swe wish to support and recognize.
    #
    # Note: many but not all options are attributes of this class. Some, notably the any/all
    #       options that describe how a list should be handled are not. The list is an attribute,
    #       but the 'enabled' attribute captures the option itself.
    #
    # These options are what we can expect in requests (on URLs via GET requests or in a POST
    # request if supplied to the constructor.

    # Options that we accept that will filter the list of games presented
    # (i.e. define the subset of all games to return)
    game_filters = {'games_ex',  # Exclusively those listed in self.games
                    'games_in',  # Including those listed in self.games
                    'top_games',  # The top (most popular) self.num_games
                    'latest_games',  # The latest self.num_games
                    'game_leagues_any',  # Games played in any of self.game_leagues
                    'game_leagues_all',  # Games played in all of self.game_leagues
                    'game_players_any',  # Games played by any of self.game_players
                    'game_players_all',  # Games played by all of self.game_players
                    'changed_since',  # Games played since self.changed_since
                    'num_days'}  # Games played in the last event of self.num_days

    # Options that we accept that will filter the list of players presented on leaderboards
    # (i.e. define the subset of all players that have played that game)
    player_filters = {'players_ex',  # Exclusively those listed in self.players
                      'players_in',  # Including those listed in self.players
                      'num_players_top',  # The top self.num_players_top players
                      'num_players_above',  # self.num_players_above players above any players selected by self.players_in
                      'num_players_below',  # self.num_players_below players below any players selected by self.players_in
                      'min_plays',  # Players who have played the game at least self.min_plays times
                      'played_since',  # Players who have played the game since self.played_since
                      'player_leagues_any',  # Players in any of self.player_leagues
                      'player_leagues_all'}  # Players in all of self.player_leagues

    # There are multi-select lists boxes that can provide the data for options like games_ex/in,
    # game_leagues_any/all, game_players_any/all, players_ex/in, player_leagues_any/all
    # If the ese contain data, BUT no explicit option using the data is on, we still want to
    # transport the data so that it comes back to a refreshed view and can inform any options that
    # are client side implemented (in Javascript). In short we don't want to lose that data in a
    # submission but we retatain it in a neutral (no filtering) fashion.These can aslo provide fallback
    # reference for any of the afforementioend options which can be URL specified without a list, if the
    # list is provided via one of tehse transporters.
    transport_options = {'games', 'players', 'leagues'}

    # Options that affect the perspective of a leadeboard view.
    # Really only one, what the effective "now" or "current" view is,
    # that we are looking from.
    perspective_options = {'as_at'}

    # Options that influence evolution presentations. These will be historic
    # leaderboards that show how a given leaderboard got to where it is, after
    # each game session recorded for that game which saw a change to the boards.
    evolution_options = {'compare_with', 'compare_back_to'}

    # Options that affect how we render leaderboards on screen
    formatting_options = {'highlight_players', 'highlight_changes', 'highlight_selected', 'names', 'links'}

    # Options influencing what ancillary or extra information we present with a leaderboard
    info_options = {'details', 'analysis_pre', 'analysis_post', 'show_d_rank', 'show_d_rating'}

    # Options impacting the layout of leaderboards on the screen/page
    layout_options = {'cols'}

    # Divide the options into two groups, content and presentation.
    content_options = game_filters \
                    | player_filters \
                    | perspective_options \
                    | evolution_options

    presentation_options = formatting_options \
                         | info_options \
                         | layout_options

    admin_options = {'ignore_cache'}

    # ALL the options, a set against which we can filter incoming requests to
    # weed out all the things that don't matter, or to asses if the request is in
    # fact one that includes any leaderboard options or not.
    all_options = content_options | presentation_options | transport_options | admin_options

    # TODO: consider adding Tourney's now and a search for
    #       games by tourney, so players, leagues and games, tourneys.

    # An option enabler. We want options to have sensible defaults to
    # populate form fields, but aside from their default values the notion
    # of enabling or disabling the option should be presented on a form
    # (checkboxes and raduo buttons) and represented here so that the form
    # can initialise those and also the processor knows which of the options
    # to apply.
    #
    # it is just a set of options, by name, that are enabled, and
    # anything not in list is not enabled.
    #
    # This only applies to the game selectors, the player selectors
    # and the perspective and evolution options.
    #
    # The formatting, extra info, and layout options are not enabled
    # or disabled,they simply are (always in force).
    enabled = {"game_leagues_any", "top_games", "player_leagues_any", "num_players_top"}

    # Because not all options require enabling, only some/many
    # we ckeep a set of enabbleable options internally, which
    # the constructor populates, and the method is_enabled() uses
    # intelligently (to return True always for option that don't
    # need enabling and only if enabled for those that do, which
    # makes checking whether an option is to be applied easy.
    need_enabling = set()

    # Now we define the attributes that back these options up.
    # NOTE: These attributes are not self-standing so to speak but
    #       relate to 'enabled' as well, which turns thes on or off
    #       and/or describes how they are to be used (in the case of
    #       any/all list imperatives.

    # Options that determine which games to list leaderboards for
    # These defaults are used to populate input elements in a form
    # The form should only resybmit them however if they are selected
    # by an accompanying check box.
    games = []  # Restrict to specified Games
    num_games = 6  # List only this many games (most popular ones or latest based on enabled option)
    game_leagues = []  # Restrict to games played by specified Leagues (any or all based on enabled option)
    game_players = []  # Restrict to games played by specified players (any or all based on enabled option)
    changed_since = None  # Show only leaderboards that changed since this date
    num_days = 1  # List only games played in the last num_days long event (also used for snapshot definition)

    # Options that determing which players are listed in the leadrboards
    # These options, like the game selectors, above provide defaults with which to
    # populate input elements in a form, but they should be presented with accompanying
    # checkboxes to select them, and if not selected the option should not be subitted.
    players = []  # A list of players to explicitly display (hide all others - except those, that other options request displayed as well)
    num_players_top = 10  # The number of players at the top of leaderboard to show
    num_players_above = 2  # The number of players above selected players to show on leaderboards
    num_players_below = 2  # The number of players below selected players to show on leaderboards
    min_plays = 2  # The minimum number of times a player has to have played this game to be listed
    played_since = None  # The date since which a player needs to have played this game to be listed
    player_leagues = []  # Restrict to players in specified Leagues

    # A perspective option that asks us to think of "current" not as at now, but as at some other time.
    as_at = None  # Do everything as if it were this time now (pretend it is now as_at)

    # Options that determine which snapshots to present for each selected game (above)
    # A snapshot being the leaderboard immediately after a given session.
    # Only one of these can be respected at a time,
    # compare_back_to is special, it can take one two types of value:
    #    a) a datetime, in which case it encodes a datetime back to which we'd like to have snapshots
    #    b) an integer or float, in which case  it encodes num_days above basically, the length of
    #       the last event looking back from as_at which is used to determine a date_time for the query.
    compare_with = 1  # Compare with this many historic leaderboards
    compare_back_to = None  # Compare all leaderboards back to this date (and the leaderboard that was the latest one then)

    # NOTE: The reamining options are not enabled or disabled they always have a value
    #       i.e. are self enabling.

    # Options for formatting the contents of a given leaderbaords
    highlight_players = True  # Highlight the players that played the last session of this game (the one that produced this leaderboard)
    highlight_changes = True  # Highlight changes between historic snapshots
    highlight_selected = True  # Highlight players selected in game_players above

    names = NameSelection.nick.name  # Render player names like this
    links = LinkSelection.CoGs.name  # Link games and players to this target

    # Options to include extra info in a leaderboard header
    details = False  # Show session details atop each boards (about the session that produced that board)
    analysis_pre = False  # Show the TrueSkill Pre-session analysis
    analysis_post = False  # Show the TrueSkill Post-session analysis
    show_d_rank = False  # Show the rank delta (movement) this session caused
    show_d_rating = False  # Show the rating delta (movement) this session caused
    show_baseline = False  # Show the baseline (if any)

    # Options for laying out leaderboards on screen
    cols = 3  # Display boards in this many columns (ignored when comparing with historic boards)

    # Admin Options
    ignore_cache = False

    # NOT YET IMPLEMENTED
    # Consider: could be a list of players, could be a bool like hightlight_players
    # and use the players list.
    trace = []  # A list of players to draw trace arrows for from snapshot to snapshot

    # A flag back to client to tell it that we made these opts static on request
    made_static = False

    def is_enabled(self, option):
        '''
        A convenient method to check if an option should be applied, returning True
        for those that always apply and the enabled status for those that need enabling.
        '''
        return option in self.enabled if option in self.need_enabling else True

    def __enable__(self, option, true_false):
        '''
        An internal method for conveniently enabling or disabling and option based a supplied boolean,
        an operation we do over and over for many options.
        '''
        # Enable or disable the option as requested by true_false
        if true_false:
            self.enabled.add(option)
        else:
            self.enabled.discard(option)

    def __init__(self, urequest={}, ufilter={}, utz=UTC):
        '''
        Build a leaderboard options instance populated with options from arequest dictionary
        (could be from request.GET or request.POST). If none is specified build with default
        values, i.e.e do nothing here (defaults are specified in attribute declarations above)

        :param urequest: a user request, i.e. a request.GET or request.POST dictionary that
                         contains options.

        :param ufilter: a user filter, i.e request.session.filter dictionary that specifies
                        the session default. Currently only 'league' is used to populate the
                        options with a default league filter based on session preferences.
                        Is extensible.

        :param utz:      the users timezone. Only used to generating date_time strings where
                         needed so that they are in the users timezone when produced.
        '''
        # If we have a options submitted then don't use the default
        # enabled list respect the incoming options instead.

        have_options = False
        for item in urequest:
            if item in self.all_options:
                have_options = True
                break

        # If any options are specified in the request we ignore the defaults that
        # are enabled and start with nothing enabled. We support one special request
        # that does nothing more and nothing less than to force this start with a clean
        # slate: "nodefaults". This is designed so that the inital view loaded has
        # nice defaults, but the AJAX requests to update leaderboards have a way of
        # saying that no options are set! So basically just show us ALL the
        # leaderboards completely! If someon explicitly disables the default options
        # on the web page (that it should display because we prodvide leaderboard_options
        # in the context for page load and in the JSON delivered to AJAX requesters),
        # the page has some way of saying this is not option explicitly, do not use
        # defaults. As soon as one option is specified normally that won't be needed,
        # but if no options are specified, it is needed to start with an empty set of
        # enabled options here.
        if have_options or "no_defaults" in urequest:
            self.enabled = set()

        # A very special case for the two snapshot options. They are not enabled
        # like the filters. There are two, compare_with and compare_back_to only
        # one of which can't should be set. We can only respect one. So if we get
        # on in the request we should anull the other.
        #
        # If both are supplied we need of course to ignore one. Matters not which,
        # but only one can be respected
        if "compare_back_to" in urequest:
            self.compare_with = 0
        elif "compare_with" in urequest:
            self.compare_back_to = None

        # Keeping the same order as the properties above and recommended for
        # form fields and the JS processor of those field ... with the exception
        # of transporters that we collect up front.

        ##################################################################
        # COLLECT TRANSPORTERS
        games = None
        players = None
        leagues = None

        if f'games' in urequest:
            games = urequest[f'games'].split(",")

        if f'players' in urequest:
            players = urequest[f'players'].split(",")

        # TODO check if we can spefic NO league filterig. That is where does preferred league come from?
        preferred_league = ufilter.get('league', None)
        if f'leagues' in urequest:
            leagues = urequest[f'leagues'].split(",")
            if preferred_league and not leagues:
                leagues = [str(preferred_league)]

        ##################################################################
        # GAME FILTERS
        #
        # We start with the Game Selection criteria/filters, namely the
        # the options that determine which games we will present boards
        # for. Each board being a list of players in order with their
        # rankings.

        # A comma separated list of games if submitted flags a request
        # to show leaderboards for those games only (exlusive) or at least
        # those games (inclusive). The option specifies the context and
        # only one of them can be specified at a time with any sense.
        self.need_enabling.add('games_ex')
        self.need_enabling.add('games_in')
        ex_in = None
        game_games = games  # Use the transport option as a fallback.
        for suffix in ("ex", "in"):
            if f'games_{suffix}' in urequest:
                game_games = urequest[f'games_{suffix}'].split(",")

                # Use the transport option "games" if no list provided for games ex/in
                # This enables URLs like
                #    ?games_in=1,2,3
                #    ?games=1,2,3&games_in
                if not game_games:
                    game_games = games

                ex_in = suffix
                break

        # Copy games to self.games if they exist, and enable a filter option if needed.
        if game_games:
            # Validate the games discarding any invalid ones
            self.games = []
            for game in game_games:
                if models.Game.objects.all().filter(pk=game).exists():
                    self.games.append(game)

        # If we found an ex or in option
        if ex_in:
            self.__enable__(f'games_{ex_in}', self.games)

        # In case one or the other was enabled in the defaults above, if we lack any leagues we ensure they are both disabled
        else:
            self.__enable__('game_ex', False)
            self.__enable__('game_in', False)

        # A number of games if submitted request that we list no
        # more than that many games (the top games when sorted by
        # some measure of popularity or the latest play times -
        # ideally within the selected leagues (i.e. global popularity
        # is of no interest to a given league or leagues)
        self.need_enabling.add('top_games')
        self.need_enabling.add('latest_games')
        if 'top_games' in urequest and urequest['top_games'].isdigit():
            self.num_games = int(urequest["top_games"])
            self.__enable__('top_games', self.num_games)
        elif 'latest_games' in urequest and urequest['latest_games'].isdigit():
            self.num_games = int(urequest["latest_games"])
            self.__enable__('latest_games', self.num_games)

        # We can acccept leagues in an any or all form
        self.need_enabling.add('game_leagues_any')
        self.need_enabling.add('game_leagues_all')
        any_all = None
        game_leagues = leagues  # Use the transport option as a fallback.
        for suffix in ("any", "all"):
            if f'game_leagues_{suffix}' in urequest:
                game_leagues = urequest[f'game_leagues_{suffix}'].split(",")

                # Use the transport option "leagues" if no list provided for game_leagues
                # This enables URLs like
                #    ?game_leagues_any=1,2,3
                #    ?leagues=1,2,3&game_leagues_any
                if not game_leagues:
                    game_leagues = leagues

                any_all = suffix
                break

        if game_leagues:
            # Validate the leagues  discarding any invalid ones
            self.game_leagues = []
            for league in game_leagues:
                if models.League.objects.all().filter(pk=league).exists():
                    self.game_leagues.append(league)

        # If we found an any or all option
        if any_all:
            self.__enable__(f'game_leagues_{any_all}', self.game_leagues)

        # In case one or the other was enabled in the defaults above, if we lack any leagues we ensure they are both disabled
        else:
            self.__enable__('game_leagues_any', False)
            self.__enable__('game_leagues_all', False)

        # The filter for players can also arrive in one of two forms
        # and any or all request (both is illegal and one will
        # perforce be be ignored here). With this list we request
        # to see leaderboards for games play by any of the listed
        # players, or those played by all of the listed players.
        self.need_enabling.add('game_players_any')
        self.need_enabling.add('game_players_all')
        any_all = None
        game_players = players  # Use the transport option as a fallback.
        for suffix in ("any", "all"):
            if f'game_players_{suffix}' in urequest:
                game_players = urequest[f'game_players_{suffix}'].split(",")

                # Use the transport option "players" if no list provided for game_players
                # This enables URLs like
                #    ?game_players_any=1,2,3
                #    ?players=1,2,3&game_players_any
                if not game_players:
                    game_players = players

                any_all = suffix
                break

        if game_players:
            # Validate the players discarding any invalid ones
            self.game_players = []
            for player in game_players:
                if models.Player.objects.all().filter(pk=player).exists():
                    self.game_players.append(player)

        # If we found an any or all option
        if any_all:
            self.__enable__(f'game_players_{any_all}', self.game_players)

        # In case one or the other was enabled in the defaults above, if we lack any leagues we ensure they are both disabled
        else:
            self.__enable__('game_players_any', False)
            self.__enable__('game_players_all', False)

        # If a date is submitted (and parses validly) this asks us to list only
        # games that have a recorded play session after that date (exclude games
        # not played since them).
        self.need_enabling.add('changed_since')
        if 'changed_since' in urequest:
            try:
                self.changed_since = decodeDateTime(urequest['changed_since'])
            except:
                self.changed_since = None  # Must be a a Falsey value

            self.__enable__('changed_since', self.changed_since)

        # A request for an event impact presentaton comes in the form
        # of num_days, where num yays flags the length of the event to
        # look for (looknig back from now or as_at). We record it in
        # self.num_days to flag that this is what we want to the processor.
        # Other filters of  course may impact on this and reduce the number
        # of games, which can in fact be handy if say the games of a long and
        # busy games  event are logged and could produce a large number of
        # boards. But for an average games night, probably makes little sense
        # and has little utility.
        self.need_enabling.add('num_days')
        if 'num_days' in urequest and is_number(urequest['num_days']) and not self.changed_since:
            self.num_days = float(urequest["num_days"])
            self.__enable__('num_days', self.num_days)

        ##################################################################
        # PLAYER FILTERS
        #
        # Now we capture the player filters. That is the options that
        # restrict which players we present on the boards.

        # A comma separated list of players if submitted flags a request
        # to show those players only (exlusive) or at least those players
        # (inclusive). The option specifies the context and only one of
        # them can be specified at a time with any sense.
        self.need_enabling.add('players_ex')
        self.need_enabling.add('players_in')
        ex_in = None
        player_players = players  # Use the transport option as a fallback.
        for suffix in ("ex", "in"):
            if f'players_{suffix}' in urequest:
                player_players = urequest[f'players_{suffix}'].split(",")

                # Use the transport option "players" if no list provided for players ex/in
                # This enables URLs like
                #    ?players_in=1,2,3
                #    ?players=1,2,3&players_in
                if not player_players:
                    player_players = players

                ex_in = suffix
                break  # Use only first one if multiple (possibly conflicting) entries are specified

        if player_players:
            # Validate the players discarding any invalid ones
            self.players = []
            for player in player_players:
                if models.Player.objects.all().filter(pk=player).exists():
                    self.players.append(player)

            if ex_in:
                self.__enable__(f'players_{ex_in}', self.players)

        # If "players" is an empty list fall back on the game_players if they
        # were submitted. This enables a URL like:
        #   ?game_players_any=1,2,3&players_ex
        # where the empty players_ex list falls back on 1,2,3
        elif self.game_players:
            # Already validated list of players
            self.players = self.game_players  # game_players_any or _all was already enabled if land here.

        # Then an option to discard all but the top num_players of each board
        # As the starting point. Other options can add players of course, this
        # is not exclusive of other player selecting options.
        self.need_enabling.add('num_players_top')
        if 'num_players_top' in urequest and urequest['num_players_top'].isdigit():
            self.num_players_top = int(urequest["num_players_top"])
            self.__enable__('num_players_top', self.num_players_top)

        # Here we're requesting to provide context to the self.players that
        # are showing on the list. We may want to see a player or two or more
        # above and/or below them.
        self.need_enabling.add('num_players_above')
        if 'num_players_above' in urequest and urequest['num_players_above'].isdigit():
            self.num_players_above = int(urequest["num_players_above"])
            self.__enable__('num_players_above', self.num_players_above)

        self.need_enabling.add('num_players_below')
        if 'num_players_below' in urequest and urequest['num_players_below'].isdigit():
            self.num_players_below = int(urequest["num_players_below"])
            self.__enable__('num_players_below', self.num_players_below)

        # TODO: Can we support and/or combinations of min_plays, played_since and leagues_any/all?

        # Now we request to include players who have played at least a
        # few times.
        self.need_enabling.add('min_plays')
        if 'min_plays' in urequest and urequest['min_plays'].isdigit():
            self.min_plays = int(urequest["min_plays"])
            self.__enable__('min_plays', self.min_plays)

        # Now we request to include only players who have played the game
        # recently enough ...
        self.need_enabling.add('played_since')
        if 'played_since' in urequest:
            try:
                self.played_since = decodeDateTime(urequest['played_since'])
            except:
                self.played_since = None  # Must be a a Falsey value

            self.__enable__('played_since', self.played_since)

        # We can acccept leagues in an any or all form
        self.need_enabling.add('player_leagues_any')
        self.need_enabling.add('player_leagues_all')
        any_all = None
        player_leagues = leagues  # Use the transport option as a fallback.
        for suffix in ("any", "all"):
            if f'player_leagues_{suffix}' in urequest:
                player_leagues = urequest[f'player_leagues_{suffix}'].split(",")

                # Use the transport option "leagues" if no list provided for player_leagues
                # This enables URLs like
                #    ?player_leagues_any=1,2,3
                #    ?leagues=1,2,3&player_leagues_any
                if not player_leagues:
                    player_leagues = leagues

                any_all = suffix
                break

        if player_leagues:
            # Validate the leagues  discarding any invalid ones
            self.player_leagues = []
            for league in player_leagues:
                if models.League.objects.all().filter(pk=league).exists():
                    self.player_leagues.append(league)

        # If we found an any or all option
        if any_all:
            self.__enable__(f'player_leagues_{any_all}', self.player_leagues)

        # In case one or the other was enabled in the defaults above, if we lack any leagues we ensure they are both disabled
        else:
            self.__enable__('player_leagues_any', False)
            self.__enable__('player_leagues_all', False)

        # Now we capture the persepctive request if it provides a valid datetime
        self.need_enabling.add('as_at')
        if 'as_at' in urequest:
            try:
                self.as_at = decodeDateTime(urequest['as_at'])
            except:
                self.as_at = None  # Must be a a Falsey value

            self.__enable__('as_at', self.as_at)

        ##################################################################
        # EVOLUTION OPTIONS
        #
        # Now the evolution options. These are simpler as we can only specify one
        # method of selecting which snapshots to display. Compare_back_to is special
        # beast though as we record it as a number or a datetime. The latter is an explict
        # request back to time, and the former is a number of days request for an event impact
        # impact presentation that can work in concertn with num_days above.
        self.need_enabling.add('compare_with')
        self.need_enabling.add('compare_back_to')
        if 'compare_with' in urequest and urequest['compare_with'].isdigit():
            self.compare_with = int(urequest['compare_with'])
            self.__enable__('compare_with', self.compare_with)
            self.__enable__('compare_back_to', False)

        elif 'compare_back_to' in urequest:
            if urequest['compare_back_to']:
                # Now if it's a number we keept it as float and if it's a strig that parses
                # as a date_time we keept it as a date_time.
                if is_number(urequest['compare_back_to']):
                    self.compare_back_to = float(urequest['compare_back_to'])
                else:
                    try:
                        self.compare_back_to = decodeDateTime(urequest['compare_back_to'])
                    except:
                        self.compare_back_to = None  # Must be a a Falsey value
            # If compare_back_to is specificed without any value, it is taken
            # to imply compare back to the changed_since time or the num_days
            # event specification if either is specified (only one is sensible
            # at a time).
            else:
                if self.changed_since:
                    self.compare_back_to = self.changed_since
                elif self.num_days:
                    self.compare_back_to = self.num_days

            self.__enable__('compare_back_to', self.compare_back_to)
            self.__enable__('compare_with', False)

        ##################################################################
        # INFO OPTIONS

        # Options to include extra info in a leaderboard header
        if 'details' in urequest:
            self.details = json.loads(urequest['details'].lower())  # A boolean value is parsed
        # else use the default value

        if 'analysis_pre' in urequest:
            self.analysis_pre = json.loads(urequest['analysis_pre'].lower())  # A boolean value is parsed

        if 'analysis_post' in urequest:
            self.analysis_post = json.loads(urequest['analysis_post'].lower())  # A boolean value is parsed

        if 'show_d_rank' in urequest:
            self.show_d_rank = json.loads(urequest['show_d_rank'].lower())  # A boolean value is parsed

        if 'show_d_rating' in urequest:
            self.show_d_rating = json.loads(urequest['show_d_rating'].lower())  # A boolean value is parsed

        # Snapshot selecting options
        if 'show_baseline' in urequest:
            self.show_baseline = json.loads(urequest['show_baseline'].lower())  # A boolean value is parsed

        ##################################################################
        # HIGHLIGHT OPTIONS

        # Options for formatting the contents of a given leaderbaords
        if 'highlight_players' in urequest:
            self.highlight_players = json.loads(urequest['highlight_players'].lower())  # A boolean value is parsed

        if 'highlight_changes' in urequest:
            self.highlight_changes = json.loads(urequest['highlight_changes'].lower())  # A boolean value is parsed

        if 'highlight_selected_players' in urequest:
            self.highlight_selected_players = json.loads(urequest['highlight_selected_players'].lower())  # A boolean value is parsed

        ##################################################################
        # FORMATTING OPTIONS

        if 'names' in urequest:
            self.names = NameSelection[urequest['names']]

        if 'links' in urequest:
            self.links = LinkSelection[urequest['links']]

        # Options for laying out leaderboards on screen
        if 'cols' in urequest:
            self.cols = urequest['cols']

        # YET TO BE IMPLEMENTED OPTIONS - draw arrows between leaderboards for the listed players.
        if 'trace' in urequest:
            self.trace = urequest['trace'].split(",")

        # A special option which isn't an option per se. If passed in we make
        # the provided options as static as we can with self.make_static()
        if 'make_static' in urequest:
            self.make_static(ufilter, utz)
            self.made_static = True

        ##################################################################
        # ADMIN OPTIONS
        if 'ignore_cache' in urequest:
            self.ignore_cache = True

        if settings.DEBUG:
            log.debug(f"Enabled leaderboard options: {self.enabled}")

    def has_player_filters(self):
        '''
        Returns True if any player filters are enabled, else False
        '''
        return (self.is_enabled('players_ex')
              or self.is_enabled('players_in')
              or self.is_enabled('num_players_top')
              or self.is_enabled('num_players_above')
              or self.is_enabled('num_players_below')
              or self.is_enabled('min_plays')
              or self.is_enabled('played_since')
              or self.is_enabled('player_leagues_any')
              or self.is_enabled('player_leagues_all'))

    def player_nominated(self, player_pk):
        '''
        Returns True if a player was nominated specifically to be listed.
        '''
        return (self.is_enabled('players_in') or self.is_enabled('players_ex')) and str(player_pk) in self.players

    def player_in_league(self, player_pk, league_pks):
        '''
        Returns True if a player meets the league criteria
        '''
        league_pks = [str(pk) for pk in league_pks]  # We force them to strings as we stored strings in self.player_leagues
        if self.is_enabled('player_leagues_any') and not set(league_pks) & set(self.player_leagues):
            return False
        elif self.is_enabled('player_leagues_all') and not set(league_pks) == set(self.player_leagues):
            return False
        return True

    def player_ok(self, player_pk, plays, last_play, league_pks):
        '''
        Returns True if a player with the specified properties passes the criteria specified
        for them.
        '''
        # We always include players we've explicitly requested
        if self.is_enabled('players_in') and str(player_pk) in self.players:
            return True

        # If not explicitly selected then a player must satisfy any specified league criteria
        # or else they won't be listed.
        if not self.player_in_league(player_pk, league_pks):
            return False

        # If we have num_players_top requested then meeting any of the remaining filters
        # should win inclusion. If not though then we are listing the whole leaderboard and
        # we require someone to remaining filters to win inclusion. In summary?
        #
        # If we have a full leadeboard we're trying to knock out all players who
        # don't meet all the remaining criterai.
        #
        # If we have a top n leaderboard we're trying to include players again and
        # meeting any criterion will do.
        criteria = []
        if self.is_enabled('min_plays'):
            criteria.append(plays >= self.min_plays)

        if self.is_enabled('played_since'):
            criteria.append(last_play >= self.played_since)

        if self.is_enabled('num_players_top'):
            return any(criteria)  # Empty any list is False, as desired
        else:
            return all(criteria)  # Empty all list is True, as desired

    def no_evolution(self):
        '''
        Returns True if no evolution options are enabled.
        '''
        return not (self.is_enabled('compare_with') or self.is_enabled('compare_back_to'))

    def apply(self, leaderboard_snapshot):
        '''
        Given a leaderboard snapshot in the format that Session.leaderboard_snapshot()
        provides, applies these options to it returning a filtered version of the same
        snapshot as dictated by these options (self).

        We only filter players. We don't apply name or link formatting here, the
        snapshot elements contain sufficient information for the view itself to
        implement those rendering options. Our aim here is to send to the view
        a filtered snaphot because global leaderboads for a game can grow very
        large and most views will be concerned with a subset based on leagues.
        '''
        leaderboard = leaderboard_snapshot[8]

        # leaderboard is a well defined list of tuples that contain player info/metadata
        # The list is ordered by ranking.
        #
        # We want to apply the player filters now. So create a new list
        # pushing on candidates as we find them.

        # If any player filters are specified, list only the players that pass the criteria the options specify
        if self.has_player_filters():
            lbf = []  # A player-filtered version of leaderboard

            for p in leaderboard:
                # Fetch data from the tuple
                rank = p[0]
                pk = str(p[1])  # Force to string as self.players is a list of string pks
                plays = p[9]
                last_play = p[11]
                leagues = p[12]

                # If the player is explicitly nominated respect that
                if self.player_nominated(pk):
                    if pk in self.players:
                        lbf.append(p)
                    continue

                # Apply remaining citeria one by one

                # List top N players regardless of who they are
                if self.player_in_league(pk, leagues) and self.is_enabled('num_players_top') and len(lbf) < self.num_players_top:
                    lbf.append(p)
                    continue

                # For the rest of the list we check if the player is ok by performance criteria and league criteria
                if self.player_ok(pk, plays, last_play, leagues):
                    lbf.append(p)
                    continue

                # If the player is not OK themsleves, perhaps proximity to a mointanted player
                # wins them inclusion?

                # We need be we look ahead n players for a nominated player
                if self.is_enabled('num_players_above'):
                    # rank is numbered from 1 ... the list from 0
                    # the current player is at list inded rank-1
                    # We want to start looking form the next player
                    # so index rank-1+1
                    # i goes from 0 to lo.num_players_above-1
                    start = rank
                    for i in range(self.num_players_above):
                        if start + i < len(leaderboard) and self.player_nominated(leaderboard[start + i][1]):
                            lbf.append(p)
                            continue

                # If need be we look back n players for a nominated player
                if self.is_enabled('num_players_below'):
                    # rank is numbered from 1 ... the list from 0
                    # the current player is at list inded rank-1
                    # We want to start looking form the previous player
                    # so index rank-1-1
                    # i goes from 0 to lo.num_players_above-1
                    start = rank - 2
                    for i in range(self.num_players_below):
                        if start - i >= 0 and self.player_nominated(leaderboard[start - i][1]):
                            lbf.append(p)
                            continue

        # If no player filters are specified, lsit the all the players
        else:
            lbf = leaderboard

        return leaderboard_snapshot[0:8] + (lbf,)

    def as_dict(self):
        '''
        Produces a dictionary of JSONified option values which can be passed to context
        and used in Javascript.
        '''
        d = {}

        # Ignore internal attributes (startng with __) and methods (callable)
        for attr in [a for a in dir(self) if not a.startswith('__')]:
            val = getattr(self, attr)

            # Don't include methods or enums or dicts
            if not callable(val) and not isinstance(val, enum.EnumMeta) and not isinstance(val, OrderedDict):
                # Format date_times sensibly
                if isinstance(val, datetime):
                    val = val.strftime(settings.DATETIME_INPUT_FORMATS[0])

                # and listify sets (sets don't work in JS)
                elif isinstance(val, set):
                    val = list(val)

                # and textify enums as they don't JSONify either
                elif isinstance(val, NameSelection) or isinstance(val, LinkSelection):
                    val = val.name

                # Only include the value if it needs no enabling or if it is enabled.
                if (attr in self.need_enabling and attr in self.enabled) or not attr in self.need_enabling:
                    d[attr] = val

        return d

    def last_session_property(self, field):
        '''
        Returns a lazy Queryset that when evaluated produces the nominated property of the
        last session played given the current options sepcifying league and perspective.
        This is irrespective of the game, and is intended for the given league or leagues
        to return a property of the last activity as a reference for most recent event
        calculatiuons.

        Two properties are interest in most recent event queries:
            'date_time' - to find the date_time that the last gaming event ended.
            'location'  - to find out where it was played
        '''
        if settings.DEBUG:
            queries_before = len(connection.queries)

        s_filter = Q()

        # Restrict the list based on league memberships
        if self.is_enabled('game_leagues_any'):
            s_filter = Q(league__pk__in=self.game_leagues)
        elif self.is_enabled('game_leagues_all'):
            for pk in self.game_leagues:
                s_filter &= Q(league__pk=pk)

        # Respect the perspective request
        if self.is_enabled('as_at'):
            s_filter &= Q(date_time__lte=self.as_at)

        properties = models.Session.objects.filter(s_filter).values(field).order_by("-date_time")
        latest_property = top(properties, 1)

        if settings.DEBUG:
            queries_after = len(connection.queries)

            log.debug("last_session_time:")

            if queries_after == queries_before:
                log.debug("\tSQL is still LAZY")
                log.debug(f"\t{get_SQL(latest_property)}")
            else:
                log.debug("\tSQL was evaluated!")
                log.debug(f"\t{connection.queries[-1]['sql']}")

        return latest_property

    def last_event_end_time(self, as_ExpressionWrapper=True):
        '''
        Returns an Expression (that can be used in filtering sessions) that is the date_time
        of the ostensible end of the last gaming event. Being the date_time of the last
        session this league or these leagues played.
        '''
        if as_ExpressionWrapper:
            leet = ExpressionWrapper(Subquery(self.last_session_property('date_time')), output_field=DateTimeField())
        else:
            leet = self.last_session_property('date_time')[0]['date_time']

        return leet

    def last_event_start_time(self, delta_days, as_ExpressionWrapper=True):
        '''
        Returns an Expression (that can be used in filtering sessions) that is the date_time
        of the ostensible start of the last gaming event. Being the last_event_end_time as above)
        less the value of delta_days. This could be self.num_days for the game filtering or
        self.compare_back_to for snapshot capture for example.

        :param delta_days:              The number of days before the last session to pin the event start time at
        :param as_ExpressionWrapper:    Return an ExpressionWrapper (for a lazy Queryset builder)
        '''
        if as_ExpressionWrapper:
            lest = ExpressionWrapper(Subquery(self.last_session_property('date_time')) - timedelta(days=delta_days), output_field=DateTimeField())
        else:
            lest = self.last_session_property('date_time')[0]['date_time'] - timedelta(days=delta_days)

        return lest

    def last_event_location(self, as_ExpressionWrapper=True):
        '''
        Returns an Expression (that can be used in filtering sessions) that is the location
        of the event. Being the location of the last session this league or these leugues
        played less
        '''
        if as_ExpressionWrapper:
            # Note: that ForeignKey is an AutoField which is a class of IntegerField.
            # So the output type of IntergerField is populated with the right SQL here.
            lel = ExpressionWrapper(Subquery(self.last_session_property('location')), output_field=IntegerField())
        else:
            lel = self.last_session_property()[0]['location']

        return lel

    def games_queryset(self):
        '''
        Returns a QuerySet of games that these options select (self.game_filters drives this)

        As a QuerySet it is lazy and hence efficient to build here. Either way a database query
        on the Game model is very cheap compared with the scrape required for a perspective drive
        leaderboard construction from recorded Performance objects. To wit we can use a query like
        this to determine if a game list for comparison with a cached version of same.
        '''

        # Start the queryset with an ordered list of all games (lazy, only the SQL created)
        # Sort them by default in descending order of play_count then session_count (measures
        # of popularity in the specified leagues).

        if settings.DEBUG:
            queries_before = len(connection.queries)

        g_filter = Q()
        s_filter = Q()

        # First restrict the list to exclusively specified games if present
        # If an exclusive list of games is provided we return just those
        if self.is_enabled('games_ex'):
            g_filter &= Q(pk__in=self.games)
            s_filter &= Q(game_id__in=self.games)

        # Restrict the list based on league memberships
        g_post_filters = []
        if self.is_enabled('game_leagues_any'):
            g_filter = Q(played_by_leagues__pk__in=self.game_leagues)
            s_filter = Q(league__pk__in=self.game_leagues)  # used for game's latest_session only
        elif self.is_enabled('game_leagues_all'):
            # Collect post filters as the AND (all) operation demands repeated joins/filters
            # See: https://stackoverflow.com/questions/66647977/django-and-filter-on-related-objects?noredirect=1#comment117816963_66647977
            # See also USE_ARRAY_AGG  below. This method is overrident by that option
            for pk in self.game_leagues:
                g_post_filters.append(Q(sessions__league__pk=pk))

            # We want to report the latest session playerd among ALL the leagues, so this is
            # simple search on all session played by ANY league from which we'll get the latest.
            s_filter = Q(league__pk__in=self.game_leagues)  # used for game's latest_session only

        # Respect the perspective request when finding last_play of a game
        # as in last_play before as_at
        if self.is_enabled('as_at'):
            s_filter &= Q(date_time__lte=self.as_at)

        # We sort them by a measure of popularity (within the selected leagues)
        latest_session_source = models.Session.objects.filter(s_filter)
        latest_session = top(latest_session_source.filter(game=OuterRef('pk')).order_by("-date_time"), 1)
        last_play = Subquery(latest_session.values('date_time'))
        session_count = Count('sessions', filter=g_filter, distinct=True)
        play_count = Count('sessions__performances', filter=g_filter, distinct=True)

        USE_ARRAY_AGG = True
        game_source = models.Game.objects.filter(g_filter)
        if g_post_filters:
            # See https://stackoverflow.com/questions/66647977/django-and-filter-on-related-objects?noredirect=1#comment117816963_66647977
            # For a discussion of methods here. ArrayAgg is the cleanest most efficient but is Postgresql specific.
            if USE_ARRAY_AGG:
                game_source = game_source.annotate(player_leagues=ArrayAgg(F('sessions__league'), distinct=True)).filter(player_leagues__contains=self.game_leagues)
            else:
                for g_post_filter in g_post_filters:
                    game_source = game_source.filter(g_post_filter)
                game_source = game_source.distinct()

        if settings.DEBUG:
            log.debug("GAME SOURCE:")
            log.debug(f"\t{get_SQL(game_source, explain=True)}")  # Without explain the SQL is wrong here on an ArrayAgg query
            log.debug("LATEST SESSION SOURCE:")
            log.debug(f"\t{get_SQL(latest_session_source)}")

        games = (game_source.annotate(last_play=last_play)
                            .annotate(session_count=session_count)
                            .annotate(play_count=play_count)
                            .filter(session_count__gt=0)
                            .order_by('-play_count'))

        # Now build up gfilter based on the game selectors
        #
        # We want to include a game if it matches ANY of"
        #
        # changed_since,
        # game_players_any or game_players_all

        or_filters = Q()

        if self.is_enabled('changed_since'):
            or_filters |= Q(sessions__date_time__gte=self.changed_since)

        # Filter the games on player participation ...
        if self.is_enabled('game_players_any') or self.is_enabled('game_players_all'):
            if self.is_enabled('game_players_any'):
                sessions = models.Session.objects.filter(performances__player__pk__in=self.game_players)
            elif self.is_enabled('game_players_all'):
                # Only method I've found is with an intersection. Problem presented here:
                # https://stackoverflow.com/questions/66647977/django-and-filter-on-related-objects?noredirect=1#comment117816963_66647977
                # sessions = Session.objects.filter(performances__player=self.game_players[0])
                # for pk in self.game_players[1:]:
                    # sessions = sessions.intersection(Session.objects.filter(performances__player=pk))

                # Another mothod using joins
                sessions = models.Session.objects.filter(performances__player=self.game_players[0])
                for pk in self.game_players[1:]:
                    sessions = sessions.filter(performances__player=pk)

            or_filters |= Q(sessions__pk__in=sessions.values_list('pk'))

        gfilter = or_filters

        if self.is_enabled('num_days'):
            # Find only games played on or after the event start time
            est = self.last_event_start_time(self.num_days)
            gfilter &= Q(sessions__date_time__gte=est)

            # Find only games played at the event location
            el = self.last_event_location()
            gfilter &= Q(sessions__location=el)

            # And let's not forget to limit it to games with sessions played before
            # self.as_at if that perspective is enabled.
            if self.is_enabled('as_at'):
                gfilter &= Q(sessions__date_time__lte=self.as_at)

        # Choose the ordering in preparation for a top n filter
        if self.is_enabled('latest_games'):
            order_games_by = ('-last_play',)
        # If we want the top n games or not by default sort the games by popularity,
        # We only sort them temporally if explicitlyw anting the n latest games.
        else:
            order_games_by = ('-play_count', '-session_count')

        # Apply the game selector(s)
        filtered_games = games.filter(gfilter).order_by(*order_games_by).distinct()

        # Taking the top num_games of course happens last (after all other filters applied)
        # It's a way of clipping long lists down to size focussing on the top entries.
        if self.is_enabled('top_games') or self.is_enabled('latest_games'):
            filtered_games = top(filtered_games, self.num_games)

        # Now if we have a games_in rquest we want to include those games explicilty
        if self.is_enabled('games_in'):
            filtered_games = filtered_games.union(
                                models.Game.objects.filter(pk__in=self.games)
                                            .annotate(last_play=last_play)
                                            .annotate(session_count=session_count)
                                            .annotate(play_count=play_count)
                                ).order_by(*order_games_by)

        if settings.DEBUG:
            queries_after = len(connection.queries)

            log.debug("GAME SELECTOR:")

            if queries_after == queries_before:
                log.debug("\tSQL is still LAZY")
                log.debug(f"\t{get_SQL(filtered_games)}")
            else:
                log.debug("\tSQL was evaluated!")
                log.debug(f"\t{connection.queries[-1]['sql']}")

            log.debug(f"SELECTED {len(filtered_games)} GAMES:")
            for game in filtered_games:
                log.debug(f"\t{game.name}")

        return filtered_games

    def snapshot_queryset(self, game, include_baseline=False):
        '''
        Returns a tuple containing:

        A QuerySet of the Session objects which which provide the foundation
        for historic snapshots selected by these options (self.evolution_options drive
        this).

        As a QuerySet this should ideally remain unevaluated on return (remain lazy).
            In practice if include_baseline is True, it may need evaluation.

        A flag that is set to true if we've been asked to include a baseline and a
        baseline outside of the requested window of snapshots was found and added.
        if this is true the client is effictively asked to hide that baseline (the
        last/earliest) session in the returned QuerySet. if false either no baseline
        is included or it is but it falls withing the winodow of snapshots requested.


        A snapshot is the leaderboard as it appears after a given game session
        The default and only standard snapshot is the current leaderboard after the
        last session of the game.

        But this can be altered by:

        A perspective request:
           lo.as_at which asks for the leaderboard as at a given time (not the latest one)

        Evolution requests:
           lo.evolution_options documents the possible selections

        We build a QeurySet of the sessions after which we want the leaderboard snapshots.

        :param game:        A Game object for which the leaderboards are requested
        :param include_baseline:    If True will include a baseline snapshot (the one just prior to those requested) so that deltas can be caluclated by the caller if desired)
        '''

        def sessions_plus(sessions):
            '''
            Given a sessions queryset adds the prefetches needed to lower the query count later and boost
            performance a little.

            On one trial of a full leaderboad generation I got this without the prefech:
            STATS:    Total Time:    36213.7 ms    Python Time:    25.0 ms    DB Time:    11.3 ms    Number of Queries:    8,339

            and this with the prefetch:
            STATS:    Total Time:    28444.2 ms    Python Time:    18.2 ms    DB Time:    10.3 ms    Number of Queries:    5,739

            and on a run with the leaderboard cache:
            STATS:    Total Time:     4448.4 ms    Python Time:     2.0 ms    DB Time:     2.4 ms    Number of Queries:    329

            Quite a saving (even better of course from the cache).

            :param sessions:
            '''
            return sessions.select_related('league', 'location', 'game').prefetch_related('performances', 'ranks')

        if settings.DEBUG:
            queries_before = len(connection.queries)

        # Start our Session filter with sessions for the game in question
        sfilter = Q(game=game)

        # Respect the perspective request
        if self.is_enabled('as_at'):
            sfilter &= Q(date_time__lte=self.as_at)

        # Respect the game_leagues filter
        # This game may be played by different leagues
        # and we may be interested in a view on one or more leagues that are specified in
        # game_leagues_any or game_leagues all.

        # A tuning constant. A view over ALL leagues listed affords a Broad and a Narrow
        # view of the sessions played. Broad includes All the sessions played in any league
        # in the list. It's simpler, faster and very likely more what is wanted. That is, looking
        # at a group of leagues, the "latest" leaderboard would be the latest among any of the leagues
        # and the latest standing relevant to ALL those leagues.
        #
        # A Narrow view looks deepr and uses only sessions that contain players from all of the leagues.
        # This loooks only at elague interactiuon, or promiscuity if you will. And is turned off by default
        # now because there is no UI to choose between the two. There may never be, it's a tad overwhelmingly
        # complicated to differentiate between these.
        BROAD_ALL_VIEW = True

        # ANY is easy, and sessions are played in aleague and we casn just find sessions in any of the leagues
        # provided in self.game_leagues.
        if self.is_enabled('game_leagues_any'):
            sfilter &= Q(league__pk__in=self.game_leagues)
            session_source = models.Session.objects.filter(sfilter)

        # ALL can be just as easy. If we are showing the leaderboards for games b=layed by ALL
        # of a list of leagues, we probbaly want actually to see snapshots, in particular the latetst
        # snapshot from the list of session played in ANY of those leagues. If so, that's easy. And we
        # do that here
        elif self.is_enabled('game_leagues_all') and BROAD_ALL_VIEW:
            sfilter &= Q(league__pk__in=self.game_leagues)
            session_source = models.Session.objects.filter(sfilter)

        # If however for ALL we want a more restruictview fetching snapshots only after sessions that contained
        # players from ALL the leagues, then this is much trickier to write as a query and needs us to drill down
        # into the players and their leagues.
        #
        # Fames are played in a league (i.e. each session is atttributed to a league), and so any session only
        # has 'a' league in Session.league. It can be more than one league at the same time and so any AND
        # constraint placed on it will fail. Instead we use a tailored query that looks at the leagues that players
        # in the session are in and returns all session which contai players across all the leagues.
        #
        # This is A) inconsistent with ANY which looks at the session league and not player leagues, and
        # B) probably only really useful for two leagues or if there are a lot of highly league promiscuous
        # players wandering between leagues ;-).
        elif self.is_enabled('game_leagues_all'):
            # This is mildly complicated we want the leagues to be ORed because the session query will be joined
            # with performances and players producing one tuple per player in a session. To wit we need to
            # bring it back to one tuple per session by annotating with a Count on leagues, and we can then
            # return session with the full count, namely ALL the leagues represented.
            #
            # But we need to filter first for all tuples that are in any of the leagues, so an OR filter.
            # the AND part arises from the fact that we select onlys essions that have the full distinct count
            # of leagues associated with thm. Hairy but it works.
            lfilter = Q()
            for pk in self.game_leagues:
                lfilter |= Q(performances__player__leagues__pk__in=pk)
            sfilter &= lfilter & Q(league_count=len(self.game_leagues))

            session_source = models.Session.objects.annotate(league_count=Count('performances__player__leagues__pk', distinct=True)).filter(sfilter)

        # With no league filtering, build the session source from the extant sfilter only
        else:
            session_source = models.Session.objects.filter(sfilter)

        # At this stage we have session_source that
        #   Specifies a game
        #   Respects and league constraints specified
        #   Respects any perspective constraint supplied

        if self.no_evolution():
            # Just get the latest session, one snapshot only
            # And extra one if a baseline is requested.
            sessions = top(session_source.order_by("-date_time"), 2 if include_baseline else 1)
            hide_baseline = include_baseline  # No evolution window, for the baseline to fall within, so if we include one, we should hide it.
        else:
            # compare_with or compare_back_to is enabled
            extra_session = None
            earliest_time = None

            # We want one extra session, the one just before the reference time.
            # This is a new QuerySet which we'll Union with the main one. We
            # want to find it just before we restrict sfilter as we'd like to
            # respect sfilter to date. It specified a game at least, possibly
            # league constraints on the sessions and a perspective constraint.
            if self.is_enabled('compare_back_to'):
                # We're defining a window here. We want all session from the start of
                # that window (done here)  and the end of the window ifs defined by
                # self.as_at or the latest session (no explicit end needed).

                # We want a reference time first, being the start of an event or
                # a time explcitly provided. We'll add the snapshot prior to this time
                # as a the state of the boartd AT that time, and if a baseline is
                # requested a second one (not intended for rendering just for rank delta
                # calculation. Of course if it is after reference_time it shoudl be rendered.
                if isinstance(self.compare_back_to, numbers.Real):
                    earliest_time = self.last_event_start_time(self.compare_back_to)
                elif isinstance(self.compare_back_to, datetime):
                    earliest_time = self.compare_back_to
                else:
                    earliest_time = None

                if earliest_time:
                    efilter = sfilter & Q(date_time__lt=earliest_time)
                    extra_session = top(sessions_plus(session_source.filter(efilter)), 2 if include_baseline else 1)

                    # If we get only one extra session, or none then we have no distinct
                    # baseline beyond the evolution window and so we should not hide it.
                    hide_baseline = include_baseline and extra_session.count() == 2

                    # The reference time is of course, also the time that we want all boards from.
                    # We update sfilter AFTER building the extra_session query because sfilter prior
                    # to his constraint is used in defining it.
                    sfilter &= Q(date_time__gte=earliest_time)

            # Then order the sessions in reverse date_time order
            sessions = sessions_plus(session_source.filter(sfilter).order_by("-date_time"))

            if extra_session:
                sessions = sessions.union(extra_session).order_by("-date_time")

            # Keep on respecting the evolution options where enabled
            if self.is_enabled('compare_with'):
                # This encodes a number of sessions so the top n on the temporally ordered
                # sessions. we want at least one more because that one more (because it's
                # compare the latested - or as_at - with n prioer boards, so we want at
                # least n+1 boards total. But if we've been asked to provide a baselined
                # we return one more which the caller presumeably doesn't render just used
                # for delta calculation (it's the hidden baselined for deltas)
                sessions = top(sessions, self.compare_with + (2 if include_baseline else 1))

                # If we get only one extra session, or none then we have no distinct
                # baseline beyond the evolution window and so we should not hide it.
                hide_baseline = include_baseline and sessions.count() == self.compare_with + 2

        if settings.DEBUG:
            queries_after = len(connection.queries)

            log.debug("SNAPSHOT SELECTOR:")

            if queries_after == queries_before:
                log.debug("\tSQL is still LAZY")
                log.debug(f"\t{get_SQL(sessions)}")
            else:
                log.debug(f"\tSQL was evaluated! It took {queries_after-queries_before} queries to do.")
                for i in range(queries_after - queries_before):
                    log.debug(f"\t{-1-i}\t{connection.queries[-1-i]['sql']}")

            log.debug(f"SELECTED {len(sessions)} SNAPSHOTS:")
            for session in sessions:
                log.debug(f"\t{session.id}: {session.date_time}")

        return (sessions, hide_baseline)

    def titles(self):
        '''
        Builds page title and subtitle based on these leaderboard options

        Returns them in a 2-tuple.

        Principles at play:

        In title:
            Display Top or Latest count if set.

            Display a League filter if in effect, using LEagues, and truncating list down
            to two entries and elipsis if possible.

            Display a Player Filter on same principle.

        In subtitle:
            Display the perspective if any
            Display the evolution options if any
        '''

        # Build A Leagues intro string
        if self.is_enabled('game_leagues_any') or self.is_enabled('game_leagues_all'):
            L = models.League.objects.filter(pk__in=self.game_leagues)
            La = "any" if self.is_enabled('game_leagues_any') else "all"
        else:
            L = []

        LA = f"{La} of the leagues" if len(L) > 1 else "the league"

        # Build A Players intro string
        if self.is_enabled('game_players_any') or self.is_enabled('game_players_all'):
            P = models.Player.objects.filter(pk__in=self.game_players)
            Pa = "any" if self.is_enabled('game_players_any') else "all"
        else:
            P = []

        PA = f"{Pa} of the players" if len(P) > 1 else "the player"

        # Build the list of leagues capping at two items with elipsis if more.
        if len(L) == 1:
            l = L[0].name
        elif len(L) == 2:
            l = f"{L[0].name} and {L[1].name}"
        elif len(L) > 2:
            l = f"{L[0].name}, {L[1].name} ..."

        # Build the list of players capping at two items with elipsis if more.
        if len(P) == 1:
            p = P[0].name_nickname
        elif len(P) == 2:
            p = f"{P[0].name_nickname} and {P[1].name_nickname}"
        elif len(P) > 2:
            p = f"{P[0].name_nickname}, {P[1].name_nickname} ..."

        # Start the TITLE off with Top or Latest
        if self.is_enabled('top_games'):
            title = f"Top {self.num_games} "
        elif self.is_enabled('latest_games'):
            title = f"Latest {self.num_games} "
        else:
            title = ""

        # Add rest of TITLE
        if not P:
            if not L:
                title += "Global Leaderboards"
            else:
                title += f"Leaderboards for {LA} {l}"
        else:
            if not L:
                title += f"Leaderboards for {PA} {p}"
            else:
                title += f"Leaderboards for {PA} {p} in {LA} {l} "

        # Now a poerspective and evolution summary in the subtitle
        subtitle = []
        if self.is_enabled("as_at"):
            subtitle.append(f"as at {localize(localtime(self.as_at))}")

        if self.is_enabled("played_since"):
            subtitle.append(f"changed after {localize(localtime(self.changed_since))}")

        if self.is_enabled("compare_back_to"):
            if isinstance(self.compare_back_to, numbers.Real):
                if self.compare_back_to == int(self.compare_back_to):
                    cb = int(self.compare_back_to)
                else:
                    cb = self.compare_back_to

                days = "day's" if cb == 1 else "days'"
                time = f"before the last event of {cb} {days} duration"
            elif isinstance(self.compare_back_to, datetime):
                time = "at that same time" if self.compare_back_to == self.changed_since else localize(localtime(self.compare_back_to))
            else:
                time = None

            if time:
                subtitle.append(f"compared back to the leaderboard {time}")
        elif self.is_enabled("compare_with"):
            subtitle.append(f"compared with {self.compare_with} prior leaderboards")

        if self.is_enabled("games_ex"):
            subtitle.append(f"for the games: {', '.join([models.Game.objects.get(pk=g).name for g in self.games])}")

        if self.is_enabled("players_ex"):
            subtitle.append(f"for the players: {', '.join([models.Player.objects.get(pk=p).name_nickname for p in self.players])}")

        return (title, "<BR>".join(subtitle))

    def make_static(self, ufilter={}, utz=UTC):
        '''
        Make the relative leaderboard_options more static. Specifically the event based ones.

        It's hard to secure a perfectly static leaderboards link becasue anything could change
        in the database over time, players come and go, games come and go whatever, there are
        just too many variables and the closest we could get really is to store the cache that
        is currently stored in the session in a more persistent database table with an ID.

        But can't see much need for that yet. Right now the main aim is that we can rapidly
        get the impact of the last event (prior to as_at) but produce a link that uses
        fixed reference times rather than the relative so they can be used in comms and
        have lasting relevance.
        '''

        # Map self.compare_back_to number to self.compare_back_to datetime
        if self.is_enabled('compare_back_to') and isinstance(self.compare_back_to, numbers.Real):
            self.compare_back_to = fix_time_zone(self.last_event_start_time(self.compare_back_to, as_ExpressionWrapper=False), utz)

        # Map self.num_days to self.changed_since
        if self.is_enabled('num_days'):
            # Disable num_days option (which is relative to now and not static.
            self.__enable__('num_days', False)

            # Enable the equivalent time window and evolution options
            self.changed_since = fix_time_zone(self.last_event_start_time(self.num_days, as_ExpressionWrapper=False), utz)
            self.__enable__('changed_since', True)

            self.as_at = fix_time_zone(self.last_event_end_time(as_ExpressionWrapper=False), utz)
            self.__enable__('as_at', True)

            self.compare_back_to = self.changed_since
            self.__enable__('compare_back_to', True)

        # If a user session filter is used, convert it toe xplicit static options
        # Only league supported for now. If not leagues are explicti and preferred
        # league is in place for the user (in the user session)
        #
        # Note: This is probably not needed. It operates in concert with the client
        # side code that generates a statc URL from the returned options. We return
        # an options"made_static" to let the client know we've done the server side
        # bit. The client side bit then build the URL from the leaderboard_options we
        # return.
        if ufilter:
            preferred_league = ufilter.get('league', None)
            if preferred_league:
                # We use a list of strings as IDs come in that way in request data
                if not self.game_leagues:
                    self.game_leagues = [str(preferred_league)]
                if not self.player_leagues:
                    self.player_leagues = [str(preferred_league)]


def augment_with_deltas(master, baseline=None, structure=LB_STRUCTURE.game_wrapped_session_wrapped_player_list, style=None):
    '''
    Given a master leaderboard and a baseline to compare it against, will
    augment the master with delta measures (adding a previous rank
    and rating elements to each player tuple)

    This is very flexible with structures and formats. Accepts JSON and Python and
    each of the leaderboard structures and returns the same. General purpose augmenter
    of playlists with a previous rank item based on the baseline.

    By default, only master is needed. if it is a game_wrapped_session_wrapped_player_list
    with snapshots in it no baseline is needed and all the snapshots will be delta augmented.

    Only two styles are supported, rich and data. They are the only two that currently include
    a unique player ID which cna be used for tha ugmentation.

    :param master:      a leaderboard
    :param baseline:    a leaderboard to compare with. None is valid only for a game_wrapped_session_wrapped_player_list with snaps
    :param structure:   an LB_STRUCTURE that master and baseline are to interpreted with
    :param style:       an LB_PLAYER_LIST_STYLE, which will be guessed at if need be, so we know where to get the rank and rating from to augment with.
    '''

    if isinstance(master, str):
        _master = json.loads(master)
    else:
        _master = mutable(master)

    if isinstance(baseline, str):
        _baseline = json.loads(baseline)
    else:
        _baseline = baseline

    igd = LB_STRUCTURE.game_data_element.value
    isd = LB_STRUCTURE.session_data_element.value
    snaps = False  # by default (only true on game_wrapped leaderboards that say so

    if structure == LB_STRUCTURE.session_wrapped_player_list:
        lb_master = _master[isd]
        lb_baseline = _baseline[isd]
    elif structure == LB_STRUCTURE.game_wrapped_player_list:
        snaps = _master[igd - 2]
        lb_master = _master[igd]

        if not snaps and _baseline:
            lb_baseline = _baseline[igd]
        else:
            lb_baseline = None
    elif structure == LB_STRUCTURE.game_wrapped_session_wrapped_player_list:
        snaps = _master[igd - 2]

        if snaps:
            # A list of session_wrapped leaderboards.
            # We remove the session wrappers to create a list of player lists
            # for uniform handling below.
            lb_master = [session_wrapper[isd] for session_wrapper in _master[igd]]
        else:
            # A single session wrapped leaderboard (extract the player list, remove the sessino wrapper)
            lb_master = _master[igd][isd]

            if _baseline:
                lb_baseline = _baseline[igd][isd]
            else:
                lb_baseline = None
    elif structure == LB_STRUCTURE.player_list:
        lb_master = _master
        lb_baseline = _baseline

    # Build a list of (master, baseline) tuples to process
    if snaps:
        pairs = [(lb_master[i], lb_master[i + 1]) for i in range(len(lb_master) - 1)]
    elif lb_baseline:
        pairs = [(lb_master, lb_baseline)]
    else:
        pairs = []

    # We now augment _master in situ
    for lb in pairs:
        # Grab the two player lists
        pl_master = lb[0]
        pl_baseline = lb[1]

        style = guess_player_list_style(pl_baseline)

        previous_rank = {}
        previous_rating = {}
        for r, p in enumerate(pl_baseline):
            # Most commonly used for rich player lists (i.e for rendering informative player lists (leaderboards), which the rich style targets)
            if style == LB_PLAYER_LIST_STYLE.rich:
                rank = p[0]
                pk = p[1]
                rating = p[6]
            elif style == LB_PLAYER_LIST_STYLE.data:
                rank = r
                pk = p[0]
                rating = p[1]
            else:
                raise ValueError("Attempt to augment and unsupport Player List style")

            previous_rank[pk] = rank
            previous_rating[pk] = rating

        for r, p in enumerate(pl_master):
            if style == LB_PLAYER_LIST_STYLE.rich:
                pk = p[1]
            elif style == LB_PLAYER_LIST_STYLE.data:
                pk = p[0]

            pran = previous_rank.get(pk, None)
            prat = previous_rating.get(pk, None)
            pl_master[r] = tuple(p) + (pran, prat)

    if isinstance(master, str):
        result = json.dumps(_master, cls=DjangoJSONEncoder)
        return result
    else:
        # Back to tuple with frozen result
        return immutable(_master)


def styled_player_tuple(player_list_tuple, rank=None, style=LB_PLAYER_LIST_STYLE.rich, names="nick"):
    '''
    Takes a tuple styled after LB_PLAYER_LIST_STYLE.data and returns a styled tupled as requested.

    styled_player_tuple() below is more convenient as it takes an ordered player list from
    which rank is derived. Only the rich style includes the rank.

    :param player_list_tuple: A tuple in LB_PLAYER_LIST_STYLE.data
    :param rank:  Rank on the leaderboard 1, 2, 3, 4 etc
    :param style: A LB_PLAYER_LIST_STYLE to return
    :param names: A style for rendering names
    '''
    (player_pk, trueskill_eta, trueskill_mu, trueskill_sigma, plays, victories, last_play) = player_list_tuple

    player = models.Player.objects.get(pk=player_pk)

    try:
        player = models.Player.objects.get(pk=player_pk)
        player_name = player.name(names)
        player_leagues = player.leagues.all()
    except models.Player.DoesNotExist:
        player = None  # TODO: what to do?
        player_name = "<unknown>"
        player_leagues = []

    if style == LB_PLAYER_LIST_STYLE.none:
        lb_entry = player_name
    elif style == LB_PLAYER_LIST_STYLE.data:
        lb_entry = player_list_tuple
    elif style == LB_PLAYER_LIST_STYLE.rating:
        lb_entry = (player_name, trueskill_eta)
    elif style == LB_PLAYER_LIST_STYLE.ratings:
        lb_entry = (player_name, trueskill_eta, trueskill_mu, trueskill_sigma)
    elif style == LB_PLAYER_LIST_STYLE.simple:
        lb_entry = (player_name, trueskill_eta, trueskill_mu, trueskill_sigma, plays, victories)
    elif style == LB_PLAYER_LIST_STYLE.rich:
        # There's a slim chance that "player" does not exist (notably when 'data' is provided
        # So access player properties cautiously with fallback.
        lb_entry = (rank,
                    player_pk,
                    player.BGGname if player else '',
                    player.name('nick') if player else '',
                    player.name('full') if player else '',
                    player.name('complete') if player else '',
                    trueskill_eta,
                    trueskill_mu,
                    trueskill_sigma,
                    plays,
                    victories,
                    last_play,
                    [l.pk for l in player_leagues])
    else:
        raise ValueError(f"Programming error in Game.leaderboard(): Illegal style submitted: {style}")

    return immutable(lb_entry)


def styled_player_list(player_list, style=LB_PLAYER_LIST_STYLE.rich, names="nick"):
    '''
    Takes a list of tuples styled after LB_PLAYER_LIST_STYLE.data and returns a list of styled tupled as requested.

    :param player_list_tuple: A tuple in LB_PLAYER_LIST_STYLE.data
    :param rank:  Rank on the leaderboard 1, 2, 3, 4 etc
    :param style: A LB_PLAYER_LIST_STYLE to return
    :param names: A style for rendering names
    '''
    styled_list = []
    for i, player_tuple in enumerate(player_list):
        styled_list.append(styled_player_tuple(player_tuple, rank=i + 1, style=style, names=names))

    return immutable(styled_list)


def leaderboard_changed(player_list1, player_list2):
    '''
    Return True if two player lists in style LB_PLAYER_LIST_STYLE.data are not functionly the same.

    :param player_list1:
    :param player_list2:
    '''
    if len(player_list1) == len(player_list2):
        for player_tuple1, player_tuple2 in zip(player_list1, player_list2):
            # We compare only the first 4 elements which define the player and rating at this position
            # If they are the same the leaderboard is functionall unchanged (the remaining items are
            # useful metadata but not relevant to ratings or ranking)
            for element1, element2 in zip(player_tuple1[0:4], player_tuple2[0:4]):
                if element1 != element2:
                    return True
        return False
    else:
        return True


def restyle_leaderboard(leaderboards, structure=LB_STRUCTURE.game_wrapped_session_wrapped_player_list, style=LB_PLAYER_LIST_STYLE.rich, names="nick"):
    '''
    Restyles a leaderboard of a given structure, assuming the player_lists are in LB_PLAYER_LIST_STYLE.data

    :param leaderboards: A game_wrapped leaderboard in LB_PLAYER_LIST_STYLE.data
    :param structure: A LB_STRUCTURE, that specifies the structure of leaderboards provided (and returned)
    :param style: A LB_PLAYER_LIST_STYLE to retyle to
    '''
    igd = LB_STRUCTURE.game_data_element.value
    isd = LB_STRUCTURE.session_data_element.value

    _leaderboards = mutable(leaderboards)

    snaps = False  # by default (only true on game_wrapped leaderboards that say so

    # Build a list of player_lists (if only of one item) and
    # note whether its a list (snaps is declared)
    if structure == LB_STRUCTURE.session_wrapped_player_list:
        player_lists = [_leaderboards[isd]]
    elif structure == LB_STRUCTURE.game_wrapped_player_list:
        snaps = _leaderboards[igd - 2]
        if snaps:
            player_lists = _leaderboards[igd]
        else:
            player_lists = [_leaderboards[igd]]
    elif structure == LB_STRUCTURE.game_wrapped_session_wrapped_player_list:
        snaps = _leaderboards[igd - 2]

        if snaps:
            player_lists = [session_wrapper[isd] for session_wrapper in _leaderboards[igd]]
        else:
            player_lists = _[leaderboards[igd][isd]]
    elif structure == LB_STRUCTURE.player_list:
        player_lists = [_leaderboards]

    for i, pl in enumerate(player_lists):
        player_lists[i] = styled_player_list(pl, style=style, names=names)

    if structure == LB_STRUCTURE.session_wrapped_player_list:
        _leaderboards[isd] = player_lists[0]
    elif structure == LB_STRUCTURE.game_wrapped_player_list:
        if snaps:
            _leaderboards[igd] = player_lists
        else:
            _leaderboards[igd] = player_lists[0]
    elif structure == LB_STRUCTURE.game_wrapped_session_wrapped_player_list:
        if snaps:
            for i, pl in enumerate(player_lists):
                _leaderboards[igd][i][isd] = pl
        else:
            _leaderboards[igd][isd] = player_lists[0]
    elif structure == LB_STRUCTURE.player_list:
        _leaderboards = player_lists[0]

    return immutable(_leaderboards)


def guess_player_list_style(player_list):
    '''
    Based on how Game.leaderboard implements the LB_PLAYER_LIST_STYLEs.

    TODO: This should really be more robust, as in not based on what is implemented in Games.leaderboard.
    Perhaps the leaderboard structure can contain information about its style.l
    Perhaps one day the whole Leaderboard creation, structuring and presenting is a class of its own.

    :param player_list:
    '''
    # Just take the first entry in the player list as a sample
    sample = player_list[0]
    if not isinstance(sample, (list, tuple)):
        return  LB_PLAYER_LIST_STYLE.none
    elif len(sample) == 7:
        return  LB_PLAYER_LIST_STYLE.data
    elif len(sample) == 6:
        return  LB_PLAYER_LIST_STYLE.simple
    elif len(sample) == 2:
        return  LB_PLAYER_LIST_STYLE.rating
    elif len(sample) == 4:
        return  LB_PLAYER_LIST_STYLE.ratings
    else:
        return  LB_PLAYER_LIST_STYLE.rich


def extract_player_list(leaderboard, structure=LB_STRUCTURE.game_wrapped_session_wrapped_player_list, style=None, snap=0):
    '''
    Extracts the player list from a structured leaderboard. The player list being a list of ordered tuples that describe
    a player on a leaderboard.

    If there are many leaderboards in the structure the first one is used or the on that is identfied by the snap argument
    This is the case with game wrapped leaderboards where the data element is a list of player lists rather than a single
    player list.

    :param leaderboard: A leaderboard with the confessed structure with style LB_PLAYER_LIST_STYLE.data
    :param structure: An LB_STRUCTURE that describes the structure of leaderboard
    :param style: An LB_PLAYER_LIST_STYLE that describes the player style (is guessed form tuple if not confessed)
    :param snap: A snapshot number if it's a game wrapped board with snapshots (snaps)
    '''
    igd = LB_STRUCTURE.game_data_element.value
    isd = LB_STRUCTURE.session_data_element.value

    if structure == LB_STRUCTURE.session_wrapped_player_list:
        player_list = leaderboard[isd]
    elif structure == LB_STRUCTURE.game_wrapped_player_list:
        snaps = leaderboard[igd - 2]
        player_lists = leaderboard[igd]

        if snaps:
            player_list = player_lists[igd]
        else:
            player_list = player_lists
    elif structure == LB_STRUCTURE.game_wrapped_session_wrapped_player_list:
        snaps = leaderboard[igd - 2]
        sessions = leaderboard[igd]

        if snaps:
            # A list of session_wrapped leaderboards
            player_list = sessions[snap][isd]
        else:
            # A single session wrapped leaderboard (extract the player list)
            player_list = sessions[isd]
    elif structure == LB_STRUCTURE.player_list:
        player_list = leaderboard
    else:
        raise ValueError(f"Unsupport leaderboard structure: {structure}")

    return player_list


def player_ratings(leaderboard, structure=LB_STRUCTURE.game_wrapped_session_wrapped_player_list, style=None, snap=0):
    '''
    Returns a dict keyed on player pk, with TrueSkill rating as the value, extracted from the provided leaderboards.

    If there are many leaderboards in the structure the first one is used. This is the case with
    game wrapped leaderboards where the data element is a list of player lists rather than a single
    player list.

    :param leaderboard: A leaderboard with the confessed structure with style LB_PLAYER_LIST_STYLE.data
    :param structure: An LB_STRUCTURE that describes the structure of leaderboard
    :param style: An LB_PLAYER_LIST_STYLE that describes the player style (is guessed form tuple if not confessed)
    :param snap: A snapshot number if it's a game wrapped board with snapshots (snaps)
    '''

    player_list = extract_player_list(leaderboard, structure, style, snap)

    if style is None:
        style = guess_player_list_style(player_list)

    ratings = {}
    for tup in player_list:
        # The player PK is the first element in the tuple except for rich boards, where it's the second
        key = tup[1] if style == LB_PLAYER_LIST_STYLE.rich else tup[0]

        # The player rating is the second element in the tuple except for rich boards, where it's the sixth
        rating = tup[6] if style == LB_PLAYER_LIST_STYLE.rich else tup[1]
        ratings[key] = rating

    return ratings


def player_rankings(leaderboard, structure=LB_STRUCTURE.game_wrapped_session_wrapped_player_list, style=None, snap=0):
    '''
    Returns a dict keyed on player pk, with leaderboard position as the value

    If there are many leaderboards in the structure the first one is used. This is the case with
    game wrapped leaderboards where the data element is a list of player lists rather than a single
    player list.

    :param leaderboard: A leaderboard with the confessed structure with style LB_PLAYER_LIST_STYLE.data
    :param structure: An LB_STRUCTURE that describes the structure of leaderboard
    :param style: An LB_PLAYER_LIST_STYLE that describes the player style (is guessed form tuple if not confessed)
    :param snap: A snapshot number if it's a game wrapped board with snapshots (snaps)
    '''
    player_list = extract_player_list(leaderboard, structure, style, snap)

    if style is None:
        style = guess_player_list_style(player_list)

    positions = {}
    for pos, tup in enumerate(player_list):
        # Always use the first entry in the player tuple as the key except in the rich style (which has it as second spot)
        key = tup[1] if style == LB_PLAYER_LIST_STYLE.rich else tup[0]
        positions[key] = pos

    return positions
