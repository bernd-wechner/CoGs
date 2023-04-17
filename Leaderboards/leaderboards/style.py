from .enums import LB_STRUCTURE, LB_PLAYER_LIST_STYLE
from .util import mutable, immutable

# models imports from this module. To avoid a circular import error we need to import models into its own namespace.
# which means accessing a model is then models.Model
from .. import models


def styled_player_tuple(player_list_tuple, rank=None, style=LB_PLAYER_LIST_STYLE.rich, names="nick"):
    '''
    Takes a tuple styled after LB_PLAYER_LIST_STYLE.data and returns a styled tuple as requested.

    styled_player_tuple() below is more convenient as it takes an ordered player list from
    which rank is derived. Only the rich style includes the rank.

    :param player_list_tuple: A tuple in LB_PLAYER_LIST_STYLE.data
    :param rank:  Rank on the leaderboard 1, 2, 3, 4 etc
    :param style: A LB_PLAYER_LIST_STYLE to return
    :param names: A style for rendering names
    '''
    (player_pk, trueskill_eta, trueskill_mu, trueskill_sigma, plays, victories, last_play) = player_list_tuple

    player = models.Player.objects.get(pk=player_pk)

    try:
        player = models.Player.objects.get(pk=player_pk)
        player_name = player.name(names)
        player_leagues = player.leagues.all()
    except models.Player.DoesNotExist:
        player = None  # TODO: what to do?
        player_name = "<unknown>"
        player_leagues = []

    if style == LB_PLAYER_LIST_STYLE.none:
        lb_entry = player_name
    elif style == LB_PLAYER_LIST_STYLE.data:
        lb_entry = player_list_tuple
    elif style == LB_PLAYER_LIST_STYLE.rating:
        lb_entry = (player_name, trueskill_eta)
    elif style == LB_PLAYER_LIST_STYLE.ratings:
        lb_entry = (player_name, trueskill_eta, trueskill_mu, trueskill_sigma)
    elif style == LB_PLAYER_LIST_STYLE.simple:
        lb_entry = (player_name, trueskill_eta, trueskill_mu, trueskill_sigma, plays, victories)
    elif style == LB_PLAYER_LIST_STYLE.rich:
        # There's a slim chance that "player" does not exist (notably when 'data' is provided
        # So access player properties cautiously with fallback.
        name_variants = (player.name('nick') if player else '',
                         player.name('full') if player else '',
                         player.name('complete') if player else '')

        trueskill_rating = (trueskill_eta,
                            trueskill_mu,
                            trueskill_sigma)

        play_stats = (plays,
                      victories,
                      last_play)

        lb_entry = (rank,
                    player_pk,
                    player.BGGname if player else '',
                    *name_variants, # Unpacked name variants
                    *trueskill_rating, # Unpacked trueskill rating
                    *play_stats, # Unpacked play stats
                    [l.pk for l in player_leagues])
    else:
        raise ValueError(f"Programming error in Game.leaderboard(): Illegal style submitted: {style}")

    return immutable(lb_entry)


def styled_player_list(player_list, style=LB_PLAYER_LIST_STYLE.rich, names="nick"):
    '''
    Takes a list of tuples styled after LB_PLAYER_LIST_STYLE.data and returns a list of styled tuples as requested.

    :param player_list_tuple: A tuple in LB_PLAYER_LIST_STYLE.data
    :param rank:  Rank on the leaderboard 1, 2, 3, 4 etc
    :param style: A LB_PLAYER_LIST_STYLE to return
    :param names: A style for rendering names
    '''
    styled_list = []
    for i, player_tuple in enumerate(player_list):
        styled_list.append(styled_player_tuple(player_tuple, rank=i + 1, style=style, names=names))

    return immutable(styled_list)


