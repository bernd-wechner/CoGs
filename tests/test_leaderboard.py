'''
Basic tests for the Leaderbaord API

The main driver here is in testing that session submissions work and are stable.
'''
import json

from django.test import TestCase
from django.urls import reverse

from Leaderboards.models import Session, Game, Player, Team, Rank, Performance, League, Location, Tourney, MISSING_VALUE as MV
from Leaderboards.leaderboards.options import leaderboard_options

from .test_DB_defintion import setup_test_database

def board_stats(result):
    '''
    Given a JSON string returned by an AJAX request to the server,returns some basic stats
    on the structure for rapid diagnosis of the result.

    The top layer of boards is expected as:
        title, subtitle, options, games[]
    The top layer of a game is expected as define dby:
        Leaderboards.models.game.Game.wrapped_leaderboard
    currently with elements:
        0 game.pk,
        1 game.BGGid
        2 game.name
        3 total number of plays
        4 total number sessions played
        5 A flag, True if data is a list, false if it is only a single value.
            The value is either a player_list (game_wrapped_player_list)
            or a session_wrapped_player_list (game_wrapped_session_wrapped_player_list)
        6 A flag, True if a reference snapshot is included
        7 A flag, True if a baseline snapshot is included
        8 data (a session snapshot - session wrapped player list)

    The last element is always the session snapshot, which has its top
    layer defined by:
        Leaderboards.models.session.Session.wrapped_leaderboard
    currently with elements:
        # Session metadata
        0 session.pk,
        1 session.date_time (in local time),
        2 session.game.play_counts()['total'],
        3 session.game.play_counts()['sessions'],

        # Player details
        4 session.players() (as a list of pks),

        # Some HTML analytic headers
        5 session.leaderboard_header(),
        6 session.leaderboard_analysis(),
        7 session.leaderboard_analysis_after(),

        # The leaderboard
        8 players[]

    The last element is always a player list and we always expect a rich one
    defined by:
        Leaderboards.leaderboards.enums.LB_PLAYER_LIST_STYLE.rich
    Which is a list of tupled defined by:
        Leaderboards.leaderboards.style.styled_player_tuple
    Which for a rich tuple currently includes:
        0 rank
        # player ID
        1 player PK
        2 player BGG name
        # name variants
        3 player nick name
        4 player full name
        5 player complete name
        # play stats
        6 number of plays
        7 number of victories
        8 last play of this game (PK)
        # leagues
        9 leagues[]

    :param result: A JSON repsone decoded and loaded with json.loads() already
    '''
    games = result[3]
    game_stats = {}
    for game in games:
        game_id = game[0]
        snaps = game[-1]
        snap_stats = {}
        for snap in snaps:
            session_id = snap[0]
            players = snap[-1]
            snap_stats[session_id] = [p[1] for p in players] # List of player IDs keyed on session ID
        game_stats[game_id] = snap_stats
    return game_stats


class LeaderboardTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.maxDiff = 2400  # To see diffs on some of the json dicts used in tests that are longish

        setup_test_database(cls)

    def response(self, view_name, get=""):
        return json.loads(self.client.get(reverse(view_name)+get).content.decode())

    ##########################################################################################################
    # Tests for the API options
    #
    # Will use the JSON API to check for stability of results (cnsistency with those captured as references)

    def test_board_selectors(self):
        '''
        Testing the board selection options.

        The test data is expected to hold 12 session between:
            '2022-01-01 00:00:00 +10:00'
        and:
            '2022-01-01 11:00:00 +10:00'
        inclusive, one hour apart.

        And 7 games, with IDs 0 to 6.

        Will need snaphots to test, so multiple session per game.
        '''
        # Get defaults for league 1
        lid = 1
        default = leaderboard_options(ufilter={'league': lid})

        if False:
            ######################################################################################
            # defaults
            response = self.response('json_leaderboards')
            stats = board_stats(response)

            # Confirm we got the default number of games
            self.assertEqual(len(stats), default.num_games, f"Expected {default.num_games} and got {len(stats)}.")
            # Confirm they are all in the filtered league
            # TODO: ensure test data has a game or two not in the league
            for gid in stats:
                game = Game.objects.get(pk=gid)
                self.assertIn(lid, game.leagues.all().values_list('pk', flat=True), f"Returned games must be in league {lid}. Game {gid} isn't.")
            # There is no ordering option yet
            # TODO: implement an ordering option
            #        latest_games does return them in order of last play though
            #        we could add an ordering option, with options lile popularity, most-recent, alphabetical
            # Ordering is by popularity, so reverse play count
            # So confirm the boards are presented in that order
            play_counts = []
            for game in response[-1]:
                play_counts.append(game[3])
            self.assertEqual(play_counts, sorted(play_counts, reverse=True), "Game leaderboards should be returned in reverse order of popularity")

            ######################################################################################
            # no defaults
            response = self.response('json_leaderboards', "?no_defaults")
            stats = board_stats(response)

            # Confirm we got all games
            n_games = Game.objects.all().count()
            self.assertGreater(n_games, default.num_games, f"Bad test config, more than {default.num_games} games are needed.")
            self.assertEqual(len(stats), n_games, f"Expected {n_games} and got {len(stats)}.")

            ######################################################################################
            # latest_games
            latest_games=4
            response = self.response('json_leaderboards', f"?latest_games={latest_games}")
            stats = board_stats(response)

            self.assertEqual(len(stats), latest_games, f"Expected {latest_games} and got {len(stats)}.")
            last_play = []
            for gid in stats:
                game = Game.objects.get(pk=gid)
                last_play.append(game.last_session.date_time)
            self.assertEqual(last_play, sorted(last_play, reverse=True), "Game leaderboards should be returned in reverse order of last time played")

        ######################################################################################
        # game_leagues (all and any)
        #
        # We need games in different leagues, at least three leagues, and two or more games
        # in each league.
        game_leagues = lambda gid: Game.objects.get(pk=gid).leagues.values_list('id', flat=True)

        response = self.response('json_leaderboards', f"?game_leagues_all=1,3")
        stats = board_stats(response)
        self.assertEqual(set(stats.keys()), {4, 5, 7})
        in_leagues = [gid for gid in stats if 1 in game_leagues(gid) and 3 in game_leagues(gid)]
        self.assertEqual(set(stats.keys()), set(in_leagues))

        # For debugging:
        # print(f"Game leagues: {[(g.pk, [l.pk for l in g.leagues.all()]) for g in Game.objects.all()]}")

        response = self.response('json_leaderboards', f"?game_leagues_any=2,3")
        stats = board_stats(response)
        self.assertEqual(set(stats.keys()), {1, 2, 3, 4, 5, 7})
        in_leagues = [gid for gid in stats if 2 in game_leagues(gid) or 3 in game_leagues(gid)]
        self.assertEqual(set(stats.keys()), set(in_leagues))

        ######################################################################################
        # game play stats (check last_play, session_count and play_count)
        #

        ######################################################################################
        # game_players (all and any)
        #
        # We need a good mix of games and players to test this.

        ######################################################################################
        # changed (after and before)

        ######################################################################################
        # game (ex and in)
        #
        # Ex should exclude all other selectors and end up only with the selected games.
        #    Test with top_games and latest_games and other options.
        # In should include all other selectors, so add these games to the mix.


    def test_player_selectors(self):
        '''
        '''
        pass

    def test_perspectives(self):
        '''
        '''
        pass

    def test_evolution(self):
        '''
        '''
        pass
