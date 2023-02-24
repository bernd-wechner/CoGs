#===============================================================================
# Views for the Game Session Importer
#===============================================================================

from django.shortcuts import render

from .formats.bgstats import import_sessions

from django.contrib.auth.mixins import LoginRequiredMixin

from django_rich_views.views import RichCreateView
from django_rich_views.render import rich_render


class view_Import(LoginRequiredMixin, RichCreateView):
    template_name = 'import.html'


def view_Map(request):
    filename = "/media/Data/Cloud/NextCloud/CoGs/Data/Russell/bggstats-exp-221114.zip"
    # filename = "/media/Data/Workspace/Eclipse/CoGs/Seed Data/BG Stats/bernd-bgstats.json"
    # filename = "/media/Data/Workspace/Eclipse/CoGs/Seed Data/BG Stats/HansaTeutonica-play220716231414.bgsplay"
    return rich_render(request, 'maps.html', context=import_sessions(filename))

