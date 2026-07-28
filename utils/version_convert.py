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


def convert_any(file: Path) -> dict:
    suffix = file.suffixes[-1]
    
    if suffix == ".scf":  # v0.2.0        
        with open(file, "r") as f:
            state = json.load(f)
        
    elif suffix == ".sscf":
        try:                
            with open(file, "r") as f:  # >v0.2.0
                state = json.load(f)

        except UnicodeDecodeError:  # <v0.2.0
            state = convert_v01_to_v02(file)

    else:
        raise RuntimeError("Was not able to convert file.")
    
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
