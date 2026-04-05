import logging
import electroacoustical as ac


def find_feasible_coils(vals, wires, settings, logger=None):
    """
    Scan best matching speaker coil options.

    :param vals: Dictionary of input values.
    :param wires: Dictionary of available wire objects.
    :param settings: Settings object.
    :param logger: Logger object for debugging.
    :return: Dictionary mapping friendly names to Motor objects.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    try:  # try to read the N_layer_options string
        layer_options = [int(s.strip()) for s in vals["N_layer_options"].split(",") if s.strip()]
        if not layer_options:
            raise ValueError("At least one option needs to be provided for number of winding layers.")
    except Exception:
        raise ValueError("Invalid input in number of layer options")

    speaker_options = []

    for N_layers in layer_options:
        for wire_name, wire in wires.items():
            try:
                coil = ac.wind_coil(
                    wire,
                    N_layers,
                    vals["w_stacking_coef"],
                    vals["former_ID"] + 2 * vals["t_former"],  # carrier_OD
                    vals["h_winding_target"],
                    vals["reduce_per_layer"],
                )
            except ValueError as e:
                logger.debug(f"Could not wind coil for {wire_name}: {e}")
                continue

            # Check if Re is within +/- 15-20% of target
            if vals["target_Re"] / 1.15 < coil.Re < vals["target_Re"] * 1.2:
                motor = ac.Motor(
                    coil,
                    vals["B_average"],
                    h_top_plate=vals["h_top_plate"],
                    t_former=vals["t_former"],
                    airgap_clearance_inner=vals["airgap_clearance_inner"],
                    airgap_clearance_outer=vals["airgap_clearance_outer"],
                    h_former_under_coil=vals["h_former_under_coil"],
                )
                speaker = ac.SpeakerDriver(
                    vals["fs"],
                    vals["Sd"],
                    vals["Qms"],
                    motor=motor,
                    dead_mass=vals["dead_mass"],
                    Rlw=vals["Rlw"],
                )
                speaker_options.append(speaker)

    # Sort the viable coil options by Lm (Efficiency/Motor strength)
    speaker_options.sort(key=lambda x: x.Lm(settings), reverse=True)

    name_to_motor = {}
    for speaker in speaker_options:
        lm = speaker.Lm(settings)
        name = f"{speaker.motor.coil.name} -> Re={speaker.Re:.2f}, Lm={lm:.2f}, Qts={speaker.Qts:.2f}"
        name_to_motor[name] = speaker.motor

    return name_to_motor
