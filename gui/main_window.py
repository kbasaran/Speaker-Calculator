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
from utils.version_convert import convert_any

import numpy as np
from core.calculations import calculate_voltage, calculate_spl
from core.factories import construct_SpeakerDriver, build_or_update_SpeakerSystem
from core.coil_winding import find_feasible_coils
import pyperclip

from config.app_config import APP_DEFINITIONS, singleton_settings
from utils.paths import get_main_dir
from gui.dialogs import (InputSectionTabWidget, SettingsDialog, CurveExportMenu,
                          show_file_paths, update_coil_options_combobox)

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
        self.results_textbox = qtw.QLabel()
        self.results_textbox.setTextFormat(qtg.Qt.MarkdownText)
        self.results_textbox.setAlignment(qtg.Qt.AlignTop)
        self.results_textbox.setTextInteractionFlags(qtc.Qt.TextInteractionFlag.TextSelectableByMouse |
                                                     qtc.Qt.TextInteractionFlag.TextSelectableByKeyboard,
                                                     )

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

        expected_text_width = qtg.QFontMetrics(
            self.results_textbox.font()).horizontalAdvance(
                "Bl : 5.555 Tm        Bl²/Re : 5.55 N²/W")
        self.results_textbox.setMinimumWidth(int(expected_text_width * 1))
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
        logger.debug("Get states initiated.")
        state = {}
        tab_widgets = [self.input_form.widget(i) for i in range(self.input_form.count())]
        for input_form_widget in tab_widgets:
            state = {**state, **input_form_widget.get_form_values()}

        state["user_notes"] = self.notes_textbox.toPlainText()
        state["user_title"] = self.title_textbox.text()

        return state

    def save_state_to_file(self, state=None):
        path_unverified = qtw.QFileDialog.getSaveFileName(self, caption='Save parameters to a file..',
                                                          dir=app_settings.get_value("last_used_folder"),
                                                          filter='Speaker calculator files (*.sscf)',
                                                          )

        try:
            file_raw = path_unverified[0]
            if file_raw:
                file = Path(file_raw)
                if file.suffix != ".sscf":
                    file = file.with_suffix(".sscf")
                # filter not working as expected, saves files without file extension scf
                # therefore above logic
                assert file.parent.exists()
            else:
                return  # empty file_raw. means nothing was selected, so pick file is canceled.
        except:
            # Path object could not be created
            raise NotADirectoryError(file_raw)

        # if you reached here, file is ready as Path object

        app_settings.set_value("last_used_folder", str(file.parent))

        if state is None:
            state = self.get_state()

        state["application_data"] = APP_DEFINITIONS

        json_string = json.dumps(state, indent=4)
        with open(file, "wt") as f:
            f.write(json_string)

        self.signal_good_beep.emit()

    @qtc.Slot(str)
    def load_state_from_file(self, file_arg: (Path | str) = None, update_last_used_folder=True):
        # no file is provided as argumnent
        # raise a file selection menu
        if file_arg is None:
            path_unverified = qtw.QFileDialog.getOpenFileName(self, caption='Open parameters from a save file..',
                                                              dir=app_settings.get_value("last_used_folder"),
                                                              filter='Speaker calculator files (*.sscf)',
                                                              )

            file_raw = path_unverified[0]
            if file_raw:
                file_arg = Path(file_raw)
            else:
                return  # canceled file select

        # file provided as argumnent
        file = Path(file_arg)
        if not file.is_file():
            raise FileNotFoundError(file)

        # file is ready as Path object at this point

        logger.info(f"Loading file '{file.name}'")
        if update_last_used_folder:
            app_settings.set_value("last_used_folder", str(file.parent))

        # backwards compatibility with older file versions
        state = convert_any(file)

        self.set_state(state)
        # self.statusBar().showMessage(f"Opened file '{file.name}'", 5000)

    def set_state(self, state: dict):
        logger.debug("Set states initiated.")
        tab_widgets = [self.input_form.widget(i) for i in range(self.input_form.count())]
        for input_form_widget in tab_widgets:
            # for each form on its corresponding tab, make a "relevant states" dictionary
            # this dictionary will not contain all the settings
            # but only the ones that have items with matching names to form's items (names in form_object_names)
            form_object_names = [name for name in input_form_widget.get_form_values().keys()]
            relevant_states = {key: val for (key, val) in state.items() if key in form_object_names}
            input_form_widget.update_form_values(relevant_states)

        self.notes_textbox.setPlainText(state.get("user_notes", "Error: NA"))
        self.title_textbox.setText(state.get("user_title", "Error: NA"))

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
        self.graph.update_figure(recalculate_limits=False)
        self.signal_good_beep.emit()

    def open_about_menu(self):
        result_text = "\n".join([
            "Speaker Calculator - Loudspeaker design and calculations tool",
            f"Version: {APP_DEFINITIONS['version']}",
            "",
            f"{APP_DEFINITIONS['copyright']}",
            f"{APP_DEFINITIONS['website']}",
            f"{APP_DEFINITIONS['email']}",
            "",
            "This program is free software: you can redistribute it and/or modify",
            "it under the terms of the GNU General Public License as published by",
            "the Free Software Foundation, either version 3 of the License, or",
            "(at your option) any later version.",
            "",
            "This program is distributed in the hope that it will be useful,",
            "but WITHOUT ANY WARRANTY; without even the implied warranty of",
            "MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the",
            "GNU General Public License for more details.",
            "",
            "You should have received a copy of the GNU General Public License",
            "along with this program.  If not, see <https://www.gnu.org/licenses/>.",
            "",
            "This software uses Qt for Python under the GPLv3 license.",
            "https://www.qt.io/",
            "",
            "See 'requirements.txt' for an extensive list of Python libraries used.",
        ])
        text_box = pwi.ResultTextBox("About", result_text, monospace=False)
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
                self.results_textbox.setText("\n\n### No coil found.\n Please check your input form.")
                self.signal_bad_beep.emit()
                return

        vals = self.get_state()
        speaker_driver = construct_SpeakerDriver(vals)
        spk_sys = self.speaker_model_state["system"] if hasattr(self, "speaker_model_state") else None
        speaker_system = build_or_update_SpeakerSystem(vals, speaker_driver, spk_sys)
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
        curves = dict()
        # self.graph.active_curves = list()  # obsoleted

        if not hasattr(self, "speaker_model_state"):
            self.signal_bad_beep.emit()
            return
        else:
            spk_sys, V_source = self.speaker_model_state["system"], self.speaker_model_state["V_source"]

        freqs = signal_tools.generate_log_spaced_freq_list(10, 1500, app_settings.get_value("calc_ppo"))
        W_sys = V_source**2 / spk_sys.R_sys
        V_spk = V_source / spk_sys.R_sys * spk_sys.speaker.Re
        W_spk = V_spk**2 / spk_sys.speaker.Re

        if checked_id == 0:

            if spk_sys.speaker.Sd == 0:  # shaker or other with no diaphragm
                accs = spk_sys.get_accelerations(V_source, freqs)

                curves.update({key.replace("Diaphragm", "Moving mass"): 20*np.log10(np.abs(acc)/1e-6) \
                               for key, acc in accs.items() if "relative" not in key})

                self.graph.set_y_limits_policy("SPL")
                self.graph.set_title(f"Acceleration, {V_source:.4g}V {W_spk:.3g}Watt@Re")
                self.graph.ax.set_ylabel(r"dB ref. $\mathregular{10^{-6}}$m/s²")

            else:  # speaker
                velocs = spk_sys.get_velocities(V_source, freqs)
                w = 2 * np.pi * freqs
                Xpeak_limited_velocities = spk_sys.speaker.Xpeak / 2**0.5 * (1j * w)

                _, SPL = calculate_spl((freqs, velocs["Diaphragm, RMS"]), spk_sys.speaker.Sd)

                _, SPL_Xpeak_limited = calculate_spl((freqs, Xpeak_limited_velocities), spk_sys.speaker.Sd)

                curves.update({"SPL piston mode, Xpeak limited": SPL_Xpeak_limited,
                               "SPL piston mode": SPL,
                               })

                self.graph.set_y_limits_policy("SPL")
                if spk_sys.speaker.Re == spk_sys.R_sys:
                    title = f"SPL@1m, Half-space\n{V_spk:.4g}V {W_spk:.3g}Watt@Re"
                else:
                    title = f"SPL@1m, Half-space\nSystem: {V_source:.4g}V, Speaker: {V_spk:.4g}V {W_spk:.3g}Watt@Re"
                self.graph.set_title(title)
                self.graph.ax.set_ylabel("dBSPL")

        elif checked_id == 1:
            curves.update({key: np.real(val) for key, val in spk_sys.get_Z(freqs).items()})
            self.graph.set_y_limits_policy("impedance")
            self.graph.set_title("Electrical impedance, real part - no inductance")
            self.graph.ax.set_ylabel("ohm")

        elif checked_id == 2:
            for key, val in spk_sys.get_displacements(V_source, freqs).items():
                if "relative" in key:
                    curves[key] = np.abs(val) * 1e3

            self.graph.set_y_limits_policy(None)
            if spk_sys.speaker.Re == spk_sys.R_sys:
                title = f"Relative Displacements\n{V_spk:.4g}V"
            else:
                title = f"Relative Displacements\nSystem: {V_source:.4g}V, Speaker: {V_spk:.4g}V"
            self.graph.set_title(title)
            self.graph.ax.set_ylabel("mm")

        elif checked_id == 3:
            for key, val in spk_sys.get_displacements(V_source, freqs).items():
                if "relative" not in key:
                    curves[key] = np.abs(val) * 1e3

            self.graph.set_y_limits_policy(None)
            if spk_sys.speaker.Re == spk_sys.R_sys:
                title = f"Displacements\n{V_spk:.4g}V"
            else:
                title = f"Displacements\nSystem: {V_source:.4g}V, Speaker: {V_spk:.4g}V"
            self.graph.set_title(title)
            self.graph.ax.set_ylabel("mm")

        elif checked_id == 4:
            curves.update({key: np.abs(val) for key, val in spk_sys.get_forces(V_source, freqs).items()})
            self.graph.set_y_limits_policy(None)
            if spk_sys.speaker.Re == spk_sys.R_sys:
                title = f"Forces\n{V_spk:.4g}V"
            else:
                title = f"Forces\nSystem: {V_source:.4g}V, Speaker: {V_spk:.4g}V"
            self.graph.set_title(title)
            self.graph.ax.set_ylabel("N")

        elif checked_id == 5:
            curves.update({key: np.abs(val) for key, val in spk_sys.get_velocities(V_source, freqs).items()})
            self.graph.set_y_limits_policy(None)
            if spk_sys.speaker.Re == spk_sys.R_sys:
                title = f"Velocities\n{V_spk:.4g}V"
            else:
                title = f"Velocities\nSystem: {V_source:.4g}V, Speaker: {V_spk:.4g}V"
            self.graph.set_title(title)
            self.graph.ax.set_ylabel("m/s")

        elif checked_id == 6:
            curves.update(spk_sys.get_phases(freqs).items())
            self.graph.set_y_limits_policy("phase")
            if spk_sys.speaker.Re == spk_sys.R_sys:
                title = f"Phase for displacements\n{V_spk:.4g}V"
            else:
                title = f"Phase for displacements\nSystem: {V_source:.4g}V, Speaker: {V_spk:.4g}V"
            self.graph.set_title(title)
            self.graph.ax.set_ylabel("degrees")

        else:
            raise ValueError(f"Checked id not recognized: {type(checked_id), checked_id}")

        for i, (name, y) in enumerate(curves.items()):
            self.graph.add_line2d(i, name, (freqs, y), update_figure=False)
            curve = signal_tools.Curve((freqs, y))
            curve.set_name_base(name)
            # self.graph.active_curves.append(curve)  # not in use anymore. was used to save curves.

        self.graph.update_figure()

    def update_all_results(self):
        checked_id = self.graph_data_choice.button_group.checkedId()
        self.update_graph(checked_id)
        summary_all = self.speaker_model_state["system"].get_summary(self.speaker_model_state["V_source"])
        self.results_textbox.setText(summary_all)
