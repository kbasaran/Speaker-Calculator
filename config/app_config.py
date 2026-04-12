from dataclasses import dataclass, fields
from pathlib import Path
import logging
import json
from PySide6 import QtCore as qtc

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
# APP_DEFINITIONS["version"] += "rc" + time.strftime("%y%m%d", time.localtime())

# @dataclass
# class Settings:
#     """Settings will be stored in SI units"""
#     global logger
#     app_name: str = APP_DEFINITIONS["app_name"]
#     author: str = APP_DEFINITIONS["author"]
#     author_short: str = APP_DEFINITIONS["author_short"]
#     version: str = APP_DEFINITIONS["version"]
#     vc_table_file = "data/wire table.ods"  # relative posix path
#     startup_state_file = "data/startup.sscf"  # relative posix path
#     f_min: int = 10
#     f_max: int = 3000
#     A_beep: float = 0.25
#     last_used_folder: str = str(Path.home())
#     matplotlib_style: str = "ggplot"
#     graph_grids: str = "Major and minor"
#     calc_ppo: int = 48 * 8
#     export_ppo: int = 48
#     interpolate_must_contain_hz: int = 1000
#
#     def __post_init__(self):
#         self.settings_sys = qtc.QSettings(self.author_short, self.get_storage_title())
#         logger.debug(f"Settings will be stored in '{self.author_short}', '{self.get_storage_title()}'")
#         self._field_types = {field.name: field.type for field in fields(self)}
#         self.read_all_from_system()
#
#     def get_storage_title(self):
#         return (
#                 self.app_name
#                 + " v"
#                 + (".".join(self.version.split(".")[:2]) if "." in self.version else "???")
#         )
#
#     def update(self, attr_name, new_val):
#         expected_type = self._field_types[attr_name]
#         if type(new_val) != expected_type:
#             raise TypeError(
#                 f"Incorrect data type received for setting '{attr_name}'. "
#                 f"Expected type: {expected_type}. Received type/value: {type(new_val)}/{new_val}."
#             )
#         setattr(self, attr_name, new_val)
#         self.settings_sys.setValue(attr_name, new_val)
#
#     def write_all_to_system(self):
#         for field in fields(self):
#             self.settings_sys.setValue(field.name, getattr(self, field.name))
#
#     def read_all_from_system(self):
#         for field in fields(self):
#             setattr(
#                 self,
#                 field.name,
#                 self.settings_sys.value(field.name, field.default, type=type(field.default)),
#             )


class SettingsManager(qtc.QObject):
    _instance = None
    settings_changed = qtc.Signal()

    # Define your defaults here
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

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.q_settings = qtc.QSettings(APP_DEFINITIONS["author_short"], cls._instance.get_storage_title())
        return cls._instance

    def get_storage_title(self):
        return (
                self.get_value("app_name")
                + " v"
                + (".".join(self.get_value("version").split(".")[:2]) if "." in self.get_value("version") else "???")
        )

    def get_value(self, key: str):
        """
        Retrieve value from QSettings.
        If key doesn't exist, return the default value from DEFAULTS.
        Returns the value with its original JSON type.
        """
        # Check if key exists in QSettings
        if not self.q_settings.contains(key):
            return self.DEFAULTS.get(key)

        # Retrieve and decode JSON
        raw = self.q_settings.value(key)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # Fallback if value wasn't JSON (legacy or corruption)
            return raw

    def get_all_as_dict(self):
        """
        Retrieve all settings as a dictionary.
        """
        return {key: self.get_value(key) for key in self.q_settings.allKeys()}

    def set_all_from_dict(self, settings_dict: dict, signal=True):
        """
        Set all settings from a dictionary.
        """
        for key, value in settings_dict.items():
            self.set_value(key, value, signal=False)
        if signal:
            self.settings_changed.emit()

    def set_value(self, key: str, value, signal=True):
        """
        Store value as JSON string in QSettings.
        Emits setting_changed signal with key and value.
        """
        json_string = json.dumps(value)
        self.q_settings.setValue(key, json_string)
        if signal:
            self.settings_changed.emit()

    def remove_value(self, key: str):
        """Delete a setting. Next get_value will return the default."""
        self.q_settings.remove(key)

    def reset_to_default(self, key: str):
        """Remove a setting so it falls back to the default value."""
        self.remove_value(key)

    def reset_all_to_defaults(self):
        """Clear all settings and reload from DEFAULTS."""
        self.q_settings.clear()
        self.settings_changed.emit()

    def sync(self):
        """Force write to disk."""
        self.q_settings.sync()

    def get_all_defaults(self):
        """Return a copy of the defaults dictionary."""
        return self.DEFAULTS.copy()


# Global accessor
def singleton_settings():
    return SettingsManager()


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