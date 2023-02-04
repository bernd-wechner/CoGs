from django.db.models import Model


# As leaderboards are lists of players, possibly in a session wrapper (list) in a game wrapper (list)
# A couple of one liners that makes a nested tree of tuples mutable (converts them all to lists)
# and vice versa, so we can lock leadeboards and unlock them explicitly if an edit is targetted.
def mutable(e):
    return list(map(mutable, e)) if isinstance(e, (list, tuple)) else e


def immutable(e):
    return tuple(map(immutable, e)) if isinstance(e, (list, tuple)) else e


def pk_keys(o):

    def pk(x): return x.pk if isinstance(x, Model) else x

    return {pk(k): pk_keys(v) for k, v in o.items()} if isinstance(o, dict) else o


def is_number(s):
    '''
    A simple test on a string to see if it's a number or not, for float values
    notably leaderboard_options.num_days and compare_back_to. Which can both come
    in as float values.
    '''
    try:
        float(s)
        return True
    except ValueError:
        return False
