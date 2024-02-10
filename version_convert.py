#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 10 10:37:25 2024

@author: kerem
"""

from pathlib import Path
import pickle

class SpeakerDriver():
    pass
    
class SpeakerSystem():
    pass

def convert_v01_to_v02(file: Path) -> dict:
               
    with open(file, "rb") as f:
        form_dict = pickle.load(f)
    
    print(form_dict.keys())


    necessary_parameters_for_v2 = [
        'fs',
        'Qms',
        'Xmax',
        'dead_mass',
        'Sd',
        
        'Rs_source',
        'excitation_unit',
        'excitation_value',
        'nominal_impedance',
        
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
    
    return {}

if __name__ == "__main__":
    convert_v01_to_v02(Path("/home/kerem/GitHub/Speaker-Stuff-Calculator/default.sscf"))