#===============================================================================
# An event viewer and summariser
#===============================================================================
# import pytz

from django.shortcuts import render

from ..models import Event


def view_Events(request):
    '''
    Two types of event are envisaged.

    1. The implicit event of n days duration (nominally 1 for a games night)
        we could default to "flexible" when no duration is specifed.
        League and location filters are important
        "flexible" could walk backwards in time, through sessions meeting the
            filter, and fidning one pegging an end of event then walkimg backwards
            until a game of more than 1 day is found and pegging an event start
            there.

    2. The explicit event (from the events model) - not yet in use.
    '''
    # The user request
    urequest = request.GET

    # Fetch the user-session preferred timezone
    # utz = pytz.timezone(request.session.get("timezone", "UTC"))

    # Fetch the user-session filter
    ufilter = request.session.get('filter', {})

    # TODO check if we can specify NO league filtering. That is where does preferred league come from?
    # This is in leaderboards view as well with same request to check behaviour
    leagues = []
    preferred_league = ufilter.get('league', None)
    if 'leagues' in urequest:
        sleagues = urequest['leagues']  # CSV string
        if sleagues:
            leagues = list(map(int, sleagues.split(",")))  # list of ints

        if preferred_league and not leagues:
            leagues = [preferred_league]

    # We support a locatoion filter as well
    locations = []
    preferred_location = ufilter.get('location', None)
    if 'locations' in urequest:
        slocations = urequest['locations']  # CSV string
        if slocations:
            locations = list(map(int, slocations.split(",")))  # list of ints

        if preferred_location and not locations:
            locations = [preferred_location]

    # Suppport for a date range
    date_from = urequest.get("from", None)
    date_to = urequest.get("to", None)

    # TODO: As this could be an expensive report, we should cache the results
    # somehow. Could go same way as leaderboards in the user session.

    # We support a num_days option identical to that used by leaderboard_options
    # meaning we will consider an event any block of days with recorded sessions
    # of up to num_days.
    num_days = urequest.get("num_days", None)

    # The number of days between sessions that breaks session groups no into events.
    gap_days = urequest.get("num_days", 1)

    events = Event.implicit(leagues, locations, date_from, date_to, num_days, gap_days)
    stats = Event.stats(events)

    filter = {}  # @ReservedAssignment
    if leagues: filter["leagues"] = leagues
    if locations: filter["locations"] = locations
    if date_from: filter["date_from"] = date_from
    if date_to: filter["date_to"] = date_to
    if num_days: filter["num_days"] = num_days
    if gap_days: filter["gap_days"] = gap_days

    c = {"title": "Game Events",
         "events": events,
         "stats": stats,
         "filter": filter
         }

    return render(request, 'views/events.html', context=c)
