# Python Imports
from time import time
from operator import add
from functools import reduce
import re
from re import RegexFlag as ref # Specifically to avoid a PyDev Error in the IDE.

# Django Imports
from django.db import connection
from django.conf import settings

class StatsMiddleware(object):

    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Uncomment the following if you want to get stats on DEBUG=True only
#         if not settings.DEBUG:
#             return self.get_response(request)

        # get number of db queries before we do anything
        n = len(connection.queries)

        # time the view
        start = time()
        response = self.get_response(request)
        total_time = time() - start

        # compute the db time for the queries just run
        db_queries = len(connection.queries) - n
        if db_queries:
            db_time = reduce(add, [float(q['time'])
                                   for q in connection.queries[n:]])
        else:
            db_time = 0.0

        # and backout python time
        python_time = total_time - db_time
        
        stats = br''.join((br'<div id="stats"><table><tr>'
                           br'<td><b>STATS:</b></td>',
                           br'<td style="padding-left: 5ch;">Total Time:</td><td>', "{:.1f} ms".format(total_time*1000).encode(), br'</td>',
                           br'<td style="padding-left: 5ch;">Python Time:</td><td>', "{:.1f} ms".format(python_time).encode(), br'</td>',
                           br'<td style="padding-left: 5ch;">DB Time:</td><td>', "{:.1f} ms".format(db_time).encode(), br'</td>',
                           br'<td style="padding-left: 5ch;">Number of Queries:</td><td>', "{:,}".format(db_queries).encode(), br'</td>', 
                           br'</tr></table></div>\1'))

        # Insert the stats just prior to the body close tag (we need to update the Content-Length header or browser won't render it all.
        if response and getattr(response, 'content', False):
            response.content = re.sub(br"(</body>)", stats, response.content, flags=ref.IGNORECASE)
            response['Content-Length'] = str(len(response.content))                        

        return response
    