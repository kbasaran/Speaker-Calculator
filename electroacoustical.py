#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Aug  6 20:23:15 2023

@author: kerem
"""
import dataclasses as dtc
from functools import cached_property
import numpy as np
import sympy as smp
import sympy.physics.mechanics as mech
from sympy.solvers import solve
from scipy import signal
import pandas as pd
from sympy.abc import t


"""
https://www.micka.de/en/introduction.php

Glossary of Symbols:

fS: Resonance frequency of driver

VAS: Volume of air having the same acoustic compliance as driver suspension

QTS: total Q of driver at fS

RE: dc resistance of driver voice coil

LE: voice-coil inductance
(it is only used for voice-coil impedance diagram)

QMS: Q of driver at fS considering driver nonelectrical losses only

QES: Q of driver at fS considering electrical resistance RE only

Rg: output resistance of source (represents any resistances between source and driver - for example resistance of crossover inductor)

QE: Q of driver at fS considering system electrical resistance RE and Rg only

QT: total Q of driver at fS including all system resistances

QL: enclosure Q at fB resulting from leakage losses

fB: resonance frequency of vented enclosure

QTC: total Q of system at fC including all system resistances

fC: resonance frequency of closed box

VB: Net internal volume of enclosure (without port volume!)

RAP: Acoustic resistance of port losses

RAL: Acoustic resistance of enclosure losses caused by leakage

RAB: Acoustic resistance of enclosure losses caused by internal energy absorption

Pe: nominal electrical input power (defined through Re): Pe=Re*(eg/(Rg+Re))2

eg: open-circuit output voltage of source
"""


"""
from another source:
    
Ql is the system's Q at Fb due to leakage losses (sealing of the cabinet, etc.).

Qa is the system's Q at Fb due to absorption losses.

Qp is the system's Q at Fb due to port losses (turbulence, viscosity, etc.).

