#===============================================================================
# Admin related views
#
# A work in progress, were hack code is plugged in for admin interventions on
# the site.
#===============================================================================
import cProfile, pstats, io

from datetime import datetime, date, timedelta
from html import escape

from django_generic_view_extensions.util import class_from_string
from django_generic_view_extensions.datetime import decodeDateTime

from ..models import Game, Session, Rank, Performance, Rating, RATING_REBUILD_TRIGGER

from django.db.models import Q
from django.utils.timezone import activate
from django.http.response import HttpResponse

from django.conf import settings


def view_CheckIntegrity(request):
    '''
    Check integrity of database

    The check_integrity routines on some models all work with assertions
    and raise exceptions when integrity errors are found. So this will bail
    on the first error, and outputs will be on the console not sent to the
    browser.

    All needs some serious tidy up for a productions site.
    '''

    def rich(obj):
        return obj.__rich_str__(link=False)

    title = "Database Integrity Check"

    assertion_failures = []  # Assertion failures

    models = ['Game', 'Performance', 'Rank', 'Session', 'Rating']

    quiet = 'quiet' in request.GET

    do_all = True
    for model in models:
        if model in request.GET:
            do_all = False
            break

    if do_all or 'Game' in request.GET:
        print("Checking all Games for internal integrity.", flush=True)
        for G in Game.objects.all():
            fails = G.check_integrity()

            if not quiet: print(f"Game {G.id}: {rich(G)}. {len(fails)} assertion failures.", flush=True)
            for f in fails:
                print(f"\t{f}", flush=True)

            if fails:
                assertion_failures += fails

    if do_all or 'Performance' in request.GET:
        print("Checking all Performances for internal integrity.", flush=True)
        for P in Performance.objects.all().order_by('-pk'):
            fails = P.check_integrity()

            if not quiet: print(f"Performance {P.id}: {rich(P)}. {len(fails)} assertion failures.", flush=True)
            for f in fails:
                print(f"\t{f}", flush=True)

            if fails:
                assertion_failures += fails

    if do_all or 'Rank' in request.GET:
        print("Checking all Ranks for internal integrity.", flush=True)

        for R in Rank.objects.all():
            fails = R.check_integrity()

            if not quiet: print(f"Rank {R.id}: {rich(R)}. {len(fails)} assertion failures.", flush=True)
            for f in fails:
                print(f"\t{f}", flush=True)

            if fails:
                assertion_failures += fails

    if do_all or 'Session' in request.GET:
        print("Checking all Sessions for internal integrity.", flush=True)
        for S in Session.objects.all():
            fails = S.check_integrity(True)

            if not quiet: print(f"Session {S.id}: {rich(S)}. {len(fails)} assertion failures.", flush=True)
            for f in fails:
                print(f"\t{f}", flush=True)

            if fails:
                assertion_failures += fails

    if do_all or 'Rating' in request.GET:
        rfilter = Q()
        try:
            if 'game' in request.GET:
                rfilter &= Q(game__pk=int(request.GET['game']))
        except:
            pass

        try:
            if 'player' in request.GET:
                rfilter &= Q(player__pk=int(request.GET['player']))
        except:
            pass

        print("Checking Ratings for internal integrity.", flush=True)
        for R in Rating.objects.all().filter(rfilter).order_by('last_play'):
            fails = R.check_integrity()

            if not quiet: print(f"Rating {R.id}: {rich(R)}. {len(fails)} assertion failures.", flush=True)
            for f in fails:
                print(f"\t{f}", flush=True)

            if fails:
                assertion_failures += fails

    now = datetime.now()
    summary = '\n'.join(assertion_failures)
    result = f"<html><body<p>{title}</p><p>It is now {now}.</p><p><pre>{summary}</pre></p></body></html>"

    return HttpResponse(result)


