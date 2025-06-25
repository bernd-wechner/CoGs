import json

#from django.core import management
from django.db import connection
from django.apps import apps
from django.urls import reverse
from django.test import TestCase
from django.test.client import RequestFactory
from django.contrib.auth import get_user_model
from django.core.management import call_command

from io import StringIO
from dateutil import parser
from datetime import datetime
from crequest.middleware import CrequestMiddleware

from django_rich_views.datetime import make_aware

from Leaderboards.models import Game, Player, League, Location, Tourney, Session, Rank, Performance, Team
from Leaderboards.leaderboards.options import leaderboard_options

def clean_session_args(game, players,
                       ranking=None,
                       date_time=None,
                       league=None,
                       location=None,
                       ppw=None,
                       rscores=None,
                       pscores=None):
    '''
    A standard form of session creation args is used for creating a DB session or session add or edit posts.

    The methods using that work better with confidently cleaned data, so this is a DRY block that implements
    the cleaning and returns the same set, cleaned up.

    :param game: A Game object or The name of a game (will be fetched by name)
    :param players: A list or list of lists of Player objects or players by name (individuals)
    :param ranking: A list of ranking value (one per player or team)
    :param date_time: a datetime string, will be parsed
    :param league: A League object or league name (will be fetched by name)
    :param location: A Location object or location name (will be fetched by name)
    :param ppw: Partial play weightings for the players (in same structure as players, list of floats, or list of lists of floats)
    :param rscores: Rank scores (0-1) as a list, one per rank
    :param pscores: Performance scores (0-1) as a list or list of lists (in same structure as players)
    '''
    # TestCase asertions are instance methods not class methods so to fire one during
    # SetUp we need an instance.
    self = TestCase()

    # Get game
    self.assertTrue(isinstance(game, (str, Game)))
    if isinstance(game, str):
        game = Game.objects.get(name=game)

    # Get the players
    self.assertTrue(isinstance(players, (list, tuple)))
    self.assertTrue(len(players) > 1)
    if isinstance(players[0], (list, tuple)):
        team_play = True
        for t in players:
            self.assertTrue(isinstance(t, (list, tuple)))
            for p in t:
                self.assertTrue(isinstance(p, (str, Player)))
    elif isinstance(players[0], (str, Player)):
        team_play = False
        for p in players:
            self.assertTrue(isinstance(p, (str, Player)))
    else:
        self.fail("create_session: players must be a list of lists or Player objects or strings")

    if team_play:
        for i, t in enumerate(players):
            for j, p in enumerate(t):
                if not isinstance(players[i][j], Player):
                    players[i][j] = Player.objects.get(name_nickname=p)  # @UndefinedVariable
    else:
        players = list(players)  # coerce to list (if it was a tuple)
        for i, p in enumerate(players):
            if not isinstance(players[i], Player):
                players[i] = Player.objects.get(name_nickname=p)  # @UndefinedVariable

    # Get the rankings
    if ranking is None:
        ranking = [None for p in players]
    else:
        self.assertTrue(len(ranking) == len(players))

    # Get the datetime
    if date_time is None:
        date_time = datetime.now()
    else:
        self.assertTrue(isinstance(date_time, (datetime, str)))
        if isinstance(date_time, str):
            date_time = make_aware(parser.parse(date_time))

    # Get the League (by name)
    if league is None:
        league = League.objects.get(pk=1)
    else:
        self.assertTrue(isinstance(league, (str, League)))
        if isinstance(league, str):
            league = League.objects.get(name=league)

    # Get the Location (by name)League
    if location is None:
        location = Location.objects.get(pk=1)
    else:
        self.assertTrue(isinstance(location, (str, Location)))
        if isinstance(location, str):
            location = Location.objects.get(name=location)

    # Get the Partial Play Weightings
    if ppw is None:
        if team_play:
            ppw = [[1.0 for p in players[i]] for t in players]
        else:
            ppw = [1.0 for p in players]
    else:
        if team_play:
            for t in players:
                for p in t:
                    self.assertTrue(isinstance(p, (int, float)))
                    self.assertTrue(p >= 0)
                    self.assertTrue(p <= 1)
        else:
            for p in players:
                self.assertTrue(isinstance(p, (int, float)))
                self.assertTrue(p >= 0)
                self.assertTrue(p <= 1)

    # Get the Rank scores
    if rscores is None:
        rscores = [None for r in ranking]
    else:
        for i, r in enumerate(ranking):
            self.assertTrue(isinstance(rscores[i], int))
            self.assertTrue(rscores[i] > 0)

    # Get the Performance scores
    if pscores is None:
        if team_play:
            pscores = [[None for p in players[i]] for t in players]
        else:
            pscores = [None for p in players]
    else:
        if team_play:
            for i, t in enumerate(players):
                for j, p in enumerate(t):
                    self.assertTrue(isinstance(pscores[i][j], int))
                    self.assertTrue(pscores[i][j] >= 0)
        else:
            for i, p in enumerate(players):
                self.assertTrue(isinstance(pscores[i], int))
                self.assertTrue(pscores[i] >= 0)

    # Return the same args cleaned as well as the derived team_play flag
    return(game, players, ranking, date_time, league, location, ppw, rscores, pscores, team_play)

