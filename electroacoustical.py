# This file is part of Speaker Calculator - Loudspeaker design and calculations tool
# Copyright (C) 2026 - Kerem Basaran
# https://github.com/kbasaran
__email__ = "kbasaran@gmail.com"

# Linecraft is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3
# of the License, or (at your option) any later version.

# Linecraft is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.

# You should have received a copy of the GNU General Public
# License along with Speaker Calculator. If not, see <https://www.gnu.org/licenses/>

import dataclasses as dtc
import numpy as np
import sympy as smp
import sympy.physics.mechanics as mech
from sympy.solvers import solve
from scipy import signal
from sympy.abc import t

def calculate_air_mass(Sd: float) -> float:
    """
    Air mass on diaphragm; the difference between Mms and Mmd.
    m² in, kg out.
    """
    return 1.13*(Sd)**(3/2)


def calculate_Lm(Bl, Re, Mms, Sd, RHO=1.1839, c_air=(101325 * 1.401 / 1.1839)**0.5):
    "Calculate Lm@Re, 1W, 1m."
    if Sd == 0:
        return -np.inf
    elif Sd < 0:
        raise RuntimeError("Surface area cannot have a negative value: " + Sd)

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
    # xty: RMS velocity of the disc along its axis, per frequency
    a = np.sqrt(Sd/np.pi)  # piston radius
    freqs = np.array(xty[0]).flatten()
    p0 = 0.5 * 1j * freqs*2*np.pi * settings.RHO * a**2 * np.array(xty[1]).flatten()
    pref = 2e-5
    SPL = 20*np.log10(np.abs(p0)/pref)
    return freqs, SPL


@dtc.dataclass
class Settings:
    RHO: float = 1.1839  # density of air at 25 degrees celcius
    P0: int = 101325  # atmospheric pressure
    GAMMA: float = 1.401  # adiabatic index of air
    Kair: float = P0 * GAMMA
    c_air: float = (Kair / RHO)**0.5


@dtc.dataclass
class Wire:
    name: str
    wire_type: str
    nominal_size: float
    shape: str
    w_avg: float
    h_avg: float
    w_max: float
    resistance: float  # ohm/m
    mass_density: float  # kg/m
    notes: str
    
    def __post_init__(self):
        self.shape = self.shape.lower()
    
    def get_summary(self) -> str:
        "Summary in markup language."
        return f"{self.name}        {self.shape[0].upper() + self.shape[1:]}"
                

