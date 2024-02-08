#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Aug  6 20:23:15 2023

@author: kerem
"""
from dataclasses import dataclass
from functools import cached_property
import numpy as np


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


@dataclass
class Wire():
    name: str
    w_nom: float
    h_nom: float
    w_max: float
    resistance: float  # ohm/m
    mass_density: float  # kg/m


@dataclass
class Coil():
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


@dataclass
class SpeakerDriver():
    """Speaker driver class."""
    Bl: float = None
    Re: float = None
    fs: float = None
    Mms: float = None
    Sd: float = None
    Qms: float = None

    def __post_init__(self):
        self.update_core_parameters()

    def define_motor(self, coil: Coil, Rlw: float, Bavg: float):
        """
        Define coil and motor parameters of speaker.

        Parameters
        ----------
        coil : Coil
            Coil winding object.
        Rlw : float
            Leadwire resistance.
        Bavg : float
            Average magnetic field on the total height of coil in rest position.

        Returns
        -------
        None.

        """
        self.Re = coil.Rdc + Rlw
        self.Bl = Bavg * coil.total_wire_length()

    def update_core_parameters(self, **kwargs):
        core_parameters = ("Bl", "Re", "fs", "Mms", "Sd", "Qms", "dead_mass")
        for key, val in kwargs.items():
            if key in core_parameters and isinstance(val, float):
                if key == "Rms" and val < 0:
                    raise ValueError(f"Damping coefficient 'Rms' cannot be negative: {val}")
                elif val <= 0:
                    raise ValueError(f"Value '{key}' cannot be zero or negative: {val}")
                else:
                    setattr(self, key, val)
            else:
                raise ValueError(f"Invalid keyword argument: {key}: {val}")

        # derived parameters
        # Mms and Mmd
        if self.coil is not None:
            try:
                self.Mmd = dead_mass + self.coil.mass
                self.Mms = self.Mmd + calculate_air_mass(self.Sd)
            except NameError:
                print("Unable to calculate 'Mms' and/or 'Mmd' with known parameters.")
        else:
            # Mmd
            try:
                self.Mmd = self.Mms - calculate_air_mass(self.Sd)
            except NameError:
                print("Unable to calculate 'Mmd' with known parameters.")

        # Kms
        try:
            self.Kms = self.Mms * (self.fs * 2 * np.pi)**2
        except NameError:
            print("Unable to calculate 'Kms' with known parameters.")

        # Rms
        try:
            self.Rms = (self.Mms * self.Kms)**0.5 / self.Qms
        except NameError:
            print("Unable to calculate 'Rms' with known parameters.")

        # Ces
        try:
            self.Ces = self.Bl**2 / self.Re
        except NameError:
            print("Unable to calculate 'Ces = Bl²/Re' with known parameters.")

        # Qts, Qes
        try:
            self.Qts = (self.Mms * self.Kms)**0.5 / (self.Rms + self.Ces)
            self.Qes = (self.Mms * self.Kms)**0.5 / (self.Ces)
        except NameError:
            print("Unable to calculate 'Qts' and/or 'Qes' with known parameters.")

        # Lm - sensitivity per W@Re
        try:
            self.Lm = calculate_Lm(self.Bl, self.Rdc, self.Mms, self.Sd)
        except NameError:
            print("Unable to calculate 'Lm' with known parameters.")


@dataclass
class Dof():
    m: float
    c: float
    k: float


@dataclass
class Housing():
    Vb: float
    Qa: float


@dataclass
class SpeakerSystem():
    speaker: SpeakerDriver
    housing: Housing = None
    dof2: Dof = None

    def set_dof2(self, dof: Dof):
        self.dof2 = dof
        self.update()

    def set_housing(self, housing: Housing):
        self.housing = housing
        self.update()

    def __post_init__(self):
        self.update()

    def update(self):
        global settings
        if self.dof2 is not None:
            zeta2_free = self.dof2.c / 2 / ((self.speaker.Mms + self.dof2.m) * self.dof2.k)**0.5
            if self.dof2.c > 0:
                q2_free = 1 / 2 / zeta2_free
            elif self.dof2.c == 0:
                q2_free = np.inf
            else:
                raise ValueError(f"Invalid value for dof2.c: {self.dof2.c}")

            # assuming relative displacement between x1 and x2 are zero
            # i.e. blocked speaker
            f2_undamped = 1 / 2 / np.pi * (self.dof2.k / (self.speaker.Mms + self.dof2.m))**0.5
            f2_damped = f2_undamped * (1 - 2 * zeta2_free**2)**0.5
            if np.iscomplex(f2_damped):
                f2_damped = None
            self.f2 = f2_undamped
            self.Q2 = q2_free

        if self.housing is not None:
            self.Kbox = self.speakerSd**2 * settings.Kair / self.housing.Vb
            self.Rbox = ((self.speaker.Kms + self.Kbox) * self.speaker.Mms)**0.5 / self.housing.Qa
            zeta_boxed_speaker = (self.Rbox + self.speaker.Rms + self.speaker.Bl**2 / self.speaker.Re) \
                / 2 / ((self.speaker.Kms+self.Kbox) * self.speaker.Mms)**0.5
            self.Qtc = 1 / 2 / zeta_boxed_speaker

            self.fb = 1 / 2 / np.pi * ((self.speaker.Kms+self.Kbox) / self.speaker.Mms)**0.5
            fb_d = self.fb * (1 - 2 * zeta_boxed_speaker**2)**0.5
            if np.iscomplex(fb_d):
                fb_d = None

            self.Vas = settings.Kair / self.speaker.Kms * self.speaker.Sd**2
        
    def get_ss_model(self):
        return "an_ss_model"
