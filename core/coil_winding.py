import logging
from typing import Dict, Any, Optional
from .models import Wire, Coil, Motor
import electroacoustical as ac

def wind_coil(wire: Wire,
              n_layers: int,
              w_stacking_coef: float,
              carrier_od: float,
              h_winding_target: float,
              reduce_per_layer: float,
              ) -> Coil:
    """
    Create a coil object based on the given winding parameters.

    :param wire: Wire object containing physical properties of the wire.
    :param n_layers: Number of winding layers.
    :param w_stacking_coef: Width stacking coefficient (overlap between layers).
    :param carrier_od: Outer diameter of the coil carrier (former).
    :param h_winding_target: Target height of the winding.
    :param reduce_per_layer: Number of windings to reduce on each subsequent layer.
    :return: A new Coil instance.
    :raises ValueError: If any layer results in less than 1 winding.
    """

    def n_winding_for_single_layer(i_layer: int) -> int:
        """Calculate the number of windings that fit on one layer of coil."""
        # 1 winding less on each stacked layer if the stacking coefficient is less than or equal to 0.9
        n_winding = h_winding_target / wire.h_avg - i_layer * reduce_per_layer
        return int(round(n_winding))

    n_windings = [n_winding_for_single_layer(i_layer) for i_layer in range(n_layers)]
    if any([n_winding < 1 for n_winding in n_windings]):
        raise ValueError("Some layers were impossible to wind with the given parameters.")

    return Coil(carrier_od, wire, n_windings, w_stacking_coef)


def find_feasible_coils(vals: Dict[str, Any], wires: Dict[str, Wire], logger: Optional[logging.Logger] = None) -> Dict[str, Motor]:
    """
    Scan for the best matching speaker coil options based on input parameters.

    :param vals: Dictionary of input values (target Re, dimensions, etc.).
    :param wires: Dictionary of available wire objects.
    :param logger: Logger object for debugging (optional).
    :return: Dictionary mapping friendly names to Motor objects.
    :raises ValueError: If the number of layer options is invalid or empty.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    try:  # try to read the N_layer_options string
        layer_options = [int(s.strip()) for s in vals["N_layer_options"].split(",") if s.strip()]
    except Exception as e:
        raise ValueError("Invalid input in number of layer options") from e
    else:
        if not layer_options:
            raise ValueError("At least one option needs to be provided for number of winding layers.")

    speaker_options = []

    for n_layers in layer_options:
        for wire_name, wire in wires.items():
            try:
                coil = wind_coil(
                    wire=wire,
                    n_layers=n_layers,
                    w_stacking_coef=vals["w_stacking_coef"],
                    carrier_od=vals["former_ID"] + 2 * vals["t_former"],  # carrier_OD
                    h_winding_target=vals["h_winding_target"],
                    reduce_per_layer=vals["reduce_per_layer"],
                )
            except ValueError as e:
                logger.debug(f"Could not wind coil for {wire_name}: {e}")
                continue

            # Check if Re is within +/- 15-20% of target
            if vals["target_Re"] / 1.15 < coil.Re < vals["target_Re"] * 1.2:
                motor = Motor(
                    coil=coil,
                    Bavg=vals["B_average"],
                    h_top_plate=vals["h_top_plate"],
                    t_former=vals["t_former"],
                    airgap_clearance_inner=vals["airgap_clearance_inner"],
                    airgap_clearance_outer=vals["airgap_clearance_outer"],
                    h_former_under_coil=vals["h_former_under_coil"],
                )
                speaker = ac.SpeakerDriver(
                    fs=vals["fs"],
                    Sd=vals["Sd"],
                    Qms=vals["Qms"],
                    motor=motor,
                    dead_mass=vals["dead_mass"],
                    Rlw=vals["Rlw"],
                )
                speaker_options.append(speaker)

    # Sort the viable coil options by Lm (Efficiency/Motor strength)
    speaker_options.sort(key=lambda x: x.Lm(), reverse=True)

    name_to_motor = {}
    for speaker in speaker_options:
        lm = speaker.Lm()
        name = f"{speaker.motor.coil.name} -> Re={speaker.Re:.2f}, Lm={lm:.2f}, Qts={speaker.Qts:.2f}"
        name_to_motor[name] = speaker.motor

    return name_to_motor
