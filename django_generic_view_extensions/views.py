'''
Django Generic View Extensions

The Views themselves

Provides:

    ListViewExtended
    DetailViewExtended
    DeleteViewExtended
    CreateViewExtended
    UpdateViewExtended

which all derive from the class of the same name less Extended (i.e. the standard Djago Generic Views).

These Extensions aim at providing primarily two things:

1) Support for rich objects (objects which make sense only as a collection of model instances).
2) Generic detail and list in the same ilk as Djangos Generic Form view, providing easy HTML for rapid easy generic rendering.

In the process it also supports Field Privacy and Admin fields though these were spun out as independent packages.
'''
# Python imports
import os, datetime  # , sys, traceback

# Django imports
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.views import LoginView

from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.db import connection, transaction
from django.db.models.query import QuerySet
from django.db.utils import IntegrityError
from django.http.response import JsonResponse, HttpResponse, HttpResponseRedirect
from django.http.request import QueryDict
from django.forms.models import fields_for_model, ModelChoiceField, ModelMultipleChoiceField
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError

# 3rd Party package imports (dependencies)
from url_filter.filtersets import ModelFilterSet
from cuser.middleware import CuserMiddleware
from dal import autocomplete

# Package imports
from . import log
from .util import app_from_object, class_from_string
from .html import list_html_output, object_html_output, object_as_html, object_as_table, object_as_ul, object_as_p, object_as_br
from .context import add_model_context, add_timezone_context, add_format_context, add_filter_context, add_ordering_context, add_debug_context
from .options import get_list_display_format, get_object_display_format
from .neighbours import get_neighbour_pks
from .model import collect_rich_object_fields, inherit_fields, add_related
from .related_forms import RelatedForms
from .filterset import format_filterset, is_filter_field

# import sys, os
# print(f'DEBUG: current trace function in {os.getpid()}', sys.gettrace())
# # import pydevd;
# # pydevd.settrace()
# def trace_func(frame, event, arg):
#     with open(f"pydev-trace-{os.getpid()}.txt", 'a') as f:
#         print('Context: ', frame.f_code.co_name, '\tFile:', frame.f_code.co_filename, '\tLine:', frame.f_lineno, '\tEvent:', event, file=f)
#     return trace_func
#
# sys.settrace(trace_func)
# print(f'DEBUG: current trace function in {os.getpid()}', sys.gettrace())


def get_filterset(self):
    FilterSet = type("FilterSet", (ModelFilterSet,), {
        'Meta': type("Meta", (object,), {
            'model': self.model
            })
    })

    qs = self.model.objects.all()

    qd = QueryDict('', mutable=True)

    # Add the GET parameter sunconditionally, a user request overrides
    if hasattr(self.request, 'GET'):
        qd.update(self.request.GET)

    # Use the session stored filter as a fall back, it is expected
    # in session["filter"] as a dictionary of (pseudo) fields and
    # values. Thatis to say, they are  nominally fields in the model,
    # but don't need to be, as long as they are keys into
    # session["filter_priorities"] which defines prioritised lists of
    # fields for that key.
    session = self.request.session
    if 'filter' in session:
        model = self.model

        # the filters we make a copy of as we may be modifying them
        # based on the filter_priorities, and don't want to modify
        # the session stored filters (our mods are only used for
        # selecting the model field to filter on based on stated
        # priorities).
        filters = session["filter"].copy()
        priorities = session.get("filter_priorities", {})

        # Now if priority lists are supplied we apply them keeping only the highest
        # priority field in any priority list in the list of priorities.
        for f in session["filter"]:
            if f in priorities:
                p = priorities[f]
                highest = len(p)  # Initial value, one greater than the largest index in the list
                for i, field in enumerate(reversed(p)):
                    if is_filter_field(model, field):
                        highest = len(p) - i - 1

                # If we found one or more fields in the priority list that are
                # filterable we must now have the highest priority one, we replace
                # the pseudo filter field with this field.
                if highest < len(p):
                    F = p[highest]
                    val = filters[f]
                    del filters[f]
                    filters[F] = val

        # Now the GET filters were already to qd, so we throw out any
        # session filters already in there as we provide priority to
        # user specified filters in the GET params over the session
        # defined fall backs.
        F = filters.copy()
        for f in filters:
            if f in qd:
                del F[f]

        qd.update(F)

    # TODO: test this with GET params and session filter!
    fs = FilterSet(data=qd, queryset=qs)

    # get_specs raises an Empty exception if there are no specs, and a ValidationError if a value is illegal
    try:
        specs = fs.get_specs()
    except:
        specs = []

    if len(specs) > 0:
        fs.fields = format_filterset(fs)
        fs.text = format_filterset(fs, as_text=True)
        return fs
    else:
        return None