@dtc.dataclass
class Coil:
    carrier_OD: float
    wire: Wire
    N_windings: tuple
    w_stacking_coef: float
    
    def _calc_turn_radius_per_layer(self):
        turn_radii_wire_center_to_axis = list()
        for i_layer in range(len(self.N_windings)):
            if i_layer == 0:
                turn_radii_wire_center_to_axis.append(
                    self.carrier_OD/2 + self.wire.w_avg/2
                    )
            else:
                turn_radii_wire_center_to_axis.append(
                    self.carrier_OD/2 + self.wire.w_avg/2
                    + (self.w_stacking_coef * i_layer * self.wire.w_avg)
                    )
        return turn_radii_wire_center_to_axis

    def total_wire_length(self):
        wire_length_per_layer = [2 * np.pi * radius * self.N_windings[i_layer] for i_layer, radius in enumerate(self.turn_radii)]
        return sum(wire_length_per_layer)

    def __post_init__(self):
        if not all([i > 0 for i in self.N_windings]):
            raise RuntimeError("Coil has layers with 0 windings.")
        self.turn_radii = self._calc_turn_radius_per_layer()
        self.N_layers = len(self.N_windings)
        self.h_winding = self.wire.h_avg * self.N_windings[0]
        self.mass = self.total_wire_length() * self.wire.mass_density
        self.Re = self.total_wire_length() * self.wire.resistance
        
        self.w_max = self.wire.w_max * self.N_layers
        self.w_nom = self.wire.w_avg * (1 + (self.N_layers - 1) * self.w_stacking_coef)

        self.OD_nom = 2 * self.turn_radii[-1] + self.wire.w_avg
        self.OD_max = self.carrier_OD + 2 * self.w_max

        self.name = (str(self.N_layers) + "L " + self.wire.name).strip()
        section_total_area = self.w_nom * self.h_winding
        if self.wire.shape == "circular":
            section_conductor_area = self.wire.nominal_size**2 * np.pi / 4 * sum(self.N_windings)
            self.fill_ratio = section_conductor_area / section_total_area
        elif self.wire.shapre == "rectangular":
            section_conductor_area = self.wire.nominal_size**2 * sum(self.N_windings)
            self.fill_ratio = section_conductor_area / section_total_area
        else:
            self.fill_ratio = np.nan
            raise ValueError("Unrecognized shape definition for wire {self.wire.name}: {self.wire.shape}")
    
    def get_wire_name_and_layers(self):
        return (
            self.wire.name,
            self.N_layers,
            )

    def get_summary(self) -> str:
        "Summary in markup language."
        summary = ("#### Windings"
                   "<br></br>"
                   f"{self.wire.name}, {self.wire.shape[0].upper() + self.wire.shape[1:]}, N<sub>wind</sub>: {sum(self.N_windings)}"
                   "<br></br>"
                   # f"N<sub>windings_total</sub>: {sum(self.N_windings)}"
                   # "<br></br>"
                   # f"N<sub>wind_per_layer</sub>:\n"
                   f"{self.N_windings}"
                   "<br></br>"
                   f"m<sub>windings</sub>: {(self.mass * 1e3):.4g} g"
                   "<br></br>"
                   f"Fill ratio: {self.fill_ratio * 100:.3g} %"

                   "<br></br>"
                   "<br></br>"
                   f"L<sub>total</sub>: {self.total_wire_length():.3g} m        "
                   f"h<sub>nom</sub> : {self.h_winding * 1000:.4g} mm"
                   "<br></br>"
                   f"w<sub>nom</sub> : {self.w_nom*1e3:.4g} mm        w<sub>max</sub> : {self.w_max*1e3:.4g} mm"
                   "<br></br>"
                   f"OD<sub>nom</sub> : {self.OD_nom*1e3:.4g} mm        OD<sub>max</sub> : {self.OD_max*1e3:.4g} mm"

                   )
        return summary


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
        return int(round(n_winding))

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
    t_former : float = None
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
    
    def __post_init__(self):
        self.former_ID = self.coil.carrier_OD - self.t_former
        self.air_gap_width = (self.airgap_clearance_inner
                         + self.t_former
                         + self.coil.w_max
                         + self.airgap_clearance_outer
                         )
    
    def get_summary(self) -> str:
        "Summary in markup language."

        self.airgap_radii = list((
            self.former_ID/2 - self.airgap_clearance_inner,
            self.air_gap_width,
            self.former_ID/2 - self.airgap_clearance_inner + self.air_gap_width,
         ))

        summary = (
            "## Motor"
            "<br></br>"
            f"Overhang : {(self.coil.h_winding - self.h_top_plate) *500:.4g} mm"
            "<br></br>"
            f"OD<sub>pole piece</sub> : {(self.coil.carrier_OD - 2 * (self.t_former + self.airgap_clearance_inner)) * 1000:.4g} mm"
            "<br></br>"
            f"ID<sub>top plate</sub> : {(self.coil.OD_max + 2 * self.airgap_clearance_outer) * 1000:.4g} mm"
            "<br></br>"
            "Airgap radii:"
            "<br></br>"
            f"{self.airgap_radii[0] * 1e3:.3f} + "
            f"{self.airgap_radii[1] * 1e3:.3f} = "
            f"{self.airgap_radii[2] * 1e3:.3f} mm"
            "<br/>  \n"
            f"{self.coil.get_summary()}"
            )

        return summary


