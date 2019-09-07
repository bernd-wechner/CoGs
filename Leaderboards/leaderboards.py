import enum, json, sys, numbers

from collections import OrderedDict
from dateutil import parser
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Q, F, ExpressionWrapper, DateTimeField, Count, Subquery, OuterRef, Window
from django.db.models.functions import Lag
from django.utils.formats import localize
from django.utils.timezone import localtime 

if settings.DEBUG:
    from django.db import connection

from django_generic_view_extensions.datetime import fix_time_zone
from django_generic_view_extensions.queryset import top, get_SQL
from django_generic_view_extensions.debug import print_debug 

from Leaderboards.models import Game, League, Player, Session

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
NameSelection             = enum.Enum("NameSelection", NameSelections)
LinkSelection             = enum.Enum("LinkSelection", LinkSelections)

def is_number(s):
    '''
    A simple test to on strig s to see if it's a number or not, for float values
    notable leaderboard_options.num_days and compare_back_to. Which can both come
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
    game_filters = {'games_ex',                  # Exclusively the listed self.games
                    'games_in',                  # Including the listed self.games
                    'top_games',                 # The top (most popular) self.num_games
                    'latest_games',              # The latest self.num_games
                    'game_leagues_any',          # Games played in any of self.game_leagues 
                    'game_leagues_all',          # Games played in all of self.game_leagues
                    'game_players_any',          # Games played by any of self.game_players
                    'game_players_all',          # Games played by all of self.game_players
                    'changed_since',             # Games played since self.changed_since
                    'num_days'}                  # Games played in the last event of self.num_days
    
    # TODO: num_days events should be constrained to same location! And we start calling them events not sessions!
        
    # Options that we accept that will filter the list of players presented on leaderboards 
    # (i.e. define the subset of all players that have played that game) 
    player_filters = {'players_ex',              # Exclusively the listed self.players  
                      'players_in',              # Inlcuding the listed self.players
                      'num_players_top',         # The top self.num_players_top players
                      'num_players_above',       # self.num_players_above players above any players selected by self.players_in
                      'num_players_below',       # self.num_players_below players below any players selected by self.players_in
                      'min_plays',               # Players who have played the game at least self.min_plays times
                      'played_since',            # Players who have played the game since self.played_since
                      'player_leagues_any',      # Players in any of self.player_leagues
                      'player_leagues_all'}      # Players in all of self.player_leagues
    
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
    info_options = {'details', 'analysis_pre', 'analysis_post'}
    
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
    all_options = content_options | presentation_options
   
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
           
    # Now we defione the attributes that back these options up.
    # NOTE: These attributes are not self-standing so to speak but  
    #       relate to 'enabled' as well, which turns thes on or off  
    #       and/or describes how they are to be used (in the case of  
    #       any/all list imperatives. 
        
    # Options that determine which games to list leaderboards for
    # These defaults are used to populate input elements in a form
    # The form should only resybmit them however if they are selected
    # by an accompanying check box.
    games = []                  # Restrict to specified Games
    num_games = 6               # List only this many games (most popular ones or latest based on enabled option)   
    game_leagues = []           # Restrict to games played by specified Leagues (any or all based on enabled option)
    game_players = []           # Restrict to games played by specified players (any or all based on enabled option)
    changed_since = None        # Show only leaderboards that changed since this date
    num_days = 1                # List only games played in the last num_days long event (also used for snapshot definition) 

    # Options that determing which players are listed in the leadrboards
    # These options, like the game selectors, above provide defaults with which to 
    # populate input elements in a form, but they should be presented with accompanying 
    # checkboxes to select them, and if not selected the option should not be subitted.
    players = []                # A list of players to explicitly display (hide all others - except those, that other options request displayed as well)
    num_players_top = 10        # The number of players at the top of leaderboard to show
    num_players_above = 2       # The number of players above selected players to show on leaderboards
    num_players_below = 2       # The number of players below selected players to show on leaderboards
    min_plays = 2               # The minimum number of times a player has to have played this game to be listed
    played_since = None         # The date since which a player needs to have played this game to be listed
    player_leagues = []         # Restrict to players in specified Leagues

    # A perspective option that asks us to think of "current" not as at now, but as at some other time.
    as_at = None                # Do everything as if it were this time now (pretend it is now as_at)

    # Options that determine which snapshots to present for each selected game (above)
    # A snapshot being the leaderboard immediately after a given session.
    # Only one of these can be respected at a time,    
    # compare_back_to is special, it can take one two types of value:
    #    a) a datetime, in which case it encodes a datetime back to which we'd like to have snapshots
    #    b) an integer or float, in which case  it encodes num_days above basically, the length of the last event looking back from as_at which is used to determine a date_time for the query.
    compare_with = 1            # Compare with this many historic leaderboards
    compare_back_to = None      # Compare all leaderboards back to this date (and the leaderboard that was the latest one then)

    # NOTE: The reamining options are not enabled or disabled they always have a value
    #       i.e. are self enabling. 

    # Options for formatting the contents of a given leaderbaords 
    highlight_players = True    # Highlight the players that played the last session of this game (the one that produced this leaderboard)
    highlight_changes = True    # Highlight changes between historic snapshots
    highlight_selected = True   # Highlight players selected in game_players above

    names = NameSelection.nick.name # Render player names like this
    links = LinkSelection.CoGs.name # Link games and players to this target

    # Options to include extra info in a leaderboard header
    details = False             # Show session details atop each boards (about the session that produced that board)
    analysis_pre = False        # Show the TrueSkill Pre-session analysis 
    analysis_post = False       # Show the TrueSkill Post-session analysis

    # Options for laying out leaderboards on screen 
    cols = 3                    # Display boards in this many columns (ignored when comparing with historic boards)

    # Admin Options 
    ignore_cache = False
    
    # NOT YET IMPLEMENTED
    # Consider: could be a list of players, could be a bool like hightlight_players
    # and use the players list.
    trace = []                  # A list of players to draw trace arrows for from snapshot to snapshot
    
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

    def __init__(self, session={}, request={}):
        '''
        Build a leaderboard options instance populated with options froma request dictionary
        (could be from request.GET or request.POST). If none is specified build with default 
        values, i.e.e do nothing here (defaults are specified in attribute declaratons above) 
        
        :param session: a request.session.filter dictionary that spectified the session default.
                        currently only 'league' is used to populate the options with a default
                        league filter based on session preferences. Is extensible.
                        
        :param request: a request.GET or request.POST dictionary that contains options.
        '''

        def decodeDateTime(dt):
            '''
            decodes a DateTime that was URL encoded. 
            Has to agree with the URL encoding chosen by the Javascript that 
            fetches leaderboards though an AJAX call of course.
            
            The colons are encoded as : - Works on Chrome even though it's 
            a reserved character not encouraged for URL use. 
            
            The space between date and time is encoded as + and so arrives
            as a space. 
            
            A - introducing the timezone passes through unencoded.
            
            A + introducing the timezone arrives here as a space
            
            Just in case : in the URL does cause an issue, up front we'll
            support - which travels undamaged from URL to here, as the 
            hh mm ss separator.
            
            All the while we are using the ISO 8601 format for datetimes,
            or encoded versions of it that we try to decode here.
            
            ref1 and ref 2 are ISO 8601 datetimes with and without timezone
            used do our work here.                         
            '''
            ref1 = "2019-03-01 18:56:16+1100"
            ref2 = "2019-03-01 18:56:16"
            
            # strigs are immutable and we need to listify them to 
            # make character referenced substitutions
            new = list(dt)
            
            if not (len(dt) == len(ref1) or len(dt) == len(ref2)):
                return dt
            
            if len(dt) == len(ref1):
                if dt[-5] == " ":
                    new[-5] = "+"

            if dt[13] == "-":
                new[13] = ":"

            if dt[16] == "-":
                new[16] = ":"

            # The n stringify the list again. 
            return "".join(new)

        # If we have a options submitted then don't use the default 
        # enabled list respect the incoming options instead.
        
        have_options = False
        for item in request: 
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
        if have_options or "no_defaults" in request:
            self.enabled = set()
            
        # A very special case for the two snapshot options. They are not enabled
        # like the filters. There are two, compare_with and compare_back_to only
        # one of which can't should be set. We can only respect one. So if we get 
        # on in the request we should anull the other.
        #
        # If both are supplied we need of course to ignore one. Matters no which, 
        # but only one can be respected 
        if "compare_back_to" in request:
            self.compare_with = 0
        elif "compare_with" in request:
            self.compare_back_to = None
            
        # Keeping the same order as the properties above and recommended for
        # form fields and the JS processor of those field ...
        
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
        games = None
        self.need_enabling.add('games_ex')          
        self.need_enabling.add('games_in')
        for suffix in ("ex", "in"):
            if f'games_{suffix}' in request:        
                games = request[f'games_{suffix}'].split(",")  
                ex_in = suffix 
                break

        if games:
            # Validate the games discarding any invalid ones
            self.games = []
            for game in games:
                if Game.objects.all().filter(pk=game).exists():
                    self.games.append(game)        
        
            self.__enable__(f'games_{ex_in}', self.games)

        # A number of games if submitted request that we list no
        # more than that many games (the top games when sorted by
        # some measure of popularity or the latest play times - 
        # ideally within the selected leagues (i.e. global popularity 
        # is of no interest to a given league or leagues) 
        self.need_enabling.add('top_games')          
        self.need_enabling.add('latest_games')          
        if 'top_games' in request and request['top_games'].isdigit():
            self.num_games = int(request["top_games"])
            self.__enable__('top_games', self.num_games)            
        elif 'latest_games' in request and request['latest_games'].isdigit():
            self.num_games = int(request["latest_games"])
            self.__enable__('latest_games', self.num_games)            

        # We can acccept leagues in an any or all form but
        # above all we have a fallback to the session specified
        # default filter if neither is specified. We support 
        # specifying an empty valye of either to avoid applying
        # the sessioni default, an explicit rewuest for no
        # league filtering     
        self.need_enabling.add('game_leagues_any')          
        self.need_enabling.add('game_leagues_all')
        preferred_league = None          
        if 'game_leagues_any' in request:
            if request['game_leagues_any']:
                leagues = request['game_leagues_any'].split(",")
            else:
                leagues = None
        elif 'game_leagues_all' in request:
            if request['game_leagues_all']:
                leagues = request['game_leagues_all'].split(",")
            else:
                leagues = None
        elif not request:
            preferred_league = session.get('league', None)
            leagues = [preferred_league] if preferred_league else []
        else:
            leagues = None
            
        if leagues:   
            # Validate the leagues  discarding any invalid ones
            self.game_leagues = []
            for league in leagues:
                if League.objects.all().filter(pk=league).exists():
                    self.game_leagues.append(league)

            # We need to enable one of these for each of the three posible outcomes above,
            # An explicti request for any league, all leagues or a fallback on preferred league.
            self.__enable__('game_leagues_any', self.game_leagues and ('game_leagues_any' in request or preferred_league))
            self.__enable__('game_leagues_all', self.game_leagues and 'game_leagues_all' in request)

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
        if 'game_players_any' in request:
            players = request['game_players_any'].split(",")
        elif 'game_players_all' in request:
            players = request['game_players_all'].split(",")
        else:
            players = [] # # Must be a a Falsey value

        if players:
            # Validate the players discarding any invalid ones
            self.game_players = []
            for player in players:
                if Player.objects.all().filter(pk=player).exists():
                    self.game_players.append(player)

            self.__enable__('game_players_any', self.game_players and 'game_players_any' in request)
            self.__enable__('game_players_all', self.game_players and 'game_players_all' in request)
            
        # In case one or the other was enabled in the defaults above, if we lack any players we ensure they are both disabled
        else:
            self.__enable__('game_players_any', False)
            self.__enable__('game_players_all', False)

        # If a date is submitted (and parses validly) this asks us to list only
        # games that have a recorded play session after that date (exclude games 
        # not played since them).
        self.need_enabling.add('changed_since')          
        if 'changed_since' in request:
            try:
                self.changed_since = fix_time_zone(parser.parse(decodeDateTime(request['changed_since'])))
            except:
                self.changed_since = None # Must be a a Falsey value

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
        if 'num_days' in request and is_number(request['num_days']):
            self.num_days = float(request["num_days"])
            self.__enable__('num_days', self.num_days)

        ##################################################################
        # PLAYER FILTERS
        #
        # Now we capture the player filters. That is the options that 
        # restrict which players we present on the boards.

        # A comma separated list of players if submitted flags a request
        # to show thos players only (exlusive) or at least those players 
        # (inclusive). The option specifies the context and only one of 
        # them can be specified at a time with any sense. 
        players = None
        self.need_enabling.add('players_ex')
        self.need_enabling.add('players_in')
        for suffix in ("ex", "in"):
            if f'players_{suffix}' in request:        
                players = request[f'players_{suffix}'].split(",")  
                ex_in = suffix 
                break

        if players:
            # Validate the players discarding any invalid ones
            self.players= []
            for player in players:
                if Player.objects.all().filter(pk=player).exists():
                    self.players.append(player)                       
        
            self.__enable__(f'players_{ex_in}', self.players)
            
        # If "players" is an empty list fall back on the game_players if they
        # were submitted. This enables a URL like:
        #   ?game_players_any=1,2,3&players_ex
        # where the empty players_ex list falls back on 1,2,3
        elif self.game_players:
            # Already validated list of players
            self.players = self.game_players
            self.__enable__(f'players_{ex_in}', self.players)
        
        # Then an option to discard all but the top num_players of each board
        # As the starting point. Other options can add players of course, this 
        # is not exclusive of other player selecting options.
        self.need_enabling.add('num_players_top')          
        if 'num_players_top' in request and request['num_players_top'].isdigit():
            self.num_players_top = int(request["num_players_top"])
            self.__enable__('num_players_top', self.num_players_top)                            
       
        # Here we're requesting to provide context to the self.players that
        # are showing on the list. We may want to see a player or two or more 
        # above and/or below them. 
        self.need_enabling.add('num_players_above')          
        if 'num_players_above' in request and request['num_players_above'].isdigit():
            self.num_players_above = int(request["num_players_above"])
            self.__enable__('num_players_above', self.num_players_above)                            

        self.need_enabling.add('num_players_below')          
        if 'num_players_below' in request and request['num_players_below'].isdigit():
            self.num_players_below = int(request["num_players_below"])
            self.__enable__('num_players_below', self.num_players_below)                            
        
        # TODO: Can we support and/or combinations of min_plays, played_since and leagues_any/all?
        
        # Now we request to include players who have played at least a 
        # few times.
        self.need_enabling.add('min_plays')          
        if 'min_plays' in request and request['min_plays'].isdigit():
            self.min_plays = int(request["min_plays"])
            self.__enable__('min_plays', self.min_plays)                            

        # Now we request to include only players who have played the game
        # recently enough ... 
        self.need_enabling.add('played_since')          
        if 'played_since' in request:
            try:
                self.played_since = fix_time_zone(parser.parse(decodeDateTime(request['played_since'])))
            except:
                self.played_since = None  # Must be a a Falsey value        

            self.__enable__('played_since', self.played_since)                            
        
        # We support a league filter, as with games, and again with an any or all
        # logical operation requested. We also support reference values to the
        # possibly already supplied game_leagues_any or game_leagues_all.
        self.need_enabling.add('player_leagues_any')          
        self.need_enabling.add('player_leagues_all')          
        if 'player_leagues_any' in request:
            if request['player_leagues_any']:
                leagues = request['player_leagues_any'].split(",")
            else:
                leagues = None
        elif 'player_leagues_all' in request:
            if request['player_leagues_all']:
                leagues = request['player_leagues_all'].split(",")
            else:
                leagues = None
        elif not request:
            preferred_league = session.get('league', None)
            leagues = [preferred_league] if preferred_league else []
        else:
            leagues = None
            
        if leagues:
            # Validate the leagues discarding any invalid ones
            self.player_leagues = []
            for league in leagues:
                if League.objects.all().filter(pk=league).exists():
                    self.player_leagues.append(league)

            # We need to enable one of these for each of the three posible outcomes above,
            # An explicti request for any league, all leagues or a fallback on preferred league.
            self.__enable__('player_leagues_any', self.player_leagues and ('player_leagues_any' in request or preferred_league))                            
            self.__enable__('player_leagues_all', self.player_leagues and 'player_leagues_all' in request)                            

        elif ('player_leagues_any' in request  or 'player_leagues_all' in request) and self.game_leagues:
            # Already validated list of players
            self.player_leagues = self.game_leagues

            # We need to enable one of these for each of the three posible outcomes above,
            # An explicti request for any league, all leagues or a fallback on preferred league.
            self.__enable__('player_leagues_any', self.player_leagues and ('player_leagues_any' in request or preferred_league))                            
            self.__enable__('player_leagues_all', self.player_leagues and 'player_leagues_all' in request)
        
        # In case one or the other was enabled in the defaults above, if we lack any leagues we ensure they are both disabled
        else:                            
            self.__enable__('player_leagues_any', False)                            
            self.__enable__('player_leagues_all', False)
        
        # Now we capture the persepctive request if it provides a valid datetime
        self.need_enabling.add('as_at')          
        if 'as_at' in request:
            try:
                self.as_at = fix_time_zone(parser.parse(decodeDateTime(request['as_at'])))
            except:
                self.as_at = None  # Must be a a Falsey value
                
            self.__enable__('as_at', self.as_at)                            
                
        ##################################################################
        # EVOLUTION OPTIONS
        #
        # Now the evolution options. These are simpler as we can onjly specify one
        # method of selecting which snapshots to display. Compare_back_to is special
        # beast though as we record it as an int or a datetime. The latter is an explict
        # request back to time, and the former is a num_days request for a session
        # impact presentation where the session is chosed by looking back from the current 
        # leaderboard (latest or as_at) this many days and finding relevant snapshots in that
        # window.
        self.need_enabling.add('compare_with')          
        self.need_enabling.add('compare_back_to')          
        if 'compare_with' in request and request['compare_with'].isdigit():
            self.compare_with = int(request['compare_with'])            
            self.__enable__('compare_with', self.compare_with)                            
            self.__enable__('compare_back_to', False)                            
            
        elif 'compare_back_to' in request:
            if is_number(request['compare_back_to']):
                self.compare_back_to = float(request['compare_back_to'])
            else:
                try:
                    self.compare_back_to = fix_time_zone(parser.parse(decodeDateTime(request['compare_back_to'])))
                except:
                    self.compare_back_to = None  # Must be a a Falsey value
                    
            self.__enable__('compare_back_to', self.compare_back_to)                            
            self.__enable__('compare_with', False)                            
                    

        ##################################################################
        # INFO OPTIONS

        # Options to include extra info in a leaderboard header
        if 'details' in request:
            self.details = json.loads(request['details'].lower()) # A boolean value is parsed
        # else use the default value     
    
        if 'analysis_pre' in request:
            self.analysis_pre = json.loads(request['analysis_pre'].lower()) # A boolean value is parsed     
    
        if 'analysis_post' in request:
            self.analysis_post = json.loads(request['analysis_post'].lower()) # A boolean value is parsed
    
        ##################################################################
        # HIGHLIGHT OPTIONS

        # Options for formatting the contents of a given leaderbaords 
        if 'highlight_players' in request:
            self.highlight_players = json.loads(request['highlight_players'].lower()) # A boolean value is parsed
             
        if 'highlight_changes' in request:
            self.highlight_changes = json.loads(request['highlight_changes'].lower()) # A boolean value is parsed

        if 'highlight_selected_players' in request:
            self.highlight_selected_players = json.loads(request['highlight_selected_players'].lower()) # A boolean value is parsed
        
        ##################################################################
        # FORMATTING OPTIONS

        if 'names' in request:
            self.names = NameSelection[request['names']]
        
        if 'links' in request: 
            self.links = LinkSelection[request['links']]

        # Options for laying out leaderboards on screen 
        if 'cols' in request:
            self.cols = request['cols']

        # YET TO BE IMPLEMENTED OPTIONS - draw arrows between leaderboards for the listed players.
        if 'trace' in request:
            self.trace = request['trace'].split(",")

        # A special option which isn't an option per se. If passed in we make
        # the provided options as static as we can with self.make_static()            
        if 'make_static' in request:
            self.make_static()
            self.made_static = True

        ##################################################################
        # ADMIN OPTIONS
        if 'ignore_cache' in request:
            self.ignore_cache = True
            
        if settings.DEBUG:
            print_debug(f"Enabled leaderboard options: {self.enabled}")                         

    def has_player_filters(self):
        '''
        Returns True if any player filters are enabled, else False
        '''
        return ( self.is_enabled('players_ex') 
              or self.is_enabled('players_in') 
              or self.is_enabled('num_players_top') 
              or self.is_enabled('num_players_above')
              or self.is_enabled('num_players_below')
              or self.is_enabled('min_plays')
              or self.is_enabled('played_since')
              or self.is_enabled('player_leagues_any')
              or self.is_enabled('player_leagues_all') )
    
    def player_nominated(self, player_pk):
        '''
        Returns True if a player was nominated specifically to be listed.        
        '''
        return (self.is_enabled('players_in') or self.is_enabled('players_ex')) and str(player_pk) in self.players

    def player_ok(self, player_pk, plays, last_play, league_pks):
        '''        
        Returns True if a player with the specified properties passes the criteria specified
        for them. 
        '''
        # We always inclide players we've explicitly requested
        if self.is_enabled('players_in') and str(player_pk) in self.players:
            return True

        # If not explicitly selected then a player must satisfy anys pecified league criteria
        # or else they won't be listed.
        league_pks = [str(pk) for pk in league_pks]  # We force them to strings as we stored strings in self.player_leagues 
        if self.is_enabled('player_leagues_any') and not set(league_pks) & set(self.player_leagues):
            return False
        elif self.is_enabled('player_leagues_all') and not set(league_pks) == set(self.player_leagues):
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
            return any(criteria) # Empty any list is False, as desired 
        else:
            return all(criteria) # Empty all list is True, as desired

    def no_evolution(self):
        '''
        Returns True if no evolution options are enabled. 
        '''
        return not ( self.is_enabled('compare_with') or self.is_enabled('compare_back_to') )

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
            lbf = []   # A player-filtered version of leaderboard 

            for p in leaderboard:
                # Fetch data from the tuple
                rank = p[0]
                pk = str(p[1])   # Force to string as self.players is a list of string pks
                plays = p[9]
                last_play = p[11]
                leagues = p[12] 
                
                # If an exlusive player list is enabled respect that
                if self.is_enabled('players_ex'):
                    if pk in self.players:
                        lbf.append(p)
                    continue
                
                # Apply remaining citeria one by one
                
                # List top N players regardless of who they are
                if self.is_enabled('num_players_top') and len(lbf) < self.num_players_top:
                    lbf.append(p)
                    continue

                # For the rest of the list we check if the player is ok by the filters                   
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
                
                d[attr] = val
        
        return d

    def last_session_time(self):
        '''
        Returns a lazy Queryset that when evaluated produces the date_time of the 
        last session played given the current options sepcifying league and perspective.
        This is irrespective of the game, and is intended for the given league or leagues
        to retrun the last time of any activity as a reference for most recent event
        calculation.
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
            
        session_times = Session.objects.filter(s_filter).values('date_time').order_by("-date_time")
        latest_session_time = top(session_times, 1)
        
        if settings.DEBUG:
            queries_after = len(connection.queries)

            print_debug("last_session_time:")
            
            if queries_after == queries_before:
                print_debug("\tSQL is still LAZY")
                print_debug(f"\t{get_SQL(latest_session_time)}")
            else:
                print_debug("\tSQL was evaluated!")
                print_debug(f"\t{connection.queries[-1]['sql']}")
        
        return latest_session_time

    def last_event_start_time(self, delta_days, as_ExpressionWrapper=True):
        '''
        Returns an Expression that can be used in filtering sessions that is the date_time 
        of the ostensible start of the event. Being the date_time of the last session this 
        league or these leugues playered less the number of days provided as an in the value
        delta_days. This could self.num_days for the game filtering or self.compare_back_to 
        for snapshot capture.
        '''
        if as_ExpressionWrapper:
            lest = ExpressionWrapper(Subquery(self.last_session_time()) - timedelta(days=delta_days), output_field=DateTimeField())
        else:
            lest = self.last_session_time()[0]['date_time'] - timedelta(days=delta_days)
            
        return lest

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
        
        # First restrict the list ot exclusively specified games if present
        # If an exclusive list of games is provided we return just those
        if self.is_enabled('games_ex'):
            g_filter &= Q(pk__in=self.games)
        
        # Restrict the list based on league memberships
        if self.is_enabled('game_leagues_any'):
            g_filter = Q(sessions__league__pk__in=self.game_leagues) 
            s_filter = Q(league__pk__in=self.game_leagues) 
        elif self.is_enabled('game_leagues_all'):
            for pk in self.game_leagues:
                g_filter &= Q(sessions__league__pk=pk)
                s_filter &= Q(league__pk=pk)

        # Respect the perspective request when finding last_play of a game 
        # as in last_play before as_at
        if self.is_enabled('as_at'):
            s_filter &= Q(date_time__lte=self.as_at)
                
        # We sort them by a measure of popularity (within the selected leagues)
        #
        # TODO: last_play is within the specified leagues (via s_filter)
        #       session_count and play_count are not. They need to be.
        
        latest_session = top(Session.objects.filter(s_filter).filter(game=OuterRef('pk')).order_by("-date_time"), 1)
        last_play = Subquery(latest_session.values('date_time'))
        session_count = Count('sessions', distinct=True)
        play_count = Count('sessions__performances', distinct=True)

        games = (Game.objects.filter(g_filter)
                             .annotate(last_play=last_play)
                             .annotate(session_count=session_count)
                             .annotate(play_count=play_count)
                             .filter(session_count__gt=0))

        # Now build up gfilter based on the game selectors
        # 
        # We want to include a game if it matches ANY of"
        #
        # changed_since, 
        # game_players_any or game_players_all
        
        or_filters = Q()

        if self.is_enabled('changed_since'):
            or_filters |= Q(sessions__date_time__gte=self.changed_since)
    
        # TODO Test this any/all implementation well
        if self.is_enabled('game_players_any'):
            or_filters |= Q(sessions__performances__player__pk__in=self.players)
        elif self.is_enabled('game_players_all'):
            and_players = Q()
            for pk in self.players:
                and_players &= Q(sessions__performances__player__pk=pk)
                
            or_filters |= and_players

        gfilter = or_filters

        if self.is_enabled('num_days'):
            reference_time = self.last_event_start_time(self.num_days)
            gfilter &= Q(sessions__date_time__gte=reference_time )

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
            order_games_by = ('-play_count','-session_count')
            
        # Apply the game selector(s)
        filtered_games = games.filter(gfilter).order_by(*order_games_by).distinct()
        
        # Taking the top num_games of course happens last (after all other filters applied)
        # TODO: Must it? Do we want to take the top n games and then apply the filters? Or
        #       be able to choose. This is a classic prioritsiation question on the options.  
        if self.is_enabled('top_games') or self.is_enabled('latest_games'):
            filtered_games = top(filtered_games, self.num_games)
            
        # Now if we have a games_in rquest we want to include those games explicilty
        if self.is_enabled('games_in'):
            filtered_games = filtered_games.union(
                                Game.objects.filter(pk__in=self.games)                             
                                            .annotate(last_play=last_play)
                                            .annotate(session_count=session_count)
                                            .annotate(play_count=play_count)
                                ).order_by(*order_games_by)
                                        
        if settings.DEBUG:
            queries_after = len(connection.queries)

            print_debug("GAME SELECTOR:")
            
            if queries_after == queries_before:
                print_debug("\tSQL is still LAZY")
                print_debug(f"\t{get_SQL(filtered_games)}")
            else:
                print_debug("\tSQL was evaluated!")
                print_debug(f"\t{connection.queries[-1]['sql']}")
            
            print_debug("SELECTED GAMES:")
            for game in filtered_games:
                print_debug(f"\t{game.name}")
            
        return filtered_games
  
    def snapshot_queryset(self, game):
        '''
        Returns a QuerySet of the Session objects which which provide the foundation
        for historic snapshots selcted by these options (self.evolution_options drive
        this).
        
        As a QuerySet this should ideal remain unevaluated on return (remain lazy).
        
        A snapshot is the leaderboard as it appears after a given game session
        The default and only standard snapshot is the current leaderboard after the 
        last session of the game.
        
        But this can be altered by:
        
        A perspective request:
           lo.as_at which asks for the leaderboard as at a given time (not the latest one)
         
        Evolution requests:
           lo.EvolutionSelections documents the possible selections
               
        We build a QeurySet of the sessions after which we want the leaderboard snapshots.        
        '''
        if settings.DEBUG:
            queries_before = len(connection.queries)
        
        # Start our Session filter with sessions for the game in question
        sfilter = Q(game=game)
        
        # Respect the game_leagues filter 
        # This game may be played by different leagues 
        # and we're not interested in their sessions
        # TODO: TEST this all/any implementation!
        if self.is_enabled('game_leagues_any'):
            sfilter &= Q(league__pk__in=self.game_leagues)
        elif self.is_enabled('game_leagues_all'):
            for pk in self.game_leagues:
                sfilter &= Q(league__pk=pk)

        # Respect the perspective request
        if self.is_enabled('as_at'):
            sfilter &= Q(date_time__lte=self.as_at)

        # At this stage we have sfilter (a filter on sessions that
        #   Specifies a game
        #   Respects and league constraints specified
        #   Respects any perspective constraint supplied

        if (self.no_evolution()):
            # Just get the latest session, one snapshot only
            sessions = top(Session.objects.filter(sfilter).order_by("-date_time"), 1)
        else:
            extra_session = None
            
            sessions = Session.objects.all()
            
            # Respect the evolution options where enabled
            if self.is_enabled('compare_back_to'):
                # We want one extra session, the one just before the reference time.
                # This is a new QuerySet which we'll Union with the main one. We
                # want to find it just before we restrict sfilter as we'd like to
                # respect sfilter to date. It specified a game at least, possibly 
                # league constraints on the sessions and a perspective constraint.                                
                if self.is_enabled('compare_back_to'):
                    if isinstance(self.compare_back_to, numbers.Real):
                        reference_time = self.last_event_start_time(self.compare_back_to)
                    elif isinstance(self.compare_back_to, datetime):
                        reference_time = self.compare_back_to
                    else:
                        reference_time = None

                if reference_time:
                    extra_session = top(sessions.filter(sfilter & Q(date_time__lt = reference_time)), 1)
                    sfilter &= Q(date_time__gte = reference_time)
            
            # Then order the sessions in reverse date_time order  
            sessions =  sessions.filter(sfilter).order_by("-date_time")
            
            if extra_session:
                sessions = sessions.union(extra_session).order_by("-date_time")
    
            # Keep on respecting the evolution options where enabled
            if self.is_enabled('compare_with'):
                # This encodes a number of sessions so the top n on the temporally ordered
                sessions = top(sessions, 1+self.compare_with)
                
        if settings.DEBUG:
            queries_after = len(connection.queries)

            print_debug("SNAPSHOT SELECTOR:")
            
            if queries_after == queries_before:
                print_debug("\tSQL is still LAZY")
                print_debug(f"\t{get_SQL(sessions)}")
            else:
                print_debug("\tSQL was evaluated!")
                print_debug(f"\t{connection.queries[-1]['sql']}")
                
            print_debug("SELECTED SNAPSHOTS:")
            for session in sessions:
                print_debug(f"\t{session.date_time}")

        return sessions
            
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
            
        TODO: COnsider what happens on games_ex and players_ex 
        '''
        
        # Build A Leagues intro string
        if self.is_enabled('game_leagues_any') or self.is_enabled('game_leagues_all'):
            L = League.objects.filter(pk__in=self.game_leagues)
            La = "any" if self.is_enabled('game_leagues_any') else "all"
        else:
            L = []
            
        LA = f"{La} of the leagues" if len(L) > 1 else "the league" 
    
        # Build A Players intro string
        if self.is_enabled('game_players_any') or self.is_enabled('game_players_all'):
            P = Player.objects.filter(pk__in=self.game_players)
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
        
        # Build the list of leagues capping at two items with elipsis if more.
        if len(P) == 1:
            p = P[0].name_nickname 
        elif len(L) == 2:
            p = f"{P[0].name_nickname} and {P[1].name_nickname}"
        elif len(L) > 2:
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
    
        return (title, "<BR>".join(subtitle))

    def make_static(self):
        '''
        Make the relative leaderboard_options more static. Specifically the event based ones.
        
        It's hard to secure a perfectlys tatic leaderboards link becasue anything could change
        in the database over time, players come and go, games come and go whatever, there are
        just too many variables and the closes we could get really is to store the cache that
        is currently stored in the session in a more persistent database table with an ID. 
        
        But can't see much need for that yet. Right now the main aim is that we can rapidly 
        get the impact of the last evert (prior to as_at) but produce a link that uses 
        fixed reference times rather than the relative so they can be used in comms and 
        have lasting relevance.
       
        TODO: add a button to top row on leaderboards page which is of a chain link, and when 
        clicked, resubmits current view via this, returning a static rendition of it.
        
        TODO: add a button beside it to show the link in the Address bar (get it out of advanced).
        Need a clear icon for that. Could be an eye with some hint of a URLness to it?
        
        Both can have excellent ToolTips of course.
        '''
        
        # Map self.num_days to self.changed_since
        if self.is_enabled('num_days'):
            self.changed_since = self.last_event_start_time(self.num_days, as_ExpressionWrapper=False)            
            self.__enable__('changed_since', True)
            self.__enable__('num_days', False)
            
        # Map self.compare_back_to number to self.compare_back_to datetime
        if self.is_enabled('compare_back_to') and isinstance(self.compare_back_to, numbers.Real):
            self.compare_back_to = self.last_event_start_time(self.compare_back_to, as_ExpressionWrapper=False)            
