#TODOs

A simple place to store the next TODOs worth tackling. 

## The top usability priorities for month to month use of the site at present

1. Add filters to the Leaderboard view. Want to be able to show Leaderboards for a given player, league or changed since date.
2. Fix the time issue zone issue. When entering sessions Iw ant to pick local time and have it recorded as UTC and reported as local time. 
3. Need to fix the Session form to allo moving between individual and team play sensibly. Using a logged Inkognito session as a test.
4. Need to make the saves atomic, in django-generic-view-extensions

## The top needs before the site can be used by anyone else (i.e. not in debug mode locally)

1. User management. Need to map Players to auth users, and support accounts. 
All users should be able to have an account, but admins and registrars need one.
Admins and registrars need on for security (data entry and editing)
Players can have one to support default filter configs. That is if the 
site kows who you are, it knows what leagues you're in and can render most views 
in your preferred league.
Key things to read:
* https://docs.djangoproject.com/en/1.8/topics/auth/default/

2. Add security to create and edit views. Only authorised users. Coul be added tot he generic extensions, 
responding to a site setting?

3. Add a testing suite. Rigorous unit testing so that we can make changes to the code into future and feel 
confident no part of the site has been broken.  
Key things to read: 
* https://docs.djangoproject.com/en/1.8/topics/testing/
* http://django-testing-docs.readthedocs.io/en/latest/fixtures.html
* http://farmdev.com/projects/fixture/
* manage.py test
* manage.py testserver

4. Reset all sql sequences to 1 for production.
The current dumped data has pks starting higher, and would like if and when we go into real service to have pks starting at 1!
Read: 
* https://docs.djangoproject.com/en/1.10/howto/initial-data/
* https://docs.djangoproject.com/en/1.10/ref/django-admin/#sqlsequencereset