@dtc.dataclass
class SpeakerDriver:
    """
    Speaker driver class.
    Mostly to carry data. It also does some Thiele & Small calculations.
    Does not make frequency dependent calculations such as SPL, impedance.
    """
    fs: float
    Sd: float
    Qms: float
    Bl: float = None  # provide only if motor is None
    Re: float = None  # provide only if motor is None
    Mms: float = None  # provide only if both motor and Mmd are None
    Mmd: float = None  # provide only if both motor and Mms are None
    motor: None | Motor = None  # None or 'Motor' instance
    dead_mass: float = None  # provide only if motor is 'Motor' instance
    Rlw: float = 0  # series electrical resistance between the speaker terminals and the coil (leadwire etc.). provide only if motor is 'Motor' instance.
    Xpeak: float = None

    def __post_init__(self):

        # verification when speaker is specified without a motor object
        if self.motor is None and self.Rlw != 0:
            raise RuntimeError("Do not define leadwire resistance Rlw when Re is already defined.")

        # when a motor object is provided
        if isinstance(self.motor, Motor) and self.dead_mass is not None:
            # check if some parameters are specified twice
            already_available_in_Motor = ("Bl", "Re")
            if not all([getattr(self, val) is None for val in already_available_in_Motor]):
                raise RuntimeError("These attributes should not be specified when motor is already specified:"
                                   f"\n{already_available_in_Motor}")
            # derive parameters using info from Motor
            self.Bl = self.motor.coil.total_wire_length() * self.motor.Bavg
            self.Re = self.motor.coil.Re + self.Rlw
            try:
                if "Mms" in locals().keys():
                    raise RuntimeError("Double definition. 'Mms' should not be defined in object instantiation"
                                       " when 'motor' is already defined.")
                self.Mmd = self.dead_mass + self.motor.coil.mass
                self.Mms = self.Mmd + calculate_air_mass(self.Sd)
            except NameError:
                raise RuntimeError("Unable to calculate 'Mms' and/or 'Mmd' with known parameters.")
        # no motor object is provided, directly Mms given    
        elif self.Mms is not None:
            if self.Mmd is not None:
                raise RuntimeError("Not allowed to define both Mmd and Mms in 'SpeakerDriver' object instantion.")
            self.Mmd = self.Mms - calculate_air_mass(self.Sd)
        # no motor object is provided, directly Mmd given
        elif self.Mmd is not None:
            self.Mms = self.Mmd + calculate_air_mass(self.Sd)
        # not enough info provided
        else:
            raise ValueError("Insufficient parameters. Define [motor, dead_mass], Mmd or Mms.")

        # more derived parameters
        self.Kms = self.Mms * (self.fs * 2 * np.pi)**2
        self.Rms = (self.Mms * self.Kms)**0.5 / self.Qms
        self.Ces = self.Bl**2 / self.Re
        self.Qts = (self.Mms * self.Kms)**0.5 / (self.Rms + self.Ces)
        self.Qes = (self.Mms * self.Kms)**0.5 / self.Ces
        zeta_speaker = 1 / 2 / self.Qts
        self.fs_damped = self.fs * (1 - 2 * zeta_speaker**2)**0.5  # complex number if overdamped system
        
    def Lm(self, settings):
        return calculate_Lm(self.Bl, self.Re, self.Mms, self.Sd, settings.RHO, settings.c_air)  # sensitivity per W@Re
    
    def Vas(self, settings):
        return settings.Kair / self.Kms * self.Sd**2

    def get_summary(self, settings, V_spk=0) -> str:
        "Summary in markup language."
        summary = ("## Speaker unit"
                   "<br></br>"
                   f"L<sub>m</sub> : {self.Lm(settings):.2f} dBSPL        "
                   f"R<sub>e</sub> : {self.Re:.2f} ohm"
                   "<br></br>"
                   f"Bl : {self.Bl:.4g} Tm        "
                   f"Bl²/R<sub>e</sub> : {self.Bl**2/self.Re:.3g} N²/W"
                   "<br></br>"
                   f"Q<sub>es</sub> : {self.Qes:.3g}        "
                   f"Q<sub>ts</sub> : {self.Qts:.3g}"
                   "<br></br>"
                   f"V<sub>as</sub> : {self.Vas(settings) * 1e3:.4g} l"
                   
                   "<br/>  \n"
                   f"#### Mass and suspension"
                   "<br></br>"
                   f"M<sub>ms</sub> : {self.Mms*1000:.4g} g        "
                   f"M<sub>md</sub> : {self.Mmd*1000:.4g} g"
                   "<br></br>"
                   f"K<sub>ms</sub> : {self.Kms / 1000:.4g} N/mm        "
                   f"R<sub>ms</sub> : {self.Rms:.4g} kg/s"

                   "<br/>  \n"
                   "#### Displacements"
                   "<br></br>"
                   f"X<sub>peak</sub> : {self.Xpeak*1000:.3g} mm"
                   )
        
        if self.motor is not None:
            Xcrash = calculate_coil_to_bottom_plate_clearance(self.Xpeak)
            summary += f"      X<sub>crash</sub> : {Xcrash*1000:.3g} mm (recomm.)"
        
        if V_spk > 0:
            # Suspension feasibility
            summary += (
                   # "\n"
                   # "##### Motor force vs. suspension"
                   "<br></br>"
                   "F<sub>motor, RMS</sub> / F<sub>suspension</sub>(X<sub>peak</sub>/2): "
                   f"{self.Bl * V_spk / self.Re / self.Kms / (self.Xpeak / 2):.0%}"
                    )
            
        if self.motor is not None:       
            summary += "\n----\n"
            summary += self.motor.get_summary()

        return summary


