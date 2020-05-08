'''
Django Generic View Extensions

Form extensions

Specifically the routines used in support rich objects forms lies herein. 

Django supplies great form for individual models and even formsets for a form 
that can submit multitple objects of the one model.

What we provide here is support for rich objects, that is objects that span models.

The primary means of defining a rich object form is with a model attribute "add_related"
which is a way of flagging in one model that if an instance (object) is added to the 
database (using a CreateView) what other models would also be added. In short, if 
this model makes no sense isolated from other models, and belong together as one
rich object definition in a sense.

See .model for a definition of add_related.
'''
# Python imports
import collections
#import pickle, codecs
from types import SimpleNamespace

# Django imports
from django.core.exceptions import ValidationError
from django.forms.models import fields_for_model, modelformset_factory, inlineformset_factory 
from django.conf import settings

# Package imports
from . import log
from .model import add_related, apply_sort_by


def classify_widget(field):
    '''
        Sets the class of a field's widget to be the name of the widget's type, so that
        a templates styling or javascript can do things to all widgets of a given type. 
    '''
    field.widget.attrs["class"] =  type(field).__name__
    return field 

def classify_widgets(form):
    '''
        For each field in a form, will add the type name of the field as a CSS class 
        to the widget so that Javascript in the form can act on the field based on 
        class if needed.
    '''
    for field in form.fields.values():
        classify_widget(field)
    return form

def get_form_fields(model):
    '''
    Return a dictionary of fields in a model to be used in form construction and management.
     
    The dictionary is in keyed on the field name with the field as a value.
    
    This is the standard Django fields_for_model but forces inclusion
    of any fields specfied in the add_related attribute of a model and it's PK   
    '''
    # Now collect the fields we want to find the values of (fields_for_model does not return the pk field)
    fields = fields_for_model(model)        

    # fields_for_model doesn't return uneditable fields ...
    # if this model has an add_related attribute and it specifies any uneditable fields then
    # override this objection and add them to the fields list, else they won't be added to the
    # related_forms. You may want for example, to explicitly to add uneditable fields to related_forms 
    # so as to be able to edit them. The reasoning is as follows: editable=False means the field won't
    # appear on the standard form editor for that model, whereas add_related means that the field
    # is offered when it's related to a model so that we can build a custom form editor for that
    # field through its relation if we want. In short we have suppressed its appearance on standard
    # model forms but made it available on related custom built model forms.
    for f in add_related(model):
        if hasattr(model, f) and not f in fields:
            fields[f] = getattr(model, f)
            
    # always include the pk field
    fields[model._meta.pk.name] = getattr(model, model._meta.pk.name)
    
    return fields

def get_formset_from_request(Form_Set, form_data):
    '''
    Given a Form_Set class and data from a request builds a form_set with field_data from the request data 
    if it can and returns it.
    '''
    # A dictionary in  {name: value or list of values}
    field_data = {}
    
    model = Form_Set.model # FIXME: Test this! A guess for now. 
    
    # Get the form fields
    fields = get_form_fields(model)
    
    # Build the formset with the supplied data, which can then be cleaned - see full_clean() below.
    form_set = Form_Set(prefix=model.__name__, data=form_data)

    # If no management form is present will fail with a ValidationError
    # no field_datacan be built in this case
    try:
        has_management_form = hasattr(form_set, 'management_form')
    except ValidationError as e:
        if e.code == "missing_management_form":
            has_management_form = False                         

    # form_data is None for an empty add form, 
    # but is not None if the add form is be re-displayed with errors
    if has_management_form:
        # Clean each form in the the formset. 
        # This leaves cleaned_data in each form of the formset, 
        # which we can use to build field values
        # related_formset.full_clean() works as well, but stops cleaning forms after the first error
        for form in form_set.forms:
            form.full_clean()
        
        # FIXME: At this point we do have:
        #    related_formset.forms.cleaned_data
        # but we also have:
        #    related_formset._errors
        # which complains about "This field is required" for session!
        # At least it's not blocking at present but this needs to 
        # be considered somehow and handled well.

        for field_name in fields:
            field_data[field_name] = []                            
            for form in form_set.forms:
                if field_name in form.cleaned_data:
                    value = form.cleaned_data[field_name]
                    # If the cleaned_data value is a database object, then we only want it's PK in the field_data list.
                    if hasattr(value, 'pk'):
                        value = value.pk
                    field_data[field_name].append(value)
                else:
                    field_data[field_name].append(None)

        # Add the field data as an attribute of the form_set we return
        form_set.field_data = field_data
                                            
    return form_set

