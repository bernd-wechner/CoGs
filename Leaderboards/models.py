# -*- coding: utf-8 -*-
import trueskill
from django.db import models
from django.utils import formats, timezone
from django.db.models import Sum, Max, Avg, Count, Q
from collections import OrderedDict
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned

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

MAX_NAME_LENGTH = 200  # The maximum length of a name in the database, i.e. the char fields for player, game, team names and so on.

def update_admin_fields(obj):
    '''
    Update the CoGs admin fields on an object (whenever it is saved).
    TODO: Use the actual logged in user here not user 1
    '''
    now = timezone.now()
    usr = Player.objects.get(pk=1)  # TODO: Get the actual logged in user

    if hasattr(obj, "last_edited_by"):
        obj.last_edited_by = usr

    if hasattr(obj, "last_edited_on"):
        obj.last_edited_on = now

    # We infer that if the object has pk it was being edited and if it has none it was being created
    if obj.pk is None:
        if hasattr(obj, "created_by"):
            obj.created_by = usr

        if hasattr(obj, "created_on"):
            obj.created_on = now

class TrueskillSettings(models.Model):
    '''
    The site wide TrueSkill settings to use (i.e. not Game).
    '''
    # Changing these affects the entire ratings history. That is we change one of these settings, either:
    #    a) All the ratings history needs to be recalculated to get a consistent ratings result based on the new settings
    #    b) We keep the ratings history with the old values and move forward with the new
    # Merits? Methods?
    # Suggest we have a form for editing these with processing logic and don't let the admin site edit them, or create logic
    # that can adapt to admin site edits - flagging the liklihood. Or perhaps we should make this not a one tuple table
    # but store each version with a date. That in can of course then support staged ratings histories, so not a bad idea.
    mu0 = models.FloatField('TrueSkill Initial Mean (µ0)', default=trueskill.MU)
    sigma0 = models.FloatField('TrueSkill Initial Standard Deviation (σ0)', default=trueskill.SIGMA)
    beta = models.FloatField('TrueSkill Skill Factor (ß)', default=trueskill.BETA)
    delta = models.FloatField('TrueSkill Delta (δ)', default=trueskill.DELTA)

    add_related = None
    def __unicode__(self): return u'µ0={} σ0={} ß={} δ={}'.format(self.mu0, self.sigma0, self.beta, self.delta)
    def __str__(self): return self.__unicode__()

    class Meta:
        verbose_name_plural = "Trueskill settings"

class League(models.Model):
    '''
    A group of Players who are competing at Games which have a Leaderboard of Ratings.

    Leagues operate independently of one another, meaning that
    when Sessions are recorded, only the Locations, Players and Games will appear on selectors.

    All Leagues share the same global and game Trueskill settings, so that a
    meaningful global leaderboard can be reported for any game across all leagues.
    '''
    name = models.CharField('Name of the League', max_length=MAX_NAME_LENGTH)
    manager = models.ForeignKey('Player', related_name='leagues_managed')

    locations = models.ManyToManyField('Location', blank=True, related_name='leagues_playing_here')
    players = models.ManyToManyField('Player', blank=True, related_name='member_of_leagues')
    games = models.ManyToManyField('Game', blank=True, related_name='played_by_leagues')

    # Simple history and administrative fields
    created_by = models.ForeignKey('Player', related_name='leagues_created', editable=False, null=True)
    created_on = models.DateTimeField(editable=False, null=True)
    last_edited_by = models.ForeignKey('Player', related_name='leagues_last_edited', editable=False, null=True)
    last_edited_on = models.DateTimeField(editable=False, null=True)

    def leaderboard(self, game=None):
        '''
        Return an ordered list of (player, rating, plays, victories) tuples that represents the leaderboard for a
        specified game or if no game is provided, a dictionary of such lists keyed on game.
        '''
        if game is None:
            # TODO: Fix this, it's wrong. Meaningless to return one leaderbaord across all games
            # instead returna  dictionary fo leaderboards keyed on game.
            ratings = Rating.objects.filter(player_leagues=self)
        else:
            ratings = Rating.objects.filter(player_leagues=self, game=game)
        
        lb = []
        for r in ratings:
            lb.append((str(r.player), r.trueskill_eta, r.plays, r.victories))
        return lb
    
    add_related = None
    def __unicode__(self): return self.name
    def __str__(self): return self.__unicode__()

    def save(self, *args, **kwargs):
        update_admin_fields(self)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['name']

