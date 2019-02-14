# Known Bugs

1) Timezone handling

Almost done here!

Just want to add smart rendering now.

The new databasae fields reveal the timezone that was active when the datetime was saved. 
And thus support smart rendering, namely when the active timezone during display is same as
the timezone active when saved, don't show timezone information in printed date_times.
But if it differs, consider including it, but perhaps as a TZ name, not as a UTC offset. 
So we'd see the TZ names if they were different.
Alternately a nice idea might be to activate for the reader the timezone it was written with, and
report the times without timezone. We then see the localtime of the session or the save recorded 
which is what most interests us. 
But we may need to see TZ in names sometimes so perhaps this is the first time we also need a config option for timezones. So on List and Detail views a TZ option listing:

	Show Local times
	Show Local times with UTC offset
	Show Local times with Timezone	
	Show UTC time
	Show <Timezone> time
	
Local times are in the timezone of the stored datetime.
<Tiemzone> is the Session timezone in effect and the option should be populated.  

and the choice can be made on the page.

This will affect Delete views too as they show a Detail view to confirm. Check.

Also on Add and Edit views we need to ensure the box can accept naive times (which will take the local timezone) or explicit times.

We may also want to record against each venue, a timezone. And an integrity check on sessions is that 
the recorded session time should always be in the timezone of the sessions venue. 


2) Datetimes stored in the database are wonky but fixable.
	To fix best in python with a fixing view. 
	For every date time, we need to remove the TZoffset from it and save.
	Need to experiment. In PGadmin4, where I see this:
		2018-12-09 10:59:00+11
	I should see this:
		2018-12-08 23:59:00+11
	And we should be rendering it it (after 1 above is fixed) as: 
		2018-12-08 23:59:00
	sometimes. The criterion shoould be sort of like this:
		if the database stored the time with a timezone that is the current time zone, just
		don't display the timezone (it's kind of distracting and yawny).
		if the timezone it was saved in is different. Then display the timezone info.
		But we havea problem with daylight saving as the timezone offset changes! So these
		tests need to be done on the timezone (by its name, not its offset) then it should work.
		Should all be well tested.
		
	We should copy all live date onto the test site to do this work, and test everything.
	Only if happy we should then copy the data back to the live site!
	

	