import os
import sys
import numpy as np

# from matplotlib.backends.qt_compat import QtWidgets as qtw
from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc

from graphing import MatplotlibWidget
from signal_tools import Curve
import personalized_widgets as pwi
import pyperclip  # requires also xclip on Linux
from functools import partial

import logging
logging.basicConfig(level=logging.INFO)

# https://matplotlib.org/stable/gallery/user_interfaces/embedding_in_qt_sgskip.html


class CurveAnalyze(qtw.QWidget):

    signal_good_beep = qtc.Signal()

    def __init__(self, settings):
        super().__init__()
        self._global_settings = settings
        self._create_core_objects()
        self._create_widgets()
        self._place_widgets()
        self._make_connections()

    def _create_core_objects(self):
        self._user_input_widgets = dict()
        self._curve_data = {}

    def _create_widgets(self):
        self._graph = MatplotlibWidget()
        self._curve_list = qtw.QListWidget()
        self._graph_buttons = pwi.PushButtonGroup(
            {"import": "Import",
             "import_quick": "Import Quick",
             "process": "Process",
             "export": "Export",
             "settings": "Settings",
             },
            {},
        )

        self._curves_list = qtw.QListWidget()
        self._curves_list.setSelectionMode(qtw.QAbstractItemView.ExtendedSelection)

    def _place_widgets(self):
        self.setLayout(qtw.QVBoxLayout())
        self.layout().addWidget(self._graph, 2)
        self.layout().addWidget(self._graph_buttons)
        self.layout().addWidget(self._curve_list)

    def _make_connections(self):
        self._graph_buttons.user_values_storage(self._user_input_widgets)
        self._user_input_widgets["import_pushbutton"].clicked.connect(
            partial(self._import_curve, self._read_clipboard)
        )

    def _import_curve(self, import_fun):
        new_curve = import_fun()
        if new_curve:
            self.add_curve(new_curve)
        else:
            # beep bad
            pass

    def _read_clipboard(self):
        data = pyperclip.paste()
        new_curve = Curve(data)
        if new_curve.is_Klippel_curve():
            return new_curve
        else:
            logging.debug("Unrecognized curve object")

    def add_curve(self, curve):
        curve_name = f"{self._curve_list.count():02d} - {curve.name}"
        list_item = qtw.QListWidgetItem(curve_name)
        self._graph.add_line2D(curve_name, (curve.x, curve.y))
        self._curve_list.addItem(list_item)
        self._curve_data[curve_name] = curve


if __name__ == "__main__":

    if not (app := qtw.QApplication.instance()):
        app = qtw.QApplication(sys.argv)
        # there is a new recommendation with qApp but how to dod the sys.argv with that?

    mw = CurveAnalyze(settings=None)

    mw.show()
    app.exec()
