"""Generation of the standalone PDF report.

The report is written as HTML against a template and then laid out onto A4
sheets by the Qt WebEngine, the same engine that draws a page in a browser.
Going through HTML keeps the whole design of the document
-- its two columns, its tables, where its pages break -- in one stylesheet that
can be opened and tried out in a browser, rather than in drawing calls here.

The result is one self-contained file: the results summary, the input-form
values that the summary does not already carry, and the graphs as embedded
PNGs. Nothing is linked from outside, so the document can be mailed or archived
on its own.

The graphs are drawn by a second, never-shown MatplotlibWidget rather than by
the one on screen. That keeps every styling decision (log-frequency ticks,
grids, the per-plot y-limit policies, legend ordering) in one place instead of
being re-implemented here, and it leaves the user's current graph selection
untouched while the report is built.
"""

import base64
import html
import io
import json
import logging
import math
import re
import tempfile
import time
from pathlib import Path
from string import Template

from PySide6 import QtCore as qtc
from PySide6 import QtGui as qtg
from PySide6 import QtWidgets as qtw
# Imported here, at module scope, so that it is in place before the application
# builds its QApplication -- the order the web engine asks for. It costs about
# 30 MB of memory and no measurable time.
from PySide6.QtWebEngineCore import QWebEnginePage

from generictools import signal_tools
from generictools.graphing_widget import MatplotlibWidget

from config.app_config import APP_DEFINITIONS, singleton_settings
from gui import labels
from gui import session_io
from gui.plot_builders import PLOT_BUILDERS, apply_spec, graph_is_available
from utils.paths import get_main_dir

logger = logging.getLogger(__name__)
app_settings = singleton_settings()

FILE_FILTER = "PDF documents (*.pdf)"
FILE_SUFFIX = ".pdf"

# Relative to the installation folder; bundled with the rest of data/ by the
# packaging script.
TEMPLATE_FILE = "data/report_template.html"

# The sheet the report is printed on. The margins live here rather than in the
# template's @page rule because the print engine takes its page geometry from the
# layout it is handed and ignores an @page margin -- so this is the one authority
# for where the sheet's edges are. Keep --page-width in the template in step with
# them: it sizes the content column to what is left between the side margins.
PAGE_SIZE_ID = qtg.QPageSize.PageSizeId.A4
PAGE_MARGINS_MM = (12, 12, 12, 14)  # left, top, right, bottom

# How long to wait for the page to be laid out and printed before giving up.
# Generous: the document carries every graph as an embedded image, so it runs to
# several megabytes.
RENDER_TIMEOUT_MS = 120_000

# Source voltage the reference set of graphs is drawn at, alongside the graphs
# for whatever excitation the user currently has set up.
REFERENCE_VOLTAGE = 2.83

# The size one graph is printed at, in millimetres. The width is the full
# content column (--page-width in the template) and the height is a third of
# what is left of a sheet once the "Graphs" heading has taken its share, so
# three graphs go on a page. Keep it in step with figure.graph in the template.
GRAPH_SIZE_MM = (186, 80)

# How much larger than the printed size the figures are laid out. Everything
# matplotlib draws around the curves -- the title, the tick labels, the lines --
# is sized in points by the style, so the only way to make it smaller on the
# page is to give it a larger page to be drawn on and then print that at a
# reduction: at a scale of 2 the text lands at half its point size. (Resolution
# has nothing to do with it. The image is printed at GRAPH_SIZE_MM whatever its
# pixel count, so raising the dpi alone yields the same picture with more pixels
# in it.) The aspect ratio is untouched, so the printed size stays as above.
GRAPH_DRAW_SCALE = 2

# Pixels per inch of *printed* graph. The images are rendered to this and then
# laid into the page at GRAPH_SIZE_MM, so it is the resolution they are actually
# reproduced at, on paper and on screen alike.
IMAGE_RESOLUTION_PPI = 300

# graph_data_choice ids whose curves do not depend on the drive level, so they
# are reported once instead of once per excitation. Impedance is a property of
# the electrical network and the phases are ratios, so neither moves with the
# voltage.
VOLTAGE_INDEPENDENT_GRAPHS = (1, 6)

