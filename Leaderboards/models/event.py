import pytz

from datetime import datetime, timedelta

from tailslide import Median

from django.db import models
from django.utils import timezone

from django.db.models import Case, When, Q
from django.db.models.fields import DurationField
from django.db.models.aggregates import Count, Min, Max, Avg
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models.expressions import Window, F, ExpressionWrapper
from django.db.models.functions.window import Lag

from django_cte import With

from django_generic_view_extensions.queryset import get_SQL
from django_generic_view_extensions.datetime import make_aware

from django_model_admin_fields import AdminModel

from .session import Session
from .performance import Performance


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

    @classmethod
    def implicit(cls, leagues=None, locations=None, dt_from=None, dt_to=None, num_days=None, gap_days=1):
        '''
        Implicit events are those inferred from Session records, and not explicitly recorded as events.

        They are defined as all block of contiguous sessions that have gap_days (defaulting 1) between
        them. The remaining arguments are filters

        :param leagues:    A list of League PKs to restrict the events to (a Session filter)
        :param locations:  A list of location PKs to restrict the events to (a Session filter)
        :param dt_from:    The start of a datetime window (a Session filter)
        :param dt_to:      The end of a datetime window (a Session filter)
        :param num_days:   The minimum duration (in days) of events (an Event filter)
        :param gap_days:   The gape between sessions that marks a gap between implicit Events.
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

        # This annotation uses a min_date_time as a default  which must be
        # TZ aware. To make datetime.min timezone aware however is not
        # possible (crashes with errors) so we add one day and it works
        # which serves our purpose of a minimum timezone aware datetime.
        min_date_time = make_aware(datetime.min + timedelta(days=1), pytz.timezone('UTC'))

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
                    prev_date_time=Window(expression=Lag('date_time', default=min_date_time), order_by=F('date_time').asc()),
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
        #
        # It works because a Window that has no partition_by included, makes a single partition
        # of all the row from this one to the end. Which is why we need to ensure and order_by
        # clause in the Window. Ordered by date_time, a count of all the event_start values (nulls)
        # are not counted, returns how many event_starts there are before this row. And so a count
        # events before this row. A sneaky SQL trick. It relies on the event_start not having a
        # default value (an ELSE clause) and hence defaulting to null. Count() ignores the nulls.
        session_events = sessions.queryset().annotate(
                            event=Window(expression=Count(sessions.col.event_start), order_by=sessions.col.date_time)
                        )

        # Step 4: We have to bring players into the fold, and they are stored in Performance objects.
        # Now we want to select from the from the session_events queryset joined with Performance.
        # and group by events to collect session counts and player lists and player counts.
        #
        # WARNING: We need an explicit order_by('events') as the Perfroamnce object has a default
        # orderig and if that is included, it forces one row per Perfornce obvect EVEN after
        # .values('event') and .distinct() diesn't even help int hat instance (I tried). Short
        # story is, use explicit ordering on the group by field (.values() field)
        session_events = With(session_events, "outer_sessions")

        events = (session_events
                 .join(Performance, session_id=session_events.col.id)
                 .annotate(event=session_events.col.event,
                           location_id=session_events.col.location_id,
                           game_id=session_events.col.game_id)
                 .order_by('event')
                 .values('event')
                 .annotate(start=Min('session__date_time'),
                           end=Max('session__date_time'),
                           duration=F('end') - F('start'),
                           locations=Count('location_id', distinct=True),
                           location_ids=ArrayAgg('location_id', distinct=True),
                           sessions=Count('session_id', distinct=True),
                           session_ids=ArrayAgg('session_id', distinct=True),
                           games=Count('game_id', distinct=True),
                           game_ids=ArrayAgg('game_id', distinct=True),
                           players=Count('player_id', distinct=True),
                           player_ids=ArrayAgg('player_id', distinct=True)
                          ))

        # Finally, apply the event filters
        if num_days:
            events = events.filter(duration__lte=num_days)

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

        return events.aggregate(Min('sessions'),
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
                                Max('players'))

    class Meta(AdminModel.Meta):
        verbose_name = "Event"
        verbose_name_plural = "Events"
