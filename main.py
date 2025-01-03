# Speaker Calculator - Loudspeaker design and calculations tool
# Copyright (C) 2024 - Kerem Basaran
# https://github.com/kbasaran
__email__ = "kbasaran@gmail.com"

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import sys
import json
import time
import dataclasses
from dataclasses import dataclass, fields

from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc
from PySide6 import QtGui as qtg

from generictools import signal_tools
from generictools.graphing_widget import MatplotlibWidget
import generictools.personalized_widgets as pwi
from version_convert import convert_v01_to_v02

import logging
from pathlib import Path
import matplotlib as mpl
import numpy as np
from functools import partial
import electroacoustical as ac
import pandas as pd

app_definitions = {"app_name": "Speaker Calculator",
                   "version": "0.2.0",
                   # "version": "Test build " + today.strftime("%Y.%m.%d"),
                   "description": "Loudspeaker design and calculations",
                   "copyright": "Copyright (C) 2024 Kerem Basaran",
                   "icon_path": str(Path("./images/logo.ico")),
                   "author": "Kerem Basaran",
                   "author_short": "kbasaran",
                   "email": "kbasaran@gmail.com",
                   "website": "https://github.com/kbasaran",
                   }


@dataclass
class Settings:
    """Settings will be stored in SI units"""
    global logger
    app_name: str = app_definitions["app_name"]
    author: str = app_definitions["author"]
    author_short: str = app_definitions["author_short"]
    version: str = app_definitions["version"]
    GAMMA: float = 1.401  # adiabatic index of air
    P0: int = 101325  # atmospheric pressure
    RHO: float = 1.1839  # density of air at 25 degrees celcius
    Kair: float = 101325. * RHO
    c_air: float = (P0 * GAMMA / RHO)**0.5
    vc_table_file = str(Path.cwd().joinpath('SSC_data', 'WIRE_TABLE.csv'))
    f_min: int = 10
    f_max: int = 3000
    A_beep: int = 0.25
    last_used_folder: str = str(Path.home())
    show_legend: bool = True
    max_legend_size: int = 10
    matplotlib_style: str = "bmh"
    graph_grids: str = "default"

    def __post_init__(self):
        settings_storage_title = (self.app_name
                                  + " - "
                                  + (self.version.split(".")[0] if "." in self.version else "")
                                  )
        self.settings_sys = qtc.QSettings(self.author_short, settings_storage_title)
        logger.debug(f"Settings will be stored in '{self.author_short}', '{settings_storage_title}'")
        self.read_all_from_system()

    def update(self, attr_name, new_val):
        # update a given setting
        assert type(getattr(self, attr_name)) == type(new_val)
        setattr(self, attr_name, new_val)
        self.settings_sys.setValue(attr_name, getattr(self, attr_name))

    def write_all_to_system(self):
        for field in fields(self):
            self.settings_sys.setValue(field.name, getattr(self, field.name))

    def read_all_from_system(self):
        for field in fields(self):
            setattr(self, field.name, self.settings_sys.value(
                field.name, field.default, type=type(field.default)))

    def as_dict(self):  # better use asdict method from dataclasses instead of this
        # return the settings as a dict
        settings = {}
        for field in fields(self):
            settings[field] = getattr(self, field.name)
        return settings

    def __repr__(self):
        return str(self.as_dict())


