'''
Django Generic View Extensions

HTML generators

Specifically support functions that generate HTML, primarily for display on DetailViews and ListViews,
but also supporting numerous options that can be passed in through a request (via .options).
'''
# Python imports
import html
import re
import six
from re import RegexFlag as ref # Specifically to avoid a PyDev Error in the IDE.
from datetime import datetime 

# Django imports
from django.conf import settings
from django.urls import reverse
from django.utils.html import conditional_escape
from django.utils.encoding import force_text
from django.utils.safestring import mark_safe

# Package imports
from . import FIELD_LINK_CLASS, NONE 
from .util import isListValue, isDictionary, isPRE, emulatePRE, indentVAL, getApproximateArialStringWidth
from .datetime import time_str
from .options import list_display_format, object_display_format, object_display_modes, flt, osf, odm, odf, lmf
from .filterset import format_filterset
from django_generic_view_extensions.debug import print_debug


def fmt_str(obj, safe=False):
    '''
    A simple enhancement of str() which formats list values a little more nicely IMO.
    
    TODO: Consider trickling an odm.char_limit down to this level so that fmt_str can
         wrap to new lines as per the deprecated hstr. The notable test case is to see 
         the Session Trueskill Impacts rendered in a nice way,. Issue is that it's not 
         catered for well yet, where we have odm.list_values == as_ul and the actual 
         value is a list (so a list of lists as the value). We could inherit 
         odm.list_value and trickle down supporting tiers. But this will take a little
         work to implement and is not trivial, given this function is reached currenntly
         by:
            collection_rich_object_fields - which has the view and view.format and hence knows what to do   
            odm_str - which it uses for each value to get string that respect the OSF but it no longer knows the ODM
            fmt_str - here, which odm_str calls in place of str()
            
        That is also not ideal. The problem is odm_str is failing to differentiate between models
        and standard python data types. Models it needs to respect ODF for, but standard data types
        not, in fact we are thinking it should respect ODM (the char_lim to wrap). 
        
    '''
    csv_delim = ', '
    nl_delim = '\n'
 
    containsdelim = False            
    multilineval = False

    if isListValue(obj):
        lines = []
        multilineval = False

        if isinstance(obj, dict):
            braces = ['{', '}']
        else:
            braces = ['[', ']']
        
        for item in obj:
            if isinstance(obj, dict):
                valstr = fmt_str(obj[item])
                lines.append("{}: {}".format(item, valstr))
            else:
                valstr = fmt_str(item)
                lines.append(valstr)
                 
            if re.match(csv_delim, valstr, ref.IGNORECASE):
                containsdelim = True            
            if re.match(r'<br>', valstr, ref.IGNORECASE):
                multilineval = True
         
        if containsdelim or multilineval:
            text = braces[0] + nl_delim.join(lines) + braces[1]
        else:
            text = braces[0] + csv_delim.join(lines) + braces[1]
    elif isinstance(obj, datetime):
        text = force_text(time_str(obj))
    else:
        text = force_text(str(obj))
        
    # Not object should land here with HTML embedded really, bar PRE strings. So
    # mark PRE strings as safe, and escape the rest. 
    if safe or isPRE(text):
        return mark_safe(text)    
    else:            
        return html.escape(text)    

