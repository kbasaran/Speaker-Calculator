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
from dataclasses import dataclass, fields

from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc
from PySide6 import QtGui as qtg

from generictools.graphing_widget import MatplotlibWidget
import generictools.personalized_widgets as pwi
from version_convert import convert_v01_to_v02

import logging
from pathlib import Path
import matplotlib as mpl
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

        # self.interactable_widgets = {}
        for name, form in forms.items():
            self.addTab(form, name)
            # self.interactable_widgets = {**self.interactable_widgets, **form.interactable_widgets}

    def _make_form_for_general_tab(self):
        form = pwi.UserForm()

        # ---- General specs
        form.add_row(pwi.Title("General speaker specifications"))

        form.add_row(pwi.FloatSpinBox("fs", "Undamped resonance frequency of the speaker in free-air condition",
                                      decimals=1,
                                      min_max=(0.1, 1e6),
                                      ),
                     description="fs (Hz)",
                     )

        form.add_row(pwi.FloatSpinBox("Qms", "Quality factor of speaker, only the mechanical part",
                                      ),
                     description="Qms",
                     )

        form.add_row(pwi.FloatSpinBox("Xpeak", "Peak excursion allowed, one way",
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Xpeak (mm)",
                     )

        form.add_row(pwi.FloatSpinBox("dead_mass", "Moving mass excluding the coil itform and the air.|n(Dead mass = Mmd - coil mass)",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Dead mass (g)",
                     )

        form.add_row(pwi.FloatSpinBox("Sd", "Diaphragm effective surface area",
                                      coeff_for_SI=1e-4,
                                      ),
                     description="Sd (cm²)"
                     )

        # ---- Electrical input
        form.add_row(pwi.SunkenLine())

        form.add_row(pwi.Title("Electrical Input"))

        form.add_row(pwi.FloatSpinBox("Rs_source",
                                      "The resistance between the speaker terminal and the voltage source."
                                      "\nMay be due to cables, connectors etc."
                                      "\nCauses resistive loss before arrival at the speaker terminals.",
                                      min_max=(0, 1e6),
                                      ),
                     description="Source resistance",
                     )

        form.add_row(pwi.ComboBox("excitation_unit", "Choose which type of input excitation you want to define.",
                                  [("Volts", "V"),
                                   ("Watts @Rdc", "W"),
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
        
        # ---- Form logic
        def adjust_form_for_excitation_unit(chosen_index):
            is_Wn = \
                form.interactable_widgets["excitation_unit"].itemData(chosen_index) == "Wn"
            form.interactable_widgets["Rnom"].setEnabled(is_Wn)

        form.interactable_widgets["excitation_unit"].currentIndexChanged.connect(adjust_form_for_excitation_unit)
        # adjustment at start
        adjust_form_for_excitation_unit(form.interactable_widgets["excitation_unit"].currentIndex())
        
        return form

    def _make_form_for_motor_tab(self):
        form = pwi.UserForm()

        # Motor spec type
        form.add_row(pwi.ComboBox("motor_spec_type", "Choose which parameters you want to input to make the motor strength calculation",
                                  [("Define Coil Dimensions and Average B", "define_coil"),
                                   ("Define Bl, Rdc, Mmd", "define_Bl_Re_Mmd"),
                                   ("Define Bl, Rdc, Mms", "define_Bl_Re_Mms"),
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

        form.add_row(pwi.FloatSpinBox("target_Rdc", "Rdc value that needs to be approached while calculating an appropriate coil and winding",
                                      ),
                     description="Target Rdc (ohm)",
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
                                      min_max=(0, 1e6)
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

        form.add_row(pwi.FloatSpinBox("w_stacking_coef",
                                      "Stacking coefficient for additional winding layers put on."
                                      "\nE.g. if this is set to 0.8 and the wire nominal thickness is 1mm"
                                      "\nnominal thickness of windings that are 1,2,3 layers will be"
                                      "\n1mm,1.8mm,2.6mm, respectively."
                                      "\nFor stacking of ideal circular wires this value is 'sin(60)=0.5'"
                                      "\nHas no effect on the height of the winding.",
                                      min_max=(0, 1),
                                      ),
                     description="Stacking coeff. for additional layers",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.FloatSpinBox("Rs_leadwire",
                                      "Resistance between the coil and the speaker terminals, e.g. leadwire",
                                      min_max=(0, form.interactable_widgets["h_winding_target"].maximum()),
                                      # took the automatically assigned maximum from another widget
                                      # instead of typing n an arbitrary number
                                      # 'None' was not expected by the underlying 'setRange' method
                                      ),
                     description="Leadwire resistance (ohm)",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.FloatSpinBox("B_average", "Average B field across the coil windings."
                                      "\nNeeds to be calculated separately and input here.",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Average B field on coil (mT)",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.LineTextBox("N_layer_options", "Enter the number of winding layer options that are accepted."
                                     "\nUse integers with a comma in between, e.g.: '2, 4'",
                                     ),
                     description="Number of layer options",
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
                                  [("SV", {"current_text": "4x CCAW230, Rdc=4.18, Lm=87.19, Qts=0.59", "current_data": {}}),
                                   ("CCAW", {"current_text": "current text"}),
                                   ("MEGA", {"current_text": "current text"}), ],
                                  ),
                     into_form=motor_definition_p1,
                     )

        # ---- Second page: "Define Bl, Rdc, Mmd"
        motor_definition_p2 = pwi.SubForm()
        form.motor_definition_stacked.addWidget(motor_definition_p2)

        form.add_row(pwi.FloatSpinBox("Bl_p2", "Force factor",
                                      ),
                     description="Bl (Tm)",
                     into_form=motor_definition_p2,
                     )

        form.add_row(pwi.FloatSpinBox("Rdc_p2", "DC resistance",
                                    ),
                     description="Rdc (ohm)",
                     into_form=motor_definition_p2,
                     )

        form.add_row(pwi.FloatSpinBox("Mmd_p2",
                                      "Moving mass, excluding coupled air mass",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Mmd (g)",
                     into_form=motor_definition_p2,
                     )

        # ---- Third page: "Define Bl, Rdc, Mms"
        motor_definition_p3 = pwi.SubForm()
        form.motor_definition_stacked.addWidget(motor_definition_p3)

        form.add_row(pwi.FloatSpinBox("Bl_p3",
                                      "Force factor",
                                      ),
                     description="Bl (Tm)",
                     into_form=motor_definition_p3,
                     )

        form.add_row(pwi.FloatSpinBox("Rdc_p3",
                                    "DC resistance",
                                    ),
                     description="Rdc (ohm)",
                     into_form=motor_definition_p3,
                     )

        form.add_row(pwi.FloatSpinBox("Mms_p3",
                                      "Moving mass, including coupled air mass",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Mms (g)",
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

        form.add_row(pwi.FloatSpinBox("h_former_extension_under_coil", "Extension of the coil former below the coil windings",
                                      coeff_for_SI=1e-3,
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
            form.interactable_widgets["h_former_extension_under_coil"].setEnabled(is_define_coil)
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

        form.add_row(pwi.FloatSpinBox("Vb", "Internal free volume filled by air",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Box internal volume (l)",
                     )

        form.add_row(pwi.FloatSpinBox("Qa", "Quality factor of the speaker resulting from absorption losses inside the box."
                                      + "\n**This value also affects effective box volume: 'Vba = Vb * (0.94 / Qa + 1)'**",
                                      decimals=1
                                      ),
                     description="Qa - box absorption",
                     )

        form.add_row(pwi.FloatSpinBox("Ql", "Quality factor of the speaker resulting from leakage losses of box",
                                      decimals=1
                                      ),
                     description="Ql - box losses",
                     )


        # ---- Form logic
        def adjust_form_for_enclosure_type(toggled_id, checked):
            form.interactable_widgets["Vb"].setEnabled(toggled_id == 1 and checked is True)
            form.interactable_widgets["Qa"].setEnabled(toggled_id == 1 and checked is True)
            form.interactable_widgets["Ql"].setEnabled(toggled_id == 1 and checked is True)


        form.interactable_widgets["box_type"].idToggled.connect(adjust_form_for_enclosure_type)
        # instantiate
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

        form.add_row(pwi.FloatSpinBox("k2", "Stiffness between the parent body and the ground",
                                      coeff_for_SI=1e3,
                                      ),
                     description="Stiffness (N/mm)",
                     )


        form.add_row(pwi.FloatSpinBox("c2", "Damping coefficient between the parent body and the ground",
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

    def __init__(self, settings, sound_engine, user_form_dict=None, open_user_file=None):
        super().__init__()
        self.setWindowTitle(app_definitions["app_name"])
        self._create_menu_bar()
        self._create_widgets()
        self._place_widgets()
        # self._add_status_bar()
        if user_form_dict:
            self.set_state(user_form_dict)
        elif open_user_file:
            self.load_state_from_file(open_user_file)

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
        self.graph = MatplotlibWidget(settings)
        self.graph_data_choice = pwi.ChoiceButtonGroup("_graph_buttons",

                                                       {0: "SPL",
                                                        1: "Impedance",
                                                        2: "Displacement",
                                                        3: "Relative",
                                                        4: "Forces",
                                                        5: "Accelerations",
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

                                                       # Graph buttons
                                                       )
        self._graph_buttons = pwi.PushButtonGroup({"update_results": "Update results",
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
        for button in self._graph_buttons.buttons().values():
            font_pixel_size = button.font().pixelSize()
            button.setMinimumHeight(48)

            # temporary disable, to be decided later
            if button.text() != "Update results":
                button.setEnabled(False)

        # Text boxes
        self.results_textbox = qtw.QPlainTextEdit()
        self.notes_textbox = qtw.QPlainTextEdit()
        self.textboxes_layout = qtw.QHBoxLayout()

        results_section = qtw.QWidget()
        results_section_layout = qtw.QVBoxLayout(results_section)
        results_section_layout.setContentsMargins(-1, 0, -1, 0)
        results_section_layout.addWidget(qtw.QLabel("Results"))
        results_section_layout.addWidget(self.results_textbox)

        notes_section = qtw.QWidget()
        notes_section_layout = qtw.QVBoxLayout(notes_section)
        notes_section_layout.setContentsMargins(-1, 0, -1, 0)
        notes_section_layout.addWidget(qtw.QLabel("Notes"))
        notes_section_layout.addWidget(self.notes_textbox)

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
        self._rh_layout.addWidget(self._graph_buttons)
        self.graph_data_choice.layout().setContentsMargins(-1, 0, -1, 0)
        self._rh_layout.addLayout(self.textboxes_layout, 2)

    def _add_status_bar(self):
        self.setStatusBar(qtw.QStatusBar())
        self.statusBar().showMessage("Test", 2000)

    def get_state(self):
        state = {}
        tab_widgets = [self.input_form.widget(i) for i in range(self.input_form.count())]
        for input_form_widget in tab_widgets:
            state = {**state, **input_form_widget.get_form_values()}
        
        state["user_notes"] = self.notes_textbox.toPlainText()

        logger.debug(f"Get states returning states dictionary:\n{state}")
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
        # when no file is provided as argumnent, this function raises a file selection menu
        if file is None:
            path_unverified = qtw.QFileDialog.getOpenFileName(self, caption='Open parameters from a save file..',
                                                              dir=settings.last_used_folder,
                                                              filter='Speaker calculator files (*.scf *.sscf)',
                                                              )

            # Check file
            if file_raw := path_unverified[0]:
                file = Path(file_raw)
            else:
                return  # canceled file select
        else:
            pass  # use the argument

        # Check if file exists
        if not file.is_file():
            raise FileNotFoundError(file)

        # if you reached here, file is ready as Path object
        logger.info(f"Loading file '{file.name}'")

        settings.update("last_used_folder", str(file.parent))

        suffix = file.suffixes[-1]

        if suffix == ".sscf":
            # backwards compatibility with v0.1
            state = convert_v01_to_v02(file)
            self.set_state(state)
            
        elif suffix == ".scf":
            with open(file, "rt") as f:
                state = json.load(f)
            self.set_state(state)
        else:
            raise ValueError(f"Invalid suffix '{suffix}'")

    def set_state(self, state: dict):
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
            partial(self._save_and_close,  user_form.interactable_widgets, settings))

    def _save_and_close(self, user_input_widgets, settings):
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


# the v01 files require below classes to open. this is because I pickled their instances
# and to load them again, app needs to create instances of these classes
# [face palm]
class SpeakerDriver():
    pass


class SpeakerSystem():
    pass


def read_wire_table(wire_table: Path) -> pd.DataFrame:
    if not wire_table.exists():
        raise FileNotFoundError(f"Wire table file not found: {Path}")
    df = pd.read_excel(wire_table, "Sheet1", skiprows=range(2), index_col=0)
    if not df.index.is_unique:
        raise IndexError("Wire names in the imported table are not unique.")
    return df


def construct_Wire(df: pd.DataFrame, name: str) -> ac.Wire:
    if name not in df.index:
        raise ValueError(f"Wire {name} is not available in wire table.")
    wire_data = df.loc[name]
    wire = ac.Wire(name,
                   wire_data["w_avg"],
                   wire_data["h_avg"],
                   wire_data["w_max"],
                   wire_data["resistance"],
                   wire_data["mass_density"],
                   )
    return wire


def find_feasible_coils(vals):
    """Scan best matching speaker coil options."""
    try:  # try to read the N_layer_options string
        layer_options = [int(str) for str in vals["N_layer_options"].replace(" ", "").split(",")]
        if not layer_options:
            raise ValueError("At least one option needs to be provided for number of winding layers.")
    except Exception:
        raise ValueError("Invalid input in number of layer options")

    # Make a dataframe to store viable winding options
    table_columns = ["name", "wire", "N_layers", "Bl", "Rdc", "Lm", "Qts", "carrier_OD",
                     "h_winding", "N_windings", "total_wire_length", "coil_w_max", "coil_mass"]
    coil_options_table = pd.DataFrame(columns=table_columns, indexcol="name")

    # Scan through winding options
    winding = Record()
    for k in ["target_Rdc", "former_ID", "t_former", "h_winding"]:
        setattr(winding, k, self.get_value(k))

    for N_layers in layer_options:
        for wire_type, row in cons.VC_TABLE.iterrows():
            Rdc, N_windings, l_wire, coil_w_max, coil_mass = calculate_windings(wire_type,
                                                                                N_layers,
                                                                                winding.former_ID + winding.t_former * 2,
                                                                                winding.h_winding)
    # if Rdc is usable, add to DataFrame
            if winding.target_Rdc / 1.1 < Rdc < winding.target_Rdc * 1.15 and all(i > 0 for i in N_windings):
                winding_name = (str(N_layers) + "x " + wire_type).strip()
                winding_data = {}
                for k in ["wire_type", "N_layers", "Rdc", "N_windings", "l_wire", "coil_w_max", "coil_mass"]:
                    winding_data[k] = locals()[k]
                coil_choice = (winding_name, winding_data)
                speaker = SpeakerDriver(coil_choice)
                self.coil_options_table.loc[winding_name] = [getattr(speaker, i) for i in table_columns]  # add all the parameters of this speaker to a new dataframe row
    self.coil_options_table.sort_values("Lm", ascending=False)

    # Add the coils in dataframe to the combobox (with their userData)
    for winding_name in self.coil_options_table.index:
        # Make a string for the text to show on the combo box
        Rdc_string = "Rdc=%.2f, " % self.coil_options_table.Rdc[winding_name]
        Lm_string = "Lm=%.2f, " % self.coil_options_table.Lm[winding_name]
        Qes_string = "Qts=%.2f" % self.coil_options_table.Qts[winding_name]
        name_in_combo_box = winding_name + ", " + Rdc_string + Lm_string + Qes_string
        userData = self.coil_options_table.to_dict("index")[winding_name]
        self.coil_choice_box["obj"].addItem(name_in_combo_box, userData)
    # if nothing to add to combobox
    if self.coil_choice_box["obj"].count() == 0:
        beep_bad()
        self.coil_choice_box["obj"].addItem("--no solution found--")
    else:
        beep()


def update_coil_options_combobox(mw):
    mw.coil_choice_box["obj"].clear()
    pass


def construct_SpeakerSystem(mw: MainWindow) -> ac.SpeakerSystem:
    "Create the loudspeaker model based on the values provided in the widget."
    global wire_table, logger
    vals = mw.get_state()
    
    if vals["motor_spec_type"]["current_data"] == "define_coil":
        coil = vals["coil_options"]["current_data"]["coil"]
        motor = ac.Motor(coil, vals["B_average"])
        speaker_driver = ac.SpeakerDriver(fs=vals["fs"],
                                          Sd=vals["Sd"],
                                          Qms=vals["Qms"],
                                          motor=motor,
                                          dead_mass=vals["dead_mass"],
                                          Rs=vals["Rs_leadwire"],
                                          Xpeak=vals["Xpeak"],
                                          )
        
    elif vals["motor_spec_type"]["current_data"] == "define_Bl_Re_Mmd":
        speaker_driver = ac.SpeakerDriver(fs=vals["fs"],
                                          Sd=vals["Sd"],
                                          Qms=vals["Qms"],
                                          Bl=vals["Bl"],
                                          Re=vals["Re"],
                                          Mmd=vals["Mmd"],
                                          Rs=vals["Rs_leadwire"],
                                          Xpeak=vals["Xpeak"],
                                          )
        
    elif vals["motor_spec_type"]["current_data"] == "define_Bl_Re_Mms":
        speaker_driver = ac.SpeakerDriver(fs=vals["fs"],
                                          Sd=vals["Sd"],
                                          Qms=vals["Qms"],
                                          Bl=vals["Bl"],
                                          Re=vals["Re"],
                                          Mms=vals["Mms"],
                                          Rs=vals["Rs_leadwire"],
                                          Xpeak=vals["Xpeak"],
                                          )
    else:
        raise ValueError("Invalid motor specification type.")


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
    parser.add_argument('-d', '--debuglevel', nargs="?", default="warning",
                        help="Set debugging level for Python logging. Valid values are debug, info, warning, error and critical.")

    return parser.parse_args()


def create_sound_engine(app):
    sound_engine = pwi.SoundEngine(settings)
    sound_engine_thread = qtc.QThread()
    sound_engine.moveToThread(sound_engine_thread)
    sound_engine_thread.start(qtc.QThread.HighPriority)

    # ---- Connections
    app.aboutToQuit.connect(sound_engine.release_all)
    app.aboutToQuit.connect(sound_engine_thread.exit)

    return sound_engine, sound_engine_thread


def setup_logging(args):
    if args.debuglevel:
        log_level = getattr(logging, args.debuglevel.upper())
    else:
        log_level = logging.INFO
    log_filename = Path.home().joinpath(f".{app_definitions['app_name'].lower()}.log")
    logging.basicConfig(filename=log_filename,
                        level=log_level,
                        format="%(asctime)s %(levelname)s - %(funcName)s: %(message)s",
                        force=True,
                        )
    # had to force this
    # https://stackoverflow.com/questions/30861524/logging-basicconfig-not-creating-log-file-when-i-run-in-pycharm
    logger = logging.getLogger()
    logger.info(f"Starting with log level {log_level}.")

    return logger


def main():
    global settings, app_definition, logger, create_sound_engine, Settings, wire_table

    args = parse_args(app_definitions)
    logger = setup_logging(args)
    settings = Settings(app_definitions["app_name"])
    wire_table_path = Path.cwd().joinpath("SC_data", "wire table.ods")
    wire_table = read_wire_table(wire_table_path)

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
        mw = MainWindow(settings, sound_engine, **kwargs)
        windows.append(mw)
        mw.signal_new_window.connect(lambda kwargs: new_window(**kwargs))
        mw.signal_bad_beep.connect(sound_engine.bad_beep)
        mw.signal_good_beep.connect(sound_engine.good_beep)
        mw.show()
        return mw

    if args.infile:
        logger.info(f"Starting application with argument infile: {args.infile}")
        mw = new_window(open_user_file=args.infile.name)
        mw.status_bar().show_message(f"Opened file '{args.infile.name}'", 5000)
    elif (default_file := Path.cwd().joinpath("default.sscf")).is_file():
        new_window(open_user_file=default_file)
    else:
        new_window()

    # construct_SpeakerSystem(windows[0])  # for testing
    app.exec()


if __name__ == "__main__":
    main()
