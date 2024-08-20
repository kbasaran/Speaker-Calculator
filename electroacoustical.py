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
from sympy.abc import t
from sympy.solvers import solve
from scipy import signal

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


def calculate_Lm(Bl, Re, Mms, Sd):
    "Calculate Lm@Re, 1W, 1m."
    w_ref = 10**-12
    I_1W_per_m2 = settings.RHO * Bl**2 * Sd**2 / settings.c_air / Re / Mms**2 / 2 / np.pi
    P_over_I_half_space = 1/2/np.pi  # m²
    return 10 * np.log10(I_1W_per_m2 * P_over_I_half_space / w_ref)


def calculate_coil_to_bottom_plate_clearance(Xpeak):
    """
    Proposed clearance for given Xpeak value.

    All values in basic SI units.
    """
    proposed_clearance = 1e-3 + (Xpeak - 3e-3) / 5
    return Xpeak + proposed_clearance


@dtc.dataclass
class Wire:
    name: str
    w_nom: float
    h_nom: float
    w_max: float
    resistance: float  # ohm/m
    mass_density: float  # kg/m


@dtc.dataclass
class Coil:
    carrier_OD: float
    wire: Wire
    N_windings: tuple
    w_stacking_coef: float

    def length_of_one_turn(self, i_layer):
        """Calculate the length of one turn of wire on a given coil layer."""
        if i_layer == 1:
            turn_radius_wire_center_to_axis = self.carrier_OD/2 + self.wire.w_nom/2
        if i_layer > 1:
            turn_radius_wire_center_to_axis = (self.carrier_OD/2
                                               + self.wire.w_nom/2
                                               + (self.w_stacking_coef * (i_layer - 1) * self.wire.w_nom)
                                               )
        # pi/4 is stacking coefficient for ideal circular wire
        return 2 * np.pi * turn_radius_wire_center_to_axis

    @cached_property
    def total_wire_length(self):
        return sum([self.length_of_one_turn(i) * self.N_windings[i] for i in range(self.N_layers)])

    def __post_init__(self):
        assert all([i > 0 for i in self.N_windings])
        self.N_layers = len(self.N_windings)
        self.h_winding = self.wire.h_nom * self.N_windings[0]
        self.mass = self.total_wire_length() * self.wire.mass_density
        self.Rdc = self.total_wire_length() * self.wire.resistance
        self.w_max = self.wire.w_max * (1 + (self.N_layers - 1) * self.w_stacking_coef)


def wind_coil(wire, N_layers, w_stacking_coef, carrier_OD, h_winding_target):
    "Create coil object based on given data."

    def N_winding_for_single_layer(i_layer: int) -> int:
        "Calculate the number of windings that fit on one layer of coil."
        n_winding = h_winding_target / wire.h_nom - i_layer * 1  # 1 winding less on each stacked layer
        return round(n_winding)

    N_windings = [N_winding_for_single_layer(i_layer) for i_layer in range(N_layers)]
    if any([n < 1 for n in N_windings]):
        raise ValueError("Some layers were impossible")

    return Coil(carrier_OD, wire, N_windings, w_stacking_coef)


def calculate_voltage(excitation_value, excitation_type, Rdc=None, Rnom=None):
    "Simplify electrical input definition to a voltage value."

    match excitation_type:

        case "Wn":
            if not Rnom:
                raise ValueError("Need to provide nominal impedance to calculate Wn")
            else:
                input_voltage = (excitation_value * Rnom) ** 0.5

        case "W":
            if not Rdc:
                raise ValueError("Need to provide Rdc to calculate W")
            else:
                input_voltage = (excitation_value * Rdc) ** 0.5

        case "V":
            input_voltage = excitation_value

        case _:
            raise ValueError("excitation type must be one of (V, W, Wn)")

    return input_voltage