class Team(models.Model):
    '''
    A player team, which is defined when a team play game is recorded and needed to properly display a session as it was played,
    and to calculate team based TrueSkill ratings. Teams have no names just a list of players.

    Teams may have names but don't need them.
    '''
    name = models.CharField('Name of the Team (optional)', max_length=MAX_NAME_LENGTH, null=True)
    players = models.ManyToManyField('Player', blank=True, editable=False, related_name='member_of_teams')

    # Simple history and administrative fields
    created_by = models.ForeignKey('Player', related_name='teams_created', editable=False, null=True)
    created_on = models.DateTimeField(editable=False, null=True)
    last_edited_by = models.ForeignKey('Player', related_name='teams_last_edited', editable=False, null=True)
    last_edited_on = models.DateTimeField(editable=False, null=True)

    add_related = ["players"]
    def __unicode__(self):
        if self.name:
            return self.name + u" [" + u", ".join([str(player) for player in self.players.all()]) + u"]"
        else:
            return u", ".join([str(player) for player in self.players.all()])
    def __str__(self): return self.__unicode__()

    def save(self, *args, **kwargs):
        update_admin_fields(self)
        super().save(*args, **kwargs)

class Player(models.Model):
    '''
    A player who is presumably collecting Ratings on Games and participating in leaderboards in one or more Leagues.

    Players can be Registrars, meaning they are permitted to record session results, or Staff meaning they can access the admin site.
    '''
    name_nickname = models.CharField('Nickname', max_length=MAX_NAME_LENGTH)
    name_personal = models.CharField('Personal Name', max_length=MAX_NAME_LENGTH)
    name_family = models.CharField('Family Name', max_length=MAX_NAME_LENGTH)

    email_address = models.EmailField('Email Address', blank=True)
    BGGname = models.CharField('BoardGameGeek Name', max_length=MAX_NAME_LENGTH, default='', blank=True)  # BGG URL is https://boardgamegeek.com/user/BGGname

    is_registrar = models.BooleanField('Authorised to record session results?', default=False)
    is_staff = models.BooleanField('Authorised to access the admin site?', default=False)

    teams = models.ManyToManyField('Team', blank=True, editable=False, through=Team.players.through, related_name='players_in_team')  # Don't edit teams always inferred from Session submissions
    leagues = models.ManyToManyField('League', blank=True, through=League.players.through, related_name='players_in_league')

    # Simple history and administrative fields
    created_by = models.ForeignKey('Player', related_name='players_created', editable=False, null=True)
    created_on = models.DateTimeField(editable=False, null=True)
    last_edited_by = models.ForeignKey('Player', related_name='players_last_edited', editable=False, null=True)
    last_edited_on = models.DateTimeField(editable=False, null=True)

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
    
    # TODO add a Leaderboard property
    #    A method needs to take a league and game as input
    #    A property can return a list of lists, leage, game, place on leaderboard

    add_related = None
    def __unicode__(self): return u'{} {} ({})'.format(self.name_personal, self.name_family, self.name_nickname)
    def __str__(self): return self.__unicode__()

    def save(self, *args, **kwargs):
        update_admin_fields(self)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['name_nickname']

