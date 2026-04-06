import numpy as np
from typing import Tuple, Any
from config.physics import air

def calculate_air_mass(sd: float) -> float:
    """
    Calculate the air mass on a diaphragm.

    This represents the difference between the mechanical mass of the moving 
    parts (Mmd) and the total moving mass including air load (Mms).

    :param sd: Diaphragm effective surface area in m².
    :return: Air mass in kg.
    """
    return 1.13 * (sd) ** (3 / 2)


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
    :param sd: Diaphragm effective surface area in m².
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
