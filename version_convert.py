#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 10 10:37:25 2024

@author: kerem
"""

from pathlib import Path
import pickle
import pathlib

# the v01 files require below classes to open. this is because I pickled their instances
# and to load again the pickles, app needs to create instances
# [face palm]


class SpeakerDriver():
    pass


class SpeakerSystem():
    pass


def convert_v01_to_v02(file: Path) -> dict:

    with open(file, "rb") as f:
        form_dict = pickle.load(f)

    necessary_parameters_for_v2 = [
        'fs',
        'Qms',
        'Xmax',
        'dead_mass',
        'Sd',

        'Rs_source',
        'excitation_unit',
        'excitation_value',
        'Rnom',

        'Rs_spk',
        'motor_spec_type',
        'target_Rdc',
        'former_ID',
        't_former',
        'h_winding_target',
        'B_average',
        'N_layer_options',
        'coil_choice_box',

        'Bl',
        'Rdc',
        'Mmd',
        'Mms',

        'h_washer',
        'airgap_clearance_inner',
        'airgap_clearance_outer',
        'former_extension_under_coil',

        'box_type',
        'Vb',
        'Qa',

        'parent_body',
        'k2',
        'm2',
        'c2',

        'user_curves',
        'user_notes',
        ]

    keys_in_v1 = [
        'result_sys',
        'user_curves',
        'fs',
        'Qms',
        'Xmax',
        'dead_mass',
        'Sd',
        'motor_spec_type',
        'target_Rdc',
        'former_ID',
        't_former',
        'h_winding',
        'B_average',
        'N_layer_options',
        'coil_choice_box',
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
        'excitation_unit',
        'excitation_value',
        'nominal_impedance',
        'box_type',
        'dof',
        'user_notes',
        'coil_options_table',
        ]

    def set_excitation_unit(value_from_v01):
        match value_from_v01["name"]:

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
                raise ValueError(f"No case matches: {value_from_v01}")

        excitation_unit_combobox_setting = {"current_text": current_text,
                                            "current_data": value_from_v01["userData"],
                                            }
        return excitation_unit_combobox_setting

    def set_coil_choice_box(value_from_v01):
        coil_choice_box_setting = {"current_text": value_from_v01["name"],
                                   "current_data": value_from_v01["userData"],
                                   }
        return coil_choice_box_setting

    def set_motor_spec_type(value_from_v01):
        motor_spec_type_setting = {"current_text": value_from_v01["name"],
                                   "current_data": value_from_v01["userData"],
                                   }
        return motor_spec_type_setting

    def set_box_type(value_from_v01):
        if value_from_v01 == "Free-air":
            return 0
        elif value_from_v01 == "Closed box":
            return 1
        else:
            raise ValueError(f'Could not convert box type setting: {form_dict["dof"]}')

    def set_parent_body(value_from_v01):
        if value_from_v01 == "1 dof":
            return 0
        elif value_from_v01 == "2 dof":
            return 1
        else:
            raise ValueError(f'Could not convert parent body setting: {form_dict["dof"]}')
            
    def set_user_curves(value_from_v01):
        curves = {}
        for i, curve in enumerate(value_from_v01):
            curves[i] = curve
        return curves

    # key, old name, conversion function
    conversion = {  "fs":                       ("fs",                      lambda x: x),
                    "Qms":                      ("Qms",                     lambda x: x),
                    "Xmax":                     ("Xmax",                    lambda x: x * 1e3),
                    "dead_mass":                ("dead_mass",               lambda x: x * 1e3),
                    "Sd":                       ("Sd",                      lambda x: x * 1e4),
    
                    "Rs_source":                (None,                      0.),
                    "excitation_unit":          ("excitation_unit",         set_excitation_unit),
                    "excitation_value":         ("excitation_value",        lambda x: x),
                    "Rnom":                     ("nominal_impedance",       lambda x: x),
            
                    "Rs_spk":                   (None,                      0.),
                    "motor_spec_type":          ("motor_spec_type",         set_motor_spec_type),
    
                    "target_Rdc":               ("Rdc",                     lambda x: x),
                    "former_ID":                ("former_ID",               lambda x: x*1e3),
                    "t_former":                 ("t_former",                lambda x: int(x*1e6)),
                    "h_winding_target":         ("h_winding",               lambda x: x*1e3),
                    "B_average":                ("B_average",               lambda x: x),
                    "N_layer_options":          ("N_layer_options",         lambda x: x),
                    "coil_options":             ("coil_choice_box",         set_coil_choice_box),

                    "Bl_p2":                    ("Bl",                      lambda x: x),
                    "Rdc_p2":                   ("Rdc",                     lambda x: x),
                    "Mmd_p2":                   ("Mmd",                     lambda x: x*1e3),

                    "Bl_p3":                    (None,                      0.),
                    "Rdc_p3":                   (None,                      0.),
                    "Mms_p3":                   (None,                      0.),
            
                    "h_top_plate":              ("h_washer",                lambda x: x*1e3),
                    "airgap_clearance_inner":   ("airgap_clearance_inner",  lambda x: int(x*1e6)),
                    "airgap_clearance_outer":   ("airgap_clearance_outer",  lambda x: int(x*1e6)),
                    "h_former_under_coil":      ("former_extension_under_coil",  lambda x: x*1e3),
            
                    "box_type":                 ("box_type",                set_box_type),
                    "Vb":                       ("Vb",                      lambda x: x*1e3),
                    "Qa":                       ("Qa",                      lambda x: x),
            
                    "parent_body":              ("dof",                     set_parent_body),
                    "k2":                       ("k2",                      lambda x: x*1e-3),
                    "m2":                       ("m2",                      lambda x: x*1e3),
                    "c2":                       ("c2",                      lambda x: x),
            
                    "user_curves":              ("user_curves",             set_user_curves),
                    "user_notes":               ("user_notes",              lambda x: x),

        }

    state = {}
    for key, (name_from_v01, converter) in conversion.items():
        if name_from_v01 is None:
            state[key] = converter
        else:
            value_from_v01 = form_dict[name_from_v01]
            state[key] = converter(value_from_v01)
    
    return state


if __name__ == "__main__":
    state = convert_v01_to_v02(Path.cwd().joinpath("default.sscf"))
