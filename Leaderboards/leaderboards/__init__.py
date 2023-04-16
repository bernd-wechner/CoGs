# Python imports
import json

# Django imports
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

# Local imports
from .enums import LB_STRUCTURE, LB_PLAYER_LIST_STYLE
from .util import mutable, immutable
from .style import guess_player_list_style

from Site.logutils import log


def augment_with_deltas(master, baseline=None, structure=LB_STRUCTURE.game_wrapped_session_wrapped_player_list, style=None):
    '''
    Given a master leaderboard and a baseline to compare it against, will
    augment the master with delta measures (adding a previous rank
    and a previous rating element to each player tuple)

    This is very flexible with structures and formats. Accepts JSON and Python and
    each of the leaderboard structures and returns the same. General purpose augmenter
    of playlists with a previous rank item based on the baseline.

    By default, only master is needed. if it is a game_wrapped_session_wrapped_player_list
    with snapshots in it no baseline is needed and all the snapshots will be delta augmented.

    Only two styles are supported, rich and data. They are the only two that currently include
    a unique player ID which cna be used for tha ugmentation.

    :param master:      a leaderboard
    :param baseline:    a leaderboard to compare with. None is valid only for a game_wrapped_session_wrapped_player_list with snaps
    :param structure:   an LB_STRUCTURE that master and baseline are to interpreted with
    :param style:       an LB_PLAYER_LIST_STYLE, which will be guessed at if need be, so we know where to get the rank and rating from to augment with.
    '''

    if isinstance(master, str):
        _master = json.loads(master)
    else:
        _master = mutable(master)

    if isinstance(baseline, str):
        _baseline = json.loads(baseline)
    else:
        _baseline = baseline

    igd = LB_STRUCTURE.game_data_element.value
    isd = LB_STRUCTURE.session_data_element.value
    snaps = False  # by default (only true on game_wrapped leaderboards that say so

    if structure == LB_STRUCTURE.session_wrapped_player_list:
        lb_master = _master[isd]
        lb_baseline = _baseline[isd]
    elif structure == LB_STRUCTURE.game_wrapped_player_list:
        snaps = _master[igd - 3]
        lb_master = _master[igd]

        if not snaps and _baseline:
            lb_baseline = _baseline[igd]
        else:
            lb_baseline = None
    elif structure == LB_STRUCTURE.game_wrapped_session_wrapped_player_list:
        snaps = _master[igd - 3]

        if snaps:
            # A list of session_wrapped leaderboards.
            # We remove the session wrappers to create a list of player lists
            # for uniform handling below.
            lb_master = [session_wrapper[isd] for session_wrapper in _master[igd]]
        else:
            # A single session wrapped leaderboard (extract the player list, remove the sessino wrapper)
            lb_master = _master[igd][isd]

            if _baseline:
                lb_baseline = _baseline[igd][isd]
            else:
                lb_baseline = None
    elif structure == LB_STRUCTURE.player_list:
        lb_master = _master
        lb_baseline = _baseline

    # Build a list of (master, baseline) tuples to process
    if snaps:
        pairs = [(lb_master[i], lb_master[i + 1]) for i in range(len(lb_master) - 1)]
    elif lb_baseline:
        pairs = [(lb_master, lb_baseline)]
    else:
        pairs = []

    # We now augment _master in situ
    for lb in pairs:
        # Grab the two player lists
        pl_master = lb[0]
        pl_baseline = lb[1]

        style = guess_player_list_style(pl_baseline)

        previous_rank = {}
        previous_rating = {}
        for r, p in enumerate(pl_baseline):
            # Most commonly used for rich player lists (i.e for rendering informative player lists (leaderboards), which the rich style targets)
            if style == LB_PLAYER_LIST_STYLE.rich:
                rank = p[0]
                pk = p[1]
                rating = p[6]
            elif style == LB_PLAYER_LIST_STYLE.data:
                rank = r
                pk = p[0]
                rating = p[1]
            else:
                raise ValueError("Attempt to augment and unsupport Player List style")

            previous_rank[pk] = rank
            previous_rating[pk] = rating

        for r, p in enumerate(pl_master):
            if style == LB_PLAYER_LIST_STYLE.rich:
                pk = p[1]
            elif style == LB_PLAYER_LIST_STYLE.data:
                pk = p[0]

            pran = previous_rank.get(pk, None)
            prat = previous_rating.get(pk, None)
            pl_master[r] = tuple(p) + (pran, prat)

    if isinstance(master, str):
        result = json.dumps(_master, cls=DjangoJSONEncoder)
        return result
    else:
        # Back to tuple with frozen result
        return immutable(_master)


def leaderboard_changed(player_list1, player_list2):
    '''
    Return True if two player lists in style LB_PLAYER_LIST_STYLE.data are not functionly the same.

    :param player_list1:
    :param player_list2:
    '''
    if len(player_list1) == len(player_list2):
        for player_tuple1, player_tuple2 in zip(player_list1, player_list2):
            # We compare only the first 4 elements which define the player and rating at this position
            # If they are the same the leaderboard is functionall unchanged (the remaining items are
            # useful metadata but not relevant to ratings or ranking)
            for element1, element2 in zip(player_tuple1[0:4], player_tuple2[0:4]):
                if element1 != element2:
                    return True
        return False
    else:
        return True

