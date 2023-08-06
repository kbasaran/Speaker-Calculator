#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Aug  6 20:23:15 2023

@author: kerem
"""

import numpy as np


def calculate_air_mass(Sd):
    """Air mass on diaphragm; the difference between Mms and Mmd."""
    return 1.13*(Sd)**(3/2)  # m2 in, kg out


def calculate_Lm(Bl, Re, Mms, Sd):
    """Calculate Lm@Re, 1W, 1m."""
    w_ref = 10**-12
    I_1W_per_m2 = cons.RHO * Bl**2 * Sd**2 / cons.c_air / Re / Mms**2 / 2 / np.pi
    P_over_I_half_space = 1/2/np.pi  # m²
    return 10 * np.log10(I_1W_per_m2 * P_over_I_half_space / w_ref)


def calculate_Xmech(Xmax):
    """Proposed Xmech value for given Xmax value.

    All values in basic SI units.
    """
    Xclearance = 1e-3 + (Xmax - 3e-3) / 5
    return Xmax + Xclearance


def calculate_windings(wire_type, N_layers, former_OD, h_winding):
    """Calculate coil mass, Rdc and l for a given coil."""
    global cons
    w_wire = cons.VC_TABLE.loc[wire_type, "width, m*e-6, avg"] / 1e6
    w_wire_max = cons.VC_TABLE.loc[wire_type, "width, m*e-6, max"] / 1e6
    h_wire = cons.VC_TABLE.loc[wire_type, "height, m*e-6, avg"] / 1e6
    stacking_coef = cons.VC_TABLE.loc[wire_type, "stacking coeff."]

    def calc_N_winding_per_layer(i_layer):
        """Calculate the number of windings that fit on one layer of coil."""
        val = h_winding / h_wire - i_layer * 2  # 2 windings less on each stacked layer
        return -1 if val < 1 else val

    def calc_length_of_one_turn_per_layer(i_layer):
        """Calculate the length of one turn of wire on a given coil layer."""
        if i_layer == 1:
            turn_mean_radius = former_OD/2 + w_wire/2
        if i_layer > 1:
            turn_mean_radius = former_OD/2 + w_wire/2 + (stacking_coef * (i_layer - 1) * w_wire)
        # pi/4 is stacking coefficient
        return 2*np.pi*turn_mean_radius

    # Windings amount for each layer
    N_windings = [calc_N_winding_per_layer(i)
                  for i in range(N_layers)]

    # Wire length for one full turn around for a given layer
    l_one_turn = [calc_length_of_one_turn_per_layer(i_layer) for i_layer in range(1, N_layers+1)]

    total_length_wire_per_layer = [N_windings[i] * l_one_turn[i]
                                   for i in range(N_layers)]

    l_wire = sum(total_length_wire_per_layer)
    Rdc = l_wire * cons.VC_TABLE.loc[wire_type, "ohm/m"]
    w_coil_max = w_wire_max * (1 + (N_layers - 1) * stacking_coef)
    coil_mass = l_wire * cons.VC_TABLE.loc[wire_type, "g/m"] / 1000

    N_windings_rounded = [int(np.round(i)) for i in N_windings]
    return(Rdc, N_windings_rounded, l_wire, w_coil_max, coil_mass)


def calculate_input_voltage(excitation, Rdc, nominal_impedance):
    """Simplify electrical input definition to input voltage."""
    val, type = excitation
    if type == "Wn":
        input_voltage = (val * nominal_impedance) ** 0.5
    elif type == "W":
        input_voltage = (val * Rdc) ** 0.5
    elif type == "V":
        input_voltage = val
    else:
        print("Input options are [float, ""V""], \
              [float, ""W""], [float, ""Wn"", float]")
        return None
    return input_voltage