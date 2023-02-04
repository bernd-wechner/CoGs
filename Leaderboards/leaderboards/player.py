from .enums import LB_STRUCTURE, LB_PLAYER_LIST_STYLE
from .style import guess_player_list_style


def extract_player_list(leaderboard, structure=LB_STRUCTURE.game_wrapped_session_wrapped_player_list, style=None, snap=0):
    '''
    Extracts the player list from a structured leaderboard. The player list being a list of ordered tuples that describe
    a player on a leaderboard.

    If there are many leaderboards in the structure the first one is used or the on that is identfied by the snap argument
    This is the case with game wrapped leaderboards where the data element is a list of player lists rather than a single
    player list.

    :param leaderboard: A leaderboard with the confessed structure with style LB_PLAYER_LIST_STYLE.data
    :param structure: An LB_STRUCTURE that describes the structure of leaderboard
    :param style: An LB_PLAYER_LIST_STYLE that describes the player style (is guessed form tuple if not confessed)
    :param snap: A snapshot number if it's a game wrapped board with snapshots (snaps)
    '''
    igd = LB_STRUCTURE.game_data_element.value
    isd = LB_STRUCTURE.session_data_element.value

    if structure == LB_STRUCTURE.session_wrapped_player_list:
        player_list = leaderboard[isd]
    elif structure == LB_STRUCTURE.game_wrapped_player_list:
        snaps = leaderboard[igd - 3]
        player_lists = leaderboard[igd]

        if snaps:
            player_list = player_lists[igd]
        else:
            player_list = player_lists
    elif structure == LB_STRUCTURE.game_wrapped_session_wrapped_player_list:
        snaps = leaderboard[igd - 3]
        sessions = leaderboard[igd]

        if snaps:
            # A list of session_wrapped leaderboards
            player_list = sessions[snap][isd]
        else:
            # A single session wrapped leaderboard (extract the player list)
            player_list = sessions[isd]
    elif structure == LB_STRUCTURE.player_list:
        player_list = leaderboard
    else:
        raise ValueError(f"Unsupport leaderboard structure: {structure}")

    return player_list


def player_ratings(leaderboard, structure=LB_STRUCTURE.game_wrapped_session_wrapped_player_list, style=None, snap=0):
    '''
    Returns a dict keyed on player pk, with TrueSkill rating as the value, extracted from the provided leaderboards.

    If there are many leaderboards in the structure the first one is used. This is the case with
    game wrapped leaderboards where the data element is a list of player lists rather than a single
    player list.

    :param leaderboard: A leaderboard with the confessed structure with style LB_PLAYER_LIST_STYLE.data
    :param structure: An LB_STRUCTURE that describes the structure of leaderboard
    :param style: An LB_PLAYER_LIST_STYLE that describes the player style (is guessed form tuple if not confessed)
    :param snap: A snapshot number if it's a game wrapped board with snapshots (snaps)
    '''

    player_list = extract_player_list(leaderboard, structure, style, snap)

    if style is None:
        style = guess_player_list_style(player_list)

    ratings = {}
    for tup in player_list:
        # The player PK is the first element in the tuple except for rich boards, where it's the second
        key = tup[1] if style == LB_PLAYER_LIST_STYLE.rich else tup[0]

        # The player rating is the second element in the tuple except for rich boards, where it's the sixth
        rating = tup[6] if style == LB_PLAYER_LIST_STYLE.rich else tup[1]
        ratings[key] = rating

    return ratings


def player_rankings(leaderboard, structure=LB_STRUCTURE.game_wrapped_session_wrapped_player_list, style=None, snap=0):
    '''
    Returns a dict keyed on player pk, with leaderboard position as the value

    If there are many leaderboards in the structure the first one is used. This is the case with
    game wrapped leaderboards where the data element is a list of player lists rather than a single
    player list.

    :param leaderboard: A leaderboard with the confessed structure with style LB_PLAYER_LIST_STYLE.data
    :param structure: An LB_STRUCTURE that describes the structure of leaderboard
    :param style: An LB_PLAYER_LIST_STYLE that describes the player style (is guessed form tuple if not confessed)
    :param snap: A snapshot number if it's a game wrapped board with snapshots (snaps)
    '''
    player_list = extract_player_list(leaderboard, structure, style, snap)

    if style is None:
        style = guess_player_list_style(player_list)

    positions = {}
    for pos, tup in enumerate(player_list):
        # Always use the first entry in the player tuple as the key except in the rich style (which has it as second spot)
        key = tup[1] if style == LB_PLAYER_LIST_STYLE.rich else tup[0]
        positions[key] = pos

    return positions