def odm_str(obj, fmt, safe=False):
    '''
    Return an object's representative string respecting the ODM (sum_format and link) and privacy configurations. 

    FIXME:  This should take one path for Django models and another for standard data types!
    Models have rich and verbose and normal str methods. Standard data types have only str but we want to 
    replace that with fmt_str to make them render more nicely on screen (notably rendering OrderedDict as 
    Dict, respecting odm.char_lim and finding a way to wrap long items. The problem is a 
    field may be a list which works well, but it may be a list of lists, and a list of list of lists ...
    and that is not working elegantly. 
    
    :param object:     The object to convert to string
    :param fmt:        The format to use, cane be an object of type: object_display_modes or of type list_display_format
                       depends on who's calling us and what they prefer to offer.
                       
    Depends on:
        fmt.link (which both object_display_modes and list_display_format provide)
        an OSF (Object Summary Format) which it pilfers from fmt.sum_format or fmt.elements based on the provided fmt 
    '''    
    odm  = object_display_modes()
    if type(fmt) == object_display_modes:
        OSF = fmt.sum_format
        OLV = fmt.list_values
        CharLim = fmt.char_limit
        LT = fmt.link
    elif type(fmt) == list_display_format:
        OSF = fmt.elements
        OLV = None
        CharLim = None
        LT = fmt.link

    # Rich and Detail views on an object are responsible for their own linking.
    # They should do that via field_render().
    # Verbose and Brief views don't so we apply a link wrapper if requested.   
    Awrapper = "{}"
    if not (OSF == osf.detail or OSF == osf.rich):
        if fmt.link == flt.internal and hasattr(obj, "link_internal") and obj.link_internal:
            Awrapper = "<A href='{}' class='{}'>".format(obj.link_internal, FIELD_LINK_CLASS) + "{}</A>"    
        elif fmt.link == flt.external and hasattr(obj, "link_external") and obj.link_external:
            Awrapper = "<A href='{}' class='{}'>".format(obj.link_external, FIELD_LINK_CLASS) + "{}</A>"    
    
    # Verbose and Brief should never contain HTML and so should be escaped.
    # Rich and Detail might contain HTML so we expect them do their own escaping
    if OSF == osf.detail:
        if callable(getattr(obj, '__detail_str__', None)):
            strobj = obj.__detail_str__(LT)
        elif callable(getattr(obj, '__rich_str__', None)):
            strobj = obj.__rich_str__(LT)
        elif callable(getattr(obj, '__verbose_str__', None)):
            strobj = html.escape(obj.__verbose_str__())
        else: 
            strobj = fmt_str(obj, safe)
    elif OSF == osf.rich:
        if callable(getattr(obj, '__rich_str__', None)):
            strobj = obj.__rich_str__(LT)
        elif callable(getattr(obj, '__verbose_str__', None)):
            strobj = html.escape(obj.__verbose_str__())
        else: 
            strobj = fmt_str(obj)
    elif OSF & osf.verbose:
        if callable(getattr(obj, '__verbose_str__', None)):
            strobj = html.escape(obj.__verbose_str__())
        else: 
            strobj = fmt_str(obj, safe)
    else:        
        if OLV == odm.as_table:
            Wrap = ("<table>", "</table>")
            wrap = ("<tr><td>", "</td></tr>")
        elif OLV == odm.as_ul:
            Wrap = ("<ul>", "</ul>")
            wrap = ("<li>", "</li>")
        elif OLV == odm.as_p:
            Wrap = ("", "")
            wrap = ("<p>", "</p>")
        elif OLV == odm.as_br:
            Wrap = ("", "")
            wrap = ("", "<br>")
        else:
            Wrap = None
            wrap = None
        
        strobj = fmt_str(obj, safe)
        
        if Wrap and isListValue(obj) and len(strobj) > CharLim:
            if isDictionary(obj):
                strobj = Wrap[0] + wrap[0] + f"{wrap[1]}{wrap[0]}".join([f"{fmt_str(k, safe)}: {fmt_str(v, safe)}" for k, v in obj.items()]) + wrap[1] + Wrap[1]
            else:
                strobj = Wrap[0] + wrap[0] + f"{wrap[1]}{wrap[0]}".join([fmt_str(o, safe) for o in obj]) + wrap[1] + Wrap[1]
    
    return Awrapper.format(strobj) 

#======================================================================================
# Function to provide rendering methods compatible Django Generic Forms (and then some) 
#======================================================================================