def get_formset_from_object(Form_Set, db_object, field):
    '''
    Given a Form_Set class, a db_object and a field that is a relation, 
    builds a form_set from the db_object if it can and returns it.
    '''
    # A shorthand term
    rm = field.related_model
    
    # Get the form fields
    fields = get_form_fields(rm)

    # A dictionary in  {name: value or list of values}
    field_data = {}
    
    # QuerySet of related objects (used to build a management form), an empty queryset by default
    ros = rm.objects.none() 
    
    # If many objects are related to this one we'll build a list of values for each field_data entry
    if field.one_to_many or field.many_to_many:

        # Get the related objects
        ros = getattr(db_object, field.name).all()

        # Sorted returns a list, but ros must be a queryset for later use in creating the related_form
        # So keep ros untouched and build a sorted list separately
        # sorted_ros is just used here to populate the lists we insert into field_data in the order specified
        sorted_ros = apply_sort_by(ros)

        # For every field in the related objects we add to the (growing) list fo values either:
        #    a value, PK or list-of-PKs 
        # A value if this field has a simple value
        # A PK if the field is a foreign key to another object (then that remote objects PK)
        # A list of PKs if it is field that points to many remote objects (like a OneToMany or ManyToMany) 
        for field_name in fields:
            field_data[field_name] = []                            
            for ro in sorted_ros:
                field_value = getattr(ro,field_name)

                # If it's a single object from another model (it'll have a pk attibute) 
                if hasattr(field_value, 'pk'):
                    # Add the objects primary key to the list
                    field_data[field_name].append(field_value.pk)

                # If it's many objects from another model (it'll have a model attribute)
                elif hasattr(field_value, 'model'):
                    # Add a list of the objects primary keys to the list
                    roros = apply_sort_by(field_value.model.objects.filter(**field_value.core_filters))

                    roro_field_data = []

                    for roro in roros:
                        roro_field_data.append(roro.pk) # build a list of primary keys

                    field_data[field_name].append(roro_field_data)

                # If it's a scalar value
                else:
                    # Add the value to the list
                    field_data[field_name].append(field_value)

    elif field.many_to_one or field.one_to_one:

        # For the one related object unpack its fields into field_data
        if hasattr(db_object, field.attname):
            if getattr(db_object, field.attname) is None:
                field_value = None
            else:
                # Although we know there will be only one ro, we need ros to build related_formset below
                ros = rm.objects.filter(pk=getattr(db_object, field.attname))  # The related object
                ro = ros[0]                                                       # There will only be one

                # Store its remaining field values in field_data
                for field_name in fields:
                    # The value of the field in the related object
                    field_value = getattr(ro, field_name)

                    # If it's a single object from another model (it'll have a primary key field)
                    if hasattr(field_value, 'pk'):
                        # Add the objects primary key to the list
                        field_data[field_name] = field_value.pk

                    # If it's many objects from another model (it'll have a model field)
                    elif hasattr(field_value,"model"):
                        # Put a list of the related objects PKs into field_data
                        rros = field_value.model.objects.filter(**field_value.core_filters)
                        field_data[field_name] = []
                        for rro in rros:
                            field_data[field_name].append(rro.pk)       # build a list of primary keys

                    # For scalar values though we just record the value of the field in field_data
                    else:
                        field_data[field_name] = field_value
    
    # Build the related formset from the related objects (ros)                
    related_formset = Form_Set(prefix=rm.__name__, queryset=ros)
    
    # Add the field data as an attribute of the form_set we return
    related_formset.field_data = field_data
    
    return related_formset

