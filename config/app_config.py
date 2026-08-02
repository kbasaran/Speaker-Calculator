import time
import logging
from pathlib import Path
from generictools.settings import SettingsManager

APP_DEFINITIONS = {"app_name": "Speaker Calculator",
                   "version": "0.5.0",
                   "description": "Loudspeaker design and calculations",
                   "copyright": "Copyright (C) 2026 Kerem Basaran",
                   "icon_path": "images/logo2025.ico",  # relative posix path
                   "author": "Kerem Basaran",
                   "author_short": "kbasaran",
                   "email": "kbasaran@gmail.com",
                   "website": "https://github.com/kbasaran",
                   }
# uncomment for release candidate builds
# APP_DEFINITIONS["version"] += "rc" + time.strftime("%y%m%d", time.localtime())

# Text shown in the Help -> About dialog.
ABOUT_TEXT = "\n".join([
    "Speaker Calculator - Loudspeaker design and calculations tool",
    f"Version: {APP_DEFINITIONS['version']}",
    "",
    f"{APP_DEFINITIONS['copyright']}",
    f"{APP_DEFINITIONS['website']}",
    f"{APP_DEFINITIONS['email']}",
    "",
    "This program is free software: you can redistribute it and/or modify",
    "it under the terms of the GNU General Public License as published by",
    "the Free Software Foundation, either version 3 of the License, or",
    "(at your option) any later version.",
    "",
    "This program is distributed in the hope that it will be useful,",
    "but WITHOUT ANY WARRANTY; without even the implied warranty of",
    "MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the",
    "GNU General Public License for more details.",
    "",
    "You should have received a copy of the GNU General Public License",
    "along with this program.  If not, see <https://www.gnu.org/licenses/>.",
    "",
    "This software uses Qt for Python under the GPLv3 license.",
    "https://www.qt.io/",
    "",
    "See 'requirements.txt' for an extensive list of Python libraries used.",
])

DEFAULTS = {
    "app_name": APP_DEFINITIONS["app_name"],
    "author": APP_DEFINITIONS["author"],
    "author_short": APP_DEFINITIONS["author_short"],
    "version": APP_DEFINITIONS["version"],
    "vc_table_file": "data/wire_table.ods",
    "startup_state_file": "data/startup.sscf",
    "f_min": 10,
    "f_max": 1500,
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
