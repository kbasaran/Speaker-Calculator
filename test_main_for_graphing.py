from test_graphing import MatplotlibWidget
from PySide6 import QtWidgets as qtw
from __feature__ import snake_case

class MainWindow(qtw.QMainWindow):

    def __init__(self):
        super().__init__()

        self.graph = MatplotlibWidget()
        self._center_widget = qtw.QWidget()
        
        self._center_layout = qtw.QHBoxLayout(self._center_widget)

        # self.setCentralWidget(self._center_widget)  # regular
        self.set_central_widget(self._center_widget)  # snake case

        # self._center_layout.addWidget(self.graph)  # regular
        self._center_layout.add_widget(self.graph)  # snake case
        
if __name__ == "__main__":
    app = qtw.QApplication([])
    mw = MainWindow()

    mw.show()
    app.exec()
