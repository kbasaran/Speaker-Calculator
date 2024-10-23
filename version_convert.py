#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 10 10:37:25 2024

@author: kerem
"""

from pathlib import Path
import pickle
import pathlib
import inspect

# the v01 files have many custom classes pickled and to unpickle them is often not possible
# in a system where API of these objects and the Python environment is of newer version and
# no more compatible [face palm]
# due to this, we need a filtered unpickling process as seen below

# Define a dummy class to replace incompatible objects
class DummyObject:
    def __init__(self, *args, **kwargs):
        pass  # Do nothing, just a placeholder


class IgnoreErrorsUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        try:
            found_class = super().find_class(module, name)
            
            # Ignore paths - they caused problems
            if inspect.isclass(found_class) and issubclass(found_class, pathlib.Path):
                raise NotImplementedError
            else:
                return found_class
        except (AttributeError, ModuleNotFoundError, NotImplementedError):
            # Return a dummy class to handle instantiation via NEWOBJ
            print(f"Warning: Ignoring object from {module}.{name} due to incompatibility.")
            return DummyObject


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

    def translate_excitation_unit(value_v01):
        match value_v01["name"]:

            case "Volt":
                current_text = "Volts"
            case "Volts":
                current_text = "Volts"

            case "W@Rdc":
                current_text = "Watts @Rdc"
            case "Watt@Rdc":
                current_text = "Watts @Rdc"

            case "W@Rnom":
                current_text = "Watts @Rnom"
            case "Watt@Rnom":
                current_text = "Watts @Rnom"

            case _:
                raise ValueError(f"No case matches: {value_v01}")

        excitation_unit_combobox_setting = {"current_text": current_text,
                                            "current_data": value_v01["userData"],
                                            }
        return excitation_unit_combobox_setting

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
               return {"current_text": "Define Bl, Rdc, Mmd",
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
            raise ValueError(f'Could not convert box type setting: {form_dict["dof"]}')

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
    # in the old version, values were stored in SI units
    # in this version, values on the widget will are stored as is

    conversion = {  "fs":                       ("fs",                      lambda x: x),
                    "Qms":                      ("Qms",                     lambda x: x),
                    "Xpeak":                    ("Xmax",                    lambda x: x * 1e3),
                    "dead_mass":                ("dead_mass",               lambda x: x * 1e3),
                    "Sd":                       ("Sd",                      lambda x: x * 1e4),
    
                    "Rs_source":                (None,                      0.),
                    "excitation_unit":          ("excitation_unit",         translate_excitation_unit),
                    "excitation_value":         ("excitation_value",        lambda x: x),
                    "Rnom":                     ("nominal_impedance",       lambda x: x),
            
                    "motor_spec_type":          ("motor_spec_type",         translate_motor_spec_type),

                    "target_Rdc":               ("Rdc",                     lambda x: x),
                    "former_ID":                ("former_ID",               lambda x: x*1e3),
                    "t_former":                 ("t_former",                lambda x: int(x*1e6)),
                    "h_winding_target":         ("h_winding",               lambda x: x*1e3),
                    "w_stacking_coef":          (None,                      0.9),
                    "Rs_leadwire":              (None,                      0.),
                    "B_average":                ("B_average",               lambda x: x),
                    "N_layer_options":          ("N_layer_options",         lambda x: x),
                    "coil_options":             ("coil_choice_box",         translate_coil_options),

                    "Bl_p2":                    ("Bl",                      lambda x: x),
                    "Rdc_p2":                   ("Rdc",                     lambda x: x),
                    "Mmd_p2":                   ("Mmd",                     lambda x: x*1e3),

                    "Bl_p3":                    (None,                      0.),
                    "Rdc_p3":                   (None,                      0.),
                    "Mms_p3":                   (None,                      0.),
            
                    "h_top_plate":              ("h_washer",                lambda x: x*1e3),
                    "airgap_clearance_inner":   ("airgap_clearance_inner",  lambda x: int(x*1e6)),
                    "airgap_clearance_outer":   ("airgap_clearance_outer",  lambda x: int(x*1e6)),
                    "h_former_extension_under_coil":      ("former_extension_under_coil",  lambda x: x*1e3),

                    "box_type":                 ("box_type",                translate_box_type),
                    "Vb":                       ("Vb",                      lambda x: x*1e3),
                    "Qa":                       ("Qa",                      lambda x: x),
                    "Ql":                       (None,                      9999.),
            
                    "parent_body":              ("dof",                     translate_parent_body),
                    "k2":                       ("k2",                      lambda x: x*1e-3),
                    "m2":                       ("m2",                      lambda x: x*1e3),
                    "c2":                       ("c2",                      lambda x: x),
            
                    "user_curves":              ("user_curves",             translate_user_curves),
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
    states = []
    for file in sscf_files:
        print()
        states.append(convert_v01_to_v02(file))
    return states


if __name__ == "__main__":
    # state = convert_v01_to_v02(Path.cwd().joinpath("default.sscf"))
    states = batch_convert_v01_files(pathlib.Path(
        "C:\\Users\\kerem.basaran\\OneDrive - PremiumSoundSolutions\\Documents\\SSC files"
        # "/home/kerem/Dropbox/Documents/Python/PSS Work/SSC files"
        ))