@dtc.dataclass
class Motor:
    coil: Coil
    Bavg: float
    Xpeak: float = None
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
    fs: float
    Sd: float
    Qms: float
    Bl: float = None  # provide only if motor is None
    Re: float = None  # provide only if motor is None
    Mms: float = None  # provide only if motor is None
    motor: None | Motor = None  # None of 'Motor' instance
    dead_mass: float = None  # provide only if motor is 'Motor' instance
    Rs: float = 0  # resistance between the coil and the speaker terminals (leadwire etc.)
    Xmax: float = None

    def __post_init__(self):
        if self.motor is not None:
            should_not_have_been_specified = ("Bl", "Re")
            if not all([self.get(val) is None for val in should_not_have_been_specified]):
                raise RuntimeError("These attributes should not be specified when motor is already specified:"
                                   f"\n{should_not_have_been_specified}")
            self.Bl = self.motor.coil.h_winding * self.motor.Bavg
            self.Re = self.motor.Rdc + self.Rs

        # derived parameters
        # Mms and Mmd
        if self.motor is not None:
            try:
                if "Mms" in locals().keys():
                    raise RuntimeError("Double definition. 'Mms' should not be defined in object instantiation"
                                       " when 'motor' is already defined.")
                self.Mmd = self.dead_mass + self.motor.coil.mass
                self.Mms = self.Mmd + calculate_air_mass(self.Sd)
            except NameError:
                print("Unable to calculate 'Mms' and/or 'Mmd' with known parameters.")
        else:
            # only Mmd
            try:
                self.Mmd = self.Mms - calculate_air_mass(self.Sd)
            except NameError:
                print("Unable to calculate 'Mmd' with known parameters.")

        self.Kms = self.Mms * (self.fs * 2 * np.pi)**2
        self.Rms = (self.Mms * self.Kms)**0.5 / self.Qms
        self.Ces = self.Bl**2 / self.Re
        self.Qts = (self.Mms * self.Kms)**0.5 / (self.Rms + self.Ces)
        self.Qes = (self.Mms * self.Kms)**0.5 / (self.Ces)
        zeta_speaker = 1 / 2 / self.Qts
        self.fs_damped = self.fs * (1 - 2 * zeta_speaker**2)**0.5  # complex number if overdamped system
        # Lm - sensitivity per W@Re
        self.Lm = calculate_Lm(self.Bl, self.Re, self.Mms, self.Sd)
        self.Vas = settings.Kair / self.Kms * self.Sd**2
    
    def get_summary(self) -> list:
        "Give a summary for acoustical and mechanical properties as two items of a list."
        # Make a string for acoustical summary
        summary_ace = f"Rdc: {self.Re:.2f} ohm    Lm: {self.Lm:.2f} dBSPL    Bl: {self.Bl:.4g} Tm"
        summary_ace += f"\nQts: {self.Qts:.3g}    Qes: {self.Qes:.3g}"
        if np.iscomplex(self.fs_damped):
            summary_ace += "    (overdamped)"
        summary_ace += f"\nKms: {self.Kms / 1000:.4g} N/mm    Rms: {self.Rms:.3g} kg/s    Mms: {self.Mms*1000:.4g} g"
        if self.motor is not None:
            summary_ace += f"\nMmd: {self.Mmd*1000:.4g} g    Windings: {self.coil_mass*1000:.2f} g"

        summary_ace += f"\nXmax: {self.Xmax*1000:.2f} mm    Bl² / Re: {self.Bl**2 / self.Re:.3g} N²/W"

        # Make a string for mechanical summary
        summary_mec = ""
        if self.motor is not None:
            Xmech = calculate_coil_to_bottom_plate_clearance(self.motor.Xpeak)
            summary_mec = f"Minimum {Xmech*1000:.2f} mm clearance under coil recommended"

        return [summary_ace, summary_mec]

@dtc.dataclass
class Housing:
    Vb: float
    Qa: float

    def K(self, Sd):
        global settings
        return Sd**2 * settings.Kair / self.Vb
    
    def R(self, Sd, Mms, Kms):
        return ((Kms + self.K(Sd)) * Mms)**0.5 / self.Qa  # need to verify calculation


@dtc.dataclass
class ParentBody:
    m: float
    k: float
    c: float
    
    # def f(self):
    #     return 1 / 2 / np.pi * (self.k / self.m)**0.5
    
    # def Q(self):
    #     return (self.k * self.m)**0.5 / self.c


@dtc.dataclass
class PassiveRadiator:
    m: float  # without coupled air mass
    k: float
    c: float
    Sp: float
    direction: int = 1
    
    def m_s(self):
        # passive radiator with coupled air mass included
        return self.m + calculate_air_mass(self.Sp)
    
    # def f(self):
    #     return 1 / 2 / np.pi * (self.k / self.m_s())**0.5

    
    # def Q(self):
    #     return (self.k * self.m_s())**0.5 / self.c


