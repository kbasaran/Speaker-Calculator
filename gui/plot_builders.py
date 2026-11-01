"""Pure plot-data builders for the main window graph.

Each builder takes the current speaker system plus the excitation context and
returns a :class:`PlotSpec` describing the curves to draw and how to label the
axes. The builders contain no Qt dependency, so they can be unit-tested against
known speaker systems independently of the GUI.

The main window looks up a builder in :data:`PLOT_BUILDERS` by the id of the
selected graph-data choice and applies the returned spec to its graph widget.
"""

from dataclasses import dataclass, field

import numpy as np

from core.calculations import calculate_spl
from core.components import BassReflexPort
from gui.labels import voltage_line as _voltage_line


@dataclass
class PlotSpec:
    """The result of building one graph: curves plus axis presentation."""
    curves: dict[str, np.ndarray] = field(default_factory=dict)
    title: str = ""
    ylabel: str = ""
    xlabel: str = "frequency"
    ylimits_policy: str | None = None
    # Optional per-curve matplotlib line kwargs (keyed by curve name). Curves not
    # listed here are drawn with the default (solid) style.
    line_kwargs: dict[str, dict] = field(default_factory=dict)


def _dotted_for_peak(curve_names) -> dict[str, dict]:
    """Line kwargs drawing 'peak' curves dotted, leaving RMS (and any others) solid."""
    return {name: {"linestyle": ":"} for name in curve_names if "peak" in name.lower()}


def build_spl(spk_sys, freqs, V_source, V_spk, W_spk) -> PlotSpec:
    curves = {}

    if spk_sys.speaker.Sd == 0:  # shaker or other with no diaphragm
        accs = spk_sys.get_accelerations(V_source, freqs)
        curves.update({key.replace("Diaphragm", "Moving mass"): 20*np.log10(np.abs(acc)/1e-6)
                       for key, acc in accs.items() if "relative" not in key})
        title = f"Acceleration\n{_voltage_line(spk_sys, V_source, V_spk, W_spk)}"
        ylabel = r"dB ref. $\mathregular{10^{-6}}$m/s²"

    else:  # speaker
        velocs = spk_sys.get_velocities(V_source, freqs)
        w = 2 * np.pi * freqs
        Xpeak_limited_velocities = spk_sys.speaker.Xpeak / 2**0.5 * (1j * w)

        # Radiated SPL is proportional to volume velocity (Sd * velocity),
        # so calculate_spl is fed the volume velocity directly with sd=1.
        # The combined Sd covers all the drivers, so these are total SPL curves.
        U_drivers = spk_sys.combined.Sd * velocs["Diaphragm, RMS"]  # volume velocity
        _, SPL = calculate_spl((freqs, U_drivers), 1.0)

        _, SPL_Xpeak_limited = calculate_spl((freqs, Xpeak_limited_velocities), spk_sys.combined.Sd)

        curves.update({"SPL piston mode, Xpeak limited": SPL_Xpeak_limited,
                       })

        # Combined driver + passive radiator response (shows the PR notch).
        # Total radiated volume velocity sums the diaphragm and PR contributions.
        # velocs["PR/vent"] is already the PR's physical outward velocity, so the
        # dir_pr_vent sign is baked in and its volume velocity adds directly.
        if spk_sys.passive_radiator is not None:
            U_total = U_drivers + spk_sys.passive_radiator.S * velocs["PR/vent, RMS"]  # volume velocity
            _, SPL_incl_pr = calculate_spl((freqs, U_total), 1.0)
            curves.update({"SPL piston mode incl. radiator": SPL_incl_pr})

        curves.update({"SPL piston mode": SPL,
                       })

        title = f"SPL @ 1m, Half-space\n{_voltage_line(spk_sys, V_source, V_spk, W_spk)}"
        ylabel = "dBSPL"

    return PlotSpec(curves, title, ylabel, ylimits_policy="SPL")


def build_impedance(spk_sys, freqs, V_source, V_spk, W_spk) -> PlotSpec:
    # Plot the impedance magnitude |Z| (what impedance analyzers measure and what
    # sets the amplifier load I = V/|Z|), not the real part. When the voice-coil
    # inductance Le is non-zero, |Z| rises at high frequency; with Le == 0 it
    # settles to the coil resistance above resonance.
    curves = {key: np.abs(val) for key, val in spk_sys.get_Z(freqs).items()}
    return PlotSpec(curves,
                    title="Electrical impedance magnitude |Z|",
                    ylabel="ohm",
                    ylimits_policy="impedance",
                    )