def get_rich_object_from_forms(root_object, related_forms):
    # TODO: This is messy. Consider just building it directly from the form data recursively.
    #       This would mean replicating some of the object creation code in get_related_forms
    #       But we could savvily build objects from form data or db_data based on context
    #       eg, Rank from form, player from database.
    #
    #       Define rich object as the:
    #        Session
    #          Ranks
    #            Teams
    #            Players
    #          Performances
    #            Players
    #
    #        Can we infer this from the add_related attributes?
    #
    #        Food for thought.
    
    # TODO: How does this generalize to a formset of sessions say?
    
    # TODO: If model_history is empty then in this model put an attribute called
    #       complex_object or such which will be a tree of dictionaries of just the object 
    #       instances with the key being the model name, and the value being one or a list
    #       of objects of that model that are releated to the root model.
    #
    #       New ideas:
    #        rich_object
    #        root_object
    #        rich_clean
    #
    #       are these the names we want to go with?
    #
    #       This is akin to the preload concept that I need to explore too (for 
    #        performance enhancement.
    #
    #        The main goal is to have just object instances to walk during a clean to have
    #        and easy way to clean the whole complex_object.
    log.debug("Building rich object for {}".format(root_object._meta.model._meta.object_name))

    rich_object = SimpleNamespace()
    rich_object.root = root_object

    log.debug("Added root: {}".format(str(root_object)))
    
    for model, form in related_forms.items():
        log.debug("Checking form: {}".format(str(model)))
        relation = SimpleNamespace()
        relation.objects = []
        setattr(rich_object, model, relation)
        for pk, iform in form.instance_forms.items():
            log.debug("Checking instance form: {}".format(str(pk)))
            relation.objects.append(iform.object)
            log.debug("Added instance: {}".format(str(iform.object)))
            for subrelation in iform:
                log.debug("Checking relation: {}".format(str(subrelation)))
    pass

def generic_related_form(form_set):
    '''
    Given a Django form_set creates a generic related form which is basically an empty form
    with a management form and field_data added so that if it's passed into context received
    by a Django template javascript can be used to build a form_set from this related form.    
    We add the field_name too if it's provided.   
    '''
    related_form = form_set.empty_form
    related_form.management_form = form_set.management_form
    
    if hasattr(form_set, 'field_data'):
        related_form.field_data = form_set.field_data
        
    if hasattr(form_set, 'field_name'):
        related_form.field_name = form_set.field_name
       
    return related_form

#def proforma_objects():    

