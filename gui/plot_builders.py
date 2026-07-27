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


@dataclass
class PlotSpec:
    """The result of building one graph: curves plus axis presentation."""
    curves: dict[str, np.ndarray] = field(default_factory=dict)
    title: str = ""
    ylabel: str = ""
    ylimits_policy: str | None = None


def _voltage_line(spk_sys, V_source, V_spk) -> str:
    """Second title line describing the excitation voltage.

    When the speaker Re equals the system resistance there is no series
    network, so a single voltage is shown; otherwise both are reported.
    """
    if spk_sys.speaker.Re == spk_sys.R_sys:
        return f"{V_spk:.4g}V"
    return f"System: {V_source:.4g}V, Speaker: {V_spk:.4g}V"


def build_spl(spk_sys, freqs, V_source, V_spk, W_spk) -> PlotSpec:
    curves = {}

    if spk_sys.speaker.Sd == 0:  # shaker or other with no diaphragm
        accs = spk_sys.get_accelerations(V_source, freqs)
        curves.update({key.replace("Diaphragm", "Moving mass"): 20*np.log10(np.abs(acc)/1e-6)
                       for key, acc in accs.items() if "relative" not in key})
        title = f"Acceleration, {V_source:.4g}V {W_spk:.3g}Watt@Re"
        ylabel = r"dB ref. $\mathregular{10^{-6}}$m/s²"

    else:  # speaker
        velocs = spk_sys.get_velocities(V_source, freqs)
        w = 2 * np.pi * freqs
        Xpeak_limited_velocities = spk_sys.speaker.Xpeak / 2**0.5 * (1j * w)

        # Radiated SPL is proportional to volume velocity (Sd * velocity),
        # so calculate_spl is fed the volume velocity directly with sd=1.
        U_driver = spk_sys.speaker.Sd * velocs["Diaphragm, RMS"]  # volume velocity
        _, SPL = calculate_spl((freqs, U_driver), 1.0)

        _, SPL_Xpeak_limited = calculate_spl((freqs, Xpeak_limited_velocities), spk_sys.speaker.Sd)

        curves.update({"SPL piston mode, Xpeak limited": SPL_Xpeak_limited,
                       })

        # Combined driver + passive radiator response (shows the PR notch).
        # Total radiated volume velocity sums the diaphragm and PR contributions.
        # velocs["PR/vent"] is already the PR's physical outward velocity, so the
        # dir_pr_vent sign is baked in and its volume velocity adds directly.
        if spk_sys.passive_radiator is not None:
            U_total = U_driver + spk_sys.passive_radiator.S * velocs["PR/vent, RMS"]  # volume velocity
            _, SPL_incl_pr = calculate_spl((freqs, U_total), 1.0)
            curves.update({"SPL piston mode incl. radiator": SPL_incl_pr})

        curves.update({"SPL piston mode": SPL,
                       })

        if spk_sys.speaker.Re == spk_sys.R_sys:
            title = f"SPL@1m, Half-space\n{V_spk:.4g}V {W_spk:.3g}Watt@Re"
        else:
            title = f"SPL@1m, Half-space\nSystem: {V_source:.4g}V, Speaker: {V_spk:.4g}V {W_spk:.3g}Watt@Re"
        ylabel = "dBSPL"

    return PlotSpec(curves, title, ylabel, ylimits_policy="SPL")


def build_impedance(spk_sys, freqs, V_source, V_spk, W_spk) -> PlotSpec:
    # Plot the impedance magnitude |Z| (what impedance analyzers measure and what
    # sets the amplifier load I = V/|Z|), not the real part. No voice-coil
    # inductance is modelled, so |Z| stays flat at high frequency.
    curves = {key: np.abs(val) for key, val in spk_sys.get_Z(freqs).items()}
    return PlotSpec(curves,
                    title="Electrical impedance magnitude |Z| - no inductance",
                    ylabel="ohm",
                    ylimits_policy="impedance",
                    )


def build_relative_displacements(spk_sys, freqs, V_source, V_spk, W_spk) -> PlotSpec:
    curves = {key: np.abs(val) * 1e3
              for key, val in spk_sys.get_displacements(V_source, freqs).items()
              if "relative" in key}
    return PlotSpec(curves,
                    title=f"Relative Displacements\n{_voltage_line(spk_sys, V_source, V_spk)}",
                    ylabel="mm",
                    )


def build_displacements(spk_sys, freqs, V_source, V_spk, W_spk) -> PlotSpec:
    curves = {key: np.abs(val) * 1e3
              for key, val in spk_sys.get_displacements(V_source, freqs).items()
              if "relative" not in key}
    return PlotSpec(curves,
                    title=f"Displacements\n{_voltage_line(spk_sys, V_source, V_spk)}",
                    ylabel="mm",
                    )


def build_forces(spk_sys, freqs, V_source, V_spk, W_spk) -> PlotSpec:
    curves = {key: np.abs(val) for key, val in spk_sys.get_forces(V_source, freqs).items()}
    return PlotSpec(curves,
                    title=f"Forces\n{_voltage_line(spk_sys, V_source, V_spk)}",
                    ylabel="N",
                    )


def build_velocities(spk_sys, freqs, V_source, V_spk, W_spk) -> PlotSpec:
    curves = {key: np.abs(val) for key, val in spk_sys.get_velocities(V_source, freqs).items()}
    return PlotSpec(curves,
                    title=f"Velocities\n{_voltage_line(spk_sys, V_source, V_spk)}",
                    ylabel="m/s",
                    )


def build_phase(spk_sys, freqs, V_source, V_spk, W_spk) -> PlotSpec:
    curves = dict(spk_sys.get_phases(freqs).items())
    return PlotSpec(curves,
                    title=f"Phase for displacements\n{_voltage_line(spk_sys, V_source, V_spk)}",
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
}
