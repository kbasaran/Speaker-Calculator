"""Load/save of the user's speaker-calculator session state (.sscf files).

These helpers isolate the on-disk format and the file dialogs from the main
window. They deliberately do not touch application settings, sound feedback, or
model recalculation - those side effects stay with the caller so this module
stays a pure serialization/IO boundary.
"""

import json
import logging
from pathlib import Path

from PySide6 import QtWidgets as qtw

from config.app_config import APP_DEFINITIONS
from utils.version_convert import convert_any

logger = logging.getLogger(__name__)

FILE_FILTER = "Speaker calculator files (*.sscf)"
FILE_SUFFIX = ".sscf"


def collect_state(input_form, title_textbox, notes_textbox) -> dict:
    """Read the full user-form state into a serializable dict."""
    logger.debug("Get states initiated.")
    state = {}
    tab_widgets = [input_form.widget(i) for i in range(input_form.count())]
    for input_form_widget in tab_widgets:
        state = {**state, **input_form_widget.get_form_values()}

    state["user_notes"] = notes_textbox.toPlainText()
    state["user_title"] = title_textbox.text()

    return state


def apply_state(input_form, title_textbox, notes_textbox, state: dict) -> None:
    """Write a state dict back into the form widgets. Does not recalculate."""
    logger.debug("Set states initiated.")
    tab_widgets = [input_form.widget(i) for i in range(input_form.count())]
    for input_form_widget in tab_widgets:
        # for each form on its corresponding tab, make a "relevant states" dictionary
        # this dictionary will not contain all the settings
        # but only the ones that have items with matching names to form's items (names in form_object_names)
        form_object_names = [name for name in input_form_widget.get_form_values().keys()]
        relevant_states = {key: val for (key, val) in state.items() if key in form_object_names}
        input_form_widget.update_complete_form(relevant_states)

    notes_textbox.setPlainText(state.get("user_notes", "Error: NA"))
    title_textbox.setText(state.get("user_title", "Error: NA"))


def prompt_save_path(parent, start_dir: str) -> Path | None:
    """Show the save dialog and return the chosen path, or None if canceled."""
    path_unverified = qtw.QFileDialog.getSaveFileName(parent, caption='Save parameters to a file..',
                                                      dir=start_dir,
                                                      filter=FILE_FILTER,
                                                      )
    try:
        file_raw = path_unverified[0]
        if file_raw:
            file = Path(file_raw)
            if file.suffix != FILE_SUFFIX:
                file = file.with_suffix(FILE_SUFFIX)
            # filter not working as expected, saves files without file extension scf
            # therefore above logic
            assert file.parent.exists()
        else:
            return None  # empty file_raw. means nothing was selected, so pick file is canceled.
    except:
        # Path object could not be created
        raise NotADirectoryError(file_raw)

    return file


def write_state_file(file: Path, state: dict) -> None:
    """Serialize a state dict to the given .sscf file."""
    state["application_data"] = APP_DEFINITIONS

    json_string = json.dumps(state, indent=4)
    with open(file, "wt") as f:
        f.write(json_string)


def prompt_load_path(parent, start_dir: str) -> Path | None:
    """Show the open dialog and return the chosen path, or None if canceled."""
    path_unverified = qtw.QFileDialog.getOpenFileName(parent, caption='Open parameters from a save file..',
                                                      dir=start_dir,
                                                      filter=FILE_FILTER,
                                                      )
    file_raw = path_unverified[0]
    if file_raw:
        return Path(file_raw)
    return None  # canceled file select


def read_state_file(file: Path) -> dict:
    """Read and version-convert an existing .sscf file into a state dict.

    The caller is responsible for validating that ``file`` exists (see the
    ``is_file`` check in the main window) so that ``last_used_folder`` can be
    updated before the conversion runs.
    """
    logger.info(f"Loading file '{file.name}'")
    # backwards compatibility with older file versions
    return convert_any(file)
