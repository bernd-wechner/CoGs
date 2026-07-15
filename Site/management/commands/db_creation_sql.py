from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    help = 'Generates SQL to create roles and databases for Postgres'

    def handle(self, *args, **options):
        configs = getattr(settings, 'DATABASES', {})
        self.stdout.write("-- SQL for creating roles and databases\n")
        
        configs_seen = []
        
        for key, config in reversed(configs.items()):
            if config not in configs_seen:
                host = config['HOST']
                port = config['PORT']
                admin = 'postgres'
                db_name = config['NAME']
                user = config['USER']
                password = config['PASSWORD']

                
                self.stdout.write(f"\n-- SQL for {key.upper()} database")
                self.stdout.write(f"-- Open a SQL prompt with (assuming your admin user is '{admin}'):")
                self.stdout.write(f"--       psql -h {host} -p {port} -U {admin}")
                self.stdout.write(f"-- and copy these commands:")
                
                                
                self.stdout.write(f'CREATE ROLE "{user}" WITH LOGIN PASSWORD \'{password}\';')
                self.stdout.write(f'CREATE DATABASE "{db_name}" OWNER "{user}";')
                self.stdout.write(f'GRANT ALL PRIVILEGES ON DATABASE "{db_name}" TO "{user}";')                
                
                self.stdout.write(f"-- To connect and verify, run:")
                self.stdout.write(f"--       psql -h {host} -p {port} -U {user} -d {db_name}")
                
                configs_seen.append(config)

        self.stdout.write("\n-- After creating the databases create the schema using:")
        self.stdout.write("--      python manage.py showmigrations  # to review pending migrations.")
        self.stdout.write("--      python manage.py migrate         # to create the schema.")