class InputSectionTabWidget(qtw.QTabWidget):
    # additional signals that this widget can publish
    signal_good_beep = qtc.Signal()
    signal_bad_beep = qtc.Signal()

    def __init__(self):
        super().__init__()
        forms = {}
        forms["General"] = self._make_form_for_general_tab()
        forms["Motor"] = self._make_form_for_motor_tab()
        forms["Enclosure"] = self._make_form_for_enclosure_tab()
        forms["System"] = self._make_form_for_system_tab()

        self.interactable_widgets = {}
        for name, form in forms.items():
            self.addTab(form, name)
            self.interactable_widgets = {**self.interactable_widgets, **form.interactable_widgets}

    def _make_form_for_general_tab(self):
        form = pwi.UserForm()

        # ---- General specs
        form.add_row(pwi.Title("General specifications"))

        form.add_row(pwi.FloatSpinBox("fs", "Resonance frequency (undamped natural frequency) of the speaker in free-air condition",
                                      decimals=1,
                                      min_max=(0.1, None),
                                      ),
                     description="f<sub>s</sub> (Hz)",
                     )

        form.add_row(pwi.FloatSpinBox("Qms", "Quality factor of speaker, only the mechanical part",
                                      ),
                     description="Q<sub>ms</sub>",
                     )

        form.add_row(pwi.FloatSpinBox("Xpeak", "Peak excursion allowed, one way",
                                      coeff_for_SI=1e-3,
                                      ),
                     description="X<sub>peak</sub> (mm)",
                     )

        form.add_row(pwi.FloatSpinBox("dead_mass", "Moving mass excluding the coil itform and the air.|n(Dead mass = Mmd - coil mass)",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Dead mass (g)",
                     )

        form.add_row(pwi.FloatSpinBox("Sd", "Diaphragm effective surface area",
                                      coeff_for_SI=1e-4,
                                      min_max=(0, None),
                                      ),
                     description="S<sub>d</sub> (cm²)"
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

        form.add_row(pwi.FloatSpinBox("excitation_value", "The value for input excitation, in units chosen above",
                                      ),
                     description="Excitation value",
                     )

        form.add_row(pwi.FloatSpinBox("Rnom", "Nominal impedance of the speaker. This is necessary to calculate the voltage input"
                                      "\nwhen 'Watts @Rnom' is selected as the input excitation unit.",
                                      ),
                     description="Nominal impedance",
                     )

        form.add_row(pwi.FloatSpinBox("R_serial",
                                      "The resistance between the speaker terminal and the voltage source."
                                      "\nMay be due to cables, connectors, amplifier etc."
                                      "\nCauses resistive loss before arrival at the speaker terminals.",
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
        form.add_row(pwi.ComboBox("motor_spec_type", "Choose which parameters you want to input to make the motor strength calculation",
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

        form.add_row(pwi.FloatSpinBox("target_Re", "Re value that needs to be approached while calculating an appropriate coil and winding",
                                      ),
                     description="Target R<sub>e</sub> (ohm)",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.FloatSpinBox("former_ID", "Internal diameter of the coil former",
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Coil Former ID (mm)",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.IntSpinBox("t_former", "Thickness of the coil former",
                                    coeff_for_SI=1e-6,
                                      min_max=(0, None)
                                    ),
                     description="Former thickness (\u03BCm)",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.FloatSpinBox("h_winding_target", "Desired height of the coil winding",
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Target winding height (mm)",
                     into_form=motor_definition_p1,
                     )


        form.add_row(pwi.FloatSpinBox("B_average", "Average B field across the coil windings."
                                      "\nNeeds to be calculated separately and input here.",
                                      decimals=3,
                                      coeff_for_SI=1,
                                      min_max=(0, None),
                                      ),
                     description="Average B field on coil (T)",
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
                                      "\nE.g. if this is set to 0.8 and the wire nominal thickness is 1mm"
                                      "\nnominal thickness of windings that are 1,2,3 layers will be"
                                      "\n1mm,1.8mm,2.6mm, respectively."
                                      "\nFor stacking of ideal circular wires this value is 'sin(60)=0.5'"
                                      "\nHas no effect on the total height of the winding."
                                      "\nBut if it is 0.9 or less, each layer will have one less winding then the previous.",
                                      min_max=(0, 1),
                                      ),
                     description="Stacking coeff. for additional layers",
                     into_form=motor_definition_p1,
                     )
        form.interactable_widgets["w_stacking_coef"].setValue(1)

        form.add_row(pwi.FloatSpinBox("Rs_leadwire",
                                      "Resistance between the coil and the speaker terminals, e.g. leadwire",
                                      min_max=(0, None),
                                      # took the automatically assigned maximum from another widget
                                      # instead of typing n an arbitrary number
                                      # 'None' was not expected by the underlying 'setRange' method
                                      ),
                     description="Leadwire resistance (ohm)",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.FloatSpinBox("reduce_per_layer",
                                    ("Reduce the number of windings on each layer by this number."
                                     "\nFor round coils suggested value is 1.5. For rectangular coils suggested value is 0.5."),
                                      min_max=(0, None),
                                      decimals=1,
                                    ),
                     description="Reduce windings per layer",
                     into_form=motor_definition_p1,
                     )


        update_coil_choices_button = pwi.PushButton("update_coil_choices",
                                                    "Update coil choices",
                                                    tooltip="Populate the below dropdown with possible coil choices for the given parameters",
                                                    )

        # update_coil_choices_button.setMinimumHeight(32)  # maybe make relative to the height of the dropdown boxes? e.g. 1.5x?
        form.add_row(update_coil_choices_button,
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.ComboBox("coil_options", "Select coil winding to be used for calculations",
                                  [],
                                  ),
                     into_form=motor_definition_p1,
                     )

        # ---- Second page: "Define Bl, Re, Mmd"
        motor_definition_p2 = pwi.SubForm()
        form.motor_definition_stacked.addWidget(motor_definition_p2)

        form.add_row(pwi.FloatSpinBox("Bl_p2", "Force factor",
                                      ),
                     description="Bl (Tm)",
                     into_form=motor_definition_p2,
                     )

        form.add_row(pwi.FloatSpinBox("Re_p2", "DC resistance",
                                    ),
                     description="R<sub>e</sub> (ohm)",
                     into_form=motor_definition_p2,
                     )

        form.add_row(pwi.FloatSpinBox("Mmd_p2",
                                      "Moving mass, excluding coupled air mass",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="M<sub>md</sub> (g)",
                     into_form=motor_definition_p2,
                     )

        # ---- Third page: "Define Bl, Re, Mms"
        motor_definition_p3 = pwi.SubForm()
        form.motor_definition_stacked.addWidget(motor_definition_p3)

        form.add_row(pwi.FloatSpinBox("Bl_p3",
                                      "Force factor",
                                      ),
                     description="Bl (Tm)",
                     into_form=motor_definition_p3,
                     )

        form.add_row(pwi.FloatSpinBox("Re_p3",
                                    "DC resistance",
                                    ),
                     description="R<sub>e</sub> (ohm)",
                     into_form=motor_definition_p3,
                     )

        form.add_row(pwi.FloatSpinBox("Mms_p3",
                                      "Moving mass, including coupled air mass",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="M<sub>ms</sub> (g)",
                     into_form=motor_definition_p3,
                     )

        # ---- Mechanical specs
        form.add_row(pwi.SunkenLine())

        form.add_row(pwi.Title("Motor mechanical specifications"))

        form.add_row(pwi.FloatSpinBox("h_top_plate", "Thickness of the top plate",
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Top plate thickness (mm)",
                     )

        form.add_row(pwi.IntSpinBox("airgap_clearance_inner", "Clearance on the inner side of the coil former",
                                    coeff_for_SI=1e-6,
                                    ),
                     description="Airgap inner clearance (\u03BCm)",
                     )

        form.add_row(pwi.IntSpinBox("airgap_clearance_outer", "Clearance on the outer side of the coil windings",
                                    coeff_for_SI=1e-6,
                                    ),
                     description="Airgap outer clearance (\u03BCm)",
                     )

        form.add_row(pwi.FloatSpinBox("h_former_under_coil", "Extension of the coil former below the coil windings",
                                      coeff_for_SI=1e-3,
                                      min_max=(0, None),
                                      ),
                     description="Former bottom ext. (mm)",
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

        form.interactable_widgets["motor_spec_type"].currentIndexChanged.connect(adjust_form_for_calc_type)
        # adjustment at start -- not necessary because it starts all enabled from and in tab 1
        # adjust_form_for_calc_type(form.interactable_widgets["motor_spec_type"].currentIndex())

        return form

    def _make_form_for_enclosure_tab(form):
        form = pwi.UserForm()

        # ---- Enclosure type
        form.add_row(pwi.Title("Enclosure type"))

        box_type_choice_buttons = pwi.ChoiceButtonGroup("box_type",
                                                        {0: "Free-air", 1: "Closed box"},
                                                        {0: "Speaker assumed to be on an infinite baffle, with no acoustical loading on either side",
                                                         1: "Speaker rear side coupled to a lossy sealed box.",
                                                         },
                                                        vertical=False,
                                                        )
        box_type_choice_buttons.layout().setContentsMargins(0, 0, 0, 0)
        form.add_row(box_type_choice_buttons)

        # ---- Closed box specs
        form.add_row(pwi.SunkenLine())

        form.add_row(pwi.Title("Closed box specifications"))

        form.add_row(pwi.FloatSpinBox("Vb", "Internal netto volume filled by air",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Box internal volume (l)",
                     )

        form.add_row(pwi.FloatSpinBox("Qa", "Quality factor of the speaker resulting from absorption losses inside the box."
                                      + "\n**This value also affects effective box volume: 'Vba = Vb * (0.94 / Qa + 1)'**",
                                      decimals=1,
                                      min_max=(0.1, None),
                                      ),
                     description="Q<sub>a</sub> - box absorption",
                     )

        form.add_row(pwi.FloatSpinBox("Ql", "Quality factor of the speaker resulting from leakage losses of box",
                                      decimals=1,
                                      min_max=(0.1, None),
                                      ),
                     description="Q<sub>l</sub> - box losses",
                     )


        # ---- Form logic
        def adjust_form_for_enclosure_type(toggled_id, checked):
            form.interactable_widgets["Vb"].setEnabled(toggled_id == 1 and checked is True)
            form.interactable_widgets["Qa"].setEnabled(toggled_id == 1 and checked is True)
            form.interactable_widgets["Ql"].setEnabled(toggled_id == 1 and checked is True)

        form.interactable_widgets["box_type"].idToggled.connect(adjust_form_for_enclosure_type)
        # adjustment at start
        adjust_form_for_enclosure_type(0, True)

        return form

    def _make_form_for_system_tab(form):
        form = pwi.UserForm()

        # ---- System type
        form.add_row(pwi.Title("Parent body"))

        dof_choice_buttons = pwi.ChoiceButtonGroup("parent_body",
                                                   {0: "Rigid", 1: "Mobile"},
                                                   {0: "1 degree of freedom - only the loudspeaker moving mass has mobility.",
                                                       1: "2 degrees of freedom - loudspeaker moving mass is attached to a parent lump mass that also has mobility."},
                                                   vertical=False,
                                                   )
        dof_choice_buttons.layout().setContentsMargins(0, 0, 0, 0)
        form.add_row(dof_choice_buttons)

        # ---- Parent body

        form.add_row(pwi.FloatSpinBox("m2", "Mass of the parent body",
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Mass (g)",
                     )

        form.add_row(pwi.FloatSpinBox("k2", "Stiffness between the parent body and the reference frame",
                                      coeff_for_SI=1e3,
                                      ),
                     description="Stiffness (N/mm)",
                     )


        form.add_row(pwi.FloatSpinBox("c2", "Damping coefficient between the parent body and the reference frame",
                                      ),
                     description="Damping coefficient (kg/s)",
                     )
        
        # ---- Form logic
        def adjust_form_for_system_type(toggled_id, checked):
            form.interactable_widgets["k2"].setEnabled(toggled_id == 1 and checked is True)
            form.interactable_widgets["m2"].setEnabled(toggled_id == 1 and checked is True)
            form.interactable_widgets["c2"].setEnabled(toggled_id == 1 and checked is True)

        form.interactable_widgets["parent_body"].idToggled.connect(adjust_form_for_system_type)
        # adjustment at start
        adjust_form_for_system_type(0, True)

        return form


class MainWindow(qtw.QMainWindow):
    global settings
    # these are signals that this object emits.
    # they will be triggered by the functions and the widgets in this object.
    signal_new_window = qtc.Signal(dict)  # new_window with kwargs as widget values
    signal_good_beep = qtc.Signal()
    signal_bad_beep = qtc.Signal()
    signal_user_settings_changed = qtc.Signal()  # settings from  menu bar changed, such as graph type

    def __init__(self, sound_engine, user_form_dict=None, open_user_file=None):
        super().__init__()
        self.setWindowTitle(app_definitions["app_name"])
        self._create_menu_bar()
        self._create_widgets()
        self._place_widgets()
        self._connect_widgets()
        # self._add_status_bar()
        if user_form_dict:
            self.set_state(user_form_dict)
        elif open_user_file:
            self.load_state_from_file(open_user_file)
        self._update_model_button_clicked()

    def _create_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        new_window_action = file_menu.addAction("New window", self.duplicate_window)
        load_action = file_menu.addAction("Load state..", self.load_state_from_file)
        save_action = file_menu.addAction("Save state..", self.save_state_to_file)

        edit_menu = menu_bar.addMenu("Edit")
        settings_action = edit_menu.addAction("Settings..", self.open_settings_dialog)

        help_menu = menu_bar.addMenu("Help")
        about_action = help_menu.addAction("About", self.open_about_menu)

    def _create_widgets(self):
        # ---- Left hand side (input form)
        self.input_form = InputSectionTabWidget()
        # connect its signals
        self.input_form.signal_good_beep.connect(self.signal_good_beep)
        self.input_form.signal_bad_beep.connect(self.signal_bad_beep)

        # ---- Right hand side (graph etc.)
        self._rh_widget = qtw.QWidget()

        # Graph
        self.graph = MatplotlibWidget(settings, layout_engine="tight")
        self.graph_data_choice = pwi.ChoiceButtonGroup("graph_data_choice",
                                                       
                                                       {0: "SPL",
                                                        1: "Impedance",
                                                        2: "Displacements",
                                                        3: "Relative",
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
        self.graph_data_choice.buttons()[3].setEnabled(False)  # the relative button is disabled at start

        self.graph_pushbuttons = pwi.PushButtonGroup({"update_results": "Update results",
                                                   "export_curve": "Export curve",
                                                   "export_quick": "Quick export",
                                                   "import_curve": "Import curve",
                                                   "remove_curve": "Remove curve",
                                                   },
                                                  {"update_results": "Update calculated values. Click this each time you modify the user form.",
                                                   "export_curve": "Open export menu",
                                                   "export_quick": "Quick export using latest settings",
                                                   "import_curve": "Open import menu",
                                                   "remove_curve": "Open remove curves menu",
                                                   },
                                                  )

        # Make buttons under the graph larger
        for button in self.graph_pushbuttons.buttons().values():
            font_pixel_size = button.font().pixelSize()
            button.setMinimumHeight(48)

            # temporary disable, to be decided later
            if button.text() != "Update results":
                button.setEnabled(False)

        # Text boxes
        self.results_textbox = qtw.QTextEdit()
        self.results_textbox.setReadOnly(True)
        self.notes_textbox = qtw.QPlainTextEdit()
        self.textboxes_layout = qtw.QHBoxLayout()

        results_section = self.results_textbox
        results_section.setSizePolicy(
            qtw.QSizePolicy.Minimum, qtw.QSizePolicy.MinimumExpanding)
        results_section.setMinimumWidth(350)


        notes_section = qtw.QWidget()
        notes_section_layout = qtw.QVBoxLayout(notes_section)
        notes_section_layout.setContentsMargins(-1, 0, -1, 0)
        notes_section_layout.addWidget(qtw.QLabel("Notes"))
        notes_section_layout.addWidget(self.notes_textbox)
        notes_section.setSizePolicy(
            qtw.QSizePolicy.MinimumExpanding, qtw.QSizePolicy.MinimumExpanding)


        self.textboxes_layout.addWidget(results_section)
        self.textboxes_layout.addWidget(notes_section)

    def _place_widgets(self):
        # ---- Make center widget
        self._center_widget = qtw.QWidget()
        self._center_layout = qtw.QHBoxLayout(self._center_widget)
        self.setCentralWidget(self._center_widget)

        # ---- Make left hand side
        lh_layout = qtw.QVBoxLayout()
        lh_layout.addWidget(self.input_form)

        self.input_form.setSizePolicy(
            qtw.QSizePolicy.Minimum, qtw.QSizePolicy.Minimum)
        self._center_layout.addLayout(lh_layout)

        # ---- Make right hand group
        self._center_layout.addWidget(self._rh_widget)
        self._rh_layout = qtw.QVBoxLayout(self._rh_widget)
        self._rh_layout.setContentsMargins(-1, 0, -1, 0)

        self._rh_layout.addWidget(self.graph, 3)
        self.graph.setSizePolicy(
            qtw.QSizePolicy.Expanding, qtw.QSizePolicy.Expanding)

        self._rh_layout.addWidget(self.graph_data_choice)
        self._rh_layout.addWidget(self.graph_pushbuttons)
        self.graph_data_choice.layout().setContentsMargins(-1, 0, -1, 0)
        self._rh_layout.addLayout(self.textboxes_layout, 2)

    def _connect_widgets(self):
        self.input_form.interactable_widgets["update_coil_choices"]\
            .clicked.connect(self.update_coil_choices_button_clicked)
        self.graph_pushbuttons.buttons()["update_results_pushbutton"]\
            .clicked.connect(self._update_model_button_clicked)
        for button in self.graph_data_choice.buttons():
            button_id = self.graph_data_choice.button_group.id(button)
            button.pressed.connect(lambda arg1=button_id: self.update_graph(arg1))
        
        # disable the relative plots
        self.input_form.interactable_widgets["parent_body"].buttons()[1].toggled.connect(
            self.graph_data_choice.buttons()[3].setEnabled)
        
    def _add_status_bar(self):
        self.setStatusBar(qtw.QStatusBar())
        self.statusBar().showMessage("Test", 2000)

    def get_state(self):
        logger.debug("Get states initiated.")
        state = {}
        tab_widgets = [self.input_form.widget(i) for i in range(self.input_form.count())]
        for input_form_widget in tab_widgets:
            state = {**state, **input_form_widget.get_form_values()}
        
        state["user_notes"] = self.notes_textbox.toPlainText()

        return state

    def save_state_to_file(self, state=None):
        global app_definitions
        path_unverified = qtw.QFileDialog.getSaveFileName(self, caption='Save parameters to a file..',
                                                          dir=settings.last_used_folder,
                                                          filter='Speaker calculator files (*.scf)',
                                                          )

        try:
            file_raw = path_unverified[0]
            if file_raw:
                file = Path(file_raw + ".scf" if file_raw[-4:] != ".scf" else file_raw)
                # filter not working as expected, saves files without file extension scf
                # therefore above logic
                assert file.parent.is_dir()
            else:
                return  # empty file_raw. means nothing was selected, so pick file is canceled.
        except:
            # Path object could not be created
            raise NotADirectoryError(file_raw)
        
        # if you reached here, file is ready as Path object

        settings.update("last_used_folder", str(file.parent))

        if state is None:
            state = self.get_state()
        state["application_data"] = app_definitions

        json_string = json.dumps(state, indent=4)
        with open(file, "wt") as f:
            f.write(json_string)

        self.signal_good_beep.emit()

    def load_state_from_file(self, file: Path = None):
        # no file is provided as argumnent
        # raise a file selection menu
        if file is None:
            path_unverified = qtw.QFileDialog.getOpenFileName(self, caption='Open parameters from a save file..',
                                                              dir=settings.last_used_folder,
                                                              filter='Speaker calculator files (*.scf *.sscf)',
                                                              )

            if file_raw := path_unverified[0]:
                file = Path(file_raw)
            else:
                return  # canceled file select

        # file provided as argumnent
        # Check if argument file exists
        elif not file.is_file():
                raise FileNotFoundError(file)

        # file is ready as Path object at this point

        logger.info(f"Loading file '{file.name}'")
        settings.update("last_used_folder", str(file.parent))

        # backwards compatibility with v0.1
        suffix = file.suffixes[-1]
        if suffix == ".sscf":
            state = convert_v01_to_v02(file)
            self.set_state(state)
            
        elif suffix == ".scf":
            with open(file, "rt") as f:
                state = json.load(f)
            self.set_state(state)
        else:
            raise ValueError(f"Invalid suffix '{suffix}'")

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

        self.notes_textbox.setPlainText(state.get("user_notes", "Error: User notes could not be loaded."))

        self.signal_good_beep.emit()

    def duplicate_window(self):
        self.signal_new_window.emit(
            {"user_form_dict": self.get_state()})

    def open_settings_dialog(self):
        settings_dialog = SettingsDialog(parent=self)
        settings_dialog.signal_settings_changed.connect(
            self._settings_dialog_return)

        return_value = settings_dialog.exec()
        # What does it return normally?
        if return_value:
            pass

    def _settings_dialog_return(self):
        self.signal_user_settings_changed.emit()
        self.graph.update_figure(recalculate_limits=False)
        self.signal_good_beep.emit()

    def open_about_menu(self):
        result_text = "\n".join([
            "Speaker Calculator - Loudspeaker design and calculations tool",
            f"Version: {app_definitions['version']}",
            "",
            f"{app_definitions['copyright']}",
            f"{app_definitions['website']}",
            f"{app_definitions['email']}",
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
        message_box = qtw.QMessageBox(qtw.QMessageBox.Information,
                                      "Feature not Implemented",
                                      )
        message_box.setStandardButtons(qtw.QMessageBox.Ok)
        message_box.exec()
    
    def update_coil_choices_button_clicked(self):
        name_to_motor = find_feasible_coils(self.get_state(), wires)
        update_coil_options_combobox(self, self.input_form.interactable_widgets["coil_options"], name_to_motor)

    def _update_model_button_clicked(self):
        self.results_textbox.clear()
        try:
            vals = self.get_state()
            speaker_driver = construct_SpeakerDriver(vals)
            spk_sys = self.speaker_model_state["system"] if hasattr(self, "speaker_model_state") else None
            speaker_system = build_or_update_SpeakerSystem(vals, speaker_driver, spk_sys)
            V_source = ac.calculate_voltage(vals["excitation_value"],
                                            vals["excitation_type"]["current_data"],
                                            Re=speaker_driver.Re,
                                            Rnom=vals["Rnom"],
                                            )

            self.speaker_model_state = {"vals": vals,
                                        "driver": speaker_driver,
                                        "system": speaker_system,
                                        "V_source": V_source,
                                        }
            
            self.update_all_results()
            self.signal_good_beep.emit()
        except KeyError as e:
            logger.debug(e)
            self.results_textbox.setPlainText("Update failed.\nSee log for more details.")
            self.signal_bad_beep.emit()

    def update_graph(self, checked_id):
        self.graph.clear_graph()

        if not hasattr(self, "speaker_model_state"):
            self.signal_bad_beep.emit()
            return
        else:
            spk_sys, V_source = self.speaker_model_state["system"], self.speaker_model_state["V_source"]

        curves = dict()
        freqs = signal_tools.generate_log_spaced_freq_list(10, 1500, 48*8)
        R_spk = spk_sys.speaker.Re
        W_spk = (V_source / spk_sys.R_sys * R_spk)**2 / R_spk

        if checked_id == 0:

            if spk_sys.speaker.Sd > 0:  # speaker
                velocs = spk_sys.get_velocities(V_source, freqs)
                w = 2 * np.pi * freqs
                Xmax_limited_velocities = spk_sys.speaker.Xpeak / 2**0.5 * (1j * w)

                _, SPL = ac.calculate_SPL(settings,
                                          (freqs, velocs["Diaphragm, RMS, absolute"]),
                                          spk_sys.speaker.Sd,
                                          )

                _, SPL_Xmax_limited = ac.calculate_SPL(settings,
                                                       (freqs, Xmax_limited_velocities),
                                                       spk_sys.speaker.Sd,
                                                       )
    
                curves.update({"SPL piston mode": SPL,
                               "SPL piston mode, Xpeak limited": SPL_Xmax_limited,
                               })

                self.graph.set_y_limits_policy("SPL")
                self.graph.set_title(f"SPL@1m, Half-space, {V_source:.4g} Volt, {W_spk:.3g} Watt@Re")
                self.graph.ax.set_ylabel("dBSPL")

            elif spk_sys.speaker.Sd == 0:  # shaker or other with no diaphragm
                accs = spk_sys.get_accelerations(V_source, freqs)
              
                curves.update({key.replace("Diaphragm", "Moving mass"): 20*np.log10(np.abs(acc)/1e-6) \
                               for key, acc in accs.items() if "relative" not in key})
                
                self.graph.set_y_limits_policy("SPL")
                self.graph.set_title(f"Acceleration, {V_source:.4g} Volt, {W_spk:.3g} Watt@Re")
                self.graph.ax.set_ylabel(r"dB ref. $\mathregular{10^{-6}}$ m/s²")

        elif checked_id == 1:
            curves.update({key: np.abs(val) for key, val in spk_sys.get_Z(freqs).items()})
            self.graph.set_y_limits_policy("impedance")
            self.graph.set_title("Electrical impedance - no inductance")
            self.graph.ax.set_ylabel("ohm")

        elif checked_id == 2:
            for key, val in spk_sys.get_displacements(V_source, freqs).items():
                if "absolute" in key: 
                    curves[key] = np.abs(val)

            self.graph.set_y_limits_policy(None)
            self.graph.set_title("Displacements")
            self.graph.ax.set_ylabel("mm")

        elif checked_id == 3:
            for key, val in spk_sys.get_displacements(V_source, freqs).items():
                if "relative" in key: 
                    curves[key] = np.abs(val)

            self.graph.set_y_limits_policy(None)
            self.graph.set_title("Displacements")
            self.graph.ax.set_ylabel("mm")

        elif checked_id == 4:
            curves.update({key: np.abs(val) for key, val in spk_sys.get_forces(V_source, freqs).items()})
            self.graph.set_y_limits_policy(None)
            self.graph.set_title("Forces")
            self.graph.ax.set_ylabel("N")
            
        elif checked_id == 5:
            curves.update({key: np.abs(val) for key, val in spk_sys.get_velocities(V_source, freqs).items()})
            self.graph.set_y_limits_policy(None)
            self.graph.set_title("Velocities")
            self.graph.ax.set_ylabel("m/s")

        elif checked_id == 6:
            curves.update(spk_sys.get_phases(freqs).items())
            self.graph.set_y_limits_policy("phase")
            self.graph.set_title("Phase, displacements")
            self.graph.ax.set_ylabel("degrees")

        else:
            raise ValueError(f"Checked id not recognized: {type(checked_id), checked_id}")

        if "curves" in locals():
            for i, (name, y) in enumerate(curves.items()):
                self.graph.add_line2d(i, name, (freqs, y))
        
    def update_all_results(self):
        checked_id = self.graph_data_choice.button_group.checkedId()
        self.update_graph(checked_id)
        summary_all = self.speaker_model_state["system"].get_summary()
        self.results_textbox.setMarkdown(summary_all)
        

class SettingsDialog(qtw.QDialog):
    global settings
    signal_settings_changed = qtc.Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowModality(qtc.Qt.WindowModality.ApplicationModal)
        layout = qtw.QVBoxLayout(self)

        # ---- Form
        user_form = pwi.UserForm()
        layout.addWidget(user_form)

        user_form.add_row(pwi.CheckBox("show_legend", "Show legend on the graph"),
                          "Show legend")

        user_form.add_row(pwi.IntSpinBox("max_legend_size", "Limit the items that can be listed on the legend. Does not affect the shown curves in graph"),
                          "Nmax for graph legend")

        mpl_styles = [
            style_name for style_name in mpl.style.available if style_name[0] != "_"]
        user_form.add_row(pwi.ComboBox("matplotlib_style",
                                       "Style for the canvas. To see options, web search: 'matplotlib style sheets reference'",
                                       [(style_name, style_name)
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

        # ---- Buttons
        button_group = pwi.PushButtonGroup({"save": "Save",
                                            "cancel": "Cancel",
                                            },
                                           {},
                                           )
        button_group.buttons()["save_pushbutton"].setDefault(True)
        layout.addWidget(button_group)

        # ---- read values from settings
        for widget_name, widget in user_form.interactable_widgets.items():
            saved_setting = getattr(settings, widget_name)
            if isinstance(widget, qtw.QCheckBox):
                widget.setChecked(saved_setting)

            elif widget_name == "matplotlib_style":
                try:
                    index_from_settings = mpl_styles.index(saved_setting)
                except IndexError:
                    index_from_settings = 0
                widget.setCurrentIndex(index_from_settings)

            elif widget_name == "graph_grids":
                try:
                    index_from_settings = [widget.itemData(i) for i in range(
                        widget.count())].index(settings.graph_grids)
                except IndexError:
                    index_from_settings = 0
                widget.setCurrentIndex(index_from_settings)

            else:
                widget.setValue(saved_setting)

        # Connections
        button_group.buttons()["cancel_pushbutton"].clicked.connect(
            self.reject)
        button_group.buttons()["save_pushbutton"].clicked.connect(
            partial(self._save_and_close,  user_form.interactable_widgets))

    def _save_and_close(self, user_input_widgets):
        mpl_styles = [
            style_name for style_name in mpl.style.available if style_name[0] != "_"]
        if user_input_widgets["matplotlib_style"].currentIndex() != mpl_styles.index(settings.matplotlib_style):
            message_box = qtw.QMessageBox(qtw.QMessageBox.Information,
                                          "Information",
                                          "Application needs to be restarted to be able to use the new Matplotlib style.",
                                          )
            message_box.setStandardButtons(
                qtw.QMessageBox.Cancel | qtw.QMessageBox.Ok)
            returned = message_box.exec()

            if returned == qtw.QMessageBox.Cancel:
                return

        for widget_name, widget in user_input_widgets.items():
            if isinstance(widget, qtw.QCheckBox):
                settings.update(widget_name, widget.isChecked())
            elif widget_name == "matplotlib_style":
                settings.update(widget_name, widget.currentData())
            elif widget_name == "graph_grids":
                settings.update(widget_name, widget.currentData())
            else:
                settings.update(widget_name, widget.value())
        self.signal_settings_changed.emit()
        self.accept()


def read_wire_table(wire_table_file: Path) -> pd.DataFrame:
    if not wire_table_file.exists():
        raise FileNotFoundError(f"Wire table file not found: {Path}")
    imported_wire_table = pd.read_excel(wire_table_file, "Sheet1", skiprows=range(2), index_col=0)
    coeff_for_SI = {
        "nominal_size": 1e-6,
        "w_avg": 1e-6,
        "h_avg": 1e-6,
        "w_max": 1e-6,
        "nominal_size": 1e-6,
        "mass_density": 1e-3,
        }
    for key, coeff in coeff_for_SI.items():
        imported_wire_table[key] = coeff * imported_wire_table[key]
    if not imported_wire_table.index.is_unique:
        raise IndexError("Wire names in the imported table are not unique.")
    
    wires_as_dict = dict()
    for wire_name, columns_data_as_series in imported_wire_table.iterrows():
        wires_as_dict[wire_name] = ac.Wire(name=wire_name, **columns_data_as_series.to_dict())

    return wires_as_dict


def find_feasible_coils(vals, wires):
    """Scan best matching speaker coil options."""
    try:  # try to read the N_layer_options string
        layer_options = [int(str) for str in vals["N_layer_options"].replace(" ", "").split(",")]
        if not layer_options:
            raise ValueError("At least one option needs to be provided for number of winding layers.")
    except Exception:
        raise ValueError("Invalid input in number of layer options")

    # Make a dataframe to store viable winding options
    # table_columns = ["name", "wire", "N_layers", "Bl", "Re", "Lm", "Qts", "carrier_OD",
    #                  "h_winding", "N_windings", "total_wire_length", "coil_w_max", "coil_mass", "coil"]
    # coil_options_table = pd.DataFrame(columns=table_columns, indexcol="name")
    speaker_options = []

    for N_layers in layer_options:
        for wire_name, wire in wires.items():
            try:
                coil = ac.wind_coil(wire,
                                    N_layers,
                                    vals["w_stacking_coef"],
                                    vals["former_ID"] + 2 * vals["t_former"],  # carrier_OD
                                    vals["h_winding_target"],
                                    vals["reduce_per_layer"],
                                    )
            except ValueError as e:
                logger.debug(f"Could not wind coil for {wire_name}: {e}")
                continue

            if vals["target_Re"] / 1.15 < coil.Re < vals["target_Re"] * 1.2:
                motor = ac.Motor(coil,
                                 vals["B_average"],
                                 h_top_plate=vals["h_top_plate"],
                                 airgap_clearance_inner=vals["airgap_clearance_inner"],
                                 airgap_clearance_outer=vals["airgap_clearance_outer"],
                                 h_former_under_coil=vals["h_former_under_coil"],
                                 )
                speaker = ac.SpeakerDriver(settings,
                                           vals["fs"],
                                           vals["Sd"],
                                           vals["Qms"],
                                           motor=motor,
                                           dead_mass=vals["dead_mass"],
                                           Rs=vals["Rs_leadwire"],
                                           )
                speaker_options.append(speaker)

    # Sort the viable coil options
    speaker_options.sort(key=lambda x: x.Lm, reverse=True)
    name_to_motor = dict()
    for speaker in speaker_options:
        name = speaker.motor.coil.name + f" -> Re={speaker.Re:.2f}, Lm={speaker.Lm:.2f}, Qts={speaker.Qts:.2f}"
        name_to_motor[name] = dataclasses.asdict(speaker.motor)
    
    return name_to_motor  # keys: friendly name values: motor object as a dictionary. contains coil and wire in it.
            

def update_coil_options_combobox(mw: MainWindow, combo_box: qtw.QComboBox, name_to_motor: dict):
    combo_box.clear()
    # Add the coils to the combobox (with their userData)
    for name, motor_as_dict in name_to_motor.items():
        # Make a string for the text to show on the combo box
        combo_box.addItem(name, motor_as_dict)
    
    # if nothing to add to combobox
    if combo_box.count() == 0:
        mw.signal_bad_beep.emit()
        combo_box.addItem("--no solution found--")
    
    else:
        mw.signal_good_beep.emit()


def construct_SpeakerDriver(vals) -> ac.SpeakerSystem:
    "Create the loudspeaker model based on the values provided in the widget."
    global wires, logger
    motor_spec_type = vals["motor_spec_type"]["current_data"]

    if motor_spec_type == "define_coil":
        try:
            motor_as_dict = vals["coil_options"]["current_data"]
            logging.debug(f"Motor object will be built from dict: {motor_as_dict}")
            wire_as_dict = motor_as_dict["coil"]["wire"]
            wire = ac.Wire(**wire_as_dict)

            coil_as_dict = motor_as_dict["coil"]
            coil_as_dict["wire"] = wire
            coil = ac.Coil(**coil_as_dict)

            motor_as_dict["coil"] = coil
            motor = ac.Motor(**motor_as_dict)


        except AttributeError:  # doesn't have motor attribute
            raise RuntimeError("Invalid motor object in coil options combobox")
        speaker_driver = ac.SpeakerDriver(settings,
                                          fs=vals["fs"],
                                          Sd=vals["Sd"],
                                          Qms=vals["Qms"],

                                          motor=motor,
                                          dead_mass=vals["dead_mass"],

                                          Rs=vals["Rs_leadwire"],
                                          Xpeak=vals["Xpeak"],
                                          )
        
    elif motor_spec_type == "define_Bl_Re_Mmd":
        speaker_driver = ac.SpeakerDriver(settings,
                                          fs=vals["fs"],
                                          Sd=vals["Sd"],
                                          Qms=vals["Qms"],

                                          Bl=vals["Bl_p2"],
                                          Re=vals["Re_p2"],
                                          Mmd=vals["Mmd_p2"],

                                          Xpeak=vals["Xpeak"],
                                          )
        
    elif motor_spec_type == "define_Bl_Re_Mms":
        speaker_driver = ac.SpeakerDriver(settings,
                                          fs=vals["fs"],
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
                                  speaker: ac.SpeakerDriver,
                                  spk_sys: (None, ac.SpeakerSystem) = None,
                                  ) -> ac.SpeakerSystem:    
    if vals["box_type"] == 1:
        housing = ac.Housing(speaker.settings,
                             vals["Vb"],
                             vals["Qa"],
                             vals["Qa"],
                             )
    else:
        housing = None
        
    if vals["parent_body"] == 1:
        parent_body = ac.ParentBody(vals["m2"],
                                    vals["k2"],
                                    vals["c2"],
                                    )
    else:
        parent_body = None
        
    if False:  # passive radiator not implemented yet
        pass
    else:
        passive_radiator = None
        
    if spk_sys is None:
        return ac.SpeakerSystem(speaker,
                                vals["R_serial"],
                                housing,
                                parent_body,
                                passive_radiator,
                                )   
    else:
        spk_sys.update_values(speaker=speaker,
                                Rs = vals["R_serial"],
                                housing = housing,
                                parent_body = parent_body,
                                passive_radiator = passive_radiator,
                                )

    return spk_sys


def parse_args(app_definitions):
    import argparse

    description = (
        f"{app_definitions['app_name']} - {app_definitions['copyright']}"
        "\nThis program comes with ABSOLUTELY NO WARRANTY"
        "\nThis is free software, and you are welcome to redistribute it"
        "\nunder certain conditions. See LICENSE file for more details."
    )

    parser = argparse.ArgumentParser(prog="python main.py",
                                     description=description,
                                     epilog={app_definitions['website']},
                                     )

    parser.add_argument('infile', nargs='?', type=Path,
                        help="Path to a '*.scf' file. This will open with preset values.")
    parser.add_argument('-d', '--loglevel', nargs="?",
                        choices=["debug", "info", "warning", "error", "critical"],
                        help="Set logging level for Python logging. Valid values are debug, info, warning, error and critical.")

    return parser.parse_args()


def create_sound_engine(app):
    global settings
    sound_engine = pwi.SoundEngine(settings)
    sound_engine_thread = qtc.QThread()
    sound_engine.moveToThread(sound_engine_thread)
    sound_engine_thread.start(qtc.QThread.HighPriority)

    # ---- Connections
    app.aboutToQuit.connect(sound_engine.release_all)
    app.aboutToQuit.connect(sound_engine_thread.exit)

    return sound_engine, sound_engine_thread


def setup_logging(level: str="warning", args=None):
    if args and args.loglevel:
        log_level = getattr(logging, args.loglevel.upper())
    else:
        log_level = level.upper()
        
    log_filename = Path.home().joinpath(f".{app_definitions['app_name'].lower()}.log")

    file_handler = logging.FileHandler(filename=log_filename)
    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    handlers = [file_handler, stdout_handler]

    logging.basicConfig(handlers=handlers,
                        level=log_level,
                        format="%(asctime)s %(levelname)s - %(funcName)s: %(message)s",
                        force=True,
                        )
    # had to force this
    # https://stackoverflow.com/questions/30861524/logging-basicconfig-not-creating-log-file-when-i-run-in-pycharm
    logger = logging.getLogger()
    logger.info(f"{time.strftime('%c')} - Started logging with log level {log_level}.")
    
    return logger


def main():
    global settings, app_definition, logger, create_sound_engine, wires

    args = parse_args(app_definitions)
    logger = setup_logging(args=args)
    settings = Settings(app_definitions["app_name"])
    wire_table_file = Path.cwd().joinpath("SC_data", "wire table.ods")
    wires = read_wire_table(wire_table_file)

    # ---- Start QApplication
    if not (app := qtw.QApplication.instance()):
        app = qtw.QApplication(sys.argv)
        # there is a new recommendation with qApp but how to do the sys.argv with that?
        # app.setQuitOnLastWindowClosed(True)  # is this necessary??
        app.setWindowIcon(qtg.QIcon(app_definitions["icon_path"]))

    # ---- Catch exceptions and handle with pop-up widget
    error_handler = pwi.ErrorHandlerDeveloper(app, logger)
    sys.excepthook = error_handler.excepthook

    # ---- Create sound engine
    sound_engine, sound_engine_thread = create_sound_engine(app)

    # ---- Create main window
    windows = []  # if you don't store them they get garbage collected once new_window terminates

    def new_window(**kwargs):
        mw = MainWindow(sound_engine, **kwargs)
        windows.append(mw)  # needs to be addressed otherwise it gets deleted from memory.
        mw.signal_new_window.connect(lambda kwargs: new_window(**kwargs))
        mw.signal_bad_beep.connect(sound_engine.bad_beep)
        mw.signal_good_beep.connect(sound_engine.good_beep)
        mw.show()
        return mw

    if args.infile:
        logger.info(f"Starting application with argument infile: {args.infile}")
        mw = new_window(open_user_file=args.infile.name)
        mw.status_bar().show_message(f"Opened file '{args.infile.name}'", 5000)
    elif (default_file := Path.cwd().joinpath("default.scf")).is_file():
        new_window(open_user_file=default_file)
    else:
        new_window()

    # construct_SpeakerSystem(windows[0])  # for testing
    app.exec()


if __name__ == "__main__":
    main()