def view_RebuildRatings(request):

    def rebuild_ratings(Game=None, From=None, Reason=None):
        activate(settings.TIME_ZONE)

        title = "Rebuild of ratings"
        if not Game and not From:
            title = "Rebuild of ALL ratings"
        else:
            if Game:
                title += f" for {Game.name}"
            if From:
                title += f" from {From}"

        pr = cProfile.Profile()
        pr.enable()
        rlog = Rating.rebuild(Game=Game, From=From, Reason=Reason, Trigger=RATING_REBUILD_TRIGGER.user_request)
        result = rlog.html
        pr.disable()

        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
        ps.print_stats()
        result += s.getvalue()

        now = datetime.now()

        return f"<html><body<p>{title}</p><p>It is now {now}.</p><p><pre>{result}</pre></p></body></html>"

    reason = "Explicitly requested rebuild"

    if 'game' in request.GET and request.GET['game'].isdigit():
        try:
            game = Game.objects.get(pk=request.GET['game'])
            reason += f" for {game.name} (id: {game.id})"
        except Game.DoesNotExist:
            game = None
    else:
        game = None

    if 'from' in request.GET:
        try:
            From = decodeDateTime(request.GET['from'])
            reason += f" from {From}"
        except:
            From = None
    else:
        From = None

    if 'from_session' in request.GET:
        try:
            session = Session.objects.get(pk=request.GET['session'])
            From = Session.date_time
            reason += f" from session {session} ({From})"
        except:
            From = None
    else:
        From = None

    if 'reason' in request.GET:
        reason = request.GET['reason']
    else:
        reason += "."

    html = rebuild_ratings(game, From, reason)

    return HttpResponse(html)


def view_UnwindToday(request):
    '''
    A simple view that deletes all sessions (and associated ranks and performances) created today. Used when testing.
    Dangerous if run on a live database on same day as data was entered clearly. Testing view only.
    '''
    unwind_to = date.today()  # - timedelta(days=1)

    performances = Performance.objects.filter(created_on__gte=unwind_to)
    performances.delete()

    ranks = Rank.objects.filter(created_on__gte=unwind_to)
    ranks.delete()

    sessions = Session.objects.filter(created_on__gte=unwind_to)
    sessions.delete()

    ratings = Rating.objects.filter(created_on__gte=unwind_to)
    ratings.delete()

    # Now for all ratings remaining we have to reset last_play (if test sessions updated that).
    ratings = Rating.objects.filter(Q(last_play__gte=unwind_to) | Q(last_victory__gte=unwind_to))
    for r in ratings:
        r.reset()

    html = "Success"

    return HttpResponse(html)


