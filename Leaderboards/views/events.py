#===============================================================================
# An event viewer and summariser
#===============================================================================
import json, re

from django.shortcuts import render
from django.http.response import HttpResponse
from django.template.loader import render_to_string
from django.core.serializers.json import DjangoJSONEncoder

from dal import autocomplete

from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models.callbacks import CustomJS

from ..models import Event, League, Location, ALL_LEAGUES, ALL_LOCATIONS

from .widgets import html_selector


def view_Events(request):
    return render(request, 'views/events.html', context=ajax_Events(request, raw=True))


def ajax_Events(request, raw=False):
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
    date_from = urequest.get("date_from", None)
    date_to = urequest.get("date_to", None)

    # Support a duration filer
    duration_min = urequest.get("duration_min", None)
    duration_max = urequest.get("duration_max", None)

    # The week day reestrictions if any
    week_days = urequest.get("week_days", None)

    # The number of days between sessions that breaks session groups into events.
    gap_days = float(urequest.get("gap_days", 1))

    # Collect the implcit events
    events = Event.implicit(leagues, locations, date_from, date_to, duration_min, duration_max, week_days, gap_days)

    # And some stats about them
    stats = Event.stats(events)

    # Build a graph (test for now)
    (players, frequency) = Event.frequency("players", events, as_lists=True)

    # We need include the graph only on a raw call (the inital page load), not on
    # AJAZ calls (that return the data update)
    if raw:
        plot = figure(height=350,
                      x_axis_label="Count of Players",
                      y_axis_label="Number of Events",
                      background_fill_alpha=0,
                      border_fill_alpha=0,
                      tools="pan,wheel_zoom,box_zoom,save,reset")

        plot.xaxis.ticker = list(range(min(players), max(players) + 1))
        plot.yaxis.ticker = list(range(0, max(frequency) + 1))
        plot.toolbar.logo = None

        plot.y_range.start = 0

        bars = plot.vbar(x=players, top=frequency, width=0.9)

        # This example is good: https://docs.bokeh.org/en/latest/docs/user_guide/interaction/callbacks.html#customjs-for-widgets
        # But not perfect. How to trigger that onchange in JS?
        bars.data_source.js_on_change("change", CustomJS(args=dict(xticker=plot.xaxis.ticker, yticker=plot.yaxis.ticker), code="""
            //console.log("DEBUG! Data source changed!");
            const startx = Math.min(...players); const endx = Math.max(...players);
            const starty = 0;                    const endy = Math.max(...frequency);

            xticker.ticks = _.range(startx, endx+1);
            yticker.ticks = _.range(starty, endy+1);
            //debugger;
        """))

        graph_script, graph_div = components(plot)

    settings = {}  # @ReservedAssignment
    if leagues: settings["leagues"] = leagues
    if locations: settings["locations"] = locations
    if date_from: settings["date_from"] = date_from
    if date_to: settings["date_to"] = date_to
    if duration_min: settings["duration_min"] = duration_min
    if duration_max: settings["duration_max"] = duration_max
    if gap_days: settings["gap_days"] = gap_days

    context = {"title": "Game Events",
               "events": events,
               "stats": stats,
               "settings": settings,
               "players": players,
               "frequency": frequency,
               "DEBUG_BokeJS": True
               }

    if raw:
        # Widgets and the graph and the ID of the graph all only needed on page load not in the JSON
        # returned to AJAX callers (only apage that ghas all these should be calling back anyhow)
        context.update({"dal_media": autocomplete.Select2().media,
                        "widget_leagues": html_selector(League, "leagues", settings.get("leagues", None), ALL_LEAGUES),
                        "widget_locations": html_selector(Location, "locations", settings.get("locations", None), ALL_LOCATIONS),
                        "graph_script": graph_script,
                        "graph_div": graph_div,
                        "plotid": plot.id})

        return context
    else:
        events_table = render_to_string("include/events_table.html", context).strip()
        events_stats_table = render_to_string("include/events_stats_table.html", context).strip()
        return HttpResponse(json.dumps((events_table, events_stats_table, settings, players, frequency), cls=DjangoJSONEncoder))
