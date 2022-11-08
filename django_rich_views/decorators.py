'''
Django Rich Views

Decorators

Decorators for use on models that support some of the extensios
'''
# Python imports
import types, inspect


def property_method(f):
    '''
    Used to decorate a function (method) to flag it as a property method.
    A property method is by definition a method that could act as a property,
    that is, can be called with no arguments, in other words all its arguments
    if any, have default values.

    :param f: The function/method to decorate
    '''
    f.is_property_method = True
    return f


def is_property_method(obj):
    '''
    Determines if obj has been decorated with @property_method and that it is
    a method and has defaults for all its parameters. If so it can be considered
    a propery method, namely a method that can be evaluated with no parameters
    (args or kwargs).

    :param obj: The object to test.
    '''
    if isinstance(obj, types.MethodType) and hasattr(obj, "is_property_method"):
        sig = inspect.signature(obj)
        has_default_val = True
        for arg in sig.parameters:
            if sig.parameters[arg].default == inspect.Parameter.empty:
                has_default_val = False
                break;

        return has_default_val
    else:
        return False
