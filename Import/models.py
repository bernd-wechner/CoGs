import os, re

from django.db import models
from django.db.models import F
from django.conf import settings
from django.contrib.auth.models import User

from django_model_admin_fields import AdminModel
from django_rich_views.model import TimeZoneMixIn

from Leaderboards.models import Game, Player, Location

MAX_NAME_LEN = 256
MAX_KEY_LEN = 256
MAX_FILENAME_LEN = 128


def local_path(instance, filename):
    # Record the filename as a model field
    instance.filename = filename

    # file will be uploaded to MEDIA_ROOT/import/<user_id>/<n> <filename>
    folder = os.path.join("import", "{instance.user.id}")
    path = os.path.join(settings.MEDIA_ROOT, folder)

    # We prefix files with a 9 digit int incrementing. Allows a given user to
    # perform a billion imports before we run out.
    files = filter(lambda f: re.match("^\d{9} ", f), os.listdir(path))
    file_no = len(files)

    # Return file path relative to MEDIA_ROOT
    return f'import/{instance.user.id}/{file_no:09d} {filename}'

############################################################################################################################
# BASIC models
#
# These capture the fact of an Import, the state its at (started, complete, half done) and record the history of imports


class ImportContext(AdminModel):
    '''
    Defines an import context against which we can store maps of game, player and location IDs as needed.

    The Maps (Game, Player, Location) are tied to a given context (via an Import) so that repeated imports
    in the same context can benefit from a growing map over time. The importing user should be a an editor
    but that user (or an admin) can permit other users to edit the context. By edit here, we mean edit the
    mappings associatated with this context.

    AdminModel provides created_on and created_on_tz and created_on_local() that describe the
    time the import was first attempted (the file uploaded and this record created)
    '''
    name = models.CharField('Name of the Session Import Context', max_length=MAX_NAME_LEN)
    editors = models.ManyToManyField(User, verbose_name='Editors', related_name='import_contexts')


class Import(AdminModel, TimeZoneMixIn):
    '''
    A record of attempted imports and status

    AdminModel provides created_on and created_on_tz and created_on_local() that describe the
    time the import was first attempted (the file uploaded and this record created)

    On creation the maps should all be created with either a known mapping or null as our ID.
    Progress in defining the map can be determined by counting the nulls (unfinished mappings)

    '''
    context = models.ForeignKey(ImportContext, verbose_name='Import Context', related_name='imports', on_delete=models.CASCADE)
    filename = models.CharField(max_length=MAX_FILENAME_LEN, editable=False)
    file = models.FileField(upload_to=local_path)

    # Set to true when the import is complete. it is complete once all the maps are defined and the sessions
    # are imported.
    complete = models.BooleanField(default=False)

    intrinsic_relations = ["context"]

    def init_maps(self, game_ids, player_ids, location_ids, save=False):
        '''
        Initialises the maps for this import. Used to track mapping progress.

        :param game_ids: An iterable of their IDs (classically a set, or list, or tuple) of their IDs
        :param player_ids: An iterable of their IDs (classically a set, or list, or tuple) of their IDs
        :param location_ids: An iterable of their IDs (classically a set, or list, or tuple) of their IDs
        :param save: Save the maps (else just return them as a list, unsaved)
        '''
        self.init_game_maps(game_ids, save)
        self.init_player_maps(player_ids, save)
        self.init_location_maps(location_ids, save)

    def init_game_maps(self, theirs, save=False):
        '''
        :param theirs: An iterable (classically a set, or list, or tuple) of their IDs
        :param save: Save the maps (else just return them as a list, unsaved)
        '''
        maps = []
        for ID in theirs:
            maps.append(GameMap(related_import=self, theirs=ID))

        if save:
            for m in maps:
                m.save()

    def init_player_maps(self, theirs, save=False):
        '''
        :param theirs: An iterable (classically a set, or list, or tuple) of their IDs
        :param save: Save the maps (else just return them as a list, unsaved)
        '''
        maps = []
        for ID in theirs:
            maps.append(PlayerMap(related_import=self, theirs=ID))

        if save:
            for m in maps:
                m.save()

    def init_location_maps(self, theirs, save=False):
        '''
        :param theirs: An iterable (classically a set, or list, or tuple) of their IDs
        :param save: Save the maps (else just return them as a list, unsaved)
        '''
        maps = []
        for ID in theirs:
            maps.append(LocationMap(related_import=self, theirs=ID))

        if save:
            for m in maps:
                m.save()

    @property
    def mapped_games(self):
        return self.game_maps.objects.exclude(ours__isnull=True)

    @property
    def games_tomap(self):
        return self.game_maps.objects.filter(ours__isnull=True)

    @property
    def games_progress(self):
        mapped = self.mapped_games.count()
        total = self.game_maps.objects.all().count()
        return (mapped, total)

    @property
    def mapped_players(self):
        return self.player_maps.objects.exclude(ours__isnull=True)

    @property
    def players_tomap(self):
        return self.player_maps.objects.filter(ours__isnull=True)

    @property
    def players_progress(self):
        mapped = self.mapped_players.count()
        total = self.player_maps.objects.all().count()
        return (mapped, total)

    @property
    def mapped_locations(self):
        return self.game_maps.objects.exclude(ours__isnull=True)

    @property
    def locations_tomap(self):
        return self.game_maps.objects.filter(ours__isnull=True)

    @property
    def locations_progress(self):
        mapped = self.mapped_locations.count()
        total = self.location_maps.objects.all().count()
        return (mapped, total)

    @property
    def progress(self):
        return {"Games": self.games_progress,
                "Players": self.players_progress,
                "Locations": self.locations_progress}

    class Meta(AdminModel.Meta):
        verbose_name = "Import"
        verbose_name_plural = "Imports"
        get_latest_by = ["created_on"]
        ordering = ['-created_on']

