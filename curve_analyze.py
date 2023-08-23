import os
import sys
import numpy as np

# from matplotlib.backends.qt_compat import QtWidgets as qtw
from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc

from graphing import MatplotlibWidget

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
        pass

    def _create_widgets(self):
        self._graph = MatplotlibWidget()

    def _place_widgets(self):
        self.setLayout(qtw.QVBoxLayout())
        self.layout().addWidget(self._graph)

    def _make_connections(self):
        pass


if __name__ == "__main__":

    if not (app := qtw.QApplication.instance()):
        app = qtw.QApplication(sys.argv)
        # there is a new recommendation with qApp but how to dod the sys.argv with that?

    mw = CurveAnalyze(settings=None)

    # # do a test plot
    # x = 100 * 2**np.arange(stop=7, step=7 / 16)
    # for i in range(1, 5):
    #     y = 45 + 10 * np.random.random(size=len(x))
    #     mw.add_line(i, f"Random line {i}", (x, y))

    mw.show()
    app.exec()
