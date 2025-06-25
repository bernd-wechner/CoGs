
'''
Basic tests for the Leaderboard API

The main driver here is in testing that session submissions work and are stable.
'''
import json

from datetime import datetime
#from dateutil import parser
import dateparser as parser

from django.conf import settings
from django.utils.formats import localize
from django.utils.timezone import localtime

from Leaderboards.models import Session, Game, Player, Team, Rank, Performance, League, Location, Tourney, MISSING_VALUE as MV
from Leaderboards.leaderboards.options import leaderboard_options
from Leaderboards.leaderboards.enums import LB_STRUCTURE

from .runner import PostgreSQL_TestCase

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
        2 session.game.play_stats()['total'],
        3 session.game.play_stats()['sessions'],

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
    # Player ID
        1 player PK
        2 player BGG name
    # Name variants
        3 player nick name
        4 player full name
        5 player complete name
    # Rating
        6 eta
        7 mu
        8 sigma
    # Play stats
        9 number of plays
        10 number of victories
        11 last play of this game (PK)
    # leagues
        12 leagues[]

    :param result: A JSON response decoded and loaded with json.loads() already
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

def board_play_stats(result):
    '''
    Similar to board stats, but with a focus on extracting the play stats from each of the boards.
    (for testing those specifically).

    We're after three board stats (to test their stability):
        date of the last play (latest session in the snaps list)
        total number of plays (in the game wrapper)
        total number of sessions (in the game wrapper)

    We include the sessionID of the latest play because the date in the board is customized
    to the local timezone adding a complexity (also tested, but if  the last play date
    fails a test we want to know if the session is stable.

    :param result: A JSON response decoded and loaded with json.loads() already
    '''
    games = result[3]
    play_stats = {}
    for game in games:
        game_id = game[0]
        plays = game[3]
        sessions = game[4]

        snaps = game[-1] # get the list of snapshots
        latest = snaps[0] # get the latest (the only guranteed snapshot)
        last_session = latest[0] # Extract the session ID
        last_play = latest[1] # Extract its play date_time

        play_stats[game_id] = (plays, sessions, last_play, last_session)
    return play_stats

def game_league_stats(result):
    '''
    Similar to board stats, but with a focus on extracting the game leagues
    (for testing those specifically).

    :param result: A JSON response decoded and loaded with json.loads() already
    '''
    games = result[3]
    league_stats = {}
    for game in games:
        game_id = game[0]
        league_ids = [l.id for l in Game.objects.get(id=game_id).leagues.all()]

        league_stats[game_id] = league_ids
    return league_stats

def game_player_stats(result):
    '''
    Similar to board stats, but with a focus on extracting the game players
    (for testing those specifically).

    :param result: A JSON response decoded and loaded with json.loads() already
    '''
    games = result[3]
    player_stats = {}
    for game in games:
        game_id = game[0]
        player_ids = set()
        for s in Game.objects.get(id=game_id).sessions.all():
            player_ids.update([p.player.id for p in s.performances.all()])

        player_stats[game_id] = sorted(list(player_ids))
    return player_stats

def print_data_set():
    '''
    Useful for designing tests, this will just print the test data in a handy way
    '''
    all_games = Game.objects.all().order_by("id")
    print("\nTest Data Set Summary (Games, Sessions, Players):")
    for g in all_games:
        game_leagues = [l.id for l in g.leagues.all()]
        print(f"{g.id} {g.name} leagues:{game_leagues}:")
        sessions = Session.objects.filter(game=g).order_by("id")  # @UndefinedVariable
        for s in sessions:
            print(f"\t{s.id} {s.date_time} ({s.date_time_local}) league:{s.league.id}")
            for perf in s.performances.all():
                player_leagues = [l.id for l in perf.player.leagues.all()]
                print(f"\t\t{perf.id} {perf.player} leagues:{player_leagues}")

