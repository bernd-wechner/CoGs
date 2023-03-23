#===============================================================================
# An event viewer and summariser
#===============================================================================
import json, re

from django.http.response import HttpResponse
from django.core.serializers.json import DjangoJSONEncoder
from django.conf import settings as django_settings

from django_rich_views.render import rich_render, rich_render_to_string

from dal import autocomplete

from bokeh import __version__ as bokeh_version
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models.callbacks import CustomJS

from ..models import Event, League, Location, ALL_LEAGUES, ALL_LOCATIONS

from .widgets import html_selector
from django.utils.safestring import mark_safe


def view_Events(request):
    return rich_render(request, 'views/events.html', context=ajax_Events(request, as_context=True))


def ajax_Events(request, as_context=False):
    '''
    Two types of event are envisaged.

    1. The implicit event of n days duration (nominally 1 for a games night)
        we could default to "flexible" when no duration is specifed.
        League and location filters are important
        "flexible" could walk backwards in time, through sessions meeting the
            filter, and finding one pegging an end of event then walkimg backwards
            until a game of more than 1 day is found and pegging an event start
            there.

    2. The explicit event (from the events model) - not yet in use.
    '''
    # Fetch the user-session filter
    ufilter = request.session.get('filter', {})

    # Get the preferred league and lolcation from the user filter
    preferred_league = ufilter.get('league', None)
    preferred_location = ufilter.get('location', None)

    if not preferred_league:
        preferred_league = request.session.get("preferred_league", 0)

    # Default settings
    defaults = { "leagues": preferred_league,
                 "locations": preferred_location,
                 "date_from": None,
                 "date_to": None,
                 "duration_min": None,
                 "duration_max": None,
                 "month_days": None,
                 "gap_days": "1"}

    # The user request
    urequest = request.GET

    # TODO check if we can specify NO league filtering. That is where does preferred league come from?
    # This is in leaderboards view as well with same request to check behaviour
    leagues = []
    if 'leagues' in urequest:
        sleagues = urequest['leagues']  # CSV string
        if sleagues:
            leagues = list(map(int, sleagues.split(",")))  # list of ints

        if preferred_league and not leagues:
            leagues = [defaults["leagues"]]
    elif defaults["leagues"]:
        leagues = [defaults["leagues"]]

    # We support a locatoion filter as well
    locations = []
    if 'locations' in urequest:
        slocations = urequest['locations']  # CSV string
        if slocations:
            locations = list(map(int, slocations.split(",")))  # list of ints

        if preferred_location and not locations:
            locations = [defaults["leagues"]]
    elif defaults["locations"]:
        locations = [defaults["locations"]]

    # Suppport for a date range
    date_from = urequest.get("date_from", defaults["date_from"])
    date_to = urequest.get("date_to", defaults["date_to"])

    # Support a duration filer
    duration_min = urequest.get("duration_min", defaults["duration_min"])
    duration_max = urequest.get("duration_max", defaults["duration_max"])

    # The month day restrictions if any (captures weekly or monthly cycles)
    month_days = urequest.get("month_days", defaults["month_days"])

    # The number of days between sessions that breaks session groups into events.
    gap_days = float(urequest.get("gap_days", defaults["gap_days"]))

    # Collect the implcit events
    events = Event.implicit(leagues, locations, date_from, date_to, duration_min, duration_max, month_days, gap_days)

    # And some stats about them
    stats = Event.stats(events)

    # Build a graph (test for now)
    (players, frequency) = Event.frequency("players", events, as_lists=True)

    # We need include the graph only on an as_context call (the inital page load), not on
    # AJAX calls (that return the data update)
    if as_context:
        plot = figure(height=350,
                      x_axis_label="Count of Players",
                      y_axis_label="Number of Events",
                      background_fill_alpha=0,
                      border_fill_alpha=0,
                      tools="pan,wheel_zoom,box_zoom,save,reset")

        # These are empirically tuned. The figure size is specified above
        # and the ticks and labels are by default adjusted below, but those
        # adjustments can pack them so close they overlap. Which is pretty
        # ugly. These two tuners will be respected to adjust the packing
        # in config to follow and are sort of judged by eye. More than this
        # number of labels is considered too tight, packing wise.
        max_xticks = 30
        max_yticks = 40

        # Now we want to run the x axis from the min to max number of
        # players. And the frequency axis we'd like to run from 0 to the
        # max frequency.
        xticks = 1 + max(players) - min(players)
        xspace = 1 + xticks // max_xticks

        yticks = 1 + max(frequency)
        yspace = 1 + yticks // max_yticks

        plot.xaxis.ticker = list(range(min(players), max(players) + 1, xspace))
        plot.yaxis.ticker = list(range(0, max(frequency) + 1, yspace))
        plot.toolbar.logo = None

        plot.y_range.start = 0

        bars = plot.vbar(x=players, top=frequency, width=0.9)

        # This example is good: https://docs.bokeh.org/en/latest/docs/user_guide/interaction/callbacks.html#customjs-for-widgets
        # But not perfect. How to trigger that onchange in JS?
        bars.data_source.js_on_change("change", CustomJS(args=dict(xticker=plot.xaxis.ticker, yticker=plot.yaxis.ticker), code=f"""
            //console.log("DEBUG! Data source changed!");
            const startx = Math.min(...players); const endx = Math.max(...players);
            const starty = 0;                    const endy = Math.max(...frequency);

            const xticks = 1 + endx - startx;
            const xspace = 1 + Math.floor(xticks / {max_xticks});

            const yticks = 1 + endy - starty;
            const yspace = 1 + Math.floor(yticks / {max_yticks});

            xticker.ticks = _.range(startx, endx+1, xspace);
            yticker.ticks = _.range(starty, endy+1, yspace);
            //debugger;
        """))

        graph_script, graph_div = components(plot)

    settings = {}
    if leagues: settings["leagues"] = leagues
    if locations: settings["locations"] = locations
    if date_from: settings["date_from"] = date_from
    if date_to: settings["date_to"] = date_to
    if duration_min: settings["duration_min"] = duration_min
    if duration_max: settings["duration_max"] = duration_max
    if month_days: settings["month_days"] = month_days
    if gap_days: settings["gap_days"] = gap_days

    use_min = "" if django_settings.DEBUG else ".min"
    media = {
        "css": mark_safe("\n".join([
            f"<link href='http://cdn.pydata.org/bokeh/release/bokeh-{bokeh_version}{use_min}.css' rel='stylesheet' type='text/css'>",
            f"<link href='http://cdn.pydata.org/bokeh/release/bokeh-widgets-{bokeh_version}{use_min}.css' rel='stylesheet' type='text/css'>"
            ])),
        "js": mark_safe("\n".join([
            f"<script src='https://cdn.bokeh.org/bokeh/release/bokeh-{bokeh_version}{use_min}.js'></script>",
            f"<script src='https://cdn.bokeh.org/bokeh/release/bokeh-widgets-{bokeh_version}{use_min}.js'></script>",
            f"<script src='https://cdn.bokeh.org/bokeh/release/bokeh-tables-{bokeh_version}{use_min}.js'></script>",
            f"<script src='https://cdn.bokeh.org/bokeh/release/bokeh-api-{bokeh_version}{use_min}.js'></script>"
            ])),
        }

    context = {"title": "Game Events",
               "events": events,
               "stats": stats,
               "settings": settings,
               "defaults": defaults,
               "players": players,
               "frequency": frequency,
               "DEBUG_BokehJS": True,
               "bokeh_media": media
               }

    if as_context:
        # Widgets and the graph and the ID of the graph all only needed on page load not in the JSON
        # returned to AJAX callers (only apage that ghas all these should be calling back anyhow)
        context.update({"dal_media": autocomplete.Select2().media,
                        "widget_leagues": html_selector(League, "leagues", settings.get("leagues", None), ALL_LEAGUES, multi=True),
                        "widget_locations": html_selector(Location, "locations", settings.get("locations", None), ALL_LOCATIONS, multi=True),
                        "graph_script": graph_script,
                        "graph_div": graph_div,
                        "plotid": plot.id,
                        "barsid": bars.id})

        return context
    else:
        events_table = rich_render_to_string("include/events_table.html", context).strip()
        events_stats_table = rich_render_to_string("include/events_stats_table.html", context).strip()
        return HttpResponse(json.dumps((events_table, events_stats_table, settings, players, frequency), cls=DjangoJSONEncoder))
