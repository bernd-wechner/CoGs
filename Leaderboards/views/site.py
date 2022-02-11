#===============================================================================
# Site focussed views
#===============================================================================
from django.contrib.auth.models import User

from django_generic_view_extensions.views import LoginViewExtended, TemplateViewExtended

from .context import extra_context_provider


def save_league_filters(session, league):
    '''
    Saves league filtering settings to the user session.

    Used by the generic_biew_extensions, specifically
    ListViewExtended and DetailViewExtended which check
    the session store for filter configurations.

    We record in the suer session the league we want to filter
    all requests with, so that a league specific view of things
    is deliverable.

    :param session: A users session object (from request.session)
    :param league: The pprimary key of a League object
    '''
    # We prioritise leagues over league as players have both the leagues they are in
    # and their preferred league, and our filter should match any league they are in
    # Some models only provide league through a relation and hence we need to list
    # those. Specifically:
    #     Teams through players
    #     Ratings through player
    #     Ranks and Performances through session

    # Set the name of the filter
    F = "league"

    # Set the priority list of fields for this filter
    P = ["leagues", "league", "session__league", "player__leagues", "players__leagues"]

    if "filter" in session:
        if league == 0:
            if F in session["filter"]:
                del session["filter"][F]
        else:
            session["filter"][F] = league
    else:
        if league != 0:
            session["filter"] = { F: league }

    if len(session["filter"]) == 0:
        del session["filter"]

    if "filter_priorities" in session:
        if league == 0:
            del session["filter_priorities"][F]
        else:
            session["filter_priorities"][F] = P
    else:
        if league != 0:
            session["filter_priorities"] = { F: P }

    if len(session["filter_priorities"]) == 0:
        del session["filter_priorities"]

    session.save()


class view_Home(TemplateViewExtended):
    template_name = 'views/home.html'
    extra_context_provider = extra_context_provider


class view_Login(LoginViewExtended):

    # On Login add a filter to the session for the preferred league
    def form_valid(self, form):
        response = super().form_valid(form)

        username = self.request.POST["username"]
        try:
            user = User.objects.get(username=username)

            # We have to lose a leaderboard cache after a login as
            # privacy settings change and lots of player name fields
            # in particular will be missing data in the cache that
            # is now available to the logged in user. This is
            # unfortunate and there may be a cheaper way to replenish
            # the name data than rebuilding the entire leaderboard.
            # TODO: consider cheap means of replenishing name data
            # in a leaderboard chache so that the cache can be preseved
            # when permissions change (visibility of name data).
            if "leaderboard_cache" in self.request.session:
                del self.request.session["leaderboard_cache"]

            if hasattr(user, 'player') and user.player:
                preferred_league = user.player.league

                if preferred_league:
                    form.request.session["preferred_league"] = preferred_league.pk
                    save_league_filters(form.request.session, preferred_league.pk)

        except user.DoesNotExist:
            pass

        return response


def view_About(request):
    '''
    Displays the About page (static HTML wrapped in our base template)
    '''
    return