def get_related_forms(model, form_data=None, db_object=None, model_history=[]):
    '''
    Given a model and optionally a data source from a form or object
    will return all the related forms for that model, tracing relations
    specified in the models add_related property.
    
    if form_data or a db_object are specified will in that order of precedence 
    use them to populate field_data (see below) so that a form can initialize 
    forms with data.

    Returns a list of generic forms each of which is:
        a standard Django empty form for the related model
        a standard Django management form for the related model (just four hidden inputs that 
                    report the number of items in a formset really)
        a dictionary of field data, which has for each field a list of values one for each 
                    related object (each list is the same length, 1 item for each related object)

        The data source for field_data can be 
            form_data (typically a QueryDict from a request.POST or request.GET) or 
            a database object (being the instance of a Model)
        If no data source is specified, then only the empty and management forms are included, 
        the dictionary of field data is not.
        
    model_history is used to avoid infinite recursion. When calling itself pushes the model onto model_history, and 
    on entering checks if model is in model_history, bailing if so.
    '''    
    def custom_field_callback(field):
        '''A place from which to deliver a customised formfield for a given field'''
        return field.formfield()

    assert not model in model_history, "Model Error: You have defined a recursive set of model relations with the model.add_related attribute."

    # This funcion is recursive, and searches for related forms in related forms in related forms ...
    # So we track the depth of the recursion here and keep a history so as to try and avoid endless loops.  
    model_depth = len(model_history)
    debug_prefix = '\t' * model_depth 
            
    log.debug(f"\n{debug_prefix}=================================================================")
    log.debug(f"{debug_prefix}Starting get_related_forms({model._meta.object_name}), history={[m._meta.object_name for m in model_history]}")

    # A db_object if supplied must be an instance of the specified model     
    if not db_object is None:
        assert isinstance(db_object, model), "Coding Error: db_object must be an instance of the specified model"

    if not form_data is None:
        log.debug(f"{debug_prefix}Using form_data:")
        for (key, val) in form_data.items():
            log.debug(f"{debug_prefix}\t{key}:{val}")
        log.debug("\n")            
    elif not db_object is None:
        log.debug(f"{debug_prefix}Using db_object: {db_object._meta.object_name} {db_object.pk}")

    related_forms = collections.OrderedDict()

    log.debug(f"{debug_prefix}Looking for {len(add_related(model))} related forms: {add_related(model)}.")

    relations = [f for f in model._meta.get_fields() if (f.is_relation)]
    if len(relations) > 0:
        for relation in relations:
            # These are the relations we can expect:
            #     many_to_many:  this is a ManyToManyField
            #     many_to_one:   this is a ForeignKey field
            #     one_to_many    this is an _set field (i.e. has a ForeignKey in another model pointing to this model and this field is the RelatedManager)
            #     one_to_one:    this is a OneToOneField
            #
            # At this point we have a model, and a list of relations (other models that relate to it)
            # For a given relation there will be one or more related objects. If the relation is of the
            # form ToOne there will be one related object. If the relation is of the form ToMany there will 
            # be many related objects. 
            #
            # For this relation we want a "related_form" which we'll provide as a empty_form
            # and if a data source is provided (form_data or db_object), to that empty_form  
            # we want to add an attribute "field_data" which has for each field in the empty form 
            # a list of values for each instance. 
            #
            # For completeness we also add instance_forms to the empty form which is a dictionary of forms
            # keyed on the PK of the individual instances (that are listed in field_data) and the value
            # is a form for that instance (essentially the empty_form with values in the fields).
            #
            # The value in field_data might itself be a simple scalar (for ordinary fields), or a PK if 
            # the field is a _to_one relation (a relation pointing to one object of another model, or a list of
            # PKs if the field is a _to_many relation (a relation pointing to many objects in another model).  
            #
            # This is a proxy for a related_formset in a way. The related_form is an empty_form, a pro
            # forma for one form in the formset and field_data contains for each field in the related model a 
            # list of values, one for each form in the formset from which a web page can, in javascript, create
            # the individual forms in the formset with populated values. 
            #
            # To reiterate:
            #
            # There is one field_data for each related model, and it is dictionary which is keyed on the 
            # related model's field name(s). The value will depend on whether the relation is to one or many 
            # other objects (i.e. contain a value or a list). 
            #
            # The field in the related_model can itself be:
            #    a value    - in which case the item added to a field_data list is a value
            #    a relation to one related object - in which case the item added to a field_data list is a PK
            #    a relation to many related objects - in which case the item added to a field_data list is a list of PKs
            #
            # So field_data for a given field could be a list of lists all depending on the relationships.
            #
            # This is recursive, in that the related_form may also be given an attribute "related_forms" which is
            # a dictionary of related forms in the self same manner for that related model. 
            # 
            # For added convenience, the fields in each related model are also included in field_data.
            # They are included as lists of values (one for each instance) with pseudo field names in form
            # model__field (using django's double underscore convention). This is complicated and a good
            # working example will be useful
            #
            # To include a relation it has to be identified in a model's add_related attribute.
            # Either this object has a field which is specified in its add_related list, or
            # The related model has a field which is specified in add_related (in the format "model.field")
            # The relation will have an attribute named "field" if it's a candidate for the latter. 
            # That "field" in the relation is the field in the related model which points to this one.
            #
            # Examples to elucidate:
            #
            # 1) If we have a Team model and object there is a related model Member which has a field 
            # named "team" which is a ForeignKey field pointing team, then this is many_to_one relationship 
            # (many Members per Team), then the Team model we should have an attribute add_related = ['Member.team']
            # to request that we include the related form for Member. There is no field in Team for the relationship
            # for us to specify! But if the team field in Member has a related_name ('members' for example) a field of 
            # that name is created in Team and so we also can request the related form with  add_related = ['members'].
            # Both methods are supported here.
            #
            # 2) If on the other hand a Member can be in multiple Teams, then we have a many_to_many relationship. This
            # could be via a ManyToMany field in Team called "members", and if so to include the related form for Member
            # we would specify add_related = ['members'].
            #
            # In case 2) the name of the relation will be 'members' and this is what we can look for in add_related(model)
            # In case 1) the name of the relation will be the related_name that was specified for the team field in Member,
            # and the relation will have a field that is the field in Member that is pointing to Team. In this example
            # a field 'team' that points to Team and so Member.team is also a way to specify this related form if desired.
            
            # If the model's add_related field mentions this relation ... and only if.
            if ( relation.name in add_related(model)
                or (hasattr(relation, "field") 
                and relation.field.model.__name__ + "." + relation.field.name in add_related(model)) ):
                
                # Build the class for the related formset. The related formset will be an instance of this class 
                Related_Formset = modelformset_factory(relation.related_model, can_delete=False, extra=0, fields=('__all__'), formfield_callback=custom_field_callback)
                related_formset = None # Will be built using either form_data or db_object as a data source 

                # By default, we have no management form. One comes into being if we succeed in
                # populating a formset with form_data or from a db_object.  
                has_management_form = False
                
                # ==============================================================
                # Build the related_formset and field_data for this relation
                
                # Try to use form_data if it's present (it may fail as the form_data may not include
                # a submission for the related model). We record success or failure in found_form_data  
                # so we can look at db_object for field values.
                found_form_data = False
                if not form_data is None:
                    related_formset = get_formset_from_request(Related_Formset, form_data)
                    if hasattr(related_formset, "field_data") and related_formset.field_data:
                        found_form_data = True

                # If no form data was found try and find it in the db_object
                if not found_form_data and not db_object is None:                    
                    log.debug(f"{debug_prefix}Getting formset from: {db_object._meta.object_name} {db_object.pk} using relation {relation} through the field {relation.name}.")
                    related_formset = get_formset_from_object(Related_Formset, db_object, relation)

                # If no management form is present this will fail with a ValidationError
                # Catch this fact here quietly, for compatibility with the 'add' 
                # approach, and ease of saving it later (the management form that is)
                try:
                    has_management_form = hasattr(related_formset, 'management_form')
                except ValidationError as e:
                    if e.code == "missing_management_form":
                        has_management_form = False
                    
                # If we didn't succeed in building a formset from form_data or a db_object just
                # build one from the model, for the empty_form including a management form,
                if not has_management_form:
                    related_formset = Related_Formset(prefix=relation.related_model.__name__)
                
                # Add the name of the field/relation to the related form.
                # We want to know this when saving related to check the field properties.
                related_formset.field_name = relation.name 

                # Build the generic_related_form for this relation and save it
                model_name = relation.related_model.__name__
                related_forms[model_name] = generic_related_form(related_formset)

    log.debug(f"{debug_prefix}Found {len(related_forms)} related forms: {[f[0] for f in related_forms.items()]}.")

    # Now add an instance form for each instance that we find in the field_data
    # and for each instance form, look for related forms in turn, walking down the 
    # tree so to speak. 
    for rf in related_forms:
        rm = related_forms[rf].Meta.model
        
        log.debug(f"\n{debug_prefix}Processing {rm._meta.object_name}: add_related={add_related(rm)} ")
        
        # add generic related forms (with no object) to provide easy access to 
        # the related empty form and field widgets in the context. Instance forms
        # are added later for each related object. 
        if add_related(rm):
            related_forms[rf].related_forms = get_related_forms(rm, model_history=model_history+[model])
            log.debug(f"{debug_prefix}Got {len(related_forms[rf].related_forms)} generic forms related to {rm._meta.object_name}: {list(related_forms[rf].related_forms.keys())}")
        
            # add instance_forms for each instance (of the related form)
            if hasattr(related_forms[rf], "field_data") and rm._meta.pk.attname in related_forms[rf].field_data:
                related_forms[rf].instance_forms = {}
    
                # Ordering is important here as field_data which are lists are in an order and should all be in the same order
                # So we need to observe and respect the order of pk values in field_data when creating instance lists of related values
                pk_list = []                   # Keep an ordered list of the PKs as the dictionary "instance_forms" loses order
                pk_attr = rm._meta.pk.attname  # Get the name of the primary key attribute
    
                # Create the instance_forms, that is one related_forms object per related instance  
                pk_placeholder = 0
                
                # To loop easily, we need a list of pks 
                # but it may be in field_data as a single pk not a list so build a list if it's not a list.
                pks = related_forms[rf].field_data[pk_attr]
                pks = pks if isinstance(pks, list) else [pks] 
                log.debug(f"{debug_prefix}Processing {rm._meta.object_name}: instance PKs={pks}")
    
                for pk in pks:
                    if pk is None:
                        ph = 'PK_{}'.format(pk_placeholder)
                        pk_placeholder += 1
                        log.debug(f"{debug_prefix}{rm._meta.object_name} PK=None so using a placeholder PK={ph}")
                    else:
                        ph = pk
                        log.debug(f"{debug_prefix}{rm._meta.object_name} PK={ph}")
                    pk_list.append(ph)
                                                            
                    if not pk is None:
                        o = rm.objects.get(pk=pk)
                        log.debug(f"{debug_prefix}{rm._meta.object_name} PK={ph}. Got object from DB: {o}")
                    else:
                        i = len(pk_list)-1
                        fields = {}
                        log.debug(f"{debug_prefix}{rm._meta.object_name} PK={ph}. Checking field_data : {related_forms[rf].field_data.items()}")                    
                        for field, values in related_forms[rf].field_data.items():
                            f = rm._meta.get_field(field)
                            log.debug(f"{debug_prefix}{rm._meta.object_name} PK={ph}. Checking field: {field}, i: {i}, values[i]: {values[i]}, f: {f}, f.is_relation: {f.is_relation}")
                            if values[i] is None:
                                val = None
                            elif f.is_relation:
                                m = f.related_model
                                log.debug(f"{debug_prefix}{rm._meta.object_name} PK={ph}. related_model: {m}, one_to_one: {f.one_to_one}, many_to_one: {f.many_to_one}, one_to_many: {f.one_to_many}, many_to_many: {f.many_to_many}")
                                if f.one_to_one or f.many_to_one:
                                    val = m.objects.get(pk=values[i])
                                elif f.one_to_many or f.many_to_many:
                                    # TODO: Test this, could fail, untested code!
                                    val = m.objects.filter(pk__in=values[i]) 
                            else:
                                val = values[i]
                            
                            # I know this bombs when a many_to_many field with val None is added to fields
                            # TODO: Check this works for many_to_many fields when val is not None! 
                            # To do this edit a team play session and put a break here on save. Should land
                            # here with a many to many with a val.   
                            if not ((f.one_to_many or f.many_to_many) and val is None):    
                                fields[field] = val
                            
                        log.debug("{debug_prefix}{rm._meta.object_name} PK={ph}. Building object from field_data : {fields}")
                        o = rm(**fields)
                        log.debug("{debug_prefix}{rm._meta.object_name} PK={ph}. Built object from field_data : {o}")
                    
                    # Earlier we added a generic empty related form, now we add a specific one for each instance populated with
                    # data avalable.
                    instance_forms = get_related_forms(rm, form_data=form_data, db_object=o, model_history=model_history+[model])
                    instance_forms.object = o
                    
                    if not instance_forms is None:               
                        log.debug(f"{debug_prefix}{rm._meta.object_name} PK={ph}. Got {len(instance_forms)} related instance forms: {list(instance_forms.keys())}.")
                        related_forms[rf].instance_forms[ph] = instance_forms
                            
            # Finally, for ease of use in the template context 
            # add field_data for all the instance related fields as well
            # TODO: Why do we populate field_data only for Player not for Rank?
            if hasattr(related_forms[rf],"instance_forms"):
                log.debug(f"{debug_prefix}Building field_data for model={rm._meta.object_name}, PKs={pk_list}")
                for pk in pk_list: # Walk the ordered list of PKs
                    log.debug(f"{debug_prefix}Found {len(related_forms[rf].instance_forms[pk])} instance forms: {list(related_forms[rf].instance_forms[pk].keys())} related to {rf} PK={pk}")
                    for form in related_forms[rf].instance_forms[pk]:
                        if hasattr(related_forms[rf].instance_forms[pk][form], "field_data") and len(related_forms[rf].instance_forms[pk][form].field_data) > 0:
                            log.debug(f"{debug_prefix}Adding field data to instance form of model={form} related to {rf} PK={pk}")
                            for ro_field in related_forms[rf].instance_forms[pk][form].field_data:
                                ro_field_name = form + "__" + ro_field
                                ro_field_value = related_forms[rf].instance_forms[pk][form].field_data[ro_field]
                                if not ro_field_name in related_forms[rf].field_data:
                                    related_forms[rf].field_data[ro_field_name] = []
                                related_forms[rf].field_data[ro_field_name].append(ro_field_value)
                                log.debug(f"{debug_prefix}Added {ro_field_name}={ro_field_value}")                           
        else:
            log.debug(f"{debug_prefix}No related forms to build.")
            
    log.debug(f"{debug_prefix}Done with get_related_forms({model._meta.object_name})")
    log.debug(f"{debug_prefix}=================================================================\n")
    return related_forms            