def get_ordering(self):
    if (self.format.ordering):
        return self.format.ordering.split(',')
    else:
        return getattr(self.model._meta, 'ordering', None)


class LoginViewExtended(LoginView):

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        add_timezone_context(self, context)
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        form.request.session['timezone'] = form.request.POST['timezone']
        return response


class TemplateViewExtended(TemplateView):
    '''
    An extension of the basic TemplateView for a home page on the site say (not related to any model)
    which provides some extra context if desired in a manner compatible with the other Extended Views
    '''

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        add_timezone_context(self, context)
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        return context


class ListViewExtended(ListView):
    # HTML formattters stolen straight form the Django ModelForm class basically.
    # Allowing us to present lists basically with the same flexibility as pre-formattted
    # HTML objects.
    _html_output = list_html_output

    as_table = object_as_table
    as_ul = object_as_ul
    as_p = object_as_p
    as_br = object_as_br
    as_html = object_as_html  # Chooses one of the first four based on request parameters

    # Fetch all the objects for this model
    def get_queryset(self, *args, **kwargs):
        if settings.DEBUG:
            log.debug(f"Getting Queryset for List View. Process ID: {os.getpid()}.")
            if len(self.request.GET) > 0:
                log.debug(f"GET parameters:")
                for key, val in self.request.GET.items():
                    log.debug(f"\t{key}={val}")
            else:
                log.debug(f"No GET parameters!")

        self.app = app_from_object(self)
        self.model = class_from_string(self, self.kwargs['model'])

        # Communicate the request user to the models (Django doesn't make this easy, need cuser middleware)
        CuserMiddleware.set_user(self.request.user)

        self.format = get_list_display_format(self.request.GET)

        self.ordering = get_ordering(self)

        self.filterset = None  # Default

        fs = None
        if len(self.request.GET) > 0 or len(self.request.session.get("filter", {})) > 0:
            # If the URL has GET parameters (following a ?) then self.request.GET
            # will contain a dictionary of name: value pairs that FilterSet uses
            # construct a new filtered queryset.
            fs = get_filterset(self)

        # If there is a filter specified in the URL
        if fs:
            self.filterset = fs
            self.queryset = fs.filter()
        else:
            self.queryset = self.model.objects.all()

        if (self.ordering):
            self.queryset = self.queryset.order_by(*self.ordering)

        if settings.DEBUG:
            log.debug(f"ordering  = {self.ordering}")
            log.debug(f"filterset = {self.filterset.get_specs()}")

        self.count = len(self.queryset)

        return self.queryset

    # Add some model identifiers to the context (if 'model' is passed in via the URL)
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        add_model_context(self, context, plural=True)
        add_timezone_context(self, context)
        add_format_context(self, context)
        add_filter_context(self, context)
        add_ordering_context(self, context)
        add_debug_context(self, context)
        context["total"] = self.model.objects.all().count
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        return context


