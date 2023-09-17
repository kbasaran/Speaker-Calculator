import logging
import sys
import numpy as np
from operator import methodcaller
from functools import partial
import signal_tools
from functools import lru_cache

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
        self.available_styles = list(plt.style.available)
        self._ref_index_and_curve = None

        desired_style = self.app_settings.matplotlib_style
        if desired_style in plt.style.available:
            plt.style.use(desired_style)
        else:
            raise KeyError(f"Desired style '{desired_style}' not available.")

        fig = Figure()
        fig.set_layout_engine("constrained")
        self.canvas = FigureCanvas(fig)
        # Ideally one would use self.addToolBar here, but it is slightly
        # incompatible between PyQt6 and other bindings, so we just add the
        # toolbar as a plain widget instead.
        self.navigation_toolbar = NavigationToolbar(self.canvas, self)
        layout.addWidget(self.navigation_toolbar)
        # print(self.navigation_toolbar.layout().itemAt(3).tooltip())  - test access to buttons in toolbar
        layout.addWidget(self.canvas)

        self.ax = self.canvas.figure.subplots()
            
        self.lines_in_order = []

        # https://matplotlib.org/stable/api/_as_gen/matplotlib._lines.line2d.html

    @qtc.Slot()
    def set_grid_type(self):
        self.ax.grid(visible=False, which="both", axis='both')

        if self.app_settings.graph_grids == "default":
            visible = plt.rcParams["axes.grid"]
            axis = plt.rcParams["axes.grid.axis"]
            which = plt.rcParams["axes.grid.which"]
            self.ax.grid(visible=visible, which=which, axis=axis)

        else:
            if "major" in self.app_settings.graph_grids:
                self.ax.grid(visible=True, which="major", axis='both')
            if "minor" in self.app_settings.graph_grids:
                self.ax.grid(visible=True, which="minor", axis='both')

    @qtc.Slot()
    def update_figure(self, recalculate_limits=True, update_legend=True):
        
        if recalculate_limits:
            y_arrays = [line.get_ydata() for line in self.ax.get_lines()]
            y_min_max = signal_tools.calculate_graph_limits(y_arrays, multiple=5, clearance_up_down=(2, 1))
            self.ax.set_ylim(y_min_max)

        if update_legend:
            if self.ax.has_data() and self.app_settings.show_legend:
                self.show_legend_ordered()
            else:
                self.ax.legend().remove()

        self.canvas.draw()

    @qtc.Slot()
    def add_line2d(self, i, label, data: tuple, update_figure=True, line2d_kwargs={}):
        if self._ref_index_and_curve and i <= self._ref_index_and_curve[0]:
            self._ref_index_and_curve[0] += 1

        # Modify curve before pasting if graph has a reference curve
        x_in, y_in = data
        if self._ref_index_and_curve:
            ref_y_intp = self.reference_curve_interpolated(tuple(x_in))
            y_in = y_in - ref_y_intp

        # Paste the curve into graph
        line, = self.ax.semilogx(x_in, y_in, label=label, **line2d_kwargs)
        self.lines_in_order.insert(i, line)

        self.update_line_zorders()
        if update_figure:
            self.update_figure()

    @qtc.Slot()
    def remove_line2d(self, ix: list, update_figure=True):
        if self._ref_index_and_curve:
            if self._ref_index_and_curve[0] in ix:
                self.toggle_reference_curve(None)
            else:
                self._ref_index_and_curve[0] -= sum(i < self._ref_index_and_curve[0] for i in ix)  # summing booleans

        for i in reversed(ix):    
            line = self.lines_in_order.pop(i)
            line.remove()
        
        self.update_line_zorders()
        if update_figure:
            self.update_figure(recalculate_limits=False)

    @lru_cache
    def reference_curve_interpolated(self, x:tuple):
        ref_x, ref_y = self._ref_index_and_curve[1].get_xy()
        return np.interp(np.log(x), np.log(ref_x), ref_y, left=np.nan, right=np.nan)
         
    @qtc.Slot()
    def toggle_reference_curve(self, ref_index_and_curve:tuple):
        if ref_index_and_curve:
            self._ref_index_and_curve = ref_index_and_curve
            for line2d in self.ax.get_lines():
                x, y = line2d.get_xdata(), line2d.get_ydata()
                ref_y_intp = self.reference_curve_interpolated(tuple(x))
                line2d.set_ydata(y - ref_y_intp)

            self.hide_show_line2d({self._ref_index_and_curve[0]: False})

            self.update_figure()

        else:
            for line2d in self.ax.get_lines():
                x, y = line2d.get_xdata(), line2d.get_ydata()
                ref_y_intp = self.reference_curve_interpolated(tuple(x))
                line2d.set_ydata(y + ref_y_intp)

            self.hide_show_line2d({self._ref_index_and_curve[0]: True})

            self._ref_index_and_curve = None
            self.update_figure()

        self.reference_curve_interpolated.cache_clear()

    def show_legend_ordered(self):
        if self.app_settings.max_legend_size > 0:
            handles = []
            iterator = iter(self.lines_in_order)
            while len(handles) < self.app_settings.max_legend_size:
                line = next(iterator, None)
                if line is None:
                    break
                if line.get_alpha() in (None, 1):
                    handles.append(line)
        else:
            handles = self.lines_in_order
            
        # visible_lines = [line for line in self.lines_in_order if line.get_alpha() in (None, 1)]
        # handles = visible_lines[:self.app_settings.max_legend_size]
        labels = [line.get_label() for line in handles]

        if self._ref_index_and_curve:
            title = "Relative to: " + self._ref_index_and_curve[1].get_full_name()
            title = title.removesuffix(" - reference")
        else:
            title = None

        self.ax.legend(handles, labels, title=title)

    def change_lines_order(self, new_positions: list):
        # each number in the new_positions is the index before location change. index in the list is the new location.
        lines_reordered = []
        for i_after, i_before in enumerate(new_positions):
            lines_reordered.append(self.lines_in_order[i_before])
            if self._ref_index_and_curve and i_before == self._ref_index_and_curve[0]:
                self._ref_index_and_curve[0] = i_after  # keep the reference index correct with this
        self.lines_in_order = lines_reordered

        self.update_line_zorders()
        self.update_figure(recalculate_limits=False)

    def update_line_zorders(self):
        for i, line in enumerate(self.lines_in_order):
            hide_offset = -1_000_000 if line.get_label()[0] == "_" else 0
            line.set_zorder(len(self.lines_in_order) - i + hide_offset)

    @qtc.Slot(int)
    def flash_curve(self, i: int):
        if not hasattr(self, "default_lw"):
            self.default_lw = self.ax.get_lines()[0].get_lw()
        line = self.lines_in_order[i]
        line.set_lw(self.default_lw*2.5)
        old_alpha = line.get_alpha()
        if old_alpha:
            line.set_alpha(1)
        old_zorder = line.get_zorder()
        line.set_zorder(len(self.lines_in_order))


        self.update_figure(recalculate_limits=False, update_legend=False)

        timer = qtc.QTimer()
        timer.singleShot(1000, partial(self.stop_flash, line, (old_alpha, self.default_lw, old_zorder)))

    def stop_flash(self, line, old_states):
        line.set_alpha(old_states[0])
        line.set_lw(old_states[1])
        line.set_zorder(old_states[2])
        self.update_figure(recalculate_limits=False, update_legend=False)

    @qtc.Slot()
    def hide_show_line2d(self, visibility_states: dict, update_figure=True):
        for i, visible in visibility_states.items():
            line = self.lines_in_order[i]

            alpha = 1 if visible else 0.1
            line.set_alpha(alpha)

            if visible:
                while (label := line.get_label())[0] == "_":
                    line.set_label(label.removeprefix("_"))
            if not visible and (label := line.get_label())[0] != "_":
                line.set_label("_" + label)

        self.update_line_zorders()

        if update_figure:
            self.update_figure(recalculate_limits=False)

    @qtc.Slot()
    def update_labels(self, labels: dict, update_figure=True):
        changed_indexes = []
        for i, label in labels.items():
            line = self.lines_in_order[i]

            new_label = label if line.get_alpha() in (None, 1) else ("_" + label)
            line.set_label(new_label)
            changed_indexes.append(i)

        if changed_indexes and update_figure and (min(changed_indexes) < self.app_settings.max_legend_size):
            self.update_figure(recalculate_limits=False)

    @qtc.Slot()
    def reset_colors(self):
        colors = plt.rcParams["axes.prop_cycle"]()

        for line in self.lines_in_order:
            line.set_color(next(colors)["color"])

        self.update_figure(recalculate_limits=False)


if __name__ == "__main__":

    if not (app := qtw.QApplication.instance()):
        app = qtw.QApplication(sys.argv)
        # there is a new recommendation with qApp but how to do the sys.argv with that?

    mw = MatplotlibWidget()

    # do a test plot
    x = 100 * 2**np.arange(stop=7, step=7 / 16)
    for i in range(1, 5):
        y = 45 + 10 * np.random.random(size=len(x))
        mw.add_line2d(i, f"Random line {i}", (x, y))

    mw.show()
    app.exec()
