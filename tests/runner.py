import inspect
import json

from datetime import datetime
from dateutil import parser

from crequest.middleware import CrequestMiddleware

from django.db import connections
from django.urls import reverse
from django.conf import settings
from django.test import TransactionTestCase
from django.test.runner import DiscoverRunner
from django.test.client import RequestFactory
from django.contrib.auth import get_user_model
from django.core.management import call_command

from django.db.backends.base.introspection import BaseDatabaseIntrospection

import psycopg2 as postgres
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.errors import InsufficientPrivilege  # @UnresolvedImport

from Leaderboards.models import Game, Player, League, Location, Tourney, Session, Rank, Performance, Team
from Leaderboards.leaderboards.options import leaderboard_options

from django_rich_views.datetime import make_aware

class PostgreSQL_TestCase(TransactionTestCase):

    def __init__(self, methodName):
        # from:https://stackoverflow.com/questions/27456881/how-to-use-verbosity-level-in-your-tests-in-django
        def get_verbosity():
            for s in reversed(inspect.stack()):
                options = s[0].f_locals.get('options')
                if isinstance(options, dict):
                    return int(options['verbosity'])
            return 1

        self.verbosity = get_verbosity()

        return super().__init__(methodName)

    # def postgreSQL_init(self):
    #     '''
    #     UNNEEDED. OLD METOD OF PASSING DATA TO TESTCASE
    #
    #     The order of events in Django test runs is as follows:
    #
    #     1. The runner initialises all the TestCases (in build_suite)
    #     2. The runner sets up databases (in setup_databases)
    #
    #     we want the database setup to be able to communicate information to the tests that are running.
    #
    #     To wit any test needing such information should call this method to fetch it. We can set it in
    #     PostgreSQL_TestCase.__init__ as that was run before we set the databases up, and so or so we
    #     need to use reflection (the inspect module) to either find the suite and set attributs on all
    #     the test cases in it, or ask test cases to call here and use reflection to find the runner and
    #     fetch them.
    #
    #     Be nice if it was easier, but we stretching the Django testing paradigm a little here by wanting
    #     a database that sticks around between tests for inspection and to aid in test design and diagnosis.
    #     '''
    #     def get_test_runner():
    #         '''
    #         The PostgreSQL_Runner sets a number of instance attributes that can help a test case. Because we set up the test
    #         database here in the runner, for the express purpose of having one test database for all our tests rather than
    #         rebuilding one for each test (Django's default behaviour), we know things here about the constructed database
    #         that the test case may want to know.
    #         '''
    #         # Use the inspect module to find the first instance of CustomTestRunner in the call stack
    #         frame = inspect.currentframe()
    #         while frame:
    #             runner = frame.f_locals.get('self')
    #             if isinstance(runner, PostgreSQL_Runner):
    #                 return runner
    #             frame = frame.f_back
    #         return None
    #
    #     self.runner = get_test_runner()
    #
    #     bucket = getattr(self.runner, "__test_case_attributes__", None)
    #     if bucket:
    #         for attr in dir(bucket):
    #             if not attr.startswith('_'):
    #                 setattr(self, attr, getattr(bucket, attr))

    def assertEqualDicts(self, first, second, msg):
        '''
        A Dict comparison that enforces identical ordering. Dicts are ordered since Python 3.7 but the 
        equality test doesn't check of equal ordering as at Python 3.10. So we have to force it by 
        comparing lists of items.
        '''
        return self.assertEqual(list(first.items()), list(second.items()), msg)

    def DictsEqual(self, first, second):
        '''
        A Dict comparison that enforces identical ordering. Dicts are ordered since Python 3.7 but the 
        equality test doesn't check of equal ordering as at Python 3.10. So we have to force it by 
        comparing lists of items.
        '''
        return list(first.items()) == list(second.items())

    def JSON_response(self, view_name, get=""):
        '''
        Clean way to get a JSON response from the server
        :param view_name:
        :param get:
        '''
        return json.loads(self.client.get(reverse(view_name)+get).content.decode())

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

    # Our runner doesn't concern itself with fixtures and so we want to 
    # clobber the setup and teardown. Notably the latter tries to flush 
    # the database one of the things we want control over here.   

    @classmethod
    def _fixture_setup(self):
        pass

    def _fixture_teardown(self):
        pass

    # @classmethod
    # def setUpClass(cls):
    #     super().setUpClass()

    @classmethod
    def setUpTestData(cls):
        cls.maxDiff = 2400 # To see diffs on some of the json dicts used in tests that are longish


