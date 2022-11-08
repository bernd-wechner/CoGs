'''
Django Rich Views

Ajax service providers.

'''
import json

from django.http.response import HttpResponse

from dal import autocomplete

from django_rich_views.util import class_from_string


#===============================================================================
# An Autocomplete view
#
# Can of course be tuned and refined. Here's a tutorial:
#
# https://django-autocomplete-light.readthedocs.io/en/master/tutorial.html
#===============================================================================
class ajax_Autocomplete(autocomplete.Select2QuerySetView):
    '''
    Support AJAX fetching of option lists for the django-autocomplte-light widgets.
    They provide a query string in self.q.

    urls.py can route a URL to here such that this:

    reverse_lazy('autocomplete', kwargs={"model": name_of_model, "field_name": name_of_field})

    lands here. Which in Django 2.1 should look like:

    path('autocomplete/<model>/<field_name>', ajax_autocomplete.as_view(), {'app': 'name_of_app_model_is_in'}, name='autocomplete'),

    it returns a queryset and will use a model provided list or a default one.
    '''

    def get_queryset(self):
        self.model = class_from_string(self.kwargs['app'], self.kwargs['model'])
        self.field_name = self.kwargs.get('field_name', None)
        self.field_operation = self.kwargs.get('field_operation', "istartswith")
        self.selector_field = getattr(self.model, "selector_field", None)
        self.selector_queryset = getattr(self.model, "selector_queryset", None)

        if self.field_operation == "in":
            self.field_value = self.q.split(",")
        else:
            self.field_value = self.q

        # If this is false then self.selector_queryset is permitted to do default pre-filtering
        # (which could be based on any other criteria, like session stored filters for example)
        # If it is true it is denied this permission. It is up to the model's selector_queryset
        # method to honor this request, and how it is honored.
        self.select_from_all = self.kwargs.get('all', False)

        # use the model's provided selector_queryset if available
        if self.field_name and self.field_name == self.selector_field and callable(self.selector_queryset):
            qs = self.selector_queryset(self.field_value, self.request.session, self.select_from_all)
        else:
            qs = self.model.objects.all()

            if self.q:
                qs = qs.filter(**{f'{self.field_name}__{self.field_operation}': self.field_value})

        # In django_rich_views.views.get_form_generic
        # the DAL widgets are configured to call Javascript functions
        # to deliver forward information. We receive it here as a forward GET param:
        forward = self.request.GET.get("forward", None)

        # It's a JSON dict so unpack that
        forward = json.loads(forward) if forward else None

        # It is designed to support exclusion of PKs from the returned queryset
        # and hence named "exclude"
        exclude = forward.get("exclude") if forward else None

        # It should be delievers a a CSV list by the Javascrip registered handler
        exclude = exclude.split(",") if exclude else None

        # These must be ints
        exclude = [int(pk) for pk in exclude] if exclude else None

        if exclude:
            qs = qs.exclude(pk__in=exclude)

        # DAL applies pagination by default. When prepopulating controls we don't want that, we want
        # all the results, not one page in a paginated result set. We offer this with an optional
        # GET parameter "all" This is very different to the kwarg "all" above which request a select
        # from all objects. This one requests all the requested objects to be returned, not a page of
        # them.
        if 'all' in self.request.GET:
            self.paginate_by = 0  # Disables pagination

        return qs


def ajax_Selector(request, app, model, pk):
    '''
    Support AJAX fetching of a select box text for a given pk.

    Specificially in support of a django-autocomplete-light select2 widget that
    we may need to provide with initial data in javascript that builds formsets
    dynamically from supplied data.

    Expects models to provide a selector_field attribute.
    '''
    Model = class_from_string(app, model)

    selector = ""
    if getattr(Model, "selector_field", None):
        try:
            Object = Model.objects.get(pk=pk)
            selector_field = getattr(Object, "selector_field", "")
            # Use the selector_field if possible, fall back on a basic
            # string representation of Object.
            selector = getattr(Object, selector_field, str(Object))
        except:
            # If we fail to find an Object, fail silently.
            pass

    return HttpResponse(selector)
