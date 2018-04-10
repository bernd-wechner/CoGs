'''
Django Generic View Extensions

Debug functions

Used from time to time in debugging the package

Functions that add to the context that templates see.
'''
# Python imports
from time import time


debug_time_first = None
debug_time_last = None

def print_debug(msg):
    '''
    Prints a timestamped message to stdout with timestamps for tracing.
    '''
    global debug_time_first
    global debug_time_last
    now = time()  # the time in seconds since the epoch as a floating point number.
    if debug_time_first is None:
        debug_time_first = now
    if debug_time_last is None:
        debug_time_last = now
    print("{:10.4f}, {:10.4f} - {}".format(now-debug_time_first, now-debug_time_last, msg))
    debug_time_last = now    