@dtc.dataclass
class Enclosure:
    # All units are SI
    Vb: float
    Qa: float
    # Ql: float = np.inf

    def Vba(self):  # effective acoustical volume
        return self.Vb

    def K(self, settings, Sd):
        return Sd**2 * settings.Kair / self.Vba()

    def R(self, settings, Sd, Mms, Kms):
        """
        Damping at fb due to air absorption in box. Calculated from Qa.
        """
        # return ((Kms + self.K(Sd)) * Mms)**0.5 / self.Qa + ((Kms + self.K(Sd)) * Mms)**0.5 / self.Ql
        return ((Kms + self.K(settings, Sd)) * Mms)**0.5 / self.Qa

    # def Vba(self):  # acoustical volume higher than actual due to internal damping
    #     # below formula is shown in GUI tooltip. Update tooltip if modifiying.
    #     return self.Vb * (0.94/self.Qa + 1)  # based on results from UniBox. Original source of formula not found.


@dtc.dataclass
class ParentBody:
    # All units are SI
    m: float
    k: float
    c: float

    def zeta(self, coupled_masses=0):
        # damping ratio
        return self.c / 2 / ((self.m + coupled_masses) * self.k)**0.5

    def Q(self, coupled_masses=0):
        if self.c > 0:
            return 1 / 2 / self.zeta(coupled_masses)
        else:
            return np.inf

    def f(self, coupled_masses=0):
        # undamped natural frequency a.k.a. resonance frequency
        f2_undamped = 1 / 2 / np.pi * (self.k / (self.m + coupled_masses))**0.5
        # f2_damped = f2_undamped * (1 - 2 * self.zeta()**2)**0.5
        # if np.iscomplex(f2_damped):
        #     f2_damped = None
        return f2_undamped


@dtc.dataclass
class PassiveRadiator:
    # All units are SI
    m: float  # without coupled air mass. a.k.a mmd_pr.
    k: float  # kmpr
    Q: float  # rmpr
    S: float  # surface area

    def m_s(self):
        # passive radiator with coupled air mass included.
        return self.m + calculate_air_mass(self.S)

    def f_free(self):
        return 1 / 2 / np.pi * (self.k / self.m_s())**0.5

    def f_housed(self, settings, Vba):
        return 1 / 2 / np.pi * ((self.k + self.k_box(settings, Vba)) / self.m_s())**0.5

    def k_box(self, settings, Vba):
        "Stiffness from air in enclosure."
        return self.Spr**2 * settings.Kair / Vba

    def R(self, settings, Vba):
        return ((self.k_box(settings, Vba) + self.k) * self.m_s())**0.5 / self.Qp
        """
        Damping at fp due to port losses in case of vented box, or due to
        mechanical losses in case of passive raditor. Calculated from Qp.
        """
        return None


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


