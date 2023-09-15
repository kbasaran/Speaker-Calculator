import os
import traceback

from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc
from PySide6 import QtGui as qtg

from dataclasses import dataclass, fields
import sounddevice as sd
import numpy as np
import signal_tools

import logging
logging.basicConfig(level=logging.INFO)


@dataclass
class Settings:
    version: str = '0.2.0'
    GAMMA: float = 1.401  # adiabatic index of air
    P0: int = 101325
    RHO: float = 1.1839  # 25 degrees celcius
    Kair: float = 101325. * RHO
    c_air: float = (P0 * GAMMA / RHO)**0.5
    vc_table_file = os.path.join(os.getcwd(), 'SSC_data', 'WIRE_TABLE.csv')
    f_min: int = 10
    f_max: int = 3000
    ppo: int = 48 * 8
    FS: int = 48000
    A_beep: int = 0.5
    T_beep = 0.1
    freq_good_beep: float = 1175. / 2
    freq_bad_beep: float = freq_good_beep / 4
    last_used_folder: str = os.path.expanduser('~')
    show_legend: bool = True
    max_legend_size: int = 10
    import_ppo: int = 0
    export_ppo: int = 96
    processing_selected_tab: int = 0
    mean_selected: bool = False
    median_selected: bool = True
    smoothing_type: int = 0
    smoothing_resolution_ppo: int = 96
    smoothing_bandwidth: int = 6
    outlier_fence_iqr: float = 10.
    outlier_action: int = 0
    matplotlib_style: str = "bmh"
    processing_interpolation_ppo: int = 96
    interpolate_must_contain_hz: int = 1000
    graph_grids: str = "major and minor"

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

    def as_dict(self):
        settings = {}
        for field in fields(self):
            settings[field] = getattr(self, field.name)
        return settings

    def __repr__(self):
        return str(self.as_dict())


