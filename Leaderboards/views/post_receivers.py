#===============================================================================
# Receive POSTed information. Part of the AJAX interface, these are how
# the client side JavaScript submits information about the client and user
# using it.
#===============================================================================
import pytz

from datetime import datetime
from geopy.geocoders import Nominatim
from http import HTTPStatus

from django.conf import settings
from django.http.response import HttpResponse
from django.utils.timezone import activate

from Site.logutils import log

from .site import save_league_filters


def receive_ClientInfo(request):
    '''
    A view that returns (presents) nothing, is not a view per se, but much rather just
    accepts POST data and acts on it. This is specifically for receiving client
    information via an XMLHttpRequest bound to the DOMContentLoaded event on site
    pages which asynchonously and silently in the background on a page load, posts
    the client information here.

    The main aim and r'aison d'etre for this whole scheme is to divine the users
    timezone as quickly and easily as we can, when they first surf in, to whatever
    URL. Of course that first page load will take place with an unknown timezone,
    but subsequent to it we'll know their timezone.

    Implemented as well, just for the heck of it are acceptors for UTC offset, and
    geolocation, that HTML5 makes available, which can be used in logging site visits.
    '''
    if (request.POST):
        if "clear_session" in request.POST:
            if settings.DEBUG:
                log.debug(f"ClientInfo received - referrer = {request.META.get('HTTP_REFERER')}")
            session_keys = list(request.session.keys())
            for key in session_keys:
                del request.session[key]
            return HttpResponse("<script>window.history.pushState('', '', '/session_cleared');</script>")

        # Check for the timezone
        if "timezone" in request.POST:
            if settings.DEBUG:
                log.debug(f"ClientInfo received - Timezone = {request.POST['timezone']}")
            request.session['timezone'] = request.POST['timezone']
            activate(request.POST['timezone'])

            # To help any map boxes that may be in use we add to the session some
            # framing and positioning info
            try:
                tz = pytz.timezone(request.POST['timezone'])
                country, city = tz.zone.split('/')
                geolocator = Nominatim(user_agent=settings.SITE_TITLE)
                location = geolocator.geocode(f"{city}, {country}")
                box, point = location.raw['boundingbox'], location.point
                request.session['geo_point'] = point
                request.session['geo_box'] = box
                if settings.DEBUG:
                    log.debug(f"\tdecoded geolocation as: {point=}, {box=}")
            except Exception as E:
                pass

        if "utcoffset" in request.POST:
            if settings.DEBUG:
                log.debug(f"ClientInfo received - UTC offset = {request.POST['utcoffset']}")
            request.session['utcoffset'] = request.POST['utcoffset']

        if "location" in request.POST:
            if settings.DEBUG:
                log.debug(f"ClientInfo received - location = {request.POST['location']}")
            request.session['location'] = request.POST['location']

            try:
                geolocator = Nominatim(user_agent=settings.SITE_TITLE)
                location = geolocator.geocode(request.POST['location'])
                box, point = location.raw['boundingbox'], location.point
                request.session['geo_point'] = point
                request.session['geo_box'] = box
                if settings.DEBUG:
                    log.debug(f"\tdecoded geolocation as: {point=}, {box=}")
            except Exception as E:
                pass

    return HttpResponse(status=HTTPStatus.NO_CONTENT)


def receive_Filter(request):
    '''
    A view that returns (presents) nothing, is not a view per se, but much rather just
    accepts POST data and acts on it. This is specifically for receiving filter
    information via an XMLHttpRequest.

    The main aim and r'aison d'etre for this whole scheme is to provide a way to
    submit view filters for recording in the session.
    '''
    if (request.POST):
        # Check for league
        if "league" in request.POST:
            if settings.DEBUG:
                log.debug(f"League = {request.POST['league']}")
            save_league_filters(request.session, int(request.POST.get("league", 0)))

    return HttpResponse()


def receive_DebugMode(request):
    '''
    A view that returns (presents) nothing, is not a view per se, but much rather just
    accepts POST data and acts on it. This is specifically for receiving a debug mode
    flag via an XMLHttpRequest when debug mode is changed.
    '''
    if (request.POST):
        # Check for league
        if "debug_mode" in request.POST:
            request.session["debug_mode"] = True if request.POST.get("debug_mode", "false") == 'true' else False

    return HttpResponse()