def list_html_output(self, LDF=None):
    ''' Helper function for outputting HTML lists of objects (intended for ListViews). 
    
        Used by as_table(), as_ul(), as_p(), as_br().
    
        an object display mode (ODM) can be specified to override the one in self.format if desired 
        as this is what as_table etc do (providing compatible entry points with the Django Generic Forms).
        
        self is an instance of ListViewExtended (or any view that wants HTML rendering of a list of objects).
        
        Relies on:
            odm_str:  which displays an object respecting the object_summary_format specified in self.format
                      which in turn should be populated by get_list_display_format() which parses the request 
                      for options.
                      
            self.queryset:    Which must be initialised by the calling form, defining the list of objects to format in HTML
            
            self.format:      Which should be of type list_display_format 
    '''
    
    if LDF is None:
        LDF = self.format.complete
        
    LMF = self.format.menus
    LIF = self.format.index
    LKF = self.format.key

    # Define the standard HTML strings for supported formats    
    if LDF == odm.as_table:
        normal_row = "<tr>{menu:s}{index:s}{key:s}<td class='list_item'>{value:s}</td></tr>"
    elif LDF == odm.as_ul:
        normal_row = "<li class='list_item'>{menu:s}{index:s}{key:s}{value:s}</li>"
    elif LDF == odm.as_p:
        normal_row = "<p class='list_item'>{menu:s}{index:s}{key:s}{value:s}</p>"
    elif LDF == odm.as_br:
        normal_row = '{menu:s}{index:s}{key:s}{value:s}<br>'
    else:
        raise ValueError("Internal Error: format must always contain one of the object layout modes.")                

    # Menu support is for three menu items against each list item
    #    View for a DetailView
    #    Edit for an UpdateView
    #    Delete for a DeleteView

    if LMF == lmf.none:
        menu = ""
    elif LMF == lmf.text:
        text = "<span class='list_menu_text'>[<a href={} class='list_menu_link'>{}</a>] </span>"
        menu = text.format("'{view:s}'", 'view')
        if self.request.user.is_authenticated:
            menu += text.format("'{edit:s}'", 'edit') + text.format("'{delete:s}'", 'delete')
        if LDF == odm.as_table:
            menu = "<td class='list_menu_cell'>{}</td>".format(menu)                    
    elif LMF == lmf.buttons:
        button = "<input type='button' onclick='location.href={};' value='{}' class='list_menu_button' /> "
        menu = button.format('"{view:s}"', 'view')
        if self.request.user.is_authenticated:
            menu += button.format('"{edit:s}"', 'edit') + button.format('"{delete:s}"', 'delete')
        if LDF == odm.as_table:
            menu = "<td class='list_menu_cell'>{}</td>".format(menu)                    

    # Index support is for one index running down page
    if LIF:
        index = "<span class='list_index_text'>{index}</span>"
        if LDF == odm.as_table:
            index = "<td class='list_index_cell'>{}</td>".format(index)                    
    else:
        index = ""

    # Key support is for one index running down page
    if LKF:
        key = "<span class='list_key_text'>{key}</span>"
        if LDF == odm.as_table:
            key = "<td class='list_key_cell'>{}</td>".format(key)
    else:
        key = ""

    # Collect output lines in a list
    output = []

    # This evaluates the queryset
    i = 1
    for o in self.queryset:
        url_view = reverse('view', kwargs={'model': self.kwargs['model'], 'pk': o.pk})
        url_edit = reverse('edit', kwargs={'model': self.kwargs['model'], 'pk': o.pk})
        url_delete = reverse('delete', kwargs={'model': self.kwargs['model'], 'pk': o.pk})
        
        # The view url is special. It should conserve filters and ordering so that the 
        # detail view browses (prior/next links) within the ordered filtered view.
        if getattr(self, 'filterset', False):
            filters = format_filterset(self.filterset, as_text=False)
            url_view += "?" + "&".join(filters)                
        
        if self.request.user.is_authenticated:
            html_menu = menu.format(view=url_view, edit=url_edit, delete=url_delete)
        else:        
            html_menu = menu.format(view=url_view)
            
        html_index = index.format(index=i)
        i += 1

        html_key = key.format(key=o.pk)
        
        html_value = six.text_type(odm_str(o, self.format))
        row = normal_row.format(menu=html_menu, index=html_index, key=html_key, value=html_value)
        output.append(row)

    return mark_safe('\n'.join(output))

