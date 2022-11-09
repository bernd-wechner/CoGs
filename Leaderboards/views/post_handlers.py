#===============================================================================
# Handlers called AFTER certain conditions in the generic views.
#
# These are the COGS specific handlers that the generic views call.
#===============================================================================
from ..models import Rating, RATING_REBUILD_TRIGGER


def post_delete_handler(self, pk=None, game=None, players=None, victors=None, rebuild=None):
    '''
    After deleting an object this is called (before the transaction is committed, so raising an
    exception can force a rollback on the delete.

    :param players:    a set of players that were in a session being deleted
    :param victors:    a set of victors in the session being deleted
    :param rebuild:    a list of sessions to rebuild ratings for if a session is being deleted
    '''
    model = self.model._meta.model_name

    if model == 'session':
        # Execute a requested rebuild
        if rebuild:
            reason = f"Session {pk} was deleted."
            Rating.rebuild(Sessions=rebuild, Reason=reason, Trigger=RATING_REBUILD_TRIGGER.session_delete)
        else:
            # A rebuld of ratings finsihes with updated ratings)
            # If we have no rebuild (by implication we just deleted
            # the last session in that games tree for those players)
            # and so we need to update the ratings ourselves.
            for p in players:
                r = Rating.get(p, game)
                r.reset()
                r.save()


def post_save_handler(self):
    '''
    Nothing implemented for post form save handling. Placeholder should we need anything.

    :param self:
    '''
