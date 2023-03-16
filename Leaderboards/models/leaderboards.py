from django.db.models import Model, JSONField, OneToOneField, CASCADE
from django_rich_views.serializers import TypedEncoder, TypedDecoder


class Leaderboard_Cache(Model):
    '''
    A simple cache for leaderboards

    These are defined by the Ratings of players, and the latest leaderboards always by
    Rating model and any snapshots my records in the  Performance model associated with
    the Session model.

    But generating them is costly and a little slow. Involves an ordering of all players
    by their ratings and extraction of some metdata to boot.

    The constructed leaderboards are defined in a data structure that is transmitted in
    JSON format to the client for rendering. Such boards come in different depths of
    detail defined in other models. The one of greatest interest here is
    Session.leaderboard_snapshot whcih is itself just a Session.wrapped_leaderboard.

    The Leaderboards.leaderboards is central to their presentation, and in partiocular:

    Leaderboards.leaderboards.enums.LB_STRUCTURE and it is the `session_wrapped_player_list`
    that is cached here in JSON format for rapid retrieval delivery and delivery.
    '''

    session = OneToOneField('Session', verbose_name='Session', related_name='leaderboard_cache', primary_key=True, on_delete=CASCADE)  # if the session is deleted, delete this cache entry can be too
    board = JSONField(null=True, encoder=TypedEncoder, decoder=TypedDecoder)

    @classmethod
    def invalidate(cls, session):
        '''
        Removes the the cahce for the specified session. Called if a session is edited or any
        rebuild of ratings impacting this sessions leaderboard cache record was requested.

        :param session: a Session object
        '''
        try:
            cache = cls.objects.get(session=session)
            cache.delete()
        except cls.DoesNotExist:
            pass