def save_related_forms(self):
    # TODO: Implement and test this - a work in progress 
    # Docs state: If your formset contains a ManyToManyField, you’ll also need to call 
    #                formset.save_m2m() to ensure the many-to-many relationships are saved properly.
    #                What does that mean?
    #
    # Very helpful page:
    #   https://docs.djangoproject.com/en/dev/topics/forms/modelforms/#id1
    #
    # TODO: Consider how this works if:
    #
    # 1. There is a foreignkey in the related model pointing here: OneToMany
    # 2. There is a foreignkey here to another model: ManyToOne
    # 3. This is a ManyToMany relationship
    #
    # In each case how are the table links saved properly?
    #
    # In case 1: the related formset is an instantiation with the original object passed as an instance. 
    # That is how Django knows which object the related formset relates to.
    # Case 2 and 3 uncertain at present. Think about it.
    
    # This code saves properly and can be used in interim.
    # TODO: Review how this fits in with cleaning
    
    # Fetch all the related forms. 
    log.debug(f"Getting related forms for {self.model._meta.object_name} {self.object.pk}, operation: {self.operation}")
    related_forms = get_related_forms(self.model, db_object=self.object)
    
    log.debug(f"Saving {len(related_forms)} Related Forms: {[name for (name, form) in related_forms.items()]}")
    
    log.debug(f"Requesting IP is: {self.request.META['REMOTE_ADDR']}")
    
    log.debug("From POST request containing:")
    for (key, val) in sorted(self.request.POST.items()):
        log.debug(f"\t{key}: {val}")
    
    # We won't want to save all of them. To save a related form we need:
    # 
    # 1. The related field in this model to be editable. If it's not it wasn't on the 
    #    parent form, or sure shouldn't have been. We can set editable=False on a model field
    #    specifically to prevent submission from forms.
    #
    # 2. There is data, any data, provided. If not form.data will be empty and it simply 
    #    means 1. was honoured at least but perhaps for some other reason the submitting form
    #    has elected not to submit this form. 
    #
    # 3. The field related to this form is mentioned in the models 'add_related' attribute. 
    #    That's the mechanism we use to flag that related forms should be added/saved with
    #    this parent form. NOTE: This is checked in get_related_forms() already so we don't 
    #    need to check it here really, but we should assert it all the same.
    #
    # That should cover it and let through any related forms that SHOULD be saved, namely
    # those mentioned in add_related, those that are editible and those that have provided 
    # data. 
    
    for name,form in related_forms.items():
        model = self.model                              # The model being saved
        obj = self.object                               # The object created when it was saved
        related_model = form._meta.model                # The related model to save
        field_name = form.field_name                    # Get the field name in self.model that this relation relates to  
        relation = getattr(model, field_name, None)     # Get the field itself (which is a relation)

        mon = model._meta.object_name                   # Model Object Name
        rmon = related_model._meta.object_name          # Related Model Object Name
        
        log.debug(f"Saving {mon}->{rmon}")
                
        if relation.field.editable and (len(self.request.POST) > 0 or len(self.request.FILES) > 0):
            assert field_name in add_related(model), "Progamming Error: field_name is not in add_related yet we're trying to save it!"
            
            Related_Formset = inlineformset_factory(model, related_model, can_delete=True, extra=0, fields=('__all__'))
            related_formset = Related_Formset(self.request.POST, self.request.FILES, instance=obj, prefix=name)
            
            if related_formset.is_valid():
                ran = relation.rel.related_name         # Related Attribute Name
                rfn = relation.field.name               # Related model field name

                log.debug(f"\t{mon}->{rmon} is valid. Used prefix={name} and instance={mon} {obj.pk}")
                if (settings.DEBUG):
                    robjs_before = len(getattr(obj, ran).all())
                    log.debug(f"\t\t{mon} {obj.pk}: checking parent before save {ran}={robjs_before}")

                # This is interesting:
                # https://stackoverflow.com/questions/12486734/how-to-save-m2m-field-in-a-formset-when-commit-false
                #
                # Apparently we can do this:
                
