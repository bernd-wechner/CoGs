'''
Django Generic View Extensions

Widgets

Functions that provide widgets.
'''

# Python imports
from collections import OrderedDict

# Django importso
from django.forms import fields_for_model, DateTimeInput, SelectMultiple
from django.utils.safestring import mark_safe

# Package imports
from .filterset import operation_text
from .forms import classify_widget


class DateTimeSelector(DateTimeInput):
    '''
    A DateTimeInput widget with the jQuery datetimepicker attached

    TODO: A stub I'd like to see implemented. Be nice if the DateTimeInput widget could come in a
          form with a picker attached with no need to do that in the template. May be impractical
          as the template needs to include Jquery (jquery.min.js) and:
              jquery.datetimepicker.full.min.js
              jquery.datetimepicker.css
          and so this widget should have some javascript that checks if these have been loaded I guess,
          and if not issue an alert or something.

          The idea stands to make this a standalone Django widget if we can.
    '''
    pass


class FilterWidget(SelectMultiple):
    '''
    For a given model, respecting the attribute 'filter_options', will provide a widget for selecting filters
    that can be put at top of a ListView for example to provide filter options as per the models request.

    :param model: The model that must provide a 'filter_options' attribute.
                  Being a list of filter criteria for which values can be sought/provided

    :param choices: The request.GET object (a dictionary), that contains the initial values we will use.

    Derive from SelectMultiple simply because it is the closest built-in widget to what we want.
    In that it can return an array of selections, which is what this widget wants to do.
    '''
    model = None
    initial_values = None

    # TODO: Integrate with widget properly. That is:
    # Consider setting these:
    #    self.media._css
    #    self.media._js
    #    self.template_name
    #    self.option_template_name
    #
    # Will help tidy things up and get HTML, CSS and JS out into static files.

    def __init__(self, *args, **kwargs):
        self.model = kwargs.pop('model', None)
        self.initial_values = dict(kwargs.pop('choices', {}))

        if self.model:
            if hasattr(self.model, 'filter_options') and isinstance(self.model.filter_options, list):
                # Save the options as choices for the SelectMultiple
                choices = []
                for option in self.model.filter_options:
                    choices.append((option, None))  # None is  a placeholder. We'll put subwidgets there when rendering

                # Add choices before calling super (SelectMultiple wants choices!)
                kwargs["choices"] = choices

        super().__init__(*args, **kwargs)

    # TODO: Methinks value in render must be ignored, as we can't get the request parameters into it

    def render(self, name, value, attrs=None):
        # Ignore this HTML this returns as we're going to use our own.
        super().render(name, value, attrs)

        # Get the model fields with their widgets
        # TODO: if an option follows a relation we'll need to get the fields/widgest from the related model!
        fields = fields_for_model(self.model)

        # TODO:
        # Only useful if a) not already done on page and with jquery added. So better idea is to supply
        # context items for including jquery, and the datetimepiccker bits and for including this scriplet.
        # i.e. not here.
        script = ""  # '<script>$(function(){$(".DateTimeField").datetimepicker({"format": datetime_format,"step" : 15});});</script>'

        for index, (option, _) in enumerate(self.choices):
            option = self.choices[index][0]
            parts = option.split('__')
            if parts[0] in fields:
                fieldname = parts[0]
                operation = parts[1] if len(parts) > 1 else "exact"

                if operation in operation_text:
                    operation = operation_text[operation]

                if fieldname in fields:
                    classify_widget(fields[fieldname])
                    label = fields[fieldname].label
                    widget = fields[fieldname].widget
                    widget.attrs["id"] = "filter_field{}".format(index)
                    value = self.initial_values.pop(fieldname, 'None')
                else:
                    label = fieldname
                    widget = None
                    value = None

                if widget:
                    self.choices[index] = (option, "{} {} {}".format(label, operation, widget.render(option, value, attrs=attrs)))

        return mark_safe("<div id={}>".format(name) + " and ".join([choice[1] for choice in self.choices]) + "</div>" + script)

    def __str__(self):
        return self.render("{}_filtering_widget".format(self.model._meta.model_name), "")


