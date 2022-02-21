# TODO: Add account security, and test it
# TODO: Once account security is in place a player will be in certain leagues,
#      restrict some views to info related to those leagues.
# TODO: Add testing: https://docs.djangoproject.com/en/1.10/topics/testing/tools/

from .site import view_Home, view_Login, view_About
from .generic import view_Add, view_Edit, view_Delete, view_Detail, view_List
from .inspect import view_Inspect

from .leaderboards import view_Leaderboards, ajax_Leaderboards
from .events import view_Events, ajax_Events
from .session_impact import view_Impact

from .ajax import ajax_List, ajax_Detail, ajax_Game_Properties, ajax_BGG_Game_Properties

from .post_receivers import receive_ClientInfo, receive_DebugMode, receive_Filter

from .admin import view_CheckIntegrity, view_RebuildRatings, view_UnwindToday, view_Kill, view_Fix
