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
    I_1W_per_m2 = CONS.RHO * Bl**2 * Sd**2 / CONS.c_air / Re / Mms**2 / 2 / np.pi
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



def calculate_air_mass(Sd):
    """Air mass on diaphragm; the difference between Mms and Mmd."""
    return 1.13*(Sd)**(3/2)  # m2 in, kg out


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
class SpeakerDriver():
    """Speaker driver class."""

    coil_choice: tuple  # (winding_name (e.g.4x SV160), user data dictionary that includes variables for that winding)
    global form, CONS

    def __post_init__(self):
        """Post-init speaker."""
        self.error = str()
        motor_spec_choice = form.get_value("motor_spec_type")["userData"]
        read_from_form = ["fs", "Qms", "Xmax", "dead_mass", "Sd"]
        for k in read_from_form:
            setattr(self, k, form.get_value(k))

        if motor_spec_choice == "define_coil":
            B_average = form.get_value("B_average")
            former_ID = form.get_value("former_ID")
            t_former = form.get_value("t_former")
            h_winding = form.get_value("h_winding")
            winding_name, winding_data = self.coil_choice
            wire_type = winding_data["wire_type"]
            N_layers = winding_data["N_layers"]
            Rdc = winding_data["Rdc"]
            N_windings = winding_data["N_windings"]
            l_wire = winding_data["l_wire"]
            w_coil_max = winding_data["w_coil_max"]
            coil_mass = winding_data["coil_mass"]
            Bl = B_average * l_wire
            Mmd = self.dead_mass + coil_mass
            attributes = ["Rdc", "Bl", "Mmd", "Mms", "Kms", "Rms", "Ces",
                          "Qts", "Qes", "Lm", "coil_mass", "w_coil_max",
                          "l_wire", "wire_type", "N_layers", "N_windings"]

        elif motor_spec_choice == "define_Bl_Re":
            try:
                Rdc = form.get_value("Rdc")
                Bl = form.get_value("Bl")
                Mmd = form.get_value("Mmd")
                attributes = ["Rdc", "Bl", "Mmd", "Mms", "Kms", "Rms", "Ces",
                              "Qts", "Qes", "Lm"]
            except Exception:
                self.error += "Unable to get Bl, Re and Mmd values from user form"
        else:
            raise Exception("Unknown motor specification type")

        # Calculate more acoustical parameters using Bl, Rdc and Mmd
        Mms = Mmd + calculate_air_mass(self.Sd)
        Kms = Mms * (self.fs * 2 * np.pi)**2
        Rms = (Mms * Kms)**0.5 / self.Qms
        Ces = Bl**2 / Rdc
        Qts = (Mms*Kms)**0.5/(Rms+Ces)
        Qes = (Mms*Kms)**0.5/(Ces)
        zeta_speaker = 1 / 2 / Qts

        fs_damped = self.fs * (1 - 2 * zeta_speaker**2)**0.5
        if np.iscomplex(fs_damped):
            fs_damped = None

        Lm = calculate_Lm(Bl, Rdc, Mms, self.Sd)

        # Add all the calculated parameters as attribute to the object
        for v in attributes:
            setattr(self, v, locals()[v])

        # Make a string for acoustical summary
        self.summary_ace = "Rdc: %.2f ohm    Lm: %.2f dBSPL    Bl: %.4g Tm"\
            % (Rdc, Lm, Bl)
        self.summary_ace += "\r\nQts: %.3g    Qes: %.3g"\
            % (Qts, Qes)

        if fs_damped:
            self.summary_ace += f"    fs: {fs_damped:.3g} Hz (damped)"
        else:
            self.summary_ace += f"    fs: {self.fs:.3g} Hz (overdamped)"

        self.summary_ace += "\r\nKms: %.4g N/mm    Rms: %.3g kg/s    Mms: %.4g g"\
            % (Kms/1000, Rms, Mms*1000)
        if motor_spec_choice == "define_coil":
            self.summary_ace += "\r\nMmd: %.4g g    Windings: %.2f g" % (self.Mmd*1000, self.coil_mass*1000)

        self.summary_ace += \
            "\r\nXmax: %.2f mm    Bl² / Re: %.3g N²/W" % (self.Xmax*1000, Bl**2 / Rdc)

        # Make a string for mechanical summary
        self.Xmech = calculate_Xmech(self.Xmax)
        self.summary_mec = \
            "Xmech ≥ %.2f mm (recommended)" % (self.Xmech*1000)

        if motor_spec_choice == "define_coil":
            # Add mechanical variables from user form as instance variables
            read_from_form = ["airgap_clearance_inner",
                              "airgap_clearance_outer",
                              "t_former",
                              "former_ID",
                              "h_winding",
                              "former_extension_under_coil",
                              "h_washer"]
            for k in read_from_form:
                setattr(self, k, form.get_value(k))

            self.air_gap_width = (self.airgap_clearance_inner + self.t_former
                                  + self.w_coil_max + self.airgap_clearance_outer)

            self.air_gap_dims = [self.former_ID/2 - self.airgap_clearance_inner,
                                 self.air_gap_width,
                                 self.former_ID/2 - self.airgap_clearance_inner
                                 + self.air_gap_width]

            self.overhang = (self.h_winding - self.h_washer) / 2

            self.washer_to_bottom_plate = (self.h_winding / 2
                                           + self.former_extension_under_coil
                                           + calculate_Xmech(self.Xmax)
                                           - self.h_washer / 2)

            self.summary_mec += \
                "\r\nOverhang + 15%%: %.2f mm" % float(self.overhang*1.15*1000)
            self.summary_mec += \
                "\r\nAirgap dims: %s mm" \
                % (str(np.round([i*1000 for i in self.air_gap_dims], 2)))
            self.summary_mec += \
                "\r\nWindings per layer: %s" % (str(self.N_windings))
            self.summary_mec += \
                "\r\nTop plate to bottom plate ≥ %.2f mm (recommended)" \
                % (self.washer_to_bottom_plate*1000)



