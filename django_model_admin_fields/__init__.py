'''
Created on 8Mar.,2018

@author: Bernd Wechner
@status: Alpha - works and is in use on a dedicated project. Is not complete, and needs testing for generalities.

Provides a class, AdminModel which is an abstract Django model that a model can derive from to inherit
some admin fields and a save override that keeps the up to date. Intended for recording some user and time
info against every record saved.
'''
import pytz

from django_currentuser.middleware import get_current_user
from timezone_field import TimeZoneField

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings
from django.utils.timezone import get_current_timezone

UTC = pytz.timezone('UTC')


def safe_tz(tz):
    '''A one-line that converts TZ string to a TimeZone object if needed'''
    return pytz.timezone(tz) if isinstance(tz, str) else tz


class AdminModel(models.Model):
    '''
    An abstract model that adds some admin fields and overrides the save method to ensure that on every
    save these fields are updated (who and when)
    '''
    # Simple history and administrative fields
    created_by = models.ForeignKey(User, verbose_name='Created By', related_name='%(class)ss_created', editable=False, null=True, on_delete=models.SET_NULL)
    created_on = models.DateTimeField('Time of Creation', editable=False, null=True)
    created_on_tz = TimeZoneField('Time of Creation, Timezone', default=settings.TIME_ZONE, editable=False)

    last_edited_by = models.ForeignKey(User, verbose_name='Last Edited By', related_name='%(class)ss_last_edited', editable=False, null=True, on_delete=models.SET_NULL)
    last_edited_on = models.DateTimeField('Time of Last Edit', editable=False, null=True)
    last_edited_on_tz = TimeZoneField('Time of Last Edit, Timezone', default=settings.TIME_ZONE, editable=False)

    # A flag for bypassing admin field updates. This is used for adminstrative
    # tasks, like database maintenance and rebuilds where we want to save things
    # but conserve the record of actual user edits etc.
    __bypass_admin__ = False

    def update_admin_fields(self):
        '''
        Update the CoGs admin fields on an object (whenever it is saved).
        '''
        now = timezone.now()
        usr = get_current_user()

        if hasattr(self, "last_edited_by"):
            self.last_edited_by = usr

        if hasattr(self, "last_edited_on"):
            self.last_edited_on = now

        if hasattr(self, "last_edited_on_tz"):
            self.last_edited_on_tz = str(get_current_timezone())

        # We infer that if the object has pk it was being edited and if it has none it was being created
        if self.pk is None:
            if hasattr(self, "created_by"):
                self.created_by = usr

            if hasattr(self, "created_on"):
                self.created_on = now

            if hasattr(self, "created_on_tz"):
                self.created_on_tz = str(get_current_timezone())

    @property
    def created_on_local(self):
        return self.created_on.astimezone(safe_tz(self.created_on_tz))

    @property
    def last_edited_on_local(self):
        return self.last_edited_on.astimezone(safe_tz(self.last_edited_on_tz))

    def save(self, *args, **kwargs):
        if not self.__bypass_admin__:
            self.update_admin_fields()
        super().save(*args, **kwargs)

    class Meta:
        get_latest_by = "created_on"
        abstract = True
