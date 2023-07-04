![CoGs Logo](https://github.com/bernd-wechner/CoGs/blob/master/Leaderboards/static/img/logo.png?raw=true)
# CoGs Leaderboard Server

Aims to be a website that can manage TrueSkill based leaderboards for game players of any kind.

## Basics:
  * The CoGs webserver is written in python3 using the Django web framework.
  * I use the Eclipse IDE with PyDev ([LiClipse](https://www.liclipse.com/) bundles this too) and while there are plenty of other options I can recommend it because:
    * Pretty awesome visual debugging. Can set breakpoints and examine all internals.
    * Pretty nice code collapse and outline features in its editor
    * Platform independent (runs on Linux and Windows). In fact I started development on Windows and moved to Linux.
    * Supports inline task management TODO comments appearing as tasks in a task list. I love that.
    * It's free, free, free, not freemium - no features you'll run into that suddenly throw up a paywall.
    * Which is all I'm after really ;-).
  * This is a very incomplete project with much learning going on. Contributions are welcome.
  * I wrote a  generic django extensions module (django-rich-views) that needs tidy up and documentation as time permits:
    * Django had awesome generic forms, but total lack of generic detail views I wanted some for easy generic display of individual records
    * Django does not supply in the context, any information on related objects. I implemented a system for doing that - for the Session form in particular, introducing the idea of a rich object, one that only makes sense as a small family of related objects. Here, the Session is such an object, it only makes sense along with Game, Location, Rank and Performance objects and Player  possibly Team objects as well. A session has no real meaning outside of this little family of objects for a single game Session.
    * Once it's tidy and well documented it could be a community contrib to Django I suspect.

## How to build a site like CoGs

Great site describes it here:

​	http://www.htmlgoodies.com/beyond/reference/create-a-django-python-project-with-pydev.html

But read that only if you get stuck I guess following the steps below. I've tried to be complete
but it can be improved with each new effort. So if you're starting out, note anything that you
would improve below, and improve it - or ask me to!

### How to build the CoGs site

1. Install git. You'll need git to clone this repo/

  `sudo apt install git`

2. Install postgresql

    `sudo apt install postgresql libpq-dev`

    pgadmin is a little harder. A useful tool for administering postgresql, I wouldn't be without it. But to install it visit:
    https://www.pgadmin.org/download/

    You'll want to test that you can connect to the postgresql server in any case, and try:

    `psql -U postgres`

    which probably won't work. `postgres` is the default database user name, but I've typically found peer authorisation in effect meaning only the `postgres` system user can log in as the `postgres` database user. On Debian derived systems (Ubuntu, Mint etc) you can see this by trying:

    `sudo -u postgres psql`

    which should work. But you can make the first version work too by changing `peer` to `trust` in `/etc/postgresql/vv/main/pg_hba.conf`(where `vv` is the postgresql version, 14 at time of writing and hba is short for Host Based Authentication) where this line defines the security locally:

    `local   all             postgres                                peer`

    just change `peer` to `trust` and you won't need `sudo` to connect with psql. You will need to restart postgres before any change takes effect though which on a systemd bases system something like `sudo service postgresql restart`.

    pgadmin4 should also be able to connect then, and it's worth testing that if you want to use that. If anything fails there is a lot of documentation in the `pg_hba.conf`file and Google, Stack Overflow and now ChatGPT are your friends.

3. Install needed dependencies, in a [venv](https://docs.python.org/3/library/venv.html) ideally. What follows is a Linux based approach (Windows will be different and if someone wants to write up a Windows set of steps please do) and makes two key assumption you need to modify as you desire:

    1. That you want to store you venvs in `~/.venvs`. A totally arbitrary subsumption to illustrate the steps and just where I happen to keep mine. You can keep yours wherever you like, just replace `~/.venvs` with a directory you want to home for your venvs.
    2. That you house your development projects in `~/workspace`. Again, you can keep them wherever you like, bust just substitute `~/workspace` with the directory you choose to call home for your development projects.

    ```bash
    # Get the basic together
    sudo apt install python3 python3-pip python3-venv python3-dev
    
    # Create an activate a venv
    mkdir ~/.venvs # if necessary
    python3 -m venv ~/.venvs/CoGs
    source ~/.venvs/CoGs/bin/activate
    
    # Prep the venv for use
    pip install --upgrade pip
    pip install wheel
    
    # Get the CoGs code base (because we need requirements.txt which describes the Pyhton packages we'll need)
    mkdir ~/workspace # if necessary
    cd ~/workspace
    git clone https://github.com/bernd-wechner/CoGs.git # Or Fork on GitHub first and clone your repo (better)
    
    # Install the requirements
    pip install -r requirements.txt
    ```


4. Install Eclipse and Pydev

   Recommend avoiding the ubuntu package and just going straight to
   https://www.eclipse.org
   and get the latest Eclipse from there.

   Then install PyDev from within Eclipse by adding these repositories:
   pydev - http://pydev.org/updates
   Django Template Editor - http://eclipse.kacprzak.org/updates

   I had enormous troubles getting PyDev to work from the ubuntu repositories
   and the PyDev support guys suggested the above which worked a breeze.

   Then if you've used a venv (as suggested) configure an interpreter for use. In Eclipse:

       1. **Window > Preferences > PyDev > Interpreters > Python Interpreters**
       1. **New > Browse for python/pypy exe**
       1. Browse to your venv python instance. For example: `~/.venvs/CoGs/bin/python`
       1. Give it name under **Interpreter Name**. I typically use "CoGs Venv" for example.

   Now load the project in Eclipse:

   1. Work out where you want it to live. On a Linux system I'd recommend `~/workspace` (if in 1. above you set one up use that)
   2. If you didn't already (in step 1. above) fetch it from github with:
      `git clone https://github.com/bernd-wechner/CoGs.git`
      (or fork on github and clone your repo which is generally better) and
   3. Open the Eclipse project file in Eclipse:

      1. **File > Open Projects from File System**
      2. Click **Directory** and navigate to the cloned repo (nominally `~/workspace/CoGs`)
   4. If you have a CoGs project in Eclipse now, try debugging a server run quickly:

      1. Right-click on the project **> Properties > PyDev - Interpreter/Grammar**. Select the Interpreter you created ("CoGs Venv" above). 

      2. Right-click on the project > **Debug As > PyDev: Django**

      3. If all is well you'll see on the Console the development server start up and end with something like this:
         ```
         Django version 4.2.3, using settings 'Site.settings'
         Starting development server at http://127.0.0.1:8000/
         Quit the server with CONTROL-C.
         ```

5. Seed your database

   Firs we need a user and database.

   * check `Site/settings.py` the `DATABASES` will reveal the configure username and password and the database name. Change those, or at least the password if you like, then create that user in postgresql.
   * Use pgAdmin4 to create role (that's the username) and make sure it has Login  rights and you set the password and create an empty database owned by that user.
   * Alternately on the command line:
     * Open SQL prompt with `psql -U postgres`
       * then at the prompt: `CREATE ROLE "CoGs" LOGIN PASSWORD 'password'; CREATE DATABASE "CoGs";`
       * Postgres is fussy here, it demands single quotes around the password and if case is to be preserved, double quotes around the role (user name) and the database name.

   * to test logging in try `psql -U CoGs` that should now prompt for the password and let you.
   * Now we need to apply the migrations, that is define the tables in the database. Django does that for us but we have to ask it to: `python manage.py migrate` should work and let you know all is good. If not, time to work out why I guess.

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

6. Try it out
   1. Open the CoGs project in Eclipse

   2. Right click the project then click `Debug As...` then `PyDev: Django`

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
