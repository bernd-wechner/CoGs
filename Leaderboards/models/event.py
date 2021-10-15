from django.db import models
from django.utils import timezone

from django_model_admin_fields import AdminModel


class Event(AdminModel):
    '''
    A model for defining gaming events. The idea being that we can show all leaderboards
    relevant to a particular event (games and tourneys) and specify the time bracket and
    venue for the event so that the recorded game sessions belonging to they event can
    be inferred.

    Timezones are ignored as they are inferred from the Location which has a timezone.
    '''
    # TODO: Events should have names (optionally), and Notes
    location = models.ForeignKey('Location', verbose_name='Event location', null=True, blank=-True, on_delete=models.SET_NULL)  # If the location is deleted keep the event.
    start = models.DateTimeField('Time', default=timezone.now)
    end = models.DateTimeField('Time', default=timezone.now)
    registrars = models.ManyToManyField('Player', verbose_name='Registrars', blank=True, related_name='registrar_at')

    class Meta(AdminModel.Meta):
        verbose_name = "Event"
        verbose_name_plural = "Events"
