import logging
import sys
import numpy as np
from operator import methodcaller
from functools import partial

from PySide6 import QtCore as qtc
from matplotlib.backends.qt_compat import QtWidgets as qtw
from matplotlib.backends.backend_qtagg import (
    FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import matplotlib.patheffects as mpe
plt.rcParams["figure.constrained_layout.h_pad"] = 0.3
plt.rcParams["figure.constrained_layout.w_pad"] = 0.4

# https://matplotlib.org/stable/gallery/user_interfaces/embedding_in_qt_sgskip.html

logging.basicConfig(level=logging.INFO)


class MatplotlibWidget(qtw.QWidget):
    def __init__(self, settings):
        self.app_settings = settings
        super().__init__()
        layout = qtw.QVBoxLayout(self)
        desired_style = 'bmh'
        if desired_style in plt.style.available:
            plt.style.use(desired_style)
        else:
            print(f"Desired style '{desired_style}' not available.")

        fig = Figure()
        fig.set_layout_engine("constrained")
        self.canvas = FigureCanvas(fig)
        # Ideally one would use self.addToolBar here, but it is slightly
        # incompatible between PyQt6 and other bindings, so we just add the
        # toolbar as a plain widget instead.
        self.navigation_toolbar = NavigationToolbar(self.canvas, self)
        layout.addWidget(self.navigation_toolbar)
        # print(self.navigation_toolbar.layout().itemAt(3).tooltip())
        layout.addWidget(self.canvas)

        self.ax = self.canvas.figure.subplots()
        self.ax.grid(which='minor')

        # self._lines = {}  # dictionary of _lines
        # https://matplotlib.org/stable/api/_as_gen/matplotlib._lines.Line2D.html

    @qtc.Slot()
    def update_figure(self):

        def ceil_to_multiple(number, multiple=5, clearance=2):
            return multiple * np.ceil((number + clearance) / multiple)

        def floor_to_multiple(number, multiple=5, clearance=2):
            return multiple * np.floor((number - clearance) / multiple)

        if self.ax.get_lines():
            y_min = floor_to_multiple(np.min(np.concatenate(
                [line.get_ydata() for line in self.ax.get_lines()])), clearance=1)
            y_max = ceil_to_multiple(np.max(np.concatenate(
                [line.get_ydata() for line in self.ax.get_lines()])))
            self.ax.set_ylim((y_min, y_max))

        if self.ax.get_lines() and self.app_settings.show_legend:
            self.show_legend_based_on_zorder()
        else:
            self.ax.legend().remove()

        self.canvas.draw()

    @qtc.Slot()
    def update_line2D(self, i: int, name_with_number: str, new_data: np.ndarray, update_figure=True):
        line = self.lines_as_dict()[i]
        line.set_data(new_data)
        line.set_label(name_with_number)
        line.set_zorder(i)
        if update_figure:
            self.update_figure()

    @qtc.Slot()
    def add_line2D(self, i, label, data: tuple, update_figure=True, **kwargs):
        for line in self.ax.get_lines():
            zorder = line.get_zorder()
            if zorder >= i:
                line.set_zorder(zorder + 1)
        self.ax.semilogx(*data, label=label, zorder=i, **kwargs)
        if update_figure:
            self.update_figure()

    @qtc.Slot()
    def remove_line2D(self, ix: list, update_figure=True):
        to_remove = np.array(ix)
        lines = self.lines_as_dict()
        for zorder, line in lines.items():
            if zorder in ix:
                line.remove()
            else:
                line.set_zorder(
                    zorder - (to_remove < zorder).sum()
                    )
        #     if zorder

        # for i in reversed(sorted(ix)):
        #     for zorder, line in lines.items():
        #         if zorder > i:
        #             line.set_zorder(zorder - 1)

        if update_figure:
            self.update_figure()

    def show_legend_based_on_zorder(self):
        handles = sorted(self.ax.get_lines(), key=methodcaller("get_zorder"))
        labels = [line.get_label() for line in handles]

        self.ax.legend(handles, labels)
        # print([line.get_zorder() for line in self.ax.get_lines()])

    def set_curves_zorder(self, zorders: list):
        for line in self.ax.get_lines():
            zorder_old = line.get_zorder()
            line.set_zorder(zorders.index(zorder_old))

        self.update_figure()

    @qtc.Slot()
    def mark_selected_curve(self, i: int):
        if not hasattr(self, "default_lw"):
            self.default_lw = self.ax.get_lines()[0].get_lw()
        timer = qtc.QTimer()
        for line in self.ax.get_lines():
            if line.get_zorder() == i:
                line.set_lw(self.default_lw*2)
                timer.singleShot(1000, partial(self.remove_marking, line))
                # line.set_path_effects([mpe.withSimplePatchShadow(offset=(2,-2))])
            # else:
                # line.set_lw(self.default_lw)
                # line.set_path_effects(None)
        self.update_figure()

    def remove_marking(self, line):
        line.set_lw(self.default_lw)
        self.update_figure()

    @qtc.Slot()
    def hide_show_line2D(self, visibility_states: dict, update_figure=True):
        lines = self.lines_as_dict()
        for i, visible in visibility_states.items():
            # lines[i].set_visible(visible)
            alpha = (1 if visible else 0.2)
            lines[i].set_alpha(alpha)

            label = lines[i].get_label()
            if visible and label[0] == "_":
                lines[i].set_label(label.removeprefix("_"))
            if not visible and label[0] != "_":
                lines[i].set_label("_" + label)

        if update_figure:
            self.update_figure()

    @qtc.Slot()
    def update_labels_and_colors(self, labels: dict, update_figure=True):
        colors = plt.rcParams["axes.prop_cycle"]()

        for line in self.ax.get_lines():
            zorder = line.get_zorder()
            new_label = labels[zorder] if line.get_alpha() in (None, 1) else ("_" + labels[zorder])
            line.set_label(new_label)
            line.set_color(next(colors)["color"])

        if update_figure:
            self.update_figure()

    def lines_as_dict(self):
        lines = {}
        for line in self.ax.get_lines():
            lines[line.get_zorder()] = line
        return lines


if __name__ == "__main__":

    if not (app := qtw.QApplication.instance()):
        app = qtw.QApplication(sys.argv)
        # there is a new recommendation with qApp but how to dod the sys.argv with that?

    mw = MatplotlibWidget()

    # do a test plot
    x = 100 * 2**np.arange(stop=7, step=7 / 16)
    for i in range(1, 5):
        y = 45 + 10 * np.random.random(size=len(x))
        mw.add_line2D(i, f"Random line {i}", (x, y))

    mw.show()
    app.exec()
