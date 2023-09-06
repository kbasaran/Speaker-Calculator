import numpy as np
import sounddevice as sd
import time
import matplotlib.pyplot as plt
plt.rcParams["figure.dpi"] = 150

class SoundEngine():
    def __init__(self):
        self.FS = sd.query_devices(
            device=sd.default.device,
            kind='output',
            )["default_samplerate"]
        self.start_stream()
        self.test_beep()
        
    def start_stream(self):
        self.stream = sd.OutputStream(samplerate=self.FS, channels=2, latency='high')
        self.stream.start()

    def beep(self, T, freq):
        t = np.arange(T * self.FS) / self.FS
        y = 0.1 * np.sin(t * 2 * np.pi * freq)

        # pad = np.zeros(100)
        # y = np.concatenate([pad, y, pad])

        y = np.tile(y, self.stream.channels)
        y = y.reshape((len(y) // self.stream.channels, self.stream.channels), order='F')
        y = np.ascontiguousarray(y, self.stream.dtype)
        plt.plot(y[-150:-50, :]); plt.grid()
        underflowed = self.stream.write(y)
        print("Underflowed: ", underflowed)

    def test_beep(self):
        self.beep(1, 100)

sound_engine = SoundEngine()
time.sleep(1)

# %%

def beep(T, freq):
    channels = 2

    FS = sd.query_devices(
        device=sd.default.device,
        kind='output',
        )["default_samplerate"]

    t = np.arange(T * FS) / FS
    y = np.tile(0.1 * np.sin(t * 2 * np.pi * freq), channels)
    y = y.reshape((len(y) // channels, channels), order='F')
    y = y.astype(sd.default.dtype[0])
    plt.plot(y[-100:, :]); plt.grid()  # what the signal looks like at the end
    sd.play(y, latency='high')

# beep(1, 200)