class DetailViewExtended(DetailView):
    '''
    An enhanced DetailView which provides the HTML output methods as_table, as_ul and as_p just like the ModelForm does (defined in BaseForm).
    '''
    # HTML formatters stolen straight form the Django ModelForm class
    # Allowing us to present object detail views  basically with the same flexibility
    # as pre-formattted HTML objects.
    _html_output = object_html_output

    as_table = object_as_table
    as_ul = object_as_ul
    as_p = object_as_p
    as_br = object_as_br
    as_html = object_as_html  # Chooses one of the first three based on request parameters

    # Override properties with values passed as arguments from as_view()
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if ('operation' in kwargs):
            self.operation = kwargs['operation']

    # Add some model identifiers to the context (if 'model' is passed in via the URL)

    # Fetch the URL specified object, needs the URL parameters "model" and "pk"
    def get_object(self, *args, **kwargs):
        self.model = class_from_string(self, self.kwargs['model'])
        self.pk = self.kwargs['pk']

        # Communicate the request user to the models (Django doesn't make this easy, need cuser middleware)
        CuserMiddleware.set_user(self.request.user)

        # Get the ordering
        self.ordering = get_ordering(self)

        # Get Neighbour info for the object browser
        self.filterset = get_filterset(self)

        neighbours = get_neighbour_pks(self.model, self.pk, filterset=self.filterset, ordering=self.ordering)

        # Support for incoming next/prior requests via a GET
        if 'next' in self.request.GET or 'prior' in self.request.GET:
            self.ref = get_object_or_404(self.model, pk=self.pk)

            # If requesting the next or prior object look for that
            # FIXME: Totally fails for Ranks, the get dictionary fails when there are ties!
            #        Doesn't generalise well at all. Must find a general way to do this for
            #        arbitrary orders. Still should specify orders in models that create unique
            #        ordering not reliant on pk break ties.
            if neighbours:
                if 'next' in self.request.GET and not neighbours[1] is None:
                    self.pk = neighbours[1]
                elif 'prior' in self.request.GET and not neighbours[0] is None:
                    self.pk = neighbours[0]

            self.obj = get_object_or_404(self.model, pk=self.pk)
            self.kwargs["pk"] = self.pk
        else:
            self.obj = get_object_or_404(self.model, pk=self.pk)

        # Add this information to the view (so it's available in the context).
        self.object_browser = neighbours

        self.format = get_object_display_format(self.request.GET)

        collect_rich_object_fields(self)

        return self.obj

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        add_model_context(self, context, plural=False)
        add_timezone_context(self, context)
        add_format_context(self, context)
        add_filter_context(self, context)
        add_ordering_context(self, context)
        add_debug_context(self, context)
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        return context

# TODO: Ranks, Performances  etc. Fix edit forms
# 1. No Creating allowed, only created when a Session is created. Need a way in model to say "no creation"
# 2. On update, some fields are editable, others not (like the name of a team can be changed, but not its members)
#    We currently list only editable fields. We should list uneditable ones as well in the manner of a DetailView.
#
# For Teams: edit Name, list players (which is the add_related for the session form)
# For Ranks: No edits at all, all edited via Sessions
# For Performances: edit Partial Play Weighting only and display Session and Player (no edit).
#
# None of this should be super complicated because intent is to only edit these through
# Session objects anyhow and the Team, Rank, Perfromance and related objects will not even
# be available on production menues, only for the admin for drilling down and debugging.


def get_context_data_generic(self, *args, **kwargs):
    '''
    Augments the standard context with model and related model information
    so that the template in well informed - and can do Javascript wizardry
    based on this information

    :param self: and instance of CreateView or UpdateView

    This is code shared by the two views so peeled out into a generic.
    '''
    # We need to set self.model here
    self.app = app_from_object(self)
    self.model = class_from_string(self, self.kwargs['model'])
    if not hasattr(self, 'fields') or self.fields == None:
        self.fields = '__all__'

    # Communicate the request user to the models (Django doesn't make this easy, need cuser middleware)
    CuserMiddleware.set_user(self.request.user)

    if isinstance(self, CreateView):
        # Note that the super.get_context_data initialises the form with get_initial
        context = super(CreateView, self).get_context_data(*args, **kwargs)
    elif isinstance(self, UpdateView):
        # Note that the super.get_context_data initialises the form with get_object
        context = super(UpdateView, self).get_context_data(*args, **kwargs)
    else:
        raise NotImplementedError("Generic get_context_data only for use by CreateView or UpdateView derivatives.")

    # Now add some context extensions ....
    add_model_context(self, context, plural=False, title='New')
    add_timezone_context(self, context)
    add_debug_context(self, context)
    if callable(getattr(self, 'extra_context_provider', None)):
        context.update(self.extra_context_provider(context))

    return context


