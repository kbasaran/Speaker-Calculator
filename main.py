import os
import sys
import traceback
import numpy as np
import json

from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc
# from PySide6 import QtGui as qtg

import sounddevice as sd
from graphing import MatplotlibWidget
import personalized_widgets as pwi

import logging
logging.basicConfig(level=logging.INFO)

# https://realpython.com/python-super/#an-overview-of-pythons-super-function
# super(super_of_which_class?=this class, in_which_object?=self)
# The parameterless call to super() is recommended and sufficient for most use cases

class SoundEngine(qtc.QObject):
    def __init__(self, settings):
        super().__init__()
        self.FS = sd.query_devices(device=sd.default.device, kind='output',
                                   )["default_samplerate"]
        self.verify_stream()

    def verify_stream(self):
        # needs to be improved and tested for device changes!
        if not hasattr(self, "stream"):
            self.stream = sd.OutputStream(samplerate=self.FS, channels=2)
        if not self.stream.active:
            self.stream.start()

    @qtc.Slot(float, float)
    def beep(self, T, freq):
        self.verify_stream()
        t = np.arange(T * self.FS) / self.FS
        y = np.sin(t * 2 * np.pi * freq)
        y = np.tile(y, self.stream.channels)
        y = y.reshape((len(y) // self.stream.channels,
                      self.stream.channels), order='F').astype(self.stream.dtype)
        y = np.ascontiguousarray(y, self.stream.dtype)
        self.stream.write(y)

    @qtc.Slot()
    def good_beep(self):
        self.beep(settings.T_beep, settings.freq_good_beep)

    @qtc.Slot()
    def bad_beep(self):
        self.beep(settings.T_beep, settings.freq_bad_beep)

    @qtc.Slot()
    def release_all(self):
        self.stream.stop(ignore_errors=True)