# Input-form values the report leaves out, so that the input section stays
# complementary to the results summary rather than repeating it, and carries
# only what says something about the design. The entries naming a place in the
# summary must be kept in sync with SpeakerSystem.get_summary and the summaries
# it calls into (SpeakerDriver, Motor, Coil).
INPUTS_NOT_REPORTED = frozenset({
    # already in the results summary, under the heading named
    "Le",           # "L_e" under Speaker unit
    "Xpeak",        # "X_peak" under Displacements
    "Bl_p2", "Bl_p3",    # "Bl"
    "Re_p2", "Re_p3",    # "R_e"
    "Mmd_p2",       # "M_md"
    "Mms_p3",       # "M_ms"
    "Qp",           # "Q_p" under Bass reflex
    "coil_options",  # spelled out under Windings
    "n_speaker", "coupling",  # "drivers, ... wiring" under System (shown when more than one)

    # nothing to say about the design
    "excitation_type",   # every graph it applies to states the excitation itself
    "excitation_value",
    "motor_spec_type",   # only records which way the numbers were entered
    })

# Inputs reported under another tab's heading than the one they are entered on.
# The nominal impedance and the external resistance sit on the General tab of the
# form, among the driver parameters, but describe the electrical system; they
# lead the System table, in the order the form lists them.
INPUTS_REPORTED_UNDER = {
    "Rnom": "System",
    "Rext": "System",
    }

# Tabs holding the parameters of one driver. With several drivers, their
# headings in the report say so.
PER_DRIVER_TABS = ("General", "Motor")

# Inputs whose value names the kind of part first and the way it is specified
# after a " - "; only the part is of interest, e.g. "PR - Define mass and damping
# ratio" is reported as "PR".
INPUTS_VALUE_BEFORE_DASH = frozenset({
    "resonator_spec_type",
    })

# Abbreviations for the units the tooltips spell out in words. Units the tooltips
# already give in short form (cm², mm, mH, ohm) pass through untouched, as does a
# parenthesised symbol (see _UNIT_SYMBOL_PATTERN).
UNIT_ABBREVIATIONS = {
    "Hertz": "Hz",
    "gram": "g",
    "liter": "l",
    "millimeter": "mm",
    "seconds": "s",
    "Tesla": "T",
    "Tesla meter": "Tm",
    "kilograms per second": "kg/s",
    "Newtons per millimeter": "N/mm",
    }

# Labels the report uses in place of what the form shows, taking precedence over
# the form's own row label. These inputs are not laid out as labelled QFormLayout
# rows and so have no label widget to read: the enclosure/parent-body radio groups
# and the combo box heading a stacked page.
WIDGET_LABELS = {
    "resonator_spec_type": "Resonator",
    "enclosure_type": "Enclosure type",
    "parent_body": "Parent body",
    }

# The tooltips state the unit of an input on a line of their own, e.g.
# "Unit is millimeter." -- that wording is the application's only record of an
# input's unit, so the report reads it from there.
_UNIT_PATTERN = re.compile(r"^Unit is (.+?)\.$", re.MULTILINE)
# A parenthesised symbol at the end of a unit, e.g. "micrometer (μm)".
_UNIT_SYMBOL_PATTERN = re.compile(r"\(([^)]+)\)$")


# ---- Input form ------------------------------------------------------------

def _unit_from_tooltip(tooltip: str) -> str:
    """The unit an input is entered in, abbreviated. '' when it has none.

    The tooltips are written for the form, where there is room to spell a unit
    out; the report sets the unit beside the number instead, so it wants the
    short form.
    """
    match = _UNIT_PATTERN.search(tooltip or "")
    if match is None:
        return ""

    unit = match.group(1).strip()

    # Prefer the symbol when the tooltip spells the unit out and then gives one.
    symbol = _UNIT_SYMBOL_PATTERN.search(unit)
    if symbol:
        return symbol.group(1)

    return UNIT_ABBREVIATIONS.get(unit, unit)


def _is_on_inactive_page(widget) -> bool:
    """Whether the widget sits on a QStackedWidget page that is not the shown one.

    The inputs of the motor and resonator definitions live on stacked pages, and
    the pages that are not on show stay *enabled* -- Qt only hides them -- so
    isEnabled() alone would report a motor definition the model was not built
    from. isVisible() cannot stand in for it either: it is False for every tab
    that is not the current one, and the report covers all four tabs. Hence this
    walk, which skips the stack a QTabWidget drives its own pages with.
    """
    child = widget
    parent = widget.parentWidget()
    while parent is not None:
        if (isinstance(parent, qtw.QStackedWidget)
                and not isinstance(parent.parentWidget(), qtw.QTabWidget)
                and parent.currentWidget() is not child):
            return True
        child, parent = parent, parent.parentWidget()
    return False


def _label_for(widget) -> str | None:
    "The text of the form-row label of a widget, or None when it has no label."
    parent = widget.parentWidget()
    while parent is not None:
        layout = parent.layout()
        if isinstance(layout, qtw.QFormLayout):
            label = layout.labelForField(widget)
            if label is not None:
                return label.text()
        parent = parent.parentWidget()
    return None


