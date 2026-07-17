from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'Display a summary of Django settings and context'

    def handle(self, *args, **options):
        '''
        A null command delegating handling to settings.py. Settings.py 
        is loaded before we get here and can check sys.args to see this 
        command was run. This is used a stub to provide a valid command 
        for it to check. 
        '''
        pass

