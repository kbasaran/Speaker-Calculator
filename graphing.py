import numpy as np

from matplotlib.backends.qt_compat import QtWidgets as qtw
from matplotlib.backends.backend_qtagg import (
    FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
from matplotlib.figure import Figure

# https://matplotlib.org/stable/gallery/user_interfaces/embedding_in_qt_sgskip.html

class MatplotlibWidget(qtw.QWidget):
    def __init__(self):
        super().__init__()
        layout = qtw.QVBoxLayout(self)

        fig = Figure()
        self.canvas = FigureCanvas(fig)
        # Ideally one would use self.addToolBar here, but it is slightly
        # incompatible between PyQt6 and other bindings, so we just add the
        # toolbar as a plain widget instead.
        layout.addWidget(NavigationToolbar(self.canvas, self))
        layout.addWidget(self.canvas)
        
        self.ax = self.canvas.figure.subplots()
        self.ax.grid()
        
        self.lines = {}  # dictionary of lines
        # https://matplotlib.org/stable/api/_as_gen/matplotlib.lines.Line2D.html


    def update_canvas(self):

        def ceil_to_multiple(number, multiple=5):
            return multiple * np.ceil((number + 2) / multiple)

        def floor_to_multiple(number, multiple=5):
            return multiple * np.floor((number - 2) / multiple)

        if len(self.lines):
            y_min = floor_to_multiple(np.min(np.concatenate([line.get_ydata() for line in self.lines.values()])))
            y_max = ceil_to_multiple(np.max(np.concatenate([line.get_ydata() for line in self.lines.values()])))
            self.ax.set_ylim((y_min, y_max))

        self.ax.legend()
        self.canvas.draw()

    def update_line(self, name: str, new_data: tuple, description=None):
        line = self.lines[name]
        line.set_data(*new_data)
        if description:
            line.set_label(description)
        self.update_canvas()

    def add_line(self, name, description, data, *args, **kwargs):
        line, = self.ax.semilogx(*data, label=description, *args, **kwargs)
        self.lines[name] = line
        self.update_canvas()


if __name__ == "__main__":

    app = qtw.QApplication([])
    mw = MatplotlibWidget()

    # do a test plot
    x = 100 * 2**np.arange(stop=7, step=7 / 16)
    for i in range(1, 5):
        y = 45 + 10 * np.random.random(size=len(x))
        mw.add_line(i, f"Random line {i}", (x, y))

    mw.show()
    app.exec()