def _display_value(widget) -> str:
    "What the widget shows the user, as text. '' for widgets that hold no value."
    if isinstance(widget, qtw.QButtonGroup):
        button = widget.checkedButton()
        return button.text() if button is not None else ""
    if isinstance(widget, qtw.QComboBox):
        return widget.currentText()
    if isinstance(widget, qtw.QAbstractSpinBox):
        return widget.cleanText()
    if isinstance(widget, qtw.QCheckBox):
        return "Yes" if widget.isChecked() else "No"
    if isinstance(widget, qtw.QLineEdit):
        return widget.text()
    return ""


def collect_extra_inputs(input_form, n_speaker: int = 1) -> list[tuple[str, list[dict]]]:
    """The active input values worth reporting beside the results summary.

    Left out are the values the summary already carries and the handful that say
    nothing about the design (see INPUTS_NOT_REPORTED).

    Returns one (tab name, rows) pair per tab that has anything to show, with the
    rows in the order the form lays them out. Only inputs that take part in the
    current model are listed: a disabled input has been switched off by the form
    logic, and one on a hidden stacked page belongs to a definition that was not
    used.

    Inputs in INPUTS_REPORTED_UNDER are moved to the head of the named tab's
    table. With n_speaker > 1 the per-driver tabs (PER_DRIVER_TABS) are headed
    "<tab>, single driver".
    """
    sections = []
    moved = {}  # tab name -> rows moved into it from other tabs

    for i_tab in range(input_form.count()):
        form = input_form.widget(i_tab)
        rows = []

        for name, widget in form.interactable_widgets.items():
            if name in INPUTS_NOT_REPORTED:
                continue
            if isinstance(widget, qtw.QAbstractButton) and not isinstance(widget, qtw.QCheckBox):
                continue  # a push button holds no value

            # A button group is not a widget; judge it by the button that is on.
            probe = widget.checkedButton() if isinstance(widget, qtw.QButtonGroup) else widget
            if probe is None or not probe.isEnabled() or _is_on_inactive_page(probe):
                continue

            value = _display_value(widget)
            if not value:
                continue
            if name in INPUTS_VALUE_BEFORE_DASH:
                value = value.split(" - ")[0].strip()

            row = {"label": WIDGET_LABELS.get(name) or _label_for(probe) or name,
                   "value": value,
                   "unit": _unit_from_tooltip(probe.toolTip()),
                   "tooltip": probe.toolTip(),
                   }
            if name in INPUTS_REPORTED_UNDER:
                moved.setdefault(INPUTS_REPORTED_UNDER[name], []).append(row)
            else:
                rows.append(row)

        sections.append((input_form.tabText(i_tab), rows))

    sections = [(tab, moved.get(tab, []) + rows) for tab, rows in sections]

    if n_speaker > 1:
        sections = [(f"{tab}, single driver" if tab in PER_DRIVER_TABS else tab, rows)
                    for tab, rows in sections]

    return [(tab, rows) for tab, rows in sections if rows]


# ---- Graphs ----------------------------------------------------------------

def _excitations_for(graph_id: int, V_source: float) -> list[float]:
    "The source voltages one graph is reported at."
    if graph_id in VOLTAGE_INDEPENDENT_GRAPHS:
        return [V_source]

    if math.isclose(V_source, REFERENCE_VOLTAGE, rel_tol=1e-9):
        return [REFERENCE_VOLTAGE]  # the current input already is the reference
    return [REFERENCE_VOLTAGE, V_source]


