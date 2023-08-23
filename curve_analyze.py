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

    def _create_widgets(self):
        self._graph = MatplotlibWidget()
        self._curve_list = CurveList()
        self._graph_buttons = pwi.PushButtonGroup(
            {"test_import": "Test import",
             "test_2": "Test button 2"},
            {"test_import": "/",
             "test_2": "/",
             },
        )

    def _place_widgets(self):
        self.setLayout(qtw.QVBoxLayout())
        self.layout().addWidget(self._graph, 2)
        self.layout().addWidget(self._graph_buttons)
        self.layout().addWidget(self._curve_list)

    def _make_connections(self):
        self._graph_buttons.user_values_storage(self._user_input_widgets)
        self._user_input_widgets["test_import_pushbutton"].clicked.connect(self._test_import_clipboard)

    def _test_import_clipboard(self):
        data = pyperclip.paste()
        new_curve = Curve(data)
        if new_curve.is_Klippel_curve():
            i = self._graph.add_line2D("test clipboard import", (new_curve.x, new_curve.y))
            logging.info(f"added line2D: {i}")
        else:
            logging.debug("Unrecognized curve object")


class CurveList(qtw.QListWidget):
    def __init__(self):
        super().__init__()

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
