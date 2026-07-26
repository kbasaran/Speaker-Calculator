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
from core.calculations import calculate_air_mass, calculate_lm, calculate_coil_to_bottom_plate_clearance
from core.components import Motor


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
        # Bl**2/Re is the electrical damping reflected into the mechanical domain: a
        # resistance [N.s/m], not a compliance. It adds to the mechanical loss Rms to
        # set the total (Qts) and electrical (Qes) quality factors.
        self.Res = self.Bl**2 / self.Re
        self.Qts = (self.Mms * self.Kms)**0.5 / (self.Rms + self.Res)
        self.Qes = (self.Mms * self.Kms)**0.5 / self.Res
        zeta_speaker = 1 / 2 / self.Qts
        # ---- Free-air *response-peak* frequency -- NOT the damped natural frequency.
        #
        # A driven mass-spring-damper (the driver, the boxed driver, the parent body)
        # has SEVERAL distinct characteristic frequencies that are easy to confuse.
        # With w0 = sqrt(K/M) the undamped natural frequency and zeta the damping ratio:
        #
        #   1) Undamped natural frequency:  w0            (here self.fs)
        #      The frequency where the mass reactance and the suspension stiffness
        #      reactance exactly cancel.
        #
        #   2) Damped natural frequency:    w0*sqrt(1 - zeta**2)
        #      The frequency of the FREE, decaying oscillation the cone rings at when
        #      plucked and released -- a transient / pole property. It is the SAME for
        #      displacement, velocity and acceleration, and exists for zeta < 1.
        #
        #   3) Response-peak frequency:     (steady-state, sinusoidally driven)
        #      The frequency at which the DRIVEN amplitude is largest. This one depends
        #      on WHICH quantity is observed, and so is generally different from (2):
        #        - displacement peak:  w0*sqrt(1 - 2*zeta**2)   (BELOW w0)
        #        - velocity peak:      w0                        (AT w0)
        #        - acceleration peak:  w0/sqrt(1 - 2*zeta**2)   (ABOVE w0)
        #      Why displacement peaks below w0: at w0 the mass and stiffness cancel, so
        #      the force sees only the damper and VELOCITY is maximal there. Since
        #      displacement = velocity / w, dividing by a smaller w just below w0 makes
        #      the displacement larger -- pushing its peak below w0.
        #
        # (2) and (3) are answers to two different experiments -- "pluck it and hear it
        # ring" vs "drive it and find the biggest steady response" -- so there is no
        # reason for them to coincide. They all collapse onto w0 as zeta -> 0.
        #
        # The value below is the DISPLACEMENT response peak (the "bump" on the
        # excursion/SPL curve). It is real only for zeta < 1/sqrt(2) (Qts > 0.707);
        # for heavier damping the magnitude response is maximally flat with no peak, so
        # the sqrt turns imaginary and the value is reported as nan.
        self.fs_response_peak = self.fs * (1 - 2 * zeta_speaker**2)**0.5
        if np.iscomplex(self.fs_response_peak):  # no response peak (Qts <= 1/sqrt(2))
            self.fs_response_peak = np.nan

    def Lm(self):
        return calculate_lm(self.Bl, self.Re, self.Mms, self.Sd)  # sensitivity per W@Re

    def Vas(self):
        return air.Kair / self.Kms * self.Sd**2

    def get_summary(self, V_spk: float = 0) -> str:
        "Summary in markup language."
        summary = ("## Speaker unit"
                   "<br></br>"
                   f"L<sub>m</sub> : {self.Lm() :.2f} dBSPL        "
                   f"R<sub>e</sub> : {self.Re:.2f} ohm"
                   "<br></br>"
                   f"Bl : {self.Bl:.4g} Tm        "
                   f"Bl²/R<sub>e</sub> : {self.Bl**2/self.Re:.3g} N²/W"
                   "<br></br>"
                   f"Q<sub>es</sub> : {self.Qes:.3g}        "
                   f"Q<sub>ts</sub> : {self.Qts:.3g}"
                   "<br></br>"
                   f"V<sub>as</sub> : {self.Vas() * 1e3:.4g} l"
                   
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
