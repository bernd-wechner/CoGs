#===============================================================================
# Log views
#
# TODO: Implement basic views. The pro forma is in 
#       Leaderboards.views.session_impact.view_Impact
#       which tries to be general impact presenter. 
#       The basic log views are very similar and so by DRY, we shoudl 
#        extract any shared code into functions herein and use them in 
#        view_Impact and here.
#       For now, the hooks are in place. 
#===============================================================================
from ..models.log import ChangeLog, RebuildLog

def view_Change(request, pk):
    clog = ChangeLog.objects.get(pk=int(pk))

def view_Rebuild(request, pk):
    rlog = RebuildLog.objects.get(pk=int(pk))
