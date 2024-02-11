#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 10 10:37:25 2024

@author: kerem
"""

from pathlib import Path
import pickle

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
        'coil_options_table',

        'Bl',
        'Rdc',
        'Mmd',

        'h_washer',
        'airgap_clearance_inner',
        'airgap_clearance_outer',
        'former_extension_under_coil',

        'box_type',
        'Vb',
        'Qa',

        'dof',
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

    new_default = {"Rs_spk": 0.,
                   "Rs_source": 0.,
                   }

    # key is new name, value is old name
    translation = {"Rnom": "nominal_impedance",
                   "h_winding_target": "h_winding",
                   }

    missing_parameters = set(necessary_parameters_for_v2)
    state = {}
    for key in necessary_parameters_for_v2:
        if key in new_default.keys():
            state[key] = new_default[key]
            missing_parameters.remove(key)
        elif key in translation.keys():
            old_key = translation[key]
            state[key] = form_dict[old_key]
            missing_parameters.remove(key)
        elif key in keys_in_v1:
            state[key] = form_dict[key]
            missing_parameters.remove(key)

    if missing_parameters:
        raise ValueError("Could not be converted: " + str(missing_parameters))

    # setattr(self, "coil_options_table", form_dict.pop("coil_options_table"))
    # form.coil_choice_box["obj"].clear()
    # if form_dict["motor_spec_type"]["userData"] == "define_coil":
    #     coil_choice = (form_dict["coil_choice_box"]["name"],
    #                    form_dict["coil_choice_box"]["userData"])
    #     form.coil_choice_box["obj"].addItem(*coil_choice)

    # items_to_skip = ["result_sys", "pickles_path"]
    # for item_name, value in form_dict.items():
    #     if item_name not in items_to_skip:
    #         self.set_value(item_name, value)

    # self.set_state(state)

    return state


if __name__ == "__main__":
    state = convert_v01_to_v02(Path.cwd().joinpath("default.sscf"))
