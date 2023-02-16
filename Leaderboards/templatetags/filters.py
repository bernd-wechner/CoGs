import datetime, re, json as JSON
from django import template

from django.utils.safestring import mark_safe
from django.template.defaultfilters import pluralize

from django_rich_views.util import DjangoObjectJSONEncoder

register = template.Library()


@register.filter
def to_name(value):
    return value.__name__


@register.filter
def value(bound_field, value):
    """
    Takes a bound field and sets the value attribute on that field to the specified value.
    """
    if hasattr(bound_field, "field") and hasattr(bound_field.field, "widget"):
        bound_field.field.widget.attrs['value'] = value
    return bound_field


@register.filter
def index(indexable, i):
    return indexable[i]


@register.filter
def ToArray(value):
    return list(value)


@register.filter
def QuoteValues(value):
    """
    Replaces all strings in a list with a quoted copy.
    Returns a list with the results.
    """

    def quote_values(obj):
        """
        Returns an object as a value in quotes
        """
        if isinstance(obj, list):
            return map(quote_values, obj)
        elif isinstance(obj, str):
            return '"' + obj + '"'
        elif obj is None:
            return "null"
        else:
            return str(obj)

    return "[" + ", ".join([quote_values(obj) for obj in value]) + "]"


@register.filter
def add_attributes(field, css):
    attrs = {}
    definition = css.split(',')

    for d in definition:
        if ':' not in d:
            attrs['class'] = d
        else:
            t, v = d.split(':')
            attrs[t] = v

    return field.as_widget(attrs=attrs)


@register.filter
def verbose(value):
    if hasattr(value, "__verbose_str__"):
        return value.__verbose_str__()
    else:
        return value.__str__()


@register.filter
def checked(value, compare=None):
    if compare is None:
        if value:
            return "checked"
        else:
            return ""
    else:
        if value == compare:
            return "checked"
        else:
            return ""


@register.filter
def fallback(value, fallback):
    if value:
        return value
    else:
        return fallback


@register.filter
def ordinal(n):
    s = ('th', 'st', 'nd', 'rd') + ('th',) * 10
    v = n % 100
    if v > 13:
        return f'{n}{s[v%10]}'
    else:
        return f'{n}{s[v]}'


