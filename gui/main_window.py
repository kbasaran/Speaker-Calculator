import json
import dataclasses
import logging
from pathlib import Path

from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc
from PySide6 import QtGui as qtg

from generictools import signal_tools
from generictools.graphing_widget import MatplotlibWidget
import generictools.personalized_widgets as pwi

import numpy as np
from core.calculations import calculate_voltage
from core.factories import construct_SpeakerDriver, build_or_update_SpeakerSystem
from core.coil_winding import find_feasible_coils
import pyperclip

from config.app_config import APP_DEFINITIONS, ABOUT_TEXT, singleton_settings
from utils.paths import get_main_dir
from gui.dialogs import SettingsDialog, CurveExportMenu
from gui.help_menu import show_file_paths
from gui.coil_options import update_coil_options_combobox
from gui.input_section_tab_widget import InputSectionTabWidget
from gui.plot_builders import PLOT_BUILDERS
from gui import session_io

logger = logging.getLogger(__name__)
app_settings = singleton_settings()


class MainWindow(qtw.QMainWindow):
    # these are signals that this object emits.
    # they will be triggered by the functions and the widgets in this object.
    signal_new_window = qtc.Signal(dict)  # new_window with kwargs as widget values
    signal_good_beep = qtc.Signal()
    signal_bad_beep = qtc.Signal()
    # signal_user_settings_changed = qtc.Signal()  # settings from menu bar changed, such as graph type

    def __init__(self, sound_engine, wires, user_form_dict=None, open_user_file=None):
        super().__init__()
        self.wires = wires
        self.setWindowTitle(" - ".join(
            (APP_DEFINITIONS["app_name"],
             APP_DEFINITIONS["version"])
            ))
        self.signal_bad_beep.connect(sound_engine.bad_beep)
        self.signal_good_beep.connect(sound_engine.good_beep)
        self._create_menu_bar()
        self._create_widgets()
        self._place_widgets()
        self.resize(self.minimumSizeHint())  # is the GUI too large? do this.
        self._connect_widgets()
        # self.setStatusBar(qtw.QStatusBar())
        # self.statusBar().showMessage("Starting new window..", 2000)

        if user_form_dict:
            self.set_state(user_form_dict)
        elif open_user_file:
            self.load_state_from_file(open_user_file)
        elif (default_startup_file := get_main_dir().joinpath(app_settings.get_value("startup_state_file"))).is_file():
            self.load_state_from_file(default_startup_file, update_last_used_folder=False)
        else:
            self._update_model_button_clicked()

    def _create_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        new_window_action = file_menu.addAction("New window", self.duplicate_window)
        load_action = file_menu.addAction("Load state..", self.load_state_from_file)
        save_action = file_menu.addAction("Save state..", self.save_state_to_file)

        edit_menu = menu_bar.addMenu("Edit")
        settings_action = edit_menu.addAction("Settings..", lambda: SettingsDialog().exec())

        help_menu = menu_bar.addMenu("Help")
        paths_action = help_menu.addAction("Show paths of assets..", lambda: show_file_paths(self))
        about_action = help_menu.addAction("About", self.open_about_menu)

    def _create_widgets(self):
        # ---- Left hand side
        lh_boxlayout = qtw.QVBoxLayout()

        self.input_form = InputSectionTabWidget()
        # connect its signals
        self.input_form.signal_good_beep.connect(self.signal_good_beep)
        self.input_form.signal_bad_beep.connect(self.signal_bad_beep)

        self.update_button = pwi.PushButton(
            "update_results",
            "Update results",
            "Update the underlying model and recalculate. Click this each time you modify the user form.",
            )

        self.title_textbox = qtw.QLineEdit()
        self.notes_textbox = qtw.QPlainTextEdit()
        self.title_textbox.setClearButtonEnabled(True)
        self.title_textbox.setMaxLength(48)

        # ---- Center - results
        # Read-only QTextBrowser (not a QLabel): it wraps overlong lines to the
        # widget width and scrolls when the summary is tall, so the summaries no
        # longer need manual line breaks to fit a fixed width. Content is Markdown,
        # so it must be set with setMarkdown() (setText() would treat the embedded
        # <br>/<sub> tags as HTML and render the Markdown headers literally).
        self.results_textbox = qtw.QTextBrowser()
        self.results_textbox.setReadOnly(True)  # selectable by default when read-only

        # ---- Right hand side (graph etc.)
        rh_widget = qtw.QWidget()

        # Graph
        self.graph = MatplotlibWidget(layout_engine="tight")
        self.graph_data_choice = pwi.ChoiceButtonGroup("graph_data_choice",

                                                       {0: "SPL",
                                                        1: "Impedance",
                                                        2: "Displacements (rel.)",
                                                        3: "Displacements",
                                                        4: "Forces",
                                                        5: "Velocities",
                                                        6: "Phase",
                                                        },

                                                       {0: "/",
                                                           1: "/",
                                                           2: "/",
                                                           3: "/",
                                                           4: "/",
                                                           5: "/",
                                                           6: "/",
                                                        },

                                                       )
        self.graph_data_choice.buttons()[2].setEnabled(False)  # the relative button is disabled at start

        self.graph_pushbuttons = pwi.PushButtonGroup({"export_curve": "Export curve",
                                                      "export_json": "Export model",
                                                      },
                                                     {"export_curve": "Export a single curve to clipboard.",
                                                      "export_json": "Export the underlying model parameters to clipboard. Export will be JSON format text.",
                                                      },
                                                     )

        # Make buttons under the graph larger
        for button in self.graph_pushbuttons.buttons().values():
            text_height = qtg.QFontMetrics(button.font()).capHeight()
            button.setMinimumHeight(text_height * 5)

    def _place_widgets(self):
        # ---- Make center widget
        mw_center_widget = qtw.QWidget()
        mw_center_layout = qtw.QHBoxLayout(mw_center_widget)
        self.setCentralWidget(mw_center_widget)

        # ---- Make left hand side
        lh_boxlayout = qtw.QVBoxLayout()
        mw_center_layout.addLayout(lh_boxlayout)

        text_height = qtg.QFontMetrics(self.notes_textbox.font()).capHeight()
        text_width = qtg.QFontMetrics(self.notes_textbox.font()).averageCharWidth()


        lh_boxlayout.addWidget(self.input_form)
        self.input_form.setSizePolicy(
            qtw.QSizePolicy.Minimum, qtw.QSizePolicy.Fixed)

        # lh_boxlayout.addSpacing(text_height / 2)
        # lh_boxlayout.addWidget(pwi.SunkenLine())
        self.update_button.setMinimumHeight(text_height * 5)
        lh_boxlayout.addWidget(self.update_button)

        lh_boxlayout.addWidget(pwi.SunkenLine())

        title_label = qtw.QLabel("<b>Title</b>")
        title_label.setSizePolicy(
            qtw.QSizePolicy.Preferred, qtw.QSizePolicy.Fixed)
        lh_boxlayout.addWidget(title_label)

        lh_boxlayout.addWidget(self.title_textbox)  # why is a line appearing under this box?
        self.title_textbox.setSizePolicy(
            qtw.QSizePolicy.Preferred, qtw.QSizePolicy.Fixed)  # height is still not fixed somehow. why?

        notes_label = qtw.QLabel("<b>Notes</b>")
        notes_label.setSizePolicy(
            qtw.QSizePolicy.Preferred, qtw.QSizePolicy.Fixed)
        lh_boxlayout.addWidget(notes_label)

        lh_boxlayout.addWidget(self.notes_textbox)
        self.notes_textbox.setSizePolicy(
            qtw.QSizePolicy.Preferred, qtw.QSizePolicy.Expanding)

        # Put a spacer line in between left hand saide with inputs and center column with results
        sunken_line = qtw.QFrame()
        sunken_line_layout = qtw.QHBoxLayout(sunken_line)
        sunken_line.setFrameShape(qtw.QFrame.VLine)
        sunken_line.setFrameShadow(qtw.QFrame.Sunken)
        sunken_line_layout.setContentsMargins(*[int(val) for val in (text_width * 2 / 3, text_height * 2, text_width * 2 / 3, text_height)])
        mw_center_layout.addWidget(sunken_line)

        # ---- Make center with results
        results_textbox_layout = qtw.QVBoxLayout()
        # results_textbox_layout.addSpacing(text_height * 1)
        results_textbox_layout.addWidget(self.results_textbox)

        mw_center_layout.addLayout(results_textbox_layout)

        # Floor the results column at the width of a representative line so it is not
        # cramped on launch. A QTextBrowser wraps to fit, so (unlike the old QLabel)
        # it never demands width from its content -- this minimum is what keeps the
        # panel wide enough. Pad for the frame border, the document margin and the
        # vertical scrollbar so the sample line still fits without wrapping.
        expected_text_width = qtg.QFontMetrics(
            self.results_textbox.font()).horizontalAdvance(
                "Bl : 5.555 Tm        Bl²/Re : 5.55 N²/W")
        chrome_width = (2 * self.results_textbox.frameWidth()
                        + 2 * int(self.results_textbox.document().documentMargin())
                        + self.results_textbox.style().pixelMetric(
                            qtw.QStyle.PixelMetric.PM_ScrollBarExtent))
        self.results_textbox.setMinimumWidth(expected_text_width + chrome_width)
        self.results_textbox.setSizePolicy(
            qtw.QSizePolicy.Preferred, qtw.QSizePolicy.Preferred)


        # ---- Make right hand with graph
        rh_layout = qtw.QVBoxLayout()
        rh_layout.setContentsMargins(-1, 0, -1, 0)
        mw_center_layout.addLayout(rh_layout)

        rh_layout.addWidget(self.graph)
        rh_layout.addWidget(self.graph_data_choice)
        rh_layout.addWidget(self.graph_pushbuttons)

        self.graph.setSizePolicy(
            qtw.QSizePolicy.Expanding, qtw.QSizePolicy.Expanding)

    def _connect_widgets(self):
        self.input_form.interactable_widgets["update_coil_choices"]\
            .clicked.connect(self.update_coil_choices_button_clicked)
        self.update_button.clicked.connect(self._update_model_button_clicked)
        for button in self.graph_data_choice.buttons():
            button_id = self.graph_data_choice.button_group.id(button)
            button.pressed.connect(lambda arg1=button_id: self.update_graph(arg1))
        self.graph_pushbuttons.buttons()["export_curve_pushbutton"].clicked.connect(self._export_curve_clicked)
        self.graph_pushbuttons.buttons()["export_json_pushbutton"].clicked.connect(self._export_model_clicked)

        # disable the relative plots
        self.input_form.interactable_widgets["parent_body"].buttons()[1].toggled.connect(
            self.graph_data_choice.buttons()[2].setEnabled)

        # Drag and drop functionality
        self.input_form.signal_file_dropped.connect(self.load_state_from_file)

        # settings connection
        app_settings.settings_changed.connect(self._settings_were_updated)

    def get_state(self):
        return session_io.collect_state(self.input_form, self.title_textbox, self.notes_textbox)

    def save_state_to_file(self, state=None):
        file = session_io.prompt_save_path(self, app_settings.get_value("last_used_folder"))
        if file is None:
            return  # nothing selected, so pick file is canceled

        # bookkeeping only -- must not emit settings_changed (would beep and
        # redraw the figure), otherwise saving beeps twice
        app_settings.set_value("last_used_folder", str(file.parent), signal=False)

        if state is None:
            state = self.get_state()

        session_io.write_state_file(file, state)
        self.signal_good_beep.emit()

    @qtc.Slot(str)
    def load_state_from_file(self, file_arg: (Path | str) = None, update_last_used_folder=True):
        # no file provided as argument -> raise a file selection menu
        if file_arg is None:
            file = session_io.prompt_load_path(self, app_settings.get_value("last_used_folder"))
            if file is None:
                return  # canceled file select
        else:
            file = Path(file_arg)

        if not file.is_file():
            raise FileNotFoundError(file)

        # update the last used folder before converting, so it is remembered
        # even if the (older-format) file fails version conversion
        if update_last_used_folder:
            # bookkeeping only -- don't emit settings_changed (see save_state_to_file)
            app_settings.set_value("last_used_folder", str(file.parent), signal=False)

        state = session_io.read_state_file(file)
        self.set_state(state)
        # self.statusBar().showMessage(f"Opened file '{file.name}'", 5000)

    def set_state(self, state: dict):
        session_io.apply_state(self.input_form, self.title_textbox, self.notes_textbox, state)
        self._update_model_button_clicked()

    def duplicate_window(self):
        self.signal_new_window.emit(
            {"user_form_dict": self.get_state()})

    # def open_settings_dialog(self):
    #     settings_dialog = SettingsDialog(parent=self)
    #     settings_dialog.signal_settings_changed.connect(
    #         self._settings_dialog_return)
    #
    #     return_value = settings_dialog.exec()
    #     # What does it return normally?
    #     if return_value:
    #         pass

    def _settings_were_updated(self):
        # A settings change may alter the frequency range/resolution (f_min, f_max,
        # calc_ppo), so recompute the curves over the new range when a model exists.
        # update_all_results -> update_graph -> update_figure(recalculate_limits=True)
        # also refreshes the x-axis limits. Fall back to a light redraw otherwise.
        if hasattr(self, "speaker_model_state"):
            self.update_all_results()
        else:
            self.graph.update_figure(recalculate_limits=False)
        self.signal_good_beep.emit()

    def open_about_menu(self):
        text_box = pwi.ResultTextBox("About", ABOUT_TEXT, monospace=False)
        text_box.exec()

    def _not_implemented_popup(self):
        message_box = qtw.QMessageBox(icon=qtw.QMessageBox.Information,
                                      text="Feature not Implemented",
                                      )
        message_box.setStandardButtons(qtw.QMessageBox.Ok)
        message_box.exec()

    def update_coil_choices_button_clicked(self):
        name_to_motor = find_feasible_coils(self.get_state(), self.wires, logger)
        update_coil_options_combobox(self.input_form.interactable_widgets["coil_options"], self.input_form, name_to_motor)
        if self.input_form.interactable_widgets["coil_options"].currentData():
            self.signal_good_beep.emit()


    def _update_model_button_clicked(self):
        self.results_textbox.clear()

        if self.input_form.interactable_widgets["motor_spec_type"].currentData() == "define_coil":
            update_coil_options_combobox(self.input_form.interactable_widgets["coil_options"],
                                         self.input_form,
                                         find_feasible_coils(self.get_state(), self.wires, logger),
                                         )
            if not self.input_form.interactable_widgets["coil_options"].currentData():
                self.results_textbox.setMarkdown("\n\n### No coil found.\n Please check your input form.")
                self.signal_bad_beep.emit()
                return

        vals = self.get_state()
        speaker_driver = construct_SpeakerDriver(vals)
        spk_sys = self.speaker_model_state["system"] if hasattr(self, "speaker_model_state") else None
        try:
            speaker_system = build_or_update_SpeakerSystem(vals, speaker_driver, spk_sys)
        except ValueError as e:
            # An infeasible resonator (e.g. a bass-reflex vent that is over-tuned and
            # would need a non-positive port length) makes the model unbuildable, the
            # same way an infeasible coil-winding target does above. Report and abort
            # the update, leaving any previous model untouched.
            self.results_textbox.setMarkdown(f"\n\n### Model update failed.\n{e}")
            self.signal_bad_beep.emit()
            return
        V_source = calculate_voltage(vals["excitation_value"],
                                        vals["excitation_type"]["current_data"],
                                        re=speaker_driver.Re,
                                        rnom=vals["Rnom"],
                                        )

        self.speaker_model_state = {"vals": vals,
                                    "driver": speaker_driver,
                                    "system": speaker_system,
                                    "V_source": V_source,
                                    }

        self.update_all_results()
        self.signal_good_beep.emit()


    def _export_curve_clicked(self):
        position = self.graph_pushbuttons.buttons()["export_curve_pushbutton"].mapToGlobal(qtc.QPoint(0,0))
        lines = self.graph.get_visible_lines_in_qlist_order()
        curves = []
        for line in lines:
            xy = line.get_xydata()
            curve = signal_tools.Curve(xy)
            curve.set_name_base(line.get_label())
            curves.append(curve)
        CurveExportMenu(curves=curves, position=position, parent=self)

    def _export_model_clicked(self):
        if not hasattr(self, "speaker_model_state"):
            self.signal_bad_beep.emit()
            return
        else:
            model = self.speaker_model_state["system"]
            pyperclip.copy(json.dumps(dataclasses.asdict(model), indent=4))
            self.signal_good_beep.emit()

    def update_graph(self, checked_id):
        self.graph.clear_graph()

        if not hasattr(self, "speaker_model_state"):
            self.signal_bad_beep.emit()
            return

        spk_sys, V_source = self.speaker_model_state["system"], self.speaker_model_state["V_source"]

        freqs = signal_tools.generate_log_spaced_freq_list(app_settings.get_value("f_min"),
                                                           app_settings.get_value("f_max"),
                                                           app_settings.get_value("calc_ppo"))
        V_spk = V_source / spk_sys.R_sys * spk_sys.speaker.Re
        W_spk = V_spk**2 / spk_sys.speaker.Re

        try:
            builder = PLOT_BUILDERS[checked_id]
        except KeyError:
            raise ValueError(f"Checked id not recognized: {type(checked_id), checked_id}")

        spec = builder(spk_sys, freqs, V_source, V_spk, W_spk)

        self.graph.set_y_limits_policy(spec.ylimits_policy)
        self.graph.set_title(spec.title)
        self.graph.ax.set_ylabel(spec.ylabel)

        for i, (name, y) in enumerate(spec.curves.items()):
            self.graph.add_line2d(i, name, (freqs, y), update_figure=False)

        self.graph.update_figure()

    def update_all_results(self):
        checked_id = self.graph_data_choice.button_group.checkedId()
        self.update_graph(checked_id)
        summary_all = self.speaker_model_state["system"].get_summary(self.speaker_model_state["V_source"])
        self.results_textbox.setMarkdown(summary_all)
