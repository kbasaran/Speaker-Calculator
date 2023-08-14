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
        self.beep(1, 100)

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

    def add_pushbuttons(self, buttons: dict, vertical=False, into_layout=None):
        into_layout = self._form_layout if not into_layout else into_layout
        layout = qtw.QVBoxLayout() if vertical else qtw.QHBoxLayout()
        obj = qtw.QWidget()
        obj.set_layout(layout)
        for key, val in buttons.items():
            name = key + "_button"
            button = qtw.QPushButton(val)
            self._form_items[name] = button
            layout.add_widget(button)
        into_layout.add_row(obj)

    def add_spin_box(self, name: str, description: str,
                     data_type,
                     min_max_vals,
                     coeff_to_SI=1,
                     into_layout=None,
                     ):
        into_layout = self._form_layout if not into_layout else into_layout
        match data_type:
            case "double_float":
                obj = qtw.QDoubleSpinBox()
                obj.step_type = qtw.QAbstractSpinBox.StepType.AdaptiveDecimalStepType
            case "integer":
                obj = qtw.QSpinBox()
            case _:
                raise ValueError("'data_type' not recognized")
        # obj.setMinimumSize(52, 18)
        obj.range = min_max_vals
        self._form_items[name] = obj
        into_layout.add_row(description, obj)

    def add_text_edit_box(self, name: str, description: str, into_layout=None):
        into_layout = self._form_layout if not into_layout else into_layout
        obj = qtw.QLineEdit()
        # obj.setMinimumSize(52, 18)
        self._form_items[name] = obj
        into_layout.add_row(description, obj)

    def add_combo_box(self, name: str, description=None,
                     items=[],
                     into_layout=None,
                     ):
        into_layout = self._form_layout if not into_layout else into_layout
        # items can contain elements that are tuples.
        # in that case the second part is user data
        obj = qtw.QComboBox()
        # obj.setMinimumSize(52, 18)
        for item in items:
            obj.add_item(*item)  # tuple with userData, therefore *
        self._form_items[name] = obj
        if description:
            into_layout.add_row(description, obj)
        else:
            into_layout.add_row(obj)

    def add_choice_buttons(self, name: str, choices: dict, vertical=False, into_layout=None):
        into_layout = self._form_layout if not into_layout else into_layout
        button_group = qtw.QButtonGroup()
        layout = qtw.QVBoxLayout() if vertical else qtw.QHBoxLayout()
        obj = qtw.QWidget()
        obj.set_layout(layout)

        for key, val in choices.items():
            button = qtw.QRadioButton(val)
            button_group.add_button(button, key)
            layout.add_widget(button)

        button_group.buttons()[0].set_checked(True)
        self._form_items[name] = button_group
        into_layout.add_row(obj)
        

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
        self._form_items = OrderedDict()
        self.add_line()
        self.add_title("Test 1")
        self.add_line()
        self.add_title("Test 2")
        self.add_pushbuttons({"save": "Save", "load": "Load", "new": "New"})
        self.add_spin_box("fs", "resonance", "double_float", (0, 99))
        self.add_spin_box("n", "amount", "integer", (0, 9))
        self.add_combo_box("coil_options", "Coil options", [("SV", "data1"),
                                                            ("CCAW", "data2"),
                                                            ("MEGA", "data3"),
                                                            ])
        self.add_text_edit_box("comments", "Comments..")
        self.add_choice_buttons("box_type", {0: "small", 1:"large", 2:"off"}, vertical=False)
        self.add_pushbuttons({"error": "Raise exception"})

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
        self._form_items["error_button"].clicked.connect(raise_error)


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
        self._top_label = qtw.QLabel("Hello World!")
        self._beep_freq_dial = qtw.QDial(minimum=100,
                                         maximum=10000,
                                         wrapping=False,
                                         )
        self._beep_freq_display = qtw.QLCDNumber()
        self._beep_advanced_pusbutton = qtw.QPushButton("Beep advanced")
        self._user_form = UserForm()

    def place_widgets(self):
        self._center_layout = qtw.QVBoxLayout()
        self._center_widget = qtw.QWidget()
        self._center_widget.set_layout(self._center_layout)
        self.set_central_widget(self._center_widget)

        self._center_layout.add_widget(self._top_label)
        self._center_layout.add_widget(self._beep_freq_dial)
        self._center_layout.add_widget(self._beep_freq_display)
        self._center_layout.add_widget(self._beep_advanced_pusbutton)
        self._center_layout.add_widget(self._user_form.widget)

    def make_connections(self):
        self._beep_advanced_pusbutton.clicked.connect(
            lambda: self.signal_beep.emit(1, self._beep_freq_dial.value)
            )
        self.signal_beep.connect(sound_engine.beep, qtc.Qt.QueuedConnection)

        self._beep_freq_display.display(self._beep_freq_dial.value)
        self._beep_freq_dial.valueChanged.connect(self._beep_freq_display.display)

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
                                  # buttons = qtw.QMessageBox.NoButton,
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
