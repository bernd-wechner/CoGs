'''
Created on 13Jan.,2017

Django Generic View Extensions

@author: Bernd Wechner
@status: Alpha - works and is in use on a dedicated project. Is not complete, and needs testing for generalities.

Django provides some excellent generic class based views:

    https://docs.djangoproject.com/en/1.10/topics/class-based-views/generic-display/
    
They are excellent for getting a site up and running really quickly from little more than a model specification. 

The admin site of course provides a rather excellent and complete version of generic database administration:

    https://docs.djangoproject.com/en/1.10/ref/contrib/admin/
     
But as at Django 1.10 the built in generic class based views fall somewhat short of complete.

This module provides extensions to the generic class based views, with the specific aim of adding more context
to use in templates and including the forms and field values for related objects.

In summary, the built generic class based views we are extending are from django.views.generic: 

ListView - for listing the objects in a model
DetailView - for examining the details of a specific object (model instance) 
CreateView - for creating new objects
UpdateView - for editing existing objects
DeleteView - for deleting existing objects

The main use of this module is to offer: 

ListViewExtended - for listing the objects in a model
DetailViewExtended - for examining the details of a specific object (model instance) 
CreateViewExtended - for creating new objects
UpdateViewExtended - for editing existing objects
DeleteViewExtended - for deleting existing objects

which can be used in place of the built-ins. They derive directly from them adding some features as follows:

Enrich the context provided to templates. Specifically these elements:

model - the model class (available as view.model as well, but what the heck.
model_name - because it's not easy to reference view.model.__name__ in a template alas.
model_name_plural - because it's handier than referencing view.model._meta.verbose_name_plural
operation - the value of "operation" passed from urlconf (should be "list", "view", "add", "edit" or "delete")
title - a convenient title constructed from the above that can be used in a template 
default_datetime_input_format - the default Django datetime input format as a PHP datetime format string. Very useful for configuring a datetime picker.

DetailViewExtended and DeleteViewExtended 

Django provides a really sweet set of context elements for forms:

form.as_table
form.as_ul
form.as_p

with which you can rapidly render the basic form for a model without further ado in three formats. 

Oddly it does not provide these for detail views. So here we do. Direct reproduction of the form
version only instead of containing HTML form elements it just contains the field contents rendered in
a nice way (using the __str__ representation of Models). These are available as:

view.as_table
view.as_ul
view.as_p

in the context they deliver. 

These views take an optional keyword argument ToManyMode to specify how lists should be rendered for 
fields that are relations to many. The many remote objects have their own __str__ representations which 
can be rich of course and so some control over how lists of these are presented is offered. ToManyMode
can take any of the 3 formats 'table', 'ul', 'p' as per the view itself, that is display the multiple 
values as a table as a bulleted list or as a set of paragraphs. It can be any other string as well in
which case that string is used as a delimiter between values. It can contain  HTML of course, for 
example '<BR>'.  

CreateViewExtended and UpdateViewExtended 

Easily the biggest extension is to include related form information in the context so that
it's easy to create a rich forms that include elements from numerous related forms. 

This is delivered in a context element 'related_forms' which is a rich representation of all the 
related forms you request in a given model. The request is made by including an atttribute 'add_related'
in the model which is a list of field names that identify a relation. This is recursive, that is, 
the related models may also contain an 'add_related' attribute. You can probably crash Django by
creating a closed loop of references if you like - not advised.

The related_forms element contains one entry per related model, being a related form for that model.

For example to illustrate two tiers, if you have a model Family and a family can have Members and 
Pets and when editing family you want access on your form to the fields of Family, Member and Pet.
But let's say Members and Pets can have Issues you're trying to track and you want rich forms that 
let a user enter a family, it smembers pets and issues all at once. 

Well CreateViewExtended and UpdateViewExtended make that easy for you, providing all the form 
elements in the context if you ask for them and also saving the submitted data properly for 
you!

Here's what it might look like:

class Family(models.Model):
    name = models.CharField('Name of the Family', max_length=80)
    add_related = ['members','pets'] # could also read ['Member.family', 'Pet.family']

class Member(models.Model):
    name = models.CharField('Name of the Member', max_length=80)
    family = models.ForeignKey('Family', related_name='members')
    issues = models.ManyToManyField('Issue', related_name='suffering_members')
    add_related = ['issues']

class Pet(models.Model):
    name = models.CharField('Name of the Pet', max_length=80)
    family = models.ForeignKey('Family', related_name='pets')
    issues = models.ManyToManyField('Issue', related_name='suffering_pets')
    add_related = ['issues']

class Issue(models.Model):
    description = models.CharField('Issue', max_length=200)

well mean the context that CreateViewExtended and UpdateViewExtended provide you with
the following possible references:

related_forms.Member.name
related_forms.Member.related_forms.Issue.description
    related_forms.Pet.name
related_forms.Pet.related_forms.Issue.description

as the form widgets for those fields respectively.

To build rich forms you need more though so added to the related_form for each model 
are two extra elements management_form and field_data.

management_form is the standard management form Django requires (and you should understand
these to build rich forms). In summary though they are simply little HTML snippets that 
contain four hidden input fields named TOTAL_FORMS, INITIAL_FORMS, MIN_NUM_FORMS, MAX_NUM_FORMS.
Documentation on exactly how these work is meager in the django world, but they are used
by the Django code when submitted form data is processed, and to that end in rich forms you
will need (in Javascript perhaps) to update TOTAL_FORMS in particular to tell Django how many
forms are being submitted. This is a little more complicated than we can cover here, but
note that Django uses the word FORM not in the sense of an HTML FORM (of which you'll probably 
only have one), but for a single model instance that is being submitted.    

In the example above, if you write a form that allows us to create a Family, and specify the
number of members and pets, and issues for each, you'll be submitting a number of members and
pets and a number of issues for each. Djnago expects a strict naming convention on all these
form elements, which embeds a number in the field names and TOTAL_FORMS informs it what
numbers to look for and process. 

TODO: Document the naming convention of Django form elements too.

field_data contains one entry for each field which returns the value of that field with a 
special caveat, the value is complex. If the field is not a Django relation then its actual 
value. If it is a relation then the pk or list of pks (primary keys) of the related objects.

related_values of course is only provided by UpdateViewExtended for editing existing 
objects and not by CreateViewExtended.

In the case above these context references are available:

related_forms.Member.management_form   
related_forms.Pet.management_form   
related_forms.Member.related_forms.Issue.management_form   
related_forms.Pet.related_forms.Issue.management_form   
related_forms.Member.field_data.name      # which is a string, the name 
related_forms.Member.field_data.issues    # which is a list of integers, the primary keys of the issues 
related_forms.Pet.field_data.name         # which is a string, the name 
related_forms.Pet.field_data.issues       # which is a list of integers, the primary keys of the issues 
related_forms.Member.related_forms.Issue.field_data.description   # which is a list of strings, the descriptions mapping to related_forms.Member.field_data.issues    
related_forms.Pet.related_forms.Issue.field_data.description      # which is a list of strings, the descriptions mapping to related_forms.Pet.field_data.issues
'''

import html

NONE = html.escape("<None>")
NOT_SPECIFIED = html.escape("<Not specified>")
FIELD_LINK_CLASS = "field_link"

def null_logger(msg):
    pass

# A hook to provide a logger
log = null_logger 