class LeaderboardTestCase(PostgreSQL_TestCase):

    ##########################################################################################################
    # Support functions for testing (do start name with test_ or will run as a test)
    
    def check_play_stats(self, result, options, league=None):
        '''
        Checks that the playstats meet expectations, and macth what the Game properties convey.
    
        :param result: A JSON response decoded and loaded with json.loads() already
        :param options: Leaderboard options in effect
        '''
        expected_order = options.order_games_by
        #order_dir = ["DESC" if k.startswith('-') else "ASC" for k in expected_order]
    
        response_stats = board_play_stats(result)
        
        # Check that the stats are right
        game_order_key = {}
        for g, (plays, sessions, last_play, _) in response_stats.items():
            game_order_key[g] = [(plays if k.endswith('play_count') 
                                 else sessions if k.endswith('session_count') 
                                 else parser.parse(last_play).timestamp() if k.endswith('last_play')
                                 else None) * (-1 if k.startswith('-') else 1)
                                 for k in expected_order]
            
            game = Game.objects.get(id=g)
            # TODO: Not options.leagues but options.game_leagues if enabled.
            stats = game.play_stats(leagues=options.leagues, 
                                     asat=options.as_at, 
                                     broad_session_count=options.show_cross_league_snaps, 
                                     broad_play_count=options.count_cross_league_plays)
            stats['last_play'] = localize(localtime(stats['last_play']))
            
            self.assertEqual(plays, stats['total'], f'Play count not as expected for game {g}. {league=}.')
            self.assertEqual(sessions, stats['sessions'], f'Session count not as expected for game {g}. {league=}.')
            self.assertEqual(last_play, stats['last_play'], f'Last play not as expected for game {g}. {league=}.')
            
        # Check that the ordering is honoured
        response_order = list(response_stats.keys())
        expected_order = list(dict(sorted(game_order_key.items(), key=lambda item: item[1])).keys())
        
        self.assertEqual(response_order, expected_order,f"Game ordering not as expected for keys: {game_order_key}. {league=}.")

    ##########################################################################################################
    # Tests for the API options
    #
    # Will use the JSON API to check for stability of results (cnsistency with those captured as references)

    def test_board_selectors(self):
        '''
        Testing the board selection options.

        TestCaseWithDB provides self.verbosity from the management command line:

        verbosity: 0=minimal output, 1=normal output, 2=verbose output, 3=very verbose output
        '''
        #OLD Attribuet fetcher
        #self.postgreSQL_init()
        testdb = self.__test_case_attributes__

        # If we need DEBUG enabled we need to force a reload too of the optios module
        if self.verbosity >= 3:
            print_data_set()
            settings.DEBUG = True
            import Leaderboards.leaderboards.options
            from importlib import reload
            reload(Leaderboards.leaderboards.options)

        # If tracing tests start on a new line (Django has just printed the first line of the functio comment and new new line)
        if self.verbosity >= 2: print()

        ######################################################################################
        # Defaults
        #
        # Check the default reponse to the logged in users preferred league
        
        # Cycle through four users checking the default leaderboard returns.
        # For each user the idea is it has a different default league and we're checking that 
        # logged in their default view is league filtered
        # The returns stats are checked manually during test design.
        # Ordering of games in these dicsts is irrelevant as we check order explicitly against
        # the options in effect. 
        users = {
            None: {1: [1, 2], 4: [1, 2, 3], 7: [1, 3], 6: [1, 3], 5: [1, 3], 3: [1, 2]},
            testdb.user_admin: {1: [1, 2], 4: [1, 2, 3], 7: [1, 3], 6: [1, 3], 5: [1, 3], 3: [1, 2]},
            testdb.user_notadmin1: {4: [1, 2, 3], 1: [1, 2], 3: [1, 2], 2: [1, 2]},
            testdb.user_notadmin2: {7: [1, 3], 6: [1, 3], 8: [3], 5: [1, 3], 4: [1, 2, 3], 10: [3]}
        }

        # # Logged in as ordinary user league 2 (test Implicit league filter)
        # lid, default = self.login_as(testdb.user_notadmin1)
        # if self.verbosity>=2: print(f"Testing default request (logged in as League {lid} user)")
        # response = self.JSON_response('json_leaderboards')
        # stats_login_ordinary1 = game_league_stats(response)
        # # Check the play stats first as they define the expected sorting and if they are wrong the boards won't be ordered as expected
        # self.assertTrue(check_play_stats(response, default), "leaderboard play stats not as expected.")
        # self.assertEqual(stats_login_ordinary1, {4: [1, 2, 3], 1: [1, 2], 3: [1, 2], 2: [1, 2]}, "Logged in (league 2) failed.")
        # self.client.logout()

        stats = {}
        opts = {}
        for user, expected_stats in users.items():
            if user:
                lid, options = self.login_as(user)
            else:
                lid, options = None, leaderboard_options()
                
            # Stroe the options for this league for validation_extras below
            opts[lid] = options

            if self.verbosity>=2: print(f"Testing default request (logged in as: {user} in league {lid})")
            response = self.JSON_response('json_leaderboards')

            # Check the play stats first as they define the expected sorting and if they are wrong the boards won't be ordered as expected
            # This also checks the ordering by htose stats (based on options)
            self.check_play_stats(response, options, lid)

            stats[user] = game_league_stats(response)

            # TODO: Consider adding last_play date_time to to the game wrapped header so all the ordering things are there.
            #       mainly for checking.
            
            # Check that we have no more than the default top num games
            if options.is_enabled('top_games'):
                self.assertLessEqual(len(stats[user]), leaderboard_options.num_games)

            # This result verified manually. Order checked with board_play_stats() above.
            self.assertEqual(stats[user], expected_stats, f"Default return failed for user: {user}.")

            if user:
                self.client.logout()
        
        validation_extras = True
        ############################################################################################################################
        # Validation of the preceding 4 tests based on a checked with this block that is not needed during ordinary test runs but
        # left here for reference and use in debugging in future.
        if validation_extras:
            # To validate these we need a list of all the games ordered by session, play count
            # and with league anotations. We build this explicityly (inneficiently) by examining
            # each game and add to it a four tuple of (session count, play count, last_play, set of leagues)
            def get_ordered_game_data(league=None):
                games = {}
                for game in Game.objects.all():
                    leagues = set([l.id for l in game.leagues.all()])
                    # Only games in the league
                    if league is None or league in leagues:
                        sessions = len(game.sessions.all() if league is None else game.sessions.filter(league__id=league))
                        plays = 0
                        if sessions > 0:
                            if league is None:
                                last = Session.objects.filter(game=game).order_by('-date_time')[0].date_time  # @UndefinedVariable
                            else:
                                # Only sessions in the league
                                last = Session.objects.filter(game=game, league__id=league).order_by('-date_time')[0].date_time  # @UndefinedVariable
                        else:
                            last = datetime.min
            
                        if league is None:
                            for s in game.sessions.all():
                                plays += len(s.performances.all())
                        else:
                            if opts[league].count_cross_league_plays:
                                for p in Performance.objects.filter(session__game=game):  # @UndefinedVariable
                                    if league in p.player.leagues.all().values_list('id', flat=True):
                                        plays += 1 
                            else:
                                for s in game.sessions.filter(league=league):
                                    plays += len(s.performances.all())
            
                        games[game.id] = (plays, sessions, last, leagues)
                ordered_games = {k: v for k, v in sorted(games.items(), key=lambda item: (item[1][0], item[1][1], item[1][2]), reverse=True)}
                # having ordered them turn the datetimes into nice strings else their repr sucks
                reordered_games = {}
                for game, data in ordered_games.items():
                    reordered_games[game] = (data[0], data[1], str(data[2]), list(data[3]))
                return reordered_games
            
            # Get the ordred list of games for each league
            games =  get_ordered_game_data()
            games_league1 =  get_ordered_game_data(1)
            games_league2 =  get_ordered_game_data(2)
            games_league3 =  get_ordered_game_data(3)
            
            # Get the top 6 of those
            top6 = {k: games[k][3] for k in list(games)[:min(6, len(games))]}
            top6_league1 = {k: games_league1[k][3] for k in list(games_league1)[:min(6, len(games_league1))] if games_league1[k][0]}
            top6_league2 = {k: games_league2[k][3] for k in list(games_league2)[:min(6, len(games_league2))] if games_league2[k][0]}
            top6_league3 = {k: games_league3[k][3] for k in list(games_league3)[:min(6, len(games_league3))] if games_league3[k][0]}
            
            print(f"returned, not logged in (no league): {len(stats[None])}\t{stats[None]}")
            print(f"expected, top6: {len(top6)}\t\t\t{top6}")
            print('PASS' if self.DictsEqual(stats[None], top6) else 'FAIL')
            
            print(f"admin (league {testdb.user_admin.player.league.id}): {len(stats[testdb.user_admin])}\t\t{stats[testdb.user_admin]}")
            print(f"top6_league1: {len(top6_league1)}\t\t\t{top6_league1}")
            print('PASS' if self.DictsEqual(stats[testdb.user_admin], top6_league1) else 'FAIL')
            
            print(f"ordinary 1 (league {testdb.user_notadmin1.player.league.id}): {len(stats[testdb.user_notadmin1])}\t{stats[testdb.user_notadmin1]}")
            print(f"top6_league2: {len(top6_league2)}\t\t\t{top6_league2}")
            print('PASS' if self.DictsEqual(stats[testdb.user_notadmin1], top6_league2) else 'FAIL')
            
            print(f"ordinary 2 (league {testdb.user_notadmin2.player.league.id}): {len(stats[testdb.user_notadmin2])}\t{stats[testdb.user_notadmin2]}")
            print(f"top6_league3: {len(top6_league3)}\t\t\t{top6_league3}")
            print('PASS' if self.DictsEqual(stats[testdb.user_notadmin2], top6_league3) else 'FAIL')

        ######################################################################################
        # No defaults
        #
        # 'no_defaults' - ignore default values, notably there's a default league and a
        #                 default top games filter.
        #
        # Regardless, we should get one board for each game (no filters in place)
        # whether logged in or not.
        if self.verbosity>=2: print("Testing ?no_defaults (when not logged in)")
        response = self.JSON_response('json_leaderboards', "?no_defaults")
        stats_no_defaults = game_league_stats(response)

        # Confirm we got all games
        n_games = Game.objects.all().count()
        self.assertGreater(n_games, leaderboard_options.num_games, f"Bad test config, more than {leaderboard_options.num_games} games are needed.")
        self.assertEqual(len(stats_no_defaults), n_games, f"Expected {n_games} and got {len(stats_no_defaults)}.")

        # When logged in the logged-in users preferred league is an implict filter no a default per se
        # So ?no_defaults should be the same as stats_login_ordinary2 but when delivered with an empty league
        # list like ?no_defaults&leagues it shoudl be the same as stats_no_defaults (no league filterimng.
        def test_no_defaults(no_league=""):
            lid, default = self.login_as(testdb.user_notadmin2)
            expected = Game.objects.all().count() if no_league else League.objects.get(id=lid).games.count()
            league_kill = f"&{no_league}" if no_league else ""
            if self.verbosity>=2: print(f"Testing ?no_defaults{league_kill} (when logged in as League {lid} user) - Expecting {expected} games of {Game.objects.all().count()}")
            response = self.JSON_response('json_leaderboards', f"?no_defaults{league_kill}")
            self.client.logout()
            stats_check = game_league_stats(response)
            # stats_no_defaults is with no log in and should have all the games (asserted above)
            # stats_login_ordinary2 was collected earlier when testing the league filter for logins
            #self.assertEqual(stats_check, stats_no_defaults if no_league else stats_login_ordinary2)

        test_no_defaults()
        test_no_defaults("leagues")
        test_no_defaults("game_leagues_any")
        test_no_defaults("game_leagues_all")

        ######################################################################################
        # top_games
        #
        # 'top_games',  # The top (most popular) self.num_games
        #
        # The aim is to select the most popular games.
        #
        # Popularity is measured on a descending sort on (session_count, play_count, last_play)
        # So:
        #      games most often hitting the table
        #      if tied, games that hosted the most players
        #      if tied, games played most recently
        #
        # It needs to respond to the league filter (implicit, through login and explict, GET param)
        def test_top(top_games):
            if self.verbosity>=2: print(f"Testing ?top_games={top_games}")
            response = self.JSON_response('json_leaderboards', f"?top_games={top_games}")
            stats = board_play_stats(response)

            self.assertEqual(len(stats), top_games, f"Expected {top_games} and got {len(stats)}.")
            # Re-sort the stats to check they are in order expected
            re_sorted = {k: v for k, v in sorted(stats.items(), key=lambda item: (item[1][2], item[1][3], item[1][1]), reverse=True)}
            self.assertEqual(stats, re_sorted, "Game leaderboards should be returned in reverse order of popularity")

        test_top(2)
        test_top(4)
        test_top(8)

        ######################################################################################
        # latest_games
        #
        # 'latest_games',  # The latest self.num_games
        #
        # The aim is to select the most recently played games.
        def test_latest(latest_games):
            if self.verbosity>=2: print(f"Testing ?latest_games={latest_games}")
            response = self.JSON_response('json_leaderboards', f"?latest_games={latest_games}")
            stats = board_play_stats(response)

            self.assertEqual(len(stats), latest_games, f"Expected {latest_games} and got {len(stats)}.")
            # Re-sort the stats to check they are in order expected
            re_sorted = {k: v for k, v in sorted(stats.items(), key=lambda item: item[1][1], reverse=True)}
            self.assertEqual(stats, re_sorted, "Game leaderboards should be returned in reverse order of last time played")

        test_latest(2)
        test_latest(4)
        test_latest(8)

        ######################################################################################
        # game_leagues (all and any)
        #
        # 'game_leagues_any',  # Games played in any of self.game_leagues
        # 'game_leagues_all',  # Games played in all of self.game_leagues
        #
        # The aim is to select games that are played by all or any of the cited leagues.
        #
        # We need games in different leagues, at least three leagues, and two or more games
        # in each league.
        #
        # TODO: leagues= without a game_leagues_any/all should not filter on leagues
        #       leagues= with an empty game_leagues_any/all should be same as specifyling leaguis with the option
        #       leagues= and game_leagues_any/all= specifying differnt lists should see the latter used

        # First test the leagues transporter ?leagues=a,b,c
        # Alone it should have zero impact.
        response = self.JSON_response('json_leaderboards', f"?leagues=1,2")
        stats = board_stats(response)
        #self.assertEqual(stats, stats_no_login)

        response = self.JSON_response('json_leaderboards', f"?no_defaults&leagues=1,2")
        stats = board_stats(response)
        self.assertEqual(stats, stats_no_defaults)

        game_leagues = lambda gid: Game.objects.get(pk=gid).leagues.values_list('id', flat=True)
        def test_gl_all(leagues):
            csv_leagues = ','.join([str(l) for l in leagues])

            # find the set of games in all the leagues
            # The session criteron is tricky here. Sessions have one league. Games can be in many. We don't require a session to be in the same league
            # as the game per se (which mirrros the current implementaton) If we have a list of leagues, then as long as the session is in one of those
            # leagues it constitutes a snapshot leaderboard of interest to the query (on those leagues), even if the game is not played in that league
            # which is of course just agame configuration and integrity error of sorts.
            intersection = set.intersection(*[set(Game.objects.filter(leagues=l, sessions__league__in=leagues).distinct().values_list('id', flat=True)) for l in leagues])

            if self.verbosity>=2: print(f"Testing ?game_leagues_all={csv_leagues} (expecting {len(intersection)} of {Game.objects.all().count()} games)")
            response = self.JSON_response('json_leaderboards', f"?game_leagues_all={csv_leagues}")
            stats = board_stats(response)

            self.assertEqual(set(stats.keys()), intersection)

        test_gl_all([1,3])
        test_gl_all([1,2])
        test_gl_all([2,3])

        def test_gl_any(leagues):
            csv_leagues = ','.join([str(l) for l in leagues])

            # find the set of games in any of the leagues
            # The session criteron is tricky here. Sessions have one league. Games can be in many. We don't require a session to be in the same league
            # as the game per se (which mirrros the current implementaton) If we have a list of leagues, then as long as the session is in one of those
            # leagues it constitutes a snapshot leaderboard of interest to the query (on those leagues), even if the game is not played in that league
            # which is of course just agame configuration and integrity error of sorts.
            union = set.union(*[set(Game.objects.filter(leagues=l, sessions__league__in=leagues).distinct().values_list('id', flat=True)) for l in leagues])

            if self.verbosity>=2: print(f"Testing ?game_leagues_any={csv_leagues} (expecting {len(union)} of {Game.objects.all().count()} games)")
            response = self.JSON_response('json_leaderboards', f"?game_leagues_any={csv_leagues}")
            stats = board_stats(response)

            self.assertEqual(set(stats.keys()), union)

        test_gl_any([1,3])
        test_gl_any([1,2])
        test_gl_any([2,3])

        ######################################################################################
        # game play stats (check last_play, session_count and play_count)
        #
        # session_count and play_count have two code paths, one with an ANY or ALL filter
        # and a second without.
        #
        # In both cases, perspective (as_at) will determine the count.
        #
        # We check play stats in cahoots with all three filters:
        #
        #    as_at - the perspective
        #    leagues -  the leagues
        #        leagues= is a transporter
        #        game_leagues_any/all can if empty draw from the transporter, or list leagues themselves.
        #    show_cross_league_snaps - Show snapshots that are in any leagues that players in the selected leagues are in (even if they are not selected)
        #
        # TODO: Need better tests for show_cross_league_snaps
        # TODO: Need to chekc the leagues transport and game_leangues_any/all interactions
        response = self.JSON_response('json_leaderboards', "?no_defaults")
        stats = board_play_stats(response)
        expected = {1: (12, 'Sat, 1 Jan 2022 12:00', 20, 5), # confirmed correct
                    2: (2, 'Sat, 1 Jan 2022 02:00', 4, 1), # confirmed correct
                    3: (3, 'Sat, 1 Jan 2022 03:00', 4, 1), # confirmed correct
                    4: (6, 'Sat, 1 Jan 2022 06:00', 10, 2), # confirmed correct
                    5: (5, 'Sat, 1 Jan 2022 05:00', 4, 1), # confirmed correct
                    6: (7, 'Sat, 1 Jan 2022 07:00', 4, 1), # confirmed correct
                    7: (8, 'Sat, 1 Jan 2022 08:00', 4, 1), # confirmed correct
                    8: (13, 'Sat, 1 Jan 2022 13:00', 2, 1), # confirmed correct
                    9: (14, 'Sat, 1 Jan 2022 14:00', 2, 1), # confirmed correct
                    10: (15, 'Sat, 1 Jan 2022 15:00', 2, 1)} # confirmed correct
        self.assertEqual(stats, expected, "Leaderboard play statistics (last_play, total_plays, total_sessions) not as expected.")

        # With an asat filter (so only games that were played before then and status at that time)
        response = self.JSON_response('json_leaderboards', "?no_defaults&asat=2022-01-01+06-00-00++11-00")
        stats = board_play_stats(response)
        expected = {1: (1, 'Sat, 1 Jan 2022 01:00', 4, 1),
                    2: (2, 'Sat, 1 Jan 2022 02:00', 4, 1),
                    3: (3, 'Sat, 1 Jan 2022 03:00', 4, 1),
                    4: (6, 'Sat, 1 Jan 2022 06:00', 10, 2),
                    5: (5, 'Sat, 1 Jan 2022 05:00', 4, 1)}
        self.assertEqual(stats, expected, "Leaderboard play statistics (last_play, total_plays, total_sessions) not as expected.")

        # With a leagues filter
        response = self.JSON_response('json_leaderboards', "?no_defaults&asat=2022-01-01+06-00-00++11-00&leagues=2")
        stats = board_play_stats(response)
        expected = {4: (6, 'Sat, 1 Jan 2022 06:00', 10, 2)}
        self.assertEqual(stats, expected, "Leaderboard play statistics (last_play, total_plays, total_sessions) not as expected.")

        # With a cross-leagues filter
        response = self.JSON_response('json_leaderboards', "?no_defaults&asat=2022-01-01+06-00-00++11-00&leagues=2&show_cross_league_snaps")
        stats = board_play_stats(response)
        # These are expected, but the test data could be better to exclude some earlier sessions, for lack cross league influece.
        # Check the player leagues and maybe tune to achieve that.
        expected = {1: (1, 'Sat, 1 Jan 2022 01:00', 4, 1),
                    2: (2, 'Sat, 1 Jan 2022 02:00', 4, 1),
                    3: (3, 'Sat, 1 Jan 2022 03:00', 4, 1),
                    4: (6, 'Sat, 1 Jan 2022 06:00', 10, 2),
                    5: (5, 'Sat, 1 Jan 2022 05:00', 4, 1)}
        self.assertEqual(stats, expected, "Leaderboard play statistics (last_play, total_plays, total_sessions) not as expected.")

        ######################################################################################
        # game_leagues (all and any)
        #
        # 'game_leagues_any',  # Games played in any of self.game_leagues
        # 'game_leagues_all',  # Games played in all of self.game_leagues
        response = self.JSON_response('json_leaderboards', "?no_defaults&game_leagues_any=2,3")
        stats = game_league_stats(response)
        expected = {4: [1, 2, 3],
                    1: [1, 2],
                    2: [1, 2],
                    3: [1, 2],
                    5: [1, 3],
                    7: [1, 3]}
        self.assertEqual(stats, expected, "Leaderboard games_leages_any failed")

        # TODO: Check this as with players_all. Players_all needed an ArrayAgg to work the _all
        response = self.JSON_response('json_leaderboards', "?no_defaults&game_leagues_all=2,3")
        stats = game_league_stats(response)
        expected = {4: [1, 2, 3]}
        self.assertEqual(stats, expected, "Leaderboard games_leages_all failed")

        ######################################################################################
        # game_players (all and any)
        #
        # 'game_players_any',  # Games played by any of self.game_players
        # 'game_players_all',  # Games played by all of self.game_players
        #
        # We need a good mix of games and players to test this.
        #
        # The aim is to select games that have been played by all or any of the cited players.
        response = self.JSON_response('json_leaderboards', "?no_defaults&game_players_any=5,7")
        stats = game_player_stats(response)
        expected = {1: [1, 2, 3, 4, 5, 6],
                    4: [1, 2, 3, 4, 5, 6],
                    8: [1, 7],
                    9: [2, 5]
                   }
        self.assertEqual(stats, expected, "Leaderboard games_players_any failed")

        response = self.JSON_response('json_leaderboards', "?no_defaults&game_players_all=2,5")
        stats = game_player_stats(response)
        expected = {1: [1, 2, 3, 4, 5, 6],
                    4: [1, 2, 3, 4, 5, 6],
                    9: [2, 5]}
        self.assertEqual(stats, expected, "Leaderboard games_players_all failed")

        ######################################################################################
        # changed (after and before)
        #
        # 'changed_after',     # Games played since self.changed_after
        # 'changed_before',    # Games played on or before self.changed_before
        response = self.JSON_response('json_leaderboards', "?no_defaults&game_players_all=2,5")

        ######################################################################################
        # game (ex and in)
        #
        # Ex should exclude all other selectors and end up only with the selected games.
        #    Test with top_games and latest_games and other options.
        # In should include all other selectors, so add these games to the mix.

    # def test_player_selectors(self):
    #     '''
    #     '''
    #     pass
    #
    # def test_perspectives(self):
    #     '''
    #     '''
    #     pass
    #
    # def test_evolution(self):
    #     '''
    #     '''
    #     pass
