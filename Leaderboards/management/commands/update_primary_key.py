# -*- coding: utf-8 -*-
# code is in the public domain
#
# Based on:
#     https://djangosnippets.org/snippets/2915/
# Updated to work with Django 1.11
#
# Place this file in:
#     myapp/management/commands/update_primary_key.py
#
# and it should then be available as:
# 
# ./manage.py update_primary_key table_name column_name value_old value_new
u'''

Management command to update a primary key and update all child-tables with a foreign key to this table.

Does use django's db introspection feature. Tables don't need to have django ORM models.

Usage: manage.py update_primary_key table_name column_name value_old value_new
'''
import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.transaction import atomic

table_list=None
def get_table_list(cursor):
    global table_list
    if not table_list:
        table_list=connection.introspection.table_names(cursor)
    return table_list

relations={} # Cache
def get_relations(cursor, table_name):
    rels=relations.get(table_name)
    if rels is None:
        rels=connection.introspection.get_relations(cursor, table_name)
        relations[table_name]=rels
    return rels

def get_back_relations(cursor, table_name):
    backs=[]
    relations_back={}
    for ref_table in get_table_list(cursor):
        ref_relations=get_relations(cursor, ref_table)
        for ref_col_idx, ref_relation in ref_relations.items():
            to_col=ref_relation[0]
            to_table=ref_relation[1]
            if to_table!=table_name:
                continue
            # Found a reference to table_name
            backs=relations_back.get(to_col)
            if not backs:
                backs=[]
                relations_back[to_col]=backs
            backs.append((ref_col_idx, ref_table))
    return (backs, relations_back)

def update_db(cursor, table_name, col, value_old, value_new):
    relations = connection.introspection.get_relations(cursor, table_name)
    
    _, relations_back = get_back_relations(cursor, table_name)
    
    if col.name in relations_back:
        relations_all = relations_back[col.name]
        #Find if there are any relations for the relations themselves. 
        #This case is mainly to support model inheritance
        for rel in relations_back[col.name]:
            _, _relations_back = get_back_relations(cursor, rel[1])
            if rel[0] in _relations_back:
                relations_all += _relations_back[rel[0]]
    else:
        relations_all = []

    sql='select count(*) from "%s" where "%s" = %%s' % (table_name, col.name)
    cursor.execute(sql, [value_old])
    count=cursor.fetchone()[0]
    sql=sql % value_old
    if count==0:
        raise CommandError('No row found: %s' % sql)
    if count>1:
        raise CommandError('More than one row found???: %s' % sql)
    def execute(sql, args):
        logging.info(sql % tuple(args))
        cursor.execute(sql, args)
    execute('update "%s" set "%s" = %%s where "%s" = %%s' % (table_name, col.name, col.name), [value_new, value_old])
    for col_idx, ref_table in relations_all:
        cursor.execute('update "%s" set "%s" = %%s where "%s" = %%s' % (table_name, col.name, col.name), [value_new, value_old])
        ref_descr=connection.introspection.get_table_description(cursor, ref_table)
        
        for ref_col in ref_descr:
            if ref_col.name==col_idx:
                break
        else:
            raise CommandError('Column %r not in table %r' % (col.name, table_name))
        
        execute('update "%s" set "%s" = %%s where "%s" = %%s' % (ref_table, ref_col.name, ref_col.name), [value_new, value_old])

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('table_name')    
        parser.add_argument('value_old')    
        parser.add_argument('value_new')    
    
    @atomic
    def handle(self, *args, **options):
        rootLogger = logging.getLogger('')
        rootLogger.setLevel(logging.INFO)

        table_name=options['table_name']
        value_old=options['value_old']
        value_new=options['value_new']
        
        cursor=connection.cursor()
        descr=connection.introspection.get_table_description(cursor, table_name)
        
        # Find the Primary Key
        const=connection.introspection.get_constraints(cursor, table_name)
        
        pk_col=None
        for key in const:
            c=const[key]
            if c['primary_key']:
                if len(c['columns']) == 1:
                    pk_col=c['columns'][0]
                    break
                else:
                    raise CommandError('Primary Key in table %r consists of multiple columns.' % (table_name))                            
        else:
            raise CommandError('Table %r has no primary key.' % (table_name))       
        
        for col in descr:
            if col.name==pk_col:
                break
        else:
            raise CommandError('Column %r not in table %r' % (pk_col, table_name))

        update_db(cursor, table_name, col, value_old, value_new)