class LeftHandForm(pwi.UserForm):
    signal_save_clicked = qtc.Signal()
    signal_load_clicked = qtc.Signal()
    signal_new_clicked = qtc.Signal()
    signal_beep_clicked = qtc.Signal()  # no need to write args in this like float, float???

    def __init__(self):
        super().__init__()

        self._populate_form()
        self._make_connections()

    def _populate_form(self):

        self.add_row(pwi.PushButtonGroup({"load": "Load", "save": "Save", "new": "New", "beep": "Beeep"},
                                      {"load": "Load parameters from a file",
                                       "save": "Save parameters to a file",
                                       "new": "Create another instance of the application, carrying all existing parameters",
                                       "beep": "just beep",
                                       }))

        self.add_row(pwi.Title("General speaker specifications"))

        self.add_row(pwi.FloatSpinBox("fs", "Undamped resonance frequency of the speaker in free-air condition",
                                   decimals=1,
                                   min_max=(0.1, settings.f_max),
                                   ),
                      description="fs (Hz)",
                      )

        self.add_row(pwi.FloatSpinBox("Qms", "Quality factor of speaker, only the mechanical part",
                                   ),
                      description="Qms",
                      )

        self.add_row(pwi.FloatSpinBox("Xmax", "Peak excursion allowed, one way",
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Xmax (mm)",
                      )

        self.add_row(pwi.FloatSpinBox("dead_mass", "Moving mass excluding the coil itself and the air.|n(Dead mass = Mmd - coil mass)",
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Dead mass (g)",
                      )

        self.add_row(pwi.FloatSpinBox("Sd", "Diaphragm effective surface area",
                                   ratio_to_SI=1e-4,
                                   ),
                      description="Sd (cm²)"
                      )

        # ----------------------------------------------------
        self.add_row(pwi.SunkenLine())

        self.add_row(pwi.ComboBox("motor_spec_type", "Choose which parameters you want to input to make the motor strength calculation",
                               [("Define Coil Dimensions and Average B", "define_coil"),
                                ("Define Bl, Rdc, Mmd", "define_Bl_Re_Mmd"),
                                   ("Define Bl, Rdc, Mms", "define_Bl_Re_Mms"),
                                ],
                               ))
        self._user_input_widgets["motor_spec_type"].setStyleSheet(
            "font-weight: bold")

        # Make a stacked widget for different motor definition parameters
        self.motor_definition_stacked = qtw.QStackedWidget()
        self._user_input_widgets["motor_spec_type"].currentIndexChanged.connect(
            self.motor_definition_stacked.setCurrentIndex)

        self.add_row(self.motor_definition_stacked)

        # Make the first page of stacked widget for "Define Coil Dimensions and Average B"
        motor_definition_p1 = pwi.SubForm()
        self.motor_definition_stacked.addWidget(motor_definition_p1)

        self.add_row(pwi.FloatSpinBox("target_Rdc", "Rdc value that needs to be approached while calculating an appropriate coil and winding",
                                   ),
                      description="Target Rdc (ohm)",
                      into_form=motor_definition_p1,
                      )

        self.add_row(pwi.FloatSpinBox("former_ID", "Internal diameter of the coil former",
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Coil Former ID (mm)",
                      into_form=motor_definition_p1,
                      )

        self.add_row(pwi.IntSpinBox("t_former", "Thickness of the coil former",
                                 ratio_to_SI=1e-6,
                                 ),
                      description="Former thickness (\u03BCm)",
                      into_form=motor_definition_p1,
                      )

        self.add_row(pwi.FloatSpinBox("h_winding", "Desired height of the coil winding",
                                   ),
                      description="Coil winding height (mm)",
                      into_form=motor_definition_p1,
                      )

        self.add_row(pwi.FloatSpinBox("B_average", "Average B field across the coil windings."
                                   "\nNeeds to be calculated separately and input here.",
                                   decimals=3,
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Average B field on coil (mT)",
                      into_form=motor_definition_p1,
                      )

        self.add_row(pwi.LineTextBox("N_layer_options", "Enter the number of winding layer options that are accepted."
                                  "\nUse integers with a comma in between, e.g.: '2, 4'",
                                  ),
                      description="Number of layer options",
                      into_form=motor_definition_p1,
                      )

        self.add_row(pwi.PushButtonGroup({"update_coil_choices": "Update coil choices"},
                                      {"update_coil_choices": "Populate the below dropdown with possible coil choices for the given parameters"},
                                      ),
                      into_form=motor_definition_p1,
                      )

        self.add_row(pwi.ComboBox("coil_options", "Select coil winding to be used for calculations",
                               [("SV", "data1"),
                                ("CCAW", "data2"),
                                ("MEGA", "data3"), ],
                               ),
                      into_form=motor_definition_p1,
                      )

        # Make the second page of stacked widget for "Define Bl, Rdc, Mmd"
        motor_definition_p2 = pwi.SubForm()
        self.motor_definition_stacked.addWidget(motor_definition_p2)

        self.add_row(pwi.FloatSpinBox("Bl_p2", "Force factor",
                                   ),
                      description="Bl (Tm)",
                      into_form=motor_definition_p2,
                      )

        self.add_row(pwi.IntSpinBox("Rdc_p2", "DC resistance",
                                 ),
                      description="Rdc (ohm)",
                      into_form=motor_definition_p2,
                      )

        self.add_row(pwi.FloatSpinBox("Mmd_p2",
                                   "Moving mass, excluding coupled air mass",
                                   decimals=3,
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Mmd (g)",
                      into_form=motor_definition_p2,
                      )

        # Make the third page of stacked widget for "Define Bl, Rdc, Mms"
        motor_definition_p3 = pwi.SubForm()
        self.motor_definition_stacked.addWidget(motor_definition_p3)

        self.add_row(pwi.FloatSpinBox("Bl_p3",
                                   "Force factor",
                                   ),
                      description="Bl (Tm)",
                      into_form=motor_definition_p3,
                      )

        self.add_row(pwi.IntSpinBox("Rdc_p3",
                                 "DC resistance",
                                 ),
                      description="Rdc (ohm)",
                      into_form=motor_definition_p3,
                      )

        self.add_row(pwi.FloatSpinBox("Mms_p3",
                                   "Moving mass, including coupled air mass",
                                   decimals=3,
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Mms (g)",
                      into_form=motor_definition_p3,
                      )

        # ----------------------------------------------------
        self.add_row(pwi.SunkenLine())

        self.add_row(pwi.Title("Motor mechanical specifications"))

        self.add_row(pwi.FloatSpinBox("h_top_plate", "Thickness of the top plate (also called washer)",
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Top plate thickness (mm)",
                      )

        self.add_row(pwi.IntSpinBox("airgap_clearance_inner", "Clearance on the inner side of the coil former",
                                 ratio_to_SI=1e-6,
                                 ),
                      description="Airgap inner clearance (\u03BCm)",
                      )

        self.add_row(pwi.IntSpinBox("airgap_clearance_outer", "Clearance on the outer side of the coil windings",
                                 ratio_to_SI=1e-6,
                                 ),
                      description="Airgap outer clearance (\u03BCm)",
                      )

        self.add_row(pwi.FloatSpinBox("former_extension_under_coil", "Extension of the coil former below the coil windings",
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Former bottom ext. (mm)",
                      )

        # ----------------------------------------------------
        self.add_row(pwi.SunkenLine())

        self.add_row(pwi.Title("Closed box specifications"))

        self.add_row(pwi.FloatSpinBox("Vb", "Internal free volume filled by air",
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Box internal volume (l)",
                      )

        self.add_row(pwi.FloatSpinBox("Qa", "Quality factor of the speaker, mechanical part due to losses in box",
                                   decimals=1
                                   ),
                      description="Qa - box absorption",
                      )

        # ----------------------------------------------------
        self.add_row(pwi.SunkenLine())

        self.add_row(pwi.Title("Second degree of freedom"))

        self.add_row(pwi.FloatSpinBox("k2", "Stiffness between the second body and the ground",
                                   ratio_to_SI=1e3,
                                   ),
                      description="Stiffness (N/mm)",
                      )

        self.add_row(pwi.FloatSpinBox("m2", "Mass of the second body",
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Mass (g)",
                      )

        self.add_row(pwi.FloatSpinBox("c2", "Damping coefficient between the second body and the ground",
                                   ),
                      description="Damping coefficient (kg/s)",
                      )

        # ----------------------------------------------------
        self.add_row(pwi.SunkenLine())

        self.add_row(pwi.Title("Electrical Input"))

        self.add_row(pwi.FloatSpinBox("Rs",
                                   "The resistance between the speaker coil and the voltage source."
                                   "\nMay be due to cables, speaker leadwires, connectors etc."
                                   "\nCauses resistive loss at the input.",
                                   ),
                      description="Series resistance",
                      )

        self.add_row(pwi.ComboBox("excitation_unit", "Choose which type of input excitation you want to define.",
                               [("Volts", "V"),
                                ("Watts @Rdc", "W"),
                                   ("Watss @Rnom", "Wn")
                                ],
                               ),
                      description="Unit",
                      )

        self.add_row(pwi.FloatSpinBox("excitation_value", "The value for input excitation, in units chosen above",
                                   ),
                      description="Excitation value",
                      )

        self.add_row(pwi.FloatSpinBox("nominal_impedance", "Nominal impedance of the speaker. This is necessary to calculate the voltage input"
                                   "\nwhen 'Watts @Rnom' is selected as the input excitation unit.",
                                   ),
                      description="Nominal impedance",
                      )

        # ----------------------------------------------------
        self.add_row(pwi.SunkenLine())

        self.add_row(pwi.Title("System type"))

        self.add_row(pwi.ChoiceButtonGroup("box_type",
                                        {0: "Free-air", 1: "Closed box"},
                                        {0: "Speaker assumed to be on an infinite baffle, with no acoustical loading on either side",
                                            1: "Speaker rear side coupled to a lossy sealed box.",
                                         },
                                        vertical=False,
                                        ),
                      )

        self.add_row(pwi.ChoiceButtonGroup("dof",
                                        {0: "1 dof", 1: "2 dof"},
                                        {0: "1 degree of freedom - only the loudspeaker moving mass has mobility.",
                                            1: "2 degrees of freedom - loudspeaker moving mass is attached to a second lump mass that has mobility."},
                                        vertical=False,
                                        )
                      )

    def _make_connections(self):
        def raise_error():
            raise FileExistsError
        self._user_input_widgets["load_pushbutton"].clicked.connect(
            self.signal_load_clicked)
        self._user_input_widgets["save_pushbutton"].clicked.connect(
            self.signal_save_clicked)
        self._user_input_widgets["new_pushbutton"].clicked.connect(
            self.signal_new_clicked)
        self._user_input_widgets["beep_pushbutton"].clicked.connect(
            self.signal_beep_clicked)


class MainWindow(qtw.QMainWindow):
    signal_new_window = qtc.Signal(dict)  # new_window with kwargs as dict
    signal_beep = qtc.Signal(float, float)

    def __init__(self, settings, sound_engine, user_form_dict=None, open_user_file=None):
        super().__init__()
        self.global_settings = settings
        self._create_core_objects()
        self._create_widgets()
        self._place_widgets()
        self._add_status_bar()
        self._make_connections()
        if user_form_dict:
            self._lh_form.update_form_values(user_form_dict)
        elif open_user_file:
            self.load_preset_file(open_user_file)

    def _create_core_objects(self):
        pass

    def _create_widgets(self):
        self._lh_form = LeftHandForm()
        self.graph = MatplotlibWidget()
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

                                                   )
        self._graph_buttons = pwi.PushButtonGroup({"update_results": "Update results",
                                              "export_curve": "Export curve",
                                              "export_quick": "Quick export",
                                              "import_curve": "Import curve",
                                              "remove_curve": "Remove curve",
                                              },
                                             {"update_results": "Update calculated values. Click this when you modify the user input.",
                                              "export_curve": "Open export menu",
                                              "export_quick": "Quick export using latest settings",
                                              "import_curve": "Open import menu",
                                              "remove_curve": "Open remove curves menu",
                                              },
                                             )

        self.results_textbox = qtw.QPlainTextEdit()
        self.notes_textbox = qtw.QPlainTextEdit()        
        self.textboxes_layout = qtw.QHBoxLayout()
        self.textboxes_layout.addWidget(self.results_textbox)
        self.textboxes_layout.addWidget(self.notes_textbox)

        self._rh_widget = qtw.QWidget()

    def _place_widgets(self):
        self._center_widget = qtw.QWidget()
        self._center_layout = qtw.QHBoxLayout(self._center_widget)
        self.setCentralWidget(self._center_widget)

        self._center_layout.addWidget(self._lh_form)
        self._lh_form.setSizePolicy(
            qtw.QSizePolicy.Fixed, qtw.QSizePolicy.Fixed)

        self._center_layout.addWidget(self._rh_widget)

        self._rh_layout = qtw.QVBoxLayout(self._rh_widget)
        self._rh_layout.addWidget(self.graph, 3)
        self.graph.setSizePolicy(
            qtw.QSizePolicy.Expanding, qtw.QSizePolicy.Expanding)

        self._rh_layout.addWidget(self.graph_data_choice)
        self._rh_layout.addWidget(self._graph_buttons)
        self._rh_layout.addLayout(self.textboxes_layout, 2)


    def _make_connections(self):

        self._lh_form.signal_beep_clicked.connect(sound_engine.good_beep)
        self._lh_form.signal_save_clicked.connect(self.save_preset_to_pick_file)
        self._lh_form.signal_load_clicked.connect(self.load_preset_with_pick_file)
        self._lh_form.signal_new_clicked.connect(self.duplicate_window)


    def _add_status_bar(self):
        self.setStatusBar(qtw.QStatusBar())
        self.statusBar().showMessage("Test", 2000)

    def save_preset_to_pick_file(self):

        path_unverified = qtw.QFileDialog.getSaveFileName(self, caption='Save to file..',
                                                          dir=self.global_settings.last_used_folder,
                                                          filter='Speaker stuff files (*.ssf)',
                                                          )
        # filter not working as expected, saves files without file extension ssf
        try:
            file = path_unverified[0]
            if file:
                assert os.path.isdir(os.path.dirname(file))
                self.global_settings.update_attr(
                    "last_used_folder", os.path.dirname(file))
            else:
                return  # nothing was selected, pick file canceled
        except:
            raise NotADirectoryError

        json_string = json.dumps(
            self._lh_form.get_form_values(), indent=4)
        with open(file, "wt") as f:
            f.write(json_string)

    def load_preset_with_pick_file(self):
        file = qtw.QFileDialog.getOpenFileName(self, caption='Open file..',
                                               dir=self.global_settings.last_used_folder,
                                               filter='Speaker stuff files (*.ssf)',
                                               )[0]
        if file:
            self.load_preset_file(file)
        else:
            pass  # canceled file select

    def load_preset_file(self, file):

        try:
            os.path.isfile(file)
        except:
            raise FileNotFoundError()
            return

        self.global_settings.update_attr(
            "last_used_folder", os.path.dirname(file))
        with open(file, "rt") as f:
            self._lh_form.update_form_values(json.load(f))

    def duplicate_window(self):
        self.signal_new_window.emit(
            {"user_form_dict": self._lh_form.get_form_values()})


def error_handler(etype, value, tb):
    global app
    error_msg = ''.join(traceback.format_exception(etype, value, tb))
    message_box = qtw.QMessageBox(qtw.QMessageBox.Warning,
                                  "Error",
                                  error_msg +
                                  "\nYour application may now be in an unstable state."
                                  "\n\nThis event will be logged unless ignored.",
                                  )
    message_box.addButton(qtw.QMessageBox.Ignore)
    close_button = message_box.addButton(qtw.QMessageBox.Close)

    message_box.setEscapeButton(qtw.QMessageBox.Ignore)
    message_box.setDefaultButton(qtw.QMessageBox.Close)

    close_button.clicked.connect(logging.warning(error_msg))

    message_box.exec()


def parse_args(settings):
    import argparse

    parser = argparse.ArgumentParser(prog=f"Speaker stuff calculator version {settings.version}",
                                     description="Main module for application.",
                                     epilog="Kerem Basaran - 2023",
                                     )
    parser.add_argument('infile', nargs='?', type=argparse.FileType('r'),
                        help="Path to a '*.ssf' file. This will open with preset values.")

    return parser.parse_args()


if __name__ == "__main__":
    settings = pwi.Settings()
    args = parse_args(settings)

    if not (app := qtw.QApplication.instance()):
        app = qtw.QApplication(sys.argv)
        # there is a new recommendation with qApp but how to dod the sys.argv with that?

    sound_engine = SoundEngine(settings)
    sound_engine_thread = qtc.QThread()
    sound_engine.moveToThread(sound_engine_thread)
    sound_engine_thread.start(qtc.QThread.HighPriority)
    # app.aboutToQuit.connect(sound_engine.release_all)  # is this necessary??
    sys.excepthook = error_handler

    def new_window(**kwargs):
        mw = MainWindow(settings, sound_engine, **kwargs)
        mw.signal_new_window.connect(lambda kwargs: new_window(**kwargs))
        mw.show()
        return mw

    windows = []
    if args.infile:
        mw = new_window(open_user_file=args.infile.name)
        mw.status_bar().show_message(f"Opened file '{args.infile.name}'")
    else:
        windows.append(new_window())

    app.exec()
