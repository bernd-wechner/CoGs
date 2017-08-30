# -*- coding: utf-8 -*-
# code is in the public domain
#
# Based on:
#     https://djangosnippets.org/snippets/2915/
#
# Place this file in:
#     myapp/management/commands/compact_primary_key.py
#
# and it should then be available as:
# 
# ./manage.py compact_primary_keys table_name_re
#
# A regular expression is formed with ^table_name_re$
#
# So to compact all the tables in a typical app 'app_.*' would cover it.
#
# Back up your database before trying this ;-). 
u'''

Management command to update a compact primary keys on specified tables in an integral
way - meaning all relationships are updated too and data integrity is maintained.

Only works on tables where the primary key is one integer column. The point being to
adjust the keys so they run from 1 sequentially up.

This fills any gaps in the key space that may have crept in due to deletions or such.

Does use django's db introspection feature. Tables don't need to have django ORM models.

Usage: manage.py update_primary_key table_name column_name value_old value_new
'''
import logging
import re

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
    logging.info("Updating table %s, record %s becomes record %s (primary key is: %s)" % (table_name, value_old, value_new, col.name))
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

def get_val_list(cursor, col, table_name):
    sql='select %s from "%s"' % (col.name, table_name)
    cursor.execute(sql)
    result = [row[0] for row in cursor.fetchall()]
    return sorted(result)

def compact_table(cursor, table_name):
    descr=connection.introspection.get_table_description(cursor, table_name)
    const=connection.introspection.get_constraints(cursor, table_name)
    
    pk_col=None
    for key in const:
        c=const[key]
        if c['primary_key']:
            if len(c['columns']) == 1:
                pk_col=c['columns'][0]
                for col in descr:
                    if col.name==pk_col:
                        break
                else:
                    raise CommandError('Column %r not in table %r' % (pk_col, table_name))
                
                pk_type=connection.introspection.get_field_type(col.type_code, col)
                is_int = pk_type in ['IntegerField', 'AutoField', 'BigIntegerField', 'BigAutoField']
                
                if is_int:
                    break
                else:
                    raise CommandError('Primary Key in table %r is not an integer.' % (table_name))                            
            else:
                raise CommandError('Primary Key in table %r consists of multiple columns.' % (table_name))                            
    else:
        raise CommandError('Table %r has no primary key.' % (table_name))       
    
    for col in descr:
        if col.name==pk_col:
            break
    else:
        raise CommandError('Column %r not in table %r' % (pk_col, table_name))

    pks = get_val_list(cursor, col, table_name)
    
    for new_pk in range(1, len(pks)+1):
        if new_pk != pks[new_pk-1]:
            update_db(cursor, table_name, col, pks[new_pk-1], new_pk)
                
class Command(BaseCommand):
    args = 'table_name column_name value_old value_new'
    help = 'Update a primary key and update all child-tables with a foreign key to this table.'
    
    def add_arguments(self, parser):
        parser.add_argument('table_name_re')    
    
    @atomic
    def handle(self, *args, **options):
        rootLogger = logging.getLogger('')
        rootLogger.setLevel(logging.INFO)

        table_name_re = options['table_name_re']
        
        cursor=connection.cursor()
        
        all_tables = get_table_list(cursor)

        RE = re.compile(r'^' + table_name_re + r'$')
        
        tables = [t for t in all_tables if RE.match(t)]
        
        for table_name in tables:
            compact_table(cursor, table_name)
        


