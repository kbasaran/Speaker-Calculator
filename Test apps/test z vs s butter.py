import scipy.signal as sig
import matplotlib.pyplot as plt
import numpy as np
plt.rcParams["figure.dpi"] = 300
import sys
sys.path.append("..")
import signal_tools


# Center
FS = 48000
nyq = FS / 2
ppo = 3
resolution = 12
x = signal_tools.generate_freq_list(100, 16000, resolution)
i_ref = int(len(x) / 2)
freq_ref = x[i_ref]
# print(freq_ref)
Wn = (freq_ref * 2**(-1/2/ppo), freq_ref * 2**(1/2/ppo))
sos = sig.butter(4, Wn, btype="bandpass", output="sos", fs=FS)
freqs = np.abs(sig.sosfreqz(sos, x, fs=FS))
# plt.semilogx(*freqs, label="center")


errors = []
for offset in np.arange(len(x)) - i_ref:

    # Offset
    i_offset = i_ref + offset
    freq_offset = x[i_offset]
    # print(freq_offset)
    Wn_offset = (freq_offset * 2**(-1/2/ppo), freq_offset * 2**(1/2/ppo))
    sos_offset = sig.butter(4, Wn_offset, btype="bandpass", output="sos", fs=FS)
    freqs_offset = np.abs(sig.sosfreqz(sos_offset, x, fs=FS))
    plt.semilogx(*freqs_offset, label="offset")
    
    # Offset with only shifting
    response = np.zeros(len(x))
    i_write_start = max(0, offset)
    i_write_end = min(len(x), len(x) + offset)
    i_read_start = max(0, -offset)
    i_read_end = min(len(x), len(x) - offset)
    
    response[i_write_start:i_write_end] = freqs[1][i_read_start:i_read_end]
    plt.semilogx(x, response, label="offset with shifting")
    plt.grid()
    # plt.legend()
    plt.show()
    errors.append(np.sum(np.abs(response)) - np.sum(np.abs(freqs_offset[1])))
    print(f"Error: {np.sum(np.abs(response - freqs_offset[1])):.4f}")

print(f"Average error: {100 * np.mean(errors):00.2f}%")
