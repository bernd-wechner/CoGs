'''
Django Generic View Extensions

Debug functions

Used from time to time in debugging the package

Functions that add to the context that templates see.
'''
# Python imports
from time import time
import re
from re import RegexFlag as ref # Specifically to avoid a PyDev Error in the IDE.

# Django imports
from django.conf import settings 

debug_time_first = None
debug_time_last = None

RE = re.compile(r'^(?P<newlines1>\n*)(?P<message>.*?)(?P<newlines2>\n*)$', ref.DOTALL)

def print_debug(msg):
    '''
    Prints a timestamped message to stdout with timestamps for tracing.
    '''
    if settings.DEBUG:
        global debug_time_first
        global debug_time_last
        now = time()  # the time in seconds since the epoch as a floating point number.
        if debug_time_first is None:
            debug_time_first = now
        if debug_time_last is None:
            debug_time_last = now
        
        matches = RE.match(msg).groupdict()
        
        print("f{matches['newlines1']}{now-debug_time_first:10.4f}, {now-debug_time_last:10.4f} - {matches['message']}{matches['newlines2']}")
        debug_time_last = now    