def restyle_leaderboard(leaderboards, structure=LB_STRUCTURE.game_wrapped_session_wrapped_player_list, style=LB_PLAYER_LIST_STYLE.rich, names="nick"):
    '''
    Restyles a leaderboard of a given structure, assuming the player_lists are in LB_PLAYER_LIST_STYLE.data

    :param leaderboards: A leaderboard with structure as specified and in LB_PLAYER_LIST_STYLE.data
    :param structure: A LB_STRUCTURE, that specifies the structure of leaderboards provided (and returned)
    :param style: A LB_PLAYER_LIST_STYLE to restyle to
    '''
    igd = LB_STRUCTURE.game_data_element.value
    isd = LB_STRUCTURE.session_data_element.value
    isp = LB_STRUCTURE.session_players_element.value # in style rich, a PK keyed dict of name variants else a list of PKs

    # Use a local mutable copy of the leaderboards provided
    _leaderboards = mutable(leaderboards)

    snaps = False  # by default (only true on game_wrapped leaderboards that say so

    # STEP 1:
    # Build a list of player_lists (if only of one item) and
    # note whether its a list (snaps is True)
    if structure == LB_STRUCTURE.session_wrapped_player_list:
        player_lists = [_leaderboards[isd]]
    elif structure == LB_STRUCTURE.game_wrapped_player_list:
        snaps = _leaderboards[igd - 3]
        if snaps:
            player_lists = _leaderboards[igd]
        else:
            player_lists = [_leaderboards[igd]]
    elif structure == LB_STRUCTURE.game_wrapped_session_wrapped_player_list:
        snaps = _leaderboards[igd - 3]

        if snaps:
            player_lists = [session_wrapper[isd] for session_wrapper in _leaderboards[igd]]
        else:
            player_lists = [_leaderboards[igd][isd]]
    elif structure == LB_STRUCTURE.player_list:
        player_lists = [_leaderboards]

    # STEP 2:
    # Restyle the player lists to the target style
    for i, pl in enumerate(player_lists):
        player_lists[i] = styled_player_list(pl, style=style, names=names)

    # STEP 3:
    # Now insert the restyled player lits back into the structured lederboards
    if structure == LB_STRUCTURE.session_wrapped_player_list:
        _leaderboards[isd] = player_lists[0]
    elif structure == LB_STRUCTURE.game_wrapped_player_list:
        if snaps:
            _leaderboards[igd] = player_lists
        else:
            _leaderboards[igd] = player_lists[0]
    elif structure == LB_STRUCTURE.game_wrapped_session_wrapped_player_list:
        if snaps:
            for i, pl in enumerate(player_lists):
                _leaderboards[igd][i][isd] = pl
        else:
            _leaderboards[igd][isd] = player_lists[0]
    elif structure == LB_STRUCTURE.player_list:
        _leaderboards = player_lists[0]

    # STEP 4:
    # If the player list style is rich we add player name variables to the list of session players
    # So that a client can use this information to replace tempated player names with the dynamically
    # selected name,
    if style == LB_PLAYER_LIST_STYLE.rich:
        if structure == LB_STRUCTURE.session_wrapped_player_list:
            # In the rich style styled_player_list() above included the name variants in the player list
            # Those are for all the name sin the leaderboard. We also want to include name vairants for the
            # session players. They can be found in the player list, but not conveniently and may not with
            # certainty appear there if the player list has some odd filter applied. So we include the three
            # name variants in element isp (LB_STRUCTURE.session_players_element) if the session header.
            sw = _leaderboards
            player_pks =  sw[isp]
            try:
                sw[isp] = {}
                for pk in player_pks:
                    _leaderboards[isp][pk] = models.Player.objects.get(pk=pk).name_variants
            except Exception as E:
                sw[isp] = player_pks

        elif structure == LB_STRUCTURE.game_wrapped_session_wrapped_player_list:
            snaps = _leaderboards[igd - 3]

            if not snaps:
                session_wrappers = [ _leaderboards[igd] ]
            else:
                session_wrappers = _leaderboards[igd]

            # For each session wrapper, as above for the session_wrapped_player_list
            for sw in session_wrappers:
                player_pks =  sw[isp]
                try:
                    sw[isp] = {}
                    for pk in player_pks:
                        sw[isp][pk] = models.Player.objects.get(pk=pk).name_variants
                except Exception as E:
                    sw[isp] = player_pks

    # Freeze the leaderboards and return
    return immutable(_leaderboards)


def guess_player_list_style(player_list):
    '''
    Based on how Game.leaderboard implements the LB_PLAYER_LIST_STYLEs.

    TODO: This should really be more robust, as in not based on what is implemented in Games.leaderboard.
    Perhaps the leaderboard structure can contain information about its style.l
    Perhaps one day the whole Leaderboard creation, structuring and presenting is a class of its own.

    :param player_list:
    '''
    # Just take the first entry in the player list as a sample
    sample = player_list[0]
    if not isinstance(sample, (list, tuple)):
        return  LB_PLAYER_LIST_STYLE.none
    elif len(sample) == 7:
        return  LB_PLAYER_LIST_STYLE.data
    elif len(sample) == 6:
        return  LB_PLAYER_LIST_STYLE.simple
    elif len(sample) == 2:
        return  LB_PLAYER_LIST_STYLE.rating
    elif len(sample) == 4:
        return  LB_PLAYER_LIST_STYLE.ratings
    else:
        return  LB_PLAYER_LIST_STYLE.rich
