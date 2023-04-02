from datetime import timedelta
from collections import Counter

from tailslide import Median

from django.db import models
from django.utils import timezone

from django.db.models import Q, Case, When, DateTimeField, DurationField
from django.db.models.aggregates import Count, Min, Max, Avg
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models.functions import Extract
from django.db.models.expressions import Window, F, ExpressionWrapper
from django.db.models.functions.window import Lag

from django_rich_views.util import isInt
from django_rich_views.model import NotesMixIn
from django_rich_views.queryset import get_SQL, print_SQL

from django_model_admin_fields import AdminModel

from django_cte import With

from .session import Session
from .performance import Performance

class Event(AdminModel, NotesMixIn):
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

    @classmethod
    def implicit(cls, leagues=None,
                      locations=None,
                      dt_from=None,
                      dt_to=None,
                      duration_min=None,
                      duration_max=None,
                      month_days=None,
                      gap_days=1,
                      minimum_event_duration=2):
        '''
        Implicit events are those inferred from Session records, and not explicitly recorded as events.

        They are defined as all block of contiguous sessions that have gap_days (defaulting 1) between
        them. The remaining arguments are filters

        :param cls:
        :param leagues:      A list of League PKs to restrict the events to (a Session filter)
        :param locations:    A list of location PKs to restrict the events to (a Session filter)
        :param dt_from:      The start of a datetime window (a Session filter)
        :param dt_to:        The end of a datetime window (a Session filter)
        :param duration_min: The minimum duration (in days) of events (an Event filter)
        :param duration_max: The maximum duration (in days) of events (an Event filter)
        :param month_days    A CSV string list of month day identifiers Entries are like Monday_N
                             where N is the week of the month (1-5). Any week when N is missing.
                             Amy day win that week when the day is missing.
        :param gap_days:     The gap between sessions that marks a gap between implicit Events.
        :param minimum_event_duration: Sessions are recorded with a single time (nominally completion).
                                       Single session events will have a duration of 0 as a consequence.
                                       This, in hours expresses the average game duration of a single game
                                       session.  It's nominal and should ideally be the duration it takes
                                       that one session to play through, which we can only estimate in any
                                       case from the expected play time of the game. But to use that will
                                       require a more complicated query joining the Game model,
        :return: A QuerySet of events (lazy, i.e no database hits in preparing it)
        '''
        # Build an annotated session queury that we can use (lazy)
        # Startnig with all sessions
        sessions = Session.objects.all()  # @UndefinedVariable

        # Then applying session filters
        if leagues:
            sessions = sessions.filter(league__pk__in=leagues)
        if locations:
            sessions = sessions.filter(location__pk__in=locations)
        if dt_from:
            sessions = sessions.filter(date_time__gte=dt_from)
        if dt_to:
            sessions = sessions.filter(date_time__lte=dt_to)

        # Then get the events (as all runs of session with gap_days
        # between them.

        # We need to anotate the sessions in two tiers alas, because we need a Window
        # to get the previous essions time, and then a window to group the sessions and
        # windows can't reference windows ... doh! The solution is what is to select
        # from a subquery. Alas Django does not support selecting FROM a subquery (yet).
        # Enter the notion of a Common Table Expression (CTE) which is essentially a
        # a way of naming a query to use as the FROM target of another query. There is
        # fortunately a package "django_cte" tahat adds CTE support to querysets. It's
        # a tad clunky bt works.
        #
        # Step 1 is to do the first windowing annotation, adding the prev_date_time and
        # based on it flagging the first session in each event.
        sessions = sessions.order_by("date_time").annotate(
                    prev_date_time=Window(expression=Lag('date_time'), order_by=F('date_time').asc()),
                    dt_difference=ExpressionWrapper(F('date_time') - F('prev_date_time'), output_field=DurationField()),
                    event_start=Case(When(dt_difference__gt=timedelta(days=gap_days), then='date_time')),
                )

        # Step 2 we need to instantiate a CTE
        sessions = With(sessions, "inner_sessions")

        # Step 3 we build a new queryset (that selects from the CTE and annotate that
        # The oddity here is tha django_cte requires us to call with_cte() to include
        # the CTE's SQL in the new query's SQL. Go figure (I've checked the code, may
        # fork and patch some time).
        #
        # The grouping expression is SQL esoterica, that I pilfered from:
        #
        #    https://stackoverflow.com/a/56729571/4002633
        #    https://dbfiddle.uk/?rdbms=postgres_11&fiddle=0360fd313400e533cd76fbc39d0e22d3
        # week
        # It works because a Window that has no partition_by included, makes a single partition
        # of all the row from this one to the end. Which is why we need to ensure and order_by
        # clause in the Window. Ordered by date_time, a count of all the event_start values (nulls)
        # are not counted, returns how many event_starts there are before this row. And so a count
        # events before this row. A sneaky SQL trick. It relies on the event_start not having a
        # default value (an ELSE clause) and hence defaulting to null. Count() ignores the nulls.
        sessions_with_event = sessions.queryset().annotate(
                            event=Window(expression=Count(sessions.col.event_start), order_by=sessions.col.date_time),
                            # local_time=ExpressionWrapper(F('date_time__local'), output_field=DateTimeField())
                        )

        print_SQL(sessions_with_event)

        # Step 4: We have to bring players into the fold, and they are stored in Performance objects.
        # Now we want to select from the from the session_events queryset joined with Performance.
        # and group by events to collect session counts and player lists and player counts.
        #
        # WARNING: We need an explicit order_by('events') as the Performance object has a default
        # ordering and if that is included, it forces one row per Perfornce obvect EVEN after
        # .values('event') and .distinct() diesn't even help int hat instance (I tried). Short
        # story is, use explicit ordering on the group by field (.values() field)
        sessions_with_event = With(sessions_with_event, "outer_sessions")

        events = (sessions_with_event
                 .join(Performance, session_id=sessions_with_event.col.id)
                 .annotate(event=sessions_with_event.col.event + 1,  # Move from 0 based to 1 based
                           location_id=sessions_with_event.col.location_id,
                           game_id=sessions_with_event.col.game_id,
                           gap_time=sessions_with_event.col.dt_difference)
                 .order_by('event')
                 .values('event')
                 .annotate(start=ExpressionWrapper(Min('session__date_time__local') - timedelta(hours=minimum_event_duration), output_field=DateTimeField()),
                           end=Max('session__date_time__local'),
                           duration=F('end') - F('start'),
                           gap_time=Max('gap_time'),
                           locations=Count('location_id', distinct=True),
                           location_ids=ArrayAgg('location_id', distinct=True),
                           sessions=Count('session_id', distinct=True),
                           session_ids=ArrayAgg('session_id', distinct=True),
                           games=Count('game_id', distinct=True),
                           game_ids=ArrayAgg('game_id', distinct=True),
                           players=Count('player_id', distinct=True),
                           player_ids=ArrayAgg('player_id', distinct=True)
                          ))

        # PROBLEM: start and end are in UTC here. They do not use the recorded TZ of the ession datetime.
        # Needs fixing!

        if month_days:
            daynum = {"sunday":1, "monday":2, "tuesday":2, "wednesday":4, "thursday":5, "friday":6, "saturday":7}

            # Build a canonical list of days (lower case, and None's removed)
            days = [d.strip().lower() for d in month_days.split(",")]

            efilter = Q()

            for day in days:
                try:
                    day_filter = None
                    week_filter = None

                    # Can be of form "day", "day_n" or "n"
                    parts = day.split("_")
                    if len(parts) == 1:
                        if parts[0] in daynum:
                            day_filter = daynum[parts[0]]
                        elif isInt(parts[0]):
                            week_filter = int(parts[0])
                    else:
                        day_filter = daynum.get(parts[0], None)
                        week_filter = int(parts[1])
                except:
                    raise ValueError(f"Bad month/day specifier: {day}")

                # A dw filter is the day file AND the week filter
                if day_filter or week_filter:
                    dwfilter = Q()
                    if day_filter:
                        dwfilter &= Q(start__week_day=day_filter)
                    if week_filter:
                        dwfilter &= Q(start__month_week=week_filter)
                    # An event filter is one dw filter OR another.
                    efilter |= dwfilter

            # Q() if Falsey which is good
            if efilter:
                events = events.filter(efilter)

        # Finally, apply the event filters
        if duration_min: events = events.filter(duration__gte=duration_min)
        if duration_max: events = events.filter(duration__lte=duration_max)

        # Return a QuerySet of events (still lazy)
        return events.order_by("-end")

    @classmethod
    def stats(cls, events=None):
        '''
        Returns stats on the events queryset provided.

        :param events: A queryset of events, that have the fields sessions, games, players
        '''
        if events is None:
            events = cls.implicit()

        if events:
            # Tailwind's Median aggregator does not work on Durations (PostgreSQL Intervals)
            # So we have to convert it to Epoch time. Extract is a Django method that can extract
            # 'epoch' which is the documented method of casting a PostgreSQL interval to epoch time.
            #    https://www.postgresql.org/message-id/19495.1059687790%40sss.pgh.pa.us
            # Django does not document 'epoch' alas but it works:
            #    https://docs.djangoproject.com/en/4.0/ref/models/database-functions/#extract
            # We need a Django ExpressionWrapper to cast the Duration field to DurationField as
            # for some reason even though it's a PostgreSQL interval, Django still thinks of it
            # as a DateTimeField (from the difference of two DateTimeFields I guess and a bug/feature)
            # that fails to recast a difference of DateTimeField's as DurationField.
            epoch_duration = Extract(ExpressionWrapper(F('duration'), output_field=DurationField()), lookup_name='epoch')
            epoch_gap = Extract(ExpressionWrapper(F('gap_time'), output_field=DurationField()), lookup_name='epoch')

            result = events.aggregate(Min('sessions'),
                                      Avg('sessions'),
                                      Median('sessions'),
                                      Max('sessions'),
                                      Min('games'),
                                      Avg('games'),
                                      Median('games'),
                                      Max('games'),
                                      Min('players'),
                                      Avg('players'),
                                      Median('players'),
                                      Max('players'),
                                      duration__min=Min('duration'),
                                      duration__avg=Avg('duration'),
                                      duration__median=Median(epoch_duration),
                                      duration__max=Max('duration'),
                                      gap__min=Min('gap_time'),
                                      gap__avg=Avg('gap_time'),
                                      gap__median=Median(epoch_gap),
                                      gap__max=Max('gap_time'))

            # Aggregate is a QuerySet enpoint (i.e results in evaluation of the Query and returns
            # a standard dict. To wit we can cast teh Epch times back to Durations for the consumer.
            result['duration__median'] = timedelta(seconds=result['duration__median'])
            result['gap__median'] = timedelta(seconds=result['gap__median'])
        else:
            result = None

        return result

    @classmethod
    def frequency(cls, field, events=None, as_lists=False):
        '''
        Returns a dict keyed on the values of field and the number of times it crops up in the
        events supplied.

        :param events: A queryset of events, that have the fields sessions, games, players
        '''
        if events is None:
            events = cls.implicit()

        # We want to take a Count of field, but field is quite possibly an aggregate itself
        # and that doesn't work, so enter CTEs once more.
        # BUT Alas, this BROKEN. with_events.queryset() for some reason includes JOINS with sessions
        # and players and is not a clean select from the CTE. it tried a quick diagnosis studying
        # queryset() but it will be costly, it's not bery lucid. So I bail and try another approach.
        # with_events = With(events, "events")
        # result = with_events.queryset()
        # result = result.annotate(**{field: getattr(with_events.col, field)}).annotate(Count(field))

        result = {e["event"]: e[field] for e in events.values("event", field)}
        result = Counter(result.values())

        if as_lists:
            field_values = []
            value_frequencies = []
            for val in sorted(result):
                field_values.append(val)
                value_frequencies.append(result[val])

            return field_values, value_frequencies
        else:
            return result

    class Meta(AdminModel.Meta):
        verbose_name = "Event"
        verbose_name_plural = "Events"