def make_state_matrix_A(state_vars, state_diffs, sols):
    matrix = []
    for state_diff in state_diffs:
        if state_diff in state_vars:
            coeffs = [int(state_vars[i] == state_diff) for i in range(len(state_vars))]
        else:
            coeffs = [sols[state_diff].coeff(state_var) for state_var in state_vars]
        matrix.append(coeffs)
    return smp.Matrix(matrix)


def make_state_matrix_B(state_diffs, input_vars, sols):
    matrix = []
    for state_diff in state_diffs:
        coeffs = [sols[state_diff].coeff(input_var) for input_var in input_vars]
        matrix.append(coeffs)
    return smp.Matrix(matrix)


@dtc.dataclass
class SpeakerSystem:
    speaker: SpeakerDriver
    Rs: float = 0  # series electrical resistance to the speaker terminals
    housing: None | Housing = None
    parent_body: None | ParentBody = None
    passive_radiator: None | PassiveRadiator = None

    def __post_init__(self):
        self._symbolic_ss_model_update()
        self.update()

    def get_parameters(self, symbol_names_to_symbols) -> dict:
        "Get a dictionary of all the parameters related to the speaker system"
        "key: symbol object, val: value"
        "An argument is required to map the symbol names to symbol objects."

        symbol_names_to_values = {
            "Mms": self.speaker.Mms,
            "Kms": self.speaker.Kms,
            "Rms": self.speaker.Rms,
            "Sd": self.speaker.Sd,
            "Bl": self.speaker.Bl,
            "Re": self.speaker.Re,


            "M2": None if self.parent_body is None else self.parent_body.m,
            "K2": None if self.parent_body is None else self.parent_body.k,
            "R2": None if self.parent_body is None else self.parent_body.c,


            "Mpr": None if self.passive_radiator is None else self.passive_radiator.m,
            "Kpr": None if self.passive_radiator is None else self.passive_radiator.k,
            "Rpr": None if self.passive_radiator is None else self.passive_radiator.c,
            "Spr": None if self.passive_radiator is None else self.passive_radiator.Sp,
            "dir_pr": None if self.passive_radiator is None else self.passive_radiator.direction,

            "Vb": None if self.housing is None else self.housing.Vb,
            "Qa": None if self.housing is None else self.housing.Qa,

            "P0": settings.P0,
            "gamma": settings.GAMMA,

            "Rs_source": self.Rs,

            }

        return {val: symbol_names_to_values[key] for key, val in symbol_names_to_symbols.items()}


    def _symbolic_ss_model_update(self):
        # Static symbols
        Mms, M2, Mpr = smp.symbols("M_ms, M_2, M_pr", real=True, positive=True)
        Kms, K2, Kpr = smp.symbols("K_ms, K_2, K_pr", real=True, positive=True)
        Rms, R2, Rpr = smp.symbols("R_ms, R_2, R_pr", real=True, positive=True)
        P0, gamma, Vb, Qa = smp.symbols("P_0, gamma, V_b, Q_a", real=True, positive=True)
        Sd, Spr, Bl, Re, Rs_source = smp.symbols("S_d, S_pr, Bl, R_e, Rs_source", real=True, positive=True)
        dir_pr = smp.symbols("direction_pr")
            # Direction coefficient for passive radiator
            # 1 if same direction with speaker, 0 if orthogonal, -1 if reverse direction
        
        self.symbol_names_to_symbols = {
            "Mms": Mms,
            "Kms": Kms,
            "Rms": Rms,

            "P0": P0,
            "gamma": gamma,

            "Sd": Sd,
            "Bl": Bl,
            "Re": Re,

            "Rs_source": Rs_source,
            }
        
        if self.parent_body is not None:
            self.symbol_names_to_symbols.update({
                "M2": M2,
                "K2": K2,
                "R2": R2,
                })

        if self.passive_radiator is not None:
            if self.housing is None:
                raise RuntimeError("Not possible to have a passive radiator without a housing.")

            self.symbol_names_to_symbols.update({
                "Mpr": Mpr,
                "Kpr": Kpr,
                "Rpr": Rpr,
                "Spr": Spr,
                "dir_pr": dir_pr,
                })

        if self.housing is not None:      
            self.symbol_names_to_symbols.update({
                "Vb": Vb,
                "Qa": Qa,
                })

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
                 - P0 * gamma / Vb * (Sd * x1 + Spr * xpr) * Sd
                 + (Vsource - Bl*(x1_t - x2_t)) / (Rs_source + Re) * Bl
                 ),

                (- M2 * x2_tt - R2 * x2_t - K2 * x2
                 - Rms*(x2_t - x1_t) - Kms*(x2 - x1)
                 + P0 * gamma / Vb * (Sd * x1 + Spr * xpr) * Sd
                 + P0 * gamma / Vb * (Sd * x1 + Spr * xpr) * Spr * dir_pr  # this is causing issues on systems with no pr but yes housing
                 - (Vsource - Bl*(x1_t - x2_t)) / (Rs_source + Re) * Bl
                 ),

                (- Mpr * xpr_tt - Rpr * xpr_t - Kpr * xpr
                 - P0 * gamma / Vb * (Sd * x1 + Spr * xpr) * Spr
                 ),

                ]

        state_vars = [x1, x1_t]

        # modify based on missing features
        if self.parent_body is None:
            eqns = [eqn.subs({x2: 0, x2_t: 0, x2_tt:0, }) for eqn in eqns]
        else:
            state_vars = [*state_vars, x2, x2_t]
            
        if self.passive_radiator is None:
            eqns = [eqn.subs({xpr: 0, xpr_t: 0, xpr_tt:0, Spr: 1, dir_pr: 0}) for eqn in eqns]
        else:
            state_vars = [*state_vars, xpr, xpr_t]

        if self.housing is None:
            eqns = [eqn.subs({P0: 0, gamma: 0}) for eqn in eqns]
            
            
        # define input variables
        input_vars = [Vsource]
        
        # define state differentials
        state_diffs = [var.diff() for var in state_vars]

        # solve for state differentials
        sols = solve(eqns, [var for var in state_diffs if var not in state_vars], as_dict=True)
        if len(sols) == 0:
            raise RuntimeError("No solution found for the equation.")
        
        # change some solutions into direct (must be a better way......)
        sols[x1_t] = x1_t

        if self.parent_body is not None:
            sols[x2_t] = x2_t

        if self.passive_radiator is not None:
            sols[xpr_t] = xpr_t

        # extract the matrix coefficients from the solution
        self.symbolic_ss = {"a": make_state_matrix_A(state_vars, state_diffs, sols),  # system matrix
                            "b": make_state_matrix_B(state_diffs, input_vars, sols),  # input matrix
                            "c": smp.Matrix(smp.eye(len(state_vars))),  # give all state vars in output
                            "d": smp.Matrix([0]*len(state_vars)),  # no feedforward
                            }

    def update(self, **kwargs):
        global settings
        topology_changed = False  # to see if we need to update the state space model topology or simply change its values
        
        # --- Use kwargs to update attributes of the object 'self'
        for key, val in kwargs.items():
            if key in ["speaker", "Rs", "housing", "parent_body", "passive_radiator"]:
                if bool(val) != bool(getattr(self, key)):  # if any item in the list changes to or from 'None'
                    topology_changed = True
                setattr(self, key, val)  # set the attributes of self object with value in kwargs
            else:
                raise KeyError("Not familiar with key '{key}'")
                
        # ---- Rebuild ss model if a new topology is in place
        if topology_changed:
            self._symbolic_ss_model_update()
            
        # ---- Update housing related attributes
        if self.housing is not None:
            zeta_boxed_speaker = (self.housing.R(self.speaker.Sd, self.speaker.Mms, self.speaker.Mms) \
                                  + self.speaker.Rms + self.speaker.Bl**2 / self.speaker.Re) \
                / 2 / ((self.speaker.Kms+self.housing.K(self.speaker.Sd)) * self.speaker.Mms)**0.5

            fb_undamped = 1 / 2 / np.pi * ((self.speaker.Kms+self.housing.K(self.speaker.Sd)) / self.speaker.Mms)**0.5

            fb_damped = fb_undamped * (1 - 2 * zeta_boxed_speaker**2)**0.5
            if np.iscomplex(fb_damped):  # means overdamped I think
                fb_damped = None

            self.fb = fb_undamped
            self.Qtc = np.inf if zeta_boxed_speaker == 0 else 1 / 2 / zeta_boxed_speaker
        
        else:
            self.fb = None
            self.Qtc = None

        # ---- Update mobile parent body related attributes
        if self.parent_body is not None:
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
                f2_damped = None

            self.f2 = f2_undamped
            self.Q2 = q2_free
            
        else:
            self.f2 = None
            self.Q2 = None

        # ---- Update passive radiator related attributes
        if self.passive_radiator is not None:
            print("PR calculations not ready yet")
        else:
            pass

        # ---- Subsitute new parameters into the symbolic ss model
        self.ss_model = self.substitute_values_into_ss_model(self.get_parameters(self.symbol_names_to_symbols))

    def substitute_values_into_ss_model(self, values:dict) -> signal.StateSpace:
        print(self.symbolic_ss["a"].subs(values))
        ss_matrices = (np.array(self.symbolic_ss["a"].subs(values)).astype(float),
                        np.array(self.symbolic_ss["b"].subs(values)).astype(float),
                        np.array(self.symbolic_ss["c"].subs(values)).astype(float),
                        np.array(self.symbolic_ss["d"].subs(values)).astype(float),
                        )
        return signal.StateSpace(*ss_matrices)

    def power_at_Re(self, Vspeaker):
        # Calculation of power at Rdc for given voltage at the speaker terminals
        return Vspeaker**2 / self.Re

    def get_forces(self) -> dict:
        # force coil means force generated by coil
        # force speaker means force generated by speaker (inertial forces)
        force_coil = self.speaker.Bl * np.real(self.calculate_Vcoil() / self.speaker.Re)  # why not np.abs?
        force_speaker = - self.x1_tt * self.speaker.Mms  # inertial force
        force_parent_body = - self.x2tt * self.M2  # inertial force
        force_pr = - self.x3tt * self.parent_body["m"]  # inertial force

        forces = {}
        forces["Lorentz force"] = force_coil
        forces["Inertial force from speaker diaphragm"] = - force_speaker

        if self.parent_body is not None:
            forces["Inertial force from parent mass"] = - force_parent_body

        if self.passive_radiator is not None:
            forces["Inertial force from passive radiator"] = - force_pr

        forces["Reaction force from reference frame"] = force_speaker + force_parent_body + force_pr

        return forces

    def get_accelerations(self) -> dict:
        accs = {}
        accs["Acceleration of speaker diaphragm, RMS"] = self.x1_tt
        accs["Acceleration of speaker diaphragm, Peak"] = self.x1_tt * 2**0.5

        if self.parent_body is not None:
            accs["Acceleration of parent body, RMS"] = self.x2_tt
            accs["Acceleration of parent body, Peak"] = self.x2_tt * 2**0.5

        if self.passive_radiator is not None:
            accs["Acceleration of passive radiator, RMS"] = self.x3_tt
            accs["Acceleration of passive radiator, Peak"] = self.x3_tt * 2**0.5

        return accs

    def get_phases_for_displacements(self) -> dict:
        phases = {}
        phases["Speaker diaphragm"] = np.angle(self.x1, deg=True)

        if self.parent_body is not None:
            phases["Parent body"] = np.angle(self.x2, deg=True)

        if self.passive_radiator is not None:
            phases["Passive radiator"] = np.angle(self.x3, deg=True)

        return phases