def render_graphs(spk_sys, V_source: float) -> list[dict]:
    """Render every graph the model supports, at the reference and current input.

    The graphs come out in choice-button order, and the ones belonging to the
    same choice are adjacent, so a choice reported at both drive levels has its
    two graphs one under the other, to be compared.

    The drawing happens on a widget of this function's own, sized for the page
    rather than for the screen, so nothing here depends on the state or the
    geometry of the graph the user is looking at.
    """
    freqs = signal_tools.generate_log_spaced_freq_list(app_settings.get_value("f_min"),
                                                       app_settings.get_value("f_max"),
                                                       app_settings.get_value("calc_ppo"),
                                                       )

    size_inches = tuple(mm / 25.4 * GRAPH_DRAW_SCALE for mm in GRAPH_SIZE_MM)
    # One drawn inch is GRAPH_DRAW_SCALE printed inches, so this puts
    # IMAGE_RESOLUTION_PPI pixels into each inch of the graph on the page.
    dpi = IMAGE_RESOLUTION_PPI / GRAPH_DRAW_SCALE

    offscreen = MatplotlibWidget(layout_engine="tight")
    offscreen.canvas.figure.set_size_inches(*size_inches)

    graphs = []
    try:
        for graph_id, builder in sorted(PLOT_BUILDERS.items()):
            # The report holds exactly the graphs the application would let the
            # user look at, instead of pages saying the model has no such part.
            if not graph_is_available(graph_id, spk_sys):
                continue

            for V_graph in _excitations_for(graph_id, V_source):
                V_spk, W_spk = labels.excitation_at_speaker(spk_sys, V_graph)
                spec = builder(spk_sys, freqs, V_graph, V_spk, W_spk)
                apply_spec(offscreen, spec, freqs,
                           app_settings.get_value("f_min"),
                           app_settings.get_value("f_max"),
                           )
                graphs.append({"id": graph_id,
                               "alt": spec.title.replace("\n", " - "),
                               "png": _figure_to_png(offscreen.canvas.figure, dpi),
                               "width": round(size_inches[0] * dpi),
                               "height": round(size_inches[1] * dpi),
                               })
    finally:
        offscreen.deleteLater()

    return graphs


def _figure_to_png(figure, dpi: float) -> bytes:
    "The figure as PNG bytes, rendered at 'dpi' pixels to the drawn inch."
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=dpi)
    return buffer.getvalue()


# ---- Document --------------------------------------------------------------

def _inputs_html(sections: list[tuple[str, list[dict]]]) -> str:
    """The input sections as one table per tab. Labels are already HTML fragments.

    The unit sits beside the number in the value cell rather than in a column of
    its own, so the table fits in half a page.
    """
    if not sections:
        return "<p>-</p>"

    parts = []
    for section_name, rows in sections:
        parts.append(f"<h3>{html.escape(section_name)}</h3>")
        parts.append('<table class="inputs">')
        for row in rows:
            title = f' title="{html.escape(row["tooltip"])}"' if row["tooltip"] else ""
            unit = (f' <span class="unit">{html.escape(row["unit"])}</span>'
                    if row["unit"] else "")
            parts.append(f'<tr{title}>'
                         f'<td class="label">{row["label"]}</td>'
                         f'<td class="value">{html.escape(row["value"])}{unit}</td>'
                         '</tr>')
        parts.append("</table>")

    return "\n".join(parts)


def _graphs_html(graphs: list[dict]) -> str:
    """The graphs as base64 PNGs, one to a row and the full width of the column.

    No heading is written: every figure carries its own title and excitation
    line, drawn into the image.
    """
    if not graphs:
        return "<p>-</p>"

    parts = []
    for graph in graphs:
        encoded = base64.b64encode(graph["png"]).decode("ascii")
        parts.append('<figure class="graph">'
                     f'<img src="data:image/png;base64,{encoded}"'
                     f' width="{graph["width"]}" height="{graph["height"]}"'
                     f' alt="{html.escape(graph["alt"])}">'
                     '</figure>')

    return "\n".join(parts)


def _state_json(state: dict) -> str:
    "The session state, for a report to stay traceable to the model behind it."
    return json.dumps({**state, "application_data": APP_DEFINITIONS}, indent=4)


def _meta_line() -> str:
    return (f"Generated {time.strftime('%Y-%m-%d %H:%M')}"
            f" &middot; {APP_DEFINITIONS['app_name']} {APP_DEFINITIONS['version']}"
            f" &middot; calculated over {app_settings.get_value('f_min'):g}"
            f"-{app_settings.get_value('f_max'):g} Hz"
            f" at {app_settings.get_value('calc_ppo'):g} points per octave"
            )


def build_html(title: str, description: str, results_html: str,
               input_sections: list, graphs: list, subtitle: str) -> str:
    """Fill the report template, giving the document WeasyPrint lays out.

    All caller-supplied text is escaped here.
    """
    template = Template(get_main_dir().joinpath(TEMPLATE_FILE).read_text(encoding="utf-8"))

    return template.substitute(
        app_name=html.escape(APP_DEFINITIONS["app_name"]),
        app_version=html.escape(APP_DEFINITIONS["version"]),
        title=html.escape(title.strip() or "Untitled"),
        subtitle=html.escape(subtitle),
        description=html.escape(description),
        results=results_html,  # already HTML, straight from the model's summary
        inputs=_inputs_html(input_sections),
        graphs=_graphs_html(graphs),
        meta=_meta_line(),
        )


# ---- File IO ---------------------------------------------------------------

