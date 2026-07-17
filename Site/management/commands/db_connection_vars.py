from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    help = 'Generates bash code to set variables useful for a Database connection. This reads site settings, so reflects the sites expectations.'

    def handle(self, *args, **options):
        configs = getattr(settings, 'DATABASES', {})
        
        config = configs['default']
        
        host = config['HOST']
        port = config['PORT']
        db_name = config['NAME']
        user = config['USER']
        password = config['PASSWORD']

        self.stdout.write(f"DB_HOST={host}")
        self.stdout.write(f"DB_PORT={port}")
        self.stdout.write(f"DB_NAME={db_name}")
        self.stdout.write(f"DB_USER={user}")
        self.stdout.write(f"DB_PASSWORD={password}")
        
