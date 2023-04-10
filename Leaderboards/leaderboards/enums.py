import enum

from collections import OrderedDict

# Some useful enums to use in the options. Really just a way of encapsulating related
# types so we can use them in templates to populate selectors and receive them from
# requests in an orderly way.
#
# They are defined as lists of 2-tuples. The first value in each tuple is the name
# of the enum and typically the value that is used in URLs and in GET and POST
# submissions. The second value is the plain text label that can be used on selector
# on a web page if needed, a more verbose explanation of the selection.

# Player name rendering
# Used for selecting the style client side.
NameSelections = OrderedDict((("nick", "nickname"),
                              ("full", "full name"),
                              ("complete", "full name (nickname)")))

# Link target selection
# Used for selecting the style client side.
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
    '''
    Defines the style of a player list that appears in a leaderboard. The primary styles of importance are data (for storage) and rich (for display).
    leaderboards.style.restyle_leaderboard is used to swap styles on a leaderbaord for storing and for rendering for example etc.

    Note: when the "data" style is used, then anyd session_wrapped_player_list (or game_wrapped_session_wrapped_player_list) includes
          session details and analyses for optional display. These should respect the player list style and can infer it from this style.

          The respect required is simply that player names be removed for storage (so for the data style). They should be replaced by
          a template conveying the PK, that leaderboards.style.restyle_leaderboard can replace by player names in the required format
          (its "names" argument defaulting to "nick" see NameSelections above).
    '''
    none = 0  # An ordered list of names
    data = 1  # An ordered list of tuples (playerid, rating, mu, sigma, plays, wins) - For a data store (can recreate any other style from this)
    rating = 2  # An ordered list of tuples (name, rating)
    ratings = 3  # An ordered list of tuples (name, rating, mu, sigma)
    simple = 4  # An ordered list of tuples (name, rating, mu, sigma, plays, wins)
    rich = 5  # simple plus lots more player info for rendering rich leaderboards (name in all formats, league ids for the player)


class LB_STRUCTURE(enum.Enum):
    '''
    Leaderboards are passed around in a few different structures. We can use this enum to describe a given
    structure to inform a function (that supports it) and where to find the juice, the player list.
    '''
    player_list = 0  # A simple list of player tuples
    session_wrapped_player_list = 1  # A session tuple containing a player_list as an element
    game_wrapped_player_list = 2  # A game tuple containing an player_list as an element
    game_wrapped_session_wrapped_player_list = 3  # A session tuple containing an session_wrapped_player_list as an element

    # This is defined by what Game.wrapped_leaderboard() produces
    game_data_element = 8  # In a game wrapper, which element caries the data (either session wrapper, or player_list)

    # These are defined by what Session.wrapped_leaderboard() produces
    session_players_element = 4  # In a session wrapper, which element contains the list of session players
    session_html_elements = (5, 6, 7) # In a session wrapper, which elemts are HTML that need player name templating and styling
    session_data_element = 8  # In a session wrapper, which element contains the player_list (i.e. the leaderboard)