"""

def calculate_air_mass(Sd: float) -> float:
    """
    Air mass on diaphragm; the difference between Mms and Mmd.
    m2 in, kg out
    """
    return 1.13*(Sd)**(3/2)


def calculate_Lm(Bl, Re, Mms, Sd, RHO=1.1839, c_air=(101325 * 1.401 / 1.1839)**0.5):
    "Calculate Lm@Re, 1W, 1m."
    if Sd == 0:
        return -np.inf
    elif Sd < 0:
        raise RuntimeError("Surface ares cannot have a negative value: " + Sd)

    w_ref = 10**-12
    I_1W_per_m2 = RHO * Bl**2 * Sd**2 / c_air / Re / Mms**2 / 2 / np.pi
    P_over_I_half_space = 1/2/np.pi  # m²
    return 10 * np.log10(I_1W_per_m2 * P_over_I_half_space / w_ref)


def calculate_coil_to_bottom_plate_clearance(Xpeak):
    """
    Proposed clearance for given Xpeak value.

    All values in basic SI units.
    """
    proposed_clearance = 1e-3 + (Xpeak - 3e-3) / 5
    return Xpeak + proposed_clearance


def calculate_SPL(settings: object, xty: tuple, Sd: float):
    # SPL calculation with simplified radiation impedance * acceleration
    # xy: RMS velocities per frequency
    a = np.sqrt(Sd/np.pi)  # piston radius
    freqs = np.array(xty[0]).flatten()
    p0 = 0.5 * 1j * freqs*2*np.pi * settings.RHO * a**2 * np.array(xty[1]).flatten()
    pref = 2e-5
    SPL = 20*np.log10(np.abs(p0)/pref)
    return freqs, SPL


@dtc.dataclass
class Wire:
    name: str
    w_avg: float
    h_avg: float
    w_max: float
    resistance: float  # ohm/m
    mass_density: float  # kg/m
    reduce_per_layer: float = 0


@dtc.dataclass
class Coil:
    carrier_OD: float
    wire: Wire | pd.Series
    N_windings: tuple
    w_stacking_coef: float

    def length_of_one_turn(self, i_layer):
        """Calculate the length of one turn of wire on a given coil layer."""
        if i_layer == 0:
            turn_radius_wire_center_to_axis = self.carrier_OD/2 + self.wire.w_avg/2
        else:
            turn_radius_wire_center_to_axis = (self.carrier_OD/2 + self.wire.w_avg/2
                                               + (self.w_stacking_coef * i_layer * self.wire.w_avg)
                                               )
        # pi/4 is stacking coefficient for ideal circular wire
        return 2 * np.pi * turn_radius_wire_center_to_axis

    def total_wire_length(self):
        return sum([self.length_of_one_turn(i) * self.N_windings[i] for i in range(self.N_layers)])

    def __post_init__(self):
        assert all([i > 0 for i in self.N_windings])
        self.N_layers = len(self.N_windings)
        self.h_winding = self.wire.h_avg * self.N_windings[0]
        self.mass = self.total_wire_length() * self.wire.mass_density
        self.Re = self.total_wire_length() * self.wire.resistance
        self.w_max = self.wire.w_max * (1 + (self.N_layers - 1) * self.w_stacking_coef)
        self.name = (str(self.N_layers) + "L " + self.wire.name).strip()


def wind_coil(wire: Wire,
              N_layers: int,
              w_stacking_coef: float,
              carrier_OD: float,
              h_winding_target: float,
              reduce_per_layer: float,
              ) -> Coil:
    "Create coil object based on given data."

    def N_winding_for_single_layer(i_layer: int) -> int:
        "Calculate the number of windings that fit on one layer of coil."
        # 1 winding less on each stacked layer if stacking coefficient is less than or equal to 0.9
        n_winding = h_winding_target / wire.h_avg - i_layer * reduce_per_layer
        return round(n_winding)

    N_windings = [N_winding_for_single_layer(i_layer) for i_layer in range(N_layers)]
    if any([N_winding < 1 for N_winding in N_windings]):
        raise ValueError("Some layers were impossible")

    return Coil(carrier_OD, wire, N_windings, w_stacking_coef)


def calculate_voltage(excitation_value, excitation_type, Re=None, Rnom=None):
    "Simplify electrical input definition to a voltage value."
    match excitation_type:

        case "Wn":
            if not Rnom:
                raise ValueError("Need to provide nominal impedance to calculate Wn")
            else:
                input_voltage = (excitation_value * Rnom) ** 0.5

        case "W":
            if not Re:
                raise ValueError("Need to provide Re to calculate W")
            else:
                input_voltage = (excitation_value * Re) ** 0.5

        case "V":
            input_voltage = excitation_value

        case _:
            raise ValueError("excitation type must be one of (V, W, Wn)")

    return input_voltage


@dtc.dataclass
class Motor:
    coil: Coil
    Bavg: float
    h_top_plate: float = None
    airgap_clearance_inner: float = None
    airgap_clearance_outer: float = None
    h_former_under_coil: float = None

    """
    Coil and motor parameters of speaker.

    Parameters
    ----------
    coil : Coil
        Coil winding object.
    Bavg : float
        Average magnetic field on the total height of coil in rest position.
    """


@dtc.dataclass
class SpeakerDriver:
    """
    Speaker driver class.
    Mostly to carry data. It also does some Thiele & Small calculations.
    Does not make frequency dependent calculations such as SPL, Impedance.
    """
    settings: object
    fs: float
    Sd: float
    Qms: float
    Bl: float = None  # provide only if motor is None
    Re: float = None  # provide only if motor is None
    Mms: float = None  # provide only if both motor and Mmd are None
    Mmd: float = None  # provide only if both motor and Mms are None
    motor: None | Motor = None  # None or 'Motor' instance
    dead_mass: float = None  # provide only if motor is 'Motor' instance
    Rs: float = 0  # resistance between the coil and the speaker terminals (leadwire etc.). provide only if motor is 'Motor' instance.
    Xpeak: float = None

    def __post_init__(self):
        if self.motor is None and self.Rs != 0:
            raise RuntimeError("Do not define leadwire resistance Rs when Re is already defined.")
        if isinstance(self.motor, Motor) and self.dead_mass is not None:
            available_from_Motor_object = ("Bl", "Re")
            if not all([getattr(self, val) is None for val in available_from_Motor_object]):
                raise RuntimeError("These attributes should not be specified when motor is already specified:"
                                   f"\n{available_from_Motor_object}")
            self.Bl = self.motor.coil.h_winding * self.motor.Bavg
            self.Re = self.motor.coil.Re + self.Rs

        # derived parameters
        # Mms and Mmd
            try:
                if "Mms" in locals().keys():
                    raise RuntimeError("Double definition. 'Mms' should not be defined in object instantiation"
                                       " when 'motor' is already defined.")
                self.Mmd = self.dead_mass + self.motor.coil.mass
                self.Mms = self.Mmd + calculate_air_mass(self.Sd)
            except NameError:
                raise RuntimeError("Unable to calculate 'Mms' and/or 'Mmd' with known parameters.")
        elif self.Mms is not None:
            if self.Mmd is not None:
                raise RuntimeError("Not allowed to define both Mmd and Mms in 'SpeakerDriver' object instantion.")
            self.Mmd = self.Mms - calculate_air_mass(self.Sd)
        elif self.Mmd is not None:
            self.Mms = self.Mmd + calculate_air_mass(self.Sd)
        else:
            raise ValueError("Insufficient parameters. Define [motor, dead_mass], Mmd or Mms.")
        
        self.Kms = self.Mms * (self.fs * 2 * np.pi)**2
        self.Rms = (self.Mms * self.Kms)**0.5 / self.Qms
        self.Ces = self.Bl**2 / self.Re
        self.Qts = (self.Mms * self.Kms)**0.5 / (self.Rms + self.Ces)
        self.Qes = (self.Mms * self.Kms)**0.5 / self.Ces
        zeta_speaker = 1 / 2 / self.Qts
        self.fs_damped = self.fs * (1 - 2 * zeta_speaker**2)**0.5  # complex number if overdamped system
        self.Lm = calculate_Lm(self.Bl, self.Re, self.Mms, self.Sd, self.settings.RHO, self.settings.c_air)  # sensitivity per W@Re
        self.Vas = self.settings.Kair / self.Kms * self.Sd**2

    def get_summary(self) -> list:
        "Give a summary for acoustical and mechanical properties as two items of a list."
        
        # Make a string for acoustical summary
        summary_ace = f"Re: {self.Re:.3g} ohm    Lm: {self.Lm:.2f} dBSPL    Bl: {self.Bl:.4g} Tm"
        summary_ace += f"\nQts: {self.Qts:.3g}    Qes: {self.Qes:.3g}"
        if np.iscomplex(self.fs_damped):
            summary_ace += "    (overdamped)"
        summary_ace += f"\nKms: {self.Kms / 1000:.4g} N/mm    Rms: {self.Rms:.3g} kg/s    Mms/Mmd: {self.Mms*1000:.4g}/{self.Mmd*1000:.4g} g"
        if self.motor is not None:
            summary_ace += f"\nWindings: {self.motor.coil.mass*1000:.4g} g"

        summary_ace += f"\nXpeak: {self.Xpeak*1000:.3g} mm    Bl²/Re: {self.Bl**2/self.Re:.3g} N²/W"

        # Make a string for mechanical summary
        summary_mec = ""
        if self.motor is not None:
            Xmech = calculate_coil_to_bottom_plate_clearance(self.Xpeak)
            summary_mec = f"Minimum {Xmech*1000:.3g} mm clearance under coil recommended"

        return "\n\n".join(["<b>Speaker driver</b>\n", summary_ace, summary_mec])


@dtc.dataclass
class Housing:
    # All units are SI
    settings: object
    Vb: float
    Qa: float
    Ql: float = np.inf

    def K(self, Sd):
        return Sd**2 * self.settings.Kair / self.Vb

    def R(self, Sd, Mms, Kms):
        return ((Kms + self.K(Sd)) * Mms)**0.5 / self.Qa + ((Kms + self.K(Sd)) * Mms)**0.5 / self.Ql

    def Vba(self):  # acoustical volume higher than actual due to internal damping
        # this calculation is referenced in GUI tooltip. Update tooltip if modifiying.
        return self.Vb * (0.94/self.Qa + 1)  # based on calculation results in UniBox. Original source of formula not found.


@dtc.dataclass
class ParentBody:
    # All units are SI
    m: float
    k: float
    c: float

    # def f(self):
    #     return 1 / 2 / np.pi * (self.k / self.m)**0.5

    # def Q(self):
    #     return (self.k * self.m)**0.5 / self.c


@dtc.dataclass
class PassiveRadiator:
    # All units are SI
    m: float  # without coupled air mass
    k: float
    c: float
    Spr: float  # surface area
    direction: int = 1

    def m_s(self):
        # passive radiator with coupled air mass included
        return self.m + calculate_air_mass(self.Sp)

    # def f(self):
    #     return 1 / 2 / np.pi * (self.k / self.m_s())**0.5

    # def Q(self):
    #     return (self.k * self.m_s())**0.5 / self.c


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
        else:
            coeffs = [sols[state_diff].coeff(state_var) for state_var in state_vars]

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
        coeffs = [sols[state_diff].coeff(input_var) for input_var in input_vars]

        matrix.append(coeffs)

    return smp.Matrix(matrix)


@dtc.dataclass
class SpeakerSystem:
    speaker: SpeakerDriver
    Rs: float = 0  # series electrical resistance to the speaker terminals.
                    # may be inside the amp or in the cables to the speaker terminals
    housing: None | Housing = None
    parent_body: None | ParentBody = None
    passive_radiator: None | PassiveRadiator = None

    def __post_init__(self):
        self.settings = self.speaker.settings
        self._build_symbolic_ss_model()
        self.update_values()

    def _build_symbolic_ss_model(self):
        # Static symbols
        Mms, M2, Mpr = smp.symbols("M_ms, M_2, M_pr", real=True, positive=True)
        Kms, K2, Kpr = smp.symbols("K_ms, K_2, K_pr", real=True, positive=True)
        Rms, R2, Rpr = smp.symbols("R_ms, R_2, R_pr", real=True, positive=True)
        P0, gamma, Vba, Qa, Ql = smp.symbols("P_0, gamma, V_ba, Q_a, Q_l", real=True, positive=True)
        Sd, Spr, Bl, Re, R_serial = smp.symbols("S_d, S_pr, Bl, R_e, R_serial", real=True, positive=True)
        dir_pr = smp.symbols("direction_pr")
        has_housing = smp.symbols("has_housing")
        # Direction coefficient for passive radiator
        # 1 if same direction with speaker, 0 if orthogonal, -1 if reverse direction

        # Dynamic symbols
        x1, x2 = mech.dynamicsymbols("x(1:3)")
        xpr = mech.dynamicsymbols("x_pr")
        Vsource = mech.dynamicsymbols("V_source", real=True)

        # Derivatives
        x1_t, x1_tt = smp.diff(x1, t), smp.diff(x1, t, t)
        x2_t, x2_tt = smp.diff(x2, t), smp.diff(x2, t, t)
        xpr_t, xpr_tt = smp.diff(xpr, t), smp.diff(xpr, t, t)

        # define state space system
        eqns = [    

                (- Mms * x1_tt
                 - Rms*(x1_t - x2_t) - Kms*(x1 - x2)
                 - has_housing * P0 * gamma / Vba * (Sd * x1 + Spr * xpr) * Sd
                 + (Vsource - Bl*(x1_t - x2_t)) / (R_serial + Re) * Bl
                 ),

                (- M2 * x2_tt - R2 * x2_t - K2 * x2
                 - Rms*(x2_t - x1_t) - Kms*(x2 - x1)
                 + has_housing * P0 * gamma / Vba * (Sd * x1 + Spr * xpr) * Sd
                 + has_housing * P0 * gamma / Vba * (Sd * x1 + Spr * xpr) * Spr * dir_pr  # this is causing issues on systems with no pr but yes housing
                 - (Vsource - Bl*(x1_t - x2_t)) / (R_serial + Re) * Bl
                 ),

                (- Mpr * xpr_tt - Rpr * xpr_t - Kpr * xpr
                 - has_housing * P0 * gamma / Vba * (Sd * x1 + Spr * xpr) * Spr
                 ),
                
                ]

        state_vars = [x1, x1_t, x2, x2_t, xpr, xpr_t]  # state variables
        input_vars = [Vsource]  # input variables
        state_diffs = [var.diff() for var in state_vars]  # state differentials

        # dictionary of all sympy symbols used in model
        self.symbols = {key: val for (key, val) in locals().items() if isinstance(val, smp.Symbol)}
        
        # solve for state differentials
        # this is a heavy task and slow
        sols = solve(eqns, [var for var in state_diffs if var not in state_vars], as_dict=True)  # heavy task, slow
        if len(sols) == 0:
            raise RuntimeError("No solution found for the equation.")

        # correction to exact variables in solutions
        sols[x1_t] = x1_t
        sols[x2_t] = x2_t
        sols[xpr_t] = xpr_t
        
        # ---- SS model with symbols
        A_sym = make_state_matrix_A(state_vars, state_diffs, sols)  # system matrix
        B_sym = make_state_matrix_B(state_diffs, input_vars, sols)  # input matrix
        C = dict()  # one per state variable -- scipy state space supports only a rank of 1 for output
        for i, state_var in enumerate(state_vars):
            C[state_var] = np.eye(len(state_vars))[i]
        D = np.zeros(1)  # no feedforward
        
        self._symbolic_ss = {"A": A_sym,  # system matrix
                             "B": B_sym,  # input matrix
                             "C": C,  # output matrices dictionary, one per state variable
                             "D": D,  # feedforward
                             "state_vars": state_vars,
                            }

    def _get_parameter_names_to_values(self) -> dict:
        "Get a dictionary of all the parameters related to the speaker system"
        "key: symbol variable name, val: value"

        parameter_names_to_values = {

            "Mms": self.speaker.Mms,
            "Kms": self.speaker.Kms,
            "Rms": self.speaker.Rms,
            "Sd": self.speaker.Sd,
            "Bl": self.speaker.Bl,
            "Re": self.speaker.Re,

            "M2": np.inf if self.parent_body is None else self.parent_body.m,
            "K2": np.inf if self.parent_body is None else self.parent_body.k,
            "R2": np.inf if self.parent_body is None else self.parent_body.c,

            "Mpr": np.inf if self.passive_radiator is None else self.passive_radiator.m,
            "Kpr": np.inf if self.passive_radiator is None else self.passive_radiator.k,
            "Rpr": np.inf if self.passive_radiator is None else self.passive_radiator.c,
            "Spr": 1e-99 if self.passive_radiator is None else self.passive_radiator.Spr,
            "dir_pr": 0 if self.passive_radiator is None else self.passive_radiator.direction,

            "Vba": 1e99 if self.housing is None else self.housing.Vba(),
            "Qa": 1e99 if self.housing is None else self.housing.Qa,
            "Ql": 1e99 if self.housing is None else self.housing.Ql,
            "has_housing": 0 if self.housing is None else 1,

            "P0": self.settings.P0,
            "gamma": self.settings.GAMMA,

            "R_serial": self.Rs,

            }

        return parameter_names_to_values

    def get_symbols_to_values(self):
        # Dictionary with sympy symbols as keys and values as values
        parameter_names_to_values = self._get_parameter_names_to_values()
        return {symbol: parameter_names_to_values[name] for name, symbol in self.symbols.items()}

    def update_values(self, **kwargs):
        # ---- Use kwargs to update attributes of the object 'self'
        # for key, val in kwargs.items():
        #     if key in ["speaker", "Rs", "housing", "parent_body", "passive_radiator"]:
        #         setattr(self, key, val)  # set the attributes of self object with value in kwargs
        #     else:
        #         raise KeyError("Not familiar with key '{key}'")


        # for key in ["speaker", "Rs", "housing", "parent_body", "passive_radiator"]:
        #     setattr(self, key, kwargs[key])  # set the attributes of self object with value in kwargs
        

        dataclass_field_names = [dataclass_field.name for dataclass_field in dtc.fields(self)]
        for key, val in kwargs.items():
            if key in dataclass_field_names:
                setattr(self, key, val)  # set the attributes of self object with value in kwargs
            else:
                raise KeyError("Not familiar with key '{key}'")

        # Update scalars
        self.R_sys = self.speaker.Re + self.Rs

        # ---- Substitute values into system matrix and input matrix
        symbols_to_values = self.get_symbols_to_values()
        A = np.array(self._symbolic_ss["A"].subs(symbols_to_values)).astype(float)
        B = np.array(self._symbolic_ss["B"].subs(symbols_to_values)).astype(float)

        # ---- Updates in relation to housing
        if isinstance(self.housing, Housing):
            zeta_boxed_speaker = (self.housing.R(self.speaker.Sd, self.speaker.Mms, self.speaker.Mms) \
                                  + self.speaker.Rms + self.speaker.Bl**2 / self.speaker.Re) \
                / 2 / ((self.speaker.Kms+self.housing.K(self.speaker.Sd)) * self.speaker.Mms)**0.5

            fb_undamped = 1 / 2 / np.pi * ((self.speaker.Kms+self.housing.K(self.speaker.Sd)) / self.speaker.Mms)**0.5

            fb_damped = fb_undamped * (1 - 2 * zeta_boxed_speaker**2)**0.5
            if np.iscomplex(fb_damped):  # means overdamped I think
                fb_damped = np.nan

            self.fb = fb_undamped
            self.Qtc = np.inf if zeta_boxed_speaker == 0 else 1 / 2 / zeta_boxed_speaker

        else:
            self.fb = np.nan
            self.Qtc = np.nan
            # Make coefficients linked to housing inner pressure 0, thus disable housing
            # ---- code to disable housing here

        # ---- Updates in relation to passive radiator
        if isinstance(self.parent_body, ParentBody):
            # Zeta is damping ratio. It is not damping coefficient (c) or quality factor (Q).
            # Zeta = c / 2 / (k*m)**0.5)
            # Q = (k*m)**0.5 / c
            zeta2_free = self.parent_body.c / 2 / ((self.speaker.Mms + self.parent_body.m) * self.parent_body.k)**0.5
            if self.parent_body.c > 0:
                q2_free = 1 / 2 / zeta2_free
            elif self.parent_body.c == 0:
                q2_free = np.inf
            else:
                raise ValueError(f"Invalid value for parent_body.c: {self.parent_body.c}")

            # assuming relative displacement between x1 and x2 are zero
            # i.e. blocked speaker
            f2_undamped = 1 / 2 / np.pi * (self.parent_body.k / (self.speaker.Mms + self.parent_body.m))**0.5

            f2_damped = f2_undamped * (1 - 2 * zeta2_free**2)**0.5
            if np.iscomplex(f2_damped):  # means overdamped I think
                f2_damped = np.nan

            self.f2 = f2_undamped
            self.Q2 = q2_free

        else:
            self.f2 = np.nan
            self.Q2 = np.nan
            # make system coefficients related to x2 and x2_t zero
            A[2:4, :] = 0
            A[:, 2:4] = 0
            B[2:4] = 0

        # ---- Update passive radiator related attributes
        if isinstance(self.passive_radiator, PassiveRadiator):
            print("PR lumped calculations not ready yet")
        else:
            # make system coefficients related to xpr and xpr_t zero
            A[4:6, :] = 0
            A[:, 4:6] = 0
            B[4:6] = 0

        # ---- Build ss models
        self.ss_models = dict()
        for state_var in self._symbolic_ss["state_vars"]:
            self.ss_models[repr(state_var)] = signal.StateSpace(A,
                                                                B,
                                                                self._symbolic_ss["C"][state_var],
                                                                self._symbolic_ss["D"],
                                                                )

    def power_at_Re(self, Vspeaker):
        # Calculation of power at Re for given voltage at the speaker terminals
        return Vspeaker**2 / self.Re
    
    def get_displacements(self, V_source, freqs: np.array) -> dict:
        # Voltage argument given in RMS
        # outputs in mm
        disps = dict()
        w = 2 * np.pi * np.array(freqs)

        x1 = signal.freqresp(self.ss_models["x1(t)"], w=w)[1] * V_source

        disps["Diaphragm, RMS, absolute"] = x1 * 1e3
        disps["Diaphragm, peak, absolute"] = x1 * 2**0.5 * 1e3

        if self.parent_body is not None:  # in fact, better return these even when no parnt_body, and filter in plotting
            x2 = signal.freqresp(self.ss_models["x2(t)"], w=w)[1] * V_source
            disps["Parent body, RMS, absolute"] = x2 * 1e3
            disps["Diaphragm, RMS, relative to parent"] = (x1 - x2) * 1e3
            disps["Diaphragm, peak, relative to parent"] = (x1 - x2) * 2**0.5 * 1e3
            # disps["Parent body, peak, absolute"] = x2 * 2**0.5 * 1e3

        if self.passive_radiator is not None:  # remove later and return always
            xpr = signal.freqresp(self.ss_models["x_pr(t)"], w=w)[1] * V_source
            disps["PR/vent, RMS, absolute"] = xpr * 1e3
            disps["PR/vent, peak, absolute"] = xpr * 2**0.5 * 1e3
            if self.parent_body is not None:
                disps["PR/vent, RMS, relative to parent"] = (xpr - x2) * 1e3
                disps["PR/vent, peak, relative to parent"] = (xpr - x2) * 2**0.5 * 1e3
                
        return disps

    def get_velocities(self, V_source, freqs: np.array) -> dict:
        # Voltage argument given in RMS
        # outputs in m/s
        velocs = dict()
        w = 2 * np.pi * np.array(freqs)

        x1_t = signal.freqresp(self.ss_models["Derivative(x1(t), t)"], w=w)[1] * V_source
        velocs["Diaphragm, RMS, absolute"] = x1_t

        if self.parent_body is not None:  # remove later and return always
            x2_t = signal.freqresp(self.ss_models["Derivative(x2(t), t)"], w=w)[1] * V_source
            velocs["Parent body, RMS, absolute"] = x2_t
            velocs["Diaphragm, RMS, relative to parent"] = x1_t - x2_t

        if self.passive_radiator is not None:  # remove later and return always
            xpr_t = signal.freqresp(self.ss_models["Derivative(x_pr(t), t)"], w=w)[1] * V_source
            velocs["PR/vent, RMS, absolute"] = xpr_t
            if self.parent_body is not None:
                velocs["PR/vent, RMS, relative to parent"] = xpr_t - x2_t
        
        return velocs

    def get_accelerations(self, V_source, freqs: np.array) -> dict:
        # Voltage argument given in RMS
        # outputs in m/s
        velocs = self.get_velocities(V_source, freqs)
        w = 2 * np.pi * np.array(freqs)

        return {key: arr.flatten() * 1j * w for key, arr in velocs.items()}
    
    def get_Z(self, freqs):
        imps = dict()
        velocs = self.get_velocities(1, freqs)

        # relative velocity of coil (x1) to magnetic field (parent body, x2)
        if self.parent_body is None:
            x1t_relative_x2t = velocs["Diaphragm, RMS, absolute"]
        else:
            x1t_relative_x2t = velocs["Diaphragm, RMS, relative to parent"]

        imps["Impedance speaker"] = self.R_sys / (1 - self.speaker.Bl * x1t_relative_x2t) - self.Rs  # speaker only
        if self.Rs > 0:  # remove later and return always
            imps["Impedance incl. source, cables"] = imps["Impedance speaker"] + self.Rs
    
        return imps

    def get_forces(self, V_source, freqs: np.array) -> dict:
        # Voltage argument given in RMS
        # force coil means force generated by coil
        # force speaker means force generated by speaker (inertial forces)
        forces = dict()
        velocs = self.get_velocities(V_source, freqs)
        accs = self.get_velocities(V_source, freqs)

        # relative velocity of coil (x1) to magnetic field (parent body, x2)
        if self.parent_body is None:
            x1t_relative_x2t = velocs["Diaphragm, RMS, absolute"]
        else:
            x1t_relative_x2t = velocs["Diaphragm, RMS, relative to parent"]

        force_coil = self.speaker.Bl * np.real(V_source - self.speaker.Bl * x1t_relative_x2t) / self.R_sys
        force_speaker = - accs["Diaphragm, RMS, absolute"] * self.speaker.Mms  # inertial force

        forces = {}
        forces["Lorentz force"] = force_coil
        forces["Inertial force from speaker"] = - force_speaker
        forces["Reaction force from reference frame"] = force_speaker

        if self.parent_body is not None:
            force_parent_body = - accs["Parent body, RMS, absolute"] * self.parent_body.m  # inertial force
            forces["Reaction force from reference frame"] += force_parent_body
            forces["Inertial force from parent mass"] = - force_parent_body

        if self.passive_radiator is not None:
            force_pr = - accs["PR/vent, RMS, absolute"] * self.passive_radiator.m_s()  # inertial force
            forces["Reaction force from reference frame"] += force_pr
            forces["Inertial force from passive radiator"] = - force_pr


        forces["Reaction force from reference frame"] = forces.pop("Reaction force from reference frame")  # move to end

        return forces

    def get_phases(self, freqs: np.array) -> dict:
        # Phase for displacements
        # output in degrees
        phases = dict()
        disps = self.get_displacements(1, freqs)

        phases["Diaphragm, absolute"] = np.angle(disps["Diaphragm, RMS, absolute"], deg=True)

        if self.parent_body is not None:
            phases["Parent body, absolute"] = np.angle(disps["Parent body, RMS, absolute"], deg=True)

        if self.passive_radiator is not None:
            phases["PR/vent, absolute"] = np.angle(disps["PR/vent, RMS, absolute"], deg=True)
            
        return phases


@dtc.dataclass
class Settings:
    RHO: float = 1.1839  # density of air at 25 degrees celcius
    Kair: float = 101325. * RHO
    GAMMA: float = 1.401  # adiabatic index of air
    P0: int = 101325  # atmospheric pressure
    c_air: float = (P0 * GAMMA / RHO)**0.5


def tests():
    settings = Settings()

    def generate_freq_list(freq_start, freq_end, ppo):
        """
        Create a numpy array for frequencies to use in calculation.
    
        ppo means points per octave
        """
        numStart = np.floor(np.log2(freq_start/1000)*ppo)
        numEnd = np.ceil(np.log2(freq_end/1000)*ppo)
        freq_array = 1000*np.array(2**(np.arange(numStart, numEnd + 1)/ppo))
        return freq_array
    
    freqs = generate_freq_list(10, 1500, 48*8)


    # # do test model 1
    # my_speaker = SpeakerDriver(100, 52e-4, 8, Bl=4, Re=4, Mms=8e-3)
    # my_system = SpeakerSystem(my_speaker)

    # # do test model 2
    # housing = Housing(0.01, 5)
    # parent_body = ParentBody(1, 1, 1)
    # my_speaker = SpeakerDriver(100, 52e-4, 8, Bl=4, Re=4, Mms=8e-3)
    # my_system = SpeakerSystem(my_speaker, housing=housing, parent_body=parent_body)

    # # do test model 3
    housing = Housing(settings, 0.001, 1e99, 99999)
    parent_body = ParentBody(1, 1, 1)
    pr = PassiveRadiator(20e-3, 1, 1, 100e-4)
    my_speaker = SpeakerDriver(settings, 100, 52e-4, 8, Bl=4.01, Re=4, Mms=0.00843)
    my_system = SpeakerSystem(my_speaker,
                              parent_body=parent_body,
                              housing=housing,
                              passive_radiator=None,
                              )

    my_system.update_values(speaker=my_speaker,
                            Rs=10,
                            housing = housing,
                            parent_body = parent_body,
                            passive_radiator = None,
                            )


    # do test model for unibox - Qa / Ql
    # housing = Housing(0.05, 9999)
    # my_speaker = SpeakerDriver(100, 52e-4, 8, Bl=3, Re=4, Mms=7.7e-3)
    # my_system = SpeakerSystem(my_speaker, housing=housing)
    # x1 = signal.freqresp(my_system.ss_model, w=np.array([100, 200]))

    w, y = signal.freqresp(my_system.ss_models["x1(t)"], w=2*np.pi*freqs)
    import matplotlib.pyplot as plt
    y_for_10Vrms = np.abs(y) * 2**0.5 * 10
    y_rms_for_10Vrms = np.abs(y) * 10
    plt.semilogx(freqs, y_for_10Vrms)
    for i, freq in enumerate(freqs):
        if int(freq) == 200:
            print(f"{freqs[i]:.5g}Hz: {y_rms_for_10Vrms[i] * 1e3:.5g}mm RMS")
    return my_system

    # to-do
    # SPL calculation and comparing results against Unibox, finding out the Qa Ql mystery (Qa makes large bigger)


if __name__ == "__main__":
    test_result = tests()