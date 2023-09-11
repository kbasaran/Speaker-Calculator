import scipy.signal as sig
import matplotlib.pyplot as plt
import numpy as np
plt.rcParams["figure.dpi"] = 300

len_i = 7
ppo = 6
i_index = int(len_i // 2)

FS = 48000
x_old = np.array(np.arange(0, FS/2, FS/2/len_i))
fn_old = (x_old[i_index] * 2**(-1/2/ppo), x_old[i_index] * 2**(1/2/ppo))
sos_old = sig.butter(8, fn_old, btype="bandpass", output="sos", fs=FS)
freqs_old = np.abs(sig.sosfreqz(sos_old, x_old, fs=FS))


Wn = (i_index / len_i * 2**(-1/2/ppo), i_index / len_i * 2**(1/2/ppo))
sos = sig.butter(8, Wn, btype="bandpass", output="sos")
freqs = np.abs(sig.sosfreqz(sos, len_i))

plt.plot(freqs_old[1])
plt.plot(freqs[1])


plt.scatter(i_index, np.abs(freqs[1][i_index]))
plt.grid()
print(freqs_old)
print(freqs[0] / 2 / np.pi * FS, freqs[1])