if __name__ == "__main__":
    @dtc.dataclass
    class Settings:
        RHO: float = 1.1839  # density of air at 25 degrees celcius
        Kair: float = 101325. * RHO
        GAMMA: float = 1.401  # adiabatic index of air
        P0: int = 101325  # atmospheric pressure
        c_air: float = (P0 * GAMMA / RHO)**0.5
    
    settings = Settings()
    # do test model 1
    my_speaker = SpeakerDriver(100, 52e-4, 8, Bl=4, Re=4, Mms=8e-3)
    my_system = SpeakerSystem(my_speaker)
    
    # do test model 2
    housing = Housing(0.01, 5)
    parent_body = ParentBody(1, 1, 1)
    my_speaker = SpeakerDriver(100, 52e-4, 8, Bl=4, Re=4, Mms=8e-3)
    my_system = SpeakerSystem(my_speaker, housing=housing, parent_body=parent_body)
    
    # do test model 3
    housing = Housing(0.01, 5)
    parent_body = ParentBody(1, 1, 1)
    pr = PassiveRadiator(20e-3, 1, 1, 100e-4)
    my_speaker = SpeakerDriver(100, 52e-4, 8, Bl=4, Re=4, Mms=8e-3)
    my_system = SpeakerSystem(my_speaker, parent_body=parent_body, housing=housing, passive_radiator=pr)