@dtc.dataclass
class SpeakerSystem:
    speaker: SpeakerDriver
    Rext: float = 0   # series electrical resistance from voltage geenrator to the speaker terminals.
                    # may be at the source amplifier or in the cables going to speaker terminals
    enclosure: None | Enclosure = None
    parent_body: None | ParentBody = None
    passive_radiator: None | PassiveRadiator = None
    dir_pr: int = 1
    settings: dtc.InitVar[Settings] = Settings()

    def __post_init__(self, settings):
        self._build_symbolic_ss_model()
        self.update_values(settings)

    def _build_symbolic_ss_model(self):
        # Static symbols
        # s: speaker
        # pb: parent body (second degree of freedom)
        # pr: passive radiator (third degree of freedom)
        Mms, Mpb, Mpr = smp.symbols("M_ms, M_2, M_pr", real=True, positive=True)
        Kms, Kpb, Kpr = smp.symbols("K_ms, K_2, K_pr", real=True, positive=True)
        Rms, Rpb, Rpr = smp.symbols("R_ms, R_2, R_pr", real=True, positive=True)
        Kair, Vba, Rbox = smp.symbols("Kair, V_ba, R_box", real=True, positive=True)
        Sd, Spr, Bl, Re, Rext = smp.symbols("S_d, S_pr, Bl, R_e, R_ext", real=True, positive=True)
        # Direction coefficient for passive radiator
        # 1 if same direction with speaker, 0 if orthogonal, -1 if reverse direction

        # Dynamic symbols
        x1, x2 = mech.dynamicsymbols("x(1:3)")
        xpr = mech.dynamicsymbols("x_pr")
        p_housing = mech.dynamicsymbols("p_housing")
        i_coil = mech.dynamicsymbols("i_coil")
        Vsource = mech.dynamicsymbols("V_source", real=True)

        # Derivatives
        x1_t, x1_tt = smp.diff(x1, t), smp.diff(x1, t, t)
        x2_t, x2_tt = smp.diff(x2, t), smp.diff(x2, t, t)
        xpr_t, xpr_tt = smp.diff(xpr, t), smp.diff(xpr, t, t)

        # define state space system
        eqns = [    

                (
                 - Mms * x1_tt
                 - (Rms + Rbox) * (x1_t - x2_t)
                 - Kms * (x1 - x2)

                 + p_housing * Sd
                 + i_coil * Bl
                 ),

                (
                 - Mpb * x2_tt
                 - Rpb * x2_t
                 - Kpb * x2
                 
                 + (Rms + Rbox) * (x1_t - x2_t)
                 + Kms * (x1 - x2)

                 + (Rpr + Rbox) * (xpr_t - x2_t)
                 + Kpr * (xpr - x2)
                 
                 - p_housing * Sd
                 - p_housing * Spr

                 - i_coil * Bl
                 ),

                (
                 - Mpr * xpr_tt
                 - (Rpr + Rbox) * (xpr_t - x2_t)
                 - Kpr * (xpr - x2)

                 + p_housing * Spr
                 ),
                
                ]

        eqns = []
        for i, eqn in enumerate(eqns):
            eqns[i] = eqn.subs(p_housing, - (Kair / Vba * (Spr * xpr + Sd * x1)))
            eqns[i] = eqn.subs(i_coil, (Vsource - Bl*(x1_t - x2_t)) / (Rext + Re))

        # p_housing = - (Kair / Vba * (Spr * xpr + Sd * x1))
        # i_coil = (Vsource - Bl*(x1_t - x2_t)) / (Rext + Re)
        # p and i are not added as state variables because they are linearly dependent on the other state variables
        # they could be added as solutions by adding in C and D above formulas

        state_vars = [x1, x1_t, x2, x2_t, xpr, xpr_t]  # state variables
        input_vars = [Vsource]  # input variables
        state_diffs = [var.diff() for var in state_vars]  # state differentials

        # dictionary of all sympy symbols used in model
        self.symbols = {key: val for (key, val) in locals().items() if isinstance(val, smp.Symbol)}
        
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

        self._symbolic_ss = {"A": A_sym,  # system matrix
                             "B": B_sym,  # input matrix
                             "C": C,  # output matrices dictionary, one per state variable
                             "D": D,  # feedforward
                             "state_vars": state_vars,
                            }

    def _get_parameter_names_to_values(self, settings) -> dict:
        "Get a dictionary of all the parameters related to the speaker system"
        "key: symbol variable name, val: value"

        parameter_names_to_values = {

            "Mms": self.speaker.Mms,
            "Kms": self.speaker.Kms,
            "Rms": self.speaker.Rms,
            "Sd": self.speaker.Sd,
            "Bl": self.speaker.Bl,
            "Re": self.speaker.Re,

            "Mpb": np.inf if self.parent_body is None else self.parent_body.m,
            "Kpb": 0 if self.parent_body is None else self.parent_body.k,
            "Rpb": 0 if self.parent_body is None else self.parent_body.c,

            "Mpr": np.inf if self.passive_radiator is None else self.passive_radiator.m_s(),  # with air coupled
            "Kpr": 0 if self.passive_radiator is None else self.passive_radiator.k,
            "Rpr": 0 if self.passive_radiator is None else self.passive_radiator.c,
            "Spr": 0 if self.passive_radiator is None else self.passive_radiator.Spr,
            "dir_pr": self.dir_pr,

            "Vba": 0 if self.enclosure is None else self.enclosure.Vba(),  # in fact Vba is infinite when no enclosure. but infinite is not allowed.
            "Rbox": 0 if self.enclosure is None else self.enclosure.R(
                settings,
                self.speaker.Sd,
                self.speaker.Mms,
                self.speaker.Kms,
                ),

            "Kair": 0 if self.enclosure is None else settings.Kair,  # 0 is trickery a bit, to disable the housing formulas.

            "Rext": self.Rext,

            }

        return parameter_names_to_values

    def get_symbols_to_values(self, settings):
        # Dictionary with sympy symbols as keys and values as values
        parameter_names_to_values = self._get_parameter_names_to_values(settings)
        return {symbol: parameter_names_to_values[name] for name, symbol in self.symbols.items()}

    def update_values(self, settings, **kwargs):
        # ---- set the attributes of self with values in kwargs
        dataclass_field_names = [dataclass_field.name for dataclass_field in dtc.fields(self)]
        for key, val in kwargs.items():
            if key in dataclass_field_names:
                setattr(self, key, val)
            else:
                raise KeyError("Not familiar with key '{key}'")

        # ---- Update scalars
        self.R_sys = self.speaker.Re + self.Rext

        # ---- Substitute values into system matrix and input matrix
        symbols_to_values = self.get_symbols_to_values(settings)
        A = np.array(self._symbolic_ss["A"].subs(symbols_to_values)).astype(float)
        B = np.array(self._symbolic_ss["B"].subs(symbols_to_values)).astype(float)

        # ---- Updates in relation to enclosure
        if isinstance(self.enclosure, Enclosure):
            zeta_boxed_speaker = (
                self.enclosure.R(settings, self.speaker.Sd, self.speaker.Mms, self.speaker.Mms) \
                                  + self.speaker.Rms + self.speaker.Bl**2 / self.speaker.Re) \
                / 2 / ((self.speaker.Kms+self.enclosure.K(settings, self.speaker.Sd)) * self.speaker.Mms)**0.5

            fb_undamped = 1 / 2 / np.pi * ((self.speaker.Kms+self.enclosure.K(settings, self.speaker.Sd)) / self.speaker.Mms)**0.5

            fb_damped = fb_undamped * (1 - 2 * zeta_boxed_speaker**2)**0.5
            if np.iscomplex(fb_damped):  # means overdamped
                fb_damped = np.nan

            self.fb = fb_undamped
            self.Qtc = np.inf if zeta_boxed_speaker == 0 else 1 / 2 / zeta_boxed_speaker

        else:
            self.fb = np.nan
            self.Qtc = np.nan


        # ---- Updates in relation to parent body
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
            if np.iscomplex(f2_damped):  # means overdamped
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
            # maybe disable showing Qtc when it is a PR
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

    def get_summary(self, settings, V_source:float=0) -> str:
        "Summary in markup language."
        V_spk = V_source / self.R_sys * self.speaker.Re
        summary = self.speaker.get_summary(settings, V_spk)

        summary += ("\n----\n"
                    "#### System"
                    "<br></br>"
                    f"R<sub>sys</sub>: {self.R_sys:.2f} ohm"
                   )
        
        if isinstance(self.enclosure, Enclosure):
            summary += (
                "<br/>  \n"
                "#### Enclosure"
                "<br></br>"
                f"Q<sub>tc</sub>: {self.Qtc:.3g}      f<sub>b</sub>: {self.fb:.4g} Hz"
                "<br></br>"
                f"K<sub>enc,s</sub>: {self.enclosure.K(settings, self.speaker.Sd)/1000:.4g} N/mm"
                )
            if isinstance(self.passive_radiator, PassiveRadiator):
                summary += "      K<sub>enc,pr</sub>: {self.enclosure.K(settings, self.passive_radiator.Spr):.4g} N/mm"
                
        if isinstance(self.parent_body, ParentBody):
            coupled_masses = self.speaker.Mmd + getattr(self.passive_radiator, "m", 0)
            summary += (
                "<br/>  \n"
                "#### Parent body"
                "\n"
                "##### Assuming child masses are decoupled"
                "<br></br>"
                f"Q<sub>pb</sub>: {self.parent_body.Q():.4g}      f<sub>pb</sub>: {self.parent_body.f():.4g} Hz"
                "\n"
                "##### Assuming child masses are coupled"
                "<br></br>"
                f"Q<sub>pb,c</sub>: {self.parent_body.Q(coupled_masses):.4g}      f<sub>pb,c</sub>: {self.parent_body.f(coupled_masses):.4g} Hz"
                )

        return summary

    def power_at_Re(self, Vspeaker):
        # Calculation of power at Re for given voltage at the speaker terminals
        return Vspeaker**2 / self.Re
    
    def get_displacements(self, V_source, freqs: np.array) -> dict:
        # Voltage argument given in RMS
        # outputs in m
        disps = dict()
        w = 2 * np.pi * np.array(freqs)

        x1 = signal.freqresp(self.ss_models["x1(t)"], w=w)[1] * V_source

        disps["Diaphragm, peak"] = x1 * 2**0.5
        disps["Diaphragm, RMS"] = x1

        if self.parent_body is not None:  # in fact, better return these even when no parnt_body, and filter in plotting
            x2 = signal.freqresp(self.ss_models["x2(t)"], w=w)[1] * V_source
            disps["Parent body, RMS"] = x2
            disps["Diaphragm, peak, relative to parent"] = (x1 - x2) * 2**0.5
            disps["Diaphragm, RMS, relative to parent"] = (x1 - x2)

        if self.passive_radiator is not None:  # remove later and return always
            xpr = signal.freqresp(self.ss_models["x_pr(t)"], w=w)[1] * V_source
            disps["PR/vent, RMS"] = xpr
            disps["PR/vent, peak"] = xpr * 2**0.5
            if self.parent_body is not None:
                disps["PR/vent, peak, relative to parent"] = (xpr - x2) * 2**0.5
                disps["PR/vent, RMS, relative to parent"] = (xpr - x2)
                
        return disps

    def get_velocities(self, V_source, freqs: np.array) -> dict:
        # Voltage argument given in RMS
        # outputs in m/s
        velocs = dict()
        w = 2 * np.pi * np.array(freqs)

        x1_t = signal.freqresp(self.ss_models["Derivative(x1(t), t)"], w=w)[1] * V_source
        velocs["Diaphragm, RMS"] = x1_t

        if self.parent_body is not None:  # remove later and return always
            x2_t = signal.freqresp(self.ss_models["Derivative(x2(t), t)"], w=w)[1] * V_source
            velocs["Parent body, RMS"] = x2_t
            velocs["Diaphragm, RMS, relative to parent"] = x1_t - x2_t

        if self.passive_radiator is not None:  # remove later and return always
            xpr_t = signal.freqresp(self.ss_models["Derivative(x_pr(t), t)"], w=w)[1] * V_source
            velocs["PR/vent, RMS"] = xpr_t
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
            x1t_relative_x2t = velocs["Diaphragm, RMS"]
        else:
            x1t_relative_x2t = velocs["Diaphragm, RMS, relative to parent"]

        imps["Impedance speaker"] = self.R_sys / (1 - self.speaker.Bl * x1t_relative_x2t) - self.Rext  # speaker only
        if self.Rext > 0:  # remove later and return always
            imps["Impedance incl. source, cables"] = imps["Impedance speaker"] + self.Rext
    
        return imps

    def get_forces(self, V_source, freqs: np.array) -> dict:
        # Voltage argument given in RMS
        # force coil means force generated by coil
        # force speaker means force generated by speaker (inertial forces)
        forces = dict()
        velocs = self.get_velocities(V_source, freqs)
        accs = self.get_accelerations(V_source, freqs)

        # relative velocity of coil (x1) to magnetic field (parent body, x2)
        if self.parent_body is None:
            x1t_relative_x2t = velocs["Diaphragm, RMS"]
        else:
            x1t_relative_x2t = velocs["Diaphragm, RMS, relative to parent"]

        force_coil = np.abs(self.speaker.Bl * (V_source - self.speaker.Bl * x1t_relative_x2t) / self.R_sys)
        force_speaker = accs["Diaphragm, RMS"] * self.speaker.Mms  # inertial force
        
        forces = {}
        forces["Lorentz force, RMS"] = force_coil
        forces["Force from speaker to parent body, RMS"] = force_speaker
        
        if self.passive_radiator is None:
            force_pr = np.zeros(len(force_speaker))
        else:
            force_pr = accs["PR/vent, RMS"] * self.passive_radiator.m_s()  # inertial force
            forces["Force from passive radiator to parent body, RMS"] = force_pr
            # forces["Reaction force from reference frame"] += force_pr

        if self.parent_body is None:
            force_pb = np.zeros(len(force_speaker))
        else:
            force_pb = accs["Parent body, RMS"] * self.parent_body.m  # inertial force
            forces["Force from parent body to reference frame, RMS"] = force_pb + force_pr + force_speaker

        return forces

    def get_phases(self, freqs: np.array) -> dict:
        # Phase for displacements
        # output in degrees
        phases = dict()
        disps = self.get_displacements(1, freqs)

        phases["Diaphragm"] = np.angle(disps["Diaphragm, RMS"], deg=True)

        if self.parent_body is not None:
            phases["Parent body"] = np.angle(disps["Parent body, RMS"], deg=True)

        if self.passive_radiator is not None:
            phases["PR/vent"] = np.angle(disps["PR/vent, RMS"], deg=True)
            
        return phases


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
    
    freqs = generate_freq_list(10, 3000, 48*8)


    # ---- do default model of 0.1.6
    enclosure = Enclosure(1e-3, 200)
    parent_body = ParentBody(0.1, 25e3, 4)
    my_speaker = SpeakerDriver(111, 53.5e-4, 6.51, Bl=4.78, Re=4.18, Mms=5.09e-3)
    my_system = SpeakerSystem(my_speaker,
                              parent_body=None,
                              enclosure=None,
                              passive_radiator=None,
                              )

    my_system.update_values(settings,
                            speaker=my_speaker,
                            Rext=1,
                            enclosure = enclosure,
                            parent_body = None,
                            # passive_radiator = pr,
                            )
    
    my_system.update_values(settings,
                            speaker=my_speaker,
                            Rext=1,
                            enclosure = None,
                            parent_body = parent_body,
                            # passive_radiator = pr,
                            )

    
    my_system.update_values(settings,
                            speaker=my_speaker,
                            Rext=1,
                            enclosure = None,
                            parent_body = None,
                            # passive_radiator = pr,
                            )
    
    my_system.update_values(settings,
                            speaker=my_speaker,
                            Rext=1,
                            enclosure = None,
                            parent_body = parent_body,
                            passive_radiator = None,
                            )
        
    my_system.update_values(settings,
                            speaker=my_speaker,
                            Rext=0,
                            enclosure = enclosure,
                            parent_body = None,
                            passive_radiator = None,
                            )

    # do test model for unibox - Qa / Ql
    # enclosure = Enclosure(0.05, 9999)
    # my_speaker = SpeakerDriver(100, 52e-4, 8, Bl=3, Re=4, Mms=7.7e-3)
    # my_system = SpeakerSystem(my_speaker, enclosure=enclosure)
    # x1 = signal.freqresp(my_system.ss_model, w=np.array([100, 200]))
    
    import matplotlib.pyplot as plt
    
    # ---- Time signal
    t = np.arange(0, 0.1, 1/100000)
    u = 2**0.5 * np.sin(25 * 2 * np.pi * t)
    youts = {}
    for i, (key, model) in enumerate(my_system.ss_models.items()):
        _, _, yout = signal.lsim(model, U=u, T=t)
        youts[key] = yout[:, i]
    
    print("relative disps: min, max")
    print(min(youts['x1(t)'] - youts['x2(t)']), max(youts['x1(t)'] - youts['x2(t)']))
    plt.plot(t, youts['x1(t)'])
    plt.plot(t, youts['x2(t)'])
    plt.plot(t, youts['x1(t)'] - youts['x2(t)'])
    plt.plot(t, youts['x_pr(t)'])
    plt.grid()
    plt.show()
    
    # ---- Print out values at frequencies
    
    # disps = my_system.get_displacements(1, 25)
    # disp_x1 = disps["Diaphragm, peak"]
    # # disp_x2 = disps["Parent body, RMS"] * 2**0.5
    # print("disps: real, abs")
    # print(np.real(disp_x1 - disp_x2), np.abs(disp_x1 - disp_x2))

    
    # forces = my_system.get_forces(1, 25)
    # print("forces: real, abs")
    # print(np.real(forces["Force from parent body to reference frame, RMS"]), np.abs(forces["Force from parent body to reference frame, RMS"]))

    w, y = signal.freqresp(my_system.ss_models["x1(t)"], w=2*np.pi*freqs)
    y_rms_for_10Vrms = np.abs(y) * 10
    y_for_10Vrms = y_rms_for_10Vrms * 2**0.5
    plt.semilogx(freqs, y_rms_for_10Vrms)
    plt.grid()
    plt.title("x1(t), RMS")
    for i, freq in enumerate(freqs):
        if int(freq) == 200 or i==0 or i==len(freqs)-1:
            print(f"{freqs[i]:.5g}Hz: {y_rms_for_10Vrms[i] * 1e3:.5g}mm RMS")
    
    return my_system


if __name__ == "__main__":
    my_system = tests()
