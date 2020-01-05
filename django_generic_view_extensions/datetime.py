'''
Django Generic View Extensions

Datetime management   
'''
# Python imports
import pytz
from datetime import datetime, timedelta

# Django imports
from django.utils.formats import localize
from django.utils.timezone import make_naive, localtime

def datetime_format_python_to_PHP(python_format_string):
    '''Given a python datetime format string, attempts to convert it to the nearest PHP datetime format string possible.'''
    python2PHP = {"%a": "D", "%a": "D", "%A": "l", "%b": "M", "%B": "F", "%c": "", "%d": "d", "%H": "H", "%I": "h", "%j": "z", "%m": "m", "%M": "i", "%p": "A", "%S": "s", "%U": "", "%w": "w", "%W": "W", "%x": "", "%X": "", "%y": "y", "%Y": "Y", "%Z": "e", "%z": "O" }

    php_format_string = python_format_string
    for py, php in python2PHP.items():
        php_format_string = php_format_string.replace(py, php)

    return php_format_string

def is_dst(zonename):
    '''Given the name of Timezone will attempt determine if that timezone is in Daylight Saving TIMe now (DST)'''
    tz = pytz.timezone(zonename)
    now = pytz.utc.localize(datetime.utcnow())
    return now.astimezone(tz).dst() != timedelta(0)

def time_str(date_time):
    '''
    A very simple one liner to return a formatted local naive date time from a database time.
    
    As this is done in many places, to format date_times, it is captured here.
        
    localtime() - converts date_time from the database stored UTC time, to local time as defined by Django's activate()
    make_naive() - just strips the timezone info so the default str() representation doesn't have the timezone data
    localize() - produces the string format defined in Django settings, typically by DATETIME_FORMAT
    '''
    # FIXME: the RFC5322 format introduces a bizarre TZ artifact. Grrr. 
    #        Try the DATETIME_FORMAT 'D,  j M Y H:i'
    return localize(make_naive(localtime(date_time)))

UTC = pytz.timezone('UTC')

def fix_time_zone(dt, tz=UTC):
    '''
    A simple function that takes a datetime object and if it has no tzinfo will give it some 
    assuming its UTC.
    '''
    if not dt is None: 
        if dt.tzinfo == None:
            return tz.localize(dt)
        elif dt.tzinfo != tz:
            return dt.astimezone(tz)
        
    return dt
