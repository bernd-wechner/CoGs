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
* VS Code and VS Codium have made strong impact in this IDEA space too and are worth considering. I use VS Code a lot in other contexts. 
* This is a very incomplete project with much learning going on. Contributions are welcome.
* I wrote a  generic django extensions module (django-rich-views) that needs tidy up and documentation as time permits:
  * Django had awesome generic forms, but total lack of generic detail views I wanted some for easy generic display of individual records
  * Django does not supply in the context, any information on related objects. I implemented a system for doing that - for the Session form in particular, introducing the idea of a rich object, one that only makes sense as a small family of related objects. Here, the Session is such an object, it only makes sense along with Game, Location, Rank and Performance objects and Player  possibly Team objects as well. A session has no real meaning outside of this little family of objects for a single game Session.
  * Once it's tidy and well documented it could be a community contrib to Django I suspect.

## How to build a site like CoGs

Great site describes it here:

​    http://www.htmlgoodies.com/beyond/reference/create-a-django-python-project-with-pydev.html

But read that only if you get stuck I guess following the steps below. I've tried to be complete
but it can be improved with each new effort. So if you're starting out, note anything that you
would improve below, and improve it - or ask me to!

### How to build the CoGs site

1. Install git. You'll need git to clone this repo/

   `sudo apt install git`

2. Install and configure postgresql

    `sudo apt install postgresql libpq-dev`

    pgadmin is a little harder. A useful tool for administering postgresql, I wouldn't be without it. But to install it visit:
    https://www.pgadmin.org/download/

    You'll want to test that you can connect to the postgresql server in any case, and try:

    `psql -U postgres`

    which probably won't work. `postgres` is the default database user name, but I've typically found peer authorisation in effect meaning only the `postgres` system user can log in as the `postgres` database user. On Debian derived systems (Ubuntu, Mint etc) you can see this by trying:

    `sudo -u postgres psql`

    which might work. But you can make the first version work too by changing `peer` to `trust` in `/etc/postgresql/vv/main/pg_hba.conf`(where `vv` is the postgresql version, 18 last time these notes were looked at and hba is short for **Host Based Authentication**) where this line defines the security locally:

    `local   all             postgres                                peer`

    just change `peer` to `trust` and you won't need `sudo` to connect with psql. You will need to restart postgres before any change takes effect though which on a systemd bases system something like `sudo service postgresql restart`.

    `pgadmin4` should also be able to connect then, and it's worth testing that if you want to use that. If anything fails there is a lot of documentation in the `pg_hba.conf`file and Google and now any online AI (multplying like rabbits) are your friends.

    Once you've connected successfully

3. Get the source and install needed dependencies, in a [venv](https://docs.python.org/3/library/venv.html) ideally. What follows is a Linux based approach (Windows will be different and if someone wants to write up a Windows set of steps please do) and makes two key assumption you need to modify as you desire:

   1. That you'll like `uv` as much as I do. It's Python package manager that just beats pip hands down. Ironically you'll need pip to install it. Main advantages I find with uv is it hands conflicts so much better and can builds venvs on any version of Python. 

   2. That you want to store your venv in in the worksapce. I've moved to dong that. Not in the git repo, but the workspace.   

   3. That you house your development projects in `~/workspace`. You can keep them wherever you like, bust just substitute `~/workspace` with the directory you choose to call home for your development projects.

   ```bash
   # Get the basic together
   sudo apt install python3 python3-pip python3-venv python3-dev
   
   # Install uv
   # See: https://github.com/astral-sh/uv 
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Create the workspace
   mkdir -p ~/workspace/CoGs
   cd ~/workspace/CoGs
   
   # Create an activate a venv
   uv venv
   
   # Activate the venv
   source .venv/bin/activate
   
   # Your prompt shoudl be prefixed by the venv name now and you can check for 
   env | grep VIRTUAL_ENV
   
   # Get the source (which defines the python requirements)
   git clone https://github.com/bernd-wechner/CoGs.git Source/develop
   # OR fork it on github and clone your fork. 
   
   # Your git repo is now Source/develop and you can just check status there
   cd Source/develop
   git status			# for quck status
   git remote -v		# To list the remote
   git pull            # Will fetch any updates from the remote repo 
   
   # The default branch is master currently which reflext what is live
   # Development happens on the develp branch so:
   git checkout develop
   
   # Install the requirements
   uv pip install -r requirements.txt
   
   # Try it out
   python manage.py
   
   # If that runs and shows you management hekp you're on a good wicket!
   # This would be even better if it runs:
   # If this doesn't work, fret not, park it for now and move on to
   # Seed your database below
   python manage.py runserver
   
   # It may not do that until you check the database connection.
   # Also of course if this doesn't work skip it for now and move
   # on to Seed your database below
   python manage.py dbshell
   
   # If it fails check the DATABASE settings in .env (which is loaded by Sy Site/settings.py)
   ```

4. Seed your database

    You'll need a user and database for the site to run.

    * The database connection parameters live in a `.env` file which is not hosted on github. I  fact they forced this in 2026 refusing any push that they think looks like it includes passwords or keys. There an `example.env` that illustrates the format. Copy that to .env and add passwords that you wand and make sure the host and port and such are right. 
      * Once you've created `.env` try `python manage.py dbshell` and if you get a prompt you can try `/l` which lists databases. 
      * Note that the `.env` file is loaded by `Site/settings.py` and the variables used in defining the `DATABASES` settings
      * There's also a utility  in the `Scripts` folder: `db_load` which reads that very `.env` as well and you can use it to ensure you have a database with:
        `Scripts/db_load -RM`
        - `-R` for reset (created an empty database)
        - `-M` for migrate (create all the tables needed in that database)
      * If this doesn't work back to database *Install and configure postgresql* above ;-)
    * Using pgAdmin4 you can check the database, the role, and permissions and all.

    Once that's all working you can inject data. Given live data is not in the repo you'll need to drop us a line and we'll share some with trusted partners only (as it invariably contains player data mostly names and emails for example and isn't public). 

    There are two options:

    1. Old fixtures

       Django provide a dumpdata and loaddata command pair for sharing data. We last used this many years ago and captured data in three formats:

       ```
          python3 manage.py dumpdata --format xml --indent 4 > data.xml
          python3 manage.py dumpdata --format json --indent 4 > data.json
          python3 manage.py dumpdata --format yaml --indent 4 > data.yaml
       ```

       Just to get all possible formats for the heck of it. You'd only need one.

       Import data is then normally done with:

       ```
          python3 manage.py loaddata <file>
       ```

       **BUT:** it turns out Django's dumpdata is a bit weird and includes a Django maintained model ContentType that created load issues. We wrote a wrapper that filters that out of the dump and loads the data successfully:

       ```
          Scripts/load_fixture <file>
       ```

       That should see you with a seeded database.

    2. Full database 

       This is in fact better as it will include and PostgreSQL extensions that models may rely on.

       We wrote some helpers to make this easier:

       ```
       Scripts/db_dump <database>
       ```

       Will create a dump that can be shared and:

       ```
       Scripts/db_load <file>
       ```

       Will load that file. Should work slickly. But if there are any issues I'll guess we'll fix 'em!'

