'''
Django Generic View Extensions

Neighbour Identification

Specifically for browsing objects in DetailViews. This should really be spun out as a separate 
package or arguably absorbed in some form or other into Django core.

Possible extension might be to allow n-hops away neighbours, so neighbours either side, 2, 5, 10 
jumps away. For nuanced browsing. 
'''
# Django imports
from django.db.models import F, Window
from django.db.models.functions import Lag, Lead, RowNumber


def get_neighbour_pks(model, pk, filterset=None, ordering=None):
    '''
    Given a model and pk that identify an object (model instance) will, given an ordering
    (defaulting to the models ordering) and optionally a filterset (from url_filter), will
    return a tuple that contains two PKs that of the prior and next neighbour in the list
    either of all objects by that ordering or the filtered list (if a filterset is provided) 
    :param model:        The model the object is an instance of
    :param pk:           The primary key of the model instance being considered
    :param filterset:    An optional filterset (see https://github.com/miki725/django-url-filter)
    :param ordering:     An optional ordering (otherwise default model ordering is used). See: https://docs.djangoproject.com/en/2.0/ref/models/options/#ordering  
    '''
    # If a filterset is provided ensure it's of the same model as specified (consistency).
    if filterset and not filterset.Meta.model == model:
        return None    
    
    # Get the ordering list for the model (a list of fields
    # See: https://docs.djangoproject.com/en/2.0/ref/models/options/#ordering
    if ordering is None:
        ordering = model._meta.ordering
    
    order_by = []
    for f in ordering:
        if f.startswith("-"):
            order_by.append(F(f[1:]).desc())
        else:
            order_by.append(F(f).asc())

    # Define the window functions for each neighbour    
    window_lag = Window(expression=Lag("pk"), order_by=order_by)
    window_lead = Window(expression=Lead("pk"), order_by=order_by)
    window_rownnum = Window(expression=RowNumber(), order_by=order_by)

    # Get a queryset annotated with neighbours. If annotated attrs clash with existing attrs an exception 
    # will be raised: https://code.djangoproject.com/ticket/11256    
    try:
        # If a non-empty filterset is supplied, respect that
        if filterset and filterset.filter:
            # We respect the filterset.
            # FIXME: Aaargh this won't work for injecting the current PK into the query! 
            # Needs testing in both cases. I can't think of a way to do it alas. THis is
            # frustrating me. Problem is across related object filters, or JOINS.
            # qs = filterset.filter() | (model.objects.filter(pk=pk).distinct() & filterset.filter())
            qs = filterset.filter()
        # Else we just use all objects
        else:
            qs = model.objects
            
        # Now annotate the queryset with the prior and next PKs
        qs = qs.annotate(neighbour_prior=window_lag, neighbour_next=window_lead, row_number=window_rownnum)
    except:
        return None
    
    # Finally we need some trickery alas to do a query on the queryset! We can't add this WHERE
    # as a filter because the LAG and LEAD Window functions fail then, they are emoty because 
    # there is no lagger or leader on the one line result! So we have to run that query on the 
    # whole table.then extract form the result the one line we want! Wish I could find a way to 
    # do this in the Django ORM not with a raw() call.    
    ao = model.objects.raw("SELECT * FROM ({}) ao WHERE {}=%s".format(str(qs.query), model._meta.pk.name),[pk])
    
    if ao:
        if len(list(ao)) == 1:
            return (ao[0].neighbour_prior,ao[0].neighbour_next, ao[0].row_number, qs.count())
        else:
            raise ValueError("Query error: object appears more than once in neighbour hunt.")
    else:
        raise None   