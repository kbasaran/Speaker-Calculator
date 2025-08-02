#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Mar  4 18:41:51 2024

@author: kerem
"""

import numpy as np
import sympy as smp
import sympy.physics.mechanics as mech
from sympy.abc import t
from sympy.solvers import solve
from scipy import signal
import time
import matplotlib.pyplot as plt
plt.grid()

start_time = time.perf_counter()

# Static symbols
Mms, M2, Mpr = smp.symbols("M_ms, M_2, M_pr", real=True, positive=True)
Kms, K2, Kpr = smp.symbols("K_ms, K_2, K_pr", real=True, positive=True)
Rms, R2, Rpr = smp.symbols("R_ms, R_2, R_pr", real=True, positive=True)
P0, gamma, Vb = smp.symbols("P_0, gamma, V_b", real=True, positive=True)
Sd, Spr, Bl, Re, Rs_source = smp.symbols("S_d, S_pr, Bl, R_e, Rs_source", real=True, positive=True)

# Dynamic symbols
x1, x2 = mech.dynamicsymbols("x(1:3)")
xpr = mech.dynamicsymbols("x_pr")
Vsource = mech.dynamicsymbols("V_source", real=True)

# Direction coefficient for passive radiator
dir_pr = smp.symbols("direction_pr")
# 1 if same direction with speaker, 0 if orthogonal, -1 if reverse direction

# Derivatives
x1_t, x1_tt = smp.diff(x1, t), smp.diff(x1, t, t)
x2_t, x2_tt = smp.diff(x2, t), smp.diff(x2, t, t)
xpr_t, xpr_tt = smp.diff(xpr, t), smp.diff(xpr, t, t)

eqns = [

        (- Mms * x1_tt
         - Rms*(x1_t - x2_t) - Kms*(x1 - x2)
         - P0 * gamma / Vb * (Sd * x1 + Spr * xpr) * Sd
         + (Vsource - Bl*(x1_t - x2_t)) / (Rs_source + Re) * Bl
         ),

        (- M2 * x2_tt - R2 * x2_t - K2 * x2
         - Rms*(x2_t - x1_t) - Kms*(x2 - x1)
         + P0 * gamma / Vb * (Sd * x1 + Spr * xpr) * Sd
         + P0 * gamma / Vb * (Sd * x1 + Spr * xpr) * Spr * dir_pr
         - (Vsource - Bl*(x1_t - x2_t)) / (Rs_source + Re) * Bl
         ),

        (- Mpr * xpr_tt - Rpr * xpr_t - Kpr * xpr
         - P0 * gamma / Vb * (Sd * x1 + Spr * xpr) * Spr
         ),

        ]

# define state space system
state_vars = [x1, x1_t, x2, x2_t, xpr, xpr_t]
input_vars = [Vsource]
state_diffs = [var.diff() for var in state_vars]

sols = solve(eqns, [state_var for state_var in state_diffs if state_var not in state_vars], as_dict=True)
sols[x1_t] = x1_t
sols[x2_t] = x2_t
sols[xpr_t] = xpr_t


def make_state_matrix_A():
    matrix = []
    for state_diff in state_diffs:
        if state_diff in state_vars:
            coeffs = [int(state_vars[i] == state_diff) for i in range(len(state_vars))]
        else:
            coeffs = [sols[state_diff].coeff(state_var) for state_var in state_vars]
        matrix.append(coeffs)
    return smp.Matrix(matrix)


def make_state_matrix_B():
    matrix = []
    for state_diff in state_diffs:
        coeffs = [sols[state_diff].coeff(input_var) for input_var in input_vars]
        matrix.append(coeffs)
    return smp.Matrix(matrix)


symbolic_ss = {"a": make_state_matrix_A(),  # system matrix
               "b": make_state_matrix_B(),  # input matrix
               "c": smp.Matrix(smp.eye(len(state_vars))),  # give all state vars in output
               "d": smp.Matrix([0]*len(state_vars)),  # no feedforward
               }  # state space model ready


values = {Bl: 2,
          Re: 4,
          Sd: 52e-4,

          Mms: 4.424e-3,
          Kms: 1746,
          Rms: 0.695,

          M2: 10e-3,
          K2: 1e3,
          R2: 4,

          Mpr: 20e-3,
          Kpr: 5e3,
          Rpr: 1,
          Spr: 30e-4,
          dir_pr: 1,

          P0: 101325,
          gamma: 1.401,
          Vb: 2e-3,
          Rs_source: 0,
          }


def substitute_symbols_in_ss(values, a, b, c, d):
    return (np.array(a.subs(values)).astype(float),
            np.array(b.subs(values)).astype(float),
            np.array(c.subs(values)).astype(float),
            np.array(d.subs(values)).astype(float),
            )


def calculate_transfer_functions(symbolic_ss: dict, values: dict) -> list:
    print(f"Substituting values in SS model starting: {(time.perf_counter() - start_time) * 1000:.1f}ms")
    ss = substitute_symbols_in_ss(values, *symbolic_ss.values())
    print(f"SS model ready in {(time.perf_counter() - start_time) * 1000:.1f}ms")
    sys = signal.StateSpace(*ss)
    transfer_function_whole_system = sys.to_tf()
    transfer_functions = {}
    for i, num in enumerate(transfer_function_whole_system.num):
        transfer_functions[state_vars[i]] = signal.TransferFunction(num, transfer_function_whole_system.den)
    return transfer_functions


def calculate_freq_responses(f: list, transfer_functions: list) -> (list, list):
    resps = {}
    w = f * 2 * np.pi
    for key, val in transfer_functions.items():
        _, resp = np.abs(signal.freqresp(val, w))
        resps[key] = resp
    return w, resps


def calculate_SPL_from_diaphragm_velocity(Sd, f, diaphragm_velocity_RMS, RHO):
    # SPL calculation with simplified radiation impedance * acceleration
    a = np.sqrt(Sd/np.pi)  # piston radius
    w = 2 * np.pi * f
    p0 = 0.5 * 1j * w * RHO * a**2 * diaphragm_velocity_RMS
    pref = 2e-5
    return 20*np.log10(np.abs(p0)/pref)


def calculate_SPL_for_Xmax(Sd, f, Xmax, RHO):
    # SPL calculation for maximum displacement
    a = np.sqrt(Sd/np.pi)  # piston radius
    w = 2 * np.pi * f
    x1_max_rms_array = [np.array(Xmax/2**0.5)] * len(w)
    x1t_max_rms_array = np.abs(x1_max_rms_array * w * 1j)
    p0_xmax_limited = 0.5 * 1j * w * RHO * a**2 * x1t_max_rms_array
    pref = 2e-5
    return 20*np.log10(np.abs(p0_xmax_limited)/pref)


def calculate_Icoil(Rs_source, Re, Bl, x_t, V_in):
    """
    Parameters
    ----------
    Rs_source : series resistance before the speaker
    Re : coil resistance
    Bl : B * l
    x_t : diaphragm velocity, RMS
    Vin : Voltage at source

    Returns
    -------
    Current going through the circuit of amplifier to speaker and coil

    """

    return (V_in - Bl * x_t) / (Rs_source + Re)


def calculate_Vcoil(Rs_source, Re, Bl, x_t, V_in):
    """
    Parameters
    ----------
    Re : coil resistance
    Bl : B * l
    x_t : diaphragm velocity, RMS
    Vin : Voltage at source

    Returns
    -------
    Voltage accross coil

    """
    Icoil = calculate_Icoil(Rs_source, Re, Bl, x_t, V_in)

    return Icoil * Re + Bl * x_t


def calculate_Zcoil(Rs_source, Re, Bl, x_t, V_in):
    """
    Parameters
    ----------
    Rs_source : series resistance before the speaker
    Re : coil resistance
    Bl : B * l
    x_t : diaphragm velocity, RMS, 1D array
    Vin : Voltage at source

    Returns
    -------
    Type: imaginary float
    Coil impedance

    """
    Icoil = calculate_Icoil(Rs_source, Re, Bl, x_t, V_in)
    Vcoil = calculate_Vcoil(Icoil, Re, Bl, x_t, V_in)
    return Vcoil / Icoil


if __name__ == "__main__":

    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True)
    transfer_functions = calculate_transfer_functions(symbolic_ss, values)
    print(f"Transfer functions ready in {(time.perf_counter() - start_time) * 1000:.1f}ms")

    f = 250 * 2**np.arange(-3, 1/12, step=1/46)
    w, resps = calculate_freq_responses(f, transfer_functions)
    z_coil = calculate_Zcoil(values[Rs_source], values[Re], values[Bl], resps[x1_t], 1)
    print(f"All calculations ready in {(time.perf_counter() - start_time) * 1000:.1f}ms")

    ax1.semilogx(f, resps[x1] * 1e3)
    ax1.grid()
    ax1.set_title("x1 (mm)")
    # print(f, resps[x1])

    ax2.semilogx(f, z_coil)
    ax2.set_title("Z (ohm)")
    ax2.grid()
