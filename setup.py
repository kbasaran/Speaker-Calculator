#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from cx_Freeze import setup, Executable
from config.app_config import APP_DEFINITIONS
from pathlib import Path
# https://cx-freeze.readthedocs.io/en/stable/setup_script.html

files_to_include = [
    (str(Path("./LICENSE")), str(Path("./LICENSE"))),
    (str(Path("./README.md")), str(Path("./README.md"))),
    (str(Path(APP_DEFINITIONS["icon_path"])), str(Path(APP_DEFINITIONS["icon_path"]))),
    *[(str(file.relative_to(Path(__file__).parent)),) * 2 for file in Path(__file__).parent.joinpath("data").rglob("*")],
    ]

# sounddevice/soundfile ship their PortAudio/libsndfile binaries in package data
# folders that cx_Freeze's import analysis does not pick up. Locate them from the
# installed packages and bundle each at the same relative path when it exists
# (e.g. _sounddevice_data ships on Windows, not on Linux).
for pkg_name, data_dir_name in (("sounddevice", "_sounddevice_data"),
                                ("soundfile", "_soundfile_data")):
    module = __import__(pkg_name)
    data_dir = Path(module.__file__).parent / data_dir_name
    if data_dir.is_dir():
        files_to_include.append((str(data_dir), data_dir_name))

print("Warning.. Adding following additional files to package:")
for pair in files_to_include:
    print("\t" + pair[0])
print()

# Dependencies are automatically detected, but it might need fine tuning.
build_exe_options = {
    "packages": ["numpy", "scipy", "matplotlib", "sympy", "pandas",  # RecursionError in cx_Freeze if these are not provided
                 "odf",  # dynamically imported by pandas as the .ods engine; not visible to static analysis
                 "sounddevice", "soundfile"],  # ship their bundled PortAudio/libsndfile binaries
    "include_files": files_to_include,
    "silent_level": 1,
}

bdist_msi_options = {
    "extensions": [{"extension": "sscf",
                    "verb": "load",
                    "argument": '"%1"',
                    "executable": "main.exe",
                    }]
    }

executables=[Executable("main.py",
                        copyright=APP_DEFINITIONS["copyright"],
                        base="gui",
                        shortcut_name=APP_DEFINITIONS["app_name"] + " v" + APP_DEFINITIONS["version"],
                        shortcut_dir="DesktopFolder",
                        icon=APP_DEFINITIONS["icon_path"],
                        ),
            ]

setup(
    name=APP_DEFINITIONS["app_name"],
    version=APP_DEFINITIONS["version"],
    description=APP_DEFINITIONS["description"],
    options={"build_exe": build_exe_options, "bdist_msi": bdist_msi_options},
    executables=executables,
)
