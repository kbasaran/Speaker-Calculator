#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
from cx_Freeze import setup, Executable
# https://cx-freeze.readthedocs.io/en/stable/setup_script.html

# This script lives in package_win/, one level below the project root. Anchor every
# source path to the root and put the root on sys.path so the project imports and
# the file globbing work regardless of the directory the build is launched from
# (the build itself is run from package_win/ so build/ and dist/ land there).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.app_config import APP_DEFINITIONS

# include_files entries are (absolute source, path-inside-the-build). Sources are
# absolute so the build does not depend on the current directory; destinations stay
# root-relative so the frozen layout mirrors the source tree.
files_to_include = [
    (str(ROOT / "LICENSE"), "LICENSE"),
    (str(ROOT / "README.md"), "README.md"),
    (str(ROOT / APP_DEFINITIONS["icon_path"]), APP_DEFINITIONS["icon_path"]),
    *[(str(file), str(file.relative_to(ROOT))) for file in (ROOT / "data").rglob("*")],
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

executables=[Executable(str(ROOT / "main.py"),
                        copyright=APP_DEFINITIONS["copyright"],
                        base="gui",
                        shortcut_name=APP_DEFINITIONS["app_name"] + " v" + APP_DEFINITIONS["version"],
                        shortcut_dir="DesktopFolder",
                        icon=str(ROOT / APP_DEFINITIONS["icon_path"]),
                        ),
            ]

setup(
    name=APP_DEFINITIONS["app_name"],
    version=APP_DEFINITIONS["version"],
    description=APP_DEFINITIONS["description"],
    options={"build_exe": build_exe_options, "bdist_msi": bdist_msi_options},
    executables=executables,
)
