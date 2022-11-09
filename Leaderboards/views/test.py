#===============================================================================
# Testrelated views
#
# A work in progress, just for simple test views.
#
# FIrst created for the (Djang Autocomplete Light) DAL test view
#===============================================================================
from .widgets import html_selector

from django.http.response import HttpResponse

from dal import autocomplete

from Leaderboards.models import League, ALL_LEAGUES


def view_DALtest(request):  # @UnusedVariable
    '''
    A simple view that shows two DAL widgets (or one) afor etsting the client side code
    '''

    js = """
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.6.0/jquery.js" crossorigin="anonymous"></script>
    """
    # <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/select2-bootstrap-theme/0.1.0-beta.10/select2-bootstrap.min.css" integrity="sha512-kq3FES+RuuGoBW3a9R2ELYKRywUEQv0wvPTItv3DSGqjpbNtGWVdvT8qwdKkqvPzT93jp8tSF4+oN4IeTEIlQA==" crossorigin="anonymous" referrerpolicy="no-referrer" />
    # <script>$.fn.select2.defaults.set( "theme", "bootstrap" );</script>
    # <script src="https://cdnjs.cloudflare.com/ajax/libs/select2/4.0.13/js/select2.full.js" crossorigin="anonymous"></script>

    dal_media = autocomplete.Select2().media

    single = html_selector(League, "id_league", 0, ALL_LEAGUES)
    multi = ""  # html_selector(League, "id_leagues", 0, ALL_LEAGUES, multi=True)

    html = f"<head>{js}\n{dal_media}</head><body><p>{single}</p><p>{multi}</p></body>"

    return HttpResponse(html)
