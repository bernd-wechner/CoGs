'''
Django Generic View Extensions

Datetime management
'''
# Python imports
import pytz, re
from datetime import datetime, timedelta
from dateutil import parser

# Django imports
from django.utils.formats import localize
from django.utils.timezone import make_naive, is_naive, localtime, get_current_timezone, make_aware as django_make_aware


def safe_tz(tz):
    '''A one-line that converts TZ string to a TimeZone object if needed'''
    return pytz.timezone(tz) if isinstance(tz, str) else tz


def datetime_format_python_to_PHP(python_format_string):
    '''Given a python datetime format string, attempts to convert it to the nearest PHP datetime format string possible.'''
    python2PHP = {"%a": "D", "%a": "D", "%A": "l", "%b": "M", "%B": "F", "%c": "", "%d": "d", "%H": "H", "%I": "h", "%j": "z", "%m": "m", "%M": "i", "%p": "A", "%S": "s", "%U": "", "%w": "w", "%W": "W", "%x": "", "%X": "", "%y": "y", "%Y": "Y", "%Z": "e", "%z": "O" }

    php_format_string = python_format_string
    for py, php in python2PHP.items():
        php_format_string = php_format_string.replace(py, php)

    return php_format_string


def is_dst(zonename=None, when=None):
    '''Given the name of Timezone will attempt determine if that timezone is in Daylight Saving Time now (DST)'''
    if zonename:
        tz = pytz.timezone(zonename)
    else:
        tz = get_current_timezone()

    if when:
        testing_time = when
    else:
        testing_time = pytz.utc.localize(datetime.utcnow())

    # Special case for datetime.min which cannot be given a timezone alas
    return testing_time != datetime.min and testing_time.astimezone(tz).dst() != timedelta(0)


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


def make_aware(date_time, timezone=None):
    '''
    A quick simple improvement in Django's make_aware which takes into account daylight savings time.
    '''
    if is_naive(date_time):
        return django_make_aware(date_time, timezone=timezone, is_dst=is_dst(when=date_time))
    else:
        return date_time


def decodeDateTime(dt, test=False):
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
    used to do our work her

    :param dt: A URL encoded date time
    '''

    # An RE that decomposes a passed in datetime and can accept the translations
    # we perform in URLencoding a datetimes namely:
    #
    # HMS can be separated by : or -
    # Date and time can be separated by T or space
    # Offset sign + can be space (or better said space implies +)
    # The : in the TZ offset is optional and can be -
    # The TZ offset is optional (as a group)
    # Seconds are optional inside of na optiona time group
    # Date is mandatory
    pattern = (r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
               +"(([T\s](?P<hour>\d{2})[:-](?P<minutes>\d{2}))?([:-](?P<seconds>\d{2}))?)?"
               +"\s?"
               +"((?P<offset_sign>[\s+-])(?P<offset_hours>\d{2})[:-]?(?P<offset_minutes>\d{2}))?$")

    if m := re.match(pattern, dt):
        p = m.groupdict()
        decoded = f"{p['year']}-{p['month']}-{p['day']}"
        if not p.get('hour', None) is None: decoded += f" {p['hour']}:{p['minutes']}"
        if not p.get('seconds', None) is None: decoded += f":{p['seconds']}"
        if not p.get('offset_sign', None) is None:
            sign = '+' if p['offset_sign'] in ('+', ' ') else '-'
            decoded += f" {sign}{p['offset_hours']}:{p['offset_minutes']}"

        if test:
            return decoded
        else:
            return parser.parse(decoded)
    else:
        return dt

# A Javascript function that encodes a datetime (the partner of decodeDateTime above.
#
# function encodeDateTime(datetime) {
#     // We communicate datetimes in the ISO 8601 format:
#     // https://en.wikipedia.org/wiki/ISO_8601
#     // but in URLs they turn into an ugly mess. If we make a few simple URL safe
#     // substitutions and unmake them at the server end all is good, and URLs
#     // become legible approximations to ISO 8601.
#     //
#     // ISO 8601 permits TZ offests with and with the : so +10:00 and +1000 are
#     // fine, but we are also more flexible and permit a space before the TZ offset
#     // and indeed in place of the unsighlty T between date and time in ISO 8601.
#     // So in effect we only care about approximating the standard ;-).
#     //
#     // Of note:
#     //
#     // + is a standard way to encode a space in URL. Though encodeURIComponent
#     // opts for %20.
#     //
#     // we can use + safely and it arrives at the server as a space.
#     //
#     // : is encoded as %3A. It turns out : is not a recommended URL character
#     // and a reserved character, but it does transport fine at least on Chrome
#     // tests.
#     //
#     // Still we can substitue - for it and that is a safe legible char already
#     // in use on the dates and can be decoded back to : by the server.
#     //
#     // The Timezone is introduced by + or -
#     //
#     // - travels unhindered. Is a safe URL character.
#     // + is encoded as %2B, but we can encode it with + which translates to a
#     // space at the server, but known we did this it can decdoe the space back
#     // to +.
#     return encodeURIComponent(datetime).replace(/%20/g, "+").replace(/%3A/g, "-").replace(/%2B/g, "+");
# }
