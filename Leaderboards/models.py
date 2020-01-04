# Python packages
import trueskill
import html
import re
import pytz
from collections import OrderedDict
from math import isclose
from scipy.stats import norm
from datetime import datetime, timedelta
from builtins import str

# Django packages
from django.db import models, DataError, IntegrityError #, connection, 
from django.db.models import Sum, Max, Avg, Count, Q, OuterRef, Subquery
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError, ObjectDoesNotExist, MultipleObjectsReturned #, PermissionDenied
from django.core.validators import RegexValidator
from django.urls import reverse_lazy
from django.contrib import admin
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.formats import localize
from django.utils.timezone import localtime
from django.utils.safestring import mark_safe
from django.conf import settings

from bitfield import BitField
from bitfield.forms import BitFieldCheckboxSelectMultiple
from timezone_field import TimeZoneField

from django_model_admin_fields import AdminModel
from django_model_privacy_mixin import PrivacyMixIn

from django_generic_view_extensions.options import flt, osf
from django_generic_view_extensions.model import field_render, link_target_url, TimeZoneMixIn
from django_generic_view_extensions.decorators import property_method
from django_generic_view_extensions.datetime import time_str
from django_generic_view_extensions.debug import print_debug 
from django_generic_view_extensions.queryset import get_SQL
from _ctypes import ArgumentError

# CoGs Leaderboard Server Data Model
#
# The underlying model of data is designed designed to allow:
#
# Game sessions to be recorded by a registrar
# TrueSkill ratings for a player on a game to be calculable from the session records.
# So that leaderboards can be presented for any game in any league (a distinct set of players who are competing)
# Consistent TrueSkill ratings across leagues so that a global leaderboard can be generated as well
# BoardGameGeek connections support for games and players
#
# Note this file defines the data model in Python syntax and a migration (Sync DB)
# converts it into a database schema (table definitions).

MAX_NAME_LENGTH = 200                       # The maximum length of a name in the database, i.e. the char fields for player, game, team names and so on.
FLOAT_TOLERANCE = 0.0000000000001           # Tolerance used for comparing float values of Trueskill settings and results between two objects when checking integrity.
NEVER = pytz.utc.localize(datetime.min)     # Used for times to indicat if there is no last play or victory that has a time

# Some reserved names for ALL objects in a model (note ID=0 is reserved for the same meaning).
ALL_LEAGUES = "Global"                      # A reserved key in leaderboard dictionaries used to represent "all leagues" in some requests
ALL_PLAYERS = "Everyone"                    # A reserved key for leaderboard filtering representing all players
ALL_GAMES = "All Games"                     # A reserved key for leaderboard filtering representing all games

#===============================================================================
# The support models, that store all the play records that are needed to
# calculate and maintain TruesKill ratings for players.
#===============================================================================

class TrueskillSettings(models.Model):
    '''
    The site wide TrueSkill settings to use (i.e. not Game).
    '''
    # Changing these affects the entire ratings history. That is we change one of these settings, either:
    #    a) All the ratings history needs to be recalculated to get a consistent ratings result based on the new settings
    #    b) We keep the ratings history with the old values and move forward with the new
    # Merits? Methods?
    # Suggest we have a form for editing these with processing logic and don't let the admin site edit them, or create logic
    # that can adapt to admin site edits - flagging the likelihood. Or perhaps we should make this not a one tuple table
    # but store each version with a date. That in can of course then support staged ratings histories, so not a bad idea.
    mu0 = models.FloatField('TrueSkill Initial Mean (µ0)', default=trueskill.MU)
    sigma0 = models.FloatField('TrueSkill Initial Standard Deviation (σ0)', default=trueskill.SIGMA)
    delta = models.FloatField('TrueSkill Delta (δ)', default=trueskill.DELTA)

    add_related = None
    def __unicode__(self): return u'µ0={} σ0={} δ={}'.format(self.mu0, self.sigma0, self.delta)
    def __str__(self): return self.__unicode__()

    class Meta:
        verbose_name_plural = "Trueskill settings"

#===============================================================================
# The Ratings model(s) where TrueSkill ratings are stored
#===============================================================================

class RatingModel(TimeZoneMixIn, AdminModel):
    '''
    A Trueskill rating for a given Player at a give Game.

    This is the ultimate goal of the whole exercise. To record game sessions in order to calculate 
    ratings for players and rank them in leaderboards.
    
    Every player has a rating at every game, though only those deviating from default (i.e. games 
    that a player has players) are stored in the database.
    
    This is an abstract model defining the table structure that us used
    by Rating and Backup_Rating. The latter being a place to copy Rating 
    before a complete rebuild of ratings. 
    
    The preferred way of fetching a Rating is through Player.rating(game) or Game.rating(player).
    '''
    player = models.ForeignKey('Player', verbose_name='Player', related_name='%(class)ss', on_delete=models.CASCADE)
    game = models.ForeignKey('Game', verbose_name='Game', related_name='%(class)ss', on_delete=models.CASCADE)

    plays = models.PositiveIntegerField('Play Count', default=0)
    victories = models.PositiveIntegerField('Victory Count', default=0)
    
    last_play = models.DateTimeField('Time of Last Play', default=NEVER)
    last_play_tz = TimeZoneField('Time of Last Play, Timezone', default=settings.TIME_ZONE, editable=False)
    last_victory = models.DateTimeField('Time of Last Victory', default=NEVER)
    last_victory_tz = TimeZoneField('Time of Last Victory, Timezone', default=settings.TIME_ZONE, editable=False)
    
    # Although Eta (η) is a simple function of Mu (µ) and Sigma (σ), we store it alongside Mu and Sigma because it is also a function of global settings µ0 and σ0.
    # To protect ourselves against changes to those global settings, or simply to detect them if it should happen, we capture their value at time of rating update in the Eta.
    # These values before each game session and their new values after a game session are stored with the Session Ranks for integrity and history plotting.
    trueskill_mu = models.FloatField('Trueskill Mean (µ)', default=trueskill.MU, editable=False)
    trueskill_sigma = models.FloatField('Trueskill Standard Deviation (σ)', default=trueskill.SIGMA, editable=False)
    trueskill_eta = models.FloatField('Trueskill Rating (η)', default=trueskill.SIGMA, editable=False)
    
    # Record the global TrueskillSettings mu0, sigma0 and delta with each rating as an integrity measure.
    # They can be compared against the global settings and and difference can trigger an update request.
    # That is, flag a warning and if they are consistent across all stored ratings suggest TrueskillSettings
    # should be restored (and offer to do so?) or if inconsistent (which is an integrity error) suggest that
    # ratings be globally recalculated
    trueskill_mu0 = models.FloatField('Trueskill Initial Mean (µ)', default=trueskill.MU, editable=False)
    trueskill_sigma0 = models.FloatField('Trueskill Initial Standard Deviation (σ)', default=trueskill.SIGMA, editable=False)
    trueskill_delta = models.FloatField('TrueSkill Delta (δ)', default=trueskill.DELTA)
    
    # Record the game specific Trueskill settings beta, tau and p with rating as an integrity measure.
    # Again for a given game these must be consistent among all ratings and the history of each rating. 
    # And change while managing leaderboards should trigger an update request for ratings relating to this game.  
    trueskill_beta = models.FloatField('TrueSkill Skill Factor (ß)', default=trueskill.BETA)
    trueskill_tau = models.FloatField('TrueSkill Dynamics Factor (τ)', default=trueskill.TAU)
    trueskill_p = models.FloatField('TrueSkill Draw Probability (p)', default=trueskill.DRAW_PROBABILITY)

    def __unicode__(self): return  u'{} - {} - {:.1f} teeth, from (µ={:.1f}, σ={:.1f} after {} plays)'.format(self.player, self.game, self.trueskill_eta, self.trueskill_mu, self.trueskill_sigma, self.plays)
    def __str__(self): return self.__unicode__()
        
    class Meta(AdminModel.Meta):
        ordering = ['-trueskill_eta']
        abstract = True
    
