#===============================================================================
# Customize Generic Views for CoGs
#===============================================================================
from django.contrib.auth.mixins import LoginRequiredMixin

from django_rich_views.views import RichDetailView, RichDeleteView, RichCreateView, RichUpdateView, RichListView
from django_rich_views.options import list_display_format, object_display_format

from .form_initialisers import form_init
from .pre_handlers import pre_dispatch_handler, pre_validation_handler, pre_transaction_handler, pre_save_handler, pre_commit_handler, pre_delete_handler
from .post_handlers import post_delete_handler, post_save_handler
from .context import extra_context_provider

# TODO: Ranks, Performances  etc. Fix edit forms
# 1. No Creating allowed, only created when a Session is created. Need a way in model to say "no creation"
# 2. On update, some fields are editable, others not (like the name of a team can be changed, but not its members)
#    We currently list only editable fields. We should list uneditable ones as well in the manner of a DetailView.
#
# For Teams: edit Name, list players (which is the intrinsic_relations for the session form)
# For Ranks: No edits at all, all edited via Sessions
# For Performances: edit Partial Play Weighting only and display Session and Player (no edit).
#
# None of this should be super complicated because intent is to only edit these through
# Session objects anyhow and the Team, Rank, Perfromance and related objects will not even
# be available on production menues, only for the admin for drilling down
# and debugging.


class view_Add(LoginRequiredMixin, RichCreateView):
    template_name = 'generic/form.html'
    # fields = '__all__'
    pre_dispatch = pre_dispatch_handler
    extra_context_provider = extra_context_provider
    form_init = form_init
    pre_validation = pre_validation_handler
    pre_transaction = pre_transaction_handler
    pre_save = pre_save_handler
    pre_commit = pre_commit_handler
    post_save = post_save_handler


class view_Edit(LoginRequiredMixin, RichUpdateView):
    template_name = 'generic/form.html'
    pre_dispatch = pre_dispatch_handler
    extra_context_provider = extra_context_provider
    pre_validation = pre_validation_handler
    pre_transaction = pre_transaction_handler
    pre_save = pre_save_handler
    pre_commit = pre_commit_handler
    post_save = post_save_handler


class view_Delete(LoginRequiredMixin, RichDeleteView):
    # TODO: When deleting a session need to check for ratings that refer to it as last_play or last_win
    #        and fix the reference or delete the rating.
    template_name = 'generic/delete.html'
    format = object_display_format()
    extra_context_provider = extra_context_provider
    pre_delete = pre_delete_handler
    post_delete = post_delete_handler


class view_List(RichListView):
    template_name = 'generic/list.html'
    format = list_display_format()
    extra_context_provider = extra_context_provider


class view_Detail(RichDetailView):
    template_name = 'generic/detail.html'
    format = object_display_format()
    extra_context_provider = extra_context_provider
