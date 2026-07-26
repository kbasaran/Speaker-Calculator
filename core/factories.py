import logging

import numpy as np

from config.physics import air
from core.calculations import calculate_air_mass
from core.components import Wire, Coil, Motor, Enclosure, ParentBody, PassiveRadiator
from core.speaker_driver import SpeakerDriver
from core.speaker_system import SpeakerSystem

logger = logging.getLogger(__name__)


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

    Vba = enclosure.Vba()
    k_box_pr = S**2 * air.Kair / Vba          # PR air-spring stiffness in the box

    # Driver's housed (sealed-box) resonance -- matches SpeakerSystem.fb
    fb = 1 / 2 / np.pi * ((speaker.Kms + enclosure.K(Sd)) / speaker.Mms)**0.5
    fp = vals["h_pr"] * fb                     # PR free-air resonance (the response notch)

    # Invert f_free = 1/2pi * sqrt(k / m_s) for the suspension stiffness
    k = m_s * (2 * np.pi * fp)**2

    # R_p = spring_damping_ratio_pr * K_p, then invert
    # R(Vba) = sqrt((k_box_pr + k) * m_s) / Q  for the quality factor
    Rp = vals["spring_damping_ratio_pr"] * k
    Qp = ((k_box_pr + k) * m_s)**0.5 / Rp

    return PassiveRadiator(m=m, k=k, Qp=Qp, S=S)


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

                                          Xpeak=vals["Xpeak"],
                                          )

    elif motor_spec_type == "define_Bl_Re_Mms":
        speaker_driver = SpeakerDriver(fs=vals["fs"],
                                          Sd=vals["Sd"],
                                          Qms=vals["Qms"],

                                          Bl=vals["Bl_p3"],
                                          Re=vals["Re_p3"],
                                          Mms=vals["Mms_p3"],

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

    if vals["enclosure_type"] == 2:  # passive radiator
        passive_radiator = construct_PassiveRadiator(vals, speaker, enclosure)
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
