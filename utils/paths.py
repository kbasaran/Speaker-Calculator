import sys
from pathlib import Path


def get_main_dir():
    if getattr(sys, 'frozen', False):
        # The application is frozen
        return Path(sys.executable).parent
    else:
        # The application is not frozen
        # Go up one level from utils/ to reach the project root
        return Path(__file__).parent.parent
