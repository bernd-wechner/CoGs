'''
Logging utilities

To use, just import "log" from here and call log.debug(msg).
'''
import re, logging

from re import RegexFlag as ref  # Specifically to avoid a PyDev Error in the IDE.
from time import time

from django.conf import settings

log = logging.getLogger("CoGs")


class RelativeFilter(logging.Filter):
    '''
    Abuse of a logging filter to augment the logged record with some relative timing data.

    For a justification of this abuse see:
        https://docs.python.org/3/howto/logging-cookbook.html#context-info

    The benefits are:

    1) Attached to logger and not to a handler
        (solution customizing Formatter are attached to handlers)
        See: https://stackoverflow.com/questions/37900521/subclassing-logging-formatter-changes-default-behavior-of-logging-formatter

    2) Is called for every message that the logger processes.
    '''
    time_reference = None
    time_last = None

    # A simple RE to suck out prefix and postfix newlines from the message and make them
    # separately available. The formatter can choose to render these or not as it sees fit
    # but a formatter like:
    #     '%(prefix)s other stuff %(message)s% other stuff (postfix)s'
    # will wrap the whole log message in the prefix/postfix pair.
    RE = re.compile(r'^(?P<newlines1>\n*)(?P<message>.*?)(?P<newlines2>\n*)$', ref.DOTALL)

    def filter(self, record):
        now = time()

        if not self.time_reference:
            self.time_reference = now
        if not self.time_last:
            self.time_last = now

        matches = self.RE.match(record.msg).groupdict()

        record.relativeReference = now - self.time_reference
        record.relativeLast = now - self.time_last
        record.prefix = matches['newlines1']
        record.postfix = matches['newlines2']
        record.msg = matches['message']

        self.time_last = now
        return True


class LoggingMiddleware(object):
    '''
    A simple middleware to add which sets the reference time for the RelativeFilter
    '''

    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        now = time()
        relative_filter.time_reference = now
        if settings.DEBUG:
            log.debug(f"Reset logging timer to 0 at {now}.")
        return self.get_response(request)


relative_filter = RelativeFilter()

log.addFilter(relative_filter)
