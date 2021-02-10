'''
Django Generic View Extensions

Datetime management   
'''
# Python imports
import pytz
from datetime import datetime, timedelta
from dateutil import parser

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
        
    localtime()  - converts date_time from the database stored UTC time, to local time as defined by Django's activate()
    make_naive() - just strips the timezone info so the default str() representation doesn't have the timezone data
    localize()   - produces the string format defined in Django settings, typically by DATETIME_FORMAT
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

def decodeDateTime(dt):
    '''
    decodes a DateTime that was URL encoded. 
    Has to agree with the URL encoding chosen by the Javascript that 
    fetches leaderboards though an AJAX call of course.
    
    The colons are encoded as : - Works on Chrome even though it's 
    a reserved character not encouraged for URL use. 
    
    The space between date and time is encoded as + and so arrives
    as a space. 
    
    A - introducing the timezone passes through unencoded.
    
    A + introducing the timezone arrives here as a space
    
    Just in case : in the URL does cause an issue, up front we'll
    support - which travels undamaged from URL to here, as the 
    hh mm ss separator.
    
    All the while we are using the ISO 8601 format for datetimes,
    or encoded versions of it that we try to decode here.
    
    ref1 and ref 2 are ISO 8601 datetimes with and without timezone
    used do our work here.                         
    
    :param dt: A URL encoded date time
    '''
    ref1 = "2019-03-01 18:56:16+1100"
    ref2 = "2019-03-01 18:56:16"
    ref3 = "2019-03-01"
    
    # strings are immutable and we need to listify them to 
    # make character referenced substitutions
    new = list(dt)
    
    if not len(dt) in [len(ref1), len(ref2), len(ref3)]:
        return dt
    
    if len(dt) == len(ref1):
        if dt[-5] == " ":
            new[-5] = "+"
    
    if len(dt) >= len(ref2):
        # The first time colon (was encoded as -)
        if dt[13] == "-":
            new[13] = ":"
    
        # The second time colon (was encoded as -)
        if dt[16] == "-":
            new[16] = ":"

    # The n stringify the list again. 
    decoded = "".join(new)
    
    return fix_time_zone(parser.parse(decoded))

# A Javascript function that encodes a datetime (the partner of decodeDateTime above. 
#
#         function encodeDateTime(datetime) {
#             // We communicate datetimes in the ISO 8601 format:
#             // https://en.wikipedia.org/wiki/ISO_8601
#             // but in URLs they turn into an ugly mess. If we make a few simple URL safe
#             // substitutions and unmake them at the server end all is good, and URLs
#             // become
#             // legible approximations to ISO 8601.
#             //
#             // Of note:
#             //
#             // + is a standard way to encode a space in URL. Though encodeURIComponent
#             // opts for %20.
#             // we can use + safely and it arrives at server as a space.
#             //
#             // : is encoded as %3A. It turns out : is not a recommended URL character
#             // and a
#             // reserved character, but it does transport fine at least on Chrome tests.
#             // Still we can substitue - for it and that is safe legible char already in
#             // use on the dates and can be decoded back to : by the server.
#             //
#             // The Timezone is introduced by + or -
#             //
#             // - travels unhindered. Is a safe URL character.
#             // + is encoded as %2B, but we can encode it with + which translates to a
#             // space at the server, but known we did this it can decdoe the space back
#             // to +.
#             return encodeURIComponent(datetime).replace(/%20/g, "+").replace(/%3A/g, "-").replace(/%2B/g, "+");
#         }