def get_form_generic(self):
    '''
    Augments the standard form with related model forms
    so that the template in well informed - and can do
    Javascript wizardry based on this information

    :param self: and instance of CreateView or UpdateView

    This is code shared by the two views so peeled out into a generic.
    '''
    model = self.model
    selector = getattr(model, "selector_field", None)

    if isinstance(self, CreateView):
        form = super(CreateView, self).get_form()
    elif isinstance(self, UpdateView):
        form = super(UpdateView, self).get_form()
    else:
        raise NotImplementedError("Generic get_form only for use by CreateView or UpdateView derivatives.")

    # Attach DAL (Django Autocomplete Light) Select2 widgets to all the mdoel selectors
    for field in form.fields.values():
        if isinstance(field, ModelChoiceField):
            field_model = field.queryset.model
            selector = getattr(field_model, "selector_field", None)
            if not selector is None:
                url = reverse_lazy('autocomplete', kwargs={"model": field_model.__name__, "field_name": selector})
                if isinstance(field, ModelMultipleChoiceField):
                    field.widget = autocomplete.ModelSelect2Multiple(url=url)
                else:
                    field.widget = autocomplete.ModelSelect2(url=url)

                field.widget.choices = field.choices

    if len(add_related(model)) > 0:
        if len(getattr(self.request, 'POST', [])) > 0:
            form_data = self.request.POST
        elif len(getattr(self.request, 'GET', [])) > 0:
            form_data = self.request.GET
        else:
            form_data = None

        if isinstance(getattr(self, "object", None), model):
            db_object = self.object
        else:
            db_object = None

        # related_forms = get_related_forms(model, form_data, db_object)
        related_forms = RelatedForms(model, form_data, db_object)

        for related_form in related_forms.values():
            for field in related_form.fields.values():
                if isinstance(field, ModelChoiceField):
                    field_model = field.queryset.model
                    selector = getattr(field_model, "selector_field", None)
                    if not selector is None:
                        url = reverse_lazy('autocomplete', kwargs={"model": field_model.__name__, "field_name": selector})
                        if isinstance(field, ModelMultipleChoiceField):
                            field.widget = autocomplete.ModelSelect2Multiple(url=url)
                        else:
                            field.widget = autocomplete.ModelSelect2(url=url)

                        field.widget.choices = field.choices

        form.related_forms = related_forms

    return form


