import os
import sys
import traceback
import numpy as np
from dataclasses import dataclass, fields
import json

from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc
from PySide6 import QtGui as qtg

import sounddevice as sd
import electroacoustical as eac
from graphing import MatplotlibWidget

import logging
logging.basicConfig(level=logging.INFO)

# https://realpython.com/python-super/#an-overview-of-pythons-super-function
# super(super_of_which_class?=this class, in_which_object?=self)
# The parameterless call to super() is recommended and sufficient for most use cases

@dataclass
class Settings:
    version: str = '0.2.0'
    GAMMA: float = 1.401  # adiabatic index of air
    P0: int = 101325
    RHO: float = 1.1839  # 25 degrees celcius
    Kair: float = 101325 * RHO
    c_air: float = (P0 * GAMMA / RHO)**0.5
    vc_table_file = os.path.join(os.getcwd(), 'SSC_data', 'WIRE_TABLE.csv')
    f_min: int = 10
    f_max: int = 3000
    ppo: int = 48 * 8
    FS: int = 48000
    A_beep: int = 0.1
    T_beep = 0.1
    freq_good_beep: float = 1175
    freq_bad_beep: float = freq_good_beep / 2
    last_used_folder: str = os.path.expanduser('~')

    def __post_init__(self):
        self.settings_sys = qtc.QSettings(
            'kbasaran', f'Speaker Stuff {self.version}')
        self.read_all_from_system()

    def update_attr(self, attr_name, new_val):
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


settings = Settings()


class SoundEngine(qtc.QThread):
    def __init__(self, settings):
        super().__init__()
        self.FS = sd.query_devices(device=sd.default.device, kind='output',
                                   )["default_samplerate"]
        self.start_stream()

    def run(self):
        self.start_stream()
        # do a start beep
        self.beep(1, 200)

    def start_stream(self):
        self.stream = sd.OutputStream(samplerate=self.FS, channels=2)
        self.stream.start()

    @qtc.Slot()
    def wait(self):
        self.msleep(1000)

    @qtc.Slot(float, str)
    def beep(self, T, freq):
        t = np.arange(T * self.FS) / self.FS
        y = settings.A_beep * np.sin(t * 2 * np.pi * freq)
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


class FloatSpinBox(qtw.QDoubleSpinBox):
    def __init__(self, name, tooltip,
                 decimals=2,
                 min_max=(0.01, 999.99),
                 ratio_to_SI=1,
                 ):
        self._name = name
        super().__init__()
        self.setToolTip(tooltip)
        self.step_type = qtw.QAbstractSpinBox.StepType.AdaptiveDecimalStepType
        self.decimals = decimals
        if min_max:
            self.setRange(*min_max)

    def user_values_storage(self, user_data_widgets: dict):
        user_data_widgets[self._name] = self


class IntSpinBox(qtw.QSpinBox):
    def __init__(self, name, tooltip,
                 min_max=(0.01, 999.99),
                 ratio_to_SI=1,
                 ):
        self._name = name
        super().__init__()
        self.setToolTip(tooltip)
        if min_max:
            self.setRange(*min_max)

    def user_values_storage(self, user_data_widgets: dict):
        user_data_widgets[self._name] = self


class LineTextBox(qtw.QLineEdit):
    def __init__(self, name, tooltip):
        self._name = name
        super().__init__()
        self.setToolTip(tooltip)

    def user_values_storage(self, user_data_widgets: dict):
        user_data_widgets[self._name] = self


