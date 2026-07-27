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

import dataclasses as dtc
import numpy as np
from config.physics import air
from core.calculations import calculate_air_mass

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
    N_windings: list
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
        elif self.wire.shape == "rectangular":
            section_conductor_area = self.wire.nominal_size**2 * sum(self.N_windings)
            self.fill_ratio = section_conductor_area / section_total_area
        else:
            self.fill_ratio = np.nan
            raise ValueError(f"Unrecognized shape definition for wire {self.wire.name}: {self.wire.shape}")

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
class Enclosure:
    # All units are SI
    Vb: float
    Qa: float
    Ql: float = np.inf  # leakage-loss quality factor; inf -> no leakage

    def Vba(self):  # effective acoustical volume
        return self.Vb

    def K(self, Sd):
        if self.Vb == 0:
            return 0
        else:
            return Sd**2 * air.Kair / self.Vba()

    def R(self, Sd, Mms, Kms):
        """
        Acoustic loss resistance of the enclosure [Pa.s/m^3], combining internal
        absorption (Qa) and leakage (Ql).

        It is referenced to the driver's boxed resonance so that, for a sealed
        single-driver box, it reproduces the familiar Qa/Ql damping. Because it
        is applied to the *volume* velocity into the box, the state-space model
        weights each radiator's reaction by its own area (Sd, Spr) and couples
        the driver and passive radiator through the shared lossy air.

        The loss quality factors combine reciprocally: 1/Qb = 1/Qa + 1/Ql.
        """
        if self.Vb == 0 or Sd == 0:
            return 0
        # driver-referred mechanical loss for Qa = Ql = 1, divided by Sd**2 to
        # express it as an acoustic resistance acting on volume velocity
        mech_ref = ((Kms + self.K(Sd)) * Mms)**0.5
        return mech_ref / Sd**2 * (1 / self.Qa + 1 / self.Ql)


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
        # For the *displacement response-peak* frequency (not the damped natural /
        # ringing frequency) use w0*sqrt(1 - 2*zeta**2); see SpeakerDriver.__post_init__
        # for the undamped-natural vs damped-natural vs response-peak distinction.
        # f2_response_peak = f2_undamped * (1 - 2 * self.zeta()**2)**0.5
        # if np.iscomplex(f2_response_peak):
        #     f2_response_peak = None
        return f2_undamped


@dtc.dataclass
class PassiveRadiator:
    # All units are SI
    m: float  # moving mass without coupled air mass. a.k.a mmd_pr.
    k: float  # suspension stiffness. a.k.a kmpr.
    R: float  # mechanical damping resistance [N.s/m]. a.k.a rmpr. Box-independent.
    S: float  # surface area

    def m_s(self):
        # passive radiator with coupled air mass included.
        return self.m + calculate_air_mass(self.S)

    def f_free(self):
        return 1 / 2 / np.pi * (self.k / self.m_s())**0.5

    def f_housed(self, Vba):
        return 1 / 2 / np.pi * ((self.k + self.k_box(Vba)) / self.m_s())**0.5

    def k_box(self, Vba):
        "Stiffness from air in enclosure."
        return self.S**2 * air.Kair / Vba

    def Qp(self, Vba):
        """
        Mechanical quality factor at the PR's housed resonance, derived from the
        box-independent damping resistance R. (At fp the loss is port losses for a
        vented box, or suspension losses for a passive radiator.)
        """
        return ((self.k_box(Vba) + self.k) * self.m_s())**0.5 / self.R


@dtc.dataclass
class BassReflexPort(PassiveRadiator):
    """A bass-reflex vent, modelled as a passive radiator with *zero* suspension
    stiffness (k = 0): the air plug in the tube has no restoring force of its own,
    so the whole "spring" is the enclosure air. It reuses the PassiveRadiator
    interface (m_s, k, R, S) unchanged, so the state-space model treats it exactly
    like a PR -- the Helmholtz resonance then falls out of the air coupling alone.

    Extra state vs. a PR:
        end_correction : total acoustic end-correction length [m], summed over both
                         ends, from the exit-flare geometry. It splits the total
                         co-vibrating acoustic mass m_s into the physical tube air
                         slug (self.m -> port_length) and the radiation end
                         correction, so the same tuning can be reported as a
                         buildable tube length.
    """
    end_correction: float = 0.0

    def m_s(self):
        # Total co-vibrating acoustic mass = tube air slug (self.m) + end-correction
        # air. Unlike a PR (flat piston -> calculate_air_mass), a vent's end
        # correction depends on its termination geometry, so it is carried
        # explicitly rather than assumed flanged.
        return self.m + air.RHO * self.S * self.end_correction

    def port_length(self):
        "Physical length of the vent tube [m] (excludes the end corrections)."
        return self.m / (air.RHO * self.S)

    def diameter(self):
        "Internal diameter of the (circular) port [m]."
        return 2 * (self.S / np.pi)**0.5
