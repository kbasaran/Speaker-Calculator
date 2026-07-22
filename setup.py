#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from cx_Freeze import setup, Executable
from config.sc_config import APP_DEFINITIONS
from pathlib import Path
# https://cx-freeze.readthedocs.io/en/stable/setup_script.html

files_to_include = [
    (str(Path("./LICENSE")), str(Path("./LICENSE"))),
    (str(Path("./README.md")), str(Path("./README.md"))),
    (str(Path(APP_DEFINITIONS["icon_path"])), str(Path(APP_DEFINITIONS["icon_path"]))),
    *[(str(file.relative_to(Path(__file__).parent)),) * 2 for file in Path(__file__).parent.joinpath("data").rglob("*")],
    ]

print("Warning.. Adding following additional files to package:")
for pair in files_to_include:
    print("\t" + pair[0])
print()

# Dependencies are automatically detected, but it might need fine tuning.
build_exe_options = {
    "packages": ["numpy", "scipy", "matplotlib", "sympy", "pandas"],  # RecursionError in cx_Freeze if these are not provided
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
