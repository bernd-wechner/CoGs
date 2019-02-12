'''
Created on 8Mar.,2018

@author: Bernd Wechner
@status: Alpha - works and is in use on a dedicated project. Is not complete, and needs testing for generalities.

Provides a class, AdminModel which is an abstract Django model that a model can derive from to inherit 
some admin fields and a save override that keeps the up to date. Intended for recording some user and time 
info against every record saved.
'''

from cuser.middleware import CuserMiddleware
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings
from django.utils.timezone import get_current_timezone

class AdminModel(models.Model):
    '''
    An abstract model that adds some admin fields and overrides the save method to ensure that on every 
    save these fields are updated (who and when) 
    '''
    # Simple history and administrative fields
    created_by = models.ForeignKey(User, verbose_name='Created By', related_name='%(class)ss_created', editable=False, null=True, on_delete=models.SET_NULL)
    created_on = models.DateTimeField('Time of Creation', editable=False, null=True)
    created_on_tz = models.CharField('Time of Creation, Timezone', max_length=settings.TIME_ZONE_NAME_MAXLEN, default=settings.TIME_ZONE, editable=False)

    last_edited_by = models.ForeignKey(User, verbose_name='Last Edited By', related_name='%(class)ss_last_edited', editable=False, null=True, on_delete=models.SET_NULL)
    last_edited_on = models.DateTimeField('Time of Last Edit', editable=False, null=True)
    last_edited_on_tz = models.CharField('Time of Last Edit, Timezone', max_length=settings.TIME_ZONE_NAME_MAXLEN, default=settings.TIME_ZONE, editable=False)
    
    def update_admin_fields(self):
        '''
        Update the CoGs admin fields on an object (whenever it is saved).
        '''
        now = timezone.now()
        usr = CuserMiddleware.get_user()
    
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
                
    def save(self, *args, **kwargs):
        self.update_admin_fields()
        super().save(*args, **kwargs)
                
    class Meta:
        get_latest_by = "created_on"
        abstract = True
