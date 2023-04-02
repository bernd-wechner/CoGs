from enum import Enum
from datetime import timedelta

# TODO: Next round of model enhancements
#
# Add expected play time to Game
# Add a location (lat/lon) field to Location.

# TODO: Use @cached_property in place of @property everywhere. See no reason not to!

# CoGs Leaderboard Server Data Model
#
# The underlying model of data is designed designed to allow:
#
# Game sessions to be recorded by a registrar
# TrueSkill ratings for a player on a game to be calculable from the session records.
# So that leaderboards can be presented for any game in any league (a distinct set of players who are competing)
# Consistent TrueSkill ratings across leagues so that a global leaderboard can be generated as well
# BoardGameGeek connections support for games and players
#
# Note this file defines the data model in Python syntax and a migration (Sync DB)
# converts it into a database schema (table definitions).

MAX_NAME_LENGTH = 200  # The maximum length of a name in the database, i.e. the char fields for player, game, team names and so on.
FLOAT_TOLERANCE = 0.0000000000001  # Tolerance used for comparing float values of Trueskill settings and results between two objects when checking integrity.

# Some reserved names for ALL objects in a model (note ID=0 is reserved for the same meaning).
ALL_LEAGUES = "Global"  # A reserved key in dictionaries used to represent "all leagues" in some requests
ALL_PLAYERS = "Everyone"  # A reserved key for filtering representing all players
ALL_GAMES = "All Games"  # A reserved key for filtering representing all games
ALL_LOCATIONS = "Anywhere"  # A reserved key for filtering representing all locations

# TODO: consider a special league that filters all "My" thins
# So on list views all things I am involved in (my leagues, my games, my players, my locations, my sessions, etc) and on Leaderboards too.
MY_PSEUDO_LEAGUE = "Mine"

MIN_TIME_DELTA = timedelta.resolution  # A nominally smallest time delta we'll consider.

MISSING_VALUE = -1  # Used primarily for PKs (which are  never negative)

#===============================================================================
# Privacy control (interfaces with django_model_privacy_mixin)
#===============================================================================
visibility_options = (
    ('all', 'Everyone'),
    ('share_leagues', 'League Members'),
    ('share_teams', 'Team Members'),
    ('all_is_registrar', 'Registrars'),
    ('all_is_staff', 'Staff'),
)

#===============================================================================
# A structured approach to rating rebuild logging
#
# An approach to defining/recording what triggers a rating rebuild
#===============================================================================
class RATING_REBUILD_TRIGGER(Enum):
    user_request = 0  # A rating rebuild was explicitly requested by an authorized user.
    session_add = 1  # A rating rebuild was triggered by a newly added session
    session_edit = 2  # A rating rebuild was triggered by a session edit
    session_delete = 3  # A rating rebuild was triggered by a session deletion

    choices = (
        (user_request, 'User Request'),
        (session_add, 'Session Add'),
        (session_edit, 'Session Edit'),
        (session_delete, 'Session Delete')
    )

    labels = {c[0]:c[1] for c in choices}

#===============================================================================
# Import the models
#===============================================================================


# Get the app name for getting model classes in model methods
APP = __package__.split('.')[0]

# The order of imports her eis very important because of interdependencies between models
from .trueskillsettings import TrueskillSettings

from .rating import Rating

from .league import League
from .team import Team
from .player import Player

from .location import Location

from .tourney import Tourney, TourneyRules
from .game import Game

from .rank import Rank
from .performance import Performance
from .session import Session

from .event import Event
from .log import RebuildLog, ChangeLog

from .leaderboards import Leaderboard_Cache