def object_html_output(self, ODM=None):
    ''' Helper function for outputting HTML formatted objects (intended for DetailViews). 
    
        Used by as_table(), as_ul(), as_p(), as_br().
    
        an object display mode (ODM) can be specified to override the one in self.format if desired 
        as this is what as_table etc do (providing compatible entry points with the Django Generic Forms).
        
        self is an instance of DetailViewExtended or DeleteViewExtended (or any view that wants HTML 
        rendering of an object.  
        
        Relies on:
             self.fields
             self.fields_bucketed 
             
        which are attributes created by collect_rich_object_fields which should have run earlier
        when the view's get_object() method was called. When the object is delivered the view is 
        updated with these (and other) attributes.
        
        Notably, each field in self.fields and variants carries a "value" attribvute which is what 
        we try to render in HTML here. We rely on privacy constraints having already been applied
        by collect_rich_object_fields and that values affected by provacy are suitably masked 
        (overwritten). 
    '''
    #TODO: This should really support CSS classes like BaseForm._html_output, so that a class can be specified
    
    ODF = self.format
    if not ODM is None:
        ODF.mode.object = ODM

    # Define the standard HTML strings for supported formats    
    if ODF.mode.object == odm.as_table:
        header_row = "<tr><th valign='top'>{header:s} {line1:s}</th><td>{line2:s}</td></tr>"
        normal_row = "<tr><th valign='top'>{label:s}</th><td>{value:s}{help_text:s}</td></tr>"
        help_text_html = '<br /><span class="helptext">%s</span>'
    elif ODF.mode.object == odm.as_ul:
        header_row = "<li><b>{header:s}</b> {line1:s}</li>"        
        normal_row = "<li><b>{label:s}:</b> {value:s}{help_text:s}</li>"
        help_text_html = ' <span class="helptext">%s</span>'
    elif ODF.mode.object == odm.as_p:
        header_row = "<p><b>{header:s}</b> {line1:s}</p>"        
        normal_row = "<p><b>{label:s}:</b> {value:s}{help_text:s}</p>"
        help_text_html = ' <span class="helptext">%s</span>'
    elif ODF.mode.object == odm.as_br:
        header_row = "<b>{header:s}</b> {line1:s}<br>"        
        normal_row = '<b>{label:s}:</b> {value:s}{help_text:s}<br>'
        help_text_html = ' <span class="helptext">%s</span>'
    else:
        raise ValueError("Internal Error: format must always contain one of the object layout modes.")                

    # Collect output lines in a list
    output = []

    for bucket in self.fields_bucketed:
        # Define a label for this bucket
        bucket_label = ('Internal fields' if bucket == odf.internal
            else 'Related fields' if bucket == odf.related
            else 'Properties' if bucket == odf.properties
            else 'Methods' if bucket == odf.methods
            else 'Summaries' if bucket == odf.summaries
            else 'Standard fields' if bucket == odf.model and ODF.flags & odf.header
            else None if bucket == odf.model
            else 'Unknown ... [internal error]')
        
        # Output a separator for this bucket if needed
        # Will depend on the object display mode
        if bucket_label and (ODF.flags & odf.separated) and self.fields_bucketed[bucket]:
            label = bucket_label if ODF.flags & odf.header else ""
            
            if ODF.flags & odf.line:
                if ODF.mode.object == odm.as_table:
                    line = "<hr style='display:inline-block; width:60%;' />"
                else:
                    label_width = int(round(getApproximateArialStringWidth(bucket_label) / getApproximateArialStringWidth('M'))) 
                    line = "&mdash;"*(ODF.mode.line_width - label_width - 1)
            
            if ODF.mode.object == odm.as_table:
                label_format = '<span style="float:left;">{}</span>'
            else:
                label_format = '{}'
                
            row = header_row.format(header=label_format.format(label), line1=line, line2=line)

            if ODF.mode.object == odm.as_ul:
                row_format = '{}<ul>'  
            elif ODF.mode.object == odm.as_br:
                row_format = '{}</p><p style="padding-left:'+str(ODF.mode.indent)+'ch">'  
            else:
                row_format = '{}'
                
            output.append(row_format.format(row))

        # Output a the fields in this bucket
        for name in self.fields_bucketed[bucket]:
            field = self.fields_bucketed[bucket][name]
            value = field.value 
            
            if hasattr(field, 'label') and field.label:
                label = conditional_escape(force_text(field.label))
            else:
                label = ''
                
            # self.format specifies how we'll render the field, i.e. build our row.
            #
            # normal_row has been specified above in accord with the as_ format specified.
            #
            # The object display mode defines where the value lands.
            # The long list display mode defines how a list value is rendered in that spot
            # short lists are rendered as CSV values in situ
            br_fix = False
            
            if field.is_list:
                proposed_value = value if value == NONE else ", ".join(value) 
                    
                is_short = (len(proposed_value) <= ODF.mode.char_limit) and not ("\n" in proposed_value)
                 
                if is_short:
                    value = proposed_value
                else:
                    # as_br is special as many fields are in one P with BRs between them. This P cannot contain
                    # block elements so there is only one sensible rendering (which is to conserve the intended
                    # paragraph and just put long list values one one BR terminated line each, indenting with 
                    # a SPAN that is permitted in a P. 
                    if ODF.mode.object == odm.as_br:
                        value = indentVAL("<br>".join(value), ODF.mode.indent)
                        br_fix = ODF.mode.object == odm.as_br
                    else:
                        if ODF.mode.list_values == odm.as_table:
                            strindent = ''
                            if ODF.mode.object == odm.as_p and ODF.mode.indent > 0:
                                strindent = " style='padding-left: {}ch'".format(ODF.mode.indent)
                            value = "<table{}><tr><td>".format(strindent) + "</td></tr><tr><td>".join(value) + "</td></tr></table>"
                        elif ODF.mode.list_values == odm.as_ul:
                            strindent = ''
                            if ODF.mode.object == odm.as_p and ODF.mode.indent > 0:
                                strindent = " style='padding-left: {}ch'".format(ODF.mode.indent)
                            value = "<ul{}><li>".format(strindent) + "</li><li>".join(value) + "</li></ul>"
                        elif ODF.mode.list_values == odm.as_p:
                            strindent = ''
                            if ODF.mode.object == odm.as_p and ODF.mode.indent > 0:
                                strindent = " style='padding-left: {}ch'".format(ODF.mode.indent)
                            value = "<p{}>".format(strindent) + "</p><p{}>".format(strindent).join(value) + "</p>"
                        elif ODF.mode.list_values == odm.as_br:
                            strindent = ''
                            if ODF.mode.object == odm.as_p and ODF.mode.indent > 0:
                                strindent = " style='padding-left: {}ch'".format(ODF.mode.indent)
                            value = "<p{}>".format(strindent) + "<br>".join(value) + "</p>"
                        else:
                            raise ValueError("Internal Error: self.format must always contain one of the list layouts.")
            else:
                proposed_value = value
                is_short = (len(proposed_value) <= ODF.mode.char_limit) and not ("\n" in proposed_value)
                
                if is_short:
                    value = proposed_value
                else:
                    indent = ODF.mode.indent if ODF.mode.object != odm.as_table else 0
                    if isPRE(value):
                        value = emulatePRE(value, indent)
                        br_fix = ODF.mode.object == odm.as_br
                    else:
                        value = indentVAL(value, indent)

            if hasattr(field, 'help_text') and field.help_text:
                help_text = help_text_html % force_text(field.help_text)
            else:
                help_text = ''

            # Indent the label only for tables with headed separators.
            # The other object display modes render best without an indent on the label. 
            if ODF.mode.object == odm.as_table and ODF.flags & odf.separated and ODF.flags & odf.header: 
                label_format = indentVAL("{}", ODF.mode.indent) 
            else:
                label_format = '{}' 

            html_label = label_format.format(force_text(label))
            html_value = six.text_type(value)
            html_help = help_text

            if settings.DEBUG:
                if field.is_list:
                    html_label = "<span style='color:red;'>" + html_label + "</span>"
                if is_short:
                    html_value = "<span style='color:red;'>" + html_value + "</span>"
                         
            row = normal_row.format(label=html_label, value=html_value, help_text=html_help)
            
            # FIXME: This works. But we should consider a cleaner way to put the br inside 
            # the span that goes round the whole list in as_br mode. The fix needs a consideration
            # of normal_row and indentVAL() the later wrapping in a SPAN the former terminating with
            # BR at present. And in that order an unwanted blank line appears. If we swap them and
            # bring the BR inside of the SPAN the render is cleaner.
            if br_fix:
                row = re.sub(r"</span><br>$",r"<br></span>",row,0,ref.IGNORECASE)

            # Finally, indent the whole "field: value" row if needed
            if ODF.mode.object == odm.as_p and ODF.flags & odf.separated and ODF.flags & odf.header: 
                row_format = indentVAL("{}", ODF.mode.indent)
            else:
                row_format = '{}' 

            output.append(row_format.format(row))

        # End the UL sublist (the one with label: value pairs on it, being sub to the header/separator list) if needed 
        if bucket_label and (ODF.flags & odf.separated) and self.fields_bucketed[bucket]:
            if ODF.mode.object == odm.as_ul:
                output.append('</ul>')
            elif ODF.mode.object == odm.as_br:
                output.append('</p><p>')

    return mark_safe('\n'.join(output))