class Rating(RatingModel):
    '''
    This is the actual repository of ratings that describe leaderboards.
    
    Its partner Backup_Rating stores a backup (form before the last rebuild) 
    '''
    @property
    def last_performance(self) -> 'Performance':
        '''
        Returns the latest performance object that this player played this game in. 
        '''
        game = self.game
        player = self.player
        
        plays = Session.objects.filter(Q(game=game) & (Q(ranks__player=player) | Q(ranks__team__players=player))).order_by('-date_time')

        return None if (plays is None or plays.count() == 0) else plays[0].performance(player) 

    @property
    def last_winning_performance(self) -> 'Performance':
        '''
        Returns the latest performance object that this player played this game in and won. 
        '''
        game = self.game
        player = self.player
        
        wins = Session.objects.filter(Q(game=game) & Q(ranks__rank=1) & (Q(ranks__player=player) | Q(ranks__team__players=player))).order_by('-date_time')

        return None if (wins is None or wins.count() == 0) else wins[0].performance(player) 

    @property
    def link_internal(self) -> str:
        return reverse_lazy('view', kwargs={"model":self._meta.model.__name__,"pk": self.pk})

    def reset(self, session):
        '''
        Given a session, resets this rating object to what it was after this session.
        
        Allows for a rewind of the rating to what it was at some time in past, so that 
        it can be rebuilt from that point onward if desired.    
        '''
        performance = session.performance(self.player)
        
        self.plays = performance.play_number
        self.victories = performance.victory_count
        
        self.last_play = session.date_time
        
        if performance.is_victory:
            self.last_victory = session.date_time
        else:
            last_victory = session.previous_victory(performance.player)
            self.last_victory = None if last_victory is None else last_victory.session.date_time   
        
        self.trueskill_mu = performance.trueskill_mu_after
        self.trueskill_sigma = performance.trueskill_sigma_after
        self.trueskill_eta = performance.trueskill_eta_after
        
        self.trueskill_mu0 = performance.trueskill_mu0
        self.trueskill_sigma0 = performance.trueskill_sigma0
        self.trueskill_beta = performance.trueskill_beta
        self.trueskill_delta = performance.trueskill_delta

        self.trueskill_tau = performance.trueskill_tau
        self.trueskill_p = performance.trueskill_p

    def recalculate_last_play_and_victory(self):
        '''
        last_play and last_victory are fields in the Rating model for convenience, quick retrieval and easy querying.
        
        They are a statistic on recorded sessions though. This method requests they  be recalculated from the base
        data.
        '''
        self.last_play = self.player.last_play(self.game)
        self.last_victory = self.player.last_win(self.game)
        self.save()

    @classmethod    
    def create(cls, player, game, mu=None, sigma=None):
        '''
        Create a new Rating for player at game, with specified mu and sigma.

        An explicit method, rather than override of __init_ which is called 
        whenever and object is instantiated which can be when creating a new 
        Rating or when fetching an old one fromt the database. So not appropriate
        to override it for new Ratings.
        ''' 

        TS = TrueskillSettings()
        
        trueskill_mu = TS.mu0 if mu == None else mu
        trueskill_sigma = TS.sigma0 if sigma == None else sigma
        
        self = cls(player=player,
                    game=game,
                    plays=0,
                    victories=0,
                    last_play=NEVER,
                    last_victory=NEVER,
                    trueskill_mu=trueskill_mu,
                    trueskill_sigma=trueskill_sigma,
                    trueskill_eta=trueskill_mu - TS.mu0 / TS.sigma0 * trueskill_sigma,  # µ − (µ0 ÷ σ0) × σ
                    trueskill_mu0=TS.mu0,
                    trueskill_sigma0=TS.sigma0,
                    trueskill_beta=game.trueskill_beta,
                    trueskill_delta=TS.delta,
                    trueskill_tau=game.trueskill_tau,
                    trueskill_p=game.trueskill_p
                    )  
        return self
    
    @classmethod
    def get(cls, player, game):
        '''
        Fetch (or create fromd efaults) the rating for a given player at a game
        and perform some quick data integrity checks in the process.  
        '''
        TS = TrueskillSettings()
        
        try:
            r = Rating.objects.get(player=player, game=game)
        except ObjectDoesNotExist:
            r = Rating.create(player=player, game=game)
        except MultipleObjectsReturned:
            raise IntegrityError("Integrity error: more than one rating for {} at {}".format(player.name_nickname, game.name))
        
        if not (isclose(r.trueskill_mu0, TS.mu0, abs_tol=FLOAT_TOLERANCE)  
         and isclose(r.trueskill_sigma0, TS.sigma0, abs_tol=FLOAT_TOLERANCE)
         and isclose(r.trueskill_delta, TS.delta, abs_tol=FLOAT_TOLERANCE)
         and isclose(r.trueskill_beta, game.trueskill_beta, abs_tol=FLOAT_TOLERANCE)
         and isclose(r.trueskill_tau, game.trueskill_tau, abs_tol=FLOAT_TOLERANCE)
         and isclose(r.trueskill_p, game.trueskill_p, abs_tol=FLOAT_TOLERANCE)):
            SettingsWere = "µ0: {}, σ0: {}, ß: {}, δ: {}, τ: {}, p: {}".format(r.trueskill_mu0, r.trueskill_sigma0, r.trueskill_delta, r.trueskill_beta, r.trueskill_tau, r.trueskill_p)
            SettingsAre = "µ0: {}, σ0: {}, ß: {}, δ: {}, τ: {}, p: {}".format(TS.mu0, TS.sigma0, TS.delta, game.trueskill_beta, game.trueskill_tau, game.trueskill_p)
            raise DataError("Data error: A trueskill setting has changed since the last rating was saved. They were ({}) and now are ({})".format(SettingsWere, SettingsAre))
            # TODO: Issue warning to the registrar more cleanly than this
            # Email admins with notification and suggested action (fixing settings or rebuilding ratings).
            # If only game specific settings changed on that game is impacted of course. 
            # If global settings are changed all ratings are affected.
            
        return r 

    @classmethod
    def update(self, session, feign_latest=False):
        '''
        Update the ratings for all the players of a given session.
        
        :param feign_latest: if True will ignore recorded future sessions and pretend the provided one is the latest one. Used for rebuiling a rating by walking through existing sessions.  
        '''
        TS = TrueskillSettings()
        
        # Check to see if this is the latest play for each player
        # And capture the current rating for each player (which we ill update) 
        is_latest = True
        player_rating = {}
        for performance in session.performances.all():
            rating = Rating.get(performance.player, session.game)
            player_rating[performance.player] = rating
            if not session.date_time > rating.last_play:
                is_latest = False
        
        if is_latest or feign_latest:
            # Trickle admin bypass down 
            if self.__bypass_admin__:
                session.__bypass_admin__ = True                    
            
            # Get the session impact (records results in database Performance objects)
            impact = session.calculate_trueskill_impacts()    
            
            # Update the rating for this player/game combo
            for player in impact:
                r = player_rating[player]

                # Record the new rating data                    
                r.trueskill_mu = impact[player]["after"]["mu"]
                r.trueskill_sigma = impact[player]["after"]["sigma"]
                r.trueskill_eta = r.trueskill_mu - TS.mu0 / TS.sigma0 * r.trueskill_sigma  # µ − (µ0 ÷ σ0) × σ
                
                # Record the TruesSkill settings used to get them                     
                r.trueskill_mu0 = TS.mu0
                r.trueskill_sigma0 = TS.sigma0
                r.trueskill_delta = TS.delta
                r.trueskill_beta = session.game.trueskill_beta
                r.trueskill_tau = session.game.trueskill_tau
                r.trueskill_p = session.game.trueskill_p
                
                # Record the context of the rating 
                r.plays = impact[player]["plays"]
                r.victories = impact[player]["victories"]
                    
                r.last_play = session.date_time
                if session.performance(player).is_victory:
                    r.last_victory = session.date_time
                # else leave r.last_victory unchanged
                
                # Trickle admin bypass down 
                if self.__bypass_admin__:
                    r.__bypass_admin__ = True                    
                    
                r.save()
        else:
            # One or more players have ratings recorded based on sessions played after the provided session.
            # This should only happen if someone is adding a session retrospectively and after sessions were
            # added that were played since the one being recorded. An unusual not a usual circumstance. But
            # one we need to accommodate all the same.
            #
            # The tangled web of (sorted list of all) future sessions impacted by adding this one are returned 
            # by session.future_sessions.
            for rating in player_rating.values():
                if session.date_time < rating.last_play:
                    rating.reset(session)

            # Having reset the ratings of all players in this session
            # update with the current session.
            Rating.update(session, feign_latest=True)

            # Then we want to update for each future session, in order so we want to buld
            fs = session.future_sessions
            if not fs is None: 
                for s in fs:
                    Rating.update(s, feign_latest=True)
    
    @classmethod
    def rebuild_all(self):
        # Walk through the history of sessions to rebuild all ratings
        # If ever performed keep a record of duration overall and per 
        # session tp permit a cost esitmate should it happen again. 
        # On a large database this could be a costly exercise, causing
        # some down time to the server (must either lock server to do 
        # this as we cannot have new ratings being created while 
        # rebuilding or we could have the update method above check
        # if a rebuild is underway and if so schedule an update ro
        
        # TODO:        
        # Copy the whole Ratings table to a backup table
        # Erase the current table
        # Walk through the sessions in chronological order rebuilding it.
        # Create a single abstract model and have both of your models inherit from there: 
        # https://docs.djangoproject.com/en/1.10/topics/db/models/#abstract-base-classes
        
        # Create an entry in Rebuild_Log
        # Start timer and counter
        # Copy all ratings to Backup_Rating
        
        # Bypass admin field updates for a rating rebuild
        self.__bypass_admin__ = True

        print("Rebuilding all leaderboard ratings...", flush=False)

        self.objects.all().delete()
        sessions = Session.objects.all().order_by('date_time')
        
        # Traverse sessions in chronological order (order_by is the time of the session) and update ratings from each session
        for s in sessions:
            print(s.pk, s.date_time, s.game.name, flush=False)
            self.update(s, feign_latest=True)
            
        print("Done.", flush=False)

        # Stop timer
        # Update the  entry in Rebuild_Log with performance results
        pass

    def check_integrity(self):
        '''
        Perform integrity check on this rating record
        '''
        # Check for uniqueness
        same = Rating.objects.filter(player=self.player, game=self.game)
        assert same.count() <= 1, "Integrity error: Duplicate rating entries for player: {} and game: {}".format(self.player, self.game)
        
        # Check that rating matches last performance
        last_play = self.last_performance
        last_win = self.last_winning_performance
        
        assert not last_play is None, "Integrity error: Rating {} ({}) has no Last Play".format(self.pk, self)
        
        assert isclose(self.trueskill_mu, last_play.trueskill_mu_after, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance µ mismatch. Rating has {} Last Play has {}".format(self.trueskill_mu, last_play.trueskill_mu_after)
        assert isclose(self.trueskill_sigma, last_play.trueskill_sigma_after, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance σ mismatch. Rating has {} Last Play has {}".format(self.trueskill_sigma, last_play.trueskill_sigma_after)
        assert isclose(self.trueskill_eta, last_play.trueskill_eta_after, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance η mismatch. Rating has {} Last Play has {}".format(self.trueskill_eta, last_play.trueskill_eta_after)

        assert isclose(self.trueskill_mu0, last_play.trueskill_mu0, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance µ0 mismatch. Rating has {} Last Play has {}".format(self.trueskill_mu0, last_play.trueskill_mu0_after)
        assert isclose(self.trueskill_sigma0, last_play.trueskill_sigma0, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance σ0 mismatch. Rating has {} Last Play has {}".format(self.trueskill_sigma0, last_play.trueskill_sigma0_after)
        assert isclose(self.trueskill_delta, last_play.trueskill_delta, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance δ mismatch. Rating has {} Last Play has {}".format(self.trueskill_delta, last_play.trueskill_delta_after)

        assert isclose(self.trueskill_tau, last_play.trueskill_tau, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance τ mismatch. Rating has {} Last Play has {}".format(self.trueskill_tau, last_play.trueskill_tau_after)
        assert isclose(self.trueskill_p, last_play.trueskill_p, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance p mismatch. Rating has {} Last Play has {}".format(self.trueskill_p, last_play.trueskill_p_after)

        # Check that the play and victory counts reflect what Performance says
        assert self.plays == last_play.play_number, "Integrity error: Play count mismatch. Rating has {} Last play has {}.".format(self.plays, last_play.play_number)
        assert self.victories == last_play.victory_count, "Integrity error: Victory count mismatch. Rating has {} Last play has {}.".format(self.victories, last_play.victory_count)

        # Check that last_play and last_victory dates are accurate reflects on Performance records
        assert self.last_play == last_play.session.date_time, "Integrity error: Last play mismatch. Rating has {} Last play has {}.".format(self.last_play, last_play.session.date_time)
        
        if last_win:
            assert self.last_victory == last_win.session.date_time, "Integrity error: Last victory mismatch. Rating has {} Last victory has {}.".format(self.last_victory, last_win.session.date_time)
        else:
            assert self.last_victory == NEVER, "Integrity error: Last victory mismatch. Rating has {} when expecting the NEVER value of {}.".format(self.last_victory, NEVER)
    
    def clean(self):
        # TODO: diagnose when this is called. What can we assume about session cleans? And what not?
        # This rating must be unique
        same = Rating.objects.filter(player=self.player, game=self.game)
        
        if same.count() > 1:
            raise ValidationError("Duplicate ratings found for player: {} and game: {}".format(self.player, self.game))
        
        # Rating should match the last performance
        # TODO: When do we land here? And how do we sync with self.update? 

class Backup_Rating(RatingModel):
    '''
    A simple container for a complete backup of Rating.
    
    Used when doing a full rebuild of ratings so as to have the previous copy on hand, and to be able to
    compare to see what the impact of the rebuild was. This can be very relevant if rebuilding because of
    a change to TrueSkill settings for example, when tuning the settings for particular games.
    
    # TODO: Put an option on the leaderboards view to see the Backup leaderboards, and another to show a comparison
    '''
    pass

class League(AdminModel):
    '''
    A group of Players who are competing at Games which have a Leaderboard of Ratings.

    Leagues operate independently of one another, meaning that
    when Sessions are recorded, only the Locations, Players and Games will appear on selectors.

    All Leagues share the same global and game Trueskill settings, so that a
    meaningful global leaderboard can be reported for any game across all leagues.
    '''
    name = models.CharField('Name of the League', max_length=MAX_NAME_LENGTH, validators=[RegexValidator(regex=f'^{ALL_LEAGUES}$', message=f'{ALL_LEAGUES} is a reserved league name', code='reserved', inverse_match=True)])
    
    manager = models.ForeignKey('Player', verbose_name='Manager', related_name='leagues_managed', null=True, on_delete=models.SET_NULL)

    locations = models.ManyToManyField('Location', verbose_name='Locations', blank=True, related_name='leagues_playing_here')
    players = models.ManyToManyField('Player', verbose_name='Players', blank=True, related_name='member_of_leagues')
    games = models.ManyToManyField('Game', verbose_name='Games', blank=True, related_name='played_by_leagues')

    # TODO: Use @cached_property (everywhere)
    @property
    def leaderboards(self) -> list:
        '''
        The leaderboards for this league.
        
        Returns a dictionary of ordered lists of (player,rating, plays) tuples, keyed on game. 
        
        The leaderboards for a specific game are available through the Game.leaderboard method
        '''
        return self.leaderboard()

    @property
    def link_internal(self) -> str:
        return reverse_lazy('view', kwargs={"model":self._meta.model.__name__,"pk": self.pk})

    @property_method
    def leaderboard(self, game=None):
        '''
        Return an ordered list of (player, rating, plays, victories) tuples that represents 
        the leaderboard for a specified game or if no game is provided, a dictionary of such 
        lists keyed on game.
        
        # TODO: consider as_at support
        '''
        if game is None:
            lb = {}
            games = Game.objects.filter(leagues=self)
            for game in games:
                lb[game] = self.leaderboard(game)                
        else:
            ratings = Rating.objects.filter(player__leagues=self, game=game)
        
            lb = []
            for r in ratings:
                lb.append((str(r.player), r.trueskill_eta, r.plays, r.victories))
                
        return lb
        
    selector_field = "name"
    @classmethod    
    def selector_queryset(cls, query="", session={}, all=False):
        '''
        Provides a queryset for ModelChoiceFields (select widgets) that ask for it.        
        :param cls: Our class (so we can build a queryset on it to return)
        :param q: A simple string being a query that is submitted (typically typed into a django-autcomplete-light ModelSelect2 or ModelSelect2Multiple widget)
        :param s: The request session (if there's a filter recorded there we honor it)
        '''
        qs = cls.objects.all()

        if not all:
            league = session.get('filter',{}).get('league', None)
            if league:
                # TODO: It's a bit odd to filter leagues on league. Might consider instead to filter
                #       one related leagues, that is the more complex question, for a selected league,
                #       itself and all leagues that share one or players with this league. These are
                #       conceivably related fields.
                qs = qs.filter(pk=league)
        
        if query:
            qs = qs.filter(**{f'{cls.selector_field}__istartswith': query})
        
        return qs
    
    add_related = None
    
    def __unicode__(self): return getattr(self, self.selector_field)
    def __str__(self): return self.__unicode__()
    def __verbose_str__(self): 
        return u"{} (manager: {})".format(self, self.manager)
    def __rich_str__(self,  link=None): 
        return u"{} (manager: {})".format(field_render(self, link), field_render(self.manager, link))
    def __detail_str__(self,  link=None):
        detail = self.__rich_str__(link)
        detail += "<UL>"
        for p in self.players.all():
            detail += "<LI>{}</LI>".format(field_render(p, link))
        detail += "</UL>"
        return detail

    class Meta(AdminModel.Meta):
        ordering = ['name']
        
class Team(AdminModel):
    '''
    A player team, which is defined when a team play game is recorded and needed to properly display a session as it was played,
    and to calculate team based TrueSkill ratings. Teams have no names just a list of players.

    Teams may have names but don't need them.
    '''
    name = models.CharField('Name of the Team (optional)', max_length=MAX_NAME_LENGTH, null=True)
    players = models.ManyToManyField('Player', verbose_name='Players', blank=True, editable=False, related_name='member_of_teams')

    @property
    def games_played(self) -> list:
        games = []
        for r in self.ranks.all():
            game = r.session.game
            if not game in games:
                games.append(game)
                
        return games

    @property
    def link_internal(self) -> str:
        return reverse_lazy('view', kwargs={"model":self._meta.model.__name__,"pk": self.pk})

    add_related = ["players"]
    def __unicode__(self):
        if self.name:
            return self.name
        else:
            return u", ".join([str(p) for p in self.players.all()])
    def __str__(self): return self.__unicode__()
    def __verbose_str__(self):
        name = self.name if self.name else "" 
        return name + u" (" + u", ".join([str(p) for p in self.players.all()]) + u")"
    
    def __rich_str__(self,  link=None):
        games = self.games_played
        if len(games) > 2:
            game_str = ", ".join(map(lambda g: field_render(g, link), games[0:1])) + "..."
        elif len(games) > 0:
            game_str = ", ".join(map(lambda g: field_render(g, link), games))
        else:
            game_str = html.escape("<No Game>")
        
        name = field_render(self.name, link_target_url(self, link)) if self.name else "" 
        return name + u" (" + u", ".join([field_render(p, link) for p in self.players.all()]) + u") for " + game_str 
        
    def __detail_str__(self,  link=None):
        if self.name: 
            detail = field_render(self.name, link_target_url(self, link))
        else:
            detail = html.escape("<Nameless Team>")

        games = self.games_played
        if len(games) > 2:
            game_str = ", ".join(map(lambda g: field_render(g, link), games[0:1])) + "..."
        elif len(games) > 0:
            game_str = ", ".join(map(lambda g: field_render(g, link), games))
        else:
            game_str = html.escape("<no game>")
            
        detail += " for " + game_str + "<UL>"
        for p in self.players.all():
            detail += "<LI>{}</LI>".format(field_render(p, link))
        detail += "</UL>"
        return detail

class Player(PrivacyMixIn, AdminModel):
    '''
    A player who is presumably collecting Ratings on Games and participating in leaderboards in one or more Leagues.

    Players can be Registrars, meaning they are permitted to record session results, or Staff meaning they can access the admin site.
    '''
    # Basic Player fields
    name_nickname = models.CharField('Nickname', max_length=MAX_NAME_LENGTH, unique=True)
    name_personal = models.CharField('Personal Name', max_length=MAX_NAME_LENGTH)
    name_family = models.CharField('Family Name', max_length=MAX_NAME_LENGTH)

    email_address = models.EmailField('Email Address', blank=True, null=True)
    BGGname = models.CharField('BoardGameGeek Name', max_length=MAX_NAME_LENGTH, default='', blank=True, null=True)  # BGG URL is https://boardgamegeek.com/user/BGGname
    
    # Privilege fields
    is_registrar = models.BooleanField('Authorised to record session results?', default=False)
    is_staff = models.BooleanField('Authorised to access the admin site?', default=False)

    # Membership fields
    teams = models.ManyToManyField('Team', through=Team.players.through, verbose_name='Teams', editable=False, related_name='players_in_team')  # Don't edit teams always inferred from Session submissions
    leagues = models.ManyToManyField('League', through=League.players.through, verbose_name='Leagues', blank=True, related_name='players_in_league')

    # A default or preferred league for each player. Optional. Can be used to customise views.
    league = models.ForeignKey(League, verbose_name='Preferred League', related_name="preferred_league_of", blank=True, null=True, default=None, on_delete=models.SET_NULL)

    # account
    user = models.OneToOneField(User, verbose_name='Username', related_name='player', blank=True, null=True, default=None, on_delete=models.SET_NULL)

    # Privacy control (interfaces with django_model_privacy_mixin)
    visibility = (
        ('all', 'Everyone'),
        ('share_leagues', 'League Members'),
        ('share_teams', 'Team Members'), 
        ('all_is_registrar', 'Registrars'), 
        ('all_is_staff', 'Staff'), 
    )
   
    visibility_name_nickname = BitField(visibility, verbose_name='Nickname Visibility', default=('all',), blank=True)
    visibility_name_personal = BitField(visibility, verbose_name='Personal Name Visibility', default=('all',), blank=True)
    visibility_name_family = BitField(visibility, verbose_name='Family Name Visibility', default=('share_leagues',), blank=True)
    visibility_email_address = BitField(visibility, verbose_name='Email Address Visibility', default=('share_leagues', 'share_teams'), blank=True)
    visibility_BGGname = BitField(visibility, verbose_name='BoardGameGeek Name Visibility', default=('share_leagues', 'share_teams'), blank=True)

    @property
    def owner(self) -> User:
        return self.user

    @property
    def full_name(self) -> str:
        return "{} {}".format(self.name_personal, self.name_family)

    @property
    def complete_name(self) -> str:
        return "{} {} ({})".format(self.name_personal, self.name_family, self.name_nickname)

    @property
    def games_played(self) -> list:
        '''
        Returns all the games that that this player has played
        '''
        games = Game.objects.filter((Q(sessions__ranks__player=self) | Q(sessions__ranks__team__players=self))).distinct()
        return None if (games is None or games.count() == 0) else games 

    @property
    def games_won(self) -> list:
        '''
        Returns all the games that that this player has won
        '''
        games = Game.objects.filter(Q(sessions__ranks__rank=1) & (Q(sessions__ranks__player=self) | Q(sessions__ranks__team__players=self))).distinct()
        return None if (games is None or games.count() == 0) else games 

    @property
    def last_plays(self) -> list:
        '''
        Returns the session of last play for each game played.
        '''
        sessions = {}
        played = [] if self.games_played is None else self.games_played
        for game in played:
            sessions[game] = self.last_play(game)
        return sessions

    @property
    def last_wins(self) -> list:
        '''
        Returns the session of last play for each game won.
        '''
        sessions = {}
        played = [] if self.games_played is None else self.games_played
        for game in played:
            lw = self.last_win(game)
            if not lw is None:
                sessions[game] = self.last_win(game)                
        return sessions

    # TODO add a Leaderboard property
    #    A method needs to take a league and game as input
    #    A property can return a list of lists, league, game, place on leaderboard

    @property
    def leaderboard_positions(self) -> list:
        '''
        Returns a dictionary of leagues, each value being a dictionary of games with a 
        value that is the leaderboard position this player holds on that league for 
        that game.
        '''
        positions = {}

        played = [] if self.games_played is None else self.games_played

        # Include a GLOBAL league only if this player is in more than one league, else
        # Global is identical to their one league anyhow. 
        multiple_leagues = self.leagues.all().count() > 1
        if multiple_leagues:
            positions[ALL_LEAGUES] = {}
            for game in played:
                positions[ALL_LEAGUES][game] = self.leaderboard_position(game)
        
        for league in self.leagues.all():
            positions[league] = {}
            for game in played:
                positions[league][game] = self.leaderboard_position(game, league)
        
        return positions

    @property
    def leaderboards_winning(self) -> list:
        '''        
        Returns a dictionary of leagues, each value being a list of games this player
        is winning the leaderboard on. 
        '''
        result = {}

        played = [] if self.games_played is None else self.games_played
        
        # Include a GLOBAL league only if this player is in more than one league, else
        # Global is identical to their one league anyhow. 
        multiple_leagues = self.leagues.all().count() > 1
        if multiple_leagues:
            result[ALL_LEAGUES] = []
            for game in played:
                if self.is_at_top_of_leaderbard(game):
                    result[ALL_LEAGUES].append(game)
        
        for league in self.leagues.all():
            result[league] = []
            for game in played:
                if self.is_at_top_of_leaderbard(game, league):
                    result[league].append(game)
        
        return result

    @property
    def link_internal(self) -> str:
        return reverse_lazy('view', kwargs={"model":self._meta.model.__name__,"pk": self.pk})
    
    @property
    def link_external(self) -> str:
        if self.BGGname and not 'BGGname' in self.hidden:
            return "https://boardgamegeek.com/user/{}".format(self.BGGname)
        else:
            return None

    def name(self, style):
        '''
        Renders the players name in a nominated style
        :param style: Supports "nick", "full", "complete", "flexi"
        
        flexi is a special request to return {pk, nick, full, complete} 
        empowering the caller to choose the name style later. This is
        ideally to allow a client to choose rendering in Javascript
        rather than fixing the rendering at server side.
        '''        
        # TODO: flexi has touse a delimeter that cannot be in a name and that should be enforced (names have them escaped
        return (self.name_nickname if style == "nick" 
           else self.full_name if style == "full" 
           else self.complete_name if style == "complete" 
           else f"{{{self.pk},{self.name_nickname},{self.full_name},{self.complete_name}}}" if style == "flexi" 
           else "Anonymous")

    def rating(self, game):
        '''
        Returns the Trueskill rating for this player at the specified game
        '''
        try:
            r = Rating.objects.get(player=self, game=game)
        except ObjectDoesNotExist:
            r = Rating.create(player=self, game=game)
        except MultipleObjectsReturned:
            raise ValueError("Database error: more than one rating for {} at {}".format(self.name_nickname, game.name))
        return r
    
    def leaderboard_position(self, game, leagues=[]):
        lb = game.leaderboard(leagues, simple=False)
        for entry in lb:
            if entry[1] == self.pk:
                return entry[0]
    
    def is_at_top_of_leaderbard(self, game, leagues=[]):
        return self.leaderboard_position(game, leagues) == 1
    
    def last_play(self, game):
        '''
        For a given game returns the session that represents the last time this player played that game.
        '''
        plays = Session.objects.filter(Q(game=game) & (Q(ranks__player=self) | Q(ranks__team__players=self))).order_by('-date_time')

        return NEVER if (plays is None or plays.count() == 0) else plays[0] 

    def last_win(self, game):
        '''
        For a given game returns the session that represents the last time this player won that game.
        '''
        plays = Session.objects.filter(Q(game=game) & Q(ranks__rank=1) & (Q(ranks__player=self) | Q(ranks__team__players=self))).order_by('-date_time')

        return NEVER if (plays is None or plays.count() == 0) else plays[0] 

    selector_field = "name_nickname"
    @classmethod
    def selector_queryset(cls, query="", session={}, all=False):
        '''
        Provides a queryset for ModelChoiceFields (select widgets) that ask for it.        
        :param cls: Our class (so we can build a queryset on it to return)
        :param q: A simple string being a query that is submitted (typically typed into a django-autcomplete-light ModelSelect2 or ModelSelect2Multiple widget)
        :param s: The request session (if there's a filter recorded there we honor it)
        '''
        qs = cls.objects.all()

        if not all:
            league = session.get('filter',{}).get('league', None)
            if league:
                # TODO: Should really respect s['filter_priorities'] as the list view does.
                qs = qs.filter(leagues=league)
        
        if query:
            qs = qs.filter(**{f'{cls.selector_field}__istartswith': query})

        qs = qs.annotate(play_count=Count('performances')).order_by("-play_count")
        
        return qs
    
    add_related = None
    
    def __unicode__(self): return getattr(self, self.selector_field)
    def __str__(self): return self.__unicode__()
    def __verbose_str__(self): 
        return u'{} {} ({})'.format(self.name_personal, self.name_family, self.name_nickname)
    
    def __rich_str__(self, link=None): 
        return u'{} - {}'.format(field_render(self.__verbose_str__(), link_target_url(self, link)), field_render(self.email_address, link if link == flt.none else flt.mailto))

    def __detail_str__(self,  link=None):
        detail = self.__rich_str__(link)
        
        lps = self.leaderboard_positions
        
        detail += "<BR>Leaderboard positions:<UL>"
        for league in lps:
            detail += "<LI>in League: {}</LI><UL>".format(field_render(league, link))
            for game in lps[league]:
                detail += "<LI>{}: {}</LI>".format(field_render(game, link), lps[league][game])
            detail += "</UL>"
        detail += "</UL>"
                
        return detail

    # TODO: clean() method to force test that player is in a league!
    class Meta(AdminModel.Meta):
        ordering = ['name_nickname']

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    formfield_overrides = { BitField: {'widget': BitFieldCheckboxSelectMultiple}, }
    
class Game(AdminModel):
    '''A game that Players can be Rated on and which has a Leaderboard (global and per League). Defines Game specific Trueskill settings.'''
    name = models.CharField('Name of the Game', max_length=200)
    BGGid = models.PositiveIntegerField('BoardGameGeek ID')  # BGG URL is https://boardgamegeek.com/boardgame/BGGid

    # Which play modes the game supports. This will decide the formats the session submission form supports
    individual_play = models.BooleanField('Supports individual play', default=True)
    team_play = models.BooleanField('Supports team play',default=False)

    # Player counts, also inform the session logging form how to render
    min_players = models.PositiveIntegerField('Minimum number of players', default=2)
    max_players = models.PositiveIntegerField('Maximum number of players', default=4)
    
    min_players_per_team = models.PositiveIntegerField('Minimum number of players in a team', default=2)
    max_players_per_team = models.PositiveIntegerField('Maximum number of players in a team', default=4)

    # Which leagues play this game? A way to keep the game selector focussed on games a given league actually plays. 
    leagues = models.ManyToManyField('League', verbose_name='Leagues', blank=True, related_name='games_played', through=League.games.through)

    # Game specific TrueSkill settings
    # tau: 0- describes the luck element in a game. 
    #      0 is a game of pure skill, 
    #        there is no upper limit. It is added to sigma after each re-reating (game session recorded)
    # p  : 0-1 describes the probability of a draw. It affects how far the mu of drawn players move toward 
    #        each other when a draw is recorded after each rating.
    #      0 means lots
    #      1 means not at all
    trueskill_beta = models.FloatField('TrueSkill Skill Factor (ß)', default=trueskill.BETA)
    trueskill_tau = models.FloatField('TrueSkill Dynamics Factor (τ)', default=trueskill.TAU)
    trueskill_p = models.FloatField('TrueSkill Draw Probability (p)', default=trueskill.DRAW_PROBABILITY)

    @property
    def global_sessions(self) -> list:
        '''
        Returns a list of sessions that played this game. Across all leagues.        
        '''
        return self.session_list()

    @property
    def league_sessions(self) -> dict:
        '''
        Returns a dictionary keyed on league, with a list of sessions that played this game as the value.        
        '''
        leagues = League.objects.all()
        sl = {}
        sl[ALL_LEAGUES] = self.session_list()
        for league in leagues:
            sl[league] = self.session_list(league)
        return sl

    @property
    def global_plays(self) -> dict:
        return self.play_counts()

    @property
    def league_plays(self) -> dict:
        '''
        Returns a dictionary keyed on league, of:
        the number of plays this game has experienced, as a dictionary containing:
            total: is the sum of all the individual player counts (so a count of total play experiences)
            max: is the largest play count of any player
            average: is the average play count of all players who've played at least once
            players: is a count of players who played this game at least once
            session: is a count of the number of sessions this game has been played
        '''
        leagues = League.objects.all() 
        pc = {}
        pc[ALL_LEAGUES] = self.play_counts()
        for league in leagues:
            pc[league] = self.play_counts(league)
        return pc

    @property
    def league_leaderboards(self) -> dict:
        '''
        The leaderboards for this game as a dictionary keyed on league 
        with the special ALL_LEAGUES holding the global leaderboard.

        Each leaderboard is an ordered list of (player,rating, plays) tuples 
        for the league.  
        '''
        leagues = League.objects.all()
        lb = {}
        lb[ALL_LEAGUES] = self.leaderboard()
        for league in leagues:
            lb[league] = self.leaderboard(league)
        return lb

    @property
    def global_leaderboard(self) -> list:
        '''
        The leaderboard for this game considering all leagues together, as a simple property of the game.
        
        Returns as an ordered list of (player,rating, plays) tuples 
        
        The leaderboard for a specific league is available through the leaderboard method.
        '''
        return self.leaderboard()

#     @property
#     def global_leaderboard2(self) -> dict:
#         '''
#         Should be same as global_leaderboards but by another means. A test of the query only
#         '''
#         leagues = list(League.objects.all().values_list('pk', flat=True))
#         return self.leaderboard(leagues)
   
    @property
    def link_internal(self) -> str:
        return reverse_lazy('view', kwargs={"model":self._meta.model.__name__,"pk": self.pk})
    
    @property
    def link_external(self) -> list:
        if self.BGGid:
            return "https://boardgamegeek.com/boardgame/{}".format(self.BGGid)
        else:
            return None
    
    @property_method
    def last_performances(self, leagues=[], players=[], asat=None) -> object:
        '''
        Returns the last performances at this game (optionally as at a given date time) for
        a player or all players in specified leagues or all players in all leagues (if no 
        leagues specified). 
        
        Returns a Performance queryset. 
        
        :param leagues:The league or leagues to consider when finding the last_performances. All leagues considered if none specified.
        :param player: The player or players to consider when finding the last_performances. All players considered if none specified.
        :param asat: Optionally, the last performance as at this date/time
        '''
        pfilter = Q(session__game=self) 
        if leagues:
            pfilter &= Q(player__leagues__in=leagues)
        if players:
            pfilter &= Q(player__in=players)
        if not asat is None:
            pfilter &= Q(session__date_time__lte=asat)
        
        # Aggregate for max date_time for a given player. That is we want a Performance 
        # per player, the one with the greatest date_time (that is before asat if specified) 
        
        pfilter = Q(
            session__date_time=Subquery(
                (Performance.objects
                    .filter(Q(player=OuterRef('player')) & pfilter)
                    .values('player')
                    .annotate(max_date=Max('session__date_time'))
                    .values('max_date')[:1]
                ), output_field=models.DateField()
            )
        )
        
        return Performance.objects.filter(pfilter).order_by('-trueskill_eta_after')

    @property_method
    def session_list(self, leagues=[], asat=None) -> list:
        '''
        Returns a list of sessions that played this game. Useful for counting or traversing.

        Such a list is returned for the specified league or leagues or for all leagues if 
        none are specified.
        
        Optionally can provide the list of sessions played as at a given date time. 
        
        :param leagues: Returns sessions played considering the specified league or leagues or all leagues if none is specified.
        :param asat: Optionally returns the sessions played as at a given date
        '''
        # If a single league was provided make a list with one entry.
        if not isinstance(leagues, list):
            if leagues:
                leagues = [leagues]
            else:
                leagues = []

        # We can accept leagues as League instances or PKs but want a PK list for the queries.
        for l in range(0, len(leagues)):
            if isinstance(leagues[l], League):
                leagues[l] = leagues[l].pk
            elif not ((isinstance(leagues[l], str) and leagues[l].isdigit()) or isinstance(leagues[l], int)):
                raise ValueError(f"Unexpected league: {leagues[l]}.")

        if asat is None:
            if leagues:
                return Session.objects.filter(game=self, league__in=leagues)
            else:    
                return Session.objects.filter(game=self)
        else:
            if leagues:
                return Session.objects.filter(game=self, league__in=leagues, date_time__lte=asat)
            else:    
                return Session.objects.filter(game=self, date_time__lte=asat)

    @property_method
    def play_counts(self, leagues=[], asat=None) -> list:
        '''
        Returns the number of plays this game has experienced, as a dictionary containing:
            total:    is the sum of all the individual player counts (so a count of total play experiences)
            max:      is the largest play count of any player
            average:  is the average play count of all players who've played at least once
            players:  is a count of players who played this game at least once
            sessions: is a count of the number of sessions this game has been played
        
        leagues can be a single league (a pk) or a list of leagues (pks).        
        We always return the playcount across all the listed leagues.
        
        If no leagues are specified returns the play_counts for all leagues.
      
        Optionally can provide the count of plays as at a given date time as well. 

        :param leagues: Returns playcounts considering the specified league or leagues or all leagues if none is specified.
        :param asat: Optionally returns the play counts as at a given date
        '''
        # If a single league was provided make a list with one entry.
        if not isinstance(leagues, list):
            if leagues:
                leagues = [leagues]
            else:
                leagues = []

        # We can accept leagues as League instances or PKs but want a PK list for the queries.
        for l in range(0, len(leagues)):
            if isinstance(leagues[l], League):
                leagues[l] = leagues[l].pk
            elif not ((isinstance(leagues[l], str) and leagues[l].isdigit()) or isinstance(leagues[l], int)):
                raise ValueError(f"Unexpected league: {leagues[l]}.")
            
        if asat is None:
            if leagues:
                ratings = Rating.objects.filter(game=self, player__leagues__in=leagues)
            else:
                ratings = Rating.objects.filter(game=self)

            pc = ratings.aggregate(total=Sum('plays'), max=Max('plays'), average=Avg('plays'), players=Count('plays'))
            for key in pc:
                if pc[key] is None:
                    pc[key] = 0
                    
            pc['sessions'] = self.session_list(leagues).count()
        else:
            # Can't use the Ratings model as that stores current ratings (and play counts). Instead use the Performance
            # model which records ratings (and play counts) after every game session and the sessions have a date/time
            # so the information can be extracted therefrom.
            if leagues:
                performances = self.last_performances(leagues=leagues, asat=asat)
            else:
                performances = self.last_performances(asat=asat)

            # The play_number of the last performance is the play count at that time.
            pc = performances.aggregate(total=Sum('play_number'), max=Max('play_number'), average=Avg('play_number'), players=Count('play_number'))
            for key in pc:
                if pc[key] is None:
                    pc[key] = 0
                    
            pc['sessions'] = self.session_list(leagues, asat=asat).count()
                
        return pc

    @property_method
    def leaderboard(self, leagues=[], asat=None, names="nick", simple=True) -> list:
        '''
        Return an ordered list of (player, rating, plays, victories) tuples that represents the leaderboard for 
        specified leagues, or for all leagues if None is specified. As at a given date/time if such is specified,
        else, as at now (latest or current, leaderboard).
        
        :param leagues:   Show only players in any of these leagues if specified, else in any league (a single league or a list of leagues)
        :param asat:      Show the leaderboard as it was at this time rather than now, if specified
        :param names:     Specifies how names should be rendered in the leaderboard, one of the Player.name() options. 
        :param simple     Defaults to Tue and is designed for the simple property method and a simple view
                          of a games leaderboard.
                          
                          if False a more complex tuple is returned on each row of the board empowering
                          the caller and a view to do some filtering with the data provided.
                          Designed for use by a leaderboard view that wants to 
                                present leaderboards with links to player info (on-site - PK, or at BGG)
                                present the mu and sigma in a ToolTip or other annotation
                                present alternate name formats (default tupe has complete, we include nick and full in prepend).
                                filter player lists based on activity (last_play) or league membership (league PKs).
                          If annotated is requested we ignore leaques and names (filtering and name renderig handled by caller) 
        '''  
        # If a single league was provided make a list with one entry.
        if not isinstance(leagues, list):
            if leagues:
                leagues = [leagues]
            else:
                leagues = []                

        print_debug(f"\t\tBuilding leaderboard for {self.name}.")
                
        # If a complex  leaderboard is requested we ignore "names" and the caller
        # must perform name formatting (we provide all formats in the tuple). But 
        # we ignore it vehemently, it's a programming error to invoke this method 
        # with "names" and not simple ...
        if not simple and names != "nick":
            raise ArgumentError("Game.leaderboards requested with annotations. Expected no names submitted but got: {names}")                        
            
        # We can accept leagues as League instances or PKs but want a PK list for the queries.
        for l in range(0, len(leagues)):
            if isinstance(leagues[l], League):
                leagues[l] = leagues[l].pk
            elif not ((isinstance(leagues[l], str) and leagues[l].isdigit()) or isinstance(leagues[l], int)):
                raise ValueError(f"Unexpected league: {leagues[l]}.")

        print_debug(f"\t\tValidated leagues")
            
        if asat:
            # Build leaderboard as at a given time as specified
            # Can't use the Ratings model as that stores current ratings. Instead use the Performance
            # model which records ratings after every game session and the sessions have a date/time
            # so the information can be extracted therefrom. These are returned in order -eta as well
            # so in the right order for a leaderboard (descending skill rating)
            if leagues:
                # Get the last performances for all players in the specified leagues
                ratings = self.last_performances(leagues=leagues, asat=asat) 
            else:
                # Get the last performances for all players in all leagues
                ratings = self.last_performances(asat=asat)
        else:
            # If leagues are specified we don't want to see people from other leagues
            # on this leaderboard, only players from the nominated leagues.  
            lb_filter = Q(game=self)
            if leagues:
                # TODO: FIXME: This is bold. player__leagues is a set, and leagues is a set
                # Does this yield the intersection or not?
                lb_filter = lb_filter & Q(player__leagues__in=leagues)
                
            # These come pre-sorted by -eta (so in the right order for the leaderboard).
            # (descending skill rating). The Rating model ensures this
            ratings = Rating.objects.filter(lb_filter).distinct()        
                 
        print_debug(f"\t\tBuilt ratings queryset.")
        
        # Now build a leaderboard from all the ratings for players (in this league) at this game. 
        lb = []
        for i, r in enumerate(ratings):
            # r may be a Rating object or a Performance object. They both have a player
            # but other metadata is specific. So we fetch them based on their accessibility
            if isinstance(r, Rating):
                trueskill_eta = r.trueskill_eta
                trueskill_mu = r.trueskill_mu
                trueskill_sigma = r.trueskill_sigma
                plays = r.plays
                victories = r.victories
                last_play = r.last_play               # TODO: last_play_tz? 
            elif isinstance(r, Performance):
                trueskill_eta = r.trueskill_eta_after
                trueskill_mu = r.trueskill_mu_after
                trueskill_sigma = r.trueskill_sigma_after
                plays = r.play_number
                victories = r.victory_count
                last_play = r.session.date_time       # TODO: date_time_tz?   
            else:
                raise ValueError(f"Progamming error in Game.leaderboard().")
            
            if simple:
                lb_entry = (r.player.name(names), trueskill_eta, plays, victories) 
            else:
                lb_entry = (i+1,
                            r.player.pk, 
                            r.player.BGGname, 
                            r.player.name('nick'), 
                            r.player.name('full'),
                            r.player.name('complete'),
                            trueskill_eta, 
                            trueskill_mu, 
                            trueskill_sigma, 
                            plays, 
                            victories,                                
                            last_play, 
                            [l.pk for l in r.player.leagues.all()])
            lb.append(lb_entry)

        print_debug(f"\t\tBuilt leaderboard.")
                            
        return None if len(lb) == 0 else lb

    def rating(self, player, asat=None):
        '''
        Returns the Trueskill rating for this player at the specified game
        '''
        
        if asat is None:
            try:
                r = Rating.objects.get(player=player, game=self)
            except ObjectDoesNotExist:
                r = Rating.create(player=player, game=self)
            except MultipleObjectsReturned:
                raise ValueError("Database error: more than one rating for {} at {}".format(player.name_nickname, self.name))
            return r
        else:
            # Use the Performance model (and time stamped associated sessions_ to construct 
            # a rating object as at a specific date/time
            # TODO: Implement
            pass  

    selector_field = "name"
    @classmethod    
    def selector_queryset(cls, query="", session={}, all=False):
        '''
        Provides a queryset for ModelChoiceFields (select widgets) that ask for it.        
        :param cls: Our class (so we can build a queryset on it to return)
        :param q: A simple string being a query that is submitted (typically typed into a django-autcomplete-light ModelSelect2 or ModelSelect2Multiple widget)
        :param s: The request session (if there's a filter recorded there we honor it)
        '''
        qs = cls.objects.all()

        if not all:
            league = session.get('filter',{}).get('league', None)
            if league:
                qs = qs.filter(leagues=league)         
        
        if query:
            # TODO: Should really respect s['filter_priorities'] as the list view does.
            qs = qs.filter(**{f'{cls.selector_field}__istartswith': query})

        qs = qs.annotate(play_count=Count('sessions')).order_by("-play_count")
               
        return qs
            
    add_related = None

    def __unicode__(self): return getattr(self, self.selector_field)
    def __str__(self): return self.__unicode__()
    def __verbose_str__(self): 
        return u'{} (plays {}-{})'.format(self.name, self.min_players, self.max_players)    

    def __rich_str__(self, link=None): 
        name = field_render(self.name, link_target_url(self, link))
        pmin = self.min_players
        pmax = self.max_players
        beta = self.trueskill_beta
        tau = self.trueskill_tau*100
        p = int(self.trueskill_p*100)
        return u'{} (plays {}-{}), Skill factor: {:0.2f}, Draw probability: {:d}%, Skill dynamics factor: {:0.2f}'.format(name, pmin, pmax, beta, p, tau)

    def __detail_str__(self,  link=None):
        detail = self.__rich_str__(link)
        
        plays = self.league_plays
        
        detail += "<BR>Play counts:<UL>"
        for league in plays:
            if league == ALL_LEAGUES:
                # Don't show the global count if there's only one league!
                if len(plays) > 2:
                    league_str = "across all leagues."
                else:
                    league_str = ""
            else:
                league_str = "in League: {}".format(field_render(league, link)) 
                
            if league_str:
                detail += "<LI>{} plays and {} players {}</LI>".format(plays[league]['sessions'], plays[league]['players'],league_str)
        detail += "</UL>"
                
        return detail

    class Meta(AdminModel.Meta):
        ordering = ['name']

class Location(AdminModel):
    '''
    A location that a game session can take place at.
    '''
    name = models.CharField('Name of the Location', max_length=MAX_NAME_LENGTH)    
    timezone = TimeZoneField('Timezone of the Location', default=settings.TIME_ZONE)
    leagues = models.ManyToManyField(League, verbose_name='Leagues using the Location', blank=True, related_name='Locations_used', through=League.locations.through)

    @property
    def link_internal(self) -> str:
        return reverse_lazy('view', kwargs={"model":self._meta.model.__name__,"pk": self.pk})

    selector_field = "name"
    @classmethod    
    def selector_queryset(cls, query="", session={}, all=False):
        '''
        Provides a queryset for ModelChoiceFields (select widgets) that ask for it.        
        :param cls: Our class (so we can build a queryset on it to return)
        :param q: A simple string being a query that is submitted (typically typed into a django-autcomplete-light ModelSelect2 or ModelSelect2Multiple widget)
        :param s: The request session (if there's a filter recorded there we honor it)
        '''
        qs = cls.objects.all()

        if not all:
            league = session.get('filter',{}).get('league', None)
            if league:
                # TODO: Should really respect s['filter_priorities'] as the list view does.
                qs = qs.filter(leagues=league)
        
        if query:
            qs = qs.filter(**{f'{cls.selector_field}__istartswith': query})
        
        return qs
    
    add_related = None

    def __unicode__(self): return getattr(self, self.selector_field)
    def __str__(self): return self.__unicode__()
    def __verbose_str__(self): 
        return u"{} (used by: {})".format(self.__str__(), ", ".join(list(self.leagues.all().values_list('name', flat=True))))
    def __rich_str__(self,  link=None):
        leagues = list(self.leagues.all())
        leagues = list(map(lambda l: field_render(l, link), leagues))
        return u"{} (used by: {})".format(field_render(self, link), ", ".join(leagues))

    class Meta(AdminModel.Meta):
        ordering = ['name']

class Session(TimeZoneMixIn, AdminModel):
    '''
    The record, with results (Ranks), of a particular Game being played competitively.
    '''
    date_time = models.DateTimeField('Time', default=timezone.now)                                          # When the game session was played
    date_time_tz = TimeZoneField('Timezone', default=settings.TIME_ZONE, editable=False)
    
    league = models.ForeignKey(League, verbose_name='League', related_name='sessions', null=True, on_delete=models.SET_NULL)       # The league playing this session
    location = models.ForeignKey(Location, verbose_name='Location', related_name='sessions', null=True, on_delete=models.SET_NULL)   # Where the game sessions was played
    game = models.ForeignKey(Game, verbose_name='Game', related_name='sessions', null=True, on_delete=models.SET_NULL)           # The game that was played
    
    # The game must support team play if this is true, 
    # and conversely, it must support individual play if this false.
    # TODO: Enforce this constraint
    # TODO: Let the session form know the modes supported so it can enable/disable the entry modes
    team_play = models.BooleanField('Team Play', default=False)  # By default games are played by individuals, if true, this session was played by teams
    
    # A note on session player records:
    #  Players are stored in two distinct places/contexts:
    #    1) In the Performance model - which records each players TrueSkill performance in this session
    #    2) in the Rank model - which records each player or teams rank (placement in the results)
    #
    # The simpler list of players in a sessions is in the Performance model where each player in each session has performance recorded.
    #
    # A less direct record of the players in a  sessionis in the Rank model, 
    #     either one player per Rank (in an Individual play session) or one Team per rank (in a Team play session)
    #     This is because ranks are associated with players in individual play mode but teams in Team play mode, 
    #     while performance is always tracked by player.

    # TODO: consider if we can filter on properties or specify annotations somehow to filter on
    filter_options = ['date_time__gt', 'date_time__lt', 'league', 'game']
    order_options = ['date_time', 'game', 'league']

    # Two equivalent ways of specifying the related forms that django-generic-view-extensions supports:
    # Am testing the new simpler way now leaving it in place for a while to see if any issues arise.
    #add_related = ["Rank.session", "Performance.session"]  # When adding a session, add the related Rank and Performance objects    
    add_related = ["ranks", "performances"]  # When adding a session, add the related Rank and Performance objects
    
    # Specify which fields to inherit from entry to entry when creating a string of objects
    inherit_fields = ["date_time", "league", "location", "game"]
    inherit_time_delta = timedelta(minutes=90)

    @property
    def num_competitors(self) -> int:
        '''
        Returns an integer count of the number of competitors in this game session,
        i.e. number of players in a single-player mode or number of teams in team player mode
        '''
        if self.team_play:
            return len(self.teams)
        else:
            return len(self.players)

    @property
    def str_competitors(self) -> str:
        '''
        Returns a simple string to append to a number which represents the "competitors"
        That is, "team", "teams", "player", or "players" as appropriate. A 1 player
        game is a solo game clearly.
        '''
        n = self.num_competitors
        if self.team_play:
            if n == 1:
                return "team"
            else:
                return "teams"
        else:
            if n == 1:
                return "player"
            else:
                return "players"

    @property
    def ranked_players(self) -> dict:
        '''
        Returns an OrderedDict (keyed on rank) of the players in the session.
        The value is either a player (for individual play sessions) or 
            a list of players (in team play sessions)
            
        Note ties have the same rank, so the key has a .index appended,
        to form a unique key. Only the key digits up to the . represent 
        the true rank, the full key permits sorting and unique storage 
        in a dictionary.
        '''
        players = OrderedDict()
        ranks = Rank.objects.filter(session=self.id)
        
        # a quick loop through to check for ties as they will demand some
        # special handling when we collect the list of players into the 
        # keyed (by rank) dictionary.
        rank_counts = OrderedDict()  
        rank_id = OrderedDict()  
        for rank in ranks:
            # rank is the rank object, rank.rank is the integer rank (1, 2, 3).
            if rank.rank in rank_counts:
                rank_counts[rank.rank] += 1
                rank_id[rank.rank] = 1
            else:
                rank_counts[rank.rank] = 1
        
        for rank in ranks:
            # rank is the rank object, rank.rank is the integer rank (1, 2, 3).
            if self.team_play:
                if rank_counts[rank.rank] > 1:
                    pid = 1
                    for player in rank.players:
                        players["{}.{}.{}".format(rank.rank, rank_id[rank.rank], pid)] = player
                        pid += 1
                    rank_id[rank.rank] += 1
                else:
                    pid = 1
                    for player in rank.players:
                        players["{}.{}".format(rank.rank, pid)] = player
                        pid += 1                    
            else:
                # The players can be listed (indexed) in rank order. 
                # When there are multiple players at the same rank (ties)
                # We use a decimal format of rank.person to ensure that 
                # the sorting remains more or less sensible.
                if rank_counts[rank.rank] > 1:
                    players["{}.{}".format(rank.rank, rank_id[rank.rank])] = rank.player
                    rank_id[rank.rank] += 1
                else: 
                    players["{}".format(rank.rank)] = rank.player
        return players

    @property
    def players(self) -> set:
        '''
        Returns an unordered set of the players in the session, with no guaranteed 
        order. Useful for traversing a list of all players in a session
        irrespective of the structure of teams or otherwise.
        
        '''
        players = set()
        performances = Performance.objects.filter(session=self.pk)
        
        for performance in performances:
            players.add(performance.player)
                
        return players

    @property
    def teams(self) -> dict:
        '''
        Returns an OrderedDict (keyed on rank) of the teams in the session.
        The value is a list of players (in team play sessions)
        Returns an empty dictionary for Individual play sessions
        
        Note ties have the same rank, so the key has a .index appended,
        to form a unique key. Only the key digits up to the . represent 
        the true rank, the full key permits sorting and inique storage 
        in a dictionary.
        '''
        teams = OrderedDict()
        if self.team_play:
            ranks = Rank.objects.filter(session=self.id)

            # a quick loop through to check for ties as they will demand some
            # special handling when we collect the list of players into the 
            # keyed (by rank) dictionary.
            rank_counts = OrderedDict()  
            rank_id = OrderedDict()  
            for rank in ranks:
                # rank is the rank object, rank.rank is the integer rank (1, 2, 3).
                if rank.rank in rank_counts:
                    rank_counts[rank.rank] += 1
                    rank_id[rank.rank] = 1
                else:
                    rank_counts[rank.rank] = 1
                        
            for rank in ranks:
                # The players can be listed (indexed) in rank order. 
                # When there are multiple players at the same rank (ties)
                # We use a decimal format of rank.person to ensure that 
                # the sorting remains more or less sensible.
                if rank_counts[rank.rank] > 1:
                    teams["{}.{}".format(rank.rank, rank_id[rank.rank])] = rank.team
                    rank_id[rank.rank] += 1
                else: 
                    teams["{}".format(rank.rank)] = rank.team
        return teams

    @property
    def victors(self) -> list:
        '''
        Returns the victors, a list of players or teams. Plural because of possible draws.
        '''
        victors = []
        ranks = Rank.objects.filter(session=self.id)

        for rank in ranks:
            # rank is the rank object, rank.rank is the integer rank (1, 2, 3).
            if self.team_play:
                if rank.rank == 1:
                    victors.append(rank.team)
            else:
                if rank.rank == 1:
                    victors.append(rank.player)
        return victors
    
    @property
    def trueskill_impacts(self) -> dict:
        '''
        Returns the recorded trueskill impacts of this session.
        Does not (re)calculate them, reads the recorded Performance
        '''
        players_left = self.players
        
        impact = OrderedDict()
        for performance in self.performances.all():
            if performance.player in players_left:
                players_left.discard(performance.player)
            else:
                raise IntegrityError("Integrity error: Session has a player performance without a matching rank. Session id: {}, Performance id: {}".format(self.id, performance.id))
            
            impact[performance.player] = OrderedDict([
                ('plays', performance.play_number),
                ('victories', performance.victory_count),
                ('last_play', performance.session.date_time),
                ('last_victory', performance.session.date_time if performance.is_victory else performance.rating.last_victory),
                ('delta', OrderedDict([
                            ('mu', performance.trueskill_mu_after - performance.trueskill_mu_before),
                            ('sigma', performance.trueskill_sigma_after - performance.trueskill_sigma_before),
                            ('eta', performance.trueskill_eta_after - performance.trueskill_eta_before)
                            ])),
                ('after', OrderedDict([
                            ('mu', performance.trueskill_mu_after),
                            ('sigma', performance.trueskill_sigma_after),
                            ('eta', performance.trueskill_eta_after)
                            ])),
                ('before', OrderedDict([
                            ('mu', performance.trueskill_mu_before),
                            ('sigma', performance.trueskill_sigma_before),
                            ('eta', performance.trueskill_eta_before)
                            ]))
            ])
            
        assert len(players_left) == 0, "Integrity error: Session has ranked players without a matching performance. Session id: {}, Players: {}".format(self.id, players_left) 
        
        return impact

    @property
    def trueskill_code(self) -> str:
        '''
        A debugging property that prints python code that will replicate this trueskill calculation
        So that this specific trueksill calculation might be diagnosed and debugged in isolation.
        '''
        TSS = TrueskillSettings()
        OldRatingGroups, Weights, Ranking = self.build_trueskill_data() 

        code = []
        code.append("<pre>#!/usr/bin/python3")
        code.append("import trueskill")
        code.append("mu0 = {}".format(TSS.mu0))
        code.append("sigma0 = {}".format(TSS.sigma0))
        code.append("delta = {}".format(TSS.delta))
        code.append("beta = {}".format(self.game.trueskill_beta))
        code.append("tau = {}".format(self.game.trueskill_tau))
        code.append("p = {}".format(self.game.trueskill_p))
        code.append("TS = trueskill.TrueSkill(mu=mu0, sigma=sigma0, beta=beta, tau=tau, draw_probability=p)")
        code.append("oldRGs = {}".format(str(OldRatingGroups)))
        code.append("Weights = {}".format(str(Weights)))
        code.append("Ranking = {}".format(str(Ranking)))
        code.append("newRGs = TS.rate(oldRGs, Ranking, Weights, delta)")
        code.append("print(newRGs)")
        code.append("</pre>")
        return "\n".join(code)

    def _get_future_sessions(self, sessions_so_far):
        '''
        Internal support for the future_session property, this is a recursive method
        that takes a list of sessions found so far so as to avoid duplicating any 
        sessions in the search.
        
        sessions_so_far: A list of sessions found so far, that is augmented  and returned
        '''
        # We want session in the future only of course
        dfilter = Q(date_time__gt=self.date_time)
        
        # We want only sessions for this sessions game
        gfilter = Q(game=self.game)
        
        # For each player we find all future sessions playing this game
        pfilter = Q(ranks__player__in=self.players) | Q(ranks__team__players__in=self.players)
            
        # Combine the filters
        filters = dfilter & gfilter & pfilter
        
        # Get the list of PKs to exclude
        exclude_pks = list(map(lambda s: s.pk, sessions_so_far))
            
        new_future_sessions = Session.objects.filter(filters).exclude(pk__in=exclude_pks).distinct().order_by('date_time')
        
        if new_future_sessions.count() > 0:
            # augment sessions_so far
            sessions_so_far += list(new_future_sessions)
              
            # The new future sessions may involve new players which 
            # requires that we scan them for new future sessions too 
            for session in new_future_sessions:
                new_sessions_so_far = session._get_future_sessions(sessions_so_far)
                
                if len(new_sessions_so_far) > len(sessions_so_far):
                    sessions_so_far = sorted(new_sessions_so_far, key=lambda s: s.date_time)

        return sessions_so_far                
        
    @property
    def future_sessions(self) -> list:
        '''
        Returns the sessions ordered by date_time that are in the future relative to this session
        that involve any of the players in this session, or players in those sessions.
        
        Namely every session that needs to be re-evaluated because this one has been inserted before
        it, or edited in some way. 
        '''
        return self._get_future_sessions([])

    @property
    def link_internal(self) -> str:
        return reverse_lazy('view', kwargs={"model":self._meta.model.__name__,"pk": self.pk})

    @property
    def actual_ranking(self) -> list:
        '''
        Returns a list of ranks in the order they ranked
        '''
        # Ranks.performance returns a (mu, sigma) tuple for the rankers
        # TrueSkill modelled performance. And the expected ranking is
        # ranking by expected performance which is mu of the performance.
        rankers = sorted(self.ranks.all(), key=lambda r: r.rank)
        return rankers

    @property
    def predicted_ranking(self) -> tuple:
        '''
        Returns a list of ranks in the predicted order as the first
        element in a tuple.
        
        The second is the probability associated with that prediction.
        
        TODO: This should really be in the trueskill package
        '''
        # Rank.performance returns a (mu, sigma) tuple for the ranker
        # TrueSkill modeled performance. And the expected ranking is
        # ranking by expected performance which is mu of the performance.
        rankers = sorted(self.ranks.all(), key=lambda r: r.performance[0], reverse=True)
        
        # TODO: This should be in the trueskill package
        # See my doc "Understanding Trueskill" for the math on this
        prob = 1
        for r in range(len(rankers)-1): 
            perf1 = rankers[r].performance
            perf2 = rankers[r+1].performance
            x = (perf1[0] - perf2[0] - trueskill.DELTA) / (perf1[1]**2 + perf2[1]**2)**0.5
            p = norm.cdf(x)
            prob *= p            
        
        return (rankers, prob)

    @property
    def predicted_ranking_after(self) -> tuple:
        '''
        Returns a list of ranks in the predicted order after this session as the first
        element in a tuple.
        
        The second is the probability associated with that prediction.
        
        TODO: This should really be in the trueskill package
        '''
        # Ranks.performance returns a (mu, sigma) tuple for the rankers
        # TrueSkill modeled performance. And the expected ranking is
        # ranking by expected performance which is mu of the performance.
        rankers = sorted(self.ranks.all(), key=lambda r: r.performance_after[0], reverse=True)
        
        # TODO: This should be in the trueskill package
        # See my doc "Understanding Trueskill" for the math on this
        prob = 1
        for r in range(len(rankers)-1):
            perf1 = rankers[r].performance
            perf2 = rankers[r+1].performance
            x = (perf1[0] - perf2[0] - trueskill.DELTA) / (perf1[1]**2 + perf2[1]**2)**0.5
            p = norm.cdf(x)
            prob *= p            
        
        return (rankers, prob)
                            
    @property
    def relationships(self) -> set:
        '''
        Returns a list of tuples containing player or team pairs representing 
        each ranker (contestant) relationship in the game.
        
        Tuples always ordered (victor, loser) except on draws in which case arbitrary.       
        '''
        ranks = self.ranks.all()
        relationships = set()
        # Not the most efficient walk but a single game has a comparatively small 
        # number of rankers (players or teams ranking) and efficiency not a drama
        # More efficient would be not rewalk walked ground (i.e second loop only has
        # to go from outer loop index up to end.
        for rank1 in ranks:
            for rank2 in ranks:
                if rank1 != rank2:
                    relationship = (rank1.ranker, rank2.ranker) if rank1.rank < rank2.rank else (rank2.ranker, rank1.ranker)
                    if not relationship in relationships:
                        relationships.add(relationship)
        
        return relationships            

    @property
    def player_relationships(self) -> set:
        '''
        Returns a list of tuples containing player pairs representing each player relationship 
        in the game. Sale as self.relationships() in individual play mode, differs onl in team 
        mode in that it find all the player relationships and ignores team relationships.
        
        Tuples always ordered (victor, loser) except on draws in which case arbitrary.       
        '''
        performances = self.performances.all()
        relationships = set()
        # Not the most efficient walk but a single game has a comparatively small 
        # number of rankers (players or teams ranking) and efficiency not a drama
        # More efficient would be not rewalk walked ground (i.e second loop only has
        # to go from outer loop index up to end.
        for performance1 in performances:
            for performance2 in performances:
                # Only need relationships where 1 beats 2 or there's a draw
                if performance1.rank <= performance2.rank and performance1.player != performance2.player:
                    relationship = (performance1.player, performance2.player)
                    back_relationship = (performance2.player, performance1.player)
                    if not back_relationship in relationships:
                        relationships.add(relationship)
        
        return relationships                    
             
    def _prediction_quality(self, after=False) -> int:
        '''
        Returns a measure of the prediction quality that TrueSkill rankings
        provided. A number from 0 to 1. 0 being got it all wrong, 1 being got 
        it all right. 
        '''
        def dictify(ordered_ranks):
            '''
            Give a list of ranks in any order will return a dictionary keyed on ranker with
            a new nominal rank based on that order. Thus by ordering a list of ranke a new
            ordering can be determined on basis of the list in that order.
            '''
            rank_dict = {}
            r = 1
            for rank in ordered_ranks:
                rank_dict[rank.ranker] = r
                r += 1
            return rank_dict   
        
        actual_rank = dictify(self.actual_ranking)
        predicted_rank = dictify(self.predicted_ranking_after[0]) if after else dictify(self.predicted_ranking[0])
        total = 0
        right = 0
        for relationship in self.relationships:
            ranker1 = relationship[0]
            ranker2 = relationship[1]
            real_result = actual_rank[ranker1] < actual_rank[ranker2]
            pred_result = predicted_rank[ranker1] < predicted_rank[ranker2]
            total += 1
            if pred_result == real_result:
                right +=1
                                                               
        return right/total if total > 0 else 0    

    @property
    def prediction_quality(self) -> int:
        return self._prediction_quality()

    @property
    def prediction_quality_after(self) -> int:
        return self._prediction_quality(True)

    @property
    def inspector(self) -> str:
        '''
        Returns a safe HTML string reporting the structure of a session for prurposes
        of rapid and easy debugging of any database integrity issues. Many other 
        properties and methods make assumptions about session integrity and if these fail 
        they bomb. The aim here is that this is robust and just reports the database 
        objects related and their basic properties with PKs in a nice HTML div that
        can be popped onto any page or on a spearate "inspector" page if desired.  
        '''
        # A TootlTip Format string
        ttf = "<div class='tooltip'>{}<span class='tooltiptext'>{}</span></div>"
        
        html = "<div id='session_inspector' class='inspector'>"
        html += "<table>"
        html += "<tr><th>pk:</th><td>{}</td></tr>".format(self.pk)
        html += "<tr><th>date_time:</th><td>{}</td></tr>".format(self.date_time)
        html += "<tr><th>league:</th><td>{}</td></tr>".format(self.league.pk)
        html += "<tr><th>location:</th><td>{}</td></tr>".format(self.location.pk)
        html += "<tr><th>game:</th><td>{}</td></tr>".format(self.game.pk)
        html += "<tr><th>team_play:</th><td>{}</td></tr>".format(self.team_play)
        
        pid = ttf.format("pid", "Performance ID - the primary key of a Performance object")
        rid = ttf.format("rid", "Rank ID - the primary key of a Rank object")
        tid = ttf.format("tid", "Ream ID - the primary key of a Team object")
        html += "<tr><th>{}</th><td><table>".format(ttf.format("Integrity:","Every player in the game must have an associated performance, rank and if relevant, team object"))
        for performance in self.performances.all():
            html += "<tr>"
            html += "<th>player:</th><td>{}</td><td>{}</td>".format(performance.player.pk, performance.player.full_name)
            html += "<th>{}:</th><td>{}</td>".format(pid, performance.pk)

            rank = None
            team = None
            if self.team_play:
                ranks = Rank.objects.filter(session=self)
                for r in ranks:
                    if not r.team is None:  # Play it safe in case of database integrity issue
                        try:
                            t = Team.objects.get(pk=r.team.pk)
                        except Team.DoesNotExist:
                            t = None
                        
                        players = t.players.all() if not t is None else []

                        if performance.player in players:
                            rank = r.pk
                            team = t.pk
            else:
                try:
                    rank = Rank.objects.get(session=self, player=performance.player).pk
                    html += "<th>{}:</th><td>{}</td>".format(rid, rank)
                except Rank.DoesNotExist:
                    rank = None
                    html += "<th>{}:</th><td>{}</td>".format(rid, rank)
                except Rank.MultipleObjectsReturned:
                    ranks = Rank.objects.filter(session=self, player=performance.player)
                    html += "<th>{}:</th><td>{}</td>".format(rid, [rank.pk for rank in ranks])
            
            html += "<th>{}:</th><td>{}</td>".format(tid, team) if self.team_play else ""
            html += "</tr>"
        html += "</table></td></tr>"
        
        html += "<tr><th>ranks:</th><td><ol start=0>"
        for rank in self.ranks.all():
            html += "<li><table>"
            html += "<tr><th>pk:</th><td>{}</td></tr>".format(rank.pk)
            html += "<tr><th>rank:</th><td>{}</td></tr>".format(rank.rank)
            html += "<tr><th>player:</th><td>{}</td><td>{}</td></tr>".format(rank.player.pk if rank.player else None, rank.player.full_name if rank.player else None)
            html += "<tr><th>team:</th><td>{}</td><td>{}</td></tr>".format(rank.team.pk if rank.team else None, rank.team.name if rank.team else "")
            if (rank.team):
                for player in rank.team.players.all():
                    html += "<tr><th></th><td>{}</td><td>{}</td></tr>".format(player.pk, player.full_name)                                
            html += "</table></li>"
        html += "</ol></td></tr>"
            
        html += "<tr><th>performances:</th><td><ol start=0>"
        for performance in self.performances.all():
            html += "<li><table>"
            html += "<tr><th>pk:</th><td>{}</td></tr>".format(performance.pk)
            html += "<tr><th>player:</th><td>{}</td><td>{}</td></tr>".format(performance.player.pk, performance.player.full_name)
            html += "<tr><th>weight:</th><td>{}</td></tr>".format(performance.partial_play_weighting)
            html += "<tr><th>play_number:</th><td>{}</td>".format(performance.play_number)
            html += "<th>victory_count:</th><td>{}</td></tr>".format(performance.victory_count)
            html += "<tr><th>mu_before:</th><td>{}</td>".format(performance.trueskill_mu_before)
            html += "<th>mu_after:</th><td>{}</td></tr>".format(performance.trueskill_mu_after)
            html += "<tr><th>sigma_before:</th><td>{}</td>".format(performance.trueskill_sigma_before)
            html += "<th>sigma_after:</th><td>{}</td></tr>".format(performance.trueskill_sigma_after)
            html += "<tr><th>eta_before:</th><td>{}</td>".format(performance.trueskill_eta_before)
            html += "<th>eta_after:</th><td>{}</td></tr>".format(performance.trueskill_eta_after)            
            html += "</table></li>"
        html += "</ol></td></tr>"
        html += "</table>"
        html += "</div>"
    
        return html

    def _html_rankers_ol(self, ordered_ranks, use_rank, expected_performance, name_style, ol_style=""):
        '''
        Internal OL factory for list of rankers on a session. 
        
        :param ordered_ranks:           Rank objects in order we'd like them listed. 
        :param use_rank:                Use Rank.rank to permit ties, else use the row number
        :param expected_performance:    Name of Rank method that returns a Predicted Performance summary
        :param name_style:              The style in which to render names
        :param ol_style:                A style to apply to the OL if any
        '''
                
        data = []
        if ol_style:
            detail = u'<OL style="{}">'.format(ol_style)
        else:
            detail = u'<OL>'

        rankers = OrderedDict()
        row = 1
        for r in ordered_ranks:
            if self.team_play:
                # Teams we can render with the default format
                # TODO: Check this, they should also respect 
                #  link and name_style for members and linking of 
                #     members names when listed!  
                ranker = field_render(r.team, flt.template)
                data.append((r.team.pk, None))
            else:
                # Render the field first as a template which has:
                # {Player.PK} in place of the players name, and a
                # {link.klass.model.pk}  .. {link_end} wrapper around anything that needs a link
                ranker = field_render(r.player, flt.template, osf.template)
                
                # Replace the player name template item with the formatted name of the player
                ranker = re.sub(fr'{{Player\.{r.player.pk}}}', r.player.name(name_style), ranker)
                
                # Add a (PK, BGGid) tuple to the data list that provides a PK to BGGid map for a the leaderboard template view 
                PK = r.player.pk
                BGG = None if (r.player.BGGname is None or len(r.player.BGGname) == 0 or r.player.BGGname.isspace()) else r.player.BGGname 
                data.append((PK, BGG))
            
            # Add expected performance to the ranker string if requested                
            eperf = ""
            if not expected_performance is None:
                perf = getattr(r, expected_performance, None) # (mu, sigma)
                if not perf is None:
                    eperf = perf[0] # mu
                    
            if eperf:
                tip = "<span class='tooltiptext' style='width: 600%;'>Expected performance (teeth)</span>"
                ranker += " (<div class='tooltip'>{:.1f}{}</div>)".format(eperf, tip)                                    
            
            if use_rank:
                if r.rank in rankers:
                    rankers[r.rank].append(ranker)
                else:
                    rankers[r.rank] = [ranker]            
            else:
                rankers[row] = [ranker]
                
            row += 1
        
        row = 1
        for rank in rankers:                
            detail += u'<LI value={}>{}</LI>'.format(row, ", ".join(rankers[rank]))
            row += 1
            
        detail += u'</OL>'
        
        return (detail, data)
        
    def leaderboard_header(self, name_style="flexi"):
        '''
        Returns a HTML header that can be used on leaderboards.

        It includes the ranked list of performers in that session. 
        
        This comes in two parts, a template, and ancillary data.
        
        The template is HTML with placeholders for the ancillary data.
        
        This permits a leaderboard view to render the template altering how 
        the template is rendered.  The ancillary data is for now just the
        pk and BGG name of the ranker in that session which allows the 
        template to link names to this site or to BGG as it desires. 
        
        :param name_style: Must be supplied
        '''
        detail = u"<b>" + time_str(self.date_time) + u"</b><br><br>"
        
        (ol, data) = self._html_rankers_ol(self.ranks.all(), True, None, name_style)
        
        detail += ol
        
        return (detail, data)         

    def leaderboard_analysis(self, name_style="flexi"):
        '''
        Returns a HTML header that can be used on leaderboards.

        It includes an analysis of the session. 
        
        This comes in two parts, a template, and ancillary data.
        
        The template is HTML with placeholders for the ancillary data.
        
        This permits a leaderboard view to render the template altering how 
        the template is rendered.  The ancillary data is for now just the
        pk and BGG name of the ranker in that session which allows the 
        template to link names to this site or to BGG as it desires.
        
        Format is as follows:
        
        1) An ordered list of players as the prediction
        2) A confidence in the prediction (a measure of probability)
        3) A quality measure of that prediction
                
        :param name_style: Must be supplied
        '''
        (ordered_ranks, confidence) = self.predicted_ranking
        
        tip_sure = "<span class='tooltiptext' style='width: 500%;'>Given the expected performance of players, the probability that this predicted ranking would happen.</span>"
        tip_accu = "<span class='tooltiptext' style='width: 300%;'>Compared with the actual result, what percentage of relationships panned out as expected performances predicted.</span>"
        detail = f"Predicted ranking (<div class='tooltip'>{confidence:.0%} sure{tip_sure}</div>, <div class='tooltip'>{self.prediction_quality:.0%} accurate){tip_accu}</div>: <br><br>"
        (ol, data) = self._html_rankers_ol(ordered_ranks, False, "performance", name_style, "margin-left: 8ch;")        
        
        detail += ol
        
        return (mark_safe(detail), data)
    
    def leaderboard_analysis_after(self, name_style="flexi"):
        '''
        Returns a HTML header that can be used on leaderboards.

        It includes an analysis of the session updates. 
        
        This comes in two parts, a templates, and ancillary data.
        
        The template is HTML with placeholders for the ancillary data.
        
        This permits a leaderboard view to render the template altering how 
        the template is rendered.  The ancillary data is for now just the
        pk and BGG name of the ranker in that session which allows the 
        template to link names to this site or to BGG as it desires.
        
        Format is as follows:
        
        1) An ordered list of players as a the prediction
        2) A confidence in the prediction (some measure of probability)
        3) A quality measure of that prediction
                
        :param name_style: Must be supplied
        '''
        (ordered_ranks, confidence) = self.predicted_ranking_after

        tip_sure = "<span class='tooltiptext' style='width: 500%;'>Given the expected performance of players, the probability that this predicted ranking would happen.</span>"
        tip_accu = "<span class='tooltiptext' style='width: 300%;'>Compared with the actual result, what percentage of relationships panned out as expected performances predicted.</span>"
        detail = f"Predicted ranking (<div class='tooltip'>{confidence:.0%} sure{tip_sure}</div>, <div class='tooltip'>{self.prediction_quality_after:.0%} accurate){tip_accu}</div>: <br><br>"
        (ol, data) = self._html_rankers_ol(ordered_ranks, False, "performance_after", name_style, "margin-left: 8ch;")
        detail += ol
        
        return (mark_safe(detail), data)                  

    def leaderboard_snapshot(self):
        '''
        Prepares a leaderboard snapshot for passing to a view for rendering. 
        
        A snapshot is defined by a tuple with these entries in order:
        
        session.pk, 
        session.date_time (in local time), 
        session.game.play_counts()['total'], 
        session.game.play_counts()['sessions'], 
        session.players() (as a list of pks), 
        session.leaderboard_header(), 
        session.leaderboard_analysis(), 
        session.leaderboard_analysis_after(), 
        game.leaderboard()
        '''        
        # Get the leaderboard asat the time of this board.
        # We request an annotated version which supplies us with the information 
        # needed for player filtering and renderig, the leaderboard returned is 
        # complete (no league filter applied, or name rendering options supplied).
        # It will be up to the view to filter players as desired and select the 
        # name format at render time.
        lb = self.game.leaderboard(asat=self.date_time, simple=False)
        
        counts = self.game.play_counts(asat=self.date_time)

        # Build the snapshot tuple
        snapshot = (self.pk, 
                    localize(localtime(self.date_time)),
                    counts['total'], 
                    counts['sessions'], 
                    [p.pk for p in self.players], 
                    self.leaderboard_header(), 
                    self.leaderboard_analysis(), 
                    self.leaderboard_analysis_after(), 
                    lb)
        
        return snapshot
   
    def previous_sessions(self, player):
        '''
        Returns all the previous sessions that the nominate player played this game in. 
        Or None if no such session exists.
        '''
        # TODO: Test thoroughly. Tricky Query. 
        time_limit = self.date_time
        
        # Get the list of previous sessions including the current session! So the list must be at least length 1 (the current session).
        # The list is sorted in descending date_time order, so that the first entry is the current sessions.
        prev_sessions = Session.objects.filter(Q(date_time__lte=time_limit) & Q(game=self.game) & (Q(ranks__player=player) | Q(ranks__team__players=player))).order_by('-date_time')

        return prev_sessions

    def previous_session(self, player):
        '''
        Returns the previous session that the nominate player played this game in. 
        Or None if no such session exists.
        '''
        prev_sessions = self.previous_sessions(player)
        
        if len(prev_sessions) < 2:
            assert len(prev_sessions)==1, "Database error: Current session not in list previous sessions list, session={}, player={}, len(prev_sessions)={}.".format(self.pk, player.pk, len(prev_sessions))
            assert prev_sessions[0]==self, "Database error: Current session not in list previous sessions list, session={}, player={}, session={}.".format(self.pk, player.pk, prev_sessions[0])
            prev_session = None
        else:
            prev_session = prev_sessions[1]
            assert prev_sessions[0].date_time == self.date_time, "Query error: current session not in list for session={}, player={}".format(self.pk, player.pk)
            assert prev_session.date_time < self.date_time, "Database error: Two sessions with identical time, session={}, previous session={}, player={}".format(self.pk, prev_session.pk, player.pk)

        return prev_session

    def previous_victories(self, player):
        '''
        Returns all the previous sessions that the nominate player played this game in that this player won 
        Or None if no such session exists.
        '''
        # TODO: Test thoroughly. Tricky Query. 
        time_limit = self.date_time
        
        # Get the list of previous sessions including the current session! So the list must be at least length 1 (the current session).
        # The list is sorted in descening date_time order, so that the first entry is the current sessions.
        prev_sessions = Session.objects.filter(Q(date_time__lte=time_limit) & Q(game=self.game) & Q(ranks__rank=1) & (Q(ranks__player=player) | Q(ranks__team__players=player))).order_by('-date_time')

        return prev_sessions

    def rank(self, player):
        '''
        Returns the Rank object for the nominated player in this session
        '''
        if self.team_play:
            ranks = self.ranks.filter(team__players=player)
        else:
            ranks = self.ranks.filter(player=player)
        
        # 2 or more ranks for this player is a database integrity failure. Something serious got broken.    
        assert len(ranks) < 2, "Database error: {} Ranks objects in database for session={}, player={}".format(len(ranks), self.pk, player.pk)
        
        # Could be called before rank objects for a session submission were saved, In which case nicely indicate so with None.
        return ranks[0] if len(ranks) == 1 else None

    def performance(self, player):
        '''
        Returns the Performance object for the nominated player in this session
        '''
        assert player != None, f"Coding error: Cannot fetch the performance of 'no player'. Session pk: {self.pk}"
        performances = self.performances.filter(player=player)
        assert len(performances) == 1, "Database error: {} Performance objects in database for session={}, player={} sql={}".format(len(performances), self.pk, player.pk, performances.query)
        return performances[0]

    def previous_performance(self, player):
        '''
        Returns the previous Performance object for the nominate player in the game of this session
        '''
        prev_session = self.previous_session(player)
        return None if prev_session is None else prev_session.performance(player)

    def previous_victory(self, player):
        '''
        Returns the last Performance object for the nominate player in the game of this session that was victory
        '''
        # TODO: Test thoroughly. Tricky Query. 
        time_limit = self.date_time
        
        # Get the list of previous sessions including the current session! So the list must be at least length 1 (the current session).
        # The list is sorted in descening date_time order, so that the first entry is the current sessions.
        prev_victory = Session.objects.filter(Q(date_time__lte=time_limit) & Q(game=self.game) & Q(ranks__rank=1) & (Q(ranks__player=player) | Q(ranks__team__players=player))).order_by('-date_time')
        return None if (prev_victory is None or prev_victory.count() == 0) else prev_victory[0].performance(player)
              
    def build_trueskill_data(self, save=False):
        '''Builds a the data structures needed by trueskill.rate
        
        if save is True, will initialise Performance objects for each player too.
    
         A RatingGroup is list of dictionaries, one dictionary for each team
            keyed on the team name or ID containing a trueskill Rating object for that team
         In single player mode we simply supply teams of 1, so each dictionary has only one member 
             and can be keyed on player name or ID.
         A trueskill Rating is just a trueskill mu and sigma pair (actually a Gaussian object with a mu and sigma).
         
        Weights is a dictionary, keyed on a player identifier with a weight as a value 
            The weights are 0 to 1, 0 meaning no play and 1 meaning full time play.
            The player identifier is is a tuple which has two values (RatingsGroup index, Key into that RatingsGroup dictionary)
            
        Ranking list is a list of ranks (1, 2, 3 for first, second, third etc) that maps item
            for item into RatingGroup. Ties are indicated by repeating a given rank. 
         '''
        RGs = []
        Weights = {}
        Ranking = []
    
        if self.team_play:
            for rank, team in self.teams.items():
                RG = {}
                RGs.append(RG)
                for player in team.players.all():
                    performance = self.performance(player)
                    if self.__bypass_admin__:
                        performance.__bypass_admin__ = True
                    performance.initialise(save)
                    RG[player.pk] = trueskill.Rating(mu=performance.trueskill_mu_before, sigma=performance.trueskill_sigma_before)
                    Weights[(len(RGs) - 1, player.pk)] = performance.partial_play_weighting
                Ranking.append(int(rank.split('.')[0]))                   
        else:
            for rank, player in self.ranked_players.items():                
                performance = self.performance(player)
                if self.__bypass_admin__:
                    performance.__bypass_admin__ = True
                performance.initialise(save)
                RGs.append({player.pk: trueskill.Rating(mu=performance.trueskill_mu_before, sigma=performance.trueskill_sigma_before)})
                Weights[(len(RGs) - 1, player.pk)] = performance.partial_play_weighting
                Ranking.append(int(rank.split('.')[0]))                   
        return RGs, Weights, Ranking        

    def calculate_trueskill_impacts(self):
        '''
        Given the rankings associated with this session (i.e. assuming they are recorded)
        and the trueskill measures for each player before the session will, calculate (and
        record against this session) on their basis the new trueskill measures.

        Saves the impacts to the database in the form of Performance objects and returns a
        summary of impacts.
        
        Does not update ratings in the database.
        '''
        TSS = TrueskillSettings()
        TS = trueskill.TrueSkill(mu=TSS.mu0, sigma=TSS.sigma0, beta=self.game.trueskill_beta, tau=self.game.trueskill_tau, draw_probability=self.game.trueskill_p)

        def RecordPerformance(rating_groups):
            '''
            Given a rating_groups structure from trueskill.rate will distribute the results to the Performance objects

            The Trueskill impacts are extracted from the rating_groups recorded in Performance objects.
            
            Ratings are not updated here. These are used to update ratings elsewhere.
            '''
            for t in rating_groups:
                for p in t:
                    player = Player.objects.get(pk=p)
                    
                    performances = Performance.objects.filter(session=self, player=player)
                    assert len(performances) == 1, "Database error: {} Performance objects in database for session={}, player={}".format(len(performances), self.pk, player.pk)
                    performance = performances[0]

                    mu = t[p].mu
                    sigma = t[p].sigma

                    performance.trueskill_mu_after = mu
                    performance.trueskill_sigma_after = sigma
                    performance.trueskill_eta_after = mu - TSS.mu0 / TSS.sigma0 * sigma  # µ − (µ0 ÷ σ0) × σ

                    # eta_before was saved when the performance ws initialised from the previous performance.
                    # We recalculate it now as an integrity check against global TrueSkill settings change.
                    # A change in eta_before suggests one of the global values TSS.mu0 or TSS.sigma0 has changed 
                    # and that is a conditon that needs handling. In theory it should force a complete rebuild 
                    # of the ratings. For now, just throw an exception.
                    # TODO: Handle changes in TSS.mu0 or TSS.sigma0 cleanly. Namely:
                    #    trigger a neat warning to the registrar (person saving a session now)
                    #    inform admins by email, with suggested action (rebuild ratings from scratch or reset TSS.mu0 and TSS.sigma0 
                    previous_trueskill_eta_before = performance.trueskill_eta_before 
                    performance.trueskill_eta_before = performance.trueskill_mu_before - TSS.mu0 / TSS.sigma0 * performance.trueskill_sigma_before
                    assert isclose(performance.trueskill_eta_before, previous_trueskill_eta_before, abs_tol=FLOAT_TOLERANCE), "Integrity error: suspiscious change in a TrueSkill rating." 
                    
                    if self.__bypass_admin__:
                        performance.__bypass_admin__ = True
                    
                    performance.save()
            return
        
        # Trueskill Library has moderate internal docs. Much better docs here:
        #    http://trueskill.org/
        # For our sanity to be clear here:
        #
        # RatingsGroup is a list each item of which is a dictionary, 
        #    keyed on player ID with a rating object as its value
        #    teams are supported by this list, that is each item in RatingsGroup
        #    is a logical player or team represented by a dicitonary of players.
        #    With individual players the team simply has one item in the dictionary.
        #    Teams with more than one player have all the players in this dictionary.
        #
        # Ranking is a list of rankings. Each list item maps into a RatingsGroup list item
        #    so the 0th value in Rank maps to the 0th value in RatingsGroup
        #    and the 1st value in Rank maps to the 0th value in RatingsGroup etc.
        #    Each item in this list is a numeric (int) ranking.
        #    Ties are recorded with the same ranking value. Equal 1 for example.
        #    The value of the rankings is relevant only for sorting, that is ordering the 
        #    objects in the RatingsGroup list (and supporting ties).
        #
        # Weights is a dictionary, keyed on a player identifier with a weight as a value 
        #    The weights are 0 to 1, 0 meaning no play and 1 meaning full time play.
        #    The player identifier is is a tuple which has two values (RatingsGroup index, Key into that RatingsGroup dictionary) 
        
        OldRatingGroups, Weights, Ranking = self.build_trueskill_data(save=True) 
        NewRatingGroups = TS.rate(OldRatingGroups, Ranking, Weights, TSS.delta)
        RecordPerformance(NewRatingGroups)

        return self.trueskill_impacts 

    def __unicode__(self): 
        return u'{} - {}'.format(time_str(self.date_time), self.game)
    
    def __str__(self): return self.__unicode__()
    
    def __verbose_str__(self):
        return u'{} - {} - {} - {}'.format(
            time_str(self.date_time), 
            self.league, 
            self.location, 
            self.game)
        
    def __rich_str__(self, link=None):
        if self.team_play:
            victors = []
            for t in self.victors:
                if t.name is None:
                    victors += ["(" + ", ".join([field_render(p.name_nickname, link_target_url(p, link)) for p in t.players.all()]) + ")"]
                else:
                    victors += [field_render(t.name, link_target_url(t, link))]
        else:
            victors = [field_render(p.name_nickname, link_target_url(p, link)) for p in self.victors]
            
        try:
            return u'{} - {} - {} - {} - {} {} ({} won)'.format(
                time_str(self.date_time), 
                field_render(self.league, link), 
                field_render(self.location, link), 
                field_render(self.game, link), 
                self.num_competitors, 
                self.str_competitors, 
                ", ".join(victors))
        except:
            pass
    
    def __detail_str__(self, link=None):
        detail = time_str(self.date_time) + "<br>"
        detail += field_render(self.game, link) + "<br>"
        detail += u'<OL>'

        rankers = OrderedDict()
        for r in self.ranks.all():
            if self.team_play:
                ranker = field_render(r.team, link)
            else:
                ranker = field_render(r.player, link)
            
            if r.rank in rankers:
                rankers[r.rank].append(ranker)
            else:
                rankers[r.rank] = [ranker]
            
        for rank in rankers:
            detail += u'<LI value={}>{}</LI>'.format(rank, ", ".join(rankers[rank]))
            
        detail += u'</OL>'
        return detail 
            
    def check_integrity(self):
        '''
        It should be impossible for a session to go wrong if implemented securely and atomically. 
        
        But all the same it's a complext object and database integrity failures can cause a lot of headaches, 
        so this is a centralised integrity check for a given session so that a walk through sessions can find 
        and identify issues easily.
        '''
        # Check all the fields
        for field in ['date_time', 'league', 'location', 'game', 'team_play']:
            assert  getattr(self, field, None) != None, "Session Integrity error (id: {}): Must have {}.".format(self.id, field)
            
        # Check that team_play is permitted for the game
        # TODO: Enable this once we have team play working properly, using an Inkognito session to fine tune the form mode change.
        # assert (self.team_play and self.game.team_play) or (not self.team_play and self.game.individual_play), "Session Integrity error (id: {}): Game does not support play mode (game:{}, play mode: {}).".format(self.id, self.game.id, self.team_play) 

        # Collect the ranks and check rank fields
        rank_values = []
        assert self.ranks.count() > 0, "Session Integrity error (id: {}): Has no ranks.".format(self.id)
        for rank in self.ranks.all():
            for field in ['session', 'rank']:
                assert  getattr(rank, field, None) != None, "Session Integrity error (id: {}): Rank {} (id: {}) must have {}.".format(self.id, rank.rank, rank.id,  field)
            if self.team_play:
                assert rank.team != None, "Session Integrity error (id: {}): Rank {} (id: {}) must have team.".format(self.id, rank.rank, rank.id)
            else:
                assert rank.player != None, "Session Integrity error (id: {}): Rank {} (id: {}) must have player.".format(self.id, rank.rank, rank.id)
            rank_values.append(rank.rank)
            
        # Check that we have a victor
        assert 1 in rank_values, "Session Integrity error (id: {}): Must have a victor (rank=1).".format(self.id)
               
        # Check that ranks are contiguous
        last_rank_val = 0
        rank_values.sort()
        for rank in rank_values:
            assert rank == last_rank_val or rank == last_rank_val+1, "Session Integrity error (id: {}): Ranks must be consecutive and have no gaps. Found rank {} when previous rank was {}.".format(self.id, rank, last_rank_val)
            last_rank_val = rank

        # Collect all the players (respecting the mode of play team/individual)
        players = set()
        if self.team_play:
            for rank in self.ranks.all():
                assert rank.team, "Session Integrity error (id: {}): Rank {} (id:{}) has no team.".format(self.id, rank.rank, rank.id)
                assert rank.team.players, "Session Integrity error (id: {}): Rank {} (id:{}) has a team (id:) with no players.".format(self.id, rank.rank, rank.id, rank.team.id)
                
                # Check that the number of players is allowed by the game
                num_players = len(rank.team.players.all())
                assert num_players >= self.game.min_players_per_team, "Session Integrity error (id: {}): Too few players in team (game: {}, team: {}, players: {}, min: {}).".format(self.id, self.game.id, rank.team.id, num_players, self.game.min_players_per_team)
                assert num_players <= self.game.max_players_per_team, "Session Integrity error (id: {}): Too many players in team (game: {}, team: {}, players: {}, max: {}).".format(self.id, self.game.id, rank.team.id, num_players, self.game.max_players_per_team)
                
                for player in rank.team.players.all():
                    assert player, "Session Integrity error (id: {}): Rank {} (id: {}) has a team (id: {}) with an invalid player.".format(self.id, rank.rank, rank.id, rank.team.id)
                    players.add(player)
        else:
            for rank in self.ranks.all():
                assert rank.player, "Session Integrity error (id: {}): Rank {} (id: {}) has no player.".format(self.id, rank.rank, rank.id)
                players.add(rank.player)
        
        # Check that the number of players is allowed by the game
        assert len(players) >= self.game.min_players, "Session Integrity error (id: {}): Too few players (game: {}, players: {}).".format(self.id, self.game.id, len(players))
        assert len(players) <= self.game.max_players, "Session Integrity error (id: {}): Too many players (game: {}, players: {}).".format(self.id, self.game.id, len(players))

        # Check that there's a performance obejct for each player and only one for each player         
        for performance in self.performances.all():
            for field in ['session', 'player', 'partial_play_weighting', 'play_number', 'victory_count']:
                assert getattr(performance, field, None) != None, "Session Integrity error (id: {}): Performance {} (id:{}) has no {}.".format(self.id, performance.play_number, performance.id, field)
            assert performance.player in players, "Session Integrity error (id: {}): Performance {} (id:{}) refers to a player that was not ranked: {}.".format(self.id, performance.play_number, performance.id, performance.player)
            players.discard(performance.player)
            
        assert len(players) == 0, "Session Integrity error (id: {}): Ranked players that lack a performance: {}.".format(self.id, performance.play_number, performance.id, players)
        
        # Check that for each performance object the _before ratings are same as _after retings in the previous performance
        for performance in self.performances.all():
            previous = self.previous_performance(performance.player)
            if previous is None:
                TS = TrueskillSettings()
                
                trueskill_eta = TS.mu0 - TS.mu0 / TS.sigma0 * TS.sigma0
                
                assert isclose(performance.trueskill_mu_before, TS.mu0, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance µ mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_mu_before, None, TS.mu0)
                assert isclose(performance.trueskill_sigma_before, TS.sigma0, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance σ mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_sigma_before, None, TS.sigma0)
                assert isclose(performance.trueskill_eta_before, trueskill_eta, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance η mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_eta_before, None, trueskill_eta)
            else:
                assert isclose(performance.trueskill_mu_before, previous.trueskill_mu_after, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance µ mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_mu_before, previous.session.date_time, previous.trueskill_mu_after)
                assert isclose(performance.trueskill_sigma_before, previous.trueskill_sigma_after, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance σ mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_sigma_before, previous.session.date_time, previous.trueskill_sigma_after)
                assert isclose(performance.trueskill_eta_before, previous.trueskill_eta_after, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance η mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_eta_before, previous.session.date_time, previous.trueskill_eta_after)

    def clean(self):
        '''
        Clean is called by DJango before form_valid is called for the form. It affords a place and way for us to
        Check that everything is in order before processing to the form_valid  method that should save.
        '''
        # Check that the number of players is allowed by the game
        # This is called before the ranks are saved and hence fails always! 
        # The bounce also loses the player selections (and maybe more form the Performance widgets?
        # FIXME: While bouncing, see what we can do to conserve the form, state!
        # FIXME: Fix the bounce, namely work out how to test the related objects in the right order of events 
        
        # FIXME: When we land here no ranks or performances are saved, and
        # self.players finds no related ranks.
        # Does this mean we need to do an is_valid and if so, save on the 
        # ranks and performances first? But if the session is not saved they 
        # too will have dramas with order.
        #
        # Maybe it's hard with clean (which is presave) to do the necessary
        # relation tests? Is this an application for an atomic save, which 
        # can be performed on all the forms with minimal clean, then 
        # subsequently an integrity check (or clean) on the enseble and
        # if failed, then roll back?
    
        # For now bypass the clean to do a test    
        return
    
        players = self.players
        nplayers = len(players)
        if nplayers < self.game.min_players:
            raise ValidationError("Session {} has fewer players ({}) than game {} demands ({}).".format(self.pk, nplayers, self.game.pk, self.game.min_players))
        if nplayers > self.game.max_players:
            raise ValidationError("Session {} has more players ({}) than game {} permits ({}).".format(self.pk, nplayers, self.game.pk, self.game.max_players))

        # Ensure the play mode is compatible with the game being played. Form should have enforced this,
        # but we ensure it here.
        if (self.team_play and not self.game.team_play):
            raise ValidationError("Session {} specifies team play when game {} does not support it.".format(self.pk, self.game.pk))

        if (not self.team_play and not self.game.individual_play):
            raise ValidationError("Session {} specifies individual play when game {} does not support it.".format(self.pk, self.game.pk))

        # Ensure the time of the session does not clash. We need for this game and for any of these players for 
        # session time to be unique so that when TruesKill ratings are calculated the session times for all
        # affected players have a clear order. Unrelated sessions that don't involve the same game or any of 
        # this sessions players can have an identical time and this won't affect the ratings.  
        
        # Now force a unique time for this game and these players
        # We just keep adding a millisecond to the time while there are coincident sessions
        while True: 
            dfilter = Q(date_time=self.date_time)
            gfilter = Q(game=self.game)
            
            pfilter = Q()
            for player in players:
                pfilter |= Q(performances__player=player)
                
            sfilter = dfilter & gfilter & pfilter 
             
            coincident_sessions = Session.objects.filter(sfilter).exclude(pk=self.pk)
            
            if coincident_sessions.count() > 0:
                self.date_time += timedelta(milliseconds=1)
            else:
                break

        # Collect the ranks and check rank fields
        rank_values = []
        
        if self.ranks.count() == 0:
            raise ValidationError("Session {} has no ranks.".format(self.id))

        for rank in self.ranks.all():
            rank_values.append(rank.rank)
            
        # Check that we have a victor
        if not 1 in rank_values:
            raise ValidationError("Session {} has no victor (rank = 1).".format(self.id))

        # Check that ranks are contiguous
        last_rank_val = 0
        rank_values.sort()
        for rank in rank_values:
            if not (rank == last_rank_val or rank == last_rank_val+1):
                raise ValidationError("Session {} has a gap in ranks (between {} and {})".format(self.id), last_rank_val, rank)
            last_rank_val = rank

    def clean_relations(self):
        pass
#         errors = {
#             "date_time": ["Bad DateTime"], 
#             "league": ["Bad League", "No not really"], 
#             NON_FIELD_ERRORS: ["One error", "Two errors"]
#             }
#         raise ValidationError(errors)            

    class Meta(AdminModel.Meta):
        ordering = ['-date_time']

class Rank(AdminModel):
    '''
    The record, for a given Session of a Rank (i.e. 1st, 2nd, 3rd etc) for a specified Player or Team.

    Either a player or team is specified, neither or both is a data error.
    Which one, is specified in the Session model where a record is kept of whether this was a Team play session or not (i.e. Individual play)
    '''
    session = models.ForeignKey(Session, verbose_name='Session', related_name='ranks', on_delete=models.CASCADE)  # The session that this ranking belongs to
    rank = models.PositiveIntegerField('Rank')  # The rank (in this session) we are recording, as in 1st, 2nd, 3rd etc.

    # One or the other of these has a value the other should be null (enforce in integrity checks)
    # We coudlof course opt to use a single GenericForeignKey here: 
    #    https://docs.djangoproject.com/en/1.10/ref/contrib/contenttypes/#generic-relations
    #    but there are some complexites they introduce that are rather unnatracive as well
    player = models.ForeignKey(Player, verbose_name='Player', blank=True, null=True, related_name='ranks', on_delete=models.SET_NULL)  # The player who finished the game at this rank (1st, 2nd, 3rd etc.)
    team = models.ForeignKey(Team, verbose_name='Team', blank=True, null=True, editable=False, related_name='ranks', on_delete=models.SET_NULL)  # if team play is recorded then a team is created (or used if already in database) to group the rankings of the team members.

    add_related = ["player", "team"]  # When adding a Rank, add the related Players or Teams (if needed, or not if already in database)

    def _performance(self, after=False) -> tuple:        
        '''
        Returns a TrueSkill Performance for this ranking player or team. Uses very TrueSkill specific theory to provide
        a tuple of mean and standard deviation (mu, sigma) that describes TrueSkill Performance prediction.
        
        :param after: if true returns predicted performance with ratings after the update. ELse before.
        '''
        # TODO: Much of this This should really be in the trueskill package not here
        if self.session.team_play:
            players = list(self.team.players.all())
        else:
            players = [self.player]
            
        mu = 0
        var = 0
        for player in players:
            performance = self.session.performance(player)
            w = performance.partial_play_weighting
            mu += w * (performance.trueskill_mu_after if after else performance.trueskill_mu_before)
            sigma = performance.trueskill_sigma_after if after else performance.trueskill_sigma_before
            var += w**2*(sigma**2 + performance.trueskill_tau**2 + performance.trueskill_beta**2) 
        return (mu, var**0.5)

    @property
    def performance(self):
        '''
        Returns a TrueSkill Performance for this ranking player or team. Uses very TrueSkil specific theory to provide
        a tuple of mean and standard deviation (mu, sigma) that describes TrueSkill Performance prediction.        
        '''
        return self._performance()
    
    @property
    def performance_after(self):
        '''
        Returns a TrueSkill Performance for this ranking player or team using the ratings the received after this session update. 
        Uses very TrueSkil specific theory to provide a tuple of mean and standard deviation (mu, sigma) that describes TrueSkill 
        Performance prediction.
        '''
        return self._performance(True)   

    @property
    def ranker(self) -> object:
        '''
        Returns either a Player or Team, as appropriate for the ranker,
        that is the player or team ranking here   
        '''
        if self.session.team_play:
            return self.team
        else:
            return self.player

    @property
    def players(self) -> list:
        '''
        The list of players associated with this rank object (not explicitly at this rank 
        as two Rank objects in one session may have the same rank, i.e. a draw may be recorded)
        
        Players in teams are listed individually.

        Returns a list of one one or more players.
        '''
        # TODO should be a set not a list really. No order.
        session = Session.objects.get(id=self.session.id)
        if session.team_play:
            if self.team is None:
                raise ValueError("Rank '{}' is associated with a team play session but has no team.".format(self.id))
            else:
                # TODO: Test that this returns a clean list and not a QuerySet
                players = list(self.team.players.all())
        else:
            if self.player is None:
                raise ValueError("Rank '{0}' is associated with an individual play session but has no player.".format(self.id))
            else:
                players = [self.player]
        return players

    @property
    def is_part_of_draw(self) -> bool:
        '''
        Returns True or False, indicating whether or not more than one rank object on this session has the same rank
        (i.e. if this rank object is one part of a recorded draw).
        '''       
        ranks = Rank.objects.filter(session=self.session, rank=self.rank)
        return len(ranks) > 1

    @property
    def is_victory(self) -> bool:
        '''
        True if this rank records a victory, False if not.
        '''
        return self.rank == 1

    @property
    def is_team_rank(self):
        return self.session.team_play

    @property
    def link_internal(self) -> str:
        return reverse_lazy('view', kwargs={"model":self._meta.model.__name__,"pk": self.pk})

    #@property_method
    def check_integrity(self):
        '''
        Perform basic integrity checks on this Rank object.
        '''
        # Check that one of self.player and self.team has a valid value and the other is None
        assert not (self.team is None and self.player is None), "Integrity error: No team or player specified in rank {}".format(self.pk)
        assert not (not self.team is None and not self.player is None), "Integrity error: Both team and player specified in rank {}".format(self.pk)
        
        if self.team is None:
            assert not self.session.team_play, "Ingerity error: Rank {} specifies player while session {} specifies team play".format(self.pk, self.session.pk)
        elif self.player is None:
            assert self.session.team_play, "Ingerity error: Rank {} specifies team while session {} does not specify team play".format(self.pk, self.session.pk)
        
    def __unicode__(self):
        return "{}".format(self.rank)
    def __str__(self): return self.__unicode__()
    def __verbose_str__(self):
        if self.session is None: # Don't crash of the rank is orphaned!
            game = "<no game>"
            ranker = self.player
        else: 
            game = self.session.game
            ranker = self.team if self.session.team_play else self.player
        return  u'{} - {} - {}'.format(game, self.rank, ranker)    
    def __rich_str__(self, link=None):
        if self.session is None: # Don't crash of the rank is orphaned!
            game = "<no game>"
            team_play = False
            ranker = field_render(self.player, link)
        else: 
            game = field_render(self.session.game, link)
            team_play = self.session.team_play
            ranker = field_render(self.team, link) if team_play else field_render(self.player, link)
        return  u'{} - {} - {}'.format(game, field_render(self.rank, link_target_url(self, link)), ranker)    
    def __detail_str__(self, link=None):
        if self.session is None: # Don't crash of the rank is orphaned!
            game = "<no game>"
            team_play = False
            ranker = field_render(self.player, link)
            mode = "individual"
        else: 
            game = field_render(self.session.game, link)
            team_play = self.session.team_play
            ranker = field_render(self.team, link) if team_play else field_render(self.player, link)
            mode = "team" if team_play else "individual"
        return  u'{} - {} - {} ({} play)'.format(game, field_render(self.rank, link_target_url(self, link)), ranker, mode)    

    def clean(self):
        # Require that one of self.team and self.player is None 
        if self.team is None and self.player is None:
            # FIXME: For now let clean pass with no team if teamplay is selected.
            # This is because the team is not created until post processing (after the clean and save)
            # at present. This should be rethought and perhaps done in pre-processing so as
            # to present teams for the validation (and clean).
            # But because we don't know if it's a team_play session or not, that is,
            # clean is happening before the link to the session is made (self.session_id = None
            # we have to pass this condition always for now. 
            #raise ValidationError("No team or player specified in rank {}".format(self.pk))
            pass
        # When editing Rank objects and changing the team_play setting in the associated setting,
        # It can easily be that a team is added and a player remains. Clean up any duplicity on 
        # submission. 
        if not self.team is None and not self.player is None:
            if not hasattr(self.session,"team_play"):
                raise ValidationError("Both team and player specified in rank {} but it has no associated session so we can't clean it.".format(self.pk))

            if self.session.team_play:
                self.player = None
            else:
                self.team = None                
        
        # Require that self.team/self.player reflects self.session.team_play
# TODO: House this elsewhere, can't clean relations here as related objects don't exist yet. This clean can only be internal to this model 
#         if self.team is None and self.session.team_play:
#             raise ValidationError("Rank {} specifies player while session {} specifies team play".format(self.pk, self.session.pk))
#         elif self.player is None and not self.session.team_play:
#             raise ValidationError("Rank {} specifies team while session {} does not specify team play".format(self.pk, self.session.pk))

    class Meta(AdminModel.Meta):
        ordering = ['rank']

class Performance(AdminModel):
    '''
    Each player in each session has a Performance associated with them.

    The only input here is the partial play weighting, which models just that, early departure from the game session before the game is complete.
    But can be used to arbitrarily weight contributions of players to teams as well if desired.

    This model also contains for each session a record of the calculated Trueskill performance of that player, namely trueskill values before
    and after the play (for data redundancy as the after values of one session are the before values of the next for a given player, which can
    also be asserted for data integrity).
    '''
    TS = TrueskillSettings()

    session = models.ForeignKey(Session, verbose_name='Session', related_name='performances', on_delete=models.CASCADE)  # The session that this weighting belongs to
    player = models.ForeignKey(Player, verbose_name='Player', related_name='performances', null=True, on_delete=models.SET_NULL)  # The player in that session to whom the weighting applies

    partial_play_weighting = models.FloatField('Partial Play Weighting (ω)', default=1)

    play_number = models.PositiveIntegerField('The number of this play (for this player at this game)', default=1, editable=False)
    victory_count = models.PositiveIntegerField('The count of victories after this session (for this player at this game)', default=0, editable=False)
    
    # Although Eta (η) is a simple function of Mu (µ) and Sigma (σ), we store it alongside Mu and Sigma because it is also a function of global settings µ0 and σ0.
    # To protect ourselves against changes to those global settings, or simply to detect them if it should happen, we capture their value at time of rating update in the Eta.
    # The before values are copied from the Rating for that Player/Game combo and the after values are written back to that Rating.
    trueskill_mu_before = models.FloatField('Trueskill Mean (µ) before the session.', default=TS.mu0, editable=False)
    trueskill_sigma_before = models.FloatField('Trueskill Standard Deviation (σ) before the session.', default=TS.sigma0, editable=False)
    trueskill_eta_before = models.FloatField('Trueskill Rating (η) before the session.', default=0, editable=False)
    
    trueskill_mu_after = models.FloatField('Trueskill Mean (µ) after the session.', default=TS.mu0, editable=False)
    trueskill_sigma_after = models.FloatField('Trueskill Standard Deviation (σ) after the session.', default=TS.sigma0, editable=False)
    trueskill_eta_after = models.FloatField('Trueskill Rating (η) after the session.', default=0, editable=False)

    # Record the global TrueskillSettings mu0, sigma0 and delta with each performance
    # This will allow us to reset ratings to the state they were at after this performance
    # It is an integrity measure as well against changes in these settings while a leaderboard
    # is running, which has significant consequences (suggesting a rebuild of all ratings is in 
    # order)  
    trueskill_mu0 = models.FloatField('Trueskill Initial Mean (µ)', default=trueskill.MU, editable=False)
    trueskill_sigma0 = models.FloatField('Trueskill Initial Standard Deviation (σ)', default=trueskill.SIGMA, editable=False)
    trueskill_delta = models.FloatField('TrueSkill Delta (δ)', default=trueskill.DELTA, editable=False)
    
    # Record the game specific Trueskill settings beta, tau and p with each performance.
    # Again for a given game these must be consistent among all ratings and the history of each rating. 
    # Any change while managing leaderboards should trigger an update request for ratings relating to this game.  
    trueskill_beta = models.FloatField('TrueSkill Skill Factor (ß)', default=trueskill.BETA, editable=False)
    trueskill_tau = models.FloatField('TrueSkill Dynamics Factor (τ)', default=trueskill.TAU, editable=False)
    trueskill_p = models.FloatField('TrueSkill Draw Probability (p)', default=trueskill.DRAW_PROBABILITY, editable=False)

    @property
    def game(self) -> Game:
        '''
        The game this performance relates to
        '''
        return self.session.game

    @property
    def date_time(self) -> datetime:
        '''
        The game this performance relates to
        '''
        return self.session.date_time

    @property
    def rank(self) -> int:
        '''
        The rank of this player in this session. Most certainly a component of a player's
        performance, but not stored in the Performance model because it is associated either
        with a player or whole team depending on the play mode (Individual or Team). So this
        property fetches the rank from the Rank model where it's stored.
        '''
        team_play = self.session.team_play
        if team_play:
            ranks = Rank.objects.filter(session=self.session.id)
            for rank in ranks:
                if not rank.team is None:  # Play it safe in case of database integrity issue
                    team = Team.objects.get(pk=rank.team.id)
                    players = team.players.all()
                    if self.player in players:
                        return rank.rank
        else:
            rank = Rank.objects.get(session=self.session.id, player=self.player.id).rank
            return rank

    @property
    def is_victory(self) -> bool:
        '''
        True if this performance records a victory for the player, False if not.
        '''
        return self.rank == 1

    @property
    def rating(self) -> Rating:
        '''
        Returns the rating object associated with this performance. That is for the same player/game combo. 
        '''
        try:
            r = Rating.objects.get(player=self.player, game=self.session.game)
        except ObjectDoesNotExist:
            r = Rating.create(player=self.player, game=self.session.game)
        except MultipleObjectsReturned:
            raise ValueError("Database error: more than one rating for {} at {}".format(self.player.name_nickname, self.session.game.name))
        return r       

    @property
    def previous_play(self) -> 'Performance':
        '''
        Returns the previous performance object that this player played this game in. 
        '''
        return self.session.previous_performance(self.player)

    @property
    def previous_win(self) -> 'Performance':
        '''
        Returns the previous performance object that this player played this game in and one in 
        '''
        return self.session.previous_victory(self.player)

    @property
    def link_internal(self) -> str:
        return reverse_lazy('view', kwargs={"model":self._meta.model.__name__,"pk": self.pk})
    
    def initialise(self, save=False):
        '''
        Initialises the performance object.
        
        With the session and player already known,
        finds the previous session that this player played this game in   
        and copies the after ratings of the previous performance (for this 
        player at this session's game) to the before ratings of this 
        performance object for that player. 
        '''

        previous = self.session.previous_performance(self.player)
        
        if previous is None:
            TSS = TrueskillSettings()
            self.play_number = 1
            self.victory_count = 1 if self.session.rank(self.player).rank == 1 else 0
            self.trueskill_mu_before = TSS.mu0
            self.trueskill_sigma_before = TSS.sigma0
            self.trueskill_eta_before = 0
            
            
        else:
            self.play_number = previous.play_number + 1
            self.victory_count = previous.victory_count + 1 if self.session.rank(self.player).rank == 1 else previous.victory_count  # TODO: Test this. 
            self.trueskill_mu_before = previous.trueskill_mu_after
            self.trueskill_sigma_before = previous.trueskill_sigma_after
            self.trueskill_eta_before = previous.trueskill_eta_after
        
        # Capture the Trueskill settings that are in place now too. 
        TS = TrueskillSettings()
        self.trueskill_mu0 = TS.mu0 
        self.trueskill_sigma0 = TS.sigma0 
        self.trueskill_delta = TS.delta
        self.trueskill_beta = self.session.game.trueskill_beta 
        self.trueskill_tau = self.session.game.trueskill_tau 
        self.trueskill_p = self.session.game.trueskill_p 
        
        if save:
            self.save()

    def check_integrity(self):
        '''
        Perform basic integrity checks on this Performance object.
        '''
        # Check that the before values match the after values of the previous play
        performance = self
        previous = self.previous_play
        
        if previous is None:
            TS = TrueskillSettings()
            
            assert isclose(performance.trueskill_mu_before, TS.mu0, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance µ mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_mu_before, None, TS.mu0)
            assert isclose(performance.trueskill_sigma_before, TS.sigma0, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance σ mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_sigma_before, None, TS.sigma0)
            assert isclose(performance.trueskill_eta_before, 0, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance η mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_eta_before, None, 0)
        else:
            assert isclose(performance.trueskill_mu_before, previous.trueskill_mu_after, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance µ mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_mu_before, previous.session.date_time, previous.trueskill_mu_after)
            assert isclose(performance.trueskill_sigma_before, previous.trueskill_sigma_after, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance σ mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_sigma_before, previous.session.date_time, previous.trueskill_sigma_after)
            assert isclose(performance.trueskill_eta_before, previous.trueskill_eta_after, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance η mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_eta_before, previous.session.date_time, previous.trueskill_eta_after)
        
        # Check that the Trueskill settings are consistent with previous play too
        if previous is None:
            TS = TrueskillSettings()
            
            assert isclose(performance.trueskill_mu0, TS.mu0, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance µ0 mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_mu0_before, None, TS.mu0)
            assert isclose(performance.trueskill_sigma0, TS.sigma0, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance σ0 mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_sigma0_before, None, TS.sigma0)
            assert isclose(performance.trueskill_delta, TS.delta, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance δ mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_delta_before, None, TS.delta)
        else:
            assert isclose(performance.trueskill_mu0, previous.trueskill_mu0, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance µ0 mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_mu_before, previous.session.date_time, previous.trueskill_mu0_after)
            assert isclose(performance.trueskill_sigma0, previous.trueskill_sigma0, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance σ0 mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_sigma_before, previous.session.date_time, previous.trueskill_sigma0_after)
            assert isclose(performance.trueskill_delta, previous.trueskill_delta, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance δ mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_delta_before, previous.session.date_time, previous.trueskill_delta_after)
            assert isclose(performance.trueskill_beta, previous.trueskill_beta, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance ß mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_beta_before, previous.session.date_time, previous.trueskill_beta_after)
            assert isclose(performance.trueskill_tau, previous.trueskill_tau, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance τ mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_tau_before, previous.session.date_time, previous.trueskill_tau_after)
            assert isclose(performance.trueskill_p, previous.trueskill_p, abs_tol=FLOAT_TOLERANCE), "Integrity error: Performance p mismatch. Before at {} is {} and After on previous at {} is {}".format(performance.session.date_time, performance.trueskill_p_before, previous.session.date_time, previous.trueskill_p_after)
        
        # Check that there is an associate Rank
        assert not self.rank is None, "Integrity error: Apparently no rank avalaible for a Performance (id: {})".format(self.id)  

        # Check that play number and victory count reflect early records
        expected_play_number = self.session.previous_sessions(self.player).count()      # Includes the current sessions
        expected_victory_count = self.session.previous_victories(self.player).count()   # Includes the current session if it's a victory
        assert self.play_number == expected_play_number, "Integrity error: Play number on Performance is wrong. Performance id: {}, Play number: {}, Expected: {}.".format(self.id, self.play_number, expected_play_number)
        assert self.victory_count == expected_victory_count, "Integrity error: Victory count on Performance is wrong. Performance id: {}, Victory count: {}, Expected: {}.".format(self.id, self.victory_count, expected_victory_count)

    def clean(self):
        return # Disable for now, enable only for testing
    
        # Find the previous performance for this player at this game and copy 
        # the trueskill after values to the trueskill before values in this 
        # performance or from initials if no previous.
        previous = self.previous_play
        
        if previous is None:
            TS = TrueskillSettings()
            
            self.trueskill_mu_before = TS.mu0
            self.trueskill_sigma_before = TS.sigma0
            self.trueskill_eta_before = 0
        else:
            self.trueskill_mu_before = previous.trueskill_mu_after
            self.trueskill_sigma_before = previous.trueskill_sigma_after
            self.trueskill_eta_before = previous.trueskill_eta_after
            
        # Catch the Trueskill settings in effect now. 
        TS = TrueskillSettings()
        self.trueskill_mu0 = TS.mu0 
        self.trueskill_sigma0 = TS.sigma0 
        self.trueskill_beta = TS.beta 
        self.trueskill_delta = TS.delta
        self.trueskill_tau = self.session.game.trueskill_tau 
        self.trueskill_p = self.session.game.trueskill_p 
        
        # If any of these settings have changed since the previous performance (for this player at this game)
        # Then we have an error that demands a rebuild of ratings for this game.
        if not previous is None:
            if self.trueskill_mu0 != previous.trueskill_mu0:
                raise ValidationError("Global Trueskill µ0 has changed (from {} to {}). Either reset the value of rebuild all ratings for game {} ({}) ".format(self.trueskill_mu0, previous.trueskill_mu0, self.session.game.pk, self.session.game))
            if self.trueskill_sigma0 != previous.trueskill_sigma0: 
                raise ValidationError("Global Trueskill σ0 has changed (from {} to {}). Either reset the value of rebuild all ratings for game {} ({}) ".format(self.trueskill_sigma0, previous.trueskill_sigma0, self.session.game.pk, self.session.game))
            if self.trueskill_beta != previous.trueskill_beta:
                raise ValidationError("Global Trueskill ß has changed (from {} to {}). Either reset the value of rebuild all ratings for game {} ({}) ".format(self.trueskill_beta, previous.trueskill_beta, self.session.game.pk, self.session.game))
            if self.trueskill_delta != previous.trueskill_delta:
                raise ValidationError("Global Trueskill δ has changed (from {} to {}). Either reset the value of rebuild all ratings for game {} ({}) ".format(self.trueskill_delta, previous.trueskill_delta, self.session.game.pk, self.session.game))
            if self.trueskill_tau != previous.trueskill_tau: 
                raise ValidationError("Game Trueskill τ has changed (from {} to {}). Either reset the value of rebuild all ratings for game {} ({}) ".format(self.trueskill_tau, previous.trueskill_tau, self.session.game.pk, self.session.game))
            if self.trueskill_p != previous.trueskill_p:
                raise ValidationError("Game Trueskill p has changed (from {} to {}). Either reset the value of rebuild all ratings for game {} ({}) ".format(self.trueskill_p, previous.trueskill_p, self.session.game.pk, self.session.game))

        # Update the play counters too. We know this form submisison means one more play but we don't necessariuly know if it's
        # a victury yet (as that is stored with an associated Rank which may or may not have been saved yet). 
        self.play_number = previous.play_number + 1
        
        if self.session.rank(self.player):
            self.victory_count = previous.victory_count + 1 if self.session.rank(self.player).rank == 1 else previous.victory_count  # TODO: Test this. 

        # Trueskill Impact is calculated at the session level not the individual performance level.
        # The trueskill after settings for the performance will be calculated there.
        pass

    add_related = None
    sort_by = ['session.date_time', 'rank.rank', 'player.name_nickname'] # Need player to sort ties and team members.
    def __unicode__(self):
        return  u'{}'.format(self.player)
    def __str__(self): return self.__unicode__()
    def __verbose_str__(self):
        if self.session is None: # Don't crash of the performance is orphaned!
            when = "<no time>"
            game = "<no game>"
        else: 
            when = self.session.date_time
            game = self.session.game
        performer = self.player
        return  u'{} - {:%d, %b %Y} - {}'.format(game, when, performer)    
        
    def __rich_str__(self, link=None):
        if self.session is None: # Don't crash of the performance is orphaned!
            when = "<no time>"
            game = "<no game>"
        else: 
            when = self.session.date_time
            game = field_render(self.session.game, link)
        performer = field_render(self.player, link)
        performance = "{:.0%} participation, play number {}, {:+.1f} teeth".format(self.partial_play_weighting, self.play_number, self.trueskill_eta_after - self.trueskill_eta_before)
        return  u'{} - {:%d, %b %Y} - {}: {}'.format(game, when, performer, field_render(performance, link_target_url(self, link)))    

    def __detail_str__(self, link=None):
        if self.session is None: # Don't crash of the performance is orphaned!
            when = "<no time>"
            game = "<no game>"
            players = "<no players>"
        else: 
            when = self.session.date_time
            game = field_render(self.session.game, link)
            players = len(self.session.players)
            
        performer = field_render(self.player, link)
        
        detail = u'{} - {:%a, %-d %b %Y} - {}:<UL>'.format(game, when, performer)
        detail += "<LI>Players: {}</LI>".format(players)
        detail += "<LI>Play number: {}</LI>".format(self.play_number)
        detail += "<LI>Play Weighting: {:.0%}</LI>".format(self.partial_play_weighting)
        detail += "<LI>Trueskill Delta: {:+.1f} teeth</LI>".format(self.trueskill_eta_after - self.trueskill_eta_before)
        detail += "<LI>Victories: {}</LI>".format(self.victory_count)
        detail += "</UL>"
        return detail    

    class Meta(AdminModel.Meta):
        ordering = ['session', 'player']

#===============================================================================
# Administrative models
#===============================================================================

class Rebuild_Log(TimeZoneMixIn, models.Model):
    '''
    A log of rating rebuilds.
    
    Kept for two reasons:
    
    1) Performance measure. Rebuild can be slow and we'd like to know how slow. 
    2) Security. To see who rebuilt when
    '''
    date_time = models.DateTimeField('Time of Ratings Rebuild', default=timezone.now)
    date_time_tz = TimeZoneField('Time of Ratings Rebuild, Timezone', default=settings.TIME_ZONE, editable=False)
    ratings = models.PositiveIntegerField('Number of Ratings Built')
    duration = models.DurationField('Duration of Rebuild')
    rebuilt_by = models.ForeignKey(User, verbose_name='Rebuilt By', related_name='rating_rebuilds', editable=False, null=True, on_delete=models.SET_NULL)
    reason = models.TextField('Reason for Rebuild')    
