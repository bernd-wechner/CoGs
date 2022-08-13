# import os
# import django
import re, json

from copy import deepcopy
from datetime import datetime
from dateutil import parser

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django_generic_view_extensions.datetime import make_aware

from Leaderboards.models import Session, Game, Player, Team, Rank, Performance, League, Location, Team, Tourney, MISSING_VALUE as MV
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
    def new_session(self, scoring):
        game = Game.objects.get(name="INDIVIDUAL_HIGH_SCORE_WINS")
        player = [p for p in Player.objects.all()]  # @UndefinedVariable

        session = Session.objects.create(game=game, team_play=False)  # @UndefinedVariable

        Rank.objects.create(session=session, rank=2, score=10, player=player[0])  # @UndefinedVariable
        Rank.objects.create(session=session, rank=3, score=5, player=player[1])  # @UndefinedVariable
        Rank.objects.create(session=session, rank=1, score=15, player=player[2])  # @UndefinedVariable
        Rank.objects.create(session=session, rank=4, score=2, player=player[3])  # @UndefinedVariable

        Performance.objects.create(session=session, player=player[0])  # @UndefinedVariable
        Performance.objects.create(session=session, player=player[1])  # @UndefinedVariable
        Performance.objects.create(session=session, player=player[2])  # @UndefinedVariable
        Performance.objects.create(session=session, player=player[3])  # @UndefinedVariable

    @classmethod
    def setUpTestData(cls):
        # Create some basic game configurations
        game0 = Game.objects.create(name="NO_SCORES", individual_play=True, team_play=False, scoring=Game.ScoringOptions.NO_SCORES.value)

        gameIH = Game.objects.create(name="INDIVIDUAL_HIGH_SCORE_WINS", individual_play=True, team_play=False, scoring=Game.ScoringOptions.INDIVIDUAL_HIGH_SCORE_WINS.value)
        gameIL = Game.objects.create(name="INDIVIDUAL_LOW_SCORE_WINS", individual_play=True, team_play=False, scoring=Game.ScoringOptions.INDIVIDUAL_LOW_SCORE_WINS.value)

        gameTH = Game.objects.create(name="TEAM_HIGH_SCORE_WINS", individual_play=False, team_play=True, scoring=Game.ScoringOptions.TEAM_HIGH_SCORE_WINS.value)
        gameTL = Game.objects.create(name="TEAM_LOW_SCORE_WINS", individual_play=False, team_play=True, scoring=Game.ScoringOptions.TEAM_LOW_SCORE_WINS.value)

        gameTIH = Game.objects.create(name="TEAM_AND_INDIVIDUAL_HIGH_SCORE_WINS", individual_play=True, team_play=True, scoring=Game.ScoringOptions.TEAM_AND_INDIVIDUAL_HIGH_SCORE_WINS.value)
        gameTIL = Game.objects.create(name="TEAM_AND_INDIVIDUAL_LOW_SCORE_WINS", individual_play=True, team_play=True, scoring=Game.ScoringOptions.TEAM_AND_INDIVIDUAL_LOW_SCORE_WINS.value)

        all_games = [game0, gameIH, gameIL, gameTH, gameTL, gameTIH, gameTIL]

        # Create a couple of tourneys
        tourney1 = Tourney.objects.create(name='tourney1')
        tourney1.games.set([game0, gameIH, gameIL])

        tourney2 = Tourney.objects.create(name='tourney2')
        tourney2.games.set([gameTH, gameTL, gameTIH, gameTIL])
        # TODO: Add TourneyRules for each game in each tourney.
        # Default Rules are created and could be configured.

        # Create some Players
        player1 = Player.objects.create(name_nickname="Player1", name_personal="Player", name_family="One", email_address="player1@leaderboard.space")  # @UndefinedVariable
        player2 = Player.objects.create(name_nickname="Player2", name_personal="Player", name_family="Two", email_address="player2@leaderboard.space")  # @UndefinedVariable
        player3 = Player.objects.create(name_nickname="Player3", name_personal="Player", name_family="Three", email_address="player3@leaderboard.space")  # @UndefinedVariable
        player4 = Player.objects.create(name_nickname="Player4", name_personal="Player", name_family="Four", email_address="player4@leaderboard.space")  # @UndefinedVariable
        player5 = Player.objects.create(name_nickname="Player5", name_personal="Player", name_family="Five", email_address="player5@leaderboard.space")  # @UndefinedVariable
        player6 = Player.objects.create(name_nickname="Player6", name_personal="Player", name_family="Six", email_address="player6@leaderboard.space")  # @UndefinedVariable
        player7 = Player.objects.create(name_nickname="Player7", name_personal="Player", name_family="Seven", email_address="player7@leaderboard.space")  # @UndefinedVariable
        player8 = Player.objects.create(name_nickname="Player8", name_personal="Player", name_family="Eight", email_address="player8@leaderboard.space")  # @UndefinedVariable

        pgroup1 = [player1, player2, player3, player4, player5, player6]
        pgroup2 = [player3, player4, player5, player6, player7, player8]

        # Create a couple of teams
        team1 = Team.objects.create(name='team1')
        team1.players.set([player1, player2])

        team2 = Team.objects.create(name='team2')
        team2.players.set([player3, player4])

        # Create a couple of locations
        location1 = Location.objects.create(name="Location1")
        location2 = Location.objects.create(name="Location2")

        # Create a couple of leagues
        league1 = League.objects.create(name='League1', manager=player1)
        league1.locations.set([location1, location2])
        league1.players.set(pgroup1)
        league1.games.set(all_games)

        league1 = League.objects.create(name='League2', manager=player8)
        league1.locations.set([location1, location2])
        league1.players.set(pgroup2)
        league1.games.set(all_games)

        # Create a user
        User = get_user_model()
        user = User.objects.create_user('admin', 'noone@gmail.com', 'password')

        cls.maxDiff = 2400  # To see diffs on some of the json dicts used in tests that are longish

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
                    'initial-date_time': '2022-07-02 03:59:00',
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
        change_id = matches.group(3)

        session = Session.objects.get(pk=session_id)  # @UndefinedVariable

        self.assertEqual(change, "create" if operation == "add" else "update")

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
        Testing:
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
                     "players": players,
                     "rankings": rankings,
                     "rscores": rscores,
                     "pscores": pscores }

        def test(form, scoring, team_play, rankings, rscores, pscores, permit_missing_scores=False):
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
            errors = []

            def add_error(self, field, message):
                self.errors.append((field, message))

            def reset(self):
                self.errors = []

        form = DummyForm()

        #########################################################################################################
        # NO SCORES
        diff = test(form, "NO_SCORES", False, [2, 1], [MV, MV], [MV, MV])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = test(form, "NO_SCORES", False, [2, 1], [10, 20], [100, 200])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = test(form, "NO_SCORES", False, [MV, MV], [10, 20], [100, 200])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = test(form, "NO_SCORES", False, [-5, 2], [10, 20], [100, 200])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = test(form, "NO_SCORES", False, [1, 2], [-10, 20], [100, 200])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [])
        form.reset()

        #########################################################################################################
        # INDIVIDUAL_HIGH_SCORE_WINS
        diff = test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [2, 1], [MV, MV], [MV, MV])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [(None, 'This is a scoring game. Please enter scores')])
        form.reset()

        diff = test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [2, 1], [MV, MV], [MV, MV], True)
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [2, 1], [10, 20], [MV, MV])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [2, 1], [20, 10], [MV, MV])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [(None, 'Submitted rankings and scores do not agree.')])
        form.reset()

        diff = test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [MV, MV], [20, 10], [MV, MV])
        self.assertEqual(diff, {'rankings': ([MV, MV], [1, 2])})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [MV, MV, MV, MV], [20, 10, 5, 10], [MV, MV, MV, MV])
        self.assertEqual(diff, {'rankings': ([MV, MV, MV, MV], [1, 2, 4, 2])})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = test(form, "INDIVIDUAL_HIGH_SCORE_WINS", True, [MV, MV, MV, MV], [20, 10, 5, 10], [MV, MV, MV, MV])
        self.assertEqual(diff, {})
        self.assertEqual(form.errors, [(None, 'This is a game that does not score teams and so team play sessions can not be recorded. Likely a form or game configuration error.')])
        form.reset()

        diff = test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10], [MV, MV, MV, MV, MV, MV])
        self.assertEqual(diff, {'rankings': ([MV, MV, MV, MV, MV, MV], [1, 2, 5, 2, 6, 2])})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [MV, MV, MV, MV, MV, MV], [MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])
        self.assertEqual(diff, {'rankings': ([MV, MV, MV, MV, MV, MV], [1, 2, 5, 2, 6, 2]), 'rscores': ([MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [1, 2, MV, MV, 6, 2], [MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])
        self.assertEqual(diff, {'rankings': ([1, 2, MV, MV, 6, 2], [1, 2, 5, 2, 6, 2]), 'rscores': ([MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = test(form, "INDIVIDUAL_HIGH_SCORE_WINS", False, [1, 2, MV, MV, 3, 2], [MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])
        self.assertEqual(diff, {'rankings': ([1, 2, MV, MV, 3, 2], [1, 2, 5, 2, 3, 2]), 'rscores': ([MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])})
        self.assertEqual(form.errors, [(None, 'Submitted rankings and scores do not agree.')])
        form.reset()

        #########################################################################################################
        # INDIVIDUAL_LOW_SCORE_WINS
        diff = test(form, "INDIVIDUAL_LOW_SCORE_WINS", False, [MV, MV, MV, MV, MV, MV], [MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])
        self.assertEqual(diff, {'rankings': ([MV, MV, MV, MV, MV, MV], [6, 3, 2, 3, 1, 3]), 'rscores': ([MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = test(form, "INDIVIDUAL_LOW_SCORE_WINS", False, [MV, MV, 2, 3, MV, MV], [MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])
        self.assertEqual(diff, {'rankings': ([MV, MV, 2, 3, MV, MV], [6, 3, 2, 3, 1, 3]), 'rscores': ([MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])})
        self.assertEqual(form.errors, [])
        form.reset()

        diff = test(form, "INDIVIDUAL_LOW_SCORE_WINS", False, [MV, MV, 3, 3, MV, MV], [MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])
        self.assertEqual(diff, {'rankings': ([MV, MV, 3, 3, MV, MV], [6, 3, 3, 3, 1, 3]), 'rscores': ([MV, MV, MV, MV, MV, MV], [20, 10, 5, 10, 2, 10])})
        self.assertEqual(form.errors, [(None, 'Submitted rankings and scores do not agree.')])
        form.reset()

        #########################################################################################################
        # TEAM_HIGH_SCORE_WINS

        # TODO: Test all the Team scenarios

