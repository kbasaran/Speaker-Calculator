# This file is part of Speaker Calculator - Loudspeaker design and calculations tool
# Copyright (C) 2026 - Kerem Basaran
# https://github.com/kbasaran
__email__ = "kbasaran@gmail.com"

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import numpy as np
from typing import Tuple, Any

import sympy as smp

from config.physics import air

def calculate_air_mass(sd: float) -> float:
    """
    Calculate the air mass on a diaphragm.

    This represents the difference between the mechanical mass of the moving 
    parts (Mmd) and the total moving mass including air load (Mms).

    :param sd: Diaphragm effective surface area in m².
    :return: Air mass in kg.
    """
    # Low-frequency co-vibrating air mass on BOTH faces of a flat circular piston:
    # 2 * (8/3) * rho * a**3 with radius a = sqrt(sd/pi), i.e.
    # 2*(8/3)*rho/pi**1.5 * sd**1.5. Coefficient ~= 1.134 for air at 25 C (was
    # hardcoded 1.13); derived from air.RHO so it tracks the configured air density.
    return 2 * (8 / 3) * air.RHO / np.pi**1.5 * sd ** (3 / 2)


def calculate_lm(bl: float, re: float, mms: float, sd: float) -> float:
    """
    Calculate Lm@Re, 1W, 1m (Efficiency/Motor strength).

    :param bl: Motor force factor (B*l) in N/A.
    :param re: Voice coil DC resistance in Ohms.
    :param mms: Total moving mass in kg.
    :param sd: Diaphragm effective surface area in m².
    :return: Sensitivity in dB.
    """
    if sd == 0:
        return -np.inf
    elif sd < 0:
        raise ValueError(f"Surface area cannot be negative: {sd}")

    w_ref = 10 ** -12
    i_1w_per_m2 = air.RHO * bl ** 2 * sd ** 2 / air.c_air / re / mms ** 2 / 2 / np.pi
    p_over_i_half_space = 1 / (2 * np.pi)  # m²
    return 10 * np.log10(i_1w_per_m2 * p_over_i_half_space / w_ref)


def calculate_coil_to_bottom_plate_clearance(x_peak: float) -> float:
    """
    Calculate proposed clearance for a given peak displacement.

    All values should be in SI units (meters).

    :param x_peak: Peak displacement in meters.
    :return: Minimum clearance to bottom plate in meters.
    """
    proposed_clearance = 1e-3 + (x_peak - 3e-3) / 5
    return x_peak + proposed_clearance


def calculate_spl(xty: Tuple[Any, Any], sd: float) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate SPL using simplified radiation impedance * acceleration.

    :param xty: Tuple containing (frequencies, RMS velocities).
    :param sd: Diaphragm effective surface area in m². Use 1 if xty is volume velocity U.
    :return: Tuple of (frequencies, SPL values in dB).
    """
    a = np.sqrt(sd / np.pi)  # piston radius
    freqs = np.array(xty[0]).flatten()
    # p0: acoustic pressure
    p0 = 0.5 * 1j * freqs * 2 * np.pi * air.RHO * a ** 2 * np.array(xty[1]).flatten()
    pref = 2e-5
    spl = 20 * np.log10(np.abs(p0) / pref)
    return freqs, spl


def calculate_voltage(excitation_value: float, excitation_type: str, re: float = None, rnom: float = None) -> float:
    """
    Simplify electrical input definition to a voltage value.

    :param excitation_value: Value of the excitation (V, W, or Wn).
    :param excitation_type: Type of excitation ('V', 'W', or 'Wn').
    :param re: Voice coil DC resistance in Ohms.
    :param rnom: Nominal impedance in Ohms.
    :return: Input voltage in Volts.
    """
    input_voltage = float("nan")
    match excitation_type:
        case "Wn":
            if not rnom:
                raise ValueError("Need to provide nominal impedance to calculate Wn")
            input_voltage = (excitation_value * rnom) ** 0.5

        case "W":
            if not re:
                raise ValueError("Need to provide Re to calculate W")
            input_voltage = (excitation_value * re) ** 0.5

        case "V":
            input_voltage = excitation_value

        case _:
            raise ValueError(f"excitation type must be one of (V, W, Wn), but got: {excitation_type}")

    return float(input_voltage)


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


def make_output_matrices(output_exprs, state_vars, input_vars):
    # Output matrix (C) and feedforward matrix (D)

    C, D = [], []
    for output_expr in output_exprs:
        # Each row corresponds to an output, as listed in output_exprs.
        # An output has to be a linear combination of the state variables
        # and the input variables, so that it can be expressed with
        # constant coefficients.
        expanded = smp.expand(output_expr)
        C.append([expanded.coeff(state_var) for state_var in state_vars])
        D.append([expanded.coeff(input_var) for input_var in input_vars])

    return smp.Matrix(C), smp.Matrix(D)


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
