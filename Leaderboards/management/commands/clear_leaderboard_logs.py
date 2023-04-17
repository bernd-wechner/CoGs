# -*- coding: utf-8 -*-
# code is in the public domain
#
# ./manage.py clear_leaderbord_logs
u'''

Management command to clear the change and rebuild logs

Usage: manage.py clear_leaderbord_logs
'''
from django.core.management.base import BaseCommand
from django.db.transaction import atomic

from Leaderboards.models.log import ChangeLog, RebuildLog


class Command(BaseCommand):
    @atomic
    def handle(self, *args, **options):
        ChangeLog.clear()
        RebuildLog.clear()