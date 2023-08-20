import numpy as np

# https://matplotlib.org/stable/gallery/user_interfaces/embedding_in_qt_sgskip.html
from matplotlib.backends.qt_compat import QtWidgets as qtw
from matplotlib.backends.backend_qtagg import (
    FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
from matplotlib.figure import Figure


class MatplotlibWidget(qtw.QWidget):
    def __init__(self):
        super().__init__()
        layout = qtw.QVBoxLayout(self)

        fig = Figure()
        self.canvas = FigureCanvas(fig)

        layout.addWidget(NavigationToolbar(self.canvas, self))
        layout.addWidget(self.canvas)

        self.ax = self.canvas.figure.subplots()
        
        self.test_draw()

    def draw_line(self, data):
        line, = self.ax.plot(*data)
        self.canvas.draw()

    def test_draw(self):
        x = np.arange(20)
        y = np.random.random(size=len(x))
        self.draw_line((x, y))

if __name__ == "__main__":
    app = qtw.QApplication([])
    mw = MatplotlibWidget()

    mw.show()
    app.exec()
