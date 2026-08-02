import logging

import numpy as np

from core.calculations import calculate_air_mass
from core.components import Wire, Coil, Motor, Enclosure, ParentBody, PassiveRadiator, BassReflexPort
from core.speaker_driver import SpeakerDriver
from core.speaker_system import SpeakerSystem
from config.physics import air

logger = logging.getLogger(__name__)


def _driver_sealed_fb(speaker: SpeakerDriver, enclosure: Enclosure) -> float:
    "Driver's housed (sealed-box) resonance f_b -- matches SpeakerSystem.fb."
    return 1 / 2 / np.pi * ((speaker.Kms + enclosure.K(speaker.Sd)) / speaker.Mms)**0.5


def construct_PassiveRadiator(vals,
                              speaker: SpeakerDriver,
                              enclosure: Enclosure,
                              ) -> PassiveRadiator:
    """Build a PassiveRadiator from the user-facing design parameters.

    User inputs (in `vals`, already converted to SI):
        h_pr                     : f_p / f_b
                                   (PR free-air resonance, i.e. the response
                                   notch, / driver sealed-box resonance)
        spring_damping_ratio_pr  : R_p / K_p of the passive radiator [s]
        area_ratio_pr            : S_p / S_d
        Mmdp                     : PR moving mass excluding the coupled air load [kg]

    The driver's housed resonance f_b depends only on the speaker and the
    enclosure, so it is evaluated here directly (same expression as
    SpeakerSystem.fb) without needing the full SpeakerSystem.
    """
    Sd = speaker.Sd
    S = vals["area_ratio_pr"] * Sd
    m = vals["Mmdp"]                          # PassiveRadiator.m (moving mass, no air load)
    m_s = m + calculate_air_mass(S)           # with coupled air mass

    # Driver's housed (sealed-box) resonance -- matches SpeakerSystem.fb
    fb = _driver_sealed_fb(speaker, enclosure)
    fp = vals["h_pr"] * fb                     # PR free-air resonance (the response notch)

    # Invert f_free = 1/2pi * sqrt(k / m_s) for the suspension stiffness
    k = m_s * (2 * np.pi * fp)**2

    # Mechanical damping resistance R_p = spring_damping_ratio_pr * K_p [N.s/m].
    Rp = vals["spring_damping_ratio_pr"] * k

    return PassiveRadiator(m=m, k=k, R=Rp, S=S)


def construct_BassReflexPort(vals, spec: str,
                             speaker: SpeakerDriver,
                             enclosure: Enclosure,
                             ) -> BassReflexPort:
    """Build a BassReflexPort from the user-facing design parameters.

    User inputs (in `vals`, already converted to SI):
        h_pr            : f_p / f_b (port tuning / driver sealed-box resonance)
                          -- shared with the passive radiator.
        port_diameter   : internal diameter of the vent [m].
        Qp              : port quality factor (losses) at the tuning frequency.
        exit_flare_type : end-correction coefficient k on the diameter; the total
                          end correction (both ends) is k * port_diameter.

    A vent is a passive radiator with zero suspension stiffness, so its resonance
    is set entirely by the enclosure air. The required acoustic mass is therefore
    *derived* from the target tuning (the inverse of the PR, where mass is an
    input), and the physical port length falls out of that mass.
    """
    if spec != "br_1":
        raise NotImplementedError(f"Bass-reflex spec type not implemented: {spec}")

    S = np.pi / 4 * vals["port_diameter"]**2

    fb = _driver_sealed_fb(speaker, enclosure)   # driver housed resonance
    fp = vals["h_pr"] * fb                        # port tuning (Helmholtz) frequency

    # Enclosure air acts as the port's only spring. Total acoustic mass needed to
    # tune the (stiffness-free) port to fp: m_s = k_box / (2*pi*fp)**2.
    k_box = enclosure.K(S)
    m_s = k_box / (2 * np.pi * fp)**2

    # Port loss resistance, inverting BassReflexPort.Qp() with k = 0.
    Rp = (k_box * m_s)**0.5 / vals["Qp"]

    # Split the acoustic mass into the physical tube air slug and the end correction.
    end_correction = vals["exit_flare_type"]["current_data"] * vals["port_diameter"]
    m_tube = m_s - air.RHO * S * end_correction

    # A non-positive tube length means no buildable port meets this target: the
    # enclosure and tuning call for less air mass than the port's end correction
    # alone. Fail the model update -- the same way an infeasible coil-winding target
    # does -- instead of returning a nonsensical negative-length vent.
    if m_tube <= 0:
        raise ValueError(
            "Bass-reflex vent is not realizable: the required port length is "
            "non-positive (the enclosure and tuning need less air mass than the "
            "port's end correction alone). Adjust the port diameter, the tuning "
            "ratio h, or the enclosure volume."
            )

    return BassReflexPort(m=m_tube, k=0.0, R=Rp, S=S, end_correction=end_correction)


