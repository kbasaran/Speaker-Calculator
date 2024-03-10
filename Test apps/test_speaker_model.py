#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Mar  4 18:41:51 2024

@author: kerem
"""

#!/usr/bin/env python
# coding: utf-8

# **Double Pendulum Self Trial**
# https://www.youtube.com/watch?v=8ZZDNd4eyVI

# In[1]:

import numpy as np
import sympy as smp
import sympy.physics.mechanics as mech
from sympy.abc import t
from sympy.solvers import solve
from scipy import signal
import matplotlib.pyplot as plt
plt.grid()

# Static symbols
Mms, M2, Mpr = smp.symbols("M_ms, M_2, M_pr", real=True, positive=True)
Kms, K2, Kpr = smp.symbols("K_ms, K_2, K_pr", real=True, positive=True)
Rms, R2, Rpr = smp.symbols("R_ms, R_2, R_pr", real=True, positive=True)
P0, gamma, Vb = smp.symbols("P_0, gamma, V_b", real=True, positive=True)
Sd, Spr, Bl, Re, Rs_source = smp.symbols("S_d, S_pr, Bl, R_e, R_source", real=True, positive=True)
# Dynamic symbols
x1, x2 = mech.dynamicsymbols("x(1:3)")
xpr = mech.dynamicsymbols("x_pr")
Vsource = mech.dynamicsymbols("V_source", real=True)
# Direction coefficient for passive radiator
dir_pr = smp.symbols("direction_pr")  # 1 if same direction with speaker, 0 if orthogonal, -1 if reverse direction
# Derivatives
x1_t, x1_tt = smp.diff(x1, t), smp.diff(x1, t, t)
x2_t, x2_tt = smp.diff(x2, t), smp.diff(x2, t, t)
xpr_t, xpr_tt = smp.diff(xpr, t), smp.diff(xpr, t, t)

# temporaily disable radiator
xpr, xpr_t, xpr_tt = 0, 0, 0

eqns = [(- Mms * x1_tt
         - Rms*(x1_t - x2_t) - Kms*(x1 - x2)
         - P0 * gamma / Vb * (Sd * x1 + Spr * xpr) * Sd
         + (Vsource - Bl*(x1_t - x2_t)) / (Rs_source + Re) * Bl
         ),
        
        (- M2 * x2_tt - R2 * x2_t - K2 * x2
         - Rms*(x2_t - x1_t) - Kms*(x2 - x1)
         + P0 * gamma / Vb * (Sd * x1 + Spr * xpr) * Sd
         - (Vsource - Bl*(x1_t - x2_t)) / (Rs_source + Re) * Bl
         ),

        ]

# define state space system
state_vars = [x1, x1_t, x2, x2_t]
input_vars = [Vsource]
state_diffs = [x1_t, x1_tt, x2_t, x2_tt]
output_vector = [x1, x1_t, x1_tt, x2, x2_t, x2_tt]

sols = solve(eqns, [state_var for state_var in state_diffs if state_var not in state_vars], as_dict=True)
sols[x1_t] = x1_t
sols[x2_t] = x2_t

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
               }

values = {Bl: 2,
          Re: 4,
          Sd: 52e-4,
          Mms: 4.424e-3,
          Kms: 1746,
          Rms: 0.695,
          M2: 10e-3,
          K2: 1e3,
          R2: 4,
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


def make_tfs() -> list:
    ss = substitute_symbols_in_ss(values, *symbolic_ss.values())
    sys = signal.StateSpace(*ss)
    tf_all = sys.to_tf()
    tf_separates = {}
    for i, num in enumerate(tf_all.num):
        tf_separates[state_vars[i]] = signal.TransferFunction(num, tf_all.den)
    return tf_separates

tf_separates = make_tfs()

f = 250 * 2**np.arange(-3, 1/12, step=1/3)

def make_freq_responses(f, tf_separates):
    resps = {}
    w = f * 2 * np.pi
    for key, val in tf_separates.items():
        _, resp = np.abs(signal.freqresp(val, w))
        resps[key] = resp
    return w, resps

w, resps = make_freq_responses(f, tf_separates)

plt.semilogx(f, resps[x1])
print(f, resps[x1])