def build_relative_displacements(spk_sys, freqs, V_source, V_spk, W_spk) -> PlotSpec:
    curves = {key: np.abs(val) * 1e3
              for key, val in spk_sys.get_displacements(V_source, freqs).items()
              if "relative" in key}

    if not curves:
        title = "Displacements - relative to parent body\n-No parent body in this model-"
    else:
        title = f"Displacements - relative to parent body\n{_voltage_line(spk_sys, V_source, V_spk, W_spk)}"

    return PlotSpec(curves,
                    title=title,
                    ylabel="mm",
                    line_kwargs=_dotted_for_peak(curves),
                    )


def build_displacements(spk_sys, freqs, V_source, V_spk, W_spk) -> PlotSpec:
    curves = {key: np.abs(val) * 1e3
              for key, val in spk_sys.get_displacements(V_source, freqs).items()
              if "relative" not in key}
    if isinstance(spk_sys.passive_radiator, BassReflexPort):
        curves = {key: val for key, val in curves.items() if "vent" not in key.lower()}
    return PlotSpec(curves,
                    title=f"Absolute displacements\n{_voltage_line(spk_sys, V_source, V_spk, W_spk)}",
                    ylabel="mm",
                    line_kwargs=_dotted_for_peak(curves),
                    )


def build_forces(spk_sys, freqs, V_source, V_spk, W_spk) -> PlotSpec:
    curves = {key: np.abs(val) for key, val in spk_sys.get_forces(V_source, freqs).items()}
    return PlotSpec(curves,
                    title=f"Forces\n{_voltage_line(spk_sys, V_source, V_spk, W_spk)}",
                    ylabel="N",
                    )


def build_velocities(spk_sys, freqs, V_source, V_spk, W_spk) -> PlotSpec:
    curves = {key: np.abs(val) for key, val in spk_sys.get_velocities(V_source, freqs).items()}
    return PlotSpec(curves,
                    title=f"Velocities\n{_voltage_line(spk_sys, V_source, V_spk, W_spk)}",
                    ylabel="m/s",
                    )


def build_box_pressure(spk_sys, freqs, V_source, V_spk, W_spk) -> PlotSpec:
    # Sound pressure of the air inside the enclosure, relative to ambient.
    # Without an enclosure there is no pressure build-up, so nothing is drawn.
    curves = {key: np.abs(val) for key, val in spk_sys.get_pressures(V_source, freqs).items()}
    if not curves:
        title = "Sound pressure inside the enclosure\n-No enclosure in this model-"
    else:
        title = f"Sound pressure inside the enclosure\n{_voltage_line(spk_sys, V_source, V_spk, W_spk)}"
    return PlotSpec(curves,
                    title=title,
                    ylabel="Pa",
                    line_kwargs=_dotted_for_peak(curves),
                    )


def build_phase(spk_sys, freqs, *args) -> PlotSpec:
    curves = dict(spk_sys.get_phases(freqs).items())
    return PlotSpec(curves,
                    title=f"Phase for displacements",
                    ylabel="degrees",
                    ylimits_policy="phase",
                    )


# Maps graph_data_choice button id -> builder. Keep in sync with the choices
# defined in MainWindow._create_widgets (graph_data_choice).
PLOT_BUILDERS = {
    0: build_spl,
    1: build_impedance,
    2: build_relative_displacements,
    3: build_displacements,
    4: build_forces,
    5: build_velocities,
    6: build_phase,
    7: build_box_pressure,
}


def graph_is_available(graph_id: int, spk_sys) -> bool:
    """Whether a speaker system can supply the graph a choice id names.

    The choice buttons and the report both ask this, so the conditions live
    beside the builders they belong to instead of once in each caller. They are
    read off the built model rather than off the input form, so they always
    agree with what the builder would find in it.
    """
    if graph_id == 2:  # displacements relative to the parent body
        return spk_sys.parent_body is not None
    if graph_id == 7:  # pressure inside the enclosure
        return spk_sys.enclosure is not None
    return True


def apply_spec(graph, spec: PlotSpec, freqs, x_min: float, x_max: float) -> None:
    """Draw a built spec onto a graph widget.

    Shared by the main window and the report so that a graph in a report is the
    same picture as the one on screen. 'graph' is a MatplotlibWidget, used only
    through its public methods -- this module stays free of Qt.

    The x limits are passed in rather than read from the settings, so the axis
    always agrees with the 'freqs' the curves were actually calculated over.
    """
    graph.clear_graph()

    graph.set_y_limits_policy(spec.ylimits_policy)
    graph.set_x_limits_policy("fixed", min=x_min, max=x_max)
    graph.set_title(spec.title)
    graph.set_xlabel(spec.xlabel)
    graph.set_ylabel(spec.ylabel)

    for i, (name, y) in enumerate(spec.curves.items()):
        graph.add_line2d(i, name, (freqs, y), update_figure=False,
                         line2d_kwargs=spec.line_kwargs.get(name, {}))

    graph.update_figure()
