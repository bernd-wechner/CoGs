from django.contrib import admin
from django.apps import apps
from django.contrib.admin.sites import AlreadyRegistered

admin.site.site_title = "CoGs"
admin.site.site_header = "CoGs Leaderboard Server Administration"

# Registers all knwon models 
# (probably more than we want on a production site
# but awesome for development).
for model in apps.get_models():
    try:
        admin.site.register(model)
    except AlreadyRegistered:
        pass

#from .models import TrueskillSettings, Game, League, Team, Location, Player, Session, Rank, Performance, Rating
#
# class TrueskillSettingsAdmin(admin.ModelAdmin):
#     list_display = ['mu0', 'sigma0', 'beta', 'delta']
# 
# class LeagueAdmin(admin.ModelAdmin):
#     list_display = ('name', 'manager')
#     search_fields = ('name', 'manager')
# 
# class TeamAdmin(admin.ModelAdmin):
#     list_display = ['name']
#     search_fields = ['name']
# 
# class LocationAdmin(admin.ModelAdmin):
#     list_display = ['name']
#     search_fields = ['name']
# 
# class PlayerAdmin(admin.ModelAdmin):
#     list_display = ('name_nickname', 'name_family', 'name_personal', 'email_address')
#     search_fields = ('name_nickname', 'name_family', 'name_personal', 'email_address')
# 
# class GameAdmin(admin.ModelAdmin):
#     list_display = ('name', 'BGGid')
#     search_fields = ['name']
# 
#     def suit_cell_attributes(self, obj, column):
#         return {'class': 'text-error'}
# 
# class SessionAdmin(admin.ModelAdmin):
#     list_display = ('date_time', 'location', 'league', 'game', 'team_play')
#     search_fields = ('date_time', 'location', 'league', 'game')
# 
# class RankAdmin(admin.ModelAdmin):
#     list_display = ('session', 'rank', 'player', 'team')
# 
# class PerformanceAdmin(admin.ModelAdmin):
#     list_display = ('session', 'player', 'partial_play_weighting', 'trueskill_mu_before', 'trueskill_sigma_before', 'trueskill_mu_after', 'trueskill_sigma_after')
# 
# class RatingAdmin(admin.ModelAdmin):
#     list_display = ('player', 'game', 'trueskill_mu', 'trueskill_sigma')
#     search_fields = ('player', 'game')
# 
# admin.site.register(TrueskillSettings, TrueskillSettingsAdmin)
# admin.site.register(League, LeagueAdmin)
# admin.site.register(Team, TeamAdmin)
# admin.site.register(Game, GameAdmin)
# admin.site.register(Location, LocationAdmin)
# admin.site.register(Player, PlayerAdmin)
# admin.site.register(Session, SessionAdmin)
# admin.site.register(Rank, RankAdmin)
# admin.site.register(Performance, PerformanceAdmin)
# admin.site.register(Rating, RatingAdmin)