class FloatSpinBox(qtw.QDoubleSpinBox):
    def __init__(self, name, tooltip,
                 decimals=2,
                 min_max=(0.01, 999.99),
                 ratio_to_SI=1,
                 user_data_widgets=None,
                 ):
        self._name = name
        super().__init__()
        if tooltip:
            self.setToolTip(tooltip)
        self.setStepType(qtw.QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        self.setDecimals(decimals)
        if min_max:
            self.setRange(*min_max)
        if user_data_widgets is not None:
            self.user_values_storage(user_data_widgets)

    def user_values_storage(self, user_data_widgets: dict):
        user_data_widgets[self._name] = self


class IntSpinBox(qtw.QSpinBox):
    def __init__(self, name, tooltip,
                 min_max=(0, 999999),
                 ratio_to_SI=1,
                 user_data_widgets=None
                 ):
        self._name = name
        super().__init__()
        if tooltip:
            self.setToolTip(tooltip)
        if min_max:
            self.setRange(*min_max)
        if user_data_widgets is not None:
            self.user_values_storage(user_data_widgets)

    def user_values_storage(self, user_data_widgets: dict):
        user_data_widgets[self._name] = self

class CheckBox(qtw.QCheckBox):
    def __init__(self, name, tooltip,
                 user_data_widgets=None
                 ):
        self._name = name
        super().__init__()
        if tooltip:
            self.setToolTip(tooltip)
        if user_data_widgets is not None:
            self.user_values_storage(user_data_widgets)

    def user_values_storage(self, user_data_widgets: dict):
        user_data_widgets[self._name] = self

class LineTextBox(qtw.QLineEdit):
    def __init__(self, name, tooltip, user_data_widgets=None):
        self._name = name
        super().__init__()
        if tooltip:
            self.setToolTip(tooltip)
        if user_data_widgets is not None:
            self.user_values_storage(user_data_widgets)

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
    def __init__(self, names: dict, tooltips: dict, vertical=False, user_data_widgets=None):
        """Both names and tooltips have the same keys: short_name's
        Values for names: text
        """
        self._buttons = dict()
        super().__init__()
        layout = qtw.QVBoxLayout(self) if vertical else qtw.QHBoxLayout(self)
        for key, val in names.items():
            name = key + "_pushbutton"
            button = qtw.QPushButton(val)
            if key in tooltips:
                button.setToolTip(tooltips[key])
            layout.addWidget(button)
            self._buttons[name] = button
        if user_data_widgets is not None:
            self.user_values_storage(user_data_widgets)

    def user_values_storage(self, user_data_widgets: dict):
        for name, button in self._buttons.items():
            user_data_widgets[name] = button

    def buttons(self) -> dict:
        return self._buttons

class ChoiceButtonGroup(qtw.QWidget):
    def __init__(self, group_name, names: dict, tooltips: dict, vertical=False, user_data_widgets=None):
        """keys for names: integers
        values for names: text
        """
        self._name = group_name
        super().__init__()
        self.button_group = qtw.QButtonGroup()
        layout = qtw.QVBoxLayout(self) if vertical else qtw.QHBoxLayout(self)
        for key, button_name in names.items():
            button = qtw.QRadioButton(button_name)
            if key in tooltips:
                button.setToolTip(tooltips[key])
            self.button_group.addButton(button, key)
            layout.addWidget(button)
        self.button_group.buttons()[0].setChecked(True)
        if user_data_widgets is not None:
            self.user_values_storage(user_data_widgets)

    def user_values_storage(self, user_data_widgets: dict):
        user_data_widgets[self._name] = self.button_group

    def buttons(self) -> list:
        return self.self.button_group.buttons()

class ComboBox(qtw.QComboBox):
    def __init__(self, name,
                 tooltip,
                 items: list,
                 user_data_widgets=None):
        self._name = name
        super().__init__()
        if tooltip:
            self.setToolTip(tooltip)
        for item in items:
            self.addItem(*item)  # tuple with userData, therefore *
        if user_data_widgets is not None:
            self.user_values_storage(user_data_widgets)

    def user_values_storage(self, user_data_widgets: dict):
        user_data_widgets[self._name] = self


class SubForm(qtw.QWidget):
    def __init__(self):
        super().__init__()
        self._layout = qtw.QFormLayout(self)
        

class UserForm(qtw.QWidget):
    def __init__(self):
        super().__init__()
        self._layout = qtw.QFormLayout(self)  # the argument makes already here the "setLayout" for the widget
        self._create_core_objects()

    def _create_core_objects(self):
        self._user_input_widgets = dict()

    def add_row(self, obj, description=None, into_form=None):
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

    def update_form_values(self, values_new: dict):
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

                elif isinstance(obj, qtw.QCheckBox):
                    obj.setChecked(value_new)

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

    def get_form_values(self) -> dict:
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

            elif isinstance(obj, qtw.QCheckBox):
                obj_value = obj.isChecked()

            else:
                obj_value = obj.value()

            values[key] = obj_value

        logging.debug("Return of 'get_form_values")
        for val, key in values.items():
            logging.debug(val, type(val), key, type(key))

        return values


class SoundEngine(qtc.QObject):
    def __init__(self, settings):
        super().__init__()
        self.app_settings = settings
        self.verify_stream()

    def verify_stream(self):
        self.FS = sd.query_devices(device=sd.default.device, kind='output',
                                   )["default_samplerate"]
        # needs to be improved and tested for device changes!
        if not hasattr(self, "stream"):
            self.stream = sd.OutputStream(samplerate=self.FS, channels=2)
        if not self.stream.active:
            self.stream.start()

    @qtc.Slot(float, float, float)
    def beep(self, A, T, freq):
        self.verify_stream()
        t = np.arange(T * self.FS) / self.FS
        y = A * np.sin(t * 2 * np.pi * freq)
        fade_window = signal_tools.make_fade_window_n(1, 0, len(y), fade_start_end_idx=(len(y) - int(self.FS / 10), len(y)))
        y = y * fade_window
        y = np.tile(y, self.stream.channels)
        y = y.reshape((len(y) // self.stream.channels,
                      self.stream.channels), order='F').astype(self.stream.dtype)
        y = np.ascontiguousarray(y, self.stream.dtype)
        self.stream.write(y)

    @qtc.Slot()
    def good_beep(self):
        self.beep(self.app_settings.A_beep, self.app_settings.T_beep, self.app_settings.freq_good_beep)

    @qtc.Slot()
    def bad_beep(self):
        self.beep(self.app_settings.A_beep, self.app_settings.T_beep, self.app_settings.freq_bad_beep)

    @qtc.Slot()
    def release_all(self):
        self.stream.stop(ignore_errors=True)

class ErrorHandlerDeveloper:
    def __init__(self, app):
        self.app = app
    
    def excepthook(self, etype, value, tb):
        error_msg = ''.join(traceback.format_exception(etype, value, tb))
        message_box = qtw.QMessageBox(qtw.QMessageBox.Warning,
                                      "Error    :(",
                                      error_msg +
                                      "\nYour application may now be in an unstable state."
                                      "\n\nThis event may be logged unless ignore is chosen.",
                                      )
        message_box.addButton(qtw.QMessageBox.Ignore)
        close_button = message_box.addButton(qtw.QMessageBox.Close)
    
        message_box.setEscapeButton(qtw.QMessageBox.Ignore)
        message_box.setDefaultButton(qtw.QMessageBox.Close)
    
        close_button.clicked.connect(logging.warning(error_msg))
    
        message_box.exec()

class ErrorHandlerUser:
    def __init__(self, app):
        self.app = app
    
    def excepthook(self, etype, value, tb):
        error_info = traceback.format_exception(etype, value, tb)
        error_msg = error_info[-2] + "\n\n" + error_info[-1]
        message_box = qtw.QMessageBox(qtw.QMessageBox.Warning,
                                      "Error    :(",
                                      error_msg +
                                      "\n\nYour application may now be in an unstable state."
                                      "\nThis event may be logged unless ignore is chosen.",
                                      )
        message_box.addButton(qtw.QMessageBox.Ignore)
        close_button = message_box.addButton(qtw.QMessageBox.Close)
    
        message_box.setEscapeButton(qtw.QMessageBox.Ignore)
        message_box.setDefaultButton(qtw.QMessageBox.Close)
    
        close_button.clicked.connect(logging.warning(error_msg))
    
        message_box.exec()