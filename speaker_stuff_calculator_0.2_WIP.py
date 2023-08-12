import os
import sys
import numpy as np
import matplotlib.pyplot as plt
from dataclasses import dataclass
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
from pathlib import Path
import electroacoustical as eac
from collections import OrderedDict

# https://realpython.com/python-super/#an-overview-of-pythons-super-function
# super(super_of_which_class?=this class, in_which_object?=self)
# The parameterless call to super() is recommended and sufficient for most use cases


@dataclass
class Settings:
    FS: int = 44100
    GAMMA: float = 1.401  # adiabatic index of air
    P0: int = 101325
    RHO: float = 1.1839  # 25 degrees celcius
    Kair: float = 101325 * RHO
    c_air: float = (P0 * GAMMA / RHO)**0.5
    vc_table_file = Path.cwd().joinpath('SSC_data', 'WIRE_TABLE.csv')
    f_min: int = 10
    f_max: int = 3000
    ppo: int = 48 * 8
    FS: int = 48000
    A_beep: int = 0.1
    T_beep = 0.1
    freq_good_beep: float = 1175
    freq_bad_beep: float = freq_good_beep / 2

    def update_attr(self, attr_name, new_val):
        assert type(self.getattr(attr_name)) == type(new_val)
        self.setattr(attr_name, new_val)


class BeeperEngine(qtc.QObject):
    def __init__(self, settings):
        super().__init__()
        self.FS = settings.FS

    def run(self):
        # do a test beep with default values
        self.beep(1, 1000)

    @qtc.Slot(float, float)
    def beep(self, T, freq):
        t = np.arange(T * self.FS) / self.FS
        y = settings.A_beep * np.sin(t * 2 * np.pi * freq)
        sd.play(y, samplerate=self.FS)

    @qtc.Slot()
    def good_beep(self):
        self.beep(settings.T_beep, settings.freq_good_beep)

    @qtc.Slot()
    def bad_beep(self):
        self.beep(settings.T_beep, settings.freq_bad_beep)


class UserForm(qtc.QObject):
    signal_field_changed = qtc.Signal(dict)

    def __init__(self):
        super().__init__()
        self.widget = qtw.QWidget()
        self._form_layout = qtw.QFormLayout()
        self.widget.set_layout(self._form_layout)
        self.create_form_items()

    def add_line(self):
        line = qtw.QFrame()
        line.frame_shape = qtw.QFrame.HLine
        line.frame_shadow = qtw.QFrame.Sunken
        line.content_margins = (0, 10, 0, 10)
        # n_line =  [name[:4] == "line" for name in self._form_items.keys()].count(True)
        # self._form_items["line_" + str(n_line)] = line
        self._form_layout.add_row(line)

    def add_title(self, text):
        title = qtw.QLabel()
        title.text = text
        title.style_sheet = "font-weight: bold"
        title.alignment = qtg.Qt.AlignmentFlag.AlignCenter
        # n_title =  [name[:5] == "title" for name in self._form_items.keys()].count(True)
        # self._form_items["title_" + str(n_title)] = title
        self._form_layout.add_row(title)

    def add_spin_box(self, name, description,
                     data_type,
                     min_max_vals,
                     coeff_to_SI=1,
                     ):
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
        self._form_layout.add_row(description, obj)

    def add_text_edit_box(self, name, description):
        obj = qtw.QLineEdit()
        # obj.setMinimumSize(52, 18)
        self._form_items[name] = obj
        self._form_layout.add_row(description, obj)

    def add_combo_box(self, name, description=None,
                     item_list=[],
                     ):
        # item_list can contain elements that are tuples.
        # in that case the second part is user data
        obj = qtw.QComboBox()
        # obj.setMinimumSize(52, 18)
        for item in item_list:
            obj.add_item(*item)  # tuple with userData, therefore *
        self._form_items[name] = obj
        if description:
            self._form_layout.add_row(description, obj)
        else:
            self._form_layout.add_row(obj)


    def set_box_value(self, obj, value):
        if isinstance(obj, qtw.QComboBox):
            assert isinstance(value, tuple)
            # assert isinstance(value[0], tuple)
            # assert isinstance(value[1], tuple)
        else:
            assert type(value) == type(obj.value)


    def get_box_value(self, obj):
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
        self.add_spin_box("fs", "resonance", "double_float", (0, 99))
        self.add_spin_box("n", "amount", "integer", (0, 9))
        self.add_combo_box("coil_options", "Coil options", [("SV", "data1"),
                                                            ("CCAW", "data2"),
                                                            ("MEGA", "data3"),
                                                            ])
        self.add_text_edit_box("comments", "Comments..")

    def get_user_form_values(self):
        values = {}
        for key, obj in self._form_items.items():
            if isinstance(obj, qtw.QComboBox):
                obj_value = {"items": [], "current_index": 0}
                for i_item in range(obj.count):
                    item_text = obj.item_text(i_item)
                    item_data = obj.item_data(i_item)
                    obj_value["items"].append( (item_text, item_data) )
                obj_value["current_index"] = obj.current_index
            elif isinstance(obj, qtw.QLineEdit):
                obj_value = obj.text
            else:
                obj_value = obj.value
            
            values[key] = obj_value

        return values

    def update_user_form_values(self, values_new):
        no_dict_key_for_widget = set(self._form_items.keys())
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


