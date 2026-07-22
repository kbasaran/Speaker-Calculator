import time
import logging
from pathlib import Path
from generictools.app_config import SettingsManager

APP_DEFINITIONS = {"app_name": "Speaker Calculator",
                   "version": "0.3.4",
                   "description": "Loudspeaker design and calculations",
                   "copyright": "Copyright (C) 2026 Kerem Basaran",
                   "icon_path": "images/logo2025.ico",  # relative posix path
                   "author": "Kerem Basaran",
                   "author_short": "kbasaran",
                   "email": "kbasaran@gmail.com",
                   "website": "https://github.com/kbasaran",
                   }
# uncomment for release candidate builds
APP_DEFINITIONS["version"] += "rc" + time.strftime("%y%m%d", time.localtime())

DEFAULTS = {
    "app_name": APP_DEFINITIONS["app_name"],
    "author": APP_DEFINITIONS["author"],
    "author_short": APP_DEFINITIONS["author_short"],
    "version": APP_DEFINITIONS["version"],
    "vc_table_file": "data/wire table.ods",
    "startup_state_file": "data/startup.sscf",
    "f_min": 10,
    "f_max": 3000,
    "A_beep": 0.25,
    "last_used_folder": str(Path.home()),
    "matplotlib_style": "ggplot",
    "graph_grids": "Major and minor",
    "calc_ppo": 48 * 8,
    "export_ppo": 48,
    "interpolate_must_contain_hz": 1000,
}


def singleton_settings():
    return SettingsManager(APP_DEFINITIONS, DEFAULTS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    logger = logging.getLogger()

    try:
        answer = input("Type 'x' to delete all settings: ")
        if answer.lower() == 'x':
            logger.info("Deleting all settings...")
            app_settings = singleton_settings()
            app_settings.reset_all_to_defaults()
            logger.info("Settings deleted successfully.")
        else:
            logger.info("Operation cancelled by user.")
    except KeyboardInterrupt:
        exit()

else:
    logger = logging.getLogger(__name__)
