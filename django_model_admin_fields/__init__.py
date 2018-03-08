'''
Created on 8Mar.,2018

@author: Bernd Wechner
@status: Alpha - works and is in use on a dedicated project. Is not complete, and needs testing for generalities.

Provides on class, AdminModel which is an abstract Django model that a model cna derive from to inherit 
some admin fields and a save override that keeps the up to date. Intended for recording some user and time 
info against every record saved.

TODO: Document here
'''

from cuser.middleware import CuserMiddleware
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

class AdminModel(models.Model):
    '''
    An abstract model that adds some admin fields and overrides the save method to ensure that on every 
    save these fields are updated (who and when) 
    '''
    # Simple history and administrative fields
    created_by = models.ForeignKey(User, related_name='%(class)ss_created', editable=False, null=True)
    created_on = models.DateTimeField(editable=False, null=True)
    last_edited_by = models.ForeignKey(User, related_name='%(class)ss_last_edited', editable=False, null=True)
    last_edited_on = models.DateTimeField(editable=False, null=True)
    
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
    
        # We infer that if the object has pk it was being edited and if it has none it was being created
        if self.pk is None:
            if hasattr(self, "created_by"):
                self.created_by = usr
    
            if hasattr(self, "created_on"):
                self.created_on = now

    def save(self, *args, **kwargs):
        self.update_admin_fields()
        super().save(*args, **kwargs)
                
    class Meta:
        abstract = True
