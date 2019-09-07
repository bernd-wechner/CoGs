'''
Django Generic View Extensions

Neighbour Identification

Specifically for browsing objects in DetailViews. This should really be spun out as a separate 
package or arguably absorbed in some form or other into Django core.

Possible extension might be to allow n-hops away neighbours, so neighbours either side, 2, 5, 10 
jumps away. For nuanced browsing. 
'''
# Django imports
from django.db.models import F, Window, Subquery
from django.db.models.functions import Lag, Lead, RowNumber

# Package imports
#from .util import get_SQL
#from .debug import print_debug

def get_neighbour_pks(model, pk, filterset=None, ordering=None):
    '''
    Given a model and pk that identify an object (model instance) will, given an ordering
    (defaulting to the models ordering) and optionally a filterset (from url_filter), will
    return a tuple that contains two PKs that of the prior and next neighbour in the list
    either of all objects by that ordering or the filtered list (if a filterset is provided)
    
    :returns: a 4 tuple containing (prior_pk, next_pk, row_number, list_length)
     
    :param model:        The model the object is an instance of
    :param pk:           The primary key of the model instance being considered
    :param filterset:    An optional filterset (see https://github.com/miki725/django-url-filter)
    :param ordering:     An optional ordering (otherwise default model ordering is used). See: https://docs.djangoproject.com/en/2.0/ref/models/options/#ordering  
    '''
    # If a filterset is provided ensure it's of the same model as specified (consistency).
    if filterset and not filterset.Meta.model == model:
        return (None, None)
    
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
    
    # A default order. We need an order or the window functions crash
    if len(order_by) == 0:
        order_by = ['pk']

    # Define the window functions for each neighbour    
    window_lag = Window(expression=Lag("pk"), order_by=order_by)
    window_lead = Window(expression=Lead("pk"), order_by=order_by)
    window_rownnum = Window(expression=RowNumber(), order_by=order_by)

    # Get a queryset annotated with neighbours. If annotated attrs clash with existing attrs an exception 
    # will be raised: https://code.djangoproject.com/ticket/11256    
    try:
        # Start with all objects
        qs = model.objects.all()

        # Now apply a filterset if we have one
        if not filterset is None:
            # We respect the filterset. BUT we need to wrap it inside a sub query, so that
            # we can apply a DISTNCT ON Pk to avoid duplicate tuples that the window 
            # functions can introduce when we are matching multiple remote objects.
            # Alas that's what they do. So we have to constrain it to one tuple per
            # PK. 
            # 
            # FIXME: Aaargh this won't work for injecting the current PK into the query!
            # My desire is to make sure that the query results include the provided pk. 
            # Needs testing in both cases. I can't think of a way to do it alas. This is
            # frustrating me. Problem is across related object filters, or JOINS.
            # qs = filterset.filter() | (model.objects.filter(pk=pk).distinct() & filterset.filter())
            qs = qs.filter(pk__in=Subquery(filterset.filter().distinct('pk').order_by('pk').values('pk')))    

        # Now order the objects properly
        qs = qs.order_by(*order_by)
            
        # Now annotate the queryset with the prior and next PKs
        qs = qs.annotate(neighbour_prior=window_lag, neighbour_next=window_lead, row_number=window_rownnum)               
    except:
        return None

    # Finally we need some trickery alas to do a query on the queryset! We can't add this WHERE
    # as a filter because the LAG and LEAD Window functions fail then, they are empty because 
    # there is no lagger or leader on the one line result! So we have to run that query on the 
    # whole table, then extract from the result the one line we want! Wish I could find a way to 
    # do this in the Django ORM not with a raw() call.    

    # First we need the SQL from the existing query. Many on-line sources seem to recommend 
    # str(qs.query) but this does not return reliable SQL! A bug in Django and much discussed:
    #    https://code.djangoproject.com/ticket/30132
    #    https://code.djangoproject.com/ticket/25705
    #    https://code.djangoproject.com/ticket/25092
    #    https://code.djangoproject.com/ticket/24991
    #    https://code.djangoproject.com/ticket/17741
    #
    # But this, it seems is the reliable method which involves dipping into Django's 
    # innards a litte (the SQL compiler)    
    sql, params = qs.query.get_compiler(using=qs.db).as_sql()
    
    # Now we wrap the SQL    
    sql = "SELECT * FROM ({}) ao WHERE {}={}".format(sql, model._meta.pk.name, pk)
    
    # And create a new QuerySet
    ao = model.objects.raw(sql, params)
    
    try:
        if ao:
            if len(ao) == 1:
                return (ao[0].neighbour_prior, ao[0].neighbour_next, ao[0].row_number, qs.count())
            else:
                raise ValueError("Query error: object appears more than once in neighbour hunt.")
        else:
            return (None,) * 4
    except:
        return (None,) * 4
        