@dataclass
class SpeakerSystem():
    """
    One or two degree of freedom acoustical system class.

    Can be two types: ["Closed box", "Free-air"]
    """

    spk: SpeakerDriver
    global CONS

    def __post_init__(self):
        """Add more attributes."""
        self.error = self.spk.error
        Bl = self.spk.Bl
        Rdc = self.spk.Rdc
        Mms = self.spk.Mms
        Rms = self.spk.Rms
        Kms = self.spk.Kms
        Sd = self.spk.Sd
        excitation = [form.get_value("excitation_value"), form.get_value("excitation_unit")["userData"]]
        Rnom = form.get_value("nominal_impedance")
        self.V_in = calculate_input_voltage(excitation, Rdc, Rnom)
        self.box_type = form.get_value("box_type")
        self.dof = int(form.get_value("dof")[0])

        # Read box parameters
        if self.box_type == "Closed box":
            self.Vb, self.Qa = form.get_value("Vb"), form.get_value("Qa")
        else:
            self.Vb, self.Qa = [np.inf] * 2

        # Read dof
        if self.dof > 1:
            m2, k2, c2 = form.get_value("m2"), form.get_value("k2"), form.get_value("c2")

        self.Kbox = Kbox = Sd**2*CONS.Kair/self.Vb

        Rbox = ((Kms + Kbox) * Mms)**0.5 / self.Qa
        zeta_boxed_speaker = (Rbox + Rms + Bl**2/Rdc) / 2 / ((Kms+Kbox) * Mms)**0.5
        self.Qtc = 1 / 2 / zeta_boxed_speaker

        self.fb = 1 / 2 / np.pi * ((Kms+Kbox) / Mms)**0.5
        self.fb_d = self.fb * (1 - 2 * zeta_boxed_speaker**2)**0.5

        if np.iscomplex(self.fb_d):
            self.fb_d = None

        self.Vas = CONS.Kair / Kms * Sd**2

        # State space model
        if not hasattr(self, "sysx1"):
            # State, input, output and feed-through matrices and state space system definitions
            if self.dof == 1:
                ass = np.array([
                    [0, 1],
                    [-Kbox/Mms-Kms/Mms, -Bl**2/Rdc/Mms-Rms/Mms-Rbox/Mms]
                    ])
                bss = np.array([[0], [Bl/Rdc/Mms]])
                cssx1 = np.array([1, 0])
                cssx1t = np.array([0, 1])
                dss = np.array([0])
            if self.dof == 2:
                ass = np.array([
                    [0, 1, 0, 0],
                    [-(Kms+Kbox)/Mms, -(Rms+Rbox+Bl**2/Rdc)/Mms, (Kms+Kbox)/Mms, (Rms+Rbox+Bl**2/Rdc)/Mms],
                    [0, 0, 0, 1],
                    [(Kms+Kbox)/m2, (Rms+Rbox+Bl**2/Rdc)/m2, -(Kms+Kbox+k2)/m2, -(Rms+Rbox+Bl**2/Rdc+c2)/m2]
                    ])
                bss = np.array([[0], [Bl/Rdc/Mms], [0], [-Bl/Rdc/m2]])
                cssx1 = np.array([1, 0, 0, 0])
                cssx1t = np.array([0, 1, 0, 0])
                cssx2 = np.array([0, 0, 1, 0])
                cssx2t = np.array([0, 0, 0, 1])
                dss = np.array([0])

            self.sysx1 = signal.StateSpace(ass, bss, cssx1, dss)
            self.sysx1t = signal.StateSpace(ass, bss, cssx1t, dss)
            if self.dof > 1:
                self.sysx2 = signal.StateSpace(ass, bss, cssx2, dss)
                self.sysx2t = signal.StateSpace(ass, bss, cssx2t, dss)

        # Output arrays
        _, self.x1_1V = signal.freqresp(self.sysx1, w=CONS.w)  # hata veriyo
        _, self.x1t_1V = signal.freqresp(self.sysx1t, w=CONS.w)
        self.x1 = self.x1_1V * self.V_in
        self.x1t = self.x1 * CONS.w

        if self.dof > 1:
            _, self.x2_1V = signal.freqresp(self.sysx2, w=CONS.w)
            _, self.x2t_1V = signal.freqresp(self.sysx2t, w=CONS.w)
            self.x2 = self.x2_1V * self.V_in
            self.x2t = self.x2 * CONS.w

        # SPL calculation with simplified radiation impedance * acceleration
        a = np.sqrt(Sd/np.pi)  # piston radius
        p0_1V = 0.5 * 1j * CONS.w * CONS.RHO * a**2 * self.x1t_1V
        pref = 2e-5
        SPL_1V = 20*np.log10(np.abs(p0_1V)/pref)

        # Xmax limited SPL calculation
        x1_max_rms_array = [np.array(self.spk.Xmax/2**0.5)] * len(CONS.f)
        x1t_max_rms_array = np.abs(x1_max_rms_array * CONS.w * 1j)
        p0_xmax_limited = 0.5 * 1j * CONS.w * CONS.RHO * a**2 * x1t_max_rms_array
        self.SPL_Xmax_limited = 20*np.log10(np.abs(p0_xmax_limited)/pref)

        self.SPL = SPL_1V + 20*np.log10(self.V_in)
        self.P_real = self.V_in ** 2 / Rdc
        self.Z = Rdc / (1 - Bl*self.x1t_1V)

        # Calculate some extra parameters
        self.x1tt_1V = self.x1t_1V * CONS.w * 1j
        self.x1tt = self.x1tt_1V * self.V_in
        self.force_1 = - self.x1tt * Mms  # inertial force
        self.force_coil = Bl * np.real(self.V_in / self.Z)

        if self.dof > 1:
            self.x2tt_1V = self.x2t_1V * CONS.w * 1j
            self.x2tt = self.x2tt_1V * self.V_in
            self.force_2 = - self.x2tt * m2  # inertial force

        if self.box_type == "Closed box" and self.fb_d:
            interested_frequency = self.fb_d * 4
        elif self.box_type == "Closed box":
            interested_frequency = self.fb * 4
        else:
            interested_frequency = self.spk.fs * 4

        f_interest, f_inter_idx = find_nearest_freq(CONS.f, interested_frequency)

        self.summary = "SPL at %iHz: %.1f dB" %\
            (f_interest, self.SPL[f_inter_idx])

        # Info over closed box
        if self.box_type == "Closed box":

            self.summary += "\r\n"

            if self.fb_d:  # not overdamped
                self.summary += "\r\nQtc: %.3g    fb: %.3g Hz / %.3g Hz (damped / undamped)" \
                                % (self.Qtc, self.fb_d, self.fb)
            else:  # overdamped
                self.summary += "\r\nQtc: %.3g    fb: %.3g Hz (overdamped)" \
                                % (self.Qtc, self.fb)

            self.summary += "\r\nVas: %.3g l    Kbox: %.4g N/mm" \
                            % (self.Vas * 1e3, self.Kbox/1000)

        # Info over second degree of freedom damping and invalid loudsp
        if self.dof == 2:

            zeta2_free = c2 / 2 / ((Mms + m2) * k2)**0.5
            if c2 > 0:
                q2_free = 1 / 2 / zeta2_free
            else:
                q2_free = np.inf

            f2_undamped = 1 / 2 / np.pi * (k2 / (Mms + m2))**0.5
            f2_damped = f2_undamped * (1 - 2 * zeta2_free**2)**0.5
            if np.iscomplex(f2_damped):
                f2_damped = None

            self.summary += "\r\n"

            self.summary += ("\r\n" + "While M2 is rigidly coupled with Mms;")

            self.summary += ("\r\n" + "ζ2: %.3g    Q2: %.3g" %
                             (zeta2_free, q2_free))

            if f2_damped:  # not overdamped
                self.summary += ("\r\n" + "f2: %.3g Hz / %.3g Hz (damped / undamped)" %
                                 (f2_damped, f2_undamped))
            else:  # overdamped
                self.summary += ("\r\n" + "f2: %.3g Hz (overdamped)" %
                                 (f2_undamped))

        # Info over displacements
        self.summary += "\r\n"

        if self.dof == 1:
            self.summary += "\r\nPeak displacement at %iHz: %.3g mm" %\
                (f_interest, np.abs(self.x1)[f_inter_idx] * 1e3 * 2**0.5)

            self.summary += "\r\nPeak displacement overall: %.3g mm" %\
                np.max(np.abs(self.x1) * 1e3 * 2**0.5)

        elif self.dof == 2:
            self.summary += "\r\nPeak relative displacement at %iHz: %.3g mm" %\
                (f_interest, np.abs(self.x1[f_inter_idx]-self.x2[f_inter_idx])*1e3*2**0.5)

            self.summary += "\r\nPeak relative displacement overall: %.3g mm" %\
                np.max(np.abs(self.x1-self.x2) * 1e3 * 2**0.5)

        else:
            self.summary += "Unable to identify the total degrees of freedom"

        # Suspension feasibility
        self.summary += "\r\nF_motor(V_in) / F_suspension(Xmax/2) = {:.0%}".format(
            Bl * self.V_in / Rdc / Kms / self.spk.Xmax * 2)