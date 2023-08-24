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
        self._curves = {}

    def _create_widgets(self):
        self._graph = MatplotlibWidget()
        self._curve_list = CurveList()
        self._graph_buttons = pwi.PushButtonGroup(
            {"import": "Import",
             "import_quick": "Import quick",
             "process": "Process",
             "export": "Export",
             "settings": "Settings",
             },
            {},
        )

    def _place_widgets(self):
        self.setLayout(qtw.QVBoxLayout())
        self.layout().addWidget(self._graph, 2)
        self.layout().addWidget(self._graph_buttons)
        self.layout().addWidget(self._curve_list)

    def _make_connections(self):
        self._graph_buttons.user_values_storage(self._user_input_widgets)
        self._user_input_widgets["import_pushbutton"].clicked.connect(partial(self._import_curve, self._read_clipboard))

    def _import_curve(self, import_fun):
        new_curve = import_fun()
        i = max([-1] + list(self._curves.keys())) + 1
        name = f"{i:02d} - {new_curve.name}"
        self._graph.add_line2D(name, (new_curve.x, new_curve.y))
        self._curves[i] = new_curve
        self._curve_list.addItem(name)
        logging.info(f"added line2D: {i}")

    def _read_clipboard(self):
        data = pyperclip.paste()
        new_curve = Curve(data)
        if new_curve.is_Klippel_curve():
            return new_curve
        else:
            logging.debug("Unrecognized curve object")


class CurveList(qtw.QListWidget):
    def __init__(self):
        super().__init__()
        self.setSelectionMode(qtw.QAbstractItemView.ExtendedSelection)

    @qtc.Slot()
    def get_chosen_curves(self) -> dict:
        pass

    def remove_curves(self, ids: list):
        pass


if __name__ == "__main__":

    if not (app := qtw.QApplication.instance()):
        app = qtw.QApplication(sys.argv)
        # there is a new recommendation with qApp but how to dod the sys.argv with that?

    mw = CurveAnalyze(settings=None)

    mw.show()
    app.exec()