def construct_SpeakerDriver(vals) -> SpeakerDriver:
    "Create the loudspeaker model based on the values provided in the widget."
    motor_spec_type = vals["motor_spec_type"]["current_data"]

    if motor_spec_type == "define_coil":
        try:
            motor_as_dict = vals["coil_options"]["current_data"]
            logger.debug(f"Motor object will be built from dict: {motor_as_dict}")
            wire_as_dict = motor_as_dict["coil"]["wire"]
            wire = Wire(**wire_as_dict)

            coil_as_dict = motor_as_dict["coil"]
            coil_as_dict["wire"] = wire
            coil = Coil(**coil_as_dict)

            motor_as_dict["coil"] = coil
            motor = Motor(**motor_as_dict)

        except (TypeError, AttributeError) as e:  # doesn't have motor attribute or is None
            print(e)
            raise RuntimeError("Invalid motor object in coil options combobox")
        speaker_driver = SpeakerDriver(fs=vals["fs"],
                                          Sd=vals["Sd"],
                                          Qms=vals["Qms"],

                                          motor=motor,
                                          dead_mass=vals["dead_mass"],

                                          Le=vals["Le"],
                                          Rlw=vals["Rlw"],
                                          Xpeak=vals["Xpeak"],
                                          )

    elif motor_spec_type == "define_Bl_Re_Mmd":
        speaker_driver = SpeakerDriver(fs=vals["fs"],
                                          Sd=vals["Sd"],
                                          Qms=vals["Qms"],

                                          Bl=vals["Bl_p2"],
                                          Re=vals["Re_p2"],
                                          Mmd=vals["Mmd_p2"],

                                          Le=vals["Le"],
                                          Xpeak=vals["Xpeak"],
                                          )

    elif motor_spec_type == "define_Bl_Re_Mms":
        speaker_driver = SpeakerDriver(fs=vals["fs"],
                                          Sd=vals["Sd"],
                                          Qms=vals["Qms"],

                                          Bl=vals["Bl_p3"],
                                          Re=vals["Re_p3"],
                                          Mms=vals["Mms_p3"],

                                          Le=vals["Le"],
                                          Xpeak=vals["Xpeak"],
                                          )
    else:
        raise ValueError(f"Motor specification type is invalid: {vals['motor_spec_type']}")

    return speaker_driver


def build_or_update_SpeakerSystem(vals,
                                  speaker: SpeakerDriver,
                                  spk_sys: None | SpeakerSystem = None,
                                  ) -> SpeakerSystem:
    if vals["enclosure_type"] in (1, 2):  # closed box or passive radiator
        enclosure = Enclosure(vals["Vb"],
                                 vals["Qa"],
                                 vals["Ql"],
                                 )
    else:
        enclosure = None

    if vals["parent_body"] == 1:
        parent_body = ParentBody(vals["mpb"],
                                    vals["kpb"],
                                    vals["rpb"],
                                    )
    else:
        parent_body = None

    if vals["enclosure_type"] == 2:  # PR or bass-reflex vent
        # resonator_spec_type identifiers are "<family>_<variant>": "pr" for a
        # passive radiator, "br" for a bass-reflex vent. Dispatch on the family so
        # future input variants (e.g. "br_2") slot in without new top-level branches.
        spec = vals["resonator_spec_type"]["current_data"]
        family = spec.split("_")[0]
        if family == "pr":
            passive_radiator = construct_PassiveRadiator(vals, speaker, enclosure)
        elif family == "br":
            passive_radiator = construct_BassReflexPort(vals, spec, speaker, enclosure)
        else:
            raise ValueError(f"Unknown resonator spec type: {spec}")
    else:
        passive_radiator = None

    if spk_sys is None:
        return SpeakerSystem(speaker=speaker,
                                Rext=vals["Rext"],
                                enclosure=enclosure,
                                parent_body=parent_body,
                                passive_radiator=passive_radiator,
                                dir_pr_vent=vals["dir_pr_vent"]["current_data"],
                                )
    else:
        spk_sys.update_values(speaker=speaker,
                              Rext=vals["Rext"],
                              enclosure=enclosure,
                              parent_body=parent_body,
                              passive_radiator=passive_radiator,
                              dir_pr_vent=vals["dir_pr_vent"]["current_data"],
                              )

    return spk_sys