def _default_file_name(title: str) -> str:
    "A file name suggestion made from the design's title."
    stem = re.sub(r"[^\w \-.]", "", title).strip() or "report"
    return stem + FILE_SUFFIX


def prompt_report_path(parent, start_dir: str, title: str) -> Path | None:
    "Show the save dialog and return the chosen path, or None if canceled."
    path_unverified = qtw.QFileDialog.getSaveFileName(parent,
                                                      caption="Save report to a file..",
                                                      dir=str(Path(start_dir) / _default_file_name(title)),
                                                      filter=FILE_FILTER,
                                                      )
    file_raw = path_unverified[0]
    if not file_raw:
        return None  # nothing selected, so pick file is canceled

    file = Path(file_raw)
    if file.suffix.lower() != FILE_SUFFIX:
        # the filter does not append the extension itself; mirrors session_io
        file = file.with_suffix(FILE_SUFFIX)

    return file


def _page_layout() -> qtg.QPageLayout:
    "The sheet the document is laid out on."
    left, top, right, bottom = PAGE_MARGINS_MM
    return qtg.QPageLayout(qtg.QPageSize(PAGE_SIZE_ID),
                           qtg.QPageLayout.Orientation.Portrait,
                           qtc.QMarginsF(left, top, right, bottom),
                           qtg.QPageLayout.Unit.Millimeter,
                           )


def _print_to_pdf(document: str, file: Path) -> None:
    """Lay the HTML out onto sheets and print them to 'file'.

    The document is handed over as a file rather than through setHtml(), which
    builds a data: URL out of what it is given and so inherits the engine's 2 MB
    cap on those -- a report carrying a dozen embedded graphs passes that several
    times over.

    Loading and printing are both asynchronous. A local event loop waits for each
    in turn, so that the function does not return while the file is still being
    written, with a timeout so a page that never finishes cannot hang the
    application.
    """
    page = QWebEnginePage()
    loop = qtc.QEventLoop()
    outcome = {}

    def loaded(ok: bool) -> None:
        if not ok:
            outcome["error"] = "the document could not be laid out"
            loop.quit()
            return
        page.printToPdf(str(file), _page_layout())

    def printed(_path: str, ok: bool) -> None:
        if ok:
            outcome["done"] = True
        else:
            outcome["error"] = "the document could not be printed"
        loop.quit()

    page.loadFinished.connect(loaded)
    page.pdfPrintingFinished.connect(printed)

    try:
        # The source has to stay on disk until the engine has read it, which is
        # why the wait below happens inside this block.
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir, "report.html")
            source.write_text(document, encoding="utf-8")
            page.load(qtc.QUrl.fromLocalFile(str(source)))
            qtc.QTimer.singleShot(RENDER_TIMEOUT_MS, loop.quit)
            loop.exec()
    finally:
        page.deleteLater()
        # Carry the deferred delete out now rather than whenever the caller's
        # event loop next turns: the profile a page belongs to complains if it
        # is released while any of its pages are still alive.
        qtc.QCoreApplication.sendPostedEvents(None, qtc.QEvent.Type.DeferredDelete)

    if "error" in outcome:
        raise RuntimeError(f"Could not write the report: {outcome['error']}.")
    if not outcome.get("done"):
        raise RuntimeError(f"Timed out writing the report after "
                           f"{RENDER_TIMEOUT_MS / 1000:.0f} seconds.")


def _attach_state(file: Path, state: dict) -> None:
    """Put the session state into the finished PDF as a file attachment.

    A PDF carries nothing that it does not print, so the state travels as an
    attachment -- viewers list it in their attachments panel -- instead of inside
    the page. That keeps a report traceable to the model it was made from.
    """
    import pypdf

    # The print engine writes a cross-reference trailer that pypdf reads as
    # inconsistent and warns about. The document round-trips correctly and there
    # is nothing a user could do about it, so the complaint is kept out of the
    # application's log.
    pypdf_log = logging.getLogger("pypdf._writer")
    previous_level = pypdf_log.level
    pypdf_log.setLevel(logging.ERROR)
    try:
        # clone_from reads the whole document before anything is written, so the
        # file can be rewritten in place.
        writer = pypdf.PdfWriter(clone_from=str(file))
        writer.add_attachment(file.with_suffix(session_io.FILE_SUFFIX).name,
                              _state_json(state).encode("utf-8"))
        writer.write(str(file))
    finally:
        pypdf_log.setLevel(previous_level)


def write_report(file: Path, document: str, state: dict) -> None:
    "Lay the report document out onto A4 sheets and write it as a PDF."
    logger.info(f"Writing report '{file.name}'")
    _print_to_pdf(document, file)
    _attach_state(file, state)
