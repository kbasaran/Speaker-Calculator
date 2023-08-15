import os
import sys
import traceback
import numpy as np
import matplotlib.pyplot as plt
from dataclasses import dataclass, fields
import json

from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc
from PySide6 import QtGui as qtg

from __feature__ import snake_case
from __feature__ import true_property
# doesn't always work.
# e.g. can't do "main_window.central_widget = my_widget". you need to use set.
# but can do "line_edit_widget.text = text"

import sounddevice as sd
import electroacoustical as eac
from collections import OrderedDict

import logging
logging.basicConfig(level=logging.INFO)

# https://realpython.com/python-super/#an-overview-of-pythons-super-function
# super(super_of_which_class?=this class, in_which_object?=self)
# The parameterless call to super() is recommended and sufficient for most use cases


@dataclass
class Settings:
    version: str = '0.2.0'
    FS: int = 44100
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

    def update_attr(self, attr_name, new_val):
        assert type(getattr(self, attr_name)) == type(new_val)
        setattr(self, attr_name, new_val)
        self.settings_sys.set_value(attr_name, getattr(self, attr_name))

    def write_all_to_system(self):
        for field in fields(self):
            self.settings_sys.set_value(field.name, getattr(self, field.name))

    def read_all_from_system(self):
        for field in fields(self):
            setattr(self, field.name, self.settings_sys.value(field.name, field.default, type=type(field.default)))

    def __post_init__(self):
        self.settings_sys = qtc.QSettings('kbasaran', f'Speaker Stuff {self.version}')
        self.read_all_from_system()

settings = Settings()