def create_session(game, players,
                   ranking=None,
                   date_time=None,
                   league=None,
                   location=None,
                   ppw=None,
                   rscores=None,
                   pscores=None):
    '''
    Creates a session in the database.

    Sessions are a rich object cioplued with instances of Rank, Performance and maybe Team
    And so one method to easily create one supports creation of a series of them in tests.

    :param game: A Game object or The name of a game (will be fetched by name)
    :param players: A list or list of lists of Player objects or players by name (individuals)
    :param ranking: A list of ranking values (one per player or team)
    :param date_time: a datetime string, will be parsed
    :param league: A League object or league name (will be fetched by name)
    :param location: A Location object or location name (will be fetched by name)
    :param ppw: Partial play weightings for the players (in same structure as players, list of floats, or list of lists of floats)
    :param rscores: Rank scores (0-1) as a list, one per rank
    :param pscores: Performance scores (0-1) as a list or list of lists (in same structure as players)
    '''
    # Clean the args
    game, players, ranking, date_time, league, location, ppw, rscores, pscores, team_play = clean_session_args(
    game, players, ranking, date_time, league, location, ppw, rscores, pscores)

    session = Session.objects.create(game=game,  # @UndefinedVariable
                                     date_time=date_time,
                                     league=league,
                                     location=location,
                                     team_play=team_play)

    if team_play:
        # Create the teams
        # Create the ranks for each team
        # Create the performances for eack player
        for i, t in enumerate(players):
            team = Team.get_create_or_edit(t, debug=True)

            rank = Rank.objects.create(session=session,
                                       rank=ranking[i],
                                       score=rscores[i],
                                       team=team)
            rank.save()
            for j, p in enumerate(players[i]):
                performance = Performance.objects.create(session=session,  # @UndefinedVariable
                                                         player=p,
                                                         score=pscores[i][j],
                                                         partial_play_weighting=ppw[i][j])
                performance.save()
    else:
        # Create the ranks for eack player
        # Create the performances for eack player
        for i, p in enumerate(players):
            rank = Rank.objects.create(session=session,
                                       rank=ranking[i],
                                       score=rscores[i],
                                       player=p)
            rank.save()

            performance = Performance.objects.create(session=session,  # @UndefinedVariable
                                                     player=p,
                                                     score=pscores[i],
                                                     partial_play_weighting=ppw[i])
            performance.save()

    # Calculate and save all the TrueSkill impacts in the session
    # If sessions are not created in temporal order this should
    # call Rating.rebuild() to rebuild them
    try:
        session.calculate_trueskill_impacts()
    except:
        session.calculate_trueskill_impacts()

    return session