5. Install memcached

    If you look in Site/settings.py at the CACHES settings, we use  memcached to help speed Django up a little. It's not really needed for development, and so it should fall back onto a default, or you can install memcached in the dev environment as I did so I can test it and that it works fine.  On Ubuntu derived systems that's as easy as:

    `sudo apt install memcached`

    But if you're on another system go straight to horses mouth for more info:

    https://memcached.org/

    And then configure it to use a unix socket by adding this to `/etc/memcached.conf` (or your systems config file for memcached):
    ```conf
    # Use a unix socket (rather than an IP connection)
    -s /run/memcached/socket
    -a 0770
    ```

    It uses the IP layer by default and sockets are a little more native and performant that the IP layer. 

    then restart memcached, again on Ubuntu related systems:

    `sudo service memcached restart`

    And check that you're in the `mecache` group or you won't have access to the mode 770 socket. But to me sure:

    `sudo usermod -aG memcache yourusername`

    Then sadly you have to log out and in again for it to stick.

6. Install Eclipse and Pydev

    Recommend avoiding the ubuntu package and just going straight to https://www.eclipse.org
    and get the latest Eclipse from there.

    Then install PyDev from within Eclipse by adding these repositories:

    1. **Help > Eclipse Marketplace...**
    2. Find: PyDev
    3. Click **Install**

    There a Django Templates editor which is handy for editing templates:

    - https://github.com/bernd-wechner/django-template-editor

    Then if you've used a venv (as suggested) configure an interpreter for use. In Eclipse:

    1. **Window > Preferences > PyDev > Interpreters > Python Interpreters**
    1. **New > Browse for python/pypy exe**
    1. Browse to your venv python instance. For example: `~/workspace/CoGs/.venv/bin/python`
    1. Give it name under **Interpreter Name**. I typically use "CoGs Venv" for example.

    Now load the project in Eclipse:

    1. Work out where you want it to live. On a Linux system I'd recommend `~/workspace` (if in 1. above you set one up use that)

    2. If you didn't already (in step 1. above) fetch it from github with:
       `git clone https://github.com/bernd-wechner/CoGs.git`
       (or fork on github and clone your repo which is generally better)

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

7. Try it out

8. Open the CoGs project in Eclipse

9. Right click the project then click `Debug As...` then `PyDev: Django`

10. In your Console panel you should see something like:

   ```
   Performing system checks...
   
   System check identified no issues (0 silenced).
   December 05, 2016 - 11:52:55
    Django version 1.10.1, using settings 'CoGs.settings'
   Starting development server at http://127.0.0.1:8000/
   Quit the server with CONTROL-C.
   
   ```

11. In your favourite web browser open http://127.0.0.1:8000/ and play around.

Now dive in ...

## Some Database documentation tips

Two tools I've used:

### postgresql_autodoc

```
 sudo apt install postgresql-autodoc
 postgresql_autodoc -d CoGs -u CoGs --password=thepass
```

Had login problems and had to fix `var/lib/pgsql/data/pg_hba.conf` making local connections use md5 connection method.

This produces `CoGs.dia` and Cogs.dot which you need dia to view:

```
sudo apt install dia
sudo apt install xdot
```

Alas the dia file seems to have all tables coincident though neatly moverable yet I can't find a cool layout option.

The dot file is well laid out. Butit proves to be large and so schemaSpy produces a more navigable result.

### schemaSpy
downloaded schemaSpy from: https://sourceforge.net/projects/schemaspy/
Installed the file:

```bash
mv schemaSpy_5.0.0.jar ~/bin/schemaSpy
chmod +x ~/bin/schemaSpy
```

downloaded the Java postgresql driver from: https://jdbc.postgresql.org/download.html

Installed the file:

```bash
sudo mv postgresql-9.4.1211.jar /usr/share/java
```

ran schemaSpy in my Doc folder:

```bash
schemaSpy -t pgsql -cp /usr/share/java/postgresql-9.4.1211.jar -host localhost -db CoGs -s public -u CoGs -p thepass -o .
```

Produces a rich documentation site under `index.html` including a better schema diagram, but you can't move things around, it's well laid out but fixed in place.

You can click on any table and get a cool relative view though. And if you install xdot can view the .dot files.