class OrderingWidget(SelectMultiple):
    '''
    For a given model, respecting the attribute 'order_options', will provide a widget for specifying ordering
    of the objects, that can be put at top of a ListView for example to provide ordering options as per the models
    request.

    :param model: The model that must provide an 'order_options' attribute.
                  Being a list of filter criteria for which values can be sought/provided

    :param choices: The ordering specified in request.GET if any.

    Internally we support a ~ prefix for no direction, i.e. not sorting on given field, the default
    position for those specified in model.ordering.

    Derive from SelectMultiple simply because it is the closest built-in widget to what we want.
    In that it can return an array of selections, which is what this widget wants to do.
    '''
    model = None
    initial_values = None

    # Character codes for use with &#nnnn; in HTML
    up_arrow = 9650
    down_arrow = 9660
    no_arrow = 9644

    def __init__(self, *args, **kwargs):
        self.model = kwargs.pop('model', None)

        # If an ordering is requested via the URL, it comes in as the choices kwarg.
        ordering = kwargs.pop('choices', None)

        # If we got an ordering in the URL save it, else if the model has a default ordering use that
        if ordering:
            self.initial_values = ordering.split(',')
        elif self.model and hasattr(self.model._meta, 'ordering'):
            self.initial_values = self.model._meta.ordering

        # Save the options as 'choices' (we'll use this in rendering, and provide it for compatibility with SelectMultiple)
        if self.model:
            # Get the model fields with their widgets
            # TODO: if an option follows a relation we'll need to get the fields/widgets from the related model!
            fields = {f.name: f for f in self.model._meta.get_fields()}

            # The choices are essentially as defined by the models 'order_option' but reflecting self.initial_values.
            #
            # if initial_values includes fields not in the order_options, give initial_values priority (add them)
            # if initial_values does not include all the order_options, that is fine.
            #
            # we'll use a choice_dir to help with this, but ultimately build choices as a list of tuples as SelectMultiple prefers.
            requested = OrderedDict()
            if self.initial_values:
                for option in self.initial_values:
                    if option.startswith("-"):
                        fieldname = option[1:]
                    else:
                        fieldname = option

                    requested[fieldname] = option

            # Now we want to do same for order_options
            defaults = OrderedDict()
            if hasattr(self.model, 'order_options') and isinstance(self.model.order_options, list):
                for option in self.model.order_options:
                    # Supported prefixes are ignored:
                    #     - descending
                    #     + ascending (the default, assumed without a +)
                    #     ~ no sort
                    if option[0] in ["-", "+", "~"]:
                        fieldname = option[1:]
                    else:
                        fieldname = option

                    defaults[fieldname] = option

            # We now have nice ordered dicts of requested and defaults so can walk requested,
            # removing from defaults and then add the remaining defaults.
            choices = []
            if len(requested) > 0:
                for fieldname, option in requested.items():
                    choices.append((option, fields[fieldname].verbose_name))
                    if fieldname in defaults:
                        del defaults[fieldname]

            if len(defaults) > 0:
                for fieldname, option in defaults.items():
                    choices.append(("~" + fieldname, fields[fieldname].verbose_name))  # By default, disabled with ~ prefix

            kwargs["choices"] = choices

        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None):
        self.name = name

        # Ignore this HTML this returns as we're going to use our own.
        super().render(name, value, attrs)

        # TODO: Initial values may not reference all the possible choices. These can simply be at the end BUT
        #       The widget should support nodir, so up arrow, down arrow and a nodir symbol, and cycle them
        #       But! Should only offer nodir if all items below this one are nodir!
        #       That is, some Javascrip smarts to add there.#

        widgets = []
        for index, (option, label) in enumerate(self.choices):
            # option = self.choices[index][0]
            if option.startswith("~"):
                arrow = "&#{};".format(self.no_arrow)
                choice_name = option[1:]
            elif option.startswith("-"):
                arrow = "&#{};".format(self.down_arrow)
                choice_name = option[1:]
            else:
                arrow = "&#{};".format(self.up_arrow)
                choice_name = option[1:] if option.startswith("-") else option

            widget = ("<div id='ordering_widget_item_{name}' class='ordering_widget_item'>"
                      "<span id='ordering_field{index}' name='{name}'>{field}</span> "
                      "<span id='ordering_dir{index}' onclick='toggle_ordering_dir(this);'>{arrow}</span>"
                      "</div>").format(index=index, name=choice_name, field=label, arrow=arrow)

            widgets.append(widget)

        header = f"<div id='{name}' class='ordering_widget'><script>{self.script}</script>"
        footer = "</div>"

        return mark_safe(header + "\n".join(widgets) + footer)

    def __str__(self):
        return self.render("{}_ordering_widget".format(self.model._meta.model_name), "")

    @property
    def script(self):
        return f"""
        $(function() {{
            $('#{self.name}').sortable();
            $('#{self.name}').disableSelection();
        }});

        function toggle_ordering_dir(btn) {{
            // TODO: If a lower option has a dir, do not include nodir in cycle.
            // TODO: If a higher option has nodir, this one cannot leave nodir.
            //       To wit user has to move up to free up options.
            // TODO: If moving a nodir up above the nodir block switch to up
            if (btn.innerHTML == String.fromCharCode({self.up_arrow}))
                btn.innerHTML = '&#{self.down_arrow};';
            else if (btn.innerHTML == String.fromCharCode({self.down_arrow}))
                btn.innerHTML = '&#{self.no_arrow};';
            else if (btn.innerHTML == String.fromCharCode({self.no_arrow}))
                btn.innerHTML = '&#{self.up_arrow};';
            else
                btn.innerHTML = '&#{self.up_arrow};';
        }}

        function ordering_url_opts() {{
           const widgetid = "session_ordering_widget";
           let fields = [], dirs = [], opts = [];

            function CollectOrderingField(index, value) {{
                fields.push($(value).attr('name'));
            }}

            function CollectOrderingDir(index, value) {{
                dirs.push($(value).text());
            }}

            function get_ordering_dir(text) {{
                if (text == String.fromCharCode(9650)) return "";
                else if (text == String.fromCharCode(9660)) return "-";
                else if (text == String.fromCharCode(9644)) return null;
                else return null;
            }}

            $("#"+widgetid).find("span[id^='ordering_field']").each(CollectOrderingField);
            $("#"+widgetid).find("span[id^='ordering_dir']").each(CollectOrderingDir);

            for (let i = 0; i < fields.length; i++) {{
                const pfx = get_ordering_dir(dirs[i]);
                if (pfx != null) opts.push(pfx+fields[i]);
            }}

           return opts.length > 0 ? ["ordering=" + opts.join(",")] : [];
        }}
    """
