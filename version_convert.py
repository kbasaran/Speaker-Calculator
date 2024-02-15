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

    def set_excitation_unit():
        excitation_unit_combobox_setting = {"current_text": form_dict["excitation_unit"]["name"],
                                            "current_data": form_dict["excitation_unit"]["userData"],
                                            }
        state["excitation_unit"] = excitation_unit_combobox_setting

    def set_coil_choice_box():
        coil_choice_box_setting = {"current_text": form_dict["coil_choice_box"]["name"],
                                   "current_data": form_dict["coil_choice_box"]["userData"],
                                   }
        state["coil_choice_box"] = coil_choice_box_setting

    def set_motor_spec_type():
        motor_spec_type_setting = {"current_text": form_dict["motor_spec_type"]["name"],
                                   "current_data": form_dict["motor_spec_type"]["userData"],
                                   }
        state["motor_spec_type"] = motor_spec_type_setting

    missing_parameters = set(necessary_parameters_for_v2)
    state = {}

    for key in necessary_parameters_for_v2:
        if key == "excitation_unit":
            set_excitation_unit()

        elif key == "coil_choice_box":
            set_coil_choice_box()

        elif key == "motor_spec_type":
            set_motor_spec_type()

        elif key == "t_former":
            state[key] = int(form_dict[key])
            # other parameters have the same issue
            # stored in SI unit or stored as in the value in widget

        elif key in new_default.keys():
            state[key] = new_default[key]

        elif key in translation.keys():
            old_key = translation[key]
            state[key] = form_dict[old_key]

        elif key in keys_in_v1:
            state[key] = form_dict[key]

        else:
            continue
        missing_parameters.remove(key)

    if missing_parameters:
        raise ValueError("Could not be converted: " + str(missing_parameters))

    return state


if __name__ == "__main__":
    state = convert_v01_to_v02(Path.cwd().joinpath("default.sscf"))