def post_generic(self, request, *args, **kwargs):
    '''
    Processes a form submission.

    :param self: and instance of CreateView or UpdateView

    This is code shared by the two views so peeled out into a generic.
    '''
    # Just reflect the POST data back to client for debugging if requested
    if self.request.POST.get("debug_post_data", "off") == "on":
        html = "<h1>self.request.POST:</h1>"
        html += "<table>"
        for key in sorted(self.request.POST):
            html += "<tr><td>{}:</td><td>{}</td></tr>".format(key, self.request.POST[key])
        html += "</table>"
        return HttpResponse(html)

    self.model = class_from_string(self, self.kwargs['model'])
    if not hasattr(self, 'fields') or self.fields == None:
        self.fields = '__all__'

    if isinstance(self, CreateView):
        # The self.object atttribute MUST exist and be None in a CreateView.
        self.object = None
    elif isinstance(self, UpdateView) or isinstance(self, DeleteView):
        self.object = self.get_object()
    else:
        raise NotImplementedError("Generic post only for use by CreateView or UpdateView derivatives.")

    # Delete is handled specially (it's much simpler that Create and Update Views)
    if isinstance(self, DeleteView):
        # Hook for pre-processing steps (before the object is actually deleted)
        # The handler can return a kwargs dict to pass to the post delete handler.
        if callable(getattr(self, 'pre_delete', None)):
            next_kwargs = self.pre_delete()
            if not next_kwargs: next_kwargs = {}
            if "debug_only" in next_kwargs:
                return HttpResponse(next_kwargs["debug_only"])

        with transaction.atomic():
            log.debug(f"Deleting: {self.object._meta.object_name} {self.object.pk}.")

            # For deletes we won't concern ourselves with related forms.
            # Generally the on_delete property of ForeignKey relations will hanld cascading
            # deletes if properly configured in the models, and if any special follow-on
            # deletes or other actions are needed the pre_delete and post_delete hooks are
            # available for a derived class lient to manage that in code explicitly.
            response = self.delete(request, *args, **kwargs)

            # Hook for post-processing steps (after the object is actually deleted)
            # Accept arguments from the pre_handler
            if callable(getattr(self, 'post_delete', None)):
                self.post_delete(**next_kwargs)

        return response

    # Create and Update are comparatively similar
    # There's a form that contains the submission and we want to
    # validate it before we commit any changes to the database.
    else:
        # Get the form
        self.form = self.get_form()

        # Just reflect the form data back to client for debugging if requested
        if self.request.POST.get("debug_form_data", "off") == "on":
            html = "<h1>self.form.data:</h1>"
            html += "<table>"
            for key in sorted(self.form.data):
                html += "<tr><td>{}:</td><td>{}</td></tr>".format(key, self.form.data[key])
            html += "</table>"
            return HttpResponse(html)

        # Hook for pre-processing the form (before the data is saved)
        if callable(getattr(self, 'pre_save', None)):
            next_kwargs = self.pre_save()
            if not next_kwargs: next_kwargs = {}
            if "debug_only" in next_kwargs:
                return HttpResponse(next_kwargs["debug_only"])

        log.debug(f"Connection vendor: {connection.vendor}")
        if connection.vendor == 'postgresql':
            log.debug(f"Is_valid? {self.form.data}")
            if self.form.is_valid():
                try:
                    log.debug(f"Open a transaction")
                    with transaction.atomic():
                        log.debug("Saving form from POST request containing:")
                        for (key, val) in sorted(self.request.POST.items()):
                            # See: https://code.djangoproject.com/ticket/1130
                            # list items are hard to identify it seems in a generic manner
                            log.debug(f"\t{key}: {val} & {self.request.POST.getlist(key)}")

                        self.object = self.form.save()
                        log.debug(f"Saved object: {self.object._meta.object_name} {self.object.pk}.")

                        kwargs = self.kwargs
                        kwargs['pk'] = self.object.pk

                        # By default, on success jump to a view of the obbject just submitted.
                        if not self.success_url:
                            self.success_url = reverse_lazy('view', kwargs=kwargs)

                        if isinstance(self, CreateView):
                            # Having saved the root object we reinitialise related forms
                            # with that object attached. Failure to this results in the
                            # form_clean failing as the formsets don't have populated
                            # back references (as we had not object) and it fails with
                            # 'This field is required.' erros on the primary keys
                            self.form.related_forms = RelatedForms(self.model, self.form.data, self.object)

                        if hasattr(self.form, 'related_forms') and isinstance(self.form.related_forms, RelatedForms):
                            log.debug(f"Saving the related forms.")
                            if self.form.related_forms.are_valid():
                                self.form.related_forms.save()
                                log.debug(f"Saved the related forms.")
                            else:
                                log.debug(f"Invalid related forms. Errors: {self.form.related_forms.errors}")
                                # Attach the newly annotated (with errros) related forms to the
                                # form so that theyt reach the response template.
                                # self.form.related_forms = related_forms
                                # We raise an exception to break out of the
                                # atomic transaction triggering a rollback.
                                raise ValidationError(f"Related forms ({', '.join(list(self.form.related_forms.errors.keys()))}) are invalid.")

                        # Give the object a chance to cleanup relations before we commit.
                        # Really a chance for the model to set some standards on relations
                        # They are all saved in the transaction now and the object can see
                        # them all in the ORM (the related objects that is)
                        if callable(getattr(self.object, 'clean_relations', None)):
                            self.object.clean_relations()

                        # Finally before committing give the view defintion a chance to so something
                        # prior to committing the update.
                        if callable(getattr(self, 'pre_commit', None)):
                            next_kwargs = self.pre_commit(**next_kwargs)

                        log.debug(f"Cleaned the relations.")
                except (IntegrityError, ValidationError) as e:
                    # TODO: Work out how to get here with an IntegrityError: what can trigger this
                    # TODO: Report IntegrityErrors too
    #                 exc_type, exc_obj, exc_tb = sys.exc_info()
    #                 fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    #                 print(exc_type, fname, exc_tb.tb_lineno)
    #                 print(traceback.format_exc())
                    self.form.add_error(None, e.message)
                    return self.form_invalid(self.form)

                # Hook for post-processing data (after it's all saved)
                if callable(getattr(self, 'post_save', None)):
                    self.post_save(**next_kwargs)

                return self.form_valid(self.form)
            else:
                return self.form_invalid(self.form)

        else:
            if self.form.is_valid():
                self.object = self.form.save()
                related_forms = RelatedForms(self.model, self.form.data, self.object)
                related_forms.save()

                # Hook for post-processing data (after it's all saved)
                if callable(getattr(self, 'post_save', None)):
                    self.post_save(**next_kwargs)

                if not self.success_url:
                    self.success_url = reverse_lazy('view', kwargs=kwargs)

                return self.form_valid(self.form)
            else:
                return self.form_invalid(self.form)