@register.filter
def day_of_month(dt):
    '''
    Given a datetime object will return an ordinal day of the month in form of
    1st Saturday or 3rd Friday

    :param dt:
    '''
    day = dt.strftime("%A")
    # if day == 'Friday': breakpoint()
    week = ordinal(1 + (dt.day - 1) // 7)
    return f"{week} {day}"


@register.filter
def duration(value, args=None):
    '''
    Format a timedelta object cleanly.

    Taken from: https://stackoverflow.com/a/65293775/4002633

    And improved to include a resolution argument.

    The arguments are provided in a CSV list, for example:

    {{timedelta|duration:"phrase,minutes"}}

    Has two arguments both keywords as follows:

    mode: "machine", "phrase", "phrase_lines", "clock"
    resolution: "microseconds", "milliseconds", "seconds", "minutes", "hours", "days"
    '''
    if not isinstance(value, datetime.timedelta):
        return value

    if args is None:
        return False

    arg_list = [arg.strip() for arg in args.split(',')]

    mode = arg_list[0]  # Required argument
    assert mode in ["machine", "phrase", "phrase_lines", "clock"]

    # An optional argument
    resolutions = ["microseconds", "milliseconds", "seconds", "minutes", "hours", "days"]
    try:
        resolution = arg_list[1]
        assert resolution in resolutions
        resolution = resolutions.index(resolution)
    except IndexError:
        resolution = 0

    remainder = value
    response = ""
    days = 0
    hours = 0
    minutes = 0
    seconds = 0
    milliseconds = 0
    microseconds = 0

    if remainder.days > 0:
        days = remainder.days
        remainder -= datetime.timedelta(days=remainder.days)

    if round(remainder.total_seconds() / 3600) > 1:
        hours = round(remainder.total_seconds() / 3600)
        remainder -= datetime.timedelta(hours=hours)

    if round(remainder.total_seconds() / 60) > 1:
        minutes = int(remainder.total_seconds() / 60)
        remainder -= datetime.timedelta(minutes=minutes)

    if remainder.total_seconds() > 0:
        seconds = int(remainder.total_seconds())
        remainder -= datetime.timedelta(seconds=seconds)

    if remainder.total_seconds() > 0:
        milliseconds = int(remainder.total_seconds() * 1000)
        remainder -= datetime.timedelta(milliseconds=milliseconds)

    if remainder.total_seconds() > 0:
        microseconds = int(remainder.total_seconds() * 1000 * 1000)
        remainder -= datetime.timedelta(microseconds=microseconds)

    if mode == "machine":

        response = "P{days}DT{hours}H{minutes}M{seconds}.{fractionseconds}S".format(
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            fractionseconds=str(milliseconds * 1000 + microseconds).zfill(6),
        )

    elif mode in ("phrase", "phrase_lines"):

        response = []
        if days and resolution <= 5:
            response.append(
                "{days} day{plural_suffix}".format(
                    days=days,
                    plural_suffix=pluralize(days),
                )
            )
        if hours and resolution <= 4:
            response.append(
                "{hours} hour{plural_suffix}".format(
                    hours=hours,
                    plural_suffix=pluralize(hours),
                )
            )
        if minutes and resolution <= 3:
            response.append(
                "{minutes} minute{plural_suffix}".format(
                    minutes=minutes,
                    plural_suffix=pluralize(minutes),
                )
            )
        if seconds and resolution <= 2:
            response.append(
                "{seconds} second{plural_suffix}".format(
                    seconds=seconds,
                    plural_suffix=pluralize(seconds),
                )
            )
        if milliseconds and resolution <= 1:
            response.append(
                "{milliseconds} millisecond{plural_suffix}".format(
                    milliseconds=milliseconds,
                    plural_suffix=pluralize(milliseconds),
                )
            )
        if microseconds and resolution <= 0:
            response.append(
                "{microseconds} microsecond{plural_suffix}".format(
                    microseconds=microseconds,
                    plural_suffix=pluralize(microseconds),
                )
            )

        if mode == "phrase":
            delim = ", "
        elif mode == "phrase_lines":
            delim = "<br>"

        if response:
            # The response is a phrase with spaces between the numbers and units
            # and after the commas, sort of like:
            #     3 days, 6 hours, 34 minutes
            # and if the browser wraps this it should wrap atthe commas and
            # not at the spaces between the numbers and units. So we force the
            # latter to be non breaking spaces, and makr the strig safe so they
            # render (as is needed when the delim is <br> too.
            response = mark_safe(re.sub(r"([^,])(\s)(\S)", r"\1&nbsp;\3", delim.join(response)))
        else:
            response = "zero"

    elif mode == "clock":

        response = []
        if days and resolution <= 5:
            response.append(
                "{days} day{plural_suffix}".format(
                    days=days,
                    plural_suffix=pluralize(days),
                )
            )

        if (hours or minutes or seconds or milliseconds or microseconds) and resolution <= 4:
            time_string = "{hours}".format(hours=str(hours).zfill(2))
            if resolution <= 3:
                time_string += ":{minutes}".format(minutes=str(minutes).zfill(2))

                if (seconds or milliseconds or microseconds) and resolution <= 2:
                    time_string += ":{seconds}".format(seconds=str(seconds).zfill(2))

                    if milliseconds or microseconds and resolution <= 1:
                        time_string += ".{fractionseconds}".format(fractionseconds=str(milliseconds * 1000 + microseconds).zfill(6))
            else:
                time_string += ":00"

            response.append(time_string)

        response = ", ".join(response)

    return response

