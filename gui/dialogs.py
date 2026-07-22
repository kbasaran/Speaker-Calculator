import os
import dataclasses
import logging
from functools import partial

from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc
from PySide6 import QtGui as qtg

from generictools import signal_tools
import generictools.personalized_widgets as pwi

import matplotlib as mpl

from config.sc_config import APP_DEFINITIONS, singleton_settings
from utils.paths import get_main_dir

logger = logging.getLogger(__name__)
app_settings = singleton_settings()


class InputSectionTabWidget(qtw.QTabWidget):
    signal_good_beep = qtc.Signal()
    signal_bad_beep = qtc.Signal()
    signal_file_dropped = qtc.Signal(str)

    TAB_NAMES = ("General", "Motor", "Enclosure", "System")

    def __init__(self):
        super().__init__()
        self.interactable_widgets = {}
        self._add_form_tabs()
        self.setAcceptDrops(True)

    def _add_form_tabs(self):
        forms = (
            self._make_form_for_general_tab(),
            self._make_form_for_motor_tab(),
            self._make_form_for_enclosure_tab(),
            self._make_form_for_system_tab(),
        )
        for tab_name, form in zip(self.TAB_NAMES, forms, strict=True):
            self.addTab(form, tab_name)
            self.interactable_widgets.update(form.interactable_widgets)

    def dragEnterEvent(self, event: qtg.QDragEnterEvent):
        """Accept file drag event if it contains URLs (files)."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: qtg.QDropEvent):
        """Handle file drop event and load file contents."""
        mime_data = event.mimeData()
        urls = mime_data.urls()
        if not urls:
            return

        paths = [url.toLocalFile().removesuffix("/") for url in urls]
        if os.name == "nt":
            paths = [path.removesuffix("/") for path in paths]

        for path in paths:
            logger.info(f"User dropped file '{path}' onto InputSectionTabWidget.")
            self.signal_file_dropped.emit(path)

    def _make_form_for_general_tab(self):
        form = pwi.UserForm()

        # ---- General specs
        form.add_row(pwi.Title("General specifications"))

        form.add_row(pwi.FloatSpinBox("fs",
                                      "Resonance frequency (undamped natural frequency) of the speaker in free-air condition."
                                      "\nUnit is Hertz.",
                                      decimals=1,
                                      min_max=(0.1, None),
                                      ),
                     description="f<sub>s</sub>",
                     )

        form.add_row(pwi.FloatSpinBox("Qms",
                                      "Quality factor of speaker, only the mechanical part."
                                      "\nUnitless quantity.",
                                      ),
                     description="Q<sub>ms</sub>",
                     )

        form.add_row(pwi.FloatSpinBox("Xpeak",
                                      "Peak excursion allowed, one way."
                                      "\nUnit is millimeter.",
                                      coeff_for_SI=1e-3,
                                      ),
                     description="X<sub>peak</sub>",
                     )

        form.add_row(pwi.FloatSpinBox("dead_mass", "Moving mass excluding the coil windings and the air load on the diaphragm."
                                                   "\n'Dead mass = Mmd - coil winding mass'"
                                                   "\nUnit is gram.",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Dead mass",
                     )

        form.add_row(pwi.FloatSpinBox("Sd",
                                      "Diaphragm effective surface area.\nUse a value of '0' if there is no diaphragm, e.g. a shaker."
                                      "Unit is cm².",
                                      coeff_for_SI=1e-4,
                                      min_max=(0, None),
                                      ),
                     description="S<sub>d</sub>"
                     )

        # ---- Electrical input
        form.add_row(pwi.SunkenLine())

        form.add_row(pwi.Title("Electrical Input"))


        form.add_row(pwi.ComboBox("excitation_type", "Choose which type of input excitation you want to define.",
                                  [("Volts", "V"),
                                   ("Watts @Re", "W"),
                                      ("Watts @Rnom", "Wn")
                                   ],
                                  ),
                     description="Unit",
                     )

        form.add_row(pwi.FloatSpinBox("excitation_value", "The value for input excitation.\nUnit is as chosen above.",
                                      ),
                     description="Value",
                     )

        form.add_row(pwi.FloatSpinBox("Rnom", "Nominal impedance of the system. This is necessary to calculate the voltage applied to the system"
                                      "\nwhen 'Watts @Rnom' is selected as the input excitation unit."
                                      "\nUnit is ohm.",
                                      ),
                     description="Nominal impedance",
                     )

        form.add_row(pwi.FloatSpinBox("Rext",
                                      "The resistance between the speaker terminal and the voltage source."
                                      "\nMay be due to cables in our outside the speaker housing, connectors, amplifier internals etc."
                                      "\nCauses resistive loss of voltage appearing at speaker terminals."
                                      "\nUnit is ohm.",
                                      min_max=(0, None),
                                      ),
                     description="External resistance",
                     )

        # ---- Form logic
        def adjust_form_for_excitation_type(chosen_index):
            is_Wn = \
                form.interactable_widgets["excitation_type"].itemData(chosen_index) == "Wn"
            form.interactable_widgets["Rnom"].setEnabled(is_Wn)

        form.interactable_widgets["excitation_type"].currentIndexChanged.connect(adjust_form_for_excitation_type)
        # adjustment at start
        adjust_form_for_excitation_type(form.interactable_widgets["excitation_type"].currentIndex())

        return form

    def _make_form_for_motor_tab(self):
        form = pwi.UserForm()

        # Motor spec type
        form.add_row(pwi.ComboBox("motor_spec_type",
                                  "Choose which parameters you want to provide to make a motor definition.",
                                  [("Define Coil Dimensions and Average B", "define_coil"),
                                   ("Define Bl, Re, Mmd", "define_Bl_Re_Mmd"),
                                   ("Define Bl, Re, Mms", "define_Bl_Re_Mms"),
                                   ],
                                  ))
        form.interactable_widgets["motor_spec_type"].setStyleSheet(
            "font-weight: bold")

        # Stacked widget for different motor definition types
        form.motor_definition_stacked = qtw.QStackedWidget()
        form.motor_definition_stacked.setSizePolicy(qtw.QSizePolicy.Preferred, qtw.QSizePolicy.Maximum)
        # expands and pushes the next form rows down if I don't do the above line
        form.interactable_widgets["motor_spec_type"].currentIndexChanged.connect(
            form.motor_definition_stacked.setCurrentIndex)

        form.add_row(form.motor_definition_stacked)

        # ---- First page: "Define Coil Dimensions and Average B"
        motor_definition_p1 = pwi.SubForm()
        form.motor_definition_stacked.addWidget(motor_definition_p1)

        form.add_row(pwi.FloatSpinBox("target_Re",
                                      "Desired Re value. Wire type and number of windings will be "
                                      "calculated so as to best approach this value."
                                      "\nUnit is ohm.",
                                      ),
                     description="Target R<sub>e</sub>",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.FloatSpinBox("former_ID",
                                      "Internal diameter of the coil former."
                                      "\nUnit is millimeter.",
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Coil former ID",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.IntSpinBox("t_former",
                                    "Thickness of the coil former."
                                    "\nUnit is micrometer (\u03BCm).",
                                    coeff_for_SI=1e-6,
                                      min_max=(0, None)
                                    ),
                     description="Former thickness",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.FloatSpinBox("h_winding_target",
                                      "Desired height of the coil winding."
                                      "\nUnit is millimeter.",
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Target winding height",
                     into_form=motor_definition_p1,
                     )


        form.add_row(pwi.FloatSpinBox("B_average",
                                      "Average of radial magnetic field across the coil winding."
                                      "\nNeeds to be calculated separately and input here."
                                      "\nE.g. a value of '0.9' would mean that a winding with a wire "
                                      "that is 5m long will have a Bl of 4.5Tm."
                                      "\nUnit is Tesla.",
                                      decimals=3,
                                      coeff_for_SI=1,
                                      min_max=(0, None),
                                      ),
                     description="Average B on coil",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.LineTextBox("N_layer_options", "Enter the number of winding layer options that are accepted."
                                     "\nUse integers with a comma in between, e.g.: '2, 4'",
                                     ),
                     description="Number of layer options",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.FloatSpinBox("w_stacking_coef",
                                      "Stacking coefficient for additional winding layers put on."
                                      "Applies only on thickness. For height, only the average height of the wire is used and this has no effect."
                                      "\nE.g. if this is set to 0.8 and the average wire thickness is 1mm,"
                                      "\nthickness of a winding that has 3 layers will be"
                                      "\n 1 + 0.8 + 0.8 = 2.6mm. (applies not on first layer but consecutive layers only)"
                                      "\nFor stacking of ideally circular wires this value is 'sin(60)=0.5'.",
                                      min_max=(0, 1.99),
                                      ),
                     description="Stacking coefficient",
                     into_form=motor_definition_p1,
                     )
        form.interactable_widgets["w_stacking_coef"].setValue(1)

        form.add_row(pwi.FloatSpinBox("Rlw",
                                      "Resistance between the coil and the speaker terminals, e.g. leadwire"
                                      "\nUnit is ohm.",
                                      min_max=(0, None),
                                      # took the automatically assigned maximum from another widget
                                      # instead of typing n an arbitrary number
                                      # 'None' was not expected by the underlying 'setRange' method
                                      ),
                     description="Leadwire resistance",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.FloatSpinBox("reduce_per_layer",
                                    ("Reduce the number of windings on each consecutive winding layer by this number."
                                     "\nFor round coils suggested value is 1.5. For rectangular coils suggested value is 0.5."),
                                      min_max=(0, None),
                                      decimals=2,
                                    ),
                     description="Reduce windings per layer",
                     into_form=motor_definition_p1,
                     )


        update_coil_choices_button = pwi.PushButton("update_coil_choices",
                                                    "Update coil choices",
                                                    tooltip="Populate the below dropdown with possible coil choices based on given parameters.",
                                                    )

        form.add_row(update_coil_choices_button,
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.ComboBox("coil_options", "Select coil winding to be used for calculations.",
                                  [],
                                  ),
                     into_form=motor_definition_p1,
                     )

        # ---- Second page: "Define Bl, Re, Mmd"
        motor_definition_p2 = pwi.SubForm()
        form.motor_definition_stacked.addWidget(motor_definition_p2)

        form.add_row(pwi.FloatSpinBox("Bl_p2",
                                      "Force factor"
                                      "\nUnit is Tesla meter.",
                                      ),
                     description="Bl",
                     into_form=motor_definition_p2,
                     )

        form.add_row(pwi.FloatSpinBox("Re_p2",
                                      "DC resistance"
                                      "\nUnit is ohm.",
                                    ),
                     description="R<sub>e</sub>",
                     into_form=motor_definition_p2,
                     )

        form.add_row(pwi.FloatSpinBox("Mmd_p2",
                                      "Moving mass, excluding coupled air mass"
                                      "\nUnit is gram.",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="M<sub>md</sub>",
                     into_form=motor_definition_p2,
                     )

        # ---- Third page: "Define Bl, Re, Mms"
        motor_definition_p3 = pwi.SubForm()
        form.motor_definition_stacked.addWidget(motor_definition_p3)

        form.add_row(pwi.FloatSpinBox("Bl_p3",
                                      "Force factor"
                                      "\nUnit is Tesla meter.",
                                      ),
                     description="Bl",
                     into_form=motor_definition_p3,
                     )

        form.add_row(pwi.FloatSpinBox("Re_p3",
                                      "DC resistance"
                                      "\nUnit is ohm.",
                                    ),
                     description="R<sub>e</sub>",
                     into_form=motor_definition_p3,
                     )

        form.add_row(pwi.FloatSpinBox("Mms_p3",
                                      "Moving mass, including coupled air mass"
                                      "\nUnit is gram.",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="M<sub>ms</sub>",
                     into_form=motor_definition_p3,
                     )

        # ---- Mechanical specs
        form.add_row(pwi.SunkenLine())

        form.add_row(pwi.Title("Motor mechanical specifications"))

        form.add_row(pwi.FloatSpinBox("h_top_plate",
                                      "Thickness of the top plate."
                                      "\nUnit is millimeter.",
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Top plate thickness",
                     )

        form.add_row(pwi.IntSpinBox("airgap_clearance_inner",
                                    "Clearance on the inner side of the coil former."
                                    "\nUnit is micrometer (\u03BCm).",
                                    coeff_for_SI=1e-6,
                                    ),
                     description="Airgap inner clearance",
                     )

        form.add_row(pwi.IntSpinBox("airgap_clearance_outer",
                                    "Clearance on the outer side of the coil windings."
                                    "\nUnit is micrometer (\u03BCm).",
                                    coeff_for_SI=1e-6,
                                    ),
                     description="Airgap outer clearance",
                     )

        form.add_row(pwi.FloatSpinBox("h_former_under_coil",
                                      "Extension of the coil former below the coil windings."
                                      "\nUnit is millimeter.",
                                      coeff_for_SI=1e-3,
                                      min_max=(0, None),
                                      ),
                     description="Former bottom ext.",
                     )

        # spacer = qtw.QSpacerItem(0, 0, qtw.QSizePolicy.Minimum, qtw.QSizePolicy.MinimumExpanding)
        # form.add_row(spacer)

        # ---- Form logic
        def adjust_form_for_calc_type(chosen_index):
            is_define_coil = \
                form.interactable_widgets["motor_spec_type"].itemData(chosen_index) == "define_coil"
            form.interactable_widgets["h_top_plate"].setEnabled(is_define_coil)
            form.interactable_widgets["airgap_clearance_inner"].setEnabled(is_define_coil)
            form.interactable_widgets["airgap_clearance_outer"].setEnabled(is_define_coil)
            form.interactable_widgets["h_former_under_coil"].setEnabled(is_define_coil)
            self.widget(0).interactable_widgets["dead_mass"].setEnabled(is_define_coil)

        # def combo_box_contents_are_obsoleted(*args):
        #     combo_box=form.interactable_widgets["coil_options"]
        #     combo_box.clear()
        #     combo_box.addItem("----")

        form.interactable_widgets["motor_spec_type"].currentIndexChanged.connect(adjust_form_for_calc_type)

        # for row_name in ["former_ID", "t_former", "w_stacking_coef", "Rlw", "reduce_per_layer", "h_winding_target"]:
        #     form.interactable_widgets[row_name].valueChanged.connect(combo_box_contents_are_obsoleted)

        return form

    def _make_form_for_enclosure_tab(self):
        form = pwi.UserForm()

        # ---- Enclosure type
        form.add_row(pwi.Title("Enclosure type"))

        enclosue_type_choice_buttons = pwi.ChoiceButtonGroup("enclosure_type",
                                                        {0: "Free-air", 1: "Closed box", 2: "PR", 3: "Vented"},
                                                        {0: "Speaker assumed to be on an infinite baffle, with no acoustical loading on either side",
                                                         1: "Speaker rear side coupled to a sealed enclosure.",
                                                         2: "Speaker rear side coupled to an enclosure with a passive raditor or a bass-reflex vent.",
                                                         3: "Speaker rear side coupled to an enclosure with a bass-reflex vent.",
                                                         },
                                                        vertical=False,
                                                        )

        enclosue_type_choice_buttons.layout().setContentsMargins(0, 0, 0, 0)
        form.add_row(enclosue_type_choice_buttons)

        # Disable PR vented options for now
        form.interactable_widgets["enclosure_type"].buttons()[2].setEnabled(False)
        form.interactable_widgets["enclosure_type"].buttons()[3].setEnabled(False)

        # ---- Closed box specs
        form.add_row(pwi.SunkenLine())

        form.add_row(pwi.Title("Closed box specifications"))

        form.add_row(pwi.FloatSpinBox("Vb",
                                      "Internal volume filled by air."
                                      "\nFor vented calculations, the air in the vent is included in this value."
                                      "\nUnit is liter.",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Net internal volume",
                     )

        form.add_row(pwi.FloatSpinBox("Qa",
                                      "Quality factor of the speaker in enclosure resulting from absorption losses inside the enclosure."
                                      "\nCalculated at f<sub>b</sub>."
                                      "\nUnitless quantity.",
                                      decimals=1,
                                      min_max=(0.1, None),
                                      ),
                     description="Q<sub>a</sub> - internal absorption",
                     )

        # form.add_row(pwi.FloatSpinBox("Ql", "Quality factor of the speaker resulting from leakage losses of the enclosure.",
        #                               decimals=1,
        #                               min_max=(0.1, None),
        #                               ),
        #              description="Q<sub>l</sub> - leakage losses",
        #              )

        # ---- Passive radiator
        form.add_row(pwi.SunkenLine())

        form.add_row(pwi.Title("Passive radiator / Vented"))
        form.add_row(qtw.QLabel("Not implemented yet."))


        # ---- Form logic
        def adjust_form_for_enclosure_type(toggled_id, checked):
            form.interactable_widgets["Vb"].setEnabled(toggled_id == 1 and checked is True)
            form.interactable_widgets["Qa"].setEnabled(toggled_id == 1 and checked is True)

        form.interactable_widgets["enclosure_type"].idToggled.connect(adjust_form_for_enclosure_type)
        # adjustment at start
        adjust_form_for_enclosure_type(0, True)

        return form

    def _make_form_for_system_tab(self):
        form = pwi.UserForm()

        # ---- System type
        form.add_row(pwi.Title("Parent body"))

        dof_choice_buttons = pwi.ChoiceButtonGroup("parent_body",
                                                   {0: "Rigid", 1: "Mobile"},
                                                   {0: "1 degree of freedom - only the loudspeaker moving mass has mobility.",
                                                    1: "2 degrees of freedom - loudspeaker moving mass is attached to a parent lump mass that also has mobility."
                                                    },
                                                   vertical=False,
                                                   )
        dof_choice_buttons.layout().setContentsMargins(0, 0, 0, 0)
        form.add_row(dof_choice_buttons)

        # ---- Parent body

        form.add_row(pwi.FloatSpinBox("mpb",
                                      "Mass of the parent body."
                                      "\nUnit is gram.",
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Mass",
                     )

        form.add_row(pwi.FloatSpinBox("kpb",
                                      "Stiffness between the parent body and the reference frame."
                                      "\nUnit is Newtons per millimeter.",
                                      coeff_for_SI=1e3,
                                      ),
                     description="Stiffness",
                     )


        form.add_row(pwi.FloatSpinBox("rpb",
                                      "Damping coefficient between the parent body and the reference frame."
                                      "\nUnit is kilograms per second.",
                                      ),
                     description="Damping coefficient",
                     )

        # ---- Form logic
        def adjust_form_for_system_type(toggled_id, checked):
            form.interactable_widgets["kpb"].setEnabled(toggled_id == 1 and checked is True)
            form.interactable_widgets["mpb"].setEnabled(toggled_id == 1 and checked is True)
            form.interactable_widgets["rpb"].setEnabled(toggled_id == 1 and checked is True)

        form.interactable_widgets["parent_body"].idToggled.connect(adjust_form_for_system_type)
        # adjustment at start
        adjust_form_for_system_type(0, True)

        return form


def show_file_paths(parent_window):
    main_dir = get_main_dir()
    coil_table_file = main_dir.joinpath(app_settings.get_value("vc_table_file")).absolute()
    startup_state_file = main_dir.joinpath(app_settings.get_value("startup_state_file")).absolute()

    result_text = (f"#### Installation folder<br></br>{main_dir}"
                   "<br></br>  \n"
                   f"#### Coil wire definitions file<br></br>{coil_table_file}"
                   "<br></br>  \n"
                   f"#### Start-up state file<br></br>{startup_state_file}"
                   )

    popup = pwi.ResultTextBox("File paths",
                              result_text,
                              monospace=False,
                              parent=parent_window,
                              markdown=True,
                              )

    popup.exec()


class CurveExportMenu(qtw.QMenu):
    def __init__(self, curves, position, parent):
        super().__init__(parent=parent)
        for curve in curves:
            self.addAction(curve.get_full_name(), partial(export_and_beep ,curve, self.parent().signal_good_beep))
        self.popup(position)

def export_and_beep(curve, good_beeper):
    curve.export_to_clipboard(ppo = app_settings.get_value("export_ppo"), must_include_freq = app_settings.get_value("interpolate_must_contain_hz"))
    good_beeper.emit()

class SettingsDialog(qtw.QDialog):

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowModality(qtc.Qt.WindowModality.ApplicationModal)
        layout = qtw.QVBoxLayout(self)

        # ---- Form
        user_form = pwi.UserForm()
        layout.addWidget(user_form)

        # user_form.add_row(pwi.IntSpinBox("max_legend_size", "Limit the items that can be listed on the legend. Does not affect the shown curves in graph"),
        #                   "Nmax for graph legend")

        mpl_styles = [
            style_name for style_name in mpl.style.available if style_name[0] != "_"]
        user_form.add_row(pwi.ComboBox("matplotlib_style",
                                       "Style for the canvas. To see options, web search: 'matplotlib style sheets reference'",
                                       [(style_name, None)
                                        for style_name in mpl_styles],
                                       ),
                          "Matplotlib style",
                          )

        user_form.add_row(pwi.ComboBox("graph_grids",
                                       None,
                                       [("Style default", "default"),
                                        ("Major only", "major only"),
                                        ("Major and minor", "major and minor"),
                                        ],
                                       ),
                          "Graph grid view",
                          )

        user_form.add_row(pwi.SunkenLine())

        user_form.add_row(pwi.FloatSpinBox("A_beep",
                                           "Amplitude of the beep. Not in dB. 0 is off, 1 is maximum amplitude",
                                           min_max=(0, 1),
                                           ),
                          "Beep amplitude",
                          )

        user_form.add_row(pwi.SunkenLine())

        user_form.add_row(pwi.IntSpinBox("export_ppo",
                                         "Resolution of the exported curve in points per octave",
                                         min_max=(1, app_settings.get_value("calc_ppo")),
                                         ),
                          "Export curve resolution (ppo)",
                          )


        user_form.add_row(pwi.IntSpinBox("interpolate_must_contain_hz",
                                         "Frequency that will always be a point within interpolated frequency array."
                                         "\nDefault value: 1000",
                                         min_max=(1, 999999),
                                         ),
                          "Interpolate must contain frequency (Hz)",
                          )

        # ---- Buttons
        button_group = pwi.PushButtonGroup({"save": "Save",
                                            "cancel": "Cancel",
                                            },
                                           {},
                                           )
        button_group.buttons()["save_pushbutton"].setDefault(True)
        layout.addWidget(button_group)

        # ---- read values from settings
        all_app_settings = app_settings.get_all_as_dict()
        app_settings_in_form = {key: all_app_settings[key] for key in user_form.interactable_widgets.keys()}
        user_form.update_form_values(app_settings_in_form)

        # Connections
        button_group.buttons()["cancel_pushbutton"].clicked.connect(
            self.reject)
        button_group.buttons()["save_pushbutton"].clicked.connect(
            partial(self._save_and_close,  user_form))

    def _save_and_close(self, user_form):
        vals = user_form.get_form_values()
        if vals["matplotlib_style"]["current_text"] != app_settings.get_value("matplotlib_style"):
            message_box = qtw.QMessageBox(qtw.QMessageBox.Information,
                                          "Information",
                                          "Application needs to be restarted to be able to use the new Matplotlib style.",
                                          )
            message_box.setStandardButtons(
                qtw.QMessageBox.Cancel | qtw.QMessageBox.Ok)
            returned = message_box.exec()

            if returned == qtw.QMessageBox.Cancel:
                return

        for widget_name, value in vals.items():
            app_settings.set_value(widget_name, value, signal=False)

        app_settings.settings_changed.emit()
        self.accept()


def update_coil_options_combobox(combo_box: qtw.QComboBox, input_form_tabbed: InputSectionTabWidget, name_to_motor: dict):
    try:
        last_selected = (
            combo_box.currentData()["coil"]["wire"]["name"],
            len(combo_box.currentData()["coil"]["N_windings"]),
            )
    except (KeyError, AttributeError, TypeError):
        last_selected = (None, None)

    combo_box.clear()

    index_to_select = -1
    # Add the coils to the combobox (with their userData)
    for i, (name, motor) in enumerate(name_to_motor.items()):
        # Make a string for the text to show on the combo box
        combo_box.addItem(name, dataclasses.asdict(motor))
        if motor.coil.get_wire_name_and_layers() == last_selected:
            index_to_select = i

    combo_box.setCurrentIndex(index_to_select)

    # if nothing to add to combobox
    if combo_box.count() == 0:
        combo_box.addItem("--no solution found--")
    elif index_to_select == -1:  # means a new coil needs to be selected by user
        input_form_tabbed.setCurrentIndex(1)
        combo_box.showPopup()