class SunkenLine(qtw.QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(qtw.QFrame.HLine)
        self.setFrameShadow(qtw.QFrame.Sunken)
        self.setContentsMargins(0, 10, 0, 10)


class Title(qtw.QLabel):
    def __init__(self, text):
        super().__init__()
        self.setText(text)
        self.setStyleSheet("font-weight: bold")
        self.setAlignment(qtg.Qt.AlignmentFlag.AlignCenter)


class PushButtonGroup(qtw.QWidget):
    def __init__(self, names: dict, tooltips: dict, vertical=False):
        # both names and tooltips have the same keys: short_name's
        # values for names: text
        self._buttons = dict()
        super().__init__()
        layout = qtw.QVBoxLayout(self) if vertical else qtw.QHBoxLayout(self)
        for key, val in names.items():
            name = key + "_button"
            button = qtw.QPushButton(val)
            button.setToolTip(tooltips[key])
            layout.addWidget(button)
            self._buttons[name] = button

    def user_values_storage(self, user_data_widgets: dict):
        for name, button in self._buttons.items():
            user_data_widgets[name] = button


class ChoiceButtonGroup(qtw.QWidget):
    def __init__(self, name, names: dict, tooltips: dict, vertical=False):
        # keys for names: integers
        # values for names: text
        self._name = name
        super().__init__()
        self.button_group = qtw.QButtonGroup()
        layout = qtw.QVBoxLayout(self) if vertical else qtw.QHBoxLayout(self)
        for key, val in names.items():
            button = qtw.QRadioButton(val)
            button.setToolTip(tooltips[key])
            self.button_group.addButton(button, key)
            layout.addWidget(button)
        self.button_group.buttons()[0].setChecked(True)

    def user_values_storage(self, user_data_widgets: dict):
        user_data_widgets[self._name] = self.button_group


class ComboBox(qtw.QComboBox):
    def __init__(self, name, tooltip,
                 items: list):
        self._name = name
        super().__init__()
        self.setToolTip(tooltip)
        for item in items:
            self.addItem(*item)  # tuple with userData, therefore *

    def user_values_storage(self, user_data_widgets: dict):
        user_data_widgets[self._name] = self


class SubForm(qtw.QWidget):
    def __init__(self):
        super().__init__()
        self._layout = qtw.QFormLayout(self)


class LeftHandForm(qtw.QWidget):
    signal_save_clicked = qtc.Signal()
    signal_load_clicked = qtc.Signal()
    signal_new_clicked = qtc.Signal()

    def __init__(self):
        super().__init__()
        self._user_input_widgets = dict()
        self._layout = qtw.QFormLayout(self)
        self._populate_form()
        self._make_connections()

    def _add_row(self, obj, description=None, into_form=None):
        if into_form:
            layout = into_form.layout()
        else:
            layout = self.layout()

        if description:
            layout.addRow(description, obj)
        else:
            layout.addRow(obj)

        if hasattr(obj, "user_values_storage"):
            obj.user_values_storage(self._user_input_widgets)

    def _populate_form(self):

        self._add_row(PushButtonGroup({"load": "Load", "save": "Save", "new": "New"},
                                      {"load": "Load parameters from a file",
                                       "save": "Save parameters to a file",
                                       "new": "Create another instance of the application, carrying all existing parameters",
                                       }))

        self._add_row(Title("General speaker specifications"))

        self._add_row(FloatSpinBox("fs", "Undamped resonance frequency of the speaker in free-air condition",
                                   decimals=1,
                                   min_max=(0.1, settings.f_max),
                                   ),
                      description="fs (Hz)",
                      )

        self._add_row(FloatSpinBox("Qms", "Quality factor of speaker, only the mechanical part",
                                   ),
                      description="Qms",
                      )

        self._add_row(FloatSpinBox("Xmax", "Peak excursion allowed, one way",
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Xmax (mm)",
                      )

        self._add_row(FloatSpinBox("dead_mass", "Moving mass excluding the coil itself and the air.|n(Dead mass = Mmd - coil mass)",
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Dead mass (g)",
                      )

        self._add_row(FloatSpinBox("Sd", "Diaphragm effective surface area",
                                   ratio_to_SI=1e-4,
                                   ),
                      description="Sd (cm²)"
                      )

        # ----------------------------------------------------
        self._add_row(SunkenLine())

        self._add_row(ComboBox("motor_spec_type", "Choose which parameters you want to input to make the motor strength calculation",
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

        self._add_row(self.motor_definition_stacked)

        # Make the first page of stacked widget for "Define Coil Dimensions and Average B"
        motor_definition_p1 = SubForm()
        self.motor_definition_stacked.addWidget(motor_definition_p1)

        self._add_row(FloatSpinBox("target_Rdc", "Rdc value that needs to be approached while calculating an appropriate coil and winding",
                                   ),
                      description="Target Rdc (ohm)",
                      into_form=motor_definition_p1,
                      )

        self._add_row(FloatSpinBox("former_ID", "Internal diameter of the coil former",
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Coil Former ID (mm)",
                      into_form=motor_definition_p1,
                      )

        self._add_row(IntSpinBox("t_former", "Thickness of the coil former",
                                 ratio_to_SI=1e-6,
                                 ),
                      description="Former thickness (\u03BCm)",
                      into_form=motor_definition_p1,
                      )

        self._add_row(FloatSpinBox("h_winding", "Desired height of the coil winding",
                                   ),
                      description="Coil winding height (mm)",
                      into_form=motor_definition_p1,
                      )

        self._add_row(FloatSpinBox("B_average", "Average B field across the coil windings."
                                   "\nNeeds to be calculated separately and input here.",
                                   decimals=3,
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Average B field on coil (mT)",
                      into_form=motor_definition_p1,
                      )

        self._add_row(LineTextBox("N_layer_options", "Enter the number of winding layer options that are accepted."
                                  "\nUse integers with a comma in between, e.g.: '2, 4'",
                                  ),
                      description="Number of layer options",
                      into_form=motor_definition_p1,
                      )

        self._add_row(PushButtonGroup({"update_coil_choices": "Update coil choices"},
                                      {"update_coil_choices": "Populate the below dropdown with possible coil choices for the given parameters"},
                                      ),
                      into_form=motor_definition_p1,
                      )

        self._add_row(ComboBox("coil_options", "Select coil winding to be used for calculations",
                               [("SV", "data1"),
                                ("CCAW", "data2"),
                                ("MEGA", "data3"), ],
                               ),
                      into_form=motor_definition_p1,
                      )

        # Make the second page of stacked widget for "Define Bl, Rdc, Mmd"
        motor_definition_p2 = SubForm()
        self.motor_definition_stacked.addWidget(motor_definition_p2)

        self._add_row(FloatSpinBox("Bl_p2", "Force factor",
                                   ),
                      description="Bl (Tm)",
                      into_form=motor_definition_p2,
                      )

        self._add_row(IntSpinBox("Rdc_p2", "DC resistance",
                                 ),
                      description="Rdc (ohm)",
                      into_form=motor_definition_p2,
                      )

        self._add_row(FloatSpinBox("Mmd_p2",
                                   "Moving mass, excluding coupled air mass",
                                   decimals=3,
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Mmd (g)",
                      into_form=motor_definition_p2,
                      )

        # Make the third page of stacked widget for "Define Bl, Rdc, Mms"
        motor_definition_p3 = SubForm()
        self.motor_definition_stacked.addWidget(motor_definition_p3)

        self._add_row(FloatSpinBox("Bl_p3",
                                   "Force factor",
                                   ),
                      description="Bl (Tm)",
                      into_form=motor_definition_p3,
                      )

        self._add_row(IntSpinBox("Rdc_p3",
                                 "DC resistance",
                                 ),
                      description="Rdc (ohm)",
                      into_form=motor_definition_p3,
                      )

        self._add_row(FloatSpinBox("Mms_p3",
                                   "Moving mass, including coupled air mass",
                                   decimals=3,
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Mms (g)",
                      into_form=motor_definition_p3,
                      )

        # ----------------------------------------------------
        self._add_row(SunkenLine())

        self._add_row(Title("Motor mechanical specifications"))

        self._add_row(FloatSpinBox("h_top_plate", "Thickness of the top plate (also called washer)",
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Top plate thickness (mm)",
                      )

        self._add_row(IntSpinBox("airgap_clearance_inner", "Clearance on the inner side of the coil former",
                                 ratio_to_SI=1e-6,
                                 ),
                      description="Airgap inner clearance (\u03BCm)",
                      )

        self._add_row(IntSpinBox("airgap_clearance_outer", "Clearance on the outer side of the coil windings",
                                 ratio_to_SI=1e-6,
                                 ),
                      description="Airgap outer clearance (\u03BCm)",
                      )

        self._add_row(FloatSpinBox("former_extension_under_coil", "Extension of the coil former below the coil windings",
                                   ratio_to_SI=1e-3,
                                   ),
                      description="Former bottom ext. (mm)",
                      )

        # ----------------------------------------------------
        self._add_row(SunkenLine())

        self._add_row(Title("Closed box specifications"))

        self._add_row(FloatSpinBox("Vb", "Internal free volume filled by air",
                          ratio_to_SI=1e-3,
                          ),
                      description="Box internal volume (l)",
                      )

        self._add_row(FloatSpinBox("Qa", "Quality factor of the speaker, mechanical part due to losses in box",
                          decimals=1
                          ),
                      description="Qa - box absorption",
                      )

        self._add_row(SunkenLine())  # ----------------------------------------------------

        self._add_row(Title("Second degree of freedom"))

        self._add_row(FloatSpinBox("k2", "Stiffness between the second body and the ground",
                          ratio_to_SI=1e3,
                          ),
                      description="Stiffness (N/mm)",
                      )

        self._add_row(FloatSpinBox("m2", "Mass of the second body",
                          ratio_to_SI=1e-3,
                          ),
                      description="Mass (g)",
                      )

        self._add_row(FloatSpinBox("c2", "Damping coefficient between the second body and the ground",
                          ),
                      description="Damping coefficient (kg/s)",
                      )

        self._add_row(SunkenLine())  # ----------------------------------------------------

        self._add_row(Title("Electrical Input"))

        self._add_row(FloatSpinBox("Rs",
                          "The resistance between the speaker coil and the voltage source."
                          "\nMay be due to cables, speaker leadwires, connectors etc."
                          "\nCauses resistive loss at the input.",
                          ),
                      description="Series resistance",
                      )

        self._add_row(ComboBox("excitation_unit", "Choose which type of input excitation you want to define.",
                            [("Volts", "V"),
                            ("Watts @Rdc", "W"),
                            ("Watss @Rnom", "Wn")
                            ],
                            ),
                      description="Unit",
                      )

        self._add_row(FloatSpinBox("excitation_value", "The value for input excitation, in units chosen above",
                          ),
                      description="Excitation value",
                      )

        self._add_row(FloatSpinBox("nominal_impedance", "Nominal impedance of the speaker. This is necessary to calculate the voltage input"
                          "\nwhen 'Watts @Rnom' is selected as the input excitation unit.",
                          ),
                      description="Nominal impedance",
                      )

        self._add_row(SunkenLine())  # ----------------------------------------------------

        # self._add_row(Title("System type")

        # self._add_row(ChoiceButtonGroup("box_type",
        #                         {0: "Free-air", 1: "Closed box"},
        #                         {0: "Free-air", 1: "Closed box"},
        #                         vertical=False,
        #                         )

        # self._add_row(ChoiceButtonGroup("dof",
        #                         {0: "1 dof", 1: "2 dof"},
        #                         {0: "1 dof", 1: "2 dof"},
        #                         vertical=False,
        #                         )

    def update_user_form_values(self, values_new: dict):
        no_dict_key_for_widget = set(
            [key for key in self._user_input_widgets.keys() if "_button" not in key])  # works???????????????????????
        no_widget_for_dict_key = set()
        for key, value_new in values_new.items():
            try:
                obj = self._user_input_widgets[key]

                if isinstance(obj, qtw.QComboBox):
                    assert isinstance(value_new, dict)
                    obj.clear()
                    # assert all([key in value_new.keys() for key in ["items", "current_index"]])
                    for item in value_new["items"]:
                        obj.addItem(*item)
                    obj.setCurrentIndex(value_new["current_index"])

                elif isinstance(obj, qtw.QLineEdit):
                    assert isinstance(value_new, str)
                    obj.setText(value_new)

                elif isinstance(obj, qtw.QPushButton):
                    raise TypeError(
                        f"Don't know what to do with value_new={value_new} for button {key}.")

                elif isinstance(obj, qtw.QButtonGroup):
                    obj.button(value_new).setChecked(True)

                else:
                    assert type(value_new) == type(obj.value())
                    obj.setValue(value_new)

                # finally
                no_dict_key_for_widget.discard(key)

            except KeyError:
                no_widget_for_dict_key.update((key,))

        if no_widget_for_dict_key | no_dict_key_for_widget:
            raise ValueError(f"No widget(s) found for the keys: '{no_widget_for_dict_key}'\n"
                             f"No data found to update the widget(s): '{no_dict_key_for_widget}'"
                             )

    def get_user_form_values(self) -> dict:
        values = {}
        for key, obj in self._user_input_widgets.items():

            if "_button" in key:
                continue

            if isinstance(obj, qtw.QComboBox):
                obj_value = {"items": [], "current_index": 0}
                for i_item in range(obj.count()):
                    item_text = obj.itemText(i_item)
                    item_data = obj.itemData(i_item)
                    obj_value["items"].append((item_text, item_data))
                obj_value["current_index"] = obj.currentIndex()

            elif isinstance(obj, qtw.QLineEdit):
                obj_value = obj.text()

            elif isinstance(obj, qtw.QButtonGroup):
                obj_value = obj.checkedId()

            else:
                obj_value = obj.value()

            values[key] = obj_value

        logging.debug("Return of 'get_user_form_values")
        for val, key in values.items():
            logging.debug(val, type(val), key, type(key))

        return values

    def _make_connections(self):
        def raise_error():
            raise FileExistsError
        self._user_input_widgets["load_button"].clicked.connect(
            self.signal_load_clicked)
        self._user_input_widgets["save_button"].clicked.connect(
            self.signal_save_clicked)
        self._user_input_widgets["new_button"].clicked.connect(
            self.signal_new_clicked)


class MainWindow(qtw.QMainWindow):
    signal_new_window = qtc.Signal(dict)  # new_window with kwargs as dict
    signal_beep = qtc.Signal(float, float)

    def __init__(self, settings, sound_engine, user_form_dict=None, open_user_file=None):
        super().__init__()
        self.global_settings = settings
        self.create_core_objects()
        self.create_widgets()
        self.place_widgets()
        self._add_status_bar()
        self.make_connections()
        if user_form_dict:
            self._lh_form.update_user_form_values(user_form_dict)
        elif open_user_file:
            self.load_preset_file(open_user_file)

    def create_core_objects(self):
        pass

    def create_widgets(self):
        self._lh_form = LeftHandForm()
        self._beep_pusbutton = qtw.QPushButton("Beep test")
        self.graph = MatplotlibWidget()

        self._rh_widget = qtw.QWidget()

    def place_widgets(self):
        self._center_widget = qtw.QWidget()
        self._center_layout = qtw.QHBoxLayout(self._center_widget)
        self.setCentralWidget(self._center_widget)

        self._center_layout.addWidget(self._lh_form)
        self._lh_form.setSizePolicy(qtw.QSizePolicy.Fixed, qtw.QSizePolicy.Fixed)

        self._center_layout.addWidget(self._rh_widget)

        self._rh_layout = qtw.QVBoxLayout(self._rh_widget)
        self._rh_layout.addWidget(self._beep_pusbutton)
        self._rh_layout.addWidget(self.graph)
        self.graph.setSizePolicy(qtw.QSizePolicy.Expanding, qtw.QSizePolicy.Expanding)

    def make_connections(self):
        self._beep_pusbutton.clicked.connect(
            lambda: self.signal_beep.emit(0.5, 100)
        )
        self.signal_beep.connect(sound_engine.beep)

        self._lh_form.signal_save_clicked.connect(
            self.save_preset_to_pick_file)
        self._lh_form.signal_load_clicked.connect(
            self.load_preset_with_pick_file)
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
            self._lh_form.get_user_form_values(), indent=4)
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
            self._lh_form.update_user_form_values(json.load(f))

    def duplicate_window(self):
        self.signal_new_window.emit(
            {"user_form_dict": self._lh_form.get_user_form_values()})


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
    settings = Settings()
    args = parse_args(settings)

    app = qtw.QApplication.instance()
    if not app:  # there is a new recommendation with qApp but how to dod the sys.argv with that?
        app = qtw.QApplication(sys.argv)

    sound_engine = SoundEngine(settings)
    sound_engine.start(qtc.QThread.HighPriority)
    sys.excepthook = error_handler
    # app.aboutToQuit.connect(sound_engine.release_all)  # is this necessary??

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
