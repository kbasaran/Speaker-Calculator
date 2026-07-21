import logging

from core.components import Wire, Coil, Motor, Enclosure, ParentBody
from core.speaker_driver import SpeakerDriver
from core.speaker_system import SpeakerSystem

logger = logging.getLogger(__name__)


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
    if vals["enclosure_type"] == 1:
        enclosure = Enclosure(vals["Vb"],
                                 vals["Qa"],
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

    if False:  # passive radiator not implemented yet
        pass
    else:
        passive_radiator = None

    if spk_sys is None:
        return SpeakerSystem(speaker=speaker,
                                Rext=vals["Rext"],
                                enclosure=enclosure,
                                parent_body=parent_body,
                                passive_radiator=passive_radiator,
                                )
    else:
        spk_sys.update_values(speaker=speaker,
                              Rext=vals["Rext"],
                              enclosure=enclosure,
                              parent_body=parent_body,
                              passive_radiator=passive_radiator,
                              )

    return spk_sys