#======================================================================================
# Function to provide rendering methods compatible Django Generic Forms (and then some) 
#======================================================================================

def object_as_table(self):
    '''Returns this object rendered as HTML <tr>s -- excluding the <table></table> - for compatibility with Django generic forms'''
    return self._html_output(odm.as_table)

def object_as_ul(self):
    '''Returns this object rendered as HTML <li>s -- excluding the <ul></ul> - for compatibility with Django generic forms'''
    return self._html_output(odm.as_ul)

def object_as_p(self):
    '''Returns this object rendered as HTML <p>s - for compatibility with Django generic forms'''
    return self._html_output(odm.as_p)

def object_as_br(self):
    '''Returns this object rendered as an HTML <p> with <br>s between fields - new to these extensions, not in the standard Django generic forms'''
    return self._html_output(odm.as_br)

def object_as_html(self):
    ''' Returns this object (self.object) rendered as per the requested object display format.
        
        Essentially selecting one of as_table, as_ul, as_p or as_brbased on the request.
        
        The other as_ methods provide compatibility with Djangos generic forms more 
        or less and they don't provide the HTML wrappers, this method, our AJAX entry
        point, does so that a template can just spew out the HTML without having to 
        worry about such a wrapper. That is, a template would normally contain:
        
        <table>
            {{ view.as_table }}
        </table>
        
        but could skip the wrapper and just use:
        
        {{ view.as_html }}
        
        which lands here and includes it. Though if using AJAX would want to wrap it 
        in an IDed div so that javascript can fetch the formatted object and update 
        the div. So just:
        
        <div id="data"></div>
        
        would do and Javascript can fetch view.as_html and set the contents of the 
        div without a page reload (thus permitting format changes in situ with Javascript)
    '''
    # The ListView and DetailView store format differently.
    if type(self.format) == object_display_format:
        fmt = self.format.mode.object
    elif type(self.format) == list_display_format:
        fmt = self.format.complete
    
    if fmt == odm.as_table:
        return mark_safe("<table>" + object_as_table(self) + "</table>")
    elif fmt == odm.as_ul:
        return mark_safe("<ul>" + object_as_ul(self) + "</ul>")
    elif fmt == odm.as_p:
        return object_as_p(self)
    elif fmt == odm.as_br:
        return mark_safe("<p>" + object_as_br(self) + "</p>")
    else:
        raise ValueError("Internal Error: self.format must always contain one of the HTML layouts.")                