class PostgreSQL_Runner(DiscoverRunner):

    class Cursor:
        ''' A simple cursor context. We cannot use a postgres connect context as that opens a transaction and DROP won't work'''
        def __init__(self, dsn):
            self.dsn = dsn
            self.connection = None
            self.cursor = None

        def __enter__(self):
            self.connection = postgres.connect(self.dsn)
            self.connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            self.cursor = self.connection.cursor()
            return self.cursor

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.cursor.close()
            self.connection.close()

    def __init__(self, *args, **kwargs):
        self.rebuild_database = kwargs.pop('rebuild_database', False) 
        self.refresh_database = kwargs.pop('refresh_database', False) 
        super().__init__(*args, **kwargs)

    @classmethod
    def add_arguments(cls, parser):
        """
        Add command-line arguments specific to this test runner.
        This method is called by Django's manage.py test command
        to register custom options.
        """
        super().add_arguments(parser) # Call super to keep default Django arguments

        parser.add_argument('--rebuild-database', action='store_true', help='Blow away the test database and rebuild it cleanly (ALL of it, and rebuld the schema).')
        parser.add_argument('--refresh-database', action='store_true', help='Blow away the test database and rebuild it cleanly (trust the schema and just flush data and repopulate).')

    def sql_truncate(self):
        ''' Analagous to manage.py sqlflush'''
        # Get the table names using django_table_names method
        connection = connections['default']
        introspection = BaseDatabaseIntrospection(connection)
        table_names = introspection.django_table_names()
        tables_to_truncate = ', '.join([f'"{table}"' for table in table_names])
        # RESET IDENTITY resets the sequences (the automatic primary key incrementers)
        # CASCADE simply ensures no foreignkey related errors if the order of tables is not right
        return f"TRUNCATE {tables_to_truncate} RESTART IDENTITY CASCADE;"

    def setup_databases(self, **kwargs):
        cp = settings.DATABASES['default']
        self.host = cp['HOST']
        self.port = cp['PORT']
        self.db = cp['NAME']
        self.user = cp['USER']
        self.password = cp['PASSWORD']

        # Drop and recreate the test database
        if self.rebuild_database:
            if self.drop_test_database():
                print(f"Dropped old Test Database, creating new Test Database...")
                self.create_test_database()
            else:
                print(f"Creating new Test Database...")
                self.create_test_database()
    
            # Run migrations to ensure schema (table defintions) is up to date
            call_command('migrate', interactive=False)

            self.setup_test_database()
            
        elif self.refresh_database:
            print(f"Flushing the database and repopulating with default test data...")
            self.flush_test_database()
            print(f"\tFlushed")
            self.setup_test_database()

    def teardown_databases(self, old_config, **kwargs):
        # Disable database teardown
        pass

    def flush_test_database(self):
        dsn = postgres.extensions.make_dsn(host=self.host, port=self.port, dbname=self.db, user=self.user, password=self.password)
        with self.Cursor(dsn) as cursor:
            cursor.execute(self.sql_truncate())

    def drop_test_database(self):
        # Create to postgres dsns, one that is datbaseless the other with the test database. Alas a connections can be bound to only one database.
        dsn = postgres.extensions.make_dsn(host=self.host, port=self.port, dbname='postgres', user=self.user, password=self.password)
        dsn_db = postgres.extensions.make_dsn(host=self.host, port=self.port, dbname=self.db, user=self.user, password=self.password)

        # Step 1: Check if the datbase exists. If not we have nothing to do here.
        sql_check = f"""
            SELECT EXISTS(
                SELECT datname
                FROM pg_catalog.pg_database
                WHERE datname = '{self.db}');
        """
        with self.Cursor(dsn) as cursor:
            cursor.execute(sql_check)
            result = cursor.fetchone()
            # The result is a 1-tuple containing True or False
            if not result[0]:
                return

        # Step 2 Drop the Database if possible, try and bootexisting users if needed, and if all else fails truncate and reset sequences if possible.
        # Define SQL to close existing conections
        sql_check = f"SELECT pid, usename, application_name, client_addr, client_port FROM pg_stat_activity WHERE datname = '{self.db}'"
        sql_boot = f"SELECT pid, pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{self.db}'"
        sql_drop = f'DROP DATABASE IF EXISTS "{self.db}";'

        # Define SQL to drop the old test database
        with self.Cursor(dsn) as cursor:
            dropped = False
            try:
                # Drop the test database
                cursor.execute(sql_drop)
                dropped = True
            except Exception as E:
                try:
                    # Check for active connections to the test database
                    print(f"Tried to drop database and failed.")
                    cursor.execute(sql_check)
                    for record in cursor:
                        (pid, username, application, addr, port) = record  # @UnusedVariable
                        if username != self.user:
                            if application:
                                app = f"{application} has the database open with user {username} "
                            else:
                                app = f"User {username} has the database open "
                            print(f"{app} from {addr}:{port}")
                    cursor.execute(sql_boot)
                    cursor.execute(sql_drop)
                    dropped = True
                except InsufficientPrivilege:
                    print(f"failed to boot them, the user {self.user} has insuffient privelege.")
                    print(f"Will attempt to flush it instead.")
                    try:
                        # Truncate all the tables and reset sequences
                        with self.Cursor(dsn_db) as cursor:
                            cursor.execute(self.sql_truncate())
                            dropped = False
                            print(f"Tables flushed and sequences reset.")
                    except Exception as E:
                        raise Exception("Failed to drop database AND failed to truncate tables and reset sequences. Not a clean way to start testing.")

        return dropped

    def create_test_database(self):
        dsn = postgres.extensions.make_dsn(host=self.host, port=self.port, dbname='postgres', user=self.user, password=self.password)
        conn = postgres.connect(dsn)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with conn.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE "{self.db}"')
        # Close the existing connection to the old database
        conn.close()

    def dummy_request(self, user):
        '''
        Adds a dummy request to the Runner which is needed by CrequestMiddleware to get
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

    def setup_test_database(self):
        '''
        Sets up a simple database for numerous test scenarios.
        '''
        print("Populating Test Database with default test data ....")

        # Define a plain object to store attributes we'll set on the TestCase above.
        class Object(object): pass
        A = Object()

        # Create a user (to login so we can post session add/edit requests)
        User = get_user_model()
        users = User.objects.all()
        A.user_admin = A.user1 = User.objects.create_user('admin', 'noone@gmail.com', 'password')  # @UnusedVariable
        A.user1.is_superuser = True
        A.user1.save()

        # Dummy a request up for creating the rest of the objects we need.
        # In Python, instance methods receive the instance itself as the first argument (conventionally named self),
        # while class methods receive the class object as the first argument (conventionally named self). However, when
        # calling an instance method within a class method, Python does not automatically inject the class object as
        # the first argument. You need to explicitly provide it when calling the instance method.
        self.dummy_request(A.user_admin)

        # Create two normal player users in a league
        # (associate with player and add to league later when players and leagues are created)
        A.user_notadmin1 = A.user2 = User.objects.create_user('noadmin1', 'noone@gmail.com', 'password')  # @UnusedVariable
        A.user_notadmin2 = A.user3 = User.objects.create_user('noadmin2', 'noone@gmail.com', 'password')  # @UnusedVariable

        # Create some basic game configurations
        A.game0 = Game.objects.create(name="NO_SCORES", individual_play=True, team_play=False, scoring=Game.ScoringOptions.NO_SCORES.value)

        A.game1 = A.gameIH = Game.objects.create(name="INDIVIDUAL_HIGH_SCORE_WINS", individual_play=True, team_play=False, scoring=Game.ScoringOptions.INDIVIDUAL_HIGH_SCORE_WINS.value)
        A.game2 = A.gameIL = Game.objects.create(name="INDIVIDUAL_LOW_SCORE_WINS", individual_play=True, team_play=False, scoring=Game.ScoringOptions.INDIVIDUAL_LOW_SCORE_WINS.value)

        A.game3 = A.gameTH = Game.objects.create(name="TEAM_HIGH_SCORE_WINS", individual_play=False, team_play=True, scoring=Game.ScoringOptions.TEAM_HIGH_SCORE_WINS.value)
        A.game4 = A.gameTL = Game.objects.create(name="TEAM_LOW_SCORE_WINS", individual_play=False, team_play=True, scoring=Game.ScoringOptions.TEAM_LOW_SCORE_WINS.value)

        A.game5 = A.gameTIH = Game.objects.create(name="TEAM_AND_INDIVIDUAL_HIGH_SCORE_WINS", individual_play=True, team_play=True, max_players=10, scoring=Game.ScoringOptions.TEAM_AND_INDIVIDUAL_HIGH_SCORE_WINS.value)
        A.game6 = A.gameTIL = Game.objects.create(name="TEAM_AND_INDIVIDUAL_LOW_SCORE_WINS", individual_play=True, team_play=True, max_players=10, scoring=Game.ScoringOptions.TEAM_AND_INDIVIDUAL_LOW_SCORE_WINS.value)

        # Some games for mixed players (filter testing)
        A.game7 = Game.objects.create(name="IHSW_1", individual_play=True, team_play=False, scoring=Game.ScoringOptions.INDIVIDUAL_HIGH_SCORE_WINS.value)
        A.game8 = Game.objects.create(name="IHSW_2", individual_play=True, team_play=False, scoring=Game.ScoringOptions.INDIVIDUAL_HIGH_SCORE_WINS.value)
        A.game9 = Game.objects.create(name="IHSW_3", individual_play=True, team_play=False, scoring=Game.ScoringOptions.INDIVIDUAL_HIGH_SCORE_WINS.value)

        A.all_games = [A.game0, A.game1, A.game2, A.game3, A.game4, A.game5, A.game6, A.game7, A.game8, A.game9]

        # Create a couple of tourneys
        A.tourney1 = Tourney.objects.create(name='tourney1')
        A.tourney1.games.set([A.game0, A.game1, A.game2])

        A.tourney2 = Tourney.objects.create(name='tourney2')
        A.tourney2.games.set([A.game3, A.game4, A.game5, A.game6])
        # TODO: Add TourneyRules for each game in each tourney.
        # Default Rules are created and could be configured.

        # Create some Players
        A.player1 = Player.objects.create(name_nickname="Player1", name_personal="Player", name_family="One", email_address="player1@leaderboard.space")  # @UndefinedVariable
        A.player2 = Player.objects.create(name_nickname="Player2", name_personal="Player", name_family="Two", email_address="player2@leaderboard.space")  # @UndefinedVariable
        A.player3 = Player.objects.create(name_nickname="Player3", name_personal="Player", name_family="Three", email_address="player3@leaderboard.space")  # @UndefinedVariable
        A.player4 = Player.objects.create(name_nickname="Player4", name_personal="Player", name_family="Four", email_address="player4@leaderboard.space")  # @UndefinedVariable
        A.player5 = Player.objects.create(name_nickname="Player5", name_personal="Player", name_family="Five", email_address="player5@leaderboard.space")  # @UndefinedVariable
        A.player6 = Player.objects.create(name_nickname="Player6", name_personal="Player", name_family="Six", email_address="player6@leaderboard.space")  # @UndefinedVariable
        A.player7 = Player.objects.create(name_nickname="Player7", name_personal="Player", name_family="Seven", email_address="player7@leaderboard.space")  # @UndefinedVariable
        A.player8 = Player.objects.create(name_nickname="Player8", name_personal="Player", name_family="Eight", email_address="player8@leaderboard.space")  # @UndefinedVariable

        A.pgroup1_6 = [A.player1, A.player2, A.player3, A.player4, A.player5, A.player6]
        A.pgroup2_7 = [A.player2, A.player3, A.player4, A.player5, A.player6, A.player7]
        A.pgroup3_8 = [A.player3, A.player4, A.player5, A.player6, A.player7, A.player8]
        A.pgroup1_4 = [A.player1, A.player2, A.player3, A.player4]
        A.pgroup1_2 = [A.player1, A.player2]
        A.pgroup3_4 = [A.player3, A.player4]
        A.pgroup1_3 = [A.player1, A.player2, A.player3]
        A.pgroup3_5 = [A.player3, A.player4, A.player5]
        A.pgroup3_6 = [A.player3, A.player4, A.player5, A.player6]
        A.pgroup4_6 = [A.player4, A.player5, A.player6]

        # # Create a couple of teams
        # team1 = Team.objects.create(name='team1')
        # team1.players.set([player1, player2])
        #
        # team2 = Team.objects.create(name='team2')
        # team2.players.set([player3, player4])

        # Create a couple of locations
        A.location1 = Location.objects.create(name="Location1")
        A.location2 = Location.objects.create(name="Location2")

        # Create a couple of leagues
        A.league1 = League.objects.create(name='League1', manager=A.player1)
        A.league1.locations.set([A.location1, A.location2])
        A.league1.players.set(A.pgroup1_6)
        A.league1.games.set([A.game0, A.game1, A.game2, A.game3, A.game4, A.game5, A.game6])

        A.league2 = League.objects.create(name='League2', manager=A.player8)
        A.league2.locations.set([A.location1, A.location2])
        A.league2.players.set(A.pgroup3_8)
        A.league2.games.set([A.game0, A.game1, A.game2, A.game3])

        A.league3 = League.objects.create(name='League3', manager=A.player8)
        A.league3.locations.set([A.location1])
        A.league3.players.set(A.pgroup3_5)
        A.league3.games.set([A.game3, A.game4, A.game5, A.game6, A.game7, A.game8, A.game9])

        # Associatiate player1 with user1 and player2 with user2
        A.player1.user = A.user1
        A.player2.user = A.user2
        A.player3.user = A.user3

        # The first two players can log in and have a default/preferred league
        A.player1.league = A.league1
        A.player2.league = A.league2
        A.player3.league = A.league3

        # Create sessions.
        # We want at least one session per game type to test various rank/score configuration submissions
        # A note on times: In January Hobart/Tasmania is at UTC+11. Using Hobart as our test site.
        # We choose a datetime suchg that the hour is equal to the session ID for convenience.
        A.session00 = create_session(A.game0, A.pgroup1_4, [1, 2, 3, 4], '2022-01-01 01:00:00 +10:00', A.league1)  # @UnusedVariable
        A.sessionIH = create_session(A.gameIH, A.pgroup1_4, [1, 2, 3, 4], '2022-01-01 02:00:00 +10:00', A.league1)  # @UnusedVariable
        A.sessionIL = create_session(A.gameIL, A.pgroup1_4, [1, 2, 3, 4], '2022-01-01 03:00:00 +10:00', A.league1)  # @UnusedVariable

        # Team based sessions (2 player teams)
        A.sessionTH2 = create_session(A.gameTH, [A.pgroup1_2, A.pgroup3_4], [1, 2], '2022-01-01 04:00:00 +10:00', A.league1)  # @UnusedVariable
        A.sessionTL2 = create_session(A.gameTL, [A.pgroup1_2, A.pgroup3_4], [1, 2], '2022-01-01 05:00:00 +10:00', A.league1)  # @UnusedVariable

        # We want a team based session in which the team is unique (3 player sessions)
        A.sessionTH3 = create_session(A.gameTH, [A.pgroup1_3, A.pgroup4_6], [1, 2], '2022-01-01 06:00:00 +10:00', A.league2)  # @UnusedVariable

        # Mixed Team/Individual sessions
        A.sessionTIHi = create_session(A.gameTIH, A.pgroup1_4, [1, 2, 3, 4], '2022-01-01 07:00:00 +10:00', A.league2)  # @UnusedVariable
        A.sessionTILt2 = create_session(A.gameTIL, [A.pgroup1_2, A.pgroup3_4], [1, 2], '2022-01-01 08:00:00 +10:00', A.league2)  # @UnusedVariable

        # We want a series of sessions to test rebuild triggering on time, game, player shifts.
        A.session01 = create_session(A.game0, A.pgroup1_4, [4, 3, 2, 1], '2022-01-01 09:00:00 +10:00', A.league1)  # @UnusedVariable
        A.session02 = create_session(A.game0, A.pgroup3_6, [2, 3, 1, 4], '2022-01-01 10:00:00 +10:00', A.league2)  # @UnusedVariable
        A.session03 = create_session(A.game0, [A.player1, A.player3, A.player5, A.player6], [1, 3, 4, 2], '2022-01-01 11:00:00 +10:00', A.league3)  # @UnusedVariable
        A.session04 = create_session(A.game0, [A.player1, A.player4, A.player5, A.player3], [1, 2, 3, 4], '2022-01-01 12:00:00 +10:00', A.league1)  # @UnusedVariable

        # Some sessions of mixed players in low play games for player filter testing
        A.session05 = create_session(A.game7, [A.player1, A.player7], [1, 2], '2022-01-01 13:00:00 +10:00', A.league1)  # @UnusedVariable
        A.session06 = create_session(A.game8, [A.player2, A.player5], [1, 2], '2022-01-01 14:00:00 +10:00', A.league2)  # @UnusedVariable
        A.session07 = create_session(A.game9, [A.player3, A.player8], [1, 2], '2022-01-01 15:00:00 +10:00', A.league3)  # @UnusedVariable

        # Ensure that each game has at least one session in each of the leagues the game is played in!
        # That will help with sensible leaderboard query tests with a preferred league filter (based on logged in user) it only
        # returns boards/snapshots/sessions (synonyms here) that are in the filter league for games that are in the filter league.
        # The is no requirement that a game added to a league has any sessions in that league yet (so we leave A.game8 (id 9)
        # with no in-league game.
        A.session08 = create_session(A.game1, A.pgroup4_6, [1, 2, 3], '2022-01-02 16:00:00 +10:00', A.league2)  # @UnusedVariable
        A.session09 = create_session(A.game2, A.pgroup4_6, [3, 2, 1], '2022-01-02 17:00:00 +10:00', A.league2)  # @UnusedVariable
        A.session10 = create_session(A.game3, A.pgroup3_5, [1, 2, 3], '2022-01-02 18:00:00 +10:00', A.league3)  # @UnusedVariable
        A.session11 = create_session(A.game4, A.pgroup3_5, [3, 2, 1], '2022-01-02 19:00:00 +10:00', A.league3)  # @UnusedVariable
        A.session12 = create_session(A.game5, A.pgroup1_3, [1, 2, 3], '2022-01-05 20:00:00 +10:00', A.league1)  # @UnusedVariable
        A.session13 = create_session(A.game5, A.pgroup3_5, [1, 3, 2], '2022-01-05 21:00:00 +10:00', A.league3)  # @UnusedVariable
        A.session14 = create_session(A.game6, A.pgroup1_3, [3, 2, 1], '2022-01-05 22:00:00 +10:00', A.league1)  # @UnusedVariable
        A.session15 = create_session(A.game6, A.pgroup3_5, [3, 1, 2], '2022-01-05 23:00:00 +10:00', A.league3)  # @UnusedVariable
        A.session16 = create_session(A.game7, A.pgroup3_5, [2, 3, 1], '2022-01-06 00:00:00 +10:00', A.league3)  # @UnusedVariable

        # TODO: When saving a session the game should automatically be added to the session league if it's not already!
        #       Makes little difference to us here as we create games, then sessions and indeed in practice which is the same,
        #       but it's a sensibel data integrity assurance.

        if settings.DEBUG:
            print(f"Test Data Set, Game/League coverage:")
            for game in Game.objects.all().order_by('id'):
                game_leagues = set([l.id for l in game.leagues.all()])
                sess_leagues = set([s.league.id for s in game.sessions.all()])
                miss_leagues = None if game_leagues - sess_leagues == set() else game_leagues - sess_leagues
                print(f"Game: {game.id}")
                print(f"\tgame leagues: {game_leagues}")
                print(f"\tsession leagues: {sess_leagues}")
                print(f"\tmissed leagues: {miss_leagues}")

        # Any tests of type PostgreSQL_TestCase that are instantiated and run after the dtabase is setup will see this.
        PostgreSQL_TestCase.__test_case_attributes__ = A

        # Save a this fixture for use in manual testing too
        # call_command('dumpdata', natural_foreign=True, indent=4, output="CoGs_test_data.json")
        print("\tDone populating Test Database.")


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
    attr = TransactionTestCase()

    # Get game
    attr.assertTrue(isinstance(game, (str, Game)))
    if isinstance(game, str):
        game = Game.objects.get(name=game)

    # Get the players
    attr.assertTrue(isinstance(players, (list, tuple)))
    attr.assertTrue(len(players) > 1)
    if isinstance(players[0], (list, tuple)):
        team_play = True
        for t in players:
            attr.assertTrue(isinstance(t, (list, tuple)))
            for p in t:
                attr.assertTrue(isinstance(p, (str, Player)))
    elif isinstance(players[0], (str, Player)):
        team_play = False
        for p in players:
            attr.assertTrue(isinstance(p, (str, Player)))
    else:
        attr.fail("create_session: players must be a list of lists or Player objects or strings")

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
        attr.assertTrue(len(ranking) == len(players))

    # Get the datetime
    if date_time is None:
        date_time = datetime.now()
    else:
        attr.assertTrue(isinstance(date_time, (datetime, str)))
        if isinstance(date_time, str):
            date_time = make_aware(parser.parse(date_time))

    # Get the League (by name)
    if league is None:
        league = League.objects.get(pk=1)
    else:
        attr.assertTrue(isinstance(league, (str, League)))
        if isinstance(league, str):
            league = League.objects.get(name=league)

    # Get the Location (by name)League
    if location is None:
        location = Location.objects.get(pk=1)
    else:
        attr.assertTrue(isinstance(location, (str, Location)))
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
                    attr.assertTrue(isinstance(p, (int, float)))
                    attr.assertTrue(p >= 0)
                    attr.assertTrue(p <= 1)
        else:
            for p in players:
                attr.assertTrue(isinstance(p, (int, float)))
                attr.assertTrue(p >= 0)
                attr.assertTrue(p <= 1)

    # Get the Rank scores
    if rscores is None:
        rscores = [None for _ in ranking]
    else:
        for i, r in enumerate(ranking):
            attr.assertTrue(isinstance(r, int))
            attr.assertTrue(r > 0)

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
                    attr.assertTrue(isinstance(pscores[i][j], int))
                    attr.assertTrue(pscores[i][j] >= 0)
        else:
            for i, p in enumerate(players):
                attr.assertTrue(isinstance(pscores[i], int))
                attr.assertTrue(pscores[i] >= 0)

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


