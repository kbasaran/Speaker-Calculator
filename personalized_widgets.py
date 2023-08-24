from PySide6 import QtWidgets as qtw
from PySide6 import QtGui as qtg


class FloatSpinBox(qtw.QDoubleSpinBox):
    def __init__(self, name, tooltip,
                 decimals=2,
                 min_max=(0.01, 999.99),
                 ratio_to_SI=1,
                 ):
        self._name = name
        super().__init__()
        if tooltip:
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
        if tooltip:
            self.setToolTip(tooltip)
        if min_max:
            self.setRange(*min_max)

    def user_values_storage(self, user_data_widgets: dict):
        user_data_widgets[self._name] = self


class LineTextBox(qtw.QLineEdit):
    def __init__(self, name, tooltip):
        self._name = name
        super().__init__()
        if tooltip:
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

    def user_values_storage(self, user_data_widgets: dict):
        for name, button in self._buttons.items():
            user_data_widgets[name] = button


class ChoiceButtonGroup(qtw.QWidget):
    def __init__(self, group_name, names: dict, tooltips: dict, vertical=False):
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

    def user_values_storage(self, user_data_widgets: dict):
        user_data_widgets[self._name] = self.button_group


class ComboBox(qtw.QComboBox):
    def __init__(self, name, tooltip,
                 items: list):
        self._name = name
        super().__init__()
        if tooltip:
            self.setToolTip(tooltip)
        for item in items:
            self.addItem(*item)  # tuple with userData, therefore *

    def user_values_storage(self, user_data_widgets: dict):
        user_data_widgets[self._name] = self


class SubForm(qtw.QWidget):
    def __init__(self):
        super().__init__()
        self._layout = qtw.QFormLayout(self)