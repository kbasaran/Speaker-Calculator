# This file is part of Speaker Calculator - Loudspeaker design and calculations tool
# Copyright (C) 2026 - Kerem Basaran
# https://github.com/kbasaran
__email__ = "kbasaran@gmail.com"

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from pathlib import Path
import copy
import pickle
import pathlib
import inspect
import json

# the v01 files have many custom classes pickled and to unpickle them is often not possible
# in a system where API of these objects and the Python environment is of newer version and
# no more compatible [face palm]
# due to this, we need a filtered unpickling process as seen below

# Define a dummy class to replace incompatible objects
class DummyObject:
    def __init__(self, *args, **kwargs):
        pass

    def __setstate__(self, state):
        pass


class IgnoreErrorsUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        try:
            found_class = super().find_class(module, name)

            # Ignore pathlib.Path subclasses
            if inspect.isclass(found_class) and issubclass(found_class, pathlib.Path):
                raise NotImplementedError

            return found_class

        except (AttributeError, ModuleNotFoundError, NotImplementedError):
            print(
                f"Warning: Ignoring object from {module}.{name} due to incompatibility."
            )
            return DummyObject


def detect_version(file: Path) -> str:
    """Detect the on-disk save-format generation of a session file.

    Returns a "<major>.<minor>" string:

      - "0.1" : a Python pickle (binary) -- the original format, which predates
                the JSON formats and carries no version stamp.
      - "0.2" and onwards : JSON. The generation is read straight from the
                'application_data.version' stamp written at save time
                (e.g. "0.4.0rc..." -> "0.4"). That stamp is kept accurate at every
                release, so it is trusted directly rather than sniffing the schema.
    """
    # v0.1 files are pickles; reading them as JSON/UTF-8 text fails -- with a
    # UnicodeDecodeError for the usual binary pickle protocols, or a
    # JSONDecodeError for an ASCII (protocol 0) pickle.
    try:
        with open(file, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "0.1"

    if not isinstance(state, dict):
        raise RuntimeError(f"Unrecognised session file structure: {file}")

    stamp = (state.get("application_data") or {}).get("version", "")
    if not stamp:
        raise RuntimeError(
            f"JSON session file has no 'application_data.version' stamp: {file}"
            )
    return ".".join(stamp.split(".")[:2])


# Default values for the keys added by the v0.4 save format (passive-radiator /
# bass-reflex resonator inputs, plus the enclosure leakage factor Ql). These are a
# frozen snapshot of the v0.4 defaults -- a migration should reproduce the schema
# as it was at that release, not track later default changes. Combobox widgets are
# stored the same way the app serialises them (current_index / _data / _text, and
# an items list where the app writes one).
V04_NEW_KEY_DEFAULTS = {
    "resonator_spec_type": {
        "current_index": 0,
        "current_data": "pr_1",
        "current_text": "PR - Define mass and damping ratio",
        "items": [],
        },
    "port_diameter": 0.05,
    "Qp": 15.0,
    "exit_flare_type": {
        "current_index": 1,
        "current_data": 0.732,
        "current_text": "One end flanged, one free",
        "items": [
            ["Both ends flanged / flared", 0.85],
            ["One end flanged, one free", 0.732],
            ["Both ends free", 0.614],
            ],
        },
    "Ql": 99999.9,
    "h_pr": 0.7,
    "spring_damping_ratio_pr": 0.005,
    "area_ratio_pr": 2.5,
    "Mmdp": 0.01,
    "dir_pr_vent": {
        "current_index": 0,
        "current_data": 1,
        "current_text": "Same with driver",
        "items": [
            ["Same with driver", 1],
            ["On opposite direction", -1],
            ],
        },
    }


def convert_v03_to_v04(state: dict) -> dict:
    """Upgrade a v0.2/v0.3 JSON state dict to the v0.4 schema.

    v0.4 added the passive-radiator / bass-reflex resonator inputs and the
    enclosure leakage factor Ql (see V04_NEW_KEY_DEFAULTS). Older files predate the
    vented enclosure option, so those keys are simply filled with defaults; they
    stay inert unless the user later switches to the resonator enclosure type.

    Only missing keys are added, so this is idempotent -- safe to run on a file
    that already carries some or all of the v0.4 keys.
    """
    for key, default in V04_NEW_KEY_DEFAULTS.items():
        state.setdefault(key, copy.deepcopy(default))
    return state


def convert_v04_to_v05(state: dict) -> dict:
    """Upgrade a v0.4 JSON state dict to the v0.5 schema.

    v0.5 keeps 'Bl_p2'/'Bl_p3' (and 'Re_p2'/'Re_p3') in sync in the GUI, since they
    describe the same physical motor parameter on the two direct-entry pages. Older
    files may hold a different value in each half of a pair (the page that wasn't
    active was left at its default), so resolve each pair to the value that belonged
    to whichever 'motor_spec_type' was actually active.

    Idempotent: a file where both pairs already match is a no-op.
    """
    mode = (state.get("motor_spec_type") or {}).get("current_data")
    if mode == "define_Bl_Re_Mms":
        bl_src, re_src = "Bl_p3", "Re_p3"
    else:
        bl_src, re_src = "Bl_p2", "Re_p2"

    bl = state.get(bl_src, state.get("Bl_p2", state.get("Bl_p3")))
    re_val = state.get(re_src, state.get("Re_p2", state.get("Re_p3")))

    state["Bl_p2"] = state["Bl_p3"] = bl
    state["Re_p2"] = state["Re_p3"] = re_val
    return state


def convert_v05_to_v06(state: dict) -> dict:
    """Upgrade a v0.5 JSON state dict to the v0.6 schema.

    v0.6 added the voice coil inductance 'Le' to the general specifications.
    Older files predate this input, so the key is simply filled with its default
    of 0 (SI units, i.e. 0 H).

    Only missing keys are added, so this is idempotent -- safe to run on a file
    that already carries the v0.6 keys.
    """
    state.setdefault("Le", 0.0)
    return state


def convert_any(file: Path) -> dict:
    """Load a session file of any past format and return a current-schema state dict."""
    version = detect_version(file)

    if version == "0.1":
        state = convert_v01_to_v02(file)   # unpickle -> v0.2-schema dict
    else:
        with open(file, "r", encoding="utf-8") as f:
            state = json.load(f)

    # Bring every pre-0.4 format up to the current (v0.4) schema. v0.1 has already
    # been lifted to the v0.2 schema above, and v0.2/v0.3 share one schema, so the
    # same upgrade covers all three; on a v0.4 file it is a no-op.
    if version in ("0.1", "0.2", "0.3"):
        state = convert_v03_to_v04(state)

    # Bring every pre-0.5 format up to the current (v0.5) schema.
    if version in ("0.1", "0.2", "0.3", "0.4"):
        state = convert_v04_to_v05(state)

    # Bring every pre-0.6 format up to the current (v0.6) schema.
    if version in ("0.1", "0.2", "0.3", "0.4", "0.5"):
        state = convert_v05_to_v06(state)

    return state
            

def convert_v01_to_v02(file: Path) -> dict:

    with open(file, "rb") as f:
        print(f"Opening file: {file.name}")
        form_dict = IgnoreErrorsUnpickler(f).load()

    keys_in_v01 = [
        'result_sys',
        'user_curves',  # list
        'fs',
        'Qms',
        'Xmax',
        'dead_mass',
        'Sd',
        'motor_spec_type',  # dict
        'target_Rdc',
        'former_ID',
        't_former',
        'h_winding',
        'B_average',
        'N_layer_options',
        'coil_choice_box',  # dict
        'Bl',
        'Rdc',
        'Mmd',
        'h_washer',
        'airgap_clearance_inner',
        'airgap_clearance_outer',
        'former_extension_under_coil',
        'Vb',
        'Qa',
        'k2',
        'm2',
        'c2',
        'excitation_unit',  # dict
        'excitation_value',
        'nominal_impedance',
        'box_type',
        'dof',
        'user_notes',
        'coil_options_table',  # dataframe
        ]

    def translate_excitation_type(value_v01):
        
        if "volt" in value_v01["name"].lower():
            current_text = "Volts"
        elif "rnom" in value_v01["name"].lower():
            current_text = "Watts @Rnom"
        elif "re" in value_v01["name"].lower() or "rdc" in value_v01["name"].lower():
            current_text = "Watts @Re"
        else:
            raise ValueError(f"No case matches: {value_v01}")

        excitation_type_combobox_setting = {"current_text": current_text,
                                            "current_data": value_v01["userData"],
                                            }
        return excitation_type_combobox_setting

    def translate_coil_options(value_v01):
        coil_choice_box_setting = {"current_text": value_v01["name"],
                                   "current_data": value_v01["userData"],
                                   }
        return coil_choice_box_setting

    def translate_motor_spec_type(value_v01):
        match value_v01["userData"]:

            case "define_coil":
               return {"current_text": "Define Coil Dimensions and Average B",
                       "current_data": "define_coil",
                       }
            case "define_Bl_Re":
               return {"current_text": "Define Bl, Re, Mmd",
                       "current_data": "define_Bl_Re_Mmd",
                       }
            case _:
                raise ValueError(f"No case matches: {value_v01}")

    def translate_box_type(value_v01):
        if value_v01 == "Free-air":
            return 0
        elif value_v01 == "Closed box":
            return 1
        else:
            raise ValueError(f'Could not convert enclosure type setting: {form_dict["dof"]}')

    def translate_parent_body(value_v01):
        if value_v01 == "1 dof":
            return 0
        elif value_v01 == "2 dof":
            return 1
        else:
            raise ValueError(f'Could not convert parent body setting: {form_dict["dof"]}')

    def translate_user_curves(value_v01):
        curves = {}
        for i, curve in enumerate(value_v01):
            curves[i] = curve
        return curves

    # key in new version, key in old version, conversion function
    # values are always stored in SI units
    # if key in v01 is None, do not give a converter function but directly a value

    conversion = {  "fs":                       ("fs",                      lambda x: x),
                    "Qms":                      ("Qms",                     lambda x: x),
                    "Xpeak":                    ("Xmax",                    lambda x: x),
                    "dead_mass":                ("dead_mass",               lambda x: x),
                    "Sd":                       ("Sd",                      lambda x: x),
    
                    "Rext":                 (None,                      0.),
                    "excitation_type":          ("excitation_unit",         translate_excitation_type),
                    "excitation_value":         ("excitation_value",        lambda x: x),
                    "Rnom":                     ("nominal_impedance",       lambda x: x),
            
                    "motor_spec_type":          ("motor_spec_type",         translate_motor_spec_type),

                    "target_Re":               ("Rdc",                     lambda x: x),
                    "former_ID":                ("former_ID",               lambda x: x),
                    "t_former":                 ("t_former",                lambda x: x),
                    "h_winding_target":         ("h_winding",               lambda x: x),
                    "w_stacking_coef":          (None,                      0.9),
                    "Rlw":                      (None,                      0.),
                    "B_average":                ("B_average",               lambda x: x),
                    "N_layer_options":          ("N_layer_options",         lambda x: x),
                    "coil_options":             ("coil_choice_box",         translate_coil_options),
                    "reduce_per_layer":         (None,                      2),

                    "Bl_p2":                    ("Bl",                      lambda x: x),
                    "Re_p2":                   ("Rdc",                     lambda x: x),
                    "Mmd_p2":                   ("Mmd",                     lambda x: x),

                    "Bl_p3":                    (None,                      0.),
                    "Re_p3":                   (None,                      0.),
                    "Mms_p3":                   (None,                      0.),
            
                    "h_top_plate":              ("h_washer",                lambda x: x),
                    "airgap_clearance_inner":   ("airgap_clearance_inner",  lambda x: x),
                    "airgap_clearance_outer":   ("airgap_clearance_outer",  lambda x: x),
                    "h_former_under_coil":      ("former_extension_under_coil",  lambda x: x),

                    "enclosure_type":           ("box_type",          translate_box_type),
                    "Vb":                       ("Vb",                      lambda x: x),
                    "Qa":                       ("Qa",                      lambda x: x),
                    # "Ql":                       (None,                      9999.9),
            
                    "parent_body":              ("dof",                     translate_parent_body),
                    "mpb":                       ("m2",                      lambda x: x),
                    "kpb":                       ("k2",                      lambda x: x),
                    "rpb":                       ("c2",                      lambda x: x),
            
                    "user_curves":              ("user_curves",             translate_user_curves),
                    "user_title":               (None,                      ""),
                    "user_notes":               ("user_notes",              lambda x: x),

        }


    missing_values = set(conversion.keys())
    state = {}
    for key, (key_in_v01, converter) in conversion.items():
        if key_in_v01 is None:
            state[key] = converter
            missing_values.remove(key)
        else:
            try:
                value_v01 = form_dict[key_in_v01]
                state[key] = converter(value_v01)
                missing_values.remove(key)
            except KeyError as e:
                print(f"KeyError for key in v01: {key_in_v01}.\n{str(e)}")

    if missing_values:
        print("----Missing----")
        print(missing_values)

    return state


def batch_convert_v01_files(folder_path):

    sscf_files = folder_path.glob("*.sscf")
    states = {}
    for file in sscf_files:
        print()
        states[file.name] = convert_v01_to_v02(file)
    return states


if __name__ == "__main__":
    # state = convert_v01_to_v02(Path.cwd().joinpath("default.sscf"))
    states = batch_convert_v01_files(pathlib.Path(
        "../private/SSC files"
        ))
