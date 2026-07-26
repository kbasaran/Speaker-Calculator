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
import sympy as smp
from scipy import signal
from sympy import solve
from sympy.abc import t
from sympy.physics import mechanics as mech

from config.physics import air
from core.calculations import make_output_matrices, make_state_matrix_A, make_state_matrix_B
from core.components import Enclosure, ParentBody, PassiveRadiator
from core.speaker_driver import SpeakerDriver


@dtc.dataclass
class SpeakerSystem:
    speaker: SpeakerDriver
    Rext: float = 0   # series electrical resistance from voltage generator to the speaker terminals.
                    # may be at the source amplifier or in the cables going to speaker terminals
    enclosure: None | Enclosure = None
    parent_body: None | ParentBody = None
    passive_radiator: None | PassiveRadiator = None
    dir_pr: int = 1

    def __post_init__(self):
        self._build_symbolic_ss_model()
        self.update_values()

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

        # Net volume velocity pushed into the box air, relative to the enclosure
        # walls (which move with the parent body x2). The box absorption/leakage
        # loss is an acoustic resistance Rbox [Pa.s/m^3] acting on this volume
        # velocity, so the reaction force on each radiator scales with its own
        # area (Sd, Spr) and the driver and PR are coupled through the shared
        # lossy air. Rms and Rpr remain the elements' own mechanical losses.
        U_box = Sd * (x1_t - x2_t) + Spr * (xpr_t - x2_t)

        # define state space system
        eqns = [

                (
                 - Mms * x1_tt
                 - Rms * (x1_t - x2_t)
                 - Kms * (x1 - x2)

                 - Rbox * Sd * U_box

                 + p_housing * Sd
                 + i_coil * Bl
                 ),

                (
                 - Mpb * x2_tt
                 - Rpb * x2_t
                 - Kpb * x2

                 + Rms * (x1_t - x2_t)
                 + Kms * (x1 - x2)

                 + Rpr * (xpr_t - x2_t)
                 + Kpr * (xpr - x2)

                 + Rbox * (Sd + Spr) * U_box

                 - p_housing * Sd
                 - p_housing * Spr

                 - i_coil * Bl
                 ),

                (
                 - Mpr * xpr_tt
                 - Rpr * (xpr_t - x2_t)
                 - Kpr * (xpr - x2)

                 - Rbox * Spr * U_box

                 + p_housing * Spr
                 ),

                ]

        # p_housing and i_coil are not state variables, because they are linearly dependent
        # on the state variables. They are substituted into the equations of motion,
        # and made available as outputs of the system through the C and D matrices.
        # box pressure depends on the net volume displaced into the enclosure,
        # measured relative to the cabinet walls (parent body x2) -- consistent
        # with the box-loss term above. With no parent body x2 == 0.
        dependent_vars = {
            p_housing: - (Kair / Vba * (Spr * (xpr - x2) + Sd * (x1 - x2))),
            i_coil: (Vsource - Bl * (x1_t - x2_t)) / (Rext + Re),
            }

        eqns = [eqn.subs(dependent_vars) for eqn in eqns]

        state_vars = [x1, x1_t, x2, x2_t, xpr, xpr_t]  # state variables
        input_vars = [Vsource]  # input variables
        state_diffs = [var.diff() for var in state_vars]  # state differentials

        # output variables, as expressions of state variables and input variables
        # key: name to access the ss model with, val: expression
        output_exprs = {"x1": x1,
                        "x1_t": x1_t,
                        "x2": x2,
                        "x2_t": x2_t,
                        "xpr": xpr,
                        "xpr_t": xpr_t,
                        "p_housing": dependent_vars[p_housing],
                        "i_coil": dependent_vars[i_coil],
                        }

        # dictionary of all sympy symbols used in model
        self.symbols = {key: val for (key, val) in locals().items() if isinstance(val, smp.Symbol)}

        # solve for state differentials
        sols = solve(eqns, [var for var in state_diffs if var not in state_vars], as_dict=True)  # heavy task, slow
        if len(sols) == 0:
            raise RuntimeError("No solution found for the equation.")

        # ---- SS model with symbols
        A_sym = make_state_matrix_A(state_vars, state_diffs, sols)  # system matrix
        B_sym = make_state_matrix_B(state_vars, state_diffs, input_vars, sols)  # input matrix
        # output matrix and feedforward matrix, one row per output
        C_sym, D_sym = make_output_matrices(output_exprs.values(), state_vars, input_vars)

        self._symbolic_ss = {"A": A_sym,  # system matrix
                             "B": B_sym,  # input matrix
                             "C": C_sym,  # output matrix
                             "D": D_sym,  # feedforward matrix
                             "state_vars": state_vars,
                             "output_names": list(output_exprs.keys()),
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

            "Mpb": np.inf if self.parent_body is None else self.parent_body.m,
            "Kpb": 0 if self.parent_body is None else self.parent_body.k,
            "Rpb": 0 if self.parent_body is None else self.parent_body.c,

            "Mpr": np.inf if self.passive_radiator is None else self.passive_radiator.m_s(),  # with air coupled
            "Kpr": 0 if self.passive_radiator is None else self.passive_radiator.k,
            "Rpr": 0 if self.passive_radiator is None else self.passive_radiator.R(self.enclosure.Vba()),
            "Spr": 0 if self.passive_radiator is None else self.passive_radiator.S,
            "dir_pr": self.dir_pr,

            "Kair": 0 if self.enclosure is None else air.Kair,  # 0 is trickery a bit, to disable the housing formulas.
            "Vba": 0 if self.enclosure is None else self.enclosure.Vba(),  # in fact Vba is infinite when no enclosure. but infinite is not allowed.
            "Rbox": 0 if self.enclosure is None else self.enclosure.R(self.speaker.Sd, self.speaker.Mms,
                                                                      self.speaker.Kms),

            "Rext": self.Rext,

            }

        return parameter_names_to_values

    def get_symbols_to_values(self):
        # Dictionary with sympy symbols as keys and values as values
        parameter_names_to_values = self._get_parameter_names_to_values()
        return {symbol: parameter_names_to_values[name] for name, symbol in self.symbols.items()}

    def update_values(self, **kwargs):
        # ---- set the attributes of self with values in kwargs
        dataclass_field_names = [dataclass_field.name for dataclass_field in dtc.fields(self)]
        for key, val in kwargs.items():
            if key in dataclass_field_names:
                setattr(self, key, val)
            else:
                raise KeyError("Not familiar with key '{key}'")

        # ---- Update scalars
        self.R_sys = self.speaker.Re + self.Rext

        # ---- Substitute values into the model matrices
        symbols_to_values = self.get_symbols_to_values()
        A = np.array(self._symbolic_ss["A"].subs(symbols_to_values)).astype(float)
        B = np.array(self._symbolic_ss["B"].subs(symbols_to_values)).astype(float)
        C = np.array(self._symbolic_ss["C"].subs(symbols_to_values)).astype(float)
        D = np.array(self._symbolic_ss["D"].subs(symbols_to_values)).astype(float)

        # ---- Updates in relation to enclosure
        if isinstance(self.enclosure, Enclosure):
            # self.Kair = air.Kair
            # box loss is stored as an acoustic resistance; refer it back to the
            # driver's mechanical domain (x Sd**2) for the sealed-box damping ratio
            Rbox_mech = self.enclosure.R(self.speaker.Sd, self.speaker.Mms, self.speaker.Kms) * self.speaker.Sd ** 2
            zeta_boxed_speaker = (
                                         Rbox_mech
                                         + self.speaker.Rms + self.speaker.Bl ** 2 / self.speaker.Re) \
                                 / 2 / ((self.speaker.Kms + self.enclosure.K(self.speaker.Sd)) * self.speaker.Mms) ** 0.5

            fb_undamped = 1 / 2 / np.pi * ((self.speaker.Kms + self.enclosure.K(self.speaker.Sd)) / self.speaker.Mms) ** 0.5

            fb_damped = fb_undamped * (1 - 2 * zeta_boxed_speaker**2)**0.5
            if np.iscomplex(fb_damped):  # means overdamped
                fb_damped = np.nan

            self.fb = fb_undamped
            self.Qtc = np.inf if zeta_boxed_speaker == 0 else 1 / 2 / zeta_boxed_speaker

        else:
            # self.Kair = 0  # trickery to remove air pressure when no enclosure
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
            # no need to touch C and D, since these states remain zero
            A[2:4, :] = 0
            A[:, 2:4] = 0
            B[2:4] = 0


        # ---- Update passive radiator related attributes
        if not isinstance(self.passive_radiator, PassiveRadiator):
            # make system coefficients related to xpr and xpr_t zero
            # no need to touch C and D, since these states remain zero
            A[4:6, :] = 0
            A[:, 4:6] = 0
            B[4:6] = 0


        # ---- Build ss models
        # one model per output -- scipy state space supports only a rank of 1 for output
        self.ss_models = dict()
        for i, output_name in enumerate(self._symbolic_ss["output_names"]):
            self.ss_models[output_name] = signal.StateSpace(A,
                                                            B,
                                                            C[[i], :],
                                                            D[[i], :],
                                                            )

    def get_summary(self, V_source: float = 0) -> str:
        "Summary in markup language."
        V_spk = V_source / self.R_sys * self.speaker.Re
        summary = self.speaker.get_summary(V_spk)

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
                f"K<sub>enc,s</sub>: {self.enclosure.K(self.speaker.Sd) / 1000:.4g} N/mm"
                )
            if isinstance(self.passive_radiator, PassiveRadiator):
                summary += f"      K<sub>enc,pr</sub>: {self.enclosure.K(self.passive_radiator.S) / 1000:.4g} N/mm"
                
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

    def _get_response(self, output_name: str, V_source, freqs: np.ndarray) -> np.ndarray:
        # Frequency response of one output of the system to a given source voltage
        # Voltage argument given in RMS, output in the unit of the output variable, RMS
        w = 2 * np.pi * np.array(freqs)
        return signal.freqresp(self.ss_models[output_name], w=w)[1] * V_source

    def get_displacements(self, V_source, freqs: np.ndarray) -> dict:
        # Voltage argument given in RMS
        # outputs in m
        disps = dict()

        x1 = self._get_response("x1", V_source, freqs)

        disps["Diaphragm, peak"] = x1 * 2**0.5
        disps["Diaphragm, RMS"] = x1

        if self.parent_body is not None:  # in fact, better return these even when no parnt_body, and filter in plotting
            x2 = self._get_response("x2", V_source, freqs)
            disps["Parent body, RMS"] = x2
            disps["Diaphragm, peak, relative to parent"] = (x1 - x2) * 2**0.5
            disps["Diaphragm, RMS, relative to parent"] = (x1 - x2)

        if self.passive_radiator is not None:  # remove later and return always
            xpr = self._get_response("xpr", V_source, freqs)
            disps["PR/vent, RMS"] = xpr
            disps["PR/vent, peak"] = xpr * 2**0.5
            if self.parent_body is not None:
                disps["PR/vent, peak, relative to parent"] = (xpr - x2) * 2**0.5
                disps["PR/vent, RMS, relative to parent"] = (xpr - x2)
                
        return disps

    def get_velocities(self, V_source, freqs: np.ndarray) -> dict:
        # Voltage argument given in RMS
        # outputs in m/s
        velocs = dict()

        x1_t = self._get_response("x1_t", V_source, freqs)
        velocs["Diaphragm, RMS"] = x1_t

        if self.parent_body is not None:  # remove later and return always
            x2_t = self._get_response("x2_t", V_source, freqs)
            velocs["Parent body, RMS"] = x2_t
            velocs["Diaphragm, RMS, relative to parent"] = x1_t - x2_t

        if self.passive_radiator is not None:  # remove later and return always
            xpr_t = self._get_response("xpr_t", V_source, freqs)
            velocs["PR/vent, RMS"] = xpr_t
            if self.parent_body is not None:
                velocs["PR/vent, RMS, relative to parent"] = xpr_t - x2_t
        
        return velocs

    def get_accelerations(self, V_source, freqs: np.ndarray) -> dict:
        # Voltage argument given in RMS
        # outputs in m/s
        velocs = self.get_velocities(V_source, freqs)
        w = 2 * np.pi * np.array(freqs)

        return {key: arr.flatten() * 1j * w for key, arr in velocs.items()}
    
    def get_currents(self, V_source, freqs: np.ndarray) -> dict:
        # Voltage argument given in RMS
        # outputs in A
        return {"Coil, RMS": self._get_response("i_coil", V_source, freqs)}

    def get_pressures(self, V_source, freqs: np.ndarray) -> dict:
        # Voltage argument given in RMS
        # outputs in Pa, relative to ambient pressure
        pressures = dict()

        if self.enclosure is not None:  # without a housing there is no pressure build-up
            pressures["Housing, RMS"] = self._get_response("p_housing", V_source, freqs)

        return pressures

    def get_Z(self, freqs):
        imps = dict()
        i_coil = self.get_currents(1, freqs)["Coil, RMS"]

        imps["Impedance speaker"] = 1 / i_coil - self.Rext  # speaker only
        if self.Rext > 0:  # remove later and return always
            imps["Impedance incl. source, cables"] = imps["Impedance speaker"] + self.Rext

        return imps

    def get_forces(self, V_source, freqs: np.ndarray) -> dict:
        # Voltage argument given in RMS
        # force coil means force generated by coil
        # force speaker means force generated by speaker (inertial forces)
        accs = self.get_accelerations(V_source, freqs)
        i_coil = self.get_currents(V_source, freqs)["Coil, RMS"]

        force_coil = self.speaker.Bl * i_coil
        force_speaker = accs["Diaphragm, RMS"] * self.speaker.Mms  # inertial force

        forces = dict()
        forces["Lorentz force, RMS"] = np.abs(force_coil)
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

    def get_phases(self, freqs: np.ndarray) -> dict:
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
