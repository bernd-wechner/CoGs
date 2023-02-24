'''
Game Record Import match hunters to support map building.

Maps record their ID (a foreign app we're importing from) to our IDs and are built when importing with the benefit of
user input.
'''

from .models import LevenshteinDistance

from Leaderboards.models import Game, Player, Location

from django.db.models import F

############################################################################################################################
# MAP clues
#
# When performing an import we need to map the context, games, playes, locations from the defintions used in the imported
# format to our internals objects.
#
# On reading import data, we collect clues for that mapping process and here we define some standard Clue sets for the purpose.


class ContextClues:
    '''
    Clues for identifying an exiting context (which has maps predefined which may help, if not suffice, in mapping a
    current import. But in any case once we finish defining the maps we need to save those maps against a context, an
    exisiting one, or a new one.
    '''
    # Clues identifying the user/player/person who is the source of this import.
    name = None # Prone to spellling issues (a proximity based list is useful to select from)
    email = None # Prone to spellling issues (a proximity based list is useful to select from)
    BGGid = None # A great way for unambiguiously matching players/people

    # A clue identifying the app they are using (a given user may import from different sources.
    source = None # Should identify one of the supported formats


class GameClues:
    '''
    A template for a CoGs game hunt, ON reading data, a clue object can be instantiated and passed to a hunter function.
    '''
    name = None # Prone to spellling issues (a proximity based list is useful to select from)
    BGGid = None # A great way for unambiguiously matching games


class PlayerClues:
    '''
    A template for a CoGs player hunt, ON reading data, a clue object can be instantiated and passed to a hunter function.
    '''
    name = None # Prone to spellling issues (a proximity based list is useful to select from)
    email = None # Prone to spellling issues (a proximity based list is useful to select from)
    BGGid = None # A great way for unambiguiously matching players
    notes = None # Random hints


class LocationClues:
    '''
    A template for a CoGs location hunt, ON reading data, a clue object can be instantiated and passed to a hunter function.
    '''
    name = None # Prone to spellling issues (a proximity based list is useful to select from)
    notes = None # Random hints

############################################################################################################################
# HUNTERS loking for a local object that matches the imoprted one (or a list of candidates)_
#
# These functions all take clues and return candidates as either a single value (when confident) or a list of possible values
# in order of confidence, if not so sure.


candidate_limit = 10


def hunt_game(clues, limit=candidate_limit, add_name=False, include_best_quality=False):
    '''
    Given Game clues will try to find candidate games in our database

    :param clues:
    :param limit:
    :param add_name:
    :param include_best_quality:
    '''
    if clues.BGGid:
        try:
            cogsGame = Game.objects.get(BGGid=clues.BGGid)
            if include_best_quality:
                return 0, cogsGame
            else:
                return cogsGame
        except Game.DoesNotExist:
            pass

    if clues.name:
        candidates = Game.objects.annotate(lev_dist=LevenshteinDistance(F('name'), clues.name)).order_by('lev_dist')[:limit]
        if candidates:
            result = list(candidates) if len(candidates) > 1 else [candidates]
            if add_name:
                result.insert(0, clues.name)
            if include_best_quality:
                return candidates[0].lev_dist / len(clues.name), result
            else:
                return result

    if include_best_quality:
        return len(clues.name), None
    else:
        return None


def hunt_player(clues, limit=candidate_limit, add_name=False, include_best_quality=False):
    '''
    Given Player clues will try to find candidate players in our database

    :param clues: an instance of PlayerClues
    :param limit:
    :param add_name:
    :param include_best_quality:
    '''
    cogsPlayer = None

    if clues.BGGid:
        try:
            cogsPlayer = Player.objects.get(BGGname=clues.BGGid)  # @UndefinedVariable
            if include_best_quality:
                return 0, cogsPlayer
            else:
                return cogsPlayer
        except Player.DoesNotExist:
            pass

    if not cogsPlayer and clues.email:
        try:
            cogsPlayer = Player.objects.get(email_address__iexact=clues.email)  # @UndefinedVariable
            if include_best_quality:
                return 0, cogsPlayer
            else:
                return cogsPlayer
        except Player.DoesNotExist:
            pass

    # clues.name can == "Anonymous player" and technically session that include anonymous players
    # we eitehr need to a) ignore or b) create an anoynous unrated player for. The case for the
    # latter is modest, I mean it's fair to assume a player unknown is not likely a master, but a
    # noob butfar from known or certain, or always likely.
    if not cogsPlayer and clues.name:
        # How to pass full_name?
        candidates = Player.objects.all().annotate(lev_dist=LevenshteinDistance(Player.Full_name, clues.name)).order_by('lev_dist')[:limit]
        if candidates:
            result = list(candidates) if len(candidates) > 1 else [candidates]
            if add_name:
                result.insert(0, clues.name)
            if include_best_quality:
                return candidates[0].lev_dist / len(clues.name), result
            else:
                return result

    # TODO: Work out how notes can be used
    # we will have candidates here already (probably). Can we combine notes with name for a joint fuzzy match?
    if not cogsPlayer and clues.notes:
        # TODO:
        # Similarly a lexical distance search on name_personal + name_personal_family
        # albeit perhaps htis one migth be a trigram similarity?
        # https://docs.djangoproject.com/en/4.1/ref/contrib/postgres/lookups/
        pass

    if include_best_quality:
        return len(clues.name), None
    else:
        return None


def hunt_location(clues, limit=candidate_limit, add_name=False, include_best_quality=False):
    '''
    Given Location clues will try to find candidate locations in our database

    :param clues:
    :param limit:
    :param add_name:
    :param include_best_quality:
    '''
    if clues.name:
        candidates = Location.objects.annotate(lev_dist=LevenshteinDistance(F('name'), clues.name)).order_by('lev_dist')[:limit]
        if candidates:
            result = list(candidates) if len(candidates) > 1 else [candidates]
            if add_name:
                result.insert(0, clues.name)
            if include_best_quality:
                return candidates[0].lev_dist / len(clues.name), result
            else:
                return result

    # TODO: Work out what to do with clues.notes if it exists

    if include_best_quality:
        return len(clues.name), None
    else:
        return None