class Game(models.Model):
    '''A game that Players can be Rated on and which has a Leaderboard (global and per League). Defines Game specific Trueskill settings.'''
    name = models.CharField('Name of the Game', max_length=200)
    BGGid = models.PositiveIntegerField('BoardGameGeek ID')  # BGG URL is https://boardgamegeek.com/boardgame/BGGid

    # Which play modes the game supports. This will decide the formats the session submission form supports
    individual_play = models.BooleanField(default=True)
    team_play = models.BooleanField(default=False)

    # Player counts, also inform the session logging form how to render
    min_players = models.PositiveIntegerField('Minimum number of players', default=2)
    max_players = models.PositiveIntegerField('Maximum number of players', default=4)
    
    min_players_per_team = models.PositiveIntegerField('Minimum number of players in a team', default=0)
    max_players_per_team = models.PositiveIntegerField('Maximum number of players in a team', default=0)

    # Which leagues play this game? A way to keep the game selector focussed on games a given league actually plays. 
    leagues = models.ManyToManyField(League, blank=True, related_name='games_played', through=League.games.through)

    # Game specific TrueSkill settings
    # tau: 0- describes the luck element in a game. 
    #      0 is a game of pure skill, 
    #        there is no upper limit. It is added to sigma after each re-reating (game session recorded)
    # p  : 0-1 describes the probability of a draw. It affects how far the mu of drawn players move toward 
    #        each other when a draw is recorded after each rating.
    #      0 means lots
    #      1 means not at all
    trueskill_tau = models.FloatField('TrueSkill Dynamics Factor (τ)', default=trueskill.TAU)
    trueskill_p = models.FloatField('TrueSkill Draw Probability (p)', default=trueskill.DRAW_PROBABILITY)

    # Simple history and administrative fields
    created_by = models.ForeignKey('Player', related_name='games_created', editable=False, null=True)
    created_on = models.DateTimeField(editable=False, null=True)
    last_edited_by = models.ForeignKey('Player', related_name='games_last_edited', editable=False, null=True)
    last_edited_on = models.DateTimeField(editable=False, null=True)

    @property
    def sessions(self):
        '''
        #TODO: This needs to be filtered in League, can't be a property that way of course so need the property to
        #      remain gobal and call a method that takes a league as argument, with no league argument indicating
        #      global should be returned.

        Returns a list of sessions that played this game. Useful for counting or traversing.        
        '''
        return Session.objects.filter(game=self)

    @property
    def plays(self):
        '''
        #TODO: This needs to be filtered in League, can't be a property that way of course so need the property to
        #      remain gobal and call a method that takes a league as argument, with no league argument indicating
        #      global should be returned.
        
        Returns the number of plays this game has experienced, as a dictionary containing:
            total: is the sum of all the individual player counts (so a count of total play experiences)
            max: is the largest play count of any player
            average: is the average play count of all players who've played at least once
            players: is a count of players who played this game at least once
            session: is a count of the number of sessions this game has been played
        '''
        # If no games have been played there will be no Rating object and this query will return None
        # Safeguard against this and return 0
        result = Rating.objects.filter(game=self).aggregate(total=Sum('plays'), max=Max('plays'), average=Avg('plays'), players=Count('plays'))
        for key in result:
            if result[key] is None:
                result[key] = 0
                
        result['sessions'] = self.sessions.count()
        return result

    @property
    def global_leaderboard(self):
        '''
        The leaderboard for this game considering all leagues together, as a simple property of the game.
        
        Returns as an ordered list of (player,rating, plays) tuples 
        
        The leaderboard for a specific league is available through the leaderboard method.
        '''
        return self.leaderboard()
    
    def rating(self, player):
        '''
        Returns the Trueskill rating for this player at the specified game
        '''
        try:
            r = Rating.objects.get(player=player, game=self)
        except ObjectDoesNotExist:
            r = Rating.create(player=player, game=self)
        except MultipleObjectsReturned:
            raise ValueError("Database error: more than one rating for {} at {}".format(player.name_nickname, self.name))
        return r

    def leaderboard(self, league=None):
        '''
        Return an ordered list of (player, rating, plays, victories) tuples that represents the leaderboard for a
        specified league, or for all leagues if None is specified.
        '''
        if league is None:
            # TODO: Fix this. To be compativel with League.leadaerboard(game), need to treat none
            # in a way the returns a dictionary of leaderboards keyed on league. To wit need a 
            # reserved league that represents "all leagues" This can be one of the dictionary 
            # entries and requested explicitly by specifying that league. A global constant like
            # ALL_LEAGUES for example which may be a league with a PK of 0 if we know that real 
            # leagues have PK > 0.
            ratings = Rating.objects.filter(game=self)
        else:
            ratings = Rating.objects.filter(game=self, player_leagues=league)
        
        lb = []
        for r in ratings:
            lb.append((str(r.player), r.trueskill_eta, r.plays, r.victories))
        return lb
            
    add_related = None
    def __unicode__(self): return self.name
    def __str__(self): return self.__unicode__()

    def save(self, *args, **kwargs):
        update_admin_fields(self)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['name']

