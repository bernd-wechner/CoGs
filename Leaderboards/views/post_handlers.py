#===============================================================================
# Handlers called AFTER certain conditions in the generic views.
#
# These are the COGS specific handlers that the generic views call.
#===============================================================================
from ..models import Rating, RATING_REBUILD_TRIGGER

from Site.logutils import log

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
            # A rebuild of ratings finishes with updated ratings)
            # If we have no rebuild requested (by implication we just 
            # deleted the last session in that games tree for those players)
            # and so we need to update the ratings ourselves.
            for p in players:
                r = Rating.get(p, game)
                r.reset()
                r.save()
        
        # TODO: Remove this some time        
        # #####################################################################################################################################
        # # Witching hour bug catcher!
        # # There is a strange phenomenon in which I see sessions where a play count is skipped!
        # # That can happen with bad save which fails to update playcount right
        # # Or a delete which doesn't update it correctly! 
        # # Both these need a detection trap so that if I can reproduce it, it breaks  here
        # # And we can examine the stack trace and locals and plan a debug strategy n the preceding 
        # # code that led to this integrity failure.
        # session = self.object
        #
        # for player in session.players:
        #     session_previous = session.previous_session(player)
        #     p1 = session_previous.performances.filter(player=player)[0]
        #     play_count_previous = p1.play_number
        #
        #     session_following = session.following_session(player)
        #     if session_following:
        #         p2 = session_following.performances.filter(player=player)[0]
        #         play_count_following = p2.play_number
        #
        #         if not play_count_following == play_count_previous + 1:
        #             log.debug(f"GOTCHA: Trying to delete a session breaking playcount! {play_count_previous=} {play_count_following=}")
        #             breakpoint()         

def post_save_handler(self):
    '''
    Nothing implemented for post form save handling. Placeholder should we need anything.

    :param self:
    '''
