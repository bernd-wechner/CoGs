# -*- coding: utf-8 -*-
# code is in the public domain
#
# ./manage.py clear_leaderbord_cache
u'''

Management command to clear the leaderboard cache

Usage: manage.py clear_leaderbord_cache
'''
from django.core.management.base import BaseCommand
from django.db.transaction import atomic

from Leaderboards.models.leaderboards import Leaderboard_Cache

class Command(BaseCommand):
    @atomic
    def handle(self, *args, **options):
        Leaderboard_Cache.clear()