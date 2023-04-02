from . import APP, MAX_NAME_LENGTH, visibility_options

from geopy.distance import GeodesicDistance
from geopy.point import Point
from random import random

from Import.models import Import

from django.db import models
from django.conf import settings
from django.apps import apps
from django.urls import reverse

from django_model_admin_fields import AdminModel
from django_model_privacy_mixin import PrivacyMixIn

from django_rich_views.model import field_render, NotesMixIn

from timezone_field import TimeZoneField

from mapbox_location_field.models import LocationField

from bitfield import BitField

League = apps.get_model(APP, "League", require_ready=False)

DefaultGeoLocationBlurRadius = 500 # meters

class Location(AdminModel, PrivacyMixIn, NotesMixIn):
    '''
    A location that a game session can take place at.
    '''
    name = models.CharField('Name of the Location', max_length=MAX_NAME_LENGTH)
    timezone = TimeZoneField('Timezone of the Location', default=settings.TIME_ZONE)
    location = LocationField('Geolocation of the Location', blank=True)
    leagues = models.ManyToManyField('League', verbose_name='Leagues using the Location', blank=True, related_name='Locations_used', through=League.locations.through)

    # PrivacyMixIn `visibility_` atttributes to configure visibility of possibly "private" fields
    # the geolocation is subject to rpivacy constraints. Being a LocationFiedl we'd want to offer
    # a blurred map in preference to hiding it completely, and not display hte lat/lon.
    visibility_location = BitField(visibility_options, verbose_name='Geolocation Visibility', default=('all',), blank=True)
    blur_radius = models.FloatField('Radius of Uncertainy for Hidden Locations', blank=True, null=True)

    # Optionally associate with an import. We call it "source" and if it is null (none)
    # this suggests not imported but entered directly through the UI.
    source = models.ForeignKey(Import, verbose_name='Source', related_name='locations', blank=True, null=True, on_delete=models.SET_NULL)

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

    intrinsic_relations = None

    def hide(self, field):
        '''
        PrivacyMixIn calls this if a field need hiding (for privacy reasons)

        This is our chance to tweak the defintion of hidden. Specifically for the location field,
        we want to blur the presentation, show a map that is "roughly" where the location is and
        not show the lat/lon.

        :param field:    The field
        '''
        value = getattr(self, field.name)
        form_field = field.formfield()
        form_widget = form_field.widget

        if isinstance(field, LocationField):
            # define a circle of uncertainty
            lon, lat = value
            bear = 360 * random()
            blur = self.blur_radius if self.blur_radius else DefaultGeoLocationBlurRadius
            dist  = blur * random()
            new_point = GeodesicDistance(meters=dist).destination(Point(lat, lon), bearing=bear)
            # We return the new point with an ancillary blur radius.
            # Note, the django-mapbox-location-field that we use takes points
            # a (lon, lat) and geopy as (lat, lon). Easy to get confused.
            # By adding a new element to the tuple renderers may need to take note.
            # Notably the form_widget ...
            return (new_point.longitude, new_point.latitude, blur)

        return PrivacyMixIn.HIDDEN

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
