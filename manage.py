#!/usr/bin/env python
import os
import sys
import warnings

# Suppress some warnings in third party packages we don't control. They pollute manage.py runs. 
warnings.filterwarnings("ignore", category=SyntaxWarning, module="trueskill")
warnings.filterwarnings("ignore", category=SyntaxWarning, module="relativefilepathfield")

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Site.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
