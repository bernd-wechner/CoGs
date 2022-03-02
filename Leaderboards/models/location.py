from . import APP, MAX_NAME_LENGTH

from django.db import models
from django.conf import settings
from django.apps import apps
from django.urls import reverse

from django_model_admin_fields import AdminModel

from django_generic_view_extensions.model import field_render

from timezone_field import TimeZoneField

from mapbox_location_field.models import LocationField

League  = apps.get_model(APP, "League", require_ready=False)

class Location(AdminModel):
    '''
    A location that a game session can take place at.
    '''
    name = models.CharField('Name of the Location', max_length=MAX_NAME_LENGTH)
    timezone = TimeZoneField('Timezone of the Location', default=settings.TIME_ZONE)
    location = LocationField('Geolocation of the Location', blank=True)
    leagues = models.ManyToManyField('League', verbose_name='Leagues using the Location', blank=True, related_name='Locations_used', through=League.locations.through)

    @property
    def link_internal(self) -> str:
        return reverse('view', kwargs={"model":self._meta.model.__name__, "pk": self.pk})

    selector_field = "name"

    @classmethod
    def selector_queryset(cls, query="", session={}, all=False):  # @ReservedAssignment
        '''
        Provides a queryset for ModelChoiceFields (select widgets) that ask for it.
        :param cls: Our class (so we can build a queryset on it to return)
        :param query: A simple string being a query that is submitted (typically typed into a django-autcomplete-light ModelSelect2 or ModelSelect2Multiple widget)
        :param session: The request session (if there's a filter recorded there we honor it)
        :param all: Requests to ignore any default league filtering
        '''
        qs = cls.objects.all()

        if not all:
            league = session.get('filter', {}).get('league', None)
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

    def __rich_str__(self, link=None):
        leagues = list(self.leagues.all())
        leagues = list(map(lambda l: field_render(l, link), leagues))
        return u"{} (used by: {})".format(field_render(self, link), ", ".join(leagues))

    class Meta(AdminModel.Meta):
        verbose_name = "Location"
        verbose_name_plural = "Locations"
        ordering = ['name']