import sys
import numpy as np
import pandas as pd
from scipy import signal
from dataclasses import dataclass
import pickle
import tkinter as tk
from tkinter import filedialog as tkfiledialog

from pathlib import Path

import logging
logging.basicConfig(level=logging.INFO)

# %% Test single file
# file_path = ".\\SSC files\\108660 AVAS.sscf"
# file = Path.cwd().joinpath(file_path)
# if not file.exists():
#     print(f"Did not find: {file_path:s}")
# else:
#     print(file.name)
#     with file.open(mode="rb") as handle:
#         myp = pickle.load(handle)
#         print(myp)


# %% Test all files in a folder

def file_dialog():
    root = tk.Tk()
    root.withdraw()
    title = "Select the folder with files to import:"
    try:
        folder_path = tkfiledialog.askdirectory(initialdir=".\\", title=title)
        return folder_path
    except Exception as e:
        print(f"File pick failed: {e}")
        return None
    else:
        root.destroy()

file_ext = "sscf"
folder_path = ".\\SSC Files"
while True:
    if folder_path is None:
        folder_path = file_dialog()

    # Check if path is valid
    if folder_path == "":
        print("Exiting..")
        sys.exit()
    else:
        p = Path(folder_path)  # path to look for the log files
        files = [x for x in p.glob("**\*" + "." + file_ext)]
        print(f"\nOpening: {p}")

    if len(files) < 1:
        folder_path = None
        print("No files found in this location. Please select another location.")
    else:
        break


for file in files:
    print(file.name)
    with file.open(mode="rb") as handle:
        myp = pickle.load(handle)
        print(myp["h_winding"])