class SoundEngine(qtc.QThread):
    def __init__(self, settings):
        super().__init__()
        self.FS = settings.FS
        self.start_stream()

    def run(self):
        self.start_stream()
        # do a start beep
        # self.beep(1, 100)

    def start_stream(self):
        self.stream = sd.Stream(samplerate=self.FS, channels=2)
        self.dtype = self.stream.dtype
        self.channel_count = self.stream.channels[0]
        self.stream.start()


    @qtc.Slot()
    def wait(self):
        self.msleep(1000)


    @qtc.Slot(float, str)
    def beep(self, T, freq):
        t = np.arange(T * self.FS) / self.FS
        y = np.tile(settings.A_beep * np.sin(t * 2 * np.pi * freq), self.channel_count)
        y = y.reshape((len(y) // self.channel_count, self.channel_count)).astype(self.dtype)
        self.stream.write(y)

    @qtc.Slot()
    def good_beep(self):
        self.beep(settings.T_beep, settings.freq_good_beep)

    @qtc.Slot()
    def bad_beep(self):
        self.beep(settings.T_beep, settings.freq_bad_beep)


class UserForm(qtc.QObject):
    signal_save_clicked = qtc.Signal()
    signal_load_clicked = qtc.Signal()
    signal_new_clicked = qtc.Signal()

    def __init__(self):
        super().__init__()
        self._form_items = OrderedDict()
        self._form_layout = qtw.QFormLayout()
        self.widget = qtw.QWidget()
        self.widget.set_layout(self._form_layout)
        self.create_form_items()
        self.make_connections()

    def add_line(self, into_layout=None):
        into_layout = self._form_layout if not into_layout else into_layout
        line = qtw.QFrame()
        line.frame_shape = qtw.QFrame.HLine
        line.frame_shadow = qtw.QFrame.Sunken
        line.content_margins = (0, 10, 0, 10)
        # n_line =  [name[:4] == "line" for name in self._form_items.keys()].count(True)
        # self._form_items["line_" + str(n_line)] = line
        into_layout.add_row(line)

    def add_title(self, text: str, into_layout=None):
        into_layout = self._form_layout if not into_layout else into_layout
        title = qtw.QLabel()
        title.text = text
        title.style_sheet = "font-weight: bold"
        title.alignment = qtg.Qt.AlignmentFlag.AlignCenter
        # n_title =  [name[:5] == "title" for name in self._form_items.keys()].count(True)
        # self._form_items["title_" + str(n_title)] = title
        into_layout.add_row(title)

    def add_pushbuttons(self, buttons: dict, tooltip: dict, vertical=False, into_layout=None):
        into_layout = self._form_layout if not into_layout else into_layout
        layout = qtw.QVBoxLayout() if vertical else qtw.QHBoxLayout()
        obj = qtw.QWidget()
        obj.set_layout(layout)
        for key, val in buttons.items():
            name = key + "_button"
            button = qtw.QPushButton(val)
            button.tool_tip = tooltip[key]
            self._form_items[name] = button
            layout.add_widget(button)
        into_layout.add_row(obj)

    def add_spin_box(self, name: str, description: str, tooltip: str,
                     data_type: str,
                     decimals=2,
                     min_max=(0.01, 999.99),
                     ratio_to_SI=1,
                     into_layout=None,
                     ):
        into_layout = self._form_layout if not into_layout else into_layout
        match data_type:
            case "double_float":
                obj = qtw.QDoubleSpinBox()
                obj.step_type = qtw.QAbstractSpinBox.StepType.AdaptiveDecimalStepType
                obj.decimals = decimals
            case "integer":
                obj = qtw.QSpinBox()
            case _:
                raise ValueError("'data_type' not recognized")
        # obj.setMinimumSize(52, 18)
        if min_max:
            obj.set_range(*min_max)
        obj.tool_tip = tooltip
        self._form_items[name] = obj
        into_layout.add_row(description, obj)

    def add_text_edit_box(self, name: str, description: str, tooltip: str, into_layout=None):
        into_layout = self._form_layout if not into_layout else into_layout
        obj = qtw.QLineEdit()
        obj.tool_tip = tooltip
        # obj.setMinimumSize(52, 18)
        self._form_items[name] = obj
        into_layout.add_row(description, obj)

    def add_combo_box(self, name: str, description: str, tooltip: str,
                     items: list,
                     into_layout=None,
                     ):
        into_layout = self._form_layout if not into_layout else into_layout
        # items can contain elements that are tuples.
        # in that case the second part is user data
        obj = qtw.QComboBox()
        # obj.setMinimumSize(52, 18)
        for item in items:
            obj.add_item(*item)  # tuple with userData, therefore *
        obj.tool_tip = tooltip
        self._form_items[name] = obj
        if description:
            into_layout.add_row(description, obj)
        else:
            into_layout.add_row(obj)

    def add_choice_buttons(self, name: str, tooltip: dict, choices: dict, vertical=False, into_layout=None):
        into_layout = self._form_layout if not into_layout else into_layout
        button_group = qtw.QButtonGroup()
        layout = qtw.QVBoxLayout() if vertical else qtw.QHBoxLayout()
        obj = qtw.QWidget()
        obj.set_layout(layout)

        for key, val in choices.items():
            button = qtw.QRadioButton(val)
            button.tool_tip = tooltip[key]
            button_group.add_button(button, key)
            layout.add_widget(button)

        button_group.buttons()[0].set_checked(True)
        self._form_items[name] = button_group
        into_layout.add_row(obj)

    def create_sub_form(self):
        layout = qtw.QFormLayout()
        sub_form = qtw.QWidget()
        sub_form.set_layout(layout)
        return sub_form, layout

    def set_widget_value(self, obj, value):
        if isinstance(obj, qtw.QComboBox):
            assert isinstance(value, tuple)
        else:
            assert type(value) == type(obj.value)


    def get_widget_value(self, obj):
        if isinstance(obj, qtw.QComboBox):
            return
        else:
            return

    def create_form_items(self):
        self.add_pushbuttons({"load": "Load", "save": "Save", "new": "New"},
                             {"load": "Load parameters from a file",
                              "save": "Save parameters to a file",
                              "new": "Create another instance of the application, carrying all existing parameters",
                              }
                              )
        self.add_title("General speaker specifications")  #--------------------
        
        self.add_spin_box("fs", "fs (Hz)",
                          data_type="double_float",
                          tooltip="Undamped resonance frequency of the speaker in free-air condition",
                          decimals=1,
                          min_max=(0.1, settings.f_max),
                          )

        self.add_spin_box("Qms", "Qms",
                          data_type="double_float",
                          tooltip="Quality factor of speaker, only the mechanical part",
                          )

        self.add_spin_box("Xmax", "Xmax (mm)",
                          data_type="double_float",
                          tooltip="Peak excursion allowed, one way",
                          ratio_to_SI=1e-3,
                          )

        self.add_spin_box("dead_mass", "Dead mass (g)",
                          data_type="double_float",
                          tooltip="Moving mass excluding the coil itself and the air.|n(Dead mass = Mmd - coil mass)",
                          ratio_to_SI=1e-3,
                          )
        
        self.add_spin_box("Sd", "Sd (cm²)",
                          data_type="double_float",
                          tooltip="Diaphragm effective surface area",
                          ratio_to_SI=1e-4,
                          )

        self.add_line()  # ----------------------------------------------------

        self.add_combo_box("motor_spec_type", None,
                           "Choose which parameters you want to input to make the motor strength calculation",
                           [("Define Coil Dimensions and Average B", "define_coil"),
                            ("Define Bl, Rdc, Mmd", "define_Bl_Re_Mmd"),
                            ("Define Bl, Rdc, Mms", "define_Bl_Re_Mms"),
                            ]
                           )
        self._form_items["motor_spec_type"].set_style_sheet("font-weight: bold")

        ## Make a stacked widget for different motor definition parameters
        self.motor_definition_stacked = qtw.QStackedWidget()
        self._form_layout.add_row(self.motor_definition_stacked)
        self._form_items["motor_spec_type"].currentIndexChanged.connect(
            self.motor_definition_stacked.set_current_index
            )
        
        ## Make the first page of stacked widget for "Define Coil Dimensions and Average B"    
        motor_definition_p1, motor_definition_p1_layout = self.create_sub_form()
        self.motor_definition_stacked.add_widget(motor_definition_p1)

        self.add_spin_box("target_Rdc", "Target Rdc (ohm)",
                          "Rdc value that needs to be approached while calculating an appropriate coil and winding",
                          "double_float", into_layout=motor_definition_p1_layout,
                          )

        self.add_spin_box("former_ID", "Coil Former ID (mm)",
                          "Internal diameter of the coil former",
                          "double_float", into_layout=motor_definition_p1_layout,
                          ratio_to_SI=1e-3,
                          )
        
        self.add_spin_box("t_former", "Former thickness (\u03BCm)",
                          "Thickness of the coil former",
                          "integer", into_layout=motor_definition_p1_layout,
                          ratio_to_SI=1e-6,
                          )
        
        self.add_spin_box("h_winding", "Coil winding height (mm)",
                          "Desired height of the coil winding",
                          "double_float", into_layout=motor_definition_p1_layout,
                          )
        
        self.add_spin_box("B_average", "Average B field on coil (mT)",
                          "Average B field across the coil windings."
                          "\nNeeds to be calculated separately and input here.",
                          "double_float", into_layout=motor_definition_p1_layout,
                          decimals=3,
                          ratio_to_SI=1e-3,
                          )
        
        self.add_text_edit_box("N_layer_options", "Number of layer options",
                          "Enter the number of winding layer options that are accepted."
                          "\nUse integers with a comma in between, e.g.: '2, 4'",
                          into_layout=motor_definition_p1_layout,
                          )

        self.add_pushbuttons({"update_coil_choices": "Update coil choices"},
                             {"update_coil_choices": "Populate the below dropdown with possible coil choices for the given parameters"},
                             into_layout=motor_definition_p1_layout,
                             )
    
        self.add_combo_box("coil_options", None,
                           "Select coil winding to be used for calculations",
                           [("SV", "data1"),
                            ("CCAW", "data2"),
                            ("MEGA", "data3"),
                            ],
                           into_layout=motor_definition_p1_layout,
                           )


        ## Make the second page of stacked widget for "Define Bl, Rdc, Mmd"
        motor_definition_p2, motor_definition_p2_layout = self.create_sub_form()
        self.motor_definition_stacked.add_widget(motor_definition_p2)

        self.add_spin_box("Bl_p2", "Bl (Tm)",
                          "Force factor",
                          "double_float", into_layout=motor_definition_p2_layout,
                          )
        
        self.add_spin_box("Rdc_p2", "Rdc (ohm)",
                          "DC resistance",
                          "integer", into_layout=motor_definition_p2_layout,
                          )
        
        self.add_spin_box("Mmd_p2", "Mmd (g)",
                          "Moving mass, excluding coupled air mass",
                          "double_float", into_layout=motor_definition_p2_layout,
                          decimals=3,
                          ratio_to_SI=1e-3,
                          )


        ## Make the third page of stacked widget for "Define Bl, Rdc, Mms"
        motor_definition_p3, motor_definition_p3_layout = self.create_sub_form()
        self.motor_definition_stacked.add_widget(motor_definition_p3)

        self.add_spin_box("Bl_p3", "Bl (Tm)",
                          "Force factor",
                          "double_float", into_layout=motor_definition_p3_layout,
                          )
        
        self.add_spin_box("Rdc_p3", "Rdc (ohm)",
                          "DC resistance",
                          "integer", into_layout=motor_definition_p3_layout,
                          )
        
        self.add_spin_box("Mms_p3", "Mms (g)",
                          "Moving mass, including coupled air mass ",
                          "double_float", into_layout=motor_definition_p3_layout,
                          decimals=3,
                          ratio_to_SI=1e-3,
                          )

        self.add_line()  # ----------------------------------------------------

        self.add_title("Motor mechanical specifications")
        
        self.add_spin_box("h_top_plate", "Top plate thickness (mm)",
                          "Thickness of the top plate (also called washer)",
                          "double_float",
                          ratio_to_SI=1e-3,
                          )

        self.add_spin_box("airgap_clearance_inner", "Airgap inner clearance (\u03BCm)",
                          "Clearance on the inner side of the coil former",
                          "integer",
                          ratio_to_SI=1e-6,
                          )
        
        self.add_spin_box("airgap_clearance_outer", "Airgap outer clearance (\u03BCm)",
                          "Clearance on the outer side of the coil windings",
                          "integer",
                          ratio_to_SI=1e-6,
                          )
        
        self.add_spin_box("former_extension_under_coil", "Former bottom ext. (mm)",
                          "Extension of the coil former below the coil windings",
                          "double_float",
                          ratio_to_SI=1e-3,
                          )

        self.add_line()  # ----------------------------------------------------

        self.add_title("Closed box specifications")
        
        self.add_spin_box("Vb", "Box internal volume (l)",
                          "Internal free volume filled by air",
                          "double_float",
                          ratio_to_SI=1e-3,
                          )

        self.add_spin_box("Qa", "Qa - box absorption",
                          "Quality factor of the speaker, mechanical part due to losses in box",
                          "double_float",
                          decimals=1
                          )

        self.add_line()  # ----------------------------------------------------

        self.add_title("Second degree of freedom")

        self.add_spin_box("k2", "Stiffness (N/mm)",
                          "Stiffness between the second body and the ground",
                          "double_float",
                          ratio_to_SI=1e3,
                          )

        self.add_spin_box("m2", "Mass (g)",
                          "Mass of the second body",
                          "double_float",
                          ratio_to_SI=1e-3,
                          )
        
        self.add_spin_box("c2", "Damping coefficient (kg/s)",
                          "Damping coefficient between the second body and the ground",
                          "double_float",
                          )

        self.add_line()  # ----------------------------------------------------

        self.add_title("Electrical Input")

        self.add_spin_box("Rs", "Series resistance",
                          "The resistance between the speaker coil and the voltage source."
                          "\nMay be due to cables, speaker leadwires, connectors etc."
                          "\nCauses resistive loss at the input.",
                          "double_float",
                          )

        self.add_combo_box("excitation_unit", "Unit",
                           "Choose which type of input excitation you want to define.",
                           [("Volts", "V"),
                            ("Watts @Rdc", "W"),
                            ("Watss @Rnom", "Wn")
                            ],
                           )
        
        self.add_spin_box("excitation_value", "Excitation value",
                          "The value for input excitation, in units chosen above",
                          "double_float",
                          )

        self.add_spin_box("nominal_impedance", "Nominal impedance",
                          "Nominal impedance of the speaker. This is necessary to calculate the voltage input"
                          "\nwhen 'Watts @Rnom' is selected as the input excitation unit.",
                          "double_float",
                          )

        self.add_line()  # ----------------------------------------------------

        self.add_title("System type")

        self.add_choice_buttons("box_type",
                                {0: "Free-air", 1:"Closed box"},
                                {0: "Free-air", 1:"Closed box"},
                                vertical=False,
                                )

        self.add_choice_buttons("dof",
                                {0: "1 dof", 1:"2 dof"},
                                {0: "1 dof", 1:"2 dof"},
                                vertical=False,
                                )

    def update_user_form_values(self, values_new: dict):
        no_dict_key_for_widget = set([key for key in self._form_items.keys() if "_button" not in key])
        no_widget_for_dict_key = set()
        for key, value_new in values_new.items():                
            try:
                obj = self._form_items[key]

                if isinstance(obj, qtw.QComboBox):
                    assert isinstance(value_new, dict)
                    obj.clear()
                    # assert all([key in value_new.keys() for key in ["items", "current_index"]])
                    for item in value_new["items"]:
                        obj.add_item(*item)
                    obj.current_index = value_new["current_index"]

                elif isinstance(obj, qtw.QLineEdit):
                    assert isinstance(value_new, str)
                    obj.text = value_new

                elif isinstance(obj, qtw.QPushButton):
                    raise TypeError(f"Don't know what to do with value_new={value_new} for button {key}.")

                elif isinstance(obj, qtw.QButtonGroup):
                    obj.button(value_new).set_checked(True)

                else:
                    assert type(value_new) == type(obj.value)
                    obj.value = value_new

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
        for key, obj in self._form_items.items():
            
            if "_button" in key:
                continue

            if isinstance(obj, qtw.QComboBox):
                obj_value = {"items": [], "current_index": 0}
                for i_item in range(obj.count):
                    item_text = obj.item_text(i_item)
                    item_data = obj.item_data(i_item)
                    obj_value["items"].append( (item_text, item_data) )
                obj_value["current_index"] = obj.current_index

            elif isinstance(obj, qtw.QLineEdit):
                obj_value = obj.text

            elif isinstance(obj, qtw.QButtonGroup):
                obj_value = obj.checked_id()

            else:
                obj_value = obj.value
            
            values[key] = obj_value

        return values

    def make_connections(self):
        def raise_error():
            raise FileExistsError
        self._form_items["load_button"].clicked.connect(self.signal_load_clicked)
        self._form_items["save_button"].clicked.connect(self.signal_save_clicked)
        self._form_items["new_button"].clicked.connect(self.signal_new_clicked)

class MainWindow(qtw.QMainWindow):
    signal_new_window = qtc.Signal(dict)
    signal_beep = qtc.Signal(float, float)

    def __init__(self, settings, sound_engine, user_form_dict=None):
        super().__init__()
        self.global_settings = settings
        self.create_core_objects()
        self.create_widgets()
        self.place_widgets()
        self.make_connections()
        if user_form_dict:
            self._user_form.update_user_form_values(user_form_dict)

    def create_core_objects(self):
        pass

    def create_widgets(self):
        self._user_form = UserForm()
        self._beep_pusbutton = qtw.QPushButton("Beep test")

    def place_widgets(self):
        self._center_layout = qtw.QVBoxLayout()
        self._center_widget = qtw.QWidget()
        self._center_widget.set_layout(self._center_layout)
        self.set_central_widget(self._center_widget)

        self._center_layout.add_widget(self._user_form.widget)
        self._center_layout.add_widget(self._beep_pusbutton)

    def make_connections(self):
        self._beep_pusbutton.clicked.connect(
            lambda: self.signal_beep.emit(1, 440)
            )
        self.signal_beep.connect(sound_engine.beep)

        self._user_form.signal_save_clicked.connect(self.save_preset_to_pick_file)
        self._user_form.signal_load_clicked.connect(self.load_preset_with_pick_file)
        self._user_form.signal_new_clicked.connect(self.new_window)

    def save_preset_to_pick_file(self):

        path_unverified = qtw.QFileDialog.get_save_file_name(self, caption='Save to file..',
                                                             dir=self.global_settings.last_used_folder,
                                                             filter='Speaker stuff files (*.ssf)',
                                                             )
        try:
            file = path_unverified[0]
            if file:
                assert os.path.isdir(os.path.dirname(file))
                self.global_settings.update_attr("last_used_folder", os.path.dirname(file))
            else:
                return  # nothing was selected, pick file canceled
        except:
            raise NotADirectoryError

        json_string = json.dumps(self._user_form.get_user_form_values(), indent=4)
        with open(file, "wt") as f:
            f.write(json_string)


    def load_preset_with_pick_file(self):
        path_unverified = qtw.QFileDialog.get_open_file_name(self, caption='Open file..',
                                                             dir=self.global_settings.last_used_folder,
                                                             filter='Speaker stuff files (*.ssf)',
                                                             )
        try:
            file = path_unverified[0]
            if file:
                assert os.path.isfile(file)
            else:
                return  # nothing was selected, pick file canceled
        except:
            raise FileNotFoundError()

        self.global_settings.update_attr("last_used_folder", os.path.dirname(file))
        self.load_preset(file)

    def load_preset(self, file=None):
        with open(file, "rt") as f:
            self._user_form.update_user_form_values(json.load(f))

    def new_window(self):
        self.signal_new_window.emit(self._user_form.get_user_form_values())


def error_handler(etype, value, tb):
    global app
    error_msg = ''.join(traceback.format_exception(etype, value, tb))
    message_box = qtw.QMessageBox(qtw.QMessageBox.Warning,
                                  "Error",
                                  error_msg +
                                  "\nThis event will be logged unless ignored."
                                  "\nYour application may now be in an unstable state.",
                                  )
    message_box.add_button(qtw.QMessageBox.Ignore)
    message_box.add_button(qtw.QMessageBox.Close)

    message_box.set_escape_button(qtw.QMessageBox.Ignore)
    message_box.set_default_button(qtw.QMessageBox.Close)

    message_box.default_button().clicked.connect(logging.warning(error_msg))
    # how to connect this signal to the Close button directly instead of
    # connecting to the default button
    message_box.exec()

if __name__ == "__main__":
    sys.excepthook = error_handler

    app = qtw.QApplication(sys.argv)  # there is a new recommendation with qApp
    settings = Settings()
    sound_engine = SoundEngine(settings)
    sound_engine.start(qtc.QThread.HighPriority)

    def new_window(user_form_dict=None):
        mw = MainWindow(settings, sound_engine, user_form_dict)
        mw.signal_new_window.connect(new_window)
        mw.show()
        return mw

    new_window()
    
    app.exec()
