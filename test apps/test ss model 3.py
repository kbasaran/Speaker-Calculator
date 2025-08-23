import dataclasses as dtc
from functools import cached_property
import numpy as np
import sympy as smp
import sympy.physics.mechanics as mech
from sympy.solvers import solve
from scipy import signal
from sympy.abc import t



def make_state_matrix_A(state_vars, state_diffs, sols):
    # State matrix

    matrix = []
    for state_diff in state_diffs:
        # Each row corresponds to the differential of a state variable
        # as listed in state_diffs
        # e.g. x1_t, x1_tt, x2_t, x2_tt

        # find coefficients of each state variable
        if state_diff in state_vars:
            coeffs = [int(state_vars[i] == state_diff) for i in range(len(state_vars))]
        elif state_diff in sols.keys():
            coeffs = [sols[state_diff].coeff(state_var) for state_var in state_vars]
        else:
            coeffs = np.zeros(len(state_vars))

        matrix.append(coeffs)

    return smp.Matrix(matrix)


def make_state_matrix_B(state_vars, state_diffs, input_vars, sols):
    # Input matrix

    matrix = []
    for state_diff in state_diffs:
        # Each row corresponds to the differential of a state variable
        # as listed in state_diffs
        # e.g. x1_t, x1_tt, x2_t, x2_tt
        
        # # find coefficients of each state variable
        if state_diff not in sols.keys():
            coeffs = np.zeros(len(input_vars))
        else:
            coeffs = [sols[state_diff].coeff(input_var) for input_var in input_vars]

        # # find coefficients of each state variable
        # if state_diff in sols.keys():
        #     coeffs = [sols[state_diff].coeff(input_var) for input_var in input_vars]
        # else:
        #     coeffs = np.zeros(len(input_vars))

        matrix.append(coeffs)
        
    return smp.Matrix(matrix)



Mms, M2, Mpr = smp.symbols("M_ms, M_2, M_pr", real=True, positive=True)
Kms, K2, Kpr = smp.symbols("K_ms, K_2, K_pr", real=True, positive=True)
Rms, R2, Rpr = smp.symbols("R_ms, R_2, R_pr", real=True, positive=True)
Kair, Vba, Rb = smp.symbols("Kair, V_ba, R_b", real=True, positive=True)
Sd, Spr, Bl, Re, R_serial = smp.symbols("S_d, S_pr, Bl, R_e, R_serial", real=True, positive=True)
# Direction coefficient for passive radiator
# 1 if same direction with speaker, 0 if orthogonal, -1 if reverse direction

# Dynamic symbols
x1, x2 = mech.dynamicsymbols("x(1:3)")
xpr = mech.dynamicsymbols("x_pr")
p = mech.dynamicsymbols("p")
Vsource = mech.dynamicsymbols("V_source", real=True)

# Derivatives
x1_t, x1_tt = smp.diff(x1, t), smp.diff(x1, t, t)
x2_t, x2_tt = smp.diff(x2, t), smp.diff(x2, t, t)
xpr_t, xpr_tt = smp.diff(xpr, t), smp.diff(xpr, t, t)
# p_t, p_tt = smp.diff(p, t), smp.diff(p, t, t)

# define state space system
eqns = [    

        (
         - Mms * x1_tt
         - Kms * (x1 - x2)

         + p * Sd
         + Vsource / (Re + R_serial) * Bl
         ),

        
        # (
        #  + p
        #  + Kair / Vba * Sd * x1
        #  ),
        
        ]

state_vars = [x1, x1_t]  # state variables
input_vars = [Vsource]  # input variables
state_diffs = [var.diff() for var in state_vars]  # state differentials

for i, eqn in enumerate(eqns):
    eqns[i] = eqn.subs(p, Kair / Vba * Sd * x1)
    

# solve for state differentials
sols = solve(eqns, [var for var in state_diffs if var not in state_vars], as_dict=True)  # heavy task, slow
if len(sols) == 0:
    raise RuntimeError("No solution found for the equation.")


# ---- SS model with symbols
A_sym = make_state_matrix_A(state_vars, state_diffs, sols)  # system matrix
B_sym = make_state_matrix_B(state_vars, state_diffs, input_vars, sols)  # input matrix
C = dict()  # one per state variable -- scipy state space supports only a rank of 1 for output
for i, state_var in enumerate(state_vars):
    C[state_var] = np.eye(len(state_vars))[i]
D = np.zeros(len(input_vars))  # no feedforward

print(A_sym)
