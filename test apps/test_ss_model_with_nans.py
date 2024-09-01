#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Sep  1 14:05:29 2024

@author: kerem
"""

import numpy as np
from sympy.abc import t
import sympy as smp
import sympy.physics.mechanics as mech
from sympy.solvers import solve
from scipy import signal
import matplotlib.pyplot as plt


def make_state_matrix_A(state_vars, state_diffs, sols):
    # State matrix

    matrix = []
    for state_diff in state_diffs:
        # Each row corresponds to the differential of a state variable
        # as listed in state_diffs
        # e.g. x1_t, x1_tt, x2_t, x2_tt

        # find coefficients of each state variable
        if state_diff in state_vars:
            coeffs = [int(state_vars[i] == state_diff)
                      for i in range(len(state_vars))]
        else:
            coeffs = [sols[state_diff].coeff(state_var)
                      for state_var in state_vars]

        matrix.append(coeffs)

    return smp.Matrix(matrix)


def make_state_matrix_B(state_diffs, input_vars, sols):
    # Input matrix

    matrix = []
    for state_diff in state_diffs:
        # Each row corresponds to the differential of a state variable
        # as listed in state_diffs
        # e.g. x1_t, x1_tt, x2_t, x2_tt

        # find coefficients of each state variable
        coeffs = [sols[state_diff].coeff(input_var)
                  for input_var in input_vars]

        matrix.append(coeffs)

    return smp.Matrix(matrix)


M1, M2 = smp.symbols("M(1:3)", real=True, positive=True)
K1, K2, K3 = smp.symbols("K(1:4)", real=True, positive=True)
R1, R2 = smp.symbols("R_1, R_2", real=True, positive=True)

# Dynamic symbols
x1, x2 = mech.dynamicsymbols("x(1:3)")
F_in = mech.dynamicsymbols("F_in", real=True)

# Derivatives
x1_t, x1_tt = smp.diff(x1, t), smp.diff(x1, t, t)
x2_t, x2_tt = smp.diff(x2, t), smp.diff(x2, t, t)

eqns = [

    (  F_in
     - M1 * x1_tt
     - K1 * x1
     - R1 * x1_t
     - K2 * (x1 - x2)
     - R2 * (x1_t - x2_t)
     ),

    (- M2 * x2_tt
     - K2 * (x2 - x1)
     - K3 * x2
     - R2 * (x2_t - x1_t)
     ),

]

state_vars = [x1, x1_t, x2, x2_t]

# define input variables
input_vars = [F_in]

# define state differentials
state_diffs = [var.diff() for var in state_vars]

# solve for state differentials
# heavy task, slow
sols = solve(
    eqns, [var for var in state_diffs if var not in state_vars], as_dict=True)
if len(sols) == 0:
    raise RuntimeError("No solution found for the equation.")

# correction to exact variables in solutions
sols[x1_t] = x1_t
sols[x2_t] = x2_t

# SS model with symbols
ss_matrices_sym = {
    "A": make_state_matrix_A(state_vars, state_diffs, sols),  # system matrix
    "B": make_state_matrix_B(state_diffs, input_vars, sols),  # input matrix
    "C": dict(),
    "D": np.zeros(1),  # no feedforward
    }

for i, state_var in enumerate(state_vars):
    ss_c = np.zeros(4)
    ss_c[i] = 1
    ss_matrices_sym["C"][state_var] = ss_c

symbols = {key: val for (key, val) in locals().items() if isinstance(val, smp.Symbol)}


# ---- Substitute float values into SS model

# symbols_to_values = {
#     M1: 9,
#     K1: 1,
#     R1: 1,
    
#     M2: 3,
#     K2: 2,
#     R2: 1,
    
#     K3: 2,
#     }

# ss_matrices = {
#     "A": np.array(ss_matrices_sym["A"].subs(symbols_to_values)).astype(float),
#     "B": np.array(ss_matrices_sym["B"].subs(symbols_to_values)).astype(float),
#     "C": ss_matrices_sym["C"],  # no symbols here already
#     "D": ss_matrices_sym["D"],  # no symbols here already
#     }

# ss_model = signal.StateSpace(*[ss_matrices["A"],
#                               ss_matrices["B"],
#                               ss_matrices["C"][x1],
#                               ss_matrices["D"]],
#                               )
# freqs = np.arange(1, 100) / 100
# w, x1 = signal.freqresp(ss_model, w=2*np.pi*freqs)
# plt.semilogx(freqs, np.abs(x1))


# ---- Substitute nan value into SS model

# assume x2 is not mobile

symbols_to_values = {
    M1: 9,
    K1: 1,
    R1: 1,
    
    M2: 3,
    K2: 2,
    R2: 1,
    
    K3: np.nan,  # between x2 and ground - no movement, no need to define
    }

ss_matrices = {
    "A": np.array(ss_matrices_sym["A"].subs(symbols_to_values)).astype(float),
    "B": np.array(ss_matrices_sym["B"].subs(symbols_to_values)).astype(float),
    "C": ss_matrices_sym["C"],  # no symbols here already
    "D": ss_matrices_sym["D"],  # no symbols here already
    }

ss_matrices["A"][2:4, :] = 0  # fill the rows that return x2 and x2_t with zeros
ss_matrices["A"][:, 2:4] = 0  # fill the rows that receive x2 and x2_t with zeros

ss_model = signal.StateSpace(*[ss_matrices["A"],
                              ss_matrices["B"],
                              ss_matrices["C"][x1_t],
                              ss_matrices["D"]],
                              )
print(ss_model)
freqs = np.arange(1, 100) / 100
w, x1 = signal.freqresp(ss_model, w=2*np.pi*freqs)
plt.semilogx(freqs, np.abs(x1))
