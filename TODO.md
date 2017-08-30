#TODOs

A simple place to store the next TODOs worth tackling.

## The top usability priorities for month to month use of the site at present

1. Fix the time issue zone issue. When entering sessions I want to pick local time and have it recorded as UTC and reported as local time.
	Methinks the client side must submit it with a post or get to the server side and the serv then interpret the submitted time in that timezone

2. Need to fix the Session form to allow moving between individual and team play sensibly. Using a logged Inkognito session as a test.

3. Need to make the saves atomic, in django-generic-view-extensions

4. Need to use django-autocomplete-light widgets for player and other drop down selectors. Alas some reading and learning to do there.
	Point is though that player lists can get large and we need a combo box with search features. django-autocomplete-light is such a one.

5. I implemented check_integrity on various models using assertions. Migrate this to system checks:
	https://docs.djangoproject.com/en/1.10/topics/checks/

6. Add graphs! yes, for a game and a list of players, plot the timeline of skills or leaderboard positions! See:
	http://www.flotcharts.org/flot/examples/

## The top needs before the site can be used by anyone else (i.e. not in debug mode locally)

1. User management. Need to map Players to auth users, and support accounts.
All users should be able to have an account, but admins and registrars need one.
Admins and registrars need on for security (data entry and editing)
Players can have one to support default filter configs. That is if the
site kows who you are, it knows what leagues you're in and can render most views
in your preferred league.
Key things to read:
* https://docs.djangoproject.com/en/1.8/topics/auth/default/

2. Add security to create and edit views. Only authorised users. Could be added to the generic extensions,
responding to a site setting?
- This is half done. A provisional effort in place. Needs some tidying.

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

Or Look at using natural keys:
	https://docs.djangoproject.com/en/1.10/topics/serialization/#topics-serialization-natural-keys
	We could use this to create fixtures with no PKs and hence will load in a clean DB with sequences from 1 again

## Longer term ideals

1. Consider implementing Bootstrap as a UI (platform portable UI)
2. Examine Django REST framework and consider using it. Good for App development
