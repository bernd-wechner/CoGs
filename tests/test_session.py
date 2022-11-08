# import os
# import django
import re

from copy import deepcopy
from datetime import datetime
from dateutil import parser

from django.test import TestCase
from django.core import management
from django.contrib.auth import get_user_model
from django_rich_views.datetime import make_aware

from Leaderboards.models import Session, Game, Player, Team, Rank, Performance, League, Location, Tourney, MISSING_VALUE as MV
from Leaderboards.views.pre_handlers import reconcile_ranks

# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Site.settings')
# django.setup()


class SessionTestCase(TestCase):

    # TODO Make session creation methods via DB calls and vbiw REQUEST simulation
    # TODO: Using created sessions test:
    #        Leaderboards.models.session.Session.dict_from_form
    #        Leaderboards.models.session.Session.dict_from_object
    # On the form and created object to ensure we get the same dict!
    # Do that for indiv and team session.
    @classmethod
    def clean_session_args(cls,
                           game, players,
                           ranking=None,
                           date_time=None,
                           league=None,
                           location=None,
                           ppw=None,
                           rscores=None,
                           pscores=None):
        '''
        A standard form of session creation args is used for creating DB session or session add or edit posts.

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

    @classmethod
    def create_session(cls,
                       game, players,
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
        game, players, ranking, date_time, league, location, ppw, rscores, pscores, team_play = cls.clean_session_args(
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

    @classmethod
    def setUpTestData(cls):
        cls.maxDiff = 2400  # To see diffs on some of the json dicts used in tests that are longish

        # Create a user (to login so we can post session add/edit requests)
        User = get_user_model()
        cls.user = User.objects.create_user('admin', 'noone@gmail.com', 'password')  # @UnusedVariable

        # Create some basic game configurations
        cls.game0 = Game.objects.create(name="NO_SCORES", individual_play=True, team_play=False, scoring=Game.ScoringOptions.NO_SCORES.value)

        cls.gameIH = Game.objects.create(name="INDIVIDUAL_HIGH_SCORE_WINS", individual_play=True, team_play=False, scoring=Game.ScoringOptions.INDIVIDUAL_HIGH_SCORE_WINS.value)
        cls.gameIL = Game.objects.create(name="INDIVIDUAL_LOW_SCORE_WINS", individual_play=True, team_play=False, scoring=Game.ScoringOptions.INDIVIDUAL_LOW_SCORE_WINS.value)

        cls.gameTH = Game.objects.create(name="TEAM_HIGH_SCORE_WINS", individual_play=False, team_play=True, scoring=Game.ScoringOptions.TEAM_HIGH_SCORE_WINS.value)
        cls.gameTL = Game.objects.create(name="TEAM_LOW_SCORE_WINS", individual_play=False, team_play=True, scoring=Game.ScoringOptions.TEAM_LOW_SCORE_WINS.value)

        cls.gameTIH = Game.objects.create(name="TEAM_AND_INDIVIDUAL_HIGH_SCORE_WINS", individual_play=True, team_play=True, max_players=10, scoring=Game.ScoringOptions.TEAM_AND_INDIVIDUAL_HIGH_SCORE_WINS.value)
        cls.gameTIL = Game.objects.create(name="TEAM_AND_INDIVIDUAL_LOW_SCORE_WINS", individual_play=True, team_play=True, max_players=10, scoring=Game.ScoringOptions.TEAM_AND_INDIVIDUAL_LOW_SCORE_WINS.value)

        cls.all_games = [cls.game0, cls.gameIH, cls.gameIL, cls.gameTH, cls.gameTL, cls.gameTIH, cls.gameTIL]

        # Create a couple of tourneys
        cls.tourney1 = Tourney.objects.create(name='tourney1')
        cls.tourney1.games.set([cls.game0, cls.gameIH, cls.gameIL])

        cls.tourney2 = Tourney.objects.create(name='tourney2')
        cls.tourney2.games.set([cls.gameTH, cls.gameTL, cls.gameTIH, cls.gameTIL])
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
        cls.pgroup1_3 = [cls.player1, cls.player2, cls.player3]
        cls.pgroup3_5 = [cls.player3, cls.player4, cls.player5]

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
        cls.league1.games.set(cls.all_games)

        cls.league1 = League.objects.create(name='League2', manager=cls.player8)
        cls.league1.locations.set([cls.location1, cls.location2])
        cls.league1.players.set(cls.pgroup3_8)
        cls.league1.games.set(cls.all_games)

        # Create sessions.
        # We want at least one session per game type to test various rank/score configuration submissions
        cls.session00 = cls.create_session(cls.game0, [cls.player1, cls.player2, cls.player3, cls.player4], [1, 2, 3, 4], '2022-01-01 00:00:00 +10:00')  # @UnusedVariable
        cls.sessionIH = cls.create_session(cls.gameIH, [cls.player1, cls.player2, cls.player3, cls.player4], [1, 2, 3, 4], '2022-01-01 01:00:00 +10:00')  # @UnusedVariable
        cls.sessionIL = cls.create_session(cls.gameIL, [cls.player1, cls.player2, cls.player3, cls.player4], [1, 2, 3, 4], '2022-01-01 02:00:00 +10:00')  # @UnusedVariable

        # Team based sessions (2 player teams)
        cls.sessionTH2 = cls.create_session(cls.gameTH, [[cls.player1, cls.player2], [cls.player3, cls.player4]], [1, 2], '2022-01-01 03:00:00 +10:00')  # @UnusedVariable
        cls.sessionTL2 = cls.create_session(cls.gameTL, [[cls.player1, cls.player2], [cls.player3, cls.player4]], [1, 2], '2022-01-01 04:00:00 +10:00')  # @UnusedVariable

        # We want a team based session in which the team is unique (3 player sessions)
        cls.sessionTH3 = cls.create_session(cls.gameTH, [[cls.player1, cls.player2, cls.player3], [cls.player4, cls.player5, cls.player6]], [1, 2], '2022-01-01 05:00:00 +10:00')  # @UnusedVariable

        # Mixed Team/Individual sessions
        cls.sessionTIHi = cls.create_session(cls.gameTIH, [cls.player1, cls.player2, cls.player3, cls.player4], [1, 2, 3, 4], '2022-01-01 06:00:00 +10:00')  # @UnusedVariable
        cls.sessionTILt2 = cls.create_session(cls.gameTIL, [[cls.player1, cls.player2], [cls.player3, cls.player4]], [1, 2], '2022-01-01 07:00:00 +10:00')  # @UnusedVariable

        # We want a series of maybe 5 sessions to test rebuild triggering on time, game, player shifts.
        cls.session01 = cls.create_session(cls.game0, [cls.player1, cls.player2, cls.player3, cls.player4], [4, 3, 2, 1], '2022-01-01 08:00:00 +10:00')  # @UnusedVariable
        cls.session02 = cls.create_session(cls.game0, [cls.player3, cls.player4, cls.player5, cls.player6], [2, 3, 1, 4], '2022-01-01 09:00:00 +10:00')  # @UnusedVariable
        cls.session03 = cls.create_session(cls.game0, [cls.player1, cls.player2, cls.player5, cls.player6], [1, 3, 4, 2], '2022-01-01 10:00:00 +10:00')  # @UnusedVariable
        cls.session04 = cls.create_session(cls.game0, [cls.player1, cls.player4, cls.player5, cls.player3], [1, 2, 3, 4], '2022-01-01 11:00:00 +10:00')  # @UnusedVariable

        # Save a this fixture for use in manual testing too
        management.call_command('dumpdata', natural_foreign=True, indent=4, output="CoGs_test_data.json")

    def test_teams(self):
        '''
        Testing team creation, and editing ...

        Teams have a get_create_or_edit class method that is responsible for finding a team given a set of players
        and optionally rename it or chaging it splayer set. This is tested here.
        '''

        # Collect existing teams
        existing_team_ids = set([t.pk for t in Team.objects.all()])

        # We need some teams existing already (they should have been bult in setUpTestData.
        self.assertTrue(len(existing_team_ids) > 0)

        ##################################################################
        # CREATING NEW TEAM

        # Create a new team:
        players = self.pgroup1_6  # 6 members
        team = Team.get_create_or_edit(players, debug=True)
        self.assertNotIn(team.id, existing_team_ids)
        self.assertGreater(team.id, max(existing_team_ids))
        self.assertIsNone(team.name)
        self.assertEqual(set(team.players.all()), set(players))

        # Create a new one with a name:
        players = self.pgroup1_4  # 4 members
        name = "Fantastic Four"
        team = Team.get_create_or_edit(players, name=name, debug=True)
        self.assertNotIn(team.id, existing_team_ids)
        self.assertGreater(team.id, max(existing_team_ids))
        self.assertEqual(team.name, name)
        self.assertEqual(set(team.players.all()), set(players))

        # Re-collect existing teams
        existing_team_ids = set([t.pk for t in Team.objects.all()])

        ##################################################################
        # GET EXISTING TEAM

        # Get an existing team:
        team = Team.objects.first()
        players = team.players.all()
        team_id = team.pk

        team = Team.get_create_or_edit(players, debug=True)
        self.assertEqual(team.pk, team_id)
        self.assertIn(team.id, existing_team_ids)
        self.assertEqual(set(team.players.all()), set(players))

        # Get an existing one and rename it
        players = self.pgroup1_4  # 4 members @UndefinedVariable
        name = "Fabulous Four"
        team = Team.get_create_or_edit(players, name=name, debug=True)
        self.assertIn(team.id, existing_team_ids)
        self.assertEqual(team.name, name)
        self.assertEqual(set(team.players.all()), set(players))

        ##################################################################
        # EDIT EXITSING TEAM (i.e pass "edit" parameter)

        ##################################################################
        # WITH NO RANK/SESSION REFERENCES

        #################################################
        # Assign players WITH NO existing team!
        # Get the team
        team = Team.objects.filter(ranks__session=None).first()

        # And assign new players
        players = self.pgroup3_5

        # Make sure they are new
        old_players = list(team.players.all())
        self.assertNotEqual(players, old_players, "Test poorly configured: Needs a list of players different from the team being altered,")

        # And that no existing team has these players
        self.assertFalse(Team.exists(players))

        # Confirm our team has no ranks
        self.assertFalse(team.ranks.all())

        # Now do the deed (edit it)
        name = "Terrible Trio"
        old_team = team
        team = Team.get_create_or_edit(players, name=name, edit=(old_team.id, None, None), debug=True)

        # The team ID was fine to reuse (as there were no references)
        self.assertIn(team.id, existing_team_ids)
        self.assertEqual(team.id, old_team.id)

        # It should have the newly set properies.
        self.assertEqual(team.name, name)
        self.assertEqual(set(team.players.all()), set(players))

        #################################################
        # Assign players that ARE IN an existing team.
        # Get the team
        team = Team.objects.filter(ranks__session=None).first()

        # And assign new players
        players = self.pgroup1_3

        # Make sure they are new
        old_players = list(team.players.all())
        self.assertNotEqual(players, old_players, "Test poorly configured: Needs a list of players different from the team being altered,")

        # And that as existing team has these players
        self.assertTrue(Team.exists(players))

        # Confirm our team has no ranks
        self.assertFalse(team.ranks.all())

        # Now do the deed (edit it)
        name = "Troubled Trio"
        old_team = team
        team = Team.get_create_or_edit(players, name=name, edit=(old_team.id, None, None), debug=True)

        # An exiting team should be returned
        self.assertIn(team.id, existing_team_ids)

        # Which is not the supplies one
        self.assertNotEqual(team.id, old_team.id)

        # The supplied one should have been killed as it had no references
        self.assertFalse(Team.objects.filter(pk=old_team.id).exists())
        self.assertFalse(Team.exists(old_players))

        # And the returned team should have the expected configuration.
        self.assertEqual(team.name, name)
        self.assertEqual(set(team.players.all()), set(players))

        ##################################################################
        # WITH A SINGLE RANK/SESSION REFERENCE

        #################################################
        # Assign players WITH NO existing team! Don't provide the rank/session reference
        session = self.sessionTH3

        # Get a team from that session
        session_teams = list(session.teams)
        self.assertTrue(len(session_teams) > 1)
        team = session_teams[0]
        rank = session.ranks.get(team=team)

        # Confirm it has one rank/session reference
        self.assertEqual(team.sessions.count(), 1)
        self.assertEqual(team.ranks.all().count(), 1)

        # And assign new players
        players = self.pgroup1_6

        # Make sure they are new
        old_players = list(team.players.all())
        self.assertNotEqual(players, old_players, "Test poorly configured: Needs a list of players different from the team being altered,")

        # Confirm no existing team has these players
        self.assertFalse(Team.exists(players))
        self.assertEqual(Team.get(players).count(), 0)

        # Now do the deed (edit it)
        name = "Sexy Sextet"
        old_team = team
        team = Team.get_create_or_edit(players, name=name, edit=(old_team.id, None, None), debug=True)

        # As there was only one reference to the team but we did not provide a rank or team ID
        # We assumed that reference to provide the unsupplied rank and session ID so reused the
        # old team.

        # The old team (being edited) should be returned
        self.assertIn(team.id, existing_team_ids)
        self.assertEqual(team.id, old_team.id)

        # With the new configuration
        self.assertEqual(team.name, name)
        self.assertEqual(set(team.players.all()), set(players))

        # The old player set by defintion cannot have a team now because its team was repurposed.
        self.assertFalse(Team.exists(old_players))

        # The rank should still have this team
        self.assertTrue(rank.team == team)

        #################################################
        # Assign players WITH NO existing team! Do provide the rank/session reference
        session = self.sessionTH3

        # Get a team from that session
        session_teams = list(session.teams)
        self.assertTrue(len(session_teams) > 1)
        team = session_teams[0]
        rank = session.ranks.get(team=team)

        # Confirm it has a single rank/session reference
        self.assertEqual(team.sessions.count(), 1)
        self.assertEqual(team.ranks.all().count(), 1)

        # Choose new players
        players = self.pgroup3_8

        # Confirm these players differ from the existing team players
        old_players = list(team.players.all())
        self.assertNotEqual(players, old_players, "Test poorly configured: Needs a list of players different from the team being altered,")

        # Confirm no team exists with those players
        self.assertFalse(Team.exists(players))
        self.assertEqual(Team.get(players).count(), 0)

        # Now do the deed (edit it)
        name = "Super Sextet"
        old_team = team
        team = Team.get_create_or_edit(players, name=name, edit=(old_team.id, rank.id, session.id), debug=True)

        # As there was only one reference to the team but we provided rank and sesison IDs then
        # the relationships are checked and we proceed as before (whem they were inferred)

        # The old team (being edited) should be returned
        self.assertIn(team.id, existing_team_ids)
        self.assertEqual(team.id, old_team.id)

        # With the new configuration
        self.assertEqual(team.name, name)
        self.assertEqual(set(team.players.all()), set(players))

        # The old player set by defintion cannot have a team now because its team was repurposed.
        self.assertFalse(Team.exists(old_players))

        # The rank should still have this team
        self.assertTrue(rank.team == team)

        #################################################
        # Assign players THAT HAVE an existing team! Do provide the rank/session reference
        session = self.sessionTH3

        # Get a team from that session
        session_teams = list(session.teams)
        self.assertTrue(len(session_teams) > 1)
        team = session_teams[0]
        rank = session.ranks.get(team=team)

        # Confirm it has a single session reference
        self.assertEqual(team.sessions.count(), 1)
        self.assertEqual(team.ranks.all().count(), 1)

        # Choose new players
        players = self.pgroup1_4

        # Confirm these players differ from the existing team players
        old_players = list(team.players.all())
        self.assertNotEqual(players, old_players, "Test poorly configured: Needs a list of players different from the team being altered,")

        # Confirm that these players are in another team
        self.assertTrue(Team.exists(players))
        self.assertGreater(Team.get(players).count(), 0)

        # Now do the deed (edit it)
        name = "Quite a Quartet"
        old_team = team
        team = Team.get_create_or_edit(players, name=name, edit=(old_team.id, rank.id, session.id), debug=True)

        # The Team ID should be a prexisting one now, but different to the old one
        self.assertIn(team.id, existing_team_ids)
        self.assertNotEqual(team.id, old_team.id)

        # Check that the new team is configured as expected
        self.assertEqual(team.name, name)
        self.assertEqual(set(team.players.all()), set(players))

        # Check that we killed the old team! It had the one reference which has been replece
        self.assertFalse(Team.objects.filter(pk=old_team.id).exists())
        self.assertFalse(Team.exists(old_players))

        # Check that reference was in fact replaced
        rank.refresh_from_db()
        self.assertTrue(rank.team == team)  # NOT old_team

        ##################################################################
        # WITH MULTIPLE RANK/SESSION REFERENCES

        #################################################
        # Assign players THAT HAVE an existing team! Do provide the rank/session reference
        #
        # We expect the old team NOT to be killed but the first team taking its place
        # in the edit session.
        session = self.sessionTH2

        # Get a team from that session
        session_teams = list(session.teams)
        self.assertTrue(len(session_teams) > 1)
        team = session_teams[0]
        rank = session.ranks.get(team=team)

        # Confirm it has more than one session reference
        self.assertGreater(team.sessions.count(), 1)
        self.assertGreater(team.ranks.all().count(), 1)

        # Choose new players
        players = self.pgroup1_4

        # Confirm these players differ from the existing team players
        old_players = list(team.players.all())
        self.assertNotEqual(players, old_players, "Test poorly configured: Needs a list of players different from the team being altered,")

        # Confirm that these players are in another team
        self.assertTrue(Team.exists(players))
        self.assertGreater(Team.get(players).count(), 0)

        # Now do the deed (edit it)
        name = "A Quiet Quartet"
        old_team = team
        team = Team.get_create_or_edit(players, name=name, edit=(old_team.id, rank.id, session.id), debug=True)

        # The Team ID should be a prexisting one now, but different to the old one
        self.assertIn(team.id, existing_team_ids)
        self.assertNotEqual(team.id, old_team.id)

        # Check that the new team is configured as expected
        self.assertEqual(team.name, name)
        self.assertEqual(set(team.players.all()), set(players))

        # Check that we did not kill the old team!
        self.assertTrue(Team.objects.filter(pk=old_team.id).exists())
        self.assertTrue(Team.exists(old_players))

        # Check that reference was in fact replaced
        rank.refresh_from_db()
        self.assertTrue(rank.team == team)  # NOT old_team

    def session_dict_test_scenario(self, operation="add", form_data_mods={}):
        '''
        Test a provided session dict scenario. A helper for test_session_dicts().

        Creates a session with a form submission and checks form_dict, resulting object_dict and delta.
        Edits the same session with a form submission with no changes and performs same checks
        Edits the same session with a form submission with non rating-rebuild triggering changes with same checks

        TODO: Edit same saession with rating rebuild triggers, tested individually.

        :param form_data_mods: A dict of form_data modifications on the basis create scenario
        '''
        self.assertIn(operation, ("add", "edit"))

        game = Game.objects.get(name="NO_SCORES").pk
        league = League.objects.get(name="League1").pk
        location = Location.objects.get(name="Location2").pk
        player1 = Player.objects.get(name_nickname="Player1").pk  # @UndefinedVariable
        player2 = Player.objects.get(name_nickname="Player2").pk  # @UndefinedVariable

        form_data = {
                    'game': str(game),
                    'date_time': '2022-07-02 03:59:00 +10:00',
                    'league': str(league),
                    'location': str(location),
                    'Rank-TOTAL_FORMS': '2',
                    'Rank-INITIAL_FORMS': '0',
                    'Rank-MIN_NUM_FORMS': '0',
                    'Rank-MAX_NUM_FORMS': '1000',
                    'Performance-TOTAL_FORMS': '2',
                    'Performance-INITIAL_FORMS': '0',
                    'Performance-MIN_NUM_FORMS': '0',
                    'Performance-MAX_NUM_FORMS': '1000',
                    'num_players': '2',
                    'Rank-0-rank': '1',
                    'Rank-0-score': '',
                    'Rank-0-player': str(player1),
                    'Rank-1-rank': '2',
                    'Rank-1-score': '',
                    'Rank-1-player': str(player2),
                    'Performance-0-player': str(player1),
                    'Performance-0-partial_play_weighting': '1',
                    'Performance-1-player': str(player2),
                    'Performance-1-partial_play_weighting': '1'
                    }

        form_data.update(form_data_mods)

        dt_expect = make_aware(parser.parse(form_data['date_time']))

        ##################################################################
        # FORM DICT

        # Get the form dict and assert the expectation
        form_dict = Session.dict_from_form(form_data)

        expect = {"model": "Session",
                  "id": form_data.get('id', MV),
                  "game": int(form_data['game']),
                  "time": dt_expect,
                  "league": int(form_data['league']),
                  "location": int(form_data['location']),
                  "team_play": False,
                  "ranks": [form_data.get(f'Rank-{i}-id', MV) for i in range(int(form_data['Rank-TOTAL_FORMS']))],
                  "rankings": [1, 2],
                  "rscores": [MV, MV],
                  "rankers": [player1, player2],
                  "performances": [form_data.get(f'Performance-{i}-id', MV) for i in range(int(form_data['Performance-TOTAL_FORMS']))],
                  "pscores": [MV, MV],
                  "performers": [player1, player2],
                  "weights": [1, 1]
                 }

        try:
            self.assertEqual(form_dict, expect)
        except:
            breakpoint()
            pass

        ##################################################################
        # POST FORM

        # Submit the form and assert the expected response
        response = self.client.post(f"/{operation}/Session/{form_data.get('id', '')}", form_data)

        self.assertEqual(response.status_code, 302)  # A Redirect
        self.assertIn('Location', response.headers)  # The redirection target

        # A session ID is assign on submission and that ID is in the redirect location
        redirect_to = response.headers['Location']
        pattern = re.compile(r"/impact/Session/(\d+)\?submission=(create|update)&changed=(\d+)")
        self.assertRegex(redirect_to, pattern)

        matches = re.match(pattern, redirect_to)
        session_id = int(matches.group(1))
        change = matches.group(2)
        change_id = matches.group(3)  # @UnusedVariable

        self.assertEqual(change, "create" if operation == "add" else "update")

        session = Session.objects.get(pk=session_id)  # @UndefinedVariable

        ##################################################################
        # OBJECT DICT

        # Get the object dict and assert the expectation
        object_dict = session.dict_from_object

        # The expectation is the submitted for with the
        # (on account of objects being created in the database
        #  in the add operation or having been available from the
        #  get go with an edit operation):
        #    a session ID
        #    a datetime with in the default timezone that saving used
        #    rank IDs
        #    performance IDs
        #
        # For an add operation our expectation are taken form the saved DB object.
        # For and edit operation it is taken from the submitted form

        expect = {"model": "Session",
                  "id": session.pk if operation == "add" else int(form_data['id']),
                  "game": session.game.pk if operation == "add" else int(form_data['game']),
                  "time": dt_expect.astimezone(session.date_time_tz),
                  "league": session.league.pk if operation == "add" else int(form_data['league']),
                  "location": session.location.pk if operation == "add" else int(form_data['location']),
                  "team_play": False,
                  "ranks": [r.pk for r in session.ranks.all()] if operation == "add"
                      else [form_data[f'Rank-{i}-id'] for i in range(int(form_data['Rank-TOTAL_FORMS']))],
                  "rankings": [1, 2],
                  "rscores": [MV, MV],
                  "rankers": [player1, player2],
                  "performances": [p.pk for p in session.performances.all()]if operation == "add"
                             else [form_data[f'Performance-{i}-id'] for i in range(int(form_data['Performance-TOTAL_FORMS']))],
                  "pscores": [MV, MV],
                  "performers": [player1, player2],
                  "weights": [1.0, 1.0]
                 }

        self.assertEqual(object_dict, expect)

        ##################################################################
        # DELTA DICT

        # _________________________________________________________________
        # BAD PK PROVIDED DELTA
        # Get the dict delta and assert the expectation (with WRONG PK provided)
        if 'id'in form_data:
            form_data['id'] += 1

        delta = session.dict_delta(form_data, session.pk + 1)

        # The session, ranks and performance IDs are all deltas.
        # This is a highly artificial use case, not ever expected.
        # Submitting a bad PK with the form data, one that does not
        # agree with the session as it was saved, lists "id" under
        # changes which should indicate an impossible scenario as
        # it is immutable (not editable) - the session id, that is.
        expect = {'model': 'Session',
                  'id': (session.pk, session.pk + 1),
                  'game': session.game.pk,
                  'time': dt_expect.astimezone(session.date_time_tz),
                  'league': session.league.pk,
                  'location': session.location.pk,
                  'team_play': False,
                  'ranks': MV,  # Added below
                  'rankings': [1, 2],
                  'rscores': [MV, MV],
                  'rankers': [1, 2],
                  'performances': MV,  # Added below
                  'pscores': [MV, MV],
                  'performers': [player1, player2],
                  'weights': [1.0, 1.0],
                  'changes': MV  # Added below
                }

        # The add operation should note a change from missing rank and performance IDs
        # to existing rank and performance ID.
        if operation == "add":
            expect['ranks'] = ([r.pk for r in session.ranks.all()], [MV, MV])
            expect['performances'] = ([p.pk for p in session.performances.all()], [MV, MV])
            expect['changes'] = ('changed', 'id', 'ranks', 'performances')
        # The edit operation should note no such change as the rank and performance IDs
        # existed when the edit form was loaded and are submitted.
        else:
            expect['ranks'] = [r.pk for r in session.ranks.all()]
            expect['performances'] = [p.pk for p in session.performances.all()]
            expect['changes'] = ('changed', 'id')

        self.assertEqual(delta, expect)

        # _________________________________________________________________
        # GOOD PK PROVIDED DELTA
        # Get the dict delta and assert the expectation (with PK provided)
        if 'id'in form_data:
            form_data['id'] = session.pk

        delta = session.dict_delta(form_data, session.pk)

        # The session, ranks and performance IDs are all deltas.
        # This is the clean use case, when form data is provided and a PK with it so that
        # object_dict and form_dict compare perfectly when there is no change made including
        # ids.
        expect['id'] = session.pk

        # If adding there's a change in rank and performance IDs
        # (object has them, form did not).
        if operation == "add":
            expect['changes'] = ('changed', 'ranks', 'performances')
        # If editing there's no change expected (the from had rank and performance IDs
        else:
            expect['changes'] = ('unchanged',)

        self.assertEqual(delta, expect)

        # _________________________________________________________________
        # BASIC DELTA
        # Get the dict delta and assert the expectation
        delta = session.dict_delta(form_data)

        # The session, ranks and performance IDs are all deltas.
        # This is also an expected use case, if not as clean as providing the PK the difference
        # is of no grave consequnce. ID is presented as changed (old and new with the new one as
        # MISSING_VALUE) but not listed as a change (as it's not relevant to change detection).
        # But the chage is listed a s"created" not "changed" because of missing form session PK.

        # If adding there's a change in session, rank and performance IDs
        # (object has them, form did not), though a session ID change should
        # not be flagged.
        if operation == "add":
            expect['id'] = (session.pk, MV)
            expect['changes'] = ('created', 'ranks', 'performances')
        else:
            expect['id'] = session.pk
            expect['changes'] = ('unchanged',)

        self.assertEqual(delta, expect)

        # RETURN BASIC DELTA
        return delta

    def test_session_dicts(self):
        '''
        Testing session dictionary from and to form data
                Leaderboards.models.session.Session.dict_from_object
                Leaderboards.models.session.Session.dict_from_form

        Specifically we want that one created from the form is the same as the one created
        from the subsequently saved object and also thta:

            Leaderboards.models.session.Session.dict_delta

        shows nothing on a subsequent resubmission.
        '''

        self.client.login(username='admin', password='password')

        ###########################################################################################################################3
        # CREATE Session:

        # Returns a basic DELTA
        delta = self.session_dict_test_scenario()

        ###########################################################################################################################3
        # EDIT Session: submit unchanged

        # From the saved session (0th element of the BASIC DELTA) we can extract what was missing in the
        # creation form:
        #     the session ID, the rank and performance IDs
        # so we can assemble an edit form submission
        session_id = delta["id"][0]
        rank_ids = delta["ranks"][0]
        performance_ids = delta["performances"][0]

        form_mod = {**{'id': session_id,
                       'Rank-INITIAL_FORMS': 2,
                       'Performance-INITIAL_FORMS': 2
                       },
                    **{f'Rank-{i}-id': rid for i, rid in enumerate(rank_ids)},
                    **{f'Performance-{i}-id': pid for i, pid in enumerate(performance_ids)}}

        delta = self.session_dict_test_scenario("edit", form_mod)

        ###########################################################################################################################3
        # EDIT Session: submit changed with no rebuild expected
        #
        # A rating rebuild is triggered (for any session following the edited session) if any of the
        # TureSkill player ratings as a result of this session change or if the order of sessions is
        # changed.
        #
        # Rebuilds should be triggered by any change that alters:
        #    - the time of a session such that it changes the order of sessions for the game
        #    - a change in the game
        #    - a change in any players
        #    - a change in the rankings
        #        - scores can impact rankings but otehrwise don't impact
        #        - the order of rankings only is relevant, if they change but their order does not no rebuild triggered.
        #    - A change in partial play weightings
        # TODO: Complete this list and eveolve tests.

        # Change the submission (non rebuild triggering changes only this time)
        form_mod.update({'date_time': '2022-07-02 03:59:00 +11:00',
                         'league': str(League.objects.get(name="League2").pk),
                         'location': str(Location.objects.get(name="Location1").pk)})

        delta = self.session_dict_test_scenario("edit", form_mod)

        ###########################################################################################################################3
        # EDIT Session: submit rebuild triggering changes
        #
        # Rebuilds should be triggered by any change that alters:
        #    - the time of a session such that it changes the order of sessions for the game
        #    - a change in the game
        #    - a change in any players
        #    - a change in the rankings
        #        - scores can impact rankings but otehrwise don't impact
        #        - the order of rankings only is relevant, if they change but their order does not no rebuild triggered.
        #    - A change in partial play weightings

        # TODO: Test each rebuild trigger.
        #       Need to build richer session data to model each one.

        # Change the submission (non rebuild triggering changes only this time)
        # form_mod.update({})

        # delta = self.session_dict_test_scenario("edit", form_mod)

    def test_rank_reconciliation(self):
        '''
        Testing the rank reconciliation method (ensuring scores and ranks are all good)
        :param self:
        '''

        def build_session_dict(scoring, team_play, players, rankings, rscores, pscores):
            '''
            Build a subset of a the session_dict that:
                Leaderboards.models.session.Session.dict_from_object
                Leaderboards.models.session.Session.dict_from_form
            produce. Sufficent for testing:
                Leaderboards.views.pre_handlers.reconcile_ranks

            :param scoring: A string being the name of a Game.ScoringOptions enum item
            :param team_play: a boolean to denote team_play or not
            :param players: a list of player IDs or a list of lists of player IDs (in team_play). TODO: lose team_lay arg as can be inferred from this.
            :param rankings: a list of rankings
            :param rscores: a list of rscores
            :param pscores: a list of pscores
            '''
            game = Game.objects.get(name=scoring)
            return { "game": game.pk,
                     "team_play": team_play,
                     "performers": players,
                     "rankings": rankings,
                     "rscores": rscores,
                     "pscores": pscores }

        def run_test(form, scoring, team_play, rankings, rscores, pscores, permit_missing_scores=False):
            players = [i for i, _ in enumerate(pscores)]
            source_session = build_session_dict(scoring, team_play, players, rankings, rscores, pscores)
            reconc_session = deepcopy(source_session)
            reconcile_ranks(form, reconc_session, permit_missing_scores)
            diff_session = {}
            for k in source_session:
                if reconc_session[k] != source_session[k]:
                    diff_session[k] = (source_session[k], reconc_session[k])
            return diff_session

        class DummyForm():
            '''
            A basic dummy form that can receive errors for testing functions that take a form as an
            argument and ad errors to it. Implemented the add_error method only.
            '''
            errors = []

            def add_error(self, field, message):
                self.errors.append((field, message))

            def reset(self):
                self.errors = []

        form = DummyForm()

        #########################################################################################################
        # NO SCORES
        diff = run_test(form, "NO_SCORES", False, [2, 1], [MV, MV], [MV, MV])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = run_test(form, "NO_SCORES", False, [2, 1], [10, 20], [100, 200])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = run_test(form, "NO_SCORES", False, [MV, MV], [10, 20], [100, 200])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = run_test(form, "NO_SCORES", False, [-5, 2], [10, 20], [100, 200])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = run_test(form, "NO_SCORES", False, [1, 2], [-10, 20], [100, 200])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [])
        form.reset()

        #########################################################################################################
        # INDIVIDUAL_HIGH_SCORE_WINS
        diff = run_test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [2, 1], [MV, MV], [MV, MV])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [(None, 'This is a scoring game. Please enter scores')])
        form.reset()

        diff = run_test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [2, 1], [MV, MV], [MV, MV], True)
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = run_test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [2, 1], [10, 20], [MV, MV])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = run_test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [2, 1], [20, 10], [MV, MV])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [(None, 'Submitted rankings and scores do not agree.')])
        form.reset()

        diff = run_test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [MV, MV], [20, 10], [MV, MV])
        self.assertEqual(diff, {'rankings': ([MV, MV], [1, 2])})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = run_test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [MV, MV, MV, MV], [20, 10, 5, 10], [MV, MV, MV, MV])
        self.assertEqual(diff, {'rankings': ([MV, MV, MV, MV], [1, 2, 4, 2])})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = run_test(form, "INDIVIDUAL_HIGH_SCORE_WINS", True, [MV, MV, MV, MV], [20, 10, 5, 10], [MV, MV, MV, MV])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [(None, 'This is a game that does not score teams and so team play sessions can not be recorded. Likely a form or game configuration error.')])
        form.reset()

        diff = run_test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10], [MV, MV, MV, MV, MV, MV])
        self.assertEqual(diff, {'rankings': ([MV, MV, MV, MV, MV, MV], [1, 2, 5, 2, 6, 2])})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = run_test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [MV, MV, MV, MV, MV, MV], [MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])
        self.assertEqual(diff, {'rankings': ([MV, MV, MV, MV, MV, MV], [1, 2, 5, 2, 6, 2]), 'rscores': ([MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = run_test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [1, 2, MV, MV, 6, 2], [MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])
        self.assertEqual(diff, {'rankings': ([1, 2, MV, MV, 6, 2], [1, 2, 5, 2, 6, 2]), 'rscores': ([MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = run_test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [1, 2, MV, MV, 3, 2], [MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])
        self.assertEqual(diff, {'rankings': ([1, 2, MV, MV, 3, 2], [1, 2, 5, 2, 3, 2]), 'rscores': ([MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])})
        self.assertEqual(form.errors, [(None, 'Submitted rankings and scores do not agree.')])
        form.reset()

        #########################################################################################################
        # INDIVIDUAL_LOW_SCORE_WINS
        diff = run_test(form, "INDIVIDUAL_LOW_SCORE_WINS", False, [MV, MV, MV, MV, MV, MV], [MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])
        self.assertEqual(diff, {'rankings': ([MV, MV, MV, MV, MV, MV], [6, 3, 2, 3, 1, 3]), 'rscores': ([MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = run_test(form, "INDIVIDUAL_LOW_SCORE_WINS", False, [MV, MV, 2, 3, MV, MV], [MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])
        self.assertEqual(diff, {'rankings': ([MV, MV, 2, 3, MV, MV], [6, 3, 2, 3, 1, 3]), 'rscores': ([MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = run_test(form, "INDIVIDUAL_LOW_SCORE_WINS", False, [MV, MV, 3, 3, MV, MV], [MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])
        self.assertEqual(diff, {'rankings': ([MV, MV, 3, 3, MV, MV], [6, 3, 3, 3, 1, 3]), 'rscores': ([MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])})
        self.assertEqual(form.errors, [(None, 'Submitted rankings and scores do not agree.')])
        form.reset()

        #########################################################################################################
        # TEAM_HIGH_SCORE_WINS

        # TODO: Test all the Team scenarios

    def session_test_scenario(self,
                              operation,
                              game, players,
                              ranking=None,
                              date_time=None,
                              league=None,
                              location=None,
                              ppw=None,
                              rscores=None,
                              pscores=None,
                              expected_errors=None
                            ):
        '''
        A single session submission is made and tested.

        We want to

            1. test session submission for each rank/scoring scenario.
            2. test each of the rating rebuild trigger scenarios

        A basic submission framework is implemented here to help the driver
        tersely submit the required POST requests check the results.

        :param operation: A tuple eiher ("add") or ("edit", pk)
        :param game: A Game object or The name of a game (will be fetched by name)
        :param players: A list or list of lists of Player objects or players by name (individuals)
        :param ranking: A list of ranking values (one per player or team)
        :param date_time: a datetime string, will be parsed
        :param league: A League object or league name (will be fetched by name)
        :param location: A Location object or location name (will be fetched by name)
        :param ppw: Partial play weightings for the players (in same structure as players, list of floats, or list of lists of floats)
        :param rscores: Rank scores (0-1) as a list, one per rank
        :param pscores: Performance scores (0-1) as a list or list of lists (in same structure as players)
        :param expected_errors: a dict of expected errors
        '''
        self.assertTrue(isinstance(operation, (str, list, tuple)))
        if isinstance(operation, str):
            self.assertTrue(operation == "add")
        else:
            self.assertIn(operation[0], ("add", "edit"))
            if operation[0] == "edit":
                self.assertTrue(isinstance(operation[1], int))

        if not expected_errors is None:
            self.assertTrue(isinstance(expected_errors, dict))

        # Clean the args (returns a team_play flag too, inferred from the players structure)
        game, players, ranking, date_time, league, location, ppw, rscores, pscores, team_play = self.clean_session_args(
        game, players, ranking, date_time, league, location, ppw, rscores, pscores)

        ##################################################################
        # Fixed Form Data

        form_data = {
                    'game': str(game.pk),
                    'date_time': str(date_time),
                    'league': str(league.pk),
                    'location': str(location.pk),
                    'Rank-TOTAL_FORMS': MV,
                    'Rank-INITIAL_FORMS': '0',
                    'Rank-MIN_NUM_FORMS': '0',
                    'Rank-MAX_NUM_FORMS': '1000',
                    'Performance-TOTAL_FORMS': MV,
                    'Performance-INITIAL_FORMS': '0',
                    'Performance-MIN_NUM_FORMS': '0',
                    'Performance-MAX_NUM_FORMS': '1000',
                    }

        if operation[0] == "edit":
            form_data['id'] = str(operation[1])

        ##################################################################
        # Player Count Dependent Form Data

        if team_play:
            form_data['team_play'] = 'on'
            form_data['num_teams'] = len(players)
        else:
            form_data['num_players'] = len(players)

        form_data['Rank-TOTAL_FORMS'] = str(len(players))

        if team_play:
            pcount = 0
            for p in players:
                pcount += len(p)
        else:
            pcount = len(players)

        form_data['Performance-TOTAL_FORMS'] = str(pcount)

        for i, r in enumerate(ranking):
            if r: form_data[f'Rank-{i}-rank'] = r
            if rscores[i]: form_data[f'Rank-{i}-score'] = rscores[i]

            if team_play:
                form_data[f'Team-{i}-num_players'] = str(len(players[i]))
            else:
                form_data[f'Rank-{i}-player'] = str(players[i].pk)

        if team_play:
            k = 0
            for i, t in enumerate(players):
                for j, p in enumerate(t):
                    form_data[f'Performance-{k}-player'] = str(p.pk)
                    form_data[f'Performance-{k}-team_num'] = str(i)
                    if pscores[i][j]: form_data[f'Performance-{k}-score'] = str(pscores[i][j])
                    form_data[f'Performance-{k}-partial_play_weighting'] = str(ppw[i][j])
                    k += 1

        else:
            for i, p in enumerate(players):
                form_data[f'Performance-{i}-player'] = str(p.pk)
                if pscores[i]: form_data[f'Performance-{i}-score'] = str(pscores[i])
                form_data[f'Performance-{i}-partial_play_weighting'] = str(ppw[i])

        ##################################################################
        # POST FORM

        # Submit the form and assert the expected response
        response = self.client.post(f"/{operation[0]}/Session/{form_data.get('id', '')}", form_data)

        if not expected_errors:
            self.assertEqual(response.status_code, 302)  # A Redirect
            self.assertIn('Location', response.headers)  # The redirection target

            # A session ID is assign on submission and that ID is in the redirect location
            redirect_to = response.headers['Location']
            pattern = re.compile(r"/impact/Session/(\d+)\?submission=(create|update)&changed=(\d+)")
            self.assertRegex(redirect_to, pattern)

            matches = re.match(pattern, redirect_to)
            session_id = int(matches.group(1))
            change = matches.group(2)
            change_id = matches.group(3)  # @UnusedVariable

            self.assertEqual(change, "create" if operation[0] == "add" else "update")

            session = Session.objects.get(pk=session_id)  # @UndefinedVariable

            return session
        else:
            errors = response.context_data['form'].errors
            self.assertEqual(errors, expected_errors)
            return None

    def test_session_submission(self):
        '''
        Testing the form submissions API.
        '''
        # So we can post session adds and edits
        self.client.login(username='admin', password='password')

        ##################################################################
        # NO_SCORES

        # _________________________________________________________________
        # A non scoring game
        session = self.session_test_scenario(("add",),
                                             "NO_SCORES",
                                             ["Player1", "Player2", "Player3", "Player4"],
                                             [1, 2, 3, 4]
                                            )

        ##################################################################
        # INDIVIDUAL_HIGH_SCORE_WINS

        # _________________________________________________________________
        # A scoring game without scores
        session = self.session_test_scenario(("add",),
                                             "INDIVIDUAL_HIGH_SCORE_WINS",
                                             ["Player1", "Player2", "Player3", "Player4"],
                                             [1, 2, 3, 4],
                                             expected_errors={'__all__': ['This is a scoring game. Please enter scores']}
                                            )
        # _________________________________________________________________
        # A scoring game with scores and no ranks
        session = self.session_test_scenario(("add",),
                                             "INDIVIDUAL_HIGH_SCORE_WINS",
                                             ["Player1", "Player2", "Player3", "Player4"],
                                             rscores=[10, 20, 30, 40]
                                            )
        # _________________________________________________________________
        # Confirm the ranks were generated as expected
        ranked_players = [p.name_nickname for p in session.ranked_players.values()]
        self.assertEqual(ranked_players, ["Player4", "Player3", "Player2", "Player1"])

        # _________________________________________________________________
        # A scoring game with agreeing scores
        session = self.session_test_scenario(("add",),
                                             "INDIVIDUAL_HIGH_SCORE_WINS",
                                             ["Player1", "Player2", "Player3", "Player4"],
                                             [1, 2, 3, 4],
                                             rscores=[40, 30, 20, 10]
                                            )
        # _________________________________________________________________
        # A scoring game with conflicting scores and ranks
        session = self.session_test_scenario(("add",),
                                             "INDIVIDUAL_HIGH_SCORE_WINS",
                                             ["Player1", "Player2", "Player3", "Player4"],
                                             [1, 2, 3, 4],
                                             rscores=[10, 20, 30, 40],
                                             expected_errors={'__all__': ['Submitted rankings and scores do not agree.']}
                                            )
        # _________________________________________________________________
        # A scoring game with a tie
        session = self.session_test_scenario(("add",),
                                             "INDIVIDUAL_HIGH_SCORE_WINS",
                                             ["Player1", "Player2", "Player3", "Player4"],
                                             rscores=[10, 20, 20, 30]
                                            )

        ranks = [r for r in session.ranked_players.keys()]
        players = [p.pk for p in session.ranked_players.values()]

        self.assertEqual(ranks, ['1', '2.1', '2.2', '3'])
        self.assertEqual(players, [4, 2, 3, 1])

        # _________________________________________________________________
        # A scoring game with ranks as tie breaks
        session = self.session_test_scenario(("add",),
                                             "INDIVIDUAL_HIGH_SCORE_WINS",
                                             ["Player1", "Player2", "Player3", "Player4"],
                                             [4, 2, 3, 1],
                                             rscores=[10, 20, 20, 30]
                                            )

        ranks = [r for r in session.ranked_players.keys()]
        players = [p.pk for p in session.ranked_players.values()]

        self.assertEqual(ranks, ['1', '2', '3', '4'])
        self.assertEqual(players, [4, 2, 3, 1])

        ##################################################################
        # INDIVIDUAL_LOW _SCORE_WINS
        # _________________________________________________________________
        # A scoring game without scores
        session = self.session_test_scenario(("add",),
                                             "INDIVIDUAL_LOW_SCORE_WINS",
                                             ["Player1", "Player2", "Player3", "Player4"],
                                             [1, 2, 3, 4],
                                             expected_errors={'__all__': ['This is a scoring game. Please enter scores']}
                                            )
        # _________________________________________________________________
        # A scoring game with scores and no ranks
        session = self.session_test_scenario(("add",),
                                             "INDIVIDUAL_LOW_SCORE_WINS",
                                             ["Player1", "Player2", "Player3", "Player4"],
                                             rscores=[30, 20, 10, 40]
                                            )
        # Confirm the ranks were generated as expected
        ranked_players = [p.name_nickname for p in session.ranked_players.values()]
        self.assertEqual(ranked_players, ["Player3", "Player2", "Player1", "Player4"])
        # _________________________________________________________________
        # A scoring game with agreeing scores
        session = self.session_test_scenario(("add",),
                                             "INDIVIDUAL_LOW_SCORE_WINS",
                                             ["Player1", "Player2", "Player3", "Player4"],
                                             [1, 2, 3, 4],
                                             rscores=[10, 20, 30, 40]
                                            )
        # _________________________________________________________________
        # A scoring game with conflicting scores and ranks
        session = self.session_test_scenario(("add",),
                                             "INDIVIDUAL_LOW_SCORE_WINS",
                                             ["Player1", "Player2", "Player3", "Player4"],
                                             [1, 2, 3, 4],
                                             rscores=[40, 30, 20, 10],
                                             expected_errors={'__all__': ['Submitted rankings and scores do not agree.']}
                                            )

        ##################################################################
        # TEAM_HIGH_SCORE_WINS

        # _________________________________________________________________
        # A scoring game without scores
        session = self.session_test_scenario(("add",),
                                             "TEAM_HIGH_SCORE_WINS",
                                             [["Player1", "Player2"], ["Player3", "Player4"]],
                                             [1, 2],
                                             expected_errors={'__all__': ['This is a scoring game. Please enter scores']}
                                            )
        # _________________________________________________________________
        # A scoring game with rscores and no ranks
        session = self.session_test_scenario(("add",),
                                             "TEAM_HIGH_SCORE_WINS",
                                             [["Player1", "Player2"], ["Player3", "Player4"]],
                                             rscores=[10, 20]
                                            )
        # Confirms the teams exist
        players = {}
        for r in session.ranks.all():
            self.assertTrue(isinstance(r.team, Team))
            players[r] = set([p.name_nickname for p in r.team.players.all()])

        for rank, team in players.items():
            # And that ranks were correctly assigned
            if rank.score == 20:
                self.assertEqual(team, set(["Player3", "Player4"]))
                self.assertEqual(rank.rank, 1)
            elif rank.score == 10:
                self.assertEqual(team, set(["Player1", "Player2"]))
                self.assertEqual(rank.rank, 2)
            else:
                self.fail()

        # _________________________________________________________________
        # A scoring game with pscores and no rscores or ranks
        session = self.session_test_scenario(("add",),
                                             "TEAM_HIGH_SCORE_WINS",
                                             [["Player1", "Player2"], ["Player3", "Player4"]],
                                             pscores=[[2, 8], [11, 9]]
                                            )
        # Confirms the teams exist
        players = {}
        for r in session.ranks.all():
            self.assertTrue(isinstance(r.team, Team))
            players[r] = set([p.name_nickname for p in r.team.players.all()])

        for rank, team in players.items():
            # And that ranks and rank scores were correctly derived
            if rank.score == 20:
                self.assertEqual(team, set(["Player3", "Player4"]))
                self.assertEqual(rank.rank, 1)
            elif rank.score == 10:
                self.assertEqual(team, set(["Player1", "Player2"]))
                self.assertEqual(rank.rank, 2)
            else:
                self.fail()