#                 for form in related_formset:                
#                     if form.has_changed(): 
#                         form.save()

                # And he also notes this fascinating pattern
                
#                 deal = fm.save(commit=False)
#                 ...
#                 deal.save()

                # Implying we can save our session with commit=False and get an object with a PK!
                # So we can then look the related forms and save them!
                # This looks cool.
                
                log.debug(f"\t{mon}->{rmon} Saving related formset...")
                instances = related_formset.save()  # returns the instances saved but we don't need them here

                # Debugging output
                if (settings.DEBUG):
                    robjs_after = len(getattr(obj, ran).all())
                    log.debug(f"\t\t{mon} {obj.pk}: checking parent after save {ran}={robjs_after}")

                    if (robjs_after>robjs_before):
                            log.debug(f"\t\t{mon} {obj.pk}: added {robjs_after-robjs_before} {rmon}s")

                    for instance in instances:
                        parent = getattr(instance, relation.field.name, None)
                        if (not parent is None):                    
                            log.debug(f"\t\t{mon} {obj.pk}: saved {rmon}={instance}. It has {rfn}={parent.pk}")
                            log.debug(f"\t\t{mon} {obj.pk}: checking parent {ran}={getattr(parent, ran).all()}")
                    
                    if (len(instances) == 0):
                            log.debug(f"\t\t{mon} {obj.pk}: did not save any {rmon}s")
                            
                    if (robjs_after<robjs_before):
                            log.debug(f"\t\t{mon} {obj.pk}: deleted {robjs_before-robjs_after} {rmon}s")
            else:
                # TODO: Report errors cleanly on new edit form
                # Errors are in related_formset.errors
                raise ValueError(f"Form errors: {related_formset.errors} in form {related_formset}")    
    
    return False # Return no errors

# This was an experiment to save object data to the session for inherit_fields. 
# Abandoned. But the learning is good and should move this to session.py and keep
# it on hand as a generic session data saver and loader (modifed a little to be more generic).
# 
# def save_inherit_fields(session, model_instance):
#     for field_name in inherit_fields(model_instance._meta.model):
#         attr = getattr(model_instance, field_name)
#         session["last_saved__"+field_name] = codecs.encode(pickle.dumps(attr), "base64").decode() 
#     
# def get_inherit_fields(session, model):
#     inheritance = {}
#     for field_name in inherit_fields(model):
#         field_value = session.get("last_saved__"+field_name)
#         if not field_value is None:
#             attr = pickle.loads(codecs.decode(field_value.encode(), "base64"))
#             inheritance[field_name] = attr
#             
#     return inheritance if len(inheritance) > 0 else None 