def form_valid_generic(self, form):
    '''
    If the form is valid, redirect to the supplied URL.

    :param self: and instance of CreateView or UpdateView

    This is code shared by the two views so peeled out into a generic.

    This is specifically intended NOT to call Djangos form_valid()
    implementation which saves the object. In these Extensions we
    perform the save in the post not the form_valid method.
    '''
    return HttpResponseRedirect(self.get_success_url())


class CreateViewExtended(CreateView):
    '''
    A CreateView which makes the model and the related_objects it defines available
    to the View so it can render form elements for the related_objects if desired.

    On a GET request get_context_data() is called to augment the context data for the form render,
    then get_initial() is called for initial values of the form fields.

    On a POST request post() is called to validate the submission and save it if good
    or bounce back with a rerender of the form with errors listed.

    Both sequences need to defined these:
        self.model
        self.fields

    So we do it in get_context_data() and in post() as our two entry points.

    Both call get_queryset() in order to obtain the model from the returned queryset, if it's not
    defined in self.model. And so we could define self.model and self.fields in one place. But it
    is a little odd and confusing to think of get_queryset() for a CreateView, so here we avoid
    that convenience and confusions.

    NOTE: We do also include a form_valid() override. This is important because in the standard
    Django post/form_valid pair, post does not save, form_valid does. If we defer to the Django
    form_valid it goes and saves the form again. This doesn't create a new copy on creates as it
    happens that by that point self.instance already has a PK thanks to the save here in post() but
    it is an unnecessary repeat save all the same.
    '''

    get_context_data = get_context_data_generic
    get_form = get_form_generic
    post = post_generic
    form_valid = form_valid_generic

    def get_initial(self):
        '''
        Returns a dictionary of values keyed on model field names that are used to populated the form widgets
        with initial values.
        '''
        initial = super().get_initial()

        try:
            # TODO: Consider gerting the last object created by the logged in user instead
            # of the last object created
            last = self.model.objects.latest()
        except ObjectDoesNotExist:
            last = None

        for field_name in inherit_fields(self.model):
            field_value = getattr(last, field_name)
            if (isinstance(field_value, datetime.datetime)):
                initial[field_name] = field_value + getattr(self.model, "inherit_time_delta", datetime.timedelta(0))
            else:
                initial[field_name] = field_value

        return initial

#     def form_invalid(self, form):
#         """
#         If the form is invalid, re-render the context data with the
#         data-filled form and errors.
#         """
#         context = self.get_context_data(form=form)
#         response = self.render_to_response(context)
#         return response


