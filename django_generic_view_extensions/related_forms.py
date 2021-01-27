'''
Django Generic View Extensions

Related Form extensions

Specifically the routines used to support rich forms by creating a related_forms
data structure to attach to any given form. 

The primary means of defining a rich object form is with a model attribute "add_related"
which is a way of flagging in one model that if an instance (object) is added to the 
database (using a CreateView) what other models would also be added. In short, if 
this model makes no sense isolated from other models, and belong together as one
rich object definition in a sense.

There are two primary use cases, viewing forms and processing fsubmitted forms.

Each of these in the case of a CreateView and an UpdateView which dictate what
data is available for display primarily.

See .model for a definition of add_related.
'''
from collections import OrderedDict

from django.conf import settings
from django.db.models import Model
from django.forms.models import modelformset_factory, inlineformset_factory, fields_for_model
from django.core.exceptions import ValidationError

from . import log
from .model import add_related, Add_Related, can_save_related_formsets
from alembic.util.compat import callable

class RelatedForms(dict):
    # The basic offering here is build a list of related forms
    # It will be recursively generated and for that reason we encapsulate
    # the process in  class with some diagnostic features.
    
    # related_forms will be a list of empty forms each empy form being granted
    # extra attributes:
    #
    # field_data     a dictionay of data that describe one or more 
    #                instances of the data filled form
    # 
    # instance_forms a list of forms populated with data, one for each 
    #                instance of database object found. 
    #
    # related_forms  recursively, the same thing. That is rich objects
    #                can conceivably be more than on level deep. 
    __model_history = []   # A list of model names traversed to avoid enldess recursion
    __model         = None
    __form_data     = None 
    __db_object     = None
    __related_forms = None
    
    @property
    def dp(self):
        '''
        An indenter for the recursive debugging output (a debug prefix, dp)
        '''
        return str(self.__model_history) + " "
        #return '\t' * len(self.__model_history)
    
    def __init__(self, model, form_data=None, db_object=None):
        '''
        Generates a list of related forms (in self.related_forms) given
        a model and either a dictionary of form data (as delivered by a 
        Django form) or a database object as a source of the data. They 
        present data differently, form data as a dictionary of POSTed 
        fields and the db object as an ORM python object being an instance
        of model.   
        
        :param model:        The model for which we want the related forms
        :param form_data:    form data to augment the related forms with, if available
        :param db_object:    an instance of model to augment related forms with, if available
        '''
        super().__init__()
        self.__model_history = []
        self.__model         = model 
        self.__form_data     = form_data
        self.__db_object     = db_object
        self.__related_forms = self.get(model, form_data, db_object)

        # As RelatedForms is derived from OrderedDict (derived from dict)
        # we update self with the related forms.  
        self.update(self.__related_forms)
        
    def get(self, model=None, form_data=None, db_object=None):
        '''
        Given a model and optionally a data source from a form or object
        will return all the related forms for that model, tracing relations
        specified in the models add_related property.
        
        if form_data and/or a db_object are specified will in that order of 
        precedence use them to populate field_data (see below) so that a 
        form can initialize forms with data.
        
        There are two supported and tested use cases for this:
        
        Form rendering:
            CreateView: we have no form_data or db_object yet.
                            modelformset_factory is used here.
            Updateview: we have no form_data but a db_object. 
                            modelformset_factory is used here
                            initialised with a db_object.
        Form posting (submission):
            We have form_dat and a db_object in both Create 
            and Update Views.
            That is because RelatedForms instantiated only 
            after a parent object has been saved

        Returns a list of generic forms each of which is:
            a standard Django empty form for the related model
            the generic/empty form is given a number of new attributes
                model
                    the model class of the parent.
                field_name
                    The name of the field in model this related form is for,
                management_form
                    a standard Django management form for the 
                    related model (just four hidden inputs that 
                    report the number of items in a formset really)
                field_data
                    a dictionary of feidl names and values
                    values of remote objects are reduced to primary keys
                    On to_one relations the value is otehrwise naked
                    On to_many relations it will be a list of such values.
                formset
                    A formset based on field_data. of key importance when
                    saving related forms.
                instance_forms
                    if there is a known related instance or istances
                    a form for each instance provided in a dict keyed by
                    primary key. The each have a related_forms attribute
                    whhich is recursively the same deal with this model 
                    and instance in focus.
                related_forms
                    Recursively the same deal with this model in focus.
    
            The data source for field_data can be 
                form_data (typically a QueryDict from a request.POST or request.GET) or 
                a database object (being the instance of a Model)
            
        model_history is used to avoid infinite recursion. When calling itself pushes 
        the model name onto model_history, and on entering checks if model is in 
        model_history, bailing if so. It is also used to make debugging output 
        more lucid. As a recurisve process it can weave tangled web quickly.
        
        :param model:        A Django model (instance of django.db.models.Model)
        :param form_data:    A dictionary of form data from request.form.data or request.POST
        :param db_object:    An instance of model.
        '''
        def custom_field_callback(field):
            '''A place from which to deliver a customised formfield for a given field if desired'''
            return field.formfield()

        # This funcion is recursive, and searches for related forms in related forms in related forms ...
        # So we track the depth of the recursion here and keep a history so as to try and avoid endless loops.  
        model_name = model._meta.object_name
        assert not model_name in self.__model_history, f"Model Error: You have defined a recursive set of model relations with the model.add_related attribute. {model_name} already in {self.__model_history}."

        self.__model_history.append(model_name)

        log.debug(f"\n{self.dp}=================================================================")
        log.debug(f"{self.dp}Starting get_related_forms({model_name}, {form_data=}, {db_object=}).")
    
        # A db_object if supplied must be an instance of the specified model     
        if not db_object is None:
            assert isinstance(db_object, model), f"Coding Error: db_object must be an instance of the specified model. {db_object=}, {model=}"
    
        # Use either form_data or db_object as a data source to populate for field_data
        # (an attribute of the related_forms we return that contains data for populating 
        # empty form with or instance_forms if we have database instances of related objects)
        if not form_data is None:
            log.debug(f"{self.dp}Using form_data:")
            for (key, val) in form_data.items():
                log.debug(f"{self.dp}\t{key}:{val}")
            log.debug("\n")
        elif not db_object is None:
            log.debug(f"{self.dp}Using db_object: {db_object._meta.object_name} {db_object.pk}")
    
        log.debug(f"{self.dp}Looking for {len(add_related(model))} related forms: {add_related(model)}.")
    
        # Collect a list of the relations this model has (i.e. the candidate related models
        # We wil only add forms for those that the models add_related attribute requests of
        # course, but of those specified, they must be relations to otehr models. 
        #
        # These can be to_one or to_many relations. 
        relations = [f for f in model._meta.get_fields() if (f.is_relation)]
        
        # Build a list of the relations_to_add that we want to add.
        relations_to_add = []
        for relation in relations:
            if Add_Related(model, relation):
                relations_to_add.append(relation)

        log.debug(f"{self.dp}Found {len(relations_to_add)} relations to add: {relations_to_add}.")

        # We have five goals here:
        #
        # 1. To build an empty form for the related_model which will be related_forms[model_name]
        # 2. To collect the PK or Pks for the related objects if possible.
        # 3. Populate related_forms[model_name].field_data with a dictionary keyed on field name
        #    that contains for each field a single value for simple fields and for to_one relations 
        #    or a list of values for to_many relations.
        # 4. Populate related_forms[model_name].instance_forms which is a dictionary keyed on PK
        #    of pre-filled forms (with the object data)  
        # 5. To drill down to the related model and repeat (recursivelY)

        # These are the relations we can expect:
        #     many_to_many:  this is a ManyToManyField
        #     many_to_one:   this is a ForeignKey field
        #     one_to_many    this is an _set field (i.e. has a ForeignKey in another model pointing to this model and this field is the RelatedManager)
        #     one_to_one:    this is a OneToOneField
        
        # For a to_one relation we want 
        #       an empty_form for the related model
        #       field_data that has single values for each field in the empty form
        #       an instance_form if a related databse object exists 
        
        # For a to_many relation we want
        #       an empty_form for the related model
        #       field_data that has a list of values for each field in the empty form 
        #            (one for each form in a formset, 
        #             or instance in to_may database relation
        #             depending on the data source)
        #       an instance_form if a related databse object exists 

        # We will build an ordered dicted of related forms 
        related_forms = OrderedDict()
    
        # ========================================================
        # STEP 1: Generate a generic/empty for for each relation
        log.debug(f"\n{self.dp}STEP 1: Generate generic/empty form as a vessel.")
        for relation in relations_to_add:
            # Get the names of the model and related model
            related_model_name = relation.related_model.__name__
            log.debug(f"\n{self.dp}\tExamining the {related_model_name} in {model_name}.")
            
            inline = can_save_related_formsets(model, relation.related_model)
            
            # We use a formset_factory to create these generic/empty forms
            #
            #    formset_factory 
            #        lets you render a bunch of forms together, but these forms 
            #        are NOT related to any database models.
            #    modelformset_factory 
            #        lets you create/edit a bunch of Django model objects together, 
            #    inlineformset_factory 
            #        lets you manage a bunch of Django model objects that are all 
            #        related to a single instance of another model. 
            if form_data and db_object and inline: 
                Related_Formset = inlineformset_factory(model, relation.related_model, can_delete=True, extra=0, fields=('__all__'), formfield_callback=custom_field_callback)
            else:
                Related_Formset = modelformset_factory(relation.related_model, can_delete=False, extra=0, fields=('__all__'), formfield_callback=custom_field_callback)
            
            # Build a forset from form data if available, else db_object, else an empty one 
            if form_data:
                if db_object and inline:
                    related_formset = Related_Formset(prefix=related_model_name, data=form_data, instance=db_object)
                else: 
                    related_formset = Related_Formset(prefix=related_model_name, data=form_data)
                    
                log.debug(f"{self.dp}\tUsing form data to populate field_data.")
                related_objects = []
            elif db_object:
                related_field = getattr(db_object, relation.name)

                log.debug(f"{self.dp}\t{relation.name=}")
                log.debug(f"{self.dp}\t{related_field=}")
                log.debug(f"{self.dp}\t{getattr(related_field, 'all', None)=}")

                if relation.one_to_many or relation.many_to_many:
                    if callable(getattr(related_field, 'all', None)):
                        related_objects = related_field.all()
                    else:
                        log.error(f"A to_many relation premise is broken!")
                        related_objects = relation.related_model.objects.none()
                elif relation.many_to_one or relation.one_to_one:
                    if related_field:
                        related_objects = type(related_field).objects.filter(pk=related_field.pk)
                    else:
                        related_objects = relation.related_model.objects.none()
                else:
                    log.error(f"An unknown relation encountered!")
                    related_objects = relation.related_model.objects.none()
                    
                log.debug(f"{self.dp}\tUsing related objects to populate field_data: {related_objects}.")
                related_formset = Related_Formset(prefix=related_model_name, queryset=related_objects, data=form_data)
            else:
                related_objects = relation.related_model.objects.none()
                related_formset = Related_Formset(prefix=related_model_name, queryset=related_objects)
                log.debug(f"{self.dp}\tfield_data cannot be populated.")
                
            # Build the generic_related_form for this relation and save it
            # This is an empty form (fields unpopulated)
            generic_form = related_formset.empty_form    # The basic form for the related model
            generic_form.model = relation.related_model  # The related model (which the form is for) self.save() want this.
            generic_form.field_name = relation.name      # The field in model which is to_one or to_many relation to the related_model
            generic_form.formset = related_formset       # Keep a copy of the formset for saving later if needed 
            
            related_forms[related_model_name] = generic_form
            
            # ==========================================
            # STEP 2: add field_data to the generic_form
            management_form = getattr(related_formset, 'management_form', None)
            
            log.debug(f"{self.dp}\tSTEP 2: {'' if management_form else 'CANNOT '}Build field_data from management form: {management_form}")

            field_data = {}
            if management_form:
                # Add the management_form to the basic related form (generic_form)
                generic_form.management_form = management_form

                log.debug(f"{self.dp}\t{related_formset.forms=}")
                number_of_forms = len(related_formset.forms)
                for form in related_formset.forms:
                    # Clean the form
                    form.full_clean()

                    d = getattr(form, "data", {})
                    cd = getattr(form, "cleaned_data", {})
                    log.debug(f"{self.dp}\t\tCleaned form: data={d}, cleaned_data={cd}")
                
                    for field_name in self.get_form_fields(relation.related_model):
                        # If data came in through form_data, we should have cleaned data.
                        if field_name in getattr(form, "cleaned_data", {}):
                            field_value = form.cleaned_data[field_name]
                        # If data came in through db_objects then we won't cleaned data 
                        # but it will initial data, but only if it's an editable field
                        elif field_name in getattr(form, "initial", {}):
                            field_value = form.initial[field_name]
                        # For all other fields, we can find them in the instance:
                        elif hasattr(form.instance, field_name):
                            field_value = getattr(form.instance, field_name)

                            # If it a to_one relationship we use the PK of the object as the value
                            if isinstance(field_value, Model):
                                field_value = field_value.pk
                            # If it'a ManyRelatedManager it'll have a values_list and we use the list of PKs
                            elif hasattr(field_value, 'values_list'):
                                field_value = list(field_value.values_list('pk', flat=True))
                        else:
                            field_value = None

                        if number_of_forms > 1:
                            if not field_name in field_data: field_data[field_name] = []
                            field_data[field_name].append(field_value)
                        else:
                            assert not field_name in field_data, f"Internal error: Premise of uniqueness broken. {field_name} already in {field_data}."
                            field_data[field_name] = field_value
                        
                        log.debug(f"{self.dp}\t\t\tAdded {field_name} = {field_value} to produce {field_data[field_name]}.")
                
                # Add the field_data assembled from the forms in the formset                              
                generic_form.field_data = field_data
            
            log.debug(f"{self.dp}\tSTEP 3: Add instance forms for {len(related_objects)} instances.")
            pk_attr = relation.related_model._meta.pk.attname

            # An instance form, it's related forms and its field data are all 
            # generated once per instance. Each instance as a for in related_formset.forms
            # modelformset_factory ensures that whether we inform it from form_data (a POST) or 
            # from a db_object (loaded from the database) 
            if related_objects and hasattr(generic_form, "field_data") and pk_attr in generic_form.field_data:
                log.debug(f"{self.dp}\tAdding instance forms.")
                
                generic_form.instance_forms = {}
                
                # For each instance ...
                number_of_instances = len(related_formset.forms)
                for form in related_formset.forms:
                    # ====================================================
                    # STEP 3: Add an instance form for each related object
                    generic_form.instance_forms[form.instance.pk] = form

                    # ===============================================
                    # STEP 4: Add related_forms to each instance form
                    rfs = self.get(relation.related_model, form_data=form_data, db_object=form.instance)
                    generic_form.instance_forms[form.instance.pk].related_forms = rfs
                    log.debug(f"{self.dp}\t\tAdded instance for form for {related_model_name} PK={form.instance.pk} with {len(rfs)} related forms: {list(rfs.keys())}")

                    # =====================================================
                    # STEP 5: Copy up related form field data to this level
                    for rf, rform in rfs.items():
                        for field, value in getattr(rform, 'field_data', {}).items():
                            name = rf + "__" + field

                            if number_of_instances > 1:
                                if not name in generic_form.field_data: generic_form.field_data[name] = []
                                generic_form.field_data[name].append(value)
                            else:
                                assert not name in generic_form.field_data, f"Internal error: Premise of uniqueness broken. {name} already in {generic_form.field_data}."
                                generic_form.field_data[name] = value
                                
                            log.debug(f"{self.dp}\t\t\tAdded {name} = {value} producing {generic_form.field_data[name]}")
                            
            # ====================================================================================
            # STEP 6: Whether there is an instance or not we want a related_forms attribute
            #         with empty forms, just so that we can provide the widgets to a Django context.
            generic_form.related_forms = self.get(relation.related_model)
    
        log.debug(f"{self.dp}Found {len(related_forms)} related forms: {[f[0] for f in related_forms.items()]}.")
        log.debug(f"{self.dp}=================================================================\n")

        self.__model_history.pop()
        return related_forms            

    def save(self):
        '''
        Save the related forms. Assumes that an object just saved was used to instantiate
        this class - a la:
        
            obj = self.form.save()
            rf =  RelatedForms(model, self.form.data, db_object)
        '''
        # ASAP: check difference between form.data and request.POST if any.
        return self._save()

    def _save(self, db_object=None, related_forms=None):
        '''
        Recursively saves related forms as needed. To avoid exposing hte recursion 
        management save() is implemented without them, and this is the internal 
        recursor.
        
        form_data is supplied when RelatedForms is instantiated and doesn't 
        need to travel through arguments. The db_object and it's related_forms 
        though do need to travel through arguments (as each recursion is a step
        down into a relation.
        
        :param db_object:        The object just saved
        :param related_forms:    The related forms to use (for saving)
        
        Each related form must have data (not be empty) if it is to be saved.
        '''
        # On the first call (depth = 0) start depth tracing with model_history.
        if not db_object: self.__model_history = []

        # On the first call, use the object RelatedForms was instantiated with 
        if not db_object:
            if self.__db_object:
                db_object = self.__db_object
            else:
                raise ValueError(f"{self.__class__.__name__}.save(): {self.__class__.__name__} must be instantiated with a db_object in order to save related forms.") 
        
        # Get the model of the object just saved.
        model = type(db_object)
        
        # Keep a list of models, to avoid a recursion loop, and to help debugging.
        model_name = model._meta.object_name
        assert not model_name in self.__model_history, f"Model Error: You have defined a recursive set of model relations with the model.add_related attribute. {model_name} already in {self.__model_history}."

        self.__model_history.append(model_name)

        # Get the related forms for this model/object
        if related_forms == None:
            related_forms = self.__related_forms

        log.debug(f"{self.dp} Starting {self.__class__.__name__}.save() with {len(related_forms)} related forms on {model_name} {db_object.pk}: {db_object}")

        # Now for each related form ... 
        for name, form in related_forms.items():
            related_model = form.model             # The related model to save
            field_name = form.field_name                    # Get the field name in model that this relation relates to  
            relation = getattr(model, field_name, None)     # Get the field itself (which is a relation)
    
            mon = model._meta.object_name                   # Model Object Name
            rmon = related_model._meta.object_name          # Related Model Object Name
            assert rmon == name, "Programming error: related forms should be filed under their related model's name."

            log.debug(f"{self.dp} {mon} has {len(form.formset.forms)} {rmon}s in the submission.")
            if relation.field.editable and can_save_related_formsets(model, related_model):
                if form.formset.is_valid():
                    ran = relation.rel.related_name         # Related Attribute Name
                    rfn = relation.field.name               # Related model field name
                    
                    log.debug(f"{self.dp}\tFormset submission is valid. Saving it ...")
                    
                    if (settings.DEBUG):
                        robjs_before = len(getattr(db_object, ran).all())
                        log.debug(f"{self.dp}\t\t{mon} {db_object.pk}: Checking parent before save: {ran}={robjs_before}")
                        
                    instances = form.formset.save()
                    
                    # Debugging output
                    if (settings.DEBUG):
                        robjs_after = len(getattr(db_object, ran).all())
                        log.debug(f"{self.dp}\t\t{mon} {db_object.pk}: checking parent after save: {ran}={robjs_after}")
    
                        if robjs_after > robjs_before:
                            log.debug(f"{self.dp}\t\t{mon} {db_object.pk}: added {robjs_after-robjs_before} {rmon}s")
                        elif robjs_after < robjs_before:
                            log.debug(f"{self.dp}\t\t{mon} {db_object.pk}: removed {robjs_after-robjs_before} {rmon}s")

                        if (len(instances) == 0):
                            log.debug(f"{self.dp}\t\t{mon} {db_object.pk}: did not save any {rmon}s")
                        else:
                            for instance in instances:
                                parent = getattr(instance, relation.field.name, None)
                                if (not parent is None):                    
                                    log.debug(f"{self.dp}\t\t{mon} {db_object.pk}: saved {rmon}={instance}. It has {rfn}={parent.pk}")
                                    log.debug(f"{self.dp}\t\t{mon} {db_object.pk}: checking parent {ran}={getattr(parent, ran).all()}")
                    
                    # Drill down the relations
                    for instance in instances:
                        self._save(instance, related_forms[instance._meta.object_name].related_forms)
                else:
                    # TODO: Report errors cleanly on new edit form
                    # Errors are in related_formset.errors
                    raise ValidationError(f"Form errors: {form.formset.errors}")

            elif not relation.field.editable:
                # This is just a warning because it's a perfectly fine  in some use cases. For 
                # example if you want to have the form available for display but don't want 
                # to save it. It has to be an editable relation to include the form. But when
                # saving of course, we can't.
                log.warning(f"Could not save related formset: {relation.field.name} was specified in {mon} in the add_related property, but {rmon} cannot be saved in inline formsets (as {relation.field.name} is not an editable field)")
            else:
                log.warning(f"Could not save related formset: {relation.field.name} was specified in {mon} in the add_related property, but {rmon} cannot be saved in inline formsets (for lack of a Foreign Key back to {mon})")

        self.__model_history.pop()

    def get_form_fields(self, model):
        '''
        Return a dictionary of fields in a model to be used in form construction and management.
         
        The dictionary is in keyed on the field name with the field as a value.
        
        This is the standard Django fields_for_model but forces inclusion
        of any fields specfied in the add_related attribute of a model and 
        it's PK   
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

    def log_debug_tree(self):
        self._debug_tree(log_tree=True)

    def print_debug_tree(self):
        self._debug_tree(log_tree=False)
        
    def _debug_tree(self, log_tree, related_forms=None, depth=0):
        if not related_forms: related_forms = self
        pfx = "\t" * depth
        
        def output(message):
            if log_tree:
                log.debug(message)
            else:
                print(message)
        
        for rf in related_forms:
            generic_form = related_forms[rf]
            output(f"{pfx}Related Form {rf}:")
            
            field_name = generic_form.field_name
            output(f"{pfx}\t{field_name=}")
            
            output(f"{pfx}\tfield_data:")
            for name, value in generic_form.field_data.items():
                output(f"{pfx}\t\t{name} = {value}")

            if getattr(generic_form, "management_form", None):
                output(f"{pfx}\tManagement Form: {generic_form.management_form}")
            
            if getattr(generic_form, "instance_forms", None):
                output(f"{pfx}\tinstance_forms:")
                for pk, form in generic_form    .instance_forms.items():
                    output(f"{pfx}\t\t{pk}:{form.initial}")

            if getattr(generic_form, "related_forms", None):
                output(f"{pfx}\trelated_forms:")
                for model, form in generic_form.related_forms.items():
                    output(f"{pfx}\t\t{model}:{form.initial}")
            
            if getattr(generic_form, "related_forms", None):
                self._debug_tree(log_tree, generic_form.related_forms, depth+1)
                    
            