def view_Fix(request):

    def rebuild_play_and_victory_counts():
        '''
        Performance objects contain play and victory counts which are therer for efficiency.
        But if they ever go awry, they can be rebuild from recorded session data and this
        function does that across the whole database.
        '''
        sessions = Session.objects.all().order_by('date_time')

        print(f"Rebuilding perfomance play and victory counts for {sessions.count()} sessions.", flush=True)

        for session in sessions:
            for performance in session.performances.all():
                if performance.pk == 900:
                    print("Gotcha.", flush=True)

                previous_performance = performance.previous_play

                if previous_performance:
                    performance.play_number = previous_performance.play_number + 1
                    performance.victory_count = previous_performance.victory_count + 1 if performance.is_victory else previous_performance.victory_count
                else:
                    performance.play_number = 1
                    performance.victory_count = 1 if performance.is_victory else 0

                performance.__bypass_admin__ = True
                performance.save()
                print(f"Fixed performance {performance.id} in session {session.id} having play_number {performance.play_number} and victory_count {performance.victory_count} for {performance.player} at game {performance.game}.", flush=True)

        print("Done.", flush=True)

    def force_unique_session_times():
        '''
        A quick hack to scan through all sessions and ensure none have the same session time
        # TODO: Enforce this when adding or editing sessions because Trueskill is temporal
        # TODO: Technically two game sessions can gave the same time, just not two session involving the same game and a common player.
        #       This is because the Trueskill for that player at that game needs to have temporally ordered game sessions
        '''

        title = "Forced Unique Session Times"
        result = ""

        sessions = Session.objects.all().order_by('date_time')
        for s in sessions:
            coincident_sessions = Session.objects.filter(date_time=s.date_time)
            if len(coincident_sessions) > 1:
                offset = 1
                for sess in coincident_sessions:
                    sess.date_time = sess.date_time + timedelta(seconds=offset)
                    sess.save()
                    result += "Added {} to {}\n".format(offset, sess)
                    offset += 1

        now = datetime.now()

        return "<html><body<p>{0}</p><p>It is now {1}.</p><p><pre>{2}</pre></p></body></html>".format(title, now, result)

    rebuild_play_and_victory_counts()

    # DONE: Used this to create Performance objects for existing Rank objects
    #     sessions = Session.objects.all()
    #
    #     for session in sessions:
    #         ranks = Rank.objects.filter(session=session.id)
    #         for rank in ranks:
    #             performance = Performance()
    #             performance.session = rank.session
    #             performance.player = rank.player
    #             performance.save()

        # Found a Performance corruption that needed fixing, a play_number was wrong
        # Quick rebuild of them all!

    # Test the rank property of the Performance model
    #     table = '<table border=1><tr><th>Performance</th><th>Rank</th></tr>'
    #     performances = Performance.objects.all()
    #     for performance in performances:
    #         table = table + '<tr><td>' + str(performance.id) + '</td><td>' + str(performance.rank) + '</td></tr>'
    #     table = table + '</table>'

        # html = force_unique_session_times()
        # html = rebuild_ratings()
        # html = import_sessions()

        #=============================================================================
        # Datetime fix up
        # We want to walk through every Session and fix the datetime so it's right
        # Subsequent to this we want to walk through every model and fix the Created and Modified datetime as well

        # Session times
    #     sessions = Session.objects.all()
    #
    #     activate('Australia/Hobart')
    #
    #     # Did this on dev database. Seems to have worked a charm.
    #     for session in sessions:
    #         dt_raw = session.date_time
    #         dt_local = localtime(dt_raw)
    #         error = dt_local.tzinfo._utcoffset
    #         dt_new = dt_raw - error
    #         dt_new_local = localtime(dt_new)
    #         log.debug(f"Session: {session.pk}    Raw: {dt_raw}    Local:{dt_local}    Error:{error}  New:{dt_new}    New Local:{dt_new_local}")
    #         session.date_time = dt_new_local
    #         session.save()
    #
    #     # The rating model has two DateTimeFields that are wrong in the same way, but thee can be fixed by rebuilding ratings.
    #     pass
    #
    #     # Now for every model that we have that derives from AdminModel we need to updated we have two fields:
    #     #     created_on
    #     #     last_edited_on
    #     # That we need to tweak the same way.
    #
    #     # We can do this by looping all our models and checking for those fields.
    #     models = apps.get_app_config('Leaderboards').get_models()
    #     for model in models:
    #         if hasattr(model, 'created_on') or hasattr(model, 'last_edited_on'):
    #             for obj in model.objects.all():
    #                 if hasattr(obj, 'created_on'):
    #                     dt_raw = obj.created_on
    #                     dt_local = localtime(dt_raw)
    #                     error = dt_local.tzinfo._utcoffset
    #                     dt_new = dt_raw - error
    #                     dt_new_local = localtime(dt_new)
    #                     log.debug(f"{model._meta.object_name}: {obj.pk}    created    Raw: {dt_raw}    Local:{dt_local}    Error:{error}  New:{dt_new}    New Local:{dt_new_local}")
    #                     obj.created_on = dt_new_local
    #
    #                 if hasattr(obj, 'last_edited_on'):
    #                     dt_raw = obj.last_edited_on
    #                     dt_local = localtime(dt_raw)
    #                     error = dt_local.tzinfo._utcoffset
    #                     dt_new = dt_raw - error
    #                     dt_new_local = localtime(dt_new)
    #                     log.debug(f"{model._meta.object_name}: {obj.pk}    edited     Raw: {dt_raw}    Local:{dt_local}    Error:{error}  New:{dt_new}    New Local:{dt_new_local}")
    #                     obj.last_edited_on = dt_new_local
    #
    #                 obj.save()

    #     for session in sessions:
    #         dt_raw = session.date_time
    #         dt_local = localtime(dt_raw)
    #         dt_naive = make_naive(dt_local)
    #         ctz = get_current_timezone()
    #         log.debug(f"dt_raw: {dt_raw}    ctz;{ctz}    dt_local:{dt_local}    dt_naive:{dt_naive}")

    html = "Success"

    return HttpResponse(html)


def view_Kill(request, model, pk):
    m = class_from_string('Leaderboards', model)
    o = m.objects.get(pk=pk)
    o.delete()

    html = "Success"

    return HttpResponse(html)

