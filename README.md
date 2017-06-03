![alt text][logo]
# CoGs Leaderboard Server

Aims to be a website that can manage TrueSkill based leaderboards for game players of any kind.

##Basics:
  * The CoGs webserver is written in python3 using the django web framework.
  * I use the Eclipse IDE with PyDev and while there are plenty of othe options I can recomment it because:
    * Pretty awesome visul debugging. Can set breakpoints and examine all internals.
    * Pretty nice code collapse and outline features in its editor
    * Platform independent (runs no Linux and Windows) In fact Is tarted dev on Windows and moved to Linux. 
    * Supports inline task management TODO comments appearing as tasks in a task list. I love that. 
    * Which is all I'm after really ;-).
  * This a very incomplete project with much learning going on. Contributions welcome.
  * I wrote a  generic django extensions module that need tidy up and documentation as time permits:
    * Django had awesome generic forms, but total lack of generic detail views I wanted some for easy generic display of indivudal records
    * Django does not supply in the context any informationon related objects. I implemented a system for doing that - for the Session form.
    * Once it's tidy and well documented it could be a community contrib to Django
 
##How to build a site like CoGs

Great site describes it here:

http://www.htmlgoodies.com/beyond/reference/create-a-django-python-project-with-pydev.html

But read that only if you get stuck I guess follwing the steps below. I've tried to be complete 
but it can be improved with each new effort. So if you're stating out, note anything that you 
could improve below, and improve it!

##How to build the CoGs site

1. Install needed dependencies:

    ```
    sudo apt-get install postgresql pgadmin3
    sudo apt-get install python3 python3-django python3-psycopg2 python3-yaml 
    sudo apt-get install git
    sudo -H pip3 install trueskill django-debug-toolbar django-url-filter django-intenumfield django-autocomplete-light titlecase 
    ```
		
2. Install Eclipse and Pydev

   Recommend avoiding the ubuntu package and just going straight to 
	https://www.eclipse.org 
   and get the latest Eclipse from there. 

   Then install PyDev from within Eclipse by adding these repositories:   	
	pydev - http://pydev.org/updates
	Django Template Editor - http://eclipse.kacprzak.org/updates

   I had enormous troubles getting PyDev to work from the ubuntu repositories 
   and the PyDev support guys suggested the above which worked a breeze.

   Now load the project in Eclipse:<br>
     i. Work out where you want it to live. On a Linux system recommend ~/workspace<br>
     ii. Fetch it from github with: git clone https://github.com/bernd-wechner/CoGs.git<br>
     iii. Open the Eclipse project file in Eclipse **(Work out how to do that and update this!)**<br>

   If you want to start from scratch and get the cleanest of clean projects, I did this once after a major overaul:<br>
      i. Create a new Pydev Django Project in Eclipse (CoGs)<br>
      ii. Create a new Django App in Eclipse (Leaderboards)<br>
      iii. Find the CoGs code and copy individual files as needed into these projects which includes but is not limited to:<br>
          * CoGs/settings.py<br>
     	  * CoGs/urls.py<br>
     	  * CoGs/wsgi.py<br>
     	  * Leaderboards/models.py<br>
     	  * Leaderboards/views.py<br>
     	  * Leaderboards/admin.py<br>
     	  * Essentially if you're copying like this you want to understand each file as you go and what its role is.<br>
     	  * Django documentation is real cool there.<br>
    
3. Seed your database
	
   I want to find a way to do this in a simple command but in the mean time.

   Database tips:
     * In pgAdminIII a user is called a Role.
     * Create a new Role "CoGs"  (i.e. a login).
     * Make sure you can log into the database. That is edit the file:
	`/var/lib/pgsql/data/pg_hba.conf`

       And make sure the connection METHOD for local is "md5" not "peer".
	
       Peer authentication will mean you're always trying to login with your account name, 
       but CoGs uses the CoGs user, and you want to be able to log in as the CoGs user by 
       providing a username and password.
		
       Restart the postgresql server after editing it with:
	`service postgresql restart`

    Export data was done with:
	```
	python3 manage.py dumpdata --format xml --indent 4 > data.xml
	python3 manage.py dumpdata --format json --indent 4 > data.json
	python3 manage.py dumpdata --format yaml --indent 4 > data.yaml
	```
   Just to get all possible formats for the heck of it. Only need one. 

   Import data is then done with:
	```
	python3 manage.py loaddata <file>
	
	where <file> is one of the three files I dumped with dumpdata. 
	```

   That should see you with a seeded database.

4. Try it out

  1. Open the CoGs project in Eclips
  2. Right click the project then click "Debug As..." the "PyDev: Django". 
  3. In your Console panel you should see something like:
  	```
	Performing system checks...

	System check identified no issues (0 silenced).
	December 05, 2016 - 11:52:55
	Django version 1.10.1, using settings 'CoGs.settings'
	Starting development server at http://127.0.0.1:8000/
	Quit the server with CONTROL-C.
	```
  4. In your favourite web browser open http://127.0.0.1:8000/ and play around.

Now dive in ...

## Some Database documentation tips

Two tools I've used:

**postgresql_autodoc**

	sudo apt install postgresql-autodoc
	postgresql_autodoc -d CoGs -u CoGs --password=ManyTeeth

Had login problems and had to fix var/lib/pgsql/data/pg_hba.conf making local connections use md5 connection method.

This produces CoGs.dia and Cogs.dot which you need dia to view:

	sudo apt install dia
	sudo apt install xdot	
	
Alas the dia file seems to have all tables coincident though neatly moverable yet I can't find a cool layout option.
The dot file is well laid out. Butit proves to be large and so schemaSpy produces a more navigable result.

**schemaSpy**
downloaded schemaSpy from: https://sourceforge.net/projects/schemaspy/
Installed the file:

	mv schemaSpy_5.0.0.jar ~/bin/schemaSpy
	chmod +x ~/bin/schemaSpy
	
downloaded the Java postgresql driver from: https://jdbc.postgresql.org/download.html

Installed the file:

	sudo mv postgresql-9.4.1211.jar /usr/share/java

ran schemaSpy in my Doc folder:

	schemaSpy -t pgsql -cp /usr/share/java/postgresql-9.4.1211.jar -host localhost -db CoGs -s public -u CoGs -p ManyTeeth -o .
		
Produces a rich documentation site under index.html including a better schema diagram, but you cna't move things around, it's well layed out but fixed in place.

You can click on any table and get a cool relative view though. And if you install xdot can view the .dot files.

[logo]: https://github.com/bernd-wechner/CoGs/blob/master/Leaderboards/static/CoGS%20Logo%20WebEmail.png "CoGs Logo"
