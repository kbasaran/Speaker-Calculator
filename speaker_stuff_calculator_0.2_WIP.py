import os
import sys
import numpy as np
import matplotlib.pyplot as plt
from dataclasses import dataclass

from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc

from __feature__ import snake_case
from __feature__ import true_property

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
        self.build_form_widget()

    def build_form_widget(self):
        self._form_layout = qtw.QFormLayout()
        self.widget.set_layout(self._form_layout)

        form_items = OrderedDict()
        form_items["fs"] = qtw.QDoubleSpinBox()

        for key, val in form_items.items():
            self._form_layout.add_row(key, val)


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

        self._user_form = UserForm()

    def create_widgets(self):
        self._top_label = qtw.QLabel("Hello World!")
        self._beep_freq_dial = qtw.QDial(minimum=100,
                                         maximum=10000,
                                         wrapping=False,
                                         )
        self._beep_freq_display = qtw.QLCDNumber()
        self._beep_advanced_pusbutton = qtw.QPushButton("Beep advanced")

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

    def make_connections(self):
        self._beep_advanced_pusbutton.clicked.connect(
            lambda: self._beeper_advanced.beep(1, self._beep_freq_dial.value)
            )
        self._beep_freq_display.display(self._beep_freq_dial.value)
        self._beep_freq_dial.valueChanged.connect(self._beep_freq_display.display)

    def start_threads(self):
        self._beeper_advanced_thread.start(qtc.QThread.LowPriority)


if __name__ == "__main__":
    app = qtw.QApplication(sys.argv)
    settings = Settings()
    mw = MainWindow(settings)
    mw.show()
    app.exec()