############################################################################################################################
# MAP models
#
# Each map belongs to a particular session import (which belongs to a import context) and maps one of their objects
# to one of ours. Any time a new import is attempted with the same context then these maps can be consulted as a first
# step in resolving any mappings.
#
# Ours can be identified with a ForeignKey
#
# Theirs could easily be:
#     an int
#     a UUID
#     a string
#   a combination of these ...
#
# Depends on the import source. So we want a flexible way of storing their key.
# and use  CharField of sufficient length.
#
# We can store ints, UUIDs, strigs in that, even tuples of them in JSON format for example.


class GameMap(AdminModel):
    related_import = models.ForeignKey(Import, verbose_name='Import', related_name='game_maps', on_delete=models.CASCADE)
    theirs = models.CharField('Their Game', max_length=MAX_KEY_LEN)
    ours = models.ForeignKey(Game, verbose_name='Our Game', related_name='import_maps', null=True, on_delete=models.SET_NULL)


class PlayerMap(AdminModel):
    related_import = models.ForeignKey(Import, verbose_name='Import', related_name='player_maps', on_delete=models.CASCADE)
    theirs = models.CharField('Their Player', max_length=MAX_KEY_LEN)
    ours = models.ForeignKey(Player, verbose_name='Our Player', related_name='import_maps', null=True, on_delete=models.SET_NULL)


class LocationMap(AdminModel):
    related_import = models.ForeignKey(Import, verbose_name='Import', related_name='location_maps', on_delete=models.CASCADE)
    theirs = models.CharField('Their Location', max_length=MAX_KEY_LEN)
    ours = models.ForeignKey(Location, verbose_name='Our Location', related_name='import_maps', null=True, on_delete=models.SET_NULL)

############################################################################################################################
# SIMILARITY support
#
# We provide a Levenshtein distance function for this.
#
#    http://andilabs.github.io/2018/04/06/searching-in-django-unaccent-levensthein-full-text-search-postgres-power.html
#
#    .annotate(levenshtein_distance_dist=Levenshtein(F('name'), 'Foobar')
#
# Django already includes  trigram function offering this too.
#
#    https://docs.djangoproject.com/en/dev/ref/contrib/postgres/lookups/#trigram-similarity
#
#    .annotate(trigram_similarity=TrigramSimilarity(F('name'), 'Foobar'))


class LevenshteinDistance(models.Func):
    template = "%(function)s(%(expressions)s, '%(search_term)s')"
    function = "levenshtein"

    def __init__(self, expression, search_term, **extras):
        search_term = search_term.replace("'", "''")
        super().__init__(
            expression,
            search_term=search_term,
            **extras
        )

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
    name = None
    email = None
    BGGid = None


class GameClues:
    '''
    A template for a CoGs game hunt, ON reading data, a clue object can be instantiated and passed to a hunter function.
    '''
    name = None
    BGGid = None


class PlayerClues:
    '''
    A template for a CoGs player hunt, ON reading data, a clue object can be instantiated and passed to a hunter function.
    '''
    name = None
    email = None
    BGGid = None
    notes = None


class LocationClues:
    '''
    A template for a CoGs location hunt, ON reading data, a clue object can be instantiated and passed to a hunter function.
    '''
    name = None
    notes = None

############################################################################################################################
# HUNTERS loking for a local object that matches the imoprted one (or a list of candidates)_
#
# Functions that take clues and return candidates as either a single value (when confident) or a list of possible values
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
        candidates = Player.objects.annotate(lev_dist=LevenshteinDistance(Player.Full_name, clues.name)).order_by('lev_dist')[:limit]
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
