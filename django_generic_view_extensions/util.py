'''
Django Generic View Extensions

Utils

A general collection of useful functions used across the package or provided for use outside.  
'''
# Python imports
import re
from re import RegexFlag as ref # Specifically to avoid a PyDev Error in the IDE. 
from titlecase import titlecase

# Django imports
from django.apps import apps
from django.db import connection
from django.db.models.query import QuerySet

# Package imports
from .options import odm


def safetitle(text):
    '''Given an object returns a title case version of its string representation.'''
    return titlecase(text if isinstance(text, str) else str(text))

def app_from_object(o):
    '''Given an object returns the name of the Django app that it's declared in'''
    return type(o).__module__.split('.')[0]    

def model_from_object(o):
    '''Given an object returns the name of the Django model that it is an instance of'''
    return o._meta.model.__name__    

def class_from_string(app_name_or_object, class_name):
    '''
    Given the name of a Django app (or object declared in that Django app) 
    and a string returns the model class with that name.
    '''
    if isinstance(app_name_or_object, str):
        module = apps.get_model(app_name_or_object, class_name)
    else:
        module = apps.get_model(app_from_object(app_name_or_object), class_name)
    return module

def datetime_format_python_to_PHP(python_format_string):
    '''Given a python datetime format string, attempts to convert it to the nearest PHP datetime format string possible.'''
    python2PHP = {"%a": "D", "%a": "D", "%A": "l", "%b": "M", "%B": "F", "%c": "", "%d": "d", "%H": "H", "%I": "h", "%j": "z", "%m": "m", "%M": "i", "%p": "A", "%S": "s", "%U": "", "%w": "w", "%W": "W", "%x": "", "%X": "", "%y": "y", "%Y": "Y", "%Z": "e" }

    php_format_string = python_format_string
    for py, php in python2PHP.items():
        php_format_string = php_format_string.replace(py, php)

    return php_format_string

def getApproximateArialStringWidth(st):
    '''
        An approximation of a strings width in a representative proportional font
        As recorded here:
            https://stackoverflow.com/questions/16007743/roughly-approximate-the-width-of-a-string-of-text-in-python
    '''
    size = 0 # in milinches
    for s in st:
        if s in 'lij|\' ': size += 37
        elif s in '![]fI.,:;/\\t': size += 50
        elif s in '`-(){}r"': size += 60
        elif s in '*^zcsJkvxy': size += 85
        elif s in 'aebdhnopqug#$L+<>=?_~FZT1234567890': size += 95
        elif s in 'BSPEAKVXY&UwNRCHD': size += 112
        elif s in 'QGOMm%W@': size += 135
        else: size += 50
    return size * 6 / 1000.0 # Convert to picas

def isListValue(obj):
    '''Given an object returns True if it is a known list type, False if not.'''
    return (isinstance(obj, list) or 
            isinstance(obj, set) or
            isinstance(obj, tuple) or
            isinstance(obj, dict) or 
            isinstance(obj, QuerySet))

def isListType(typ):
    '''Given a type returns True if it is a known list type, False if not.'''
    return (typ is list or 
            typ is set or
            typ is tuple or
            typ is dict or 
            typ is QuerySet)

def isDictionary(obj):
    '''Given an object returns True if it is a dictionary (key/value pairs), False if not.'''
    return isinstance(obj, dict)

def isPRE(obj):
    '''Returns True if the string is an HTML string wrapped in <PRE></PRE>'''
    return not re.fullmatch(r'^\s*<PRE>.*</PRE>\s*$', obj, ref.IGNORECASE|ref.DOTALL) is None

def containsPRE(obj):
    '''Returns True if the string is an HTML containing <PRE></PRE>'''
    return not re.match(r'<PRE>.*</PRE>', obj, ref.IGNORECASE|ref.DOTALL) is None

def emulatePRE(string, indent=odm.indent):
    '''Returns the same string with <PRE></PRE> replaced by a emulation that will work inside of <P></P>'''
    tag_start = r"<SPAN style='display: block; font-family: monospace; white-space: pre; padding-left:{}ch; margin-top=0;'>".format(indent)
    tag_end = r"</SPAN>"
    string = re.sub(r"<PRE>\s*", tag_start, string, 0, flags=ref.IGNORECASE)
    string = re.sub(r"\s*</PRE>", tag_end, string, 0, flags=ref.IGNORECASE)
    return string

def indentVAL(string, indent=odm.indent):
    '''Returns the same string wrapped in a SPAN that indents it'''
    if indent > 0:
        tag_start = r"<SPAN style='display: block; padding-left:{}ch; margin-top=0; margin-bottom=0; padding-bottom=0;'>".format(indent)
        tag_end = r"</SPAN>"
        return tag_start + string + tag_end
    else:
        return string
    
def get_SQL(query):
    '''
    A workaround for a bug in Django which is reported here (several times):
        https://code.djangoproject.com/ticket/30132
        https://code.djangoproject.com/ticket/25705
        https://code.djangoproject.com/ticket/25092
        https://code.djangoproject.com/ticket/24991
        https://code.djangoproject.com/ticket/17741
        
    that should be documented here:
        https://docs.djangoproject.com/en/2.1/faq/models/#how-can-i-see-the-raw-sql-queries-django-is-running
    but isn't.
    
    The work around was published by Zach Borboa here:
        https://code.djangoproject.com/ticket/17741#comment:4
        
    :param query:
    '''
    sql, params = query.sql_with_params()
    cursor = connection.cursor()
    cursor.execute('EXPLAIN ' + sql, params)
    return cursor.db.ops.last_executed_query(cursor, sql, params).replace("EXPLAIN ", "", 1)    