class MainWindow(qtw.QMainWindow):

    def __init__(self, settings):
        super().__init__()
        self.global_settings = settings
        self.create_core_objects()
        self.create_widgets()
        self.place_widgets()
        self.make_connections()
        self.start_threads()

    def create_core_objects(self):
        self._beeper_advanced = BeeperEngine(settings)
        self._beeper_advanced_thread = qtc.QThread()
        self._beeper_advanced.move_to_thread(self._beeper_advanced_thread)


    def create_widgets(self):
        self._top_label = qtw.QLabel("Hello World!")
        self._beep_freq_dial = qtw.QDial(minimum=100,
                                         maximum=10000,
                                         wrapping=False,
                                         )
        self._beep_freq_display = qtw.QLCDNumber()
        self._beep_advanced_pusbutton = qtw.QPushButton("Beep advanced")
        self._user_form = UserForm()
        self._save_pusbutton = qtw.QPushButton("Save")
        self._load_pusbutton = qtw.QPushButton("Load")


    def place_widgets(self):
        self._center_widget = qtw.QWidget()
        self._center_layout = qtw.QVBoxLayout()
        self._center_widget.set_layout(self._center_layout)
        self.set_central_widget(self._center_widget)

        self._center_layout.add_widget(self._top_label)
        self._center_layout.add_widget(self._beep_freq_dial)
        self._center_layout.add_widget(self._beep_freq_display)
        self._center_layout.add_widget(self._beep_advanced_pusbutton)
        self._center_layout.add_widget(self._user_form.widget)
        self._center_layout.add_widget(self._save_pusbutton)
        self._center_layout.add_widget(self._load_pusbutton)


    def make_connections(self):
        self._beep_advanced_pusbutton.clicked.connect(
            lambda: self._beeper_advanced.beep(1, self._beep_freq_dial.value)
            )
        self._beep_freq_display.display(self._beep_freq_dial.value)
        self._beep_freq_dial.valueChanged.connect(self._beep_freq_display.display)
        self._save_pusbutton.clicked.connect(self.save_preset)
        self._load_pusbutton.clicked.connect(self.load_preset)

    def start_threads(self):
        self._beeper_advanced_thread.start(qtc.QThread.LowPriority)

    def load_preset(self, preset):
        load_file_path = os.path.join(os.getcwd(), "my_save.json")
        with open(load_file_path, "rt") as f:
            self._user_form.update_user_form_values(json.load(f))

    def save_preset(self):
        save_file_path = os.path.join(os.getcwd(), "my_save.json")
        with open(save_file_path, "wt") as f:
            f.write(json.dumps(self._user_form.get_user_form_values(), indent=4))


if __name__ == "__main__":
    app = qtw.QApplication(sys.argv)  # ne recommendation with qApp
    settings = Settings()
    mw = MainWindow(settings)
    mw.show()
    app.exec()
