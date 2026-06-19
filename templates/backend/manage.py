#!/usr/bin/env python
<<<<<<< HEAD
"""Django's command-line utility for administrative tasks."""
=======
>>>>>>> 43df0bde1d4462afbebd112bf3f839a4daeee51d
import os
import sys


def main():
<<<<<<< HEAD
    """Run administrative tasks."""
=======
>>>>>>> 43df0bde1d4462afbebd112bf3f839a4daeee51d
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
<<<<<<< HEAD
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
=======
            "Couldn't import Django. Activate the virtual environment first."
>>>>>>> 43df0bde1d4462afbebd112bf3f839a4daeee51d
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
