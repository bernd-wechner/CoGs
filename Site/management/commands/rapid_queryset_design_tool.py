# -*- coding: utf-8 -*-
# code is in the public domain
#
# ./manage.py clear_leaderbord_logs
u'''

Management command to for rapid queryset design

Best used in a debugger. Edit, run, edit run etc, to see what the SQL produced is.

Useful for complicated queries involving Subquery, nested ones even, and OuterRefs etc.
'''
from django.conf import settings
from django.db.transaction import atomic
from django.core.management.base import BaseCommand

from django.db.models import Q, Subquery, OuterRef, PositiveIntegerField, Count

from Leaderboards.models import Session, Performance, Game, League, Player

from django_rich_views.queryset import print_SQL

class SubqueryCount(Subquery):
    # Custom Count function to just perform simple count on any queryset without grouping.
    # https://stackoverflow.com/a/47371514/1164966
    template = "(SELECT count(*) FROM (%(subquery)s) _count)"
    output_field = PositiveIntegerField()

class Command(BaseCommand):
    @atomic
    def handle(self, *args, **options):
        #games = Game.objects.filter(Q(sessions__performances__player=1)).annotate(count=Count('id')).order_by('-count')
        
        # performances = Performance.objects.filter(session__game=29)  # @UndefinedVariable
        # total = performances.count() 
        # players = performances.values('player').distinct().order_by().count()
        # max_perfs = performances.values('player').annotate(count=Count('player')).order_by('-count')[0]['count']
        # avg_perfs = total//players        
        
        
        # This was the design of the Game annotations for leaderboard sorting on popularity (for the count_cross-league_plays option.
        # s_filter = Q(league=1)
        # game_sessions = Session.objects.filter(s_filter, game=OuterRef(OuterRef(OuterRef("id")))).values('id').order_by()
        # player_list = Session.objects.filter(id__in=Subquery(game_sessions), game=OuterRef(OuterRef("id"))).values_list('performances__player__id', flat=True).distinct().order_by()
        # p_filter = Q(player__in=Subquery(player_list))
        # all_game_plays = Performance.objects.filter(session__game=OuterRef("id")).filter(p_filter).values('id').order_by()
        # print_SQL(Game.objects.annotate(play_count=SubqueryCount(all_game_plays)).values('id', 'play_count').order_by())

        # We have these groups of plays:
        #    ii. In-league plays for in-league players 
        #    oi. Out-of-league plays for in-league players 
        #    io. In-league plays for out-of-league players
        #    oo. Out-of-league plays for out-of-league players 
        #    ooi. Out-of-league plays for out-of-league players who have in-league play(s)
        #
        # We should technically be able to write queries for:
        #    ii-io - the simple count (every in league play is a vote)
        #    ii-oi - the better simple count (every play by an in-league player is a vote) 
        #    ii-oi-io-ooi - the holistic count (every play by anyone who's played in-league is a vote) (excludes oo!i)
        #    ii-oi-io-oo - is global and has no league filtering in place! It's evey play!
        #
        # ii-io and ii-oi I implemented originally as narrow and broad. Then discovered ii-oi-io-ooi while designing the query! Doh!
        #
        # Seen another way there are these votes cast:
        #
        # All plays of in-league sessions (ii-io)
        # All plays by in-league players (ii-oi)
        # All plays by in-league sessions players (ii-oi-io-ooi)
        #
        # Methinks on the site we'll stick with ii-io and ii-oi
        # ii-io was my orginal easy implementation:
        # ii-oi was what I tried to design above but got wrong and is too complciated for ii-oi
        #
        # So this is an ii-oi query test: 

        # The sleek version
        all_game_plays = Performance.objects.filter(session__game=OuterRef("id"), player__leagues__in=[1]).values('id').order_by()
        print_SQL(Game.objects.annotate(play_count=SubqueryCount(all_game_plays)).values('id', 'play_count').order_by())

        # My oddly complicated version which I think I build aimng for the ii-oi-io-ooi scenario bu actually produced ii-oi
        # But for some reason this oddly constructed one returns a slightly smaller count on some games. Not sure why.
        # 
        # This gets all the players who've played an in_league game and then counts their performances at that game. 
        # How can it miss perforamnces (it seems to)
        s_filter = Q(league=1)
        game_sessions = Session.objects.filter(s_filter, game=OuterRef(OuterRef(OuterRef("id")))).values('id').order_by()
        player_list = Session.objects.filter(id__in=Subquery(game_sessions), game=OuterRef(OuterRef("id"))).values_list('performances__player__id', flat=True).distinct().order_by()
        p_filter = Q(player__in=Subquery(player_list))
        all_game_plays = Performance.objects.filter(session__game=OuterRef("id")).filter(p_filter).values('id').order_by()
        print_SQL(Game.objects.annotate(play_count=SubqueryCount(all_game_plays)).values('id', 'play_count').order_by())
         
        # Game 10 for example returns 1 play for the first query, and 0 for the second. So drill down.
        check = Performance.objects.filter(session__game_id=10).values('id','player_id', 'session__league_id', 'player__leagues')
        print_SQL(check)
        # There are 2 performance on game 10 
        check = Performance.objects.filter(session__game_id=10, session__league_id=1).values('id','player_id')
        print_SQL(check)
        # None neither of those performances is in aleague 1 session, only a league 3 session.
        # But one of the players is in league 1. 
        # So the difference is that the broken one is in fact looking at in_league sesssions 
        # finding the players in those (including visitors) and then counting all their erformances).
        # It therefore is a not excaclty any of io patterns! Approximates iio ;-)
        #
        # This is iio:
        iioo = Game.objects.annotate(play_count=Count('sessions__performances', distinct=True, filter=Q(sessions__league__in=[1]))).values('id', 'play_count').order_by()
        print_SQL(iioo)
        # But it's not, this one has much smaller counts!

        x=1
