'''
Game Record Import models

Provides:

    1. A model for each of Games, Player and Location storing a map from theit (some other apps) ID to ours (GameMap, PlayerMap, LocationMap)
    2. A model to store import contexts (ImportContext) which bind a set of maps
    3. A model that records Imports (and is used for managing them)
        - Session has a FroegnKey back to here that can optionalle record an import that a Session came from.
        - Session being hte object that binds a game, players, location and results to record a play session.
    4. Proximite measure support (LevenshteinDistance) for matching their game names to ours, players to our etc and providing
        ordered proposals on the basis of proximity for map creation.
'''

import os, re

from django.db import models
from django.conf import settings
from django.contrib.auth.models import User

from django_model_admin_fields import AdminModel
from django_rich_views.model import TimeZoneMixIn

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


class ImportContext(AdminModel, TimeZoneMixIn):
    '''
    Defines an import context against which we can store maps of game, player and location IDs as needed.

    The Maps (Game, Player, Location) are tied to a given context (via an Import) so that repeated imports
    in the same context can benefit from a growing map over time. The importing user should be an editor
    but that user (or an admin) can permit other users to edit the context. By edit here, we mean edit the
    mappings associated with this context.

    AdminModel provides created_on and created_on_tz and created_on_local() that describe the
    time the import was first attempted (the file uploaded and this record created)
    '''
    name = models.CharField('Name of the Session Import Context', max_length=MAX_NAME_LEN)
    editors = models.ManyToManyField(User, verbose_name='Editors', related_name='import_contexts')

    @property
    def game_maps(self):
        '''
        All the game maps associated with this context.
        '''
        return GameMap.objects.filter(related_import__context=self)

    @property
    def player_maps(self):
        '''
        All the player maps associated with this context.
        '''
        return PlayerMap.objects.filter(related_import__context=self)

    @property
    def location_maps(self):
        '''
        All the location maps associated with this context.
        '''
        return LocationMap.objects.filter(related_import__context=self)


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
        Initialises the maps for this import.

        Each map, GameMap, PlayerMap, LocationMap maps their ID to our ID (theirs to ours)

        We initialise them simply with theirs, the creation of ours will be based on suggestions based
        on Clues -- see GameClues, PlayerClues and LocationClues below (not models, just classes used in
        the hunt for matches see hunt_game, hunt_player and hunt_location below).

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
        Given a list of their game IDs initialises the import map creation process by creating an
        empty (incomplete) map for each of their games.

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
        Given a list of their player IDs initialises the import map creation process by creating an
        empty (incomplete) map for each of their players.

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
        Given a list of their location IDs initialises the import map creation process by creating an
        empty (incomplete) map for each of their locations.

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
        '''
        All the games that have been mapped already.
        '''
        return self.game_maps.objects.exclude(ours__isnull=True)

    @property
    def games_tomap(self):
        '''
        All the games that are in the import but have not been mapped yet
        '''
        return self.game_maps.objects.filter(ours__isnull=True)

    @property
    def games_progress(self):
        '''
        Returns a measure of progress as a 2-tuple.
        The % complete is simply mapped/total*100.
        '''
        mapped = self.mapped_games.count()
        total = self.game_maps.objects.all().count()
        return (mapped, total)

    @property
    def mapped_players(self):
        '''
        All the players that have been mapped already.
        '''
        return self.player_maps.objects.exclude(ours__isnull=True)

    @property
    def players_tomap(self):
        '''
        All the players that are in the import but have not been mapped yet
        '''
        return self.player_maps.objects.filter(ours__isnull=True)

    @property
    def players_progress(self):
        '''
        Returns a measure of progress as a 2-tuple.
        The % complete is simply mapped/total*100.
        '''
        mapped = self.mapped_players.count()
        total = self.player_maps.objects.all().count()
        return (mapped, total)

    @property
    def mapped_locations(self):
        '''
        All the locations that have been mapped already.
        '''
        return self.game_maps.objects.exclude(ours__isnull=True)

    @property
    def locations_tomap(self):
        '''
        All the locations that are in the import but have not been mapped yet
        '''
        return self.game_maps.objects.filter(ours__isnull=True)

    @property
    def locations_progress(self):
        '''
        Returns a measure of progress as a 2-tuple.
        The % complete is simply mapped/total*100.
        '''
        mapped = self.mapped_locations.count()
        total = self.location_maps.objects.all().count()
        return (mapped, total)

    @property
    def progress(self):
        '''
        Returns a measure of total progress as a 2-tuple for each of hte maps we intend to build.
        '''
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


class GameMap(AdminModel, TimeZoneMixIn):
    '''
    Records a map of their ID to our ID for a game. The map is defined during a session import and associated with that.
    The session import is associated with a context and all the context related game maps can be fetched from the context.

    We use lazy references to Leaderrboard models so as to avoid circular references.
    '''
    related_import = models.ForeignKey(Import, verbose_name='Import', related_name='game_maps', on_delete=models.CASCADE)
    theirs = models.CharField('Their Game', max_length=MAX_KEY_LEN)
    ours = models.ForeignKey('Leaderboards.Game', verbose_name='Our Game', related_name='import_maps', null=True, on_delete=models.SET_NULL)


class PlayerMap(AdminModel, TimeZoneMixIn):
    '''
    Records a map of their ID to our ID for a player. The map is defined during a session import and associated with that.
    The session import is associated with a context and all the context related game maps can be fetched from the context.

    We use lazy references to Leaderrboard models so as to avoid circular references.
    '''
    related_import = models.ForeignKey(Import, verbose_name='Import', related_name='player_maps', on_delete=models.CASCADE)
    theirs = models.CharField('Their Player', max_length=MAX_KEY_LEN)
    ours = models.ForeignKey('Leaderboards.Player', verbose_name='Our Player', related_name='import_maps', null=True, on_delete=models.SET_NULL)


class LocationMap(AdminModel, TimeZoneMixIn):
    '''
    Records a map of their ID to our ID for a location. The map is defined during a session import and associated with that.
    The session import is associated with a context and all the context related game maps can be fetched from the context.

    We use lazy references to Leaderrboard models so as to avoid circular references.
    '''
    related_import = models.ForeignKey(Import, verbose_name='Import', related_name='location_maps', on_delete=models.CASCADE)
    theirs = models.CharField('Their Location', max_length=MAX_KEY_LEN)
    ours = models.ForeignKey('Leaderboards.Location', verbose_name='Our Location', related_name='import_maps', null=True, on_delete=models.SET_NULL)

############################################################################################################################
# SIMILARITY support
#
# We provide a Levenshtein distance function for this.
#
# Documented here:
#
#    http://andilabs.github.io/2018/04/06/searching-in-django-unaccent-levensthein-full-text-search-postgres-power.html
#
# Used as follows:
#
#    .annotate(levenshtein_distance_dist=Levenshtein(F('name'), 'Foobar')
#
# Django already includes a trigram function offering this too.
#
#    https://docs.djangoproject.com/en/dev/ref/contrib/postgres/lookups/#trigram-similarity
#
#    .annotate(trigram_similarity=TrigramSimilarity(F('name'), 'Foobar'))
#
# But Levenshtein is natively available in PostGResQL and alledgedly better than Trigram.

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