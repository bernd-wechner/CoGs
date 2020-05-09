'''
Logging utilities

To use, just import "log" from here and call log.debug(msg).
'''
# Python imports
from time import time
from copy import copy
import re, logging
from re import RegexFlag as ref # Specifically to avoid a PyDev Error in the IDE.

# Django imports
from django.conf import settings 

log = logging.getLogger("CoGs")

class RelativeFilter(logging.Filter):
    '''
    Abuse of a logging filter to augment the logged record with some realtive timing data.
    
    For a justification of this abuse see: 
        https://docs.python.org/3/howto/logging-cookbook.html#context-info
    
    The benefits are:
    
    1) Attached to logger and not to a handler 
        (solution customizing Formatter are attached to handlers_
        See: https://stackoverflow.com/questions/37900521/subclassing-logging-formatter-changes-default-behavior-of-logging-formatter
        
    2) Is called for every message that the logger processes. 
    '''
    # 
    # TODO: copy debug RE's method of moving newlines around the log line.
    # need to change record.msg.
    time_reference = None
    time_last = None
    
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
    
relative_filter = RelativeFilter()

log.addFilter(relative_filter)
