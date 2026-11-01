"""Short human-readable labels derived from a speaker system.

These helpers turn model state into presentation strings: the excitation line
that heads the graph titles and the one-line window title that identifies a
design when several windows are open side by side. Like the plot builders they
carry no Qt dependency, so they can be unit-tested against known speaker
systems.
"""

import numpy as np

from config.app_config import APP_DEFINITIONS
from core.calculations import calculate_spl

# The window title reports the response at a low frequency and at the top of the
# calculated range. 30 Hz is low enough to sit in the region an enclosure design
# is judged on, while still being inside the default sweep.
TITLE_SPL_LOW_FREQ = 30.0


def excitation_at_speaker(spk_sys, V_source) -> tuple[float, float]:
    """Voltage across the speaker terminals and the power into Re, from V_source.

    A series resistance (source, cables) divides the source voltage down, so the
    speaker only sees V_source * Re / R_sys. With several drivers both refer to
    the combined driver: the voltage at the terminals of the whole set and the
    total power into all the voice coils.
    """
    Re = spk_sys.combined.Re
    V_spk = V_source / spk_sys.R_sys * Re
    return V_spk, V_spk**2 / Re


def voltage_line(spk_sys, V_source, V_spk, W_spk) -> str:
    """Excitation voltage description, used in graph and window titles.

    When the speaker Re equals the system resistance there is no series
    network, so a single voltage is shown; otherwise both are reported.
    """
    if spk_sys.combined.Re == spk_sys.R_sys:
        return f"{V_spk:.4g}V {W_spk:.3g}Watt @ Re"
    return f"System: {V_source:.4g}V, Speaker: {V_spk:.4g}V {W_spk:.3g}Watt @ Re"


def _total_spl(spk_sys, freqs, V_source) -> np.ndarray:
    """Radiated SPL including the PR/vent contribution, i.e. the summed output.

    Mirrors the "incl. radiator" curve of build_spl: SPL is proportional to the
    total radiated volume velocity, so the diaphragm and PR/vent volume
    velocities are summed and fed to calculate_spl with sd=1. The PR/vent
    velocity already carries the dir_pr_vent sign, so it adds directly.
    """
    velocs = spk_sys.get_velocities(V_source, freqs)
    U = spk_sys.combined.Sd * velocs["Diaphragm, RMS"]
    if spk_sys.passive_radiator is not None:
        U = U + spk_sys.passive_radiator.S * velocs["PR/vent, RMS"]
    _, SPL = calculate_spl((freqs, U), 1.0)
    return SPL


def design_identity(spk_sys, V_source, f_max: float) -> str:
    """The handful of numbers that distinguish one design from another at a glance.

    Shared by the window title and the report header, so a report carries the
    same identity as the window it was made from.
    """
    spk = spk_sys.speaker
    V_spk, W_spk = excitation_at_speaker(spk_sys, V_source)

    # Driver parameters are per driver; a count in front marks a multi-driver
    # design, whose SPL figure below is the total of all the drivers.
    parts = [f"{spk.Sd * 1e4:.3g} cm²",
             f"{spk.Bl**2 / spk.Re:.2g} N²/W",
             f"{spk.Mms * 1e3:.3g} g",
             ]
    if spk_sys.n_speaker > 1:
        parts.insert(0, f"{spk_sys.n_speaker}× {spk_sys.coupling}")

    # A driver with no diaphragm (shaker) radiates no sound; build_spl plots its
    # acceleration instead, so there is no SPL to report here.
    if spk.Sd > 0:
        freqs = np.array([TITLE_SPL_LOW_FREQ, f_max])
        spl_low, spl_high = _total_spl(spk_sys, freqs, V_source)
        parts.append(f"{spl_low:.1f}/{spl_high:.1f} dB @ {W_spk:.2g} W, {TITLE_SPL_LOW_FREQ:.0f}/{f_max:.0f} Hz")

    return " - ".join(parts)


def window_title(spk_sys, V_source, user_title: str, f_max: float) -> str:
    """One-line design identity for the window title bar.

    Puts the user's own title first, followed by the design's identifying
    numbers, so windows holding different designs can be told apart in the task
    bar and window switcher.
    """
    name = user_title.strip() or "Untitled"
    app_version = f"{APP_DEFINITIONS["app_name"]} {APP_DEFINITIONS["version"]}"

    return name + "  -  " + design_identity(spk_sys, V_source, f_max) + "  /  " + app_version