class Location(models.Model):
    '''
    A location that a game session can take place at.
    '''
    name = models.CharField('name of the location', max_length=MAX_NAME_LENGTH)

    leagues = models.ManyToManyField(League, blank=True, related_name='Locations_used', through=League.locations.through)

    # Simple history and administrative fields
    created_by = models.ForeignKey('Player', related_name='locations_created', editable=False, null=True)
    created_on = models.DateTimeField(editable=False, null=True)
    last_edited_by = models.ForeignKey('Player', related_name='locations_last_edited', editable=False, null=True)
    last_edited_on = models.DateTimeField(editable=False, null=True)

    add_related = None
    def __unicode__(self): return self.name
    def __str__(self): return self.__unicode__()

    def save(self, *args, **kwargs):
        update_admin_fields(self)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['name']

class Session(models.Model):
    '''
    The record, with results (Ranks), of a particular Game being played competitively.
    '''
    date_time = models.DateTimeField(default=timezone.now)  # When the game session was played
    league = models.ForeignKey(League, related_name='sessions')  # The league playing this session
    location = models.ForeignKey(Location, related_name='sessions')  # Where the game sessions was played
    game = models.ForeignKey(Game, related_name='sessions')  # The game that was played
    
    # The game must support team play if this is true, 
    # and conversely, it must support individual play if this false.
    # TODO: Enforce this constraint
    # TODO: Let the session form know the modes supported so it can enable/disable the entry modes
    team_play = models.BooleanField(default=False)  # By default games are played by individuals, if true, this session was played by teams
    
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

    # Simple history and administrative fields
    created_by = models.ForeignKey('Player', related_name='sessions_created', editable=False, null=True)
    created_on = models.DateTimeField(editable=False, null=True)
    last_edited_by = models.ForeignKey('Player', related_name='sessions_last_edited', editable=False, null=True)
    last_edited_on = models.DateTimeField(editable=False, null=True)

    @property
    def num_competitors(self):
        '''
        Returns an integer count of the number of competitors in this game session,
        i.e. number of player sin a single-player mode or number of teams in team player mode
        '''
        if self.team_play:
            return len(self.teams)
        else:
            return len(self.players)

    @property
    def str_competitors(self):
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
    def players(self):
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
    def teams(self):
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
    def victors(self):
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
    def trueskill_impacts(self):
        '''
        Returns the recorded trueskill impacts of this session.
        Does not (re)calculate them.
        '''
        # TODO: Check that a performance record exists for each player explicitly
        # and if not, then trigger calculate_trueskill_impacts() to generate them.
        # Three scenarios:
        #    none exist:    just create them and return a summary of them
        #    all exist:     return a summary of them
        #    some exist:    flag a database inetrity error!
        impact = OrderedDict()
        for performance in self.performances.all():
            impact[performance.player] = OrderedDict([
                ('plays', performance.play_number),
                ('victories', performance.victory_count),
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
        return impact

    @property
    def trueskill_code(self):
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
        code.append("beta = {}".format(TSS.beta))
        code.append("delta = {}".format(TSS.delta))
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
    
    def previous_session(self, player):
        '''
        Returns the previous session that the nominate player played this game in. 
        Or None if no such session exists.
        '''
        # TODO: Test thoroughly. Tricky Query. 
        time_limit = self.date_time
        
        prev_sessions = Session.objects.filter(Q(date_time__lte=time_limit) & Q(game=self.game) & (Q(ranks__player=player) | Q(ranks__team__players=player))).order_by('-date_time')
        if len(prev_sessions) < 2:
            assert len(prev_sessions)==1, "Database error: Current session not in list, session={}, player={}".format(self.pk, player.pk)
            prev_session = None
        else:
            prev_session = prev_sessions[1]
            assert prev_sessions[0].date_time == self.date_time, "Query error: current session not in list for session={}, player={}".format(self.pk, player.pk)
            assert prev_session.date_time < self.date_time, "Database error: Two sessions with identical time, session={}, previous session={}, player={}".format(self.pk, prev_session.pk, player.pk)

        return prev_session

    def rank(self, player):
        '''
        Returns the Rank object for the nominated player in this session
        '''
        if self.team_play:
            ranks = self.ranks.filter(team__player=player)  # TODO: Test this, made it up on the fly, need to get the rank of the team the player is in. 
        else:
            ranks = self.ranks.filter(player=player)
            
        assert len(ranks) == 1, "Database error: {} Ranks objects in database for session={}, player={}".format(len(ranks), self.pk, player.pk)
        return ranks[0]

    def performance(self, player):
        '''
        Returns the Performance object for the nominated player in this session
        '''
        performances = self.performances.filter(player=player)
        assert len(performances) == 1, "Database error: {} Performance objects in database for session={}, player={}".format(len(performances), self.pk, player.pk)
        return performances[0]

    def previous_performance(self, player):
        '''
        Returns the previous Performance object for the nominate player in the game of this session
        '''
        prev_session = self.previous_session(player)
        return None if prev_session is None else prev_session.performance(player)
              
    def build_trueskill_data(self):
        '''Builds a the data structures needed by trueskill.rate
    
         A RatingGroup is list of dictionaries, one dictionary for each team
            keyed on the player name or ID containing a trueskill Rating object for that player
         In single player mode we simply supply teams of 1, so each dictionary has only one member.
         A trueskill Rating is just a trueskill mu and sigma pair (actually a Gaussian object with a mu and sigma).
         
        Weights is a dictionary, keyed on a player identifier with a weight as a value 
            The weights are 0 to 1, 0 meaning no play and 1 meaning full time play.
            The player identifier is is a tuple which has two values (RatingsGroup index, Key into that RatingsGroup dictionary)
            
        Ranking list is a list of ranks (1, 2, 3 for first, second, third etc) that maps item
            for item intok RatingGroup. Ties are indicated by repeating a given rank. 
         '''
        RGs = []
        Weights = {}
        Ranking = []
    
        # TODO: The Plan:
        # For each player in the game:
        #    Find the previous session of that game they played.
        #    Copy hte after ratings to hte before ratings here, 
        #    If not found use the inital setttings.
        
        if self.team_play:
            for rank, team in self.teams.items():
                RG = {}
                RGs.append(RG)
                for player in team.players.all():
                    performance = self.performance(player)
                    performance.initialise(save=True)
                    RG[player.pk] = trueskill.Rating(mu=performance.trueskill_mu_before, sigma=performance.trueskill_sigma_before)
                    Weights[(len(RGs) - 1, player.pk)] = performance.partial_play_weighting
                Ranking.append(int(rank.split('.')[0]))                   
        else:
            for rank, player in self.players.items():  # ordered dictionary of players keyed on rank
                performance = self.performance(player)
                performance.initialise(save=True)
                RGs.append({player.pk: trueskill.Rating(mu=performance.trueskill_mu_before, sigma=performance.trueskill_sigma_before)})
                Weights[(len(RGs) - 1, player.pk)] = performance.partial_play_weighting
                Ranking.append(int(rank.split('.')[0]))                   
        return RGs, Weights, Ranking        

    def calculate_trueskill_impacts(self):
        '''
        Given the rankings associated with this session (i.e. assuming they are recorded)
        and the trueskill measures for each player before the session will, calculate (and
        record against this session) on their basis the new trueskill measures.

        Saves the impacts to the database and returns a summary of impacts.
        '''
        TSS = TrueskillSettings()
        TS = trueskill.TrueSkill(mu=TSS.mu0, sigma=TSS.sigma0, beta=TSS.beta, tau=self.game.trueskill_tau, draw_probability=self.game.trueskill_p)

        def RecordRatingGroups(rating_groups):
            '''Given a rating_groups structure from trueskill.rate will distribute the results to the Performance objects

            The Trueskill impacts are extracted from the rating_groups recorded in Performance objects.
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

                    # Eta should already be in the database and at this value.
                    # TODO: Properly manage errors here.
                    # Eta can change if the global settings mu0 and sigma0 are changed.
                    # Changing those requires a full recalculation of ratings I suspect and is an onerous expensive task.
                    # So should be policed.
                    performance.trueskill_eta_before = performance.trueskill_mu_before - TSS.mu0 / TSS.sigma0 * performance.trueskill_sigma_before
                    performance.save()
                    
                    # TODO: save new rating for this player/game combo                   
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
        
        OldRatingGroups, Weights, Ranking = self.build_trueskill_data() 
        NewRatingGroups = TS.rate(OldRatingGroups, Ranking, Weights, TSS.delta)
        RecordRatingGroups(NewRatingGroups)

        return self.trueskill_impacts 

    add_related = ["Rank.session", "Performance.session"]  # When adding a session, add the related Rank and Performance objects
    def __unicode__(self): return u'{} - {} - {} - {} - {} {} ({} won)'.format(formats.date_format(self.date_time, 'DATETIME_FORMAT'), self.league, self.location, self.game, self.num_competitors, self.str_competitors, ", ".join([p.name_nickname for p in self.victors]))
    def __str__(self): return self.__unicode__()

    def save(self, *args, **kwargs):
        update_admin_fields(self)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-date_time']

class Rank(models.Model):
    '''
    The record, for a given Session of a Rank (i.e. 1st, 2nd, 3rd etc) for a specified Player or Team.

    Either a player or team is specified, neither or both is a data error.
    Which one, is specified in the Session model where a record is kept of whether this was a Team play session or not (i.e. Individual play)
    '''
    session = models.ForeignKey(Session, related_name='ranks')  # The session that this ranking belongs to
    rank = models.PositiveIntegerField()  # The rank (in this session) we are recording, as in 1st, 2nd, 3rd etc.

    # One or the other of these has a value the other should be null
    player = models.ForeignKey(Player, blank=True, null=True, related_name='ranks')  # The player who finished the game at this rank (1st, 2nd, 3rd etc.)
    team = models.ForeignKey(Team, blank=True, null=True, editable=False, related_name='ranks')  # if team play is recorded then a team is created (or used if already in database) to group the rankings of the team members.

    # Simple history and administrative fields
    created_by = models.ForeignKey('Player', related_name='ranks_created', editable=False, null=True)
    created_on = models.DateTimeField(editable=False, null=True)
    last_edited_by = models.ForeignKey('Player', related_name='ranks_last_edited', editable=False, null=True)
    last_edited_on = models.DateTimeField(editable=False, null=True)

    @property
    def players(self):
        '''
        The list of players associated with this rank object (not explicitly at this rank 
        as two Rank objects in one session may have the same rank, i.e. a draw may be recorded)
        
        Players in teams are listed individually.

        Returns a list of one one or more players.
        '''
        session = Session.objects.get(id=self.session.id)
        if session.team_play:
            if self.team is None:
                raise ValueError("Rank '{0}' is associated with a team play session but has no team.".format(self.id))
            else:
                players = self.team.players.all()
        else:
            if self.player is None:
                raise ValueError("Rank '{0}' is associated with an individual play session but has no player.".format(self.id))
            else:
                players = [self.player]
        return players

    @property
    def is_part_of_draw(self):
        '''
        Returns True or False, indicating whether or not more than one rank object on this session has the same rank
        (i.e. if this rank object is one part of a recorded draw).
        '''       
        ranks = Rank.objects.filter(session=self.session, rank=self.rank)
        return len(ranks) > 1

    add_related = ["player", "team"]  # When adding a Rank, add the related Players or Teams (if needed, or not if already in database)
    def __unicode__(self): return  u'{} - {} - {}'.format(self.session.game, self.rank, self.team if self.session.team_play else self.player)
    def __str__(self): return self.__unicode__()

    def save(self, *args, **kwargs):
        update_admin_fields(self)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['rank']

class Performance(models.Model):
    '''
    Each player in each session has a Performance associated with them.

    The only input here is the partial play weighting, which models just that, early departure from the game session before the game is complete.
    But can be used to arbitrarily weight contributions of players to teams as well if desired.

    This model also contains for each session a record of the calculated Trueskill performance of that player, namely trueskill values before
    and after the play (for data redundancy as the after values of one session are the before values of the next for a given player, which can
    also be asserted for data integrity).
    '''
    TS = TrueskillSettings()

    session = models.ForeignKey(Session, related_name='performances')  # The session that this weighting belongs to
    player = models.ForeignKey(Player, related_name='performances')  # The player in that session to whom the weighting applies

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

    # Simple history and administrative fields
    created_by = models.ForeignKey('Player', related_name='performances_created', editable=False, null=True)
    created_on = models.DateTimeField(editable=False, null=True)
    last_edited_by = models.ForeignKey('Player', related_name='performances_last_edited', editable=False, null=True)
    last_edited_on = models.DateTimeField(editable=False, null=True)

    @property
    def rank(self):
        '''
        The rank of this player in this session. Most certainly a component of a player's
        performance, but not stored in the Performance model because it is associated either
        with a player or whole team depending on the play mode (Individual or Team). So this
        property fetches the rank from the Rank model where it's stored.
        '''
        session = Session.objects.get(id=self.session.id)
        team_play = session.team_play
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
        
        if save:
            self.save()

    add_related = None
    sort_by = ['session', 'rank']
    def __unicode__(self): return  u'{} - {} - {:.0%} (play number {}, {:+.2f} teeth)'.format(self.session, self.player, self.partial_play_weighting, self.play_number, self.trueskill_eta_after - self.trueskill_eta_before)
    def __str__(self): return self.__unicode__()

    def save(self, *args, **kwargs):
        update_admin_fields(self)
        super().save(*args, **kwargs)

class Rating(models.Model):
    '''
    A Trueskill rating for a given Player at a give Game.

    This is the ultimate goal of the whole exercise. To record game sessions in order to calculate 
    ratings for players and rank them in leaderboards.
    
    Every player has a rating at every game, though only those deviating from default (i.e. games 
    that a player has players) are stored in the database. 
    
    The preferred way of fetinching a Rating is through Player.rating(game) or Game.rating(player). 
    '''
    player = models.ForeignKey(Player, related_name='ratings')
    game = models.ForeignKey(Game, related_name='ratings')

    plays = models.PositiveIntegerField('Play Count', default=0)
    victories = models.PositiveIntegerField('Victory Count', default=0)
    
    # Although Eta (η) is a simple function of Mu (µ) and Sigma (σ), we store it alongside Mu and Sigma because it is also a function of global settings µ0 and σ0.
    # To protect ourselves against changes to those global settings, or simply to detect them if it should happen, we capture their value at time of rating update in the Eta.
    # These values before each game session and their new values after a game session are stored with the Session Ranks for integrity and history plotting.
    trueskill_mu = models.FloatField('Trueskill Mean (µ)', default=trueskill.MU, editable=False)
    trueskill_sigma = models.FloatField('Trueskill Standard Deviation (σ)', default=trueskill.SIGMA, editable=False)
    trueskill_eta = models.FloatField('Trueskill Rating (η)', default=trueskill.SIGMA, editable=False)
    
    # Record the gloabl TrueskillSettings mu0, sigma0, beta and delta with each rating as an integrity measure.
    # They can be compared against the global settings and and difference can trigger an update request.
    # That is, flag a warning and if they are consistent across all stored ratings suggest TrueskillSettings
    # should be restored (and offer to do so?) or if inconsistent (which is an integrity error) suggest that
    # ratings be globally recalculated
    trueskill_mu0 = models.FloatField('Trueskill Initial Mean (µ)', default=trueskill.MU, editable=False)
    trueskill_sigma0 = models.FloatField('Trueskill Initial Standard Deviation (σ)', default=trueskill.SIGMA, editable=False)
    trueskill_beta = models.FloatField('TrueSkill Skill Factor (ß)', default=trueskill.BETA)
    trueskill_delta = models.FloatField('TrueSkill Delta (δ)', default=trueskill.DELTA)
    
    # Record the game specific Trueskill settings tau and p with rating as an integrity measure.
    # Again for a given game these must be consistent among all ratings and the history of each rating. 
    # And change while managing leaderboards should trigger an update request for ratings relating to this game.  
    trueskill_tau = models.FloatField('TrueSkill Dynamics Factor (τ)', default=trueskill.TAU)
    trueskill_p = models.FloatField('TrueSkill Draw Probability (p)', default=trueskill.DRAW_PROBABILITY)

    # Simple history and administrative fields
    created_by = models.ForeignKey('Player', related_name='ratings_created', editable=False, null=True)
    created_on = models.DateTimeField(editable=False, null=True)
    last_edited_by = models.ForeignKey('Player', related_name='ratings_last_edited', editable=False, null=True)
    last_edited_on = models.DateTimeField(editable=False, null=True)

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
                    trueskill_mu=trueskill_mu,
                    trueskill_sigma=trueskill_sigma,
                    trueskill_eta=trueskill_mu - TS.mu0 / TS.sigma0 * trueskill_sigma,  # µ − (µ0 ÷ σ0) × σ
                    trueskill_mu0=trueskill_mu,
                    trueskill_sigma0=trueskill_sigma,
                    )  
        return self
    
    @classmethod
    def update(self, player, game, plays, victories, mu, sigma):
        '''
        Update the rating for a given player at a game with the specified mu/sigma pair.
        
        Sensitive to the global (i.e. not game or league specific) TrueSkillSettings, 
        specifically mu0/sigma0 and so if they are ever changed, ratings need to 
        recalculated globally.
        '''
        TS = TrueskillSettings()
        
        try:
            r = Rating.objects.get(player=player, game=game)
        except ObjectDoesNotExist:
            r = Rating.create(player=player, game=game)
        except MultipleObjectsReturned:
            raise ValueError("Database error: more than one rating for {} at {}".format(player.name_nickname, game.name))
        
        if ((r.trueskill_mu0 != TS.mu0)  
         or (r.trueskill_sigma0 != TS.sigma0)
         or (r.trueskill_beta != TS.beta)
         or (r.trueskill_delta != TS.delta)
         or (r.trueskill_tau != game.trueskill_tau)
         or (r.trueskill_p != game.trueskill_p)):
            # TODO: Implement
            # Check for integrity (that there is only one distinct value of each in the Ratings store)
            # If present warn, sugessting either to fix TrueskillSettings or regenerate ratings.  
            # If only game specific settings changed need only regenerate ratings for that game.
            pass 
        
        r.plays = plays
        r.victories = victories
        
        r.trueskill_mu = mu
        r.trueskill_sigma = sigma
        r.trueskill_eta = r.trueskill_mu - TS.mu0 / TS.sigma0 * r.trueskill_sigma  # µ − (µ0 ÷ σ0) × σ
        
        r.trueskill_mu0 = TS.mu0
        r.trueskill_sigma0 = TS.sigma0
        r.trueskill_beta = TS.beta
        r.trueskill_delta = TS.delta
        r.trueskill_tau = game.trueskill_tau
        r.trueskill_p = game.trueskill_p
        
        r.save()

    @classmethod
    def update_from(self, session):
        '''
        Update a ratings for a given session 
        '''
        
        # TODO: the date_time of this session must be after all those of previously 
        # recorded sessions involving these players and this game. If it is not, if 
        # it's a session being inserted then this may require a rebuild of ratings 
        # from this session on.
        impact = session.calculate_trueskill_impacts()
        game = session.game
        
        for player in impact:
            plays = impact[player]["plays"]
            victories = impact[player]["victories"]
            mu = impact[player]["after"]["mu"]
            sigma = impact[player]["after"]["sigma"]
            
            if game.name == "COGZ":
                print("-> ", session.pk, session.date_time, session.game.name, player, victories)
            
            self.update(player, game, plays, victories, mu, sigma)
    
    @classmethod
    def check_integrity(self):
        # TODO: Implement
        # Check for integrity (that there is only one distinct value of each in the Ratings store)
        pass
    
    @classmethod
    def rebuild_all(self):
        # TODO: Implement
        # Walk through the history of sessions to rebuild all ratings
        # If ever performed keep a record of duration overall and per 
        # session tp permit a cost esitmate should it happen again. 
        # On a large database this could be a costly exercise, causing
        # some down time to the server (must either lock server to do 
        # this as we cannot have new ratings being created while 
        # rebuilding or we could have the update method above check
        # if a rebuild is underway and if so schedule an update ro
        
        # Copy the whole Ratings table to a backup table
        # Erase the current table
        # Walk through the sessions in chronological order rebuilding it.
        
        self.objects.all().delete()
        sessions = Session.objects.all().order_by('date_time')
        
        # Traverse sessions in chronological order (order_by is the time of the session) and update ratings from each session
        for s in sessions:
            print(s.pk, s.date_time, s.game.name)
            self.update_from(s)
    
    def __unicode__(self): return  u'{} - {} - {:f} teeth, from (µ={:f}, σ={:f} after {} plays)'.format(self.player, self.game, self.trueskill_eta, self.trueskill_mu, self.trueskill_sigma, self.plays)
    def __str__(self): return self.__unicode__()
        
    class Meta:
        ordering = ['-trueskill_eta']
        
