#===============================================================================
# Handler for initialising forms (called after default initialisations applied_
#
# These are the COGS specific handlers that the generic views call.
#===============================================================================


def form_init(self, initial):
    '''
    :param self : and instance of CreateView
    :param initial: a dict of initial values keyed on field name
    :returns: initial, augmented or altered as desired
    '''
    try:
        user = self.request.user
        model = self.model._meta.model_name
    except:
        return initial

    # If a player is being added, default the league and leagues to those of the logged in user adding them
    if model == "player":
        initial["league"] = user.player.league.pk
        initial["leagues"] = [l.pk for l in user.player.leagues.all()]

    return initial