class UpdateViewExtended(UpdateView):
    '''
    An UpdateView which makes the model and the related_objects it defines available to the View so it can render form elements for the related_objects if desired.

    Note: This is almost identical to the CreateViewExtended class above bar one line, where we set self.object!
          Which is precisely how Django differentiates a Create from an Update!

          Aside from that though we define get_object() in place of get_initial().

          Unlike the CreateView on a GET request Django calls get_object() first then get_context_data().
          And on a POST request it just calls post(). So we set up self.model and self.object in
          get_object() for GET requests and post() for POST requests.
    '''

    get_context_data = get_context_data_generic
    get_form = get_form_generic
    post = post_generic
    form_valid = form_valid_generic

    def get_object(self, *args, **kwargs):
        '''Fetches the object to edit and augments the standard queryset by passing the model to the view so it can make model based decisions and access model attributes.'''
        self.pk = self.kwargs['pk']
        self.model = class_from_string(self, self.kwargs['model'])
        self.obj = get_object_or_404(self.model, pk=self.kwargs['pk'])

        if not hasattr(self, 'fields') or self.fields == None:
            self.fields = '__all__'

        if callable(getattr(self.obj, 'fields_for_model', None)):
            self.fields = self.obj.fields_for_model()
        else:
            self.fields = fields_for_model(self.model)

        # Communicate the request user to the models (Django doesn't make this easy, need cuser middleware)
        CuserMiddleware.set_user(self.request.user)

        return self.obj


class DeleteViewExtended(DeleteView):
    '''An enhanced DeleteView which provides the HTML output methods as_table, as_ul and as_p just like the ModelForm does.'''
    # HTML formatters stolen straight form the Django ModelForm class
    _html_output = object_html_output
    as_table = object_as_table
    as_ul = object_as_ul
    as_p = object_as_p
    as_br = object_as_br
    as_html = object_as_html  # Chooses one of the first three based on request parameters
    post = post_generic

    # Override properties with values passed as arguments from as_view()
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if ('operation' in kwargs):
            self.opertion = kwargs['operation']

    # Get the actual object to update
    def get_object(self, *args, **kwargs):
        self.app = app_from_object(self)
        self.model = class_from_string(self, self.kwargs['model'])

        # Communicate the request user to the models (Django doesn't make this easy, need cuser middleware)
        CuserMiddleware.set_user(self.request.user)

        self.pk = self.kwargs['pk']
        self.obj = get_object_or_404(self.model, pk=self.kwargs['pk'])
        self.format = get_object_display_format(self.request.GET)

        # By default jump to a list of objects (fomr which htis one was deleted)
        if not self.success_url:
            self.success_url = reverse_lazy('list', kwargs={'model': self.kwargs['model']})

        collect_rich_object_fields(self)

        return self.obj

    # Add some model identifiers to the context (if 'model' is passed in via the URL)
    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        add_model_context(self, context, plural=False, title='Delete')
        add_timezone_context(self, context)
        add_format_context(self, context)
        add_debug_context(self, context)
        if callable(getattr(self, 'extra_context_provider', None)): context.update(self.extra_context_provider())
        return context

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

        # If this is false then self.selector_queryset is permitted to do pre-filtering
        # (which could be based on any othe rcriteria, like session stored filters for example)
        # If it is true it is denied this permission.
        self.select_from_all = self.kwargs.get('all', False)

        # use the model's selectoprovided selector_queryset if available
        if self.field_name and self.field_name == self.selector_field and callable(self.selector_queryset):
            qs = self.selector_queryset(self.field_value, self.request.session, self.select_from_all)
        else:
            qs = self.model.objects.all()

            if self.q:
                qs = qs.filter(**{f'{self.field_name}__{self.field_operation}': self.field_value})

        return qs


def ajax_Selector(request, app, model, pk):
    '''
    Support AJAX fetching of a select box text for a given pk.

    Specificially in support of a django-autocomplte-light select2 widget that
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