class TestCaseWithDB(TestCase):

    def dummy_request(self, user):
        '''
        Adds a dummy request to the TestCase which is needed by CrequestMiddleware to get
        the requesting user which djnago_admin_fields requires to write the admin files (created_by etc)

        So a quick way to dummy up a request that has this user attribute is useful for creating the
        database entries

        :param user: A User model object
        '''
        # CrequestMiddleware is used to admin fields when objects are created
        # It needs a request object with a user attribute.
        self.request_factory = RequestFactory()
        rqt = self.request_factory.get('/')
        rqt.user = self.user = user
        self.request = rqt
        CrequestMiddleware.set_request(self.request)

    def JSON_response(self, view_name, get=""):
        '''
        Clean way to get a JSON response from the server
        :param view_name:
        :param get:
        '''
        return json.loads(self.client.get(reverse(view_name)+get).content.decode())

    def login_as(self, user):
        '''
        A function to log in as a given user cleanly.

        :param user: A User model object
        '''
        self.client.force_login(user)
        lid = user.player.league.id

        s = self.client.session
        s.update({"filter": {"league": lid}})
        s.save()

        default = leaderboard_options(ufilter=self.client.session["filter"])

        self.dummy_request(user)

        return lid, default

    def reset_SQL_sequences(self):
        '''
        For tests that report primary keys and validate against them it's important all Test Cases
        have identical PKs. Alas unless SQL sequences are reset between TestCases that doesn't happen.

        Inspired by: https://gist.github.com/diegolopmon/e0d376fa46995b2b433e
        '''
        SQL = StringIO()
        for app in apps.get_app_configs():
            call_command('sqlsequencereset', app.label, stdout=SQL)
        cursor = connection.cursor()
        cursor.execute(SQL.getvalue())

    @classmethod
    def setUpTestData(cls):
        cls.maxDiff = 2400  # To see diffs on some of the json dicts used in tests that are longish
        cls.setup_test_database()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        print("Resetting SQL Sequences")
        cls.reset_SQL_sequences(None)
        return

    @classmethod
    def setup_test_database(cls):
        '''
        Sets up a simple database for numerous test scenarios.
        '''
        print("Setting up Test Database")

        # Create a user (to login so we can post session add/edit requests)
        User = get_user_model()
        cls.user_admin = cls.user1 = User.objects.create_user('admin', 'noone@gmail.com', 'password')  # @UnusedVariable
        cls.user1.is_superuser = True
        cls.user1.save()

        # Dummy a request up for creating the rest of the objects we need.
        # In Python, instance methods receive the instance itself as the first argument (conventionally named self),
        # while class methods receive the class object as the first argument (conventionally named cls). However, when
        # calling an instance method within a class method, Python does not automatically inject the class object as
        # the first argument. You need to explicitly provide it when calling the instance method.
        cls.dummy_request(cls, cls.user_admin)

        # Create two normal player users in a league
        # (associate with player and add to league later when players and leagues are created)
        cls.user_notadmin1 = cls.user2 = User.objects.create_user('noadmin1', 'noone@gmail.com', 'password')  # @UnusedVariable
        cls.user_notadmin2 = cls.user3 = User.objects.create_user('noadmin2', 'noone@gmail.com', 'password')  # @UnusedVariable

        # Create some basic game configurations
        cls.game0 = Game.objects.create(name="NO_SCORES", individual_play=True, team_play=False, scoring=Game.ScoringOptions.NO_SCORES.value)

        cls.game1 = cls.gameIH = Game.objects.create(name="INDIVIDUAL_HIGH_SCORE_WINS", individual_play=True, team_play=False, scoring=Game.ScoringOptions.INDIVIDUAL_HIGH_SCORE_WINS.value)
        cls.game2 = cls.gameIL = Game.objects.create(name="INDIVIDUAL_LOW_SCORE_WINS", individual_play=True, team_play=False, scoring=Game.ScoringOptions.INDIVIDUAL_LOW_SCORE_WINS.value)

        cls.game3 = cls.gameTH = Game.objects.create(name="TEAM_HIGH_SCORE_WINS", individual_play=False, team_play=True, scoring=Game.ScoringOptions.TEAM_HIGH_SCORE_WINS.value)
        cls.game4 = cls.gameTL = Game.objects.create(name="TEAM_LOW_SCORE_WINS", individual_play=False, team_play=True, scoring=Game.ScoringOptions.TEAM_LOW_SCORE_WINS.value)

        cls.game5 = cls.gameTIH = Game.objects.create(name="TEAM_AND_INDIVIDUAL_HIGH_SCORE_WINS", individual_play=True, team_play=True, max_players=10, scoring=Game.ScoringOptions.TEAM_AND_INDIVIDUAL_HIGH_SCORE_WINS.value)
        cls.game6 = cls.gameTIL = Game.objects.create(name="TEAM_AND_INDIVIDUAL_LOW_SCORE_WINS", individual_play=True, team_play=True, max_players=10, scoring=Game.ScoringOptions.TEAM_AND_INDIVIDUAL_LOW_SCORE_WINS.value)

        # Some games for mixed players (filter testing)
        cls.game7 = Game.objects.create(name="IHSW_1", individual_play=True, team_play=False, scoring=Game.ScoringOptions.INDIVIDUAL_HIGH_SCORE_WINS.value)
        cls.game8 = Game.objects.create(name="IHSW_2", individual_play=True, team_play=False, scoring=Game.ScoringOptions.INDIVIDUAL_HIGH_SCORE_WINS.value)
        cls.game9 = Game.objects.create(name="IHSW_3", individual_play=True, team_play=False, scoring=Game.ScoringOptions.INDIVIDUAL_HIGH_SCORE_WINS.value)

        cls.all_games = [cls.game0, cls.game1, cls.game2, cls.game3, cls.game4, cls.game5, cls.game6, cls.game7, cls.game8, cls.game9]

        # Create a couple of tourneys
        cls.tourney1 = Tourney.objects.create(name='tourney1')
        cls.tourney1.games.set([cls.game0, cls.game1, cls.game2])

        cls.tourney2 = Tourney.objects.create(name='tourney2')
        cls.tourney2.games.set([cls.game3, cls.game4, cls.game5, cls.game6])
        # TODO: Add TourneyRules for each game in each tourney.
        # Default Rules are created and could be configured.

        # Create some Players
        cls.player1 = Player.objects.create(name_nickname="Player1", name_personal="Player", name_family="One", email_address="player1@leaderboard.space")  # @UndefinedVariable
        cls.player2 = Player.objects.create(name_nickname="Player2", name_personal="Player", name_family="Two", email_address="player2@leaderboard.space")  # @UndefinedVariable
        cls.player3 = Player.objects.create(name_nickname="Player3", name_personal="Player", name_family="Three", email_address="player3@leaderboard.space")  # @UndefinedVariable
        cls.player4 = Player.objects.create(name_nickname="Player4", name_personal="Player", name_family="Four", email_address="player4@leaderboard.space")  # @UndefinedVariable
        cls.player5 = Player.objects.create(name_nickname="Player5", name_personal="Player", name_family="Five", email_address="player5@leaderboard.space")  # @UndefinedVariable
        cls.player6 = Player.objects.create(name_nickname="Player6", name_personal="Player", name_family="Six", email_address="player6@leaderboard.space")  # @UndefinedVariable
        cls.player7 = Player.objects.create(name_nickname="Player7", name_personal="Player", name_family="Seven", email_address="player7@leaderboard.space")  # @UndefinedVariable
        cls.player8 = Player.objects.create(name_nickname="Player8", name_personal="Player", name_family="Eight", email_address="player8@leaderboard.space")  # @UndefinedVariable

        cls.pgroup1_6 = [cls.player1, cls.player2, cls.player3, cls.player4, cls.player5, cls.player6]
        cls.pgroup2_7 = [cls.player2, cls.player3, cls.player4, cls.player5, cls.player6, cls.player7]
        cls.pgroup3_8 = [cls.player3, cls.player4, cls.player5, cls.player6, cls.player7, cls.player8]
        cls.pgroup1_4 = [cls.player1, cls.player2, cls.player3, cls.player4]
        cls.pgroup1_2 = [cls.player1, cls.player2]
        cls.pgroup3_4 = [cls.player3, cls.player4]
        cls.pgroup1_3 = [cls.player1, cls.player2, cls.player3]
        cls.pgroup3_5 = [cls.player3, cls.player4, cls.player5]
        cls.pgroup3_6 = [cls.player3, cls.player4, cls.player5, cls.player6]
        cls.pgroup4_6 = [cls.player4, cls.player5, cls.player6]

        # # Create a couple of teams
        # team1 = Team.objects.create(name='team1')
        # team1.players.set([player1, player2])
        #
        # team2 = Team.objects.create(name='team2')
        # team2.players.set([player3, player4])

        # Create a couple of locations
        cls.location1 = Location.objects.create(name="Location1")
        cls.location2 = Location.objects.create(name="Location2")

        # Create a couple of leagues
        cls.league1 = League.objects.create(name='League1', manager=cls.player1)
        cls.league1.locations.set([cls.location1, cls.location2])
        cls.league1.players.set(cls.pgroup1_6)
        cls.league1.games.set([cls.game0, cls.game1, cls.game2, cls.game3, cls.game4, cls.game5, cls.game6])

        cls.league2 = League.objects.create(name='League2', manager=cls.player8)
        cls.league2.locations.set([cls.location1, cls.location2])
        cls.league2.players.set(cls.pgroup3_8)
        cls.league2.games.set([cls.game0, cls.game1, cls.game2, cls.game3])

        cls.league3 = League.objects.create(name='League3', manager=cls.player8)
        cls.league3.locations.set([cls.location1])
        cls.league3.players.set(cls.pgroup3_5)
        cls.league3.games.set([cls.game3, cls.game4, cls.game5, cls.game6, cls.game7, cls.game8, cls.game9])

        # Associatiate player1 with user1 and player2 with user2
        cls.player1.user = cls.user1
        cls.player2.user = cls.user2
        cls.player3.user = cls.user3

        # The first two players can log in and have a default/preferred league
        cls.player1.league = cls.league1
        cls.player2.league = cls.league2
        cls.player3.league = cls.league3

        # Create sessions.
        # We want at least one session per game type to test various rank/score configuration submissions
        # A note on times: In January Hobart/Tasmania is at UTC+11. Using Hobart as our test site.
        # We choose a datetime suchg that the hour is equal to the session ID for convenience.
        cls.session00 = create_session(cls.game0, cls.pgroup1_4, [1, 2, 3, 4], '2022-01-01 01:00:00 +11:00', cls.league1)  # @UnusedVariable
        cls.sessionIH = create_session(cls.gameIH, cls.pgroup1_4, [1, 2, 3, 4], '2022-01-01 02:00:00 +11:00', cls.league1)  # @UnusedVariable
        cls.sessionIL = create_session(cls.gameIL, cls.pgroup1_4, [1, 2, 3, 4], '2022-01-01 03:00:00 +11:00', cls.league1)  # @UnusedVariable

        # Team based sessions (2 player teams)
        cls.sessionTH2 = create_session(cls.gameTH, [cls.pgroup1_2, cls.pgroup3_4], [1, 2], '2022-01-01 04:00:00 +11:00', cls.league1)  # @UnusedVariable
        cls.sessionTL2 = create_session(cls.gameTL, [cls.pgroup1_2, cls.pgroup3_4], [1, 2], '2022-01-01 05:00:00 +11:00', cls.league1)  # @UnusedVariable

        # We want a team based session in which the team is unique (3 player sessions)
        cls.sessionTH3 = create_session(cls.gameTH, [cls.pgroup1_3, cls.pgroup4_6], [1, 2], '2022-01-01 06:00:00 +11:00', cls.league2)  # @UnusedVariable

        # Mixed Team/Individual sessions
        cls.sessionTIHi = create_session(cls.gameTIH, cls.pgroup1_4, [1, 2, 3, 4], '2022-01-01 07:00:00 +11:00', cls.league2)  # @UnusedVariable
        cls.sessionTILt2 = create_session(cls.gameTIL, [cls.pgroup1_2, cls.pgroup3_4], [1, 2], '2022-01-01 08:00:00 +11:00', cls.league2)  # @UnusedVariable

        # We want a series of sessions to test rebuild triggering on time, game, player shifts.
        cls.session01 = create_session(cls.game0, cls.pgroup1_4, [4, 3, 2, 1], '2022-01-01 09:00:00 +11:00', cls.league1)  # @UnusedVariable
        cls.session02 = create_session(cls.game0, cls.pgroup3_6, [2, 3, 1, 4], '2022-01-01 10:00:00 +11:00', cls.league2)  # @UnusedVariable
        cls.session03 = create_session(cls.game0, [cls.player1, cls.player3, cls.player5, cls.player6], [1, 3, 4, 2], '2022-01-01 11:00:00 +11:00', cls.league3)  # @UnusedVariable
        cls.session04 = create_session(cls.game0, [cls.player1, cls.player4, cls.player5, cls.player3], [1, 2, 3, 4], '2022-01-01 12:00:00 +11:00', cls.league1)  # @UnusedVariable

        # Some sessions of mixed players in low play games for player filter testing
        cls.session05 = create_session(cls.game7, [cls.player1, cls.player7], [1, 2], '2022-01-01 13:00:00 +11:00', cls.league1)  # @UnusedVariable
        cls.session06 = create_session(cls.game8, [cls.player2, cls.player5], [1, 2], '2022-01-01 14:00:00 +11:00', cls.league2)  # @UnusedVariable
        cls.session07 = create_session(cls.game9, [cls.player3, cls.player8], [1, 2], '2022-01-01 15:00:00 +11:00', cls.league3)  # @UnusedVariable

        # Save a this fixture for use in manual testing too
        # management.call_command('dumpdata', natural_foreign=True, indent=4, output="CoGs_test_data.json")
