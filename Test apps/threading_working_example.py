import sys
import numpy as np
import sounddevice as sd

from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc

class SoundEngine(qtc.QObject):
    def __init__(self):
        super().__init__()
        self.FS = 48000
        self.start_stream()
        # do a start beep
        self.beep(2, 200)

    def start_stream(self):
        self.stream = sd.Stream(samplerate=self.FS, channels=2)
        self.dtype = self.stream.dtype
        self.channel_count = self.stream.channels[0]
        self.stream.start()

    @qtc.Slot(float, float)
    def beep(self, T=1, freq=1000):
        t = np.arange(T * self.FS) / self.FS
        y = np.tile(0.1 * np.sin(t * 2 * np.pi * freq), self.channel_count)
        y = y.reshape((len(y) // self.channel_count, self.channel_count), order='F').astype(self.dtype)
        y = np.ascontiguousarray(y, self.stream.dtype)
        self.stream.write(y)


class MainWindow(qtw.QMainWindow):
    # https://doc.qt.io/qtforpython-6/tutorials/basictutorial/signals_and_slots.html
    signal_beep = qtc.Signal(float, float)

    def __init__(self, sound_engine):
        super().__init__()
        self.create_widgets()
        self.place_widgets()
        self.make_connections()

    def create_widgets(self):
        self._beep_freq_dial = qtw.QDial(minimum=200,
                                         maximum=2000,
                                         wrapping=False,
                                         )
        self._beep_freq_display = qtw.QLCDNumber()
        self._beep_pusbutton = qtw.QPushButton("Beep")

    def place_widgets(self):
        self._center_widget = qtw.QWidget()
        self._center_layout = qtw.QVBoxLayout(self._center_widget)
        # self._center_widget.set_layout(self._center_layout)
        self.setCentralWidget(self._center_widget)

        self._center_layout.addWidget(self._beep_freq_dial)
        self._center_layout.addWidget(self._beep_freq_display)
        self._center_layout.addWidget(self._beep_pusbutton)

    def make_connections(self):
        self._beep_pusbutton.clicked.connect(
            lambda: self.signal_beep.emit(1, float(self._beep_freq_dial.value()))
            )
        self.signal_beep.connect(sound_engine.beep)

        self._beep_freq_display.display(self._beep_freq_dial.value())
        self._beep_freq_dial.valueChanged.connect(self._beep_freq_display.display)

if __name__ == "__main__":
    app = qtw.QApplication(sys.argv)  # there is a new recommendation with qApp

    sound_engine = SoundEngine()
    sound_engine_thread = qtc.QThread()
    sound_engine.moveToThread(sound_engine_thread)
    sound_engine_thread.start(qtc.QThread.HighPriority)

    mw = MainWindow(sound_engine)
    mw.show()

    app.exec()
