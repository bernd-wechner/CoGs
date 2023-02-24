'''
Game Record Import BGstats support

The BGstats app can export game play records in a JSON format.

We implement support for reading those here.

WIP

'''
import json
import zipfile

#from Leaderboards.models import Game, Player, Location, Session

from ..hunters import ContextClues, GameClues, PlayerClues, LocationClues, hunt_game, hunt_player, hunt_location


class SessionPreCache:
    '''
    Just a pro forma for capturing a session with foreign IDs
    '''
    date_time = None
    game = None
    location = None
    players = None


def import_sessions(filename):
    if zipfile.is_zipfile(filename):
        with zipfile.ZipFile(filename, 'r') as bszip:
            contents = bszip.namelist()
            assert len(contents) == 1, "Only a single JSON file zipped is supported."
            assert contents[0].endswith('.json'), "Only .json files are supported."
            with bszip.open(contents[0]) as bgstats:
                data = json.loads(bgstats.read().decode())
    else:
        assert filename.endswith('.json'), "Only .json files are supported."
        with open(filename, 'r') as bgstats:
            data = json.load(bgstats)

    ####################################################
    # PHASE 1 Contextualise the mappings
    bgstats_user = data.get("userInfo", None)

    context = ContextClues()
    if bgstats_user:
        context.name = bgstats_user.get("name", None)
        context.email = bgstats_user.get("cloudEmail", None)
        context.bggID = bgstats_user.get("bggUsername", None)
        # This could defer collection of the above three to when a
        # player record of this ID is found.
        user_bgsID = bgstats_user.get("meRefId", None)

    ####################################################
    # PHASE 2 Scan plays
    #
    # We want to build a set of referenced Games, Players and a Locations.
    # Only those do we need to build maps for.
    # As we're scanning though we may as well, build a list of sessions
    # to add.

    bgstat_plays = data.get("plays", None)

    sessions = []
    refGames = set()
    refPlayers = set()
    refLocations = set()

    for play in bgstat_plays:
        valid = True
        session = SessionPreCache()
        session.date_time = play.get('playDate', None)
        session.game = play.get('gameRefId', None)
        session.location = play.get('locationRefId', None)

        if session.game:
            refGames.add(session.game)
        else:
            valid = False

        if session.location:
            refLocations.add(session.location)

        # Stroe by bgsID, tuples of rank, score
        session.players = {}
        for player in play.get('playerScores', []):
            player_id = player.get('playerRefId', None)
            rank = player.get('rank', None)
            score = player.get('score', None)

            if player_id:
                session.players[player_id] = (rank, score)
                refPlayers.add(player_id)
            else:
                valid = False

        if not session.players:
            valid = False

        if valid:
            sessions.append(session)

    ####################################################
    # PHASE 3 Build mappings

    # Collect the games
    # index them by bgsID (lordy only knows why BGS doesn't export them that way)
    bgsGames = {g['id']: g for g in data.get("games", []) if 'id' in g}

    # BGstats ID to a (sortkey, clues, candidates) tuple
    # key is their ID, value is our ID or a list of candidates to present to the user (along with the New Game option)
    map_games = {}

    if bgsGames and refGames:
        for gid in refGames:
            game = bgsGames.get(gid, None)

            if game:
                game_clues = GameClues()

                bgsID = game.get('id', None)

                game_clues.BGGid = game.get("bggId", None)
                game_clues.name = game.get("bggName", game.get("name", None))

                sortkey, candidates = hunt_game(game_clues, include_best_quality=True)

                map_games[bgsID] = (sortkey, game_clues, candidates)
            else:
                print(f"Play referenced game {gid} which is not found in the list of exported games.")

    # Collect the players
    # index them by bgsID (lordy only knows why BGS doesn't export them that way)
    bgsPlayers = {p['id']: p for p in data.get("players", []) if 'id' in p}

    # The context may have referenced a player by id. If so, update it now with details from that player
    if user_bgsID in bgsPlayers:
        player = bgsPlayers[user_bgsID]
        if not context.name:
            context.name = player.get('name', None)
        if not context.email:
            context.email = player.get('email', None)  # TODO confirm the name of this field (Russell can give me an email and save and export)
        if not context.bggID:
            context.bggID = player.get('bggUsername', None)

    # BGStats Player ID to a (sortkey, clues, candidates) tuple
    # key is their ID, value is our ID or a list of candidates to present to the user (along with the New Player option)
    map_players = {}

    if bgsPlayers and refPlayers:
        for pid in refPlayers:
            player = bgsPlayers.get(pid, None)

            if player:
                player_clues = PlayerClues()

                bgsID = player.get('id', None)

                player_clues.name = player.get('name', None)
                player_clues.email = player.get('email', None)  # TODO confirm the name of this field (Russell can give me an email and save and export)
                player_clues.BGGid = player.get('bggUsername', None)

                # This is a JSON dict and I have seen these keys:
                # isNpc
                # PlayerNotes
                metadata = player.get('metaData', None)

                if metadata:
                    md = json.loads(metadata)
                    player_clues.notes = md.get("PlayerNotes", None)

                sortkey, candidates = hunt_player(player_clues, include_best_quality=True)

                map_players[bgsID] = (sortkey, player_clues, candidates)
            else:
                print(f"Play referenced player {pid} which is not found in the list of exported players.")

    # Collect the locations
    # index them by bgsID (lordy only knows why BGS doesn't export them that way)
    bgsLocations = {l['id']: l for l in data.get("locations", None) if 'id' in l}

    # BGStats Location ID to a (sortkey, clues, candidates) tuple
    # key is their ID, value is our ID or a list of candidates to present to the user (along with the New Location option)
    map_locations = {}

    if bgsLocations and refLocations:
        for lid in refLocations:
            location = bgsLocations.get(lid, None)

            if location:
                location_clues = LocationClues()

                bgsID = location.get('id', None)

                location_clues.name = location.get('name', None)

                metadata = location.get('metaData', None)
                if metadata:
                    md = json.loads(metadata)
                    location_clues.notes = md.get("LocationNotes", None)  # TODO: Check premise here, not sen in wild, inferred from Player observations

            sortkey, candidates = hunt_location(location_clues, include_best_quality=True)

            map_locations[bgsID] = (sortkey, location_clues, candidates)

    ####################################################
    # Order the map dicts for template presentation (using the sortkey)
    sorted_game_map = {key: value for
                        key, value in sorted(map_games.items(),
                            key=lambda item:
                                (item[1][0],
                                 len(item[1][2]) if isinstance(item[1][2], (list, tuple)) else 0
                                )
                            )
                        }

    sorted_player_map = {key: value for
                        key, value in sorted(map_players.items(),
                            key=lambda item:
                                (item[1][0],
                                 len(item[1][2]) if isinstance(item[1][2], (list, tuple)) else 0
                                )
                            )
                        }

    sorted_location_map = {key: value for
                        key, value in sorted(map_locations.items(),
                            key=lambda item:
                                (item[1][0],
                                 len(item[1][2]) if isinstance(item[1][2], (list, tuple)) else 0
                                )
                            )
                        }

    ####################################################
    # Return a template context

    context = {
        "map_games": sorted_game_map,
        "map_players": sorted_player_map,
        "map_locations": sorted_location_map
        }

    return context
