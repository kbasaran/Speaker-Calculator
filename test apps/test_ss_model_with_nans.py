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


ss_a = make_state_matrix_A(state_vars, state_diffs, sols)  # system matrix
ss_b = make_state_matrix_B(state_diffs, input_vars, sols)  # input matrix
ss_d = np.zeros(1)  # no feedforward

symbolic_ss = list()
ss_c_all = np.eye((len(state_vars)))
for i, state_var in enumerate(state_vars):
    ss_c = ss_c_all[i, :]
    symbolic_ss.append([ss_a, ss_b, ss_c, ss_d])


symbols = {key: val for (key, val) in locals().items()
           if isinstance(val, smp.Symbol)}

symbols_to_values = {
    M1: 9,
    K1: 1,
    R1: 1,
    
    M2: 3,
    K2: 2,
    R2: 1,
    
    K3: 2,
    }

ss_matrices = [list(),]
ss_matrices[0] = (np.array(symbolic_ss[0][0].subs(symbols_to_values)).astype(float),
                  np.array(symbolic_ss[0][1].subs(symbols_to_values)).astype(float),
                  symbolic_ss[0][2],
                  symbolic_ss[0][3],
                  )
print(ss_matrices[0])

ss_model = signal.StateSpace(*ss_matrices[0])
freqs = np.arange(1, 100) / 100
w, x1 = signal.freqresp(ss_model, w=2*np.pi*freqs)
plt.semilogx(freqs, np.abs(x1))