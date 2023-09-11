import scipy.signal as sig
import matplotlib.pyplot as plt
import numpy as np
plt.rcParams["figure.dpi"] = 300

len_i = 29
ppo = 6
i_index = int(len_i // 2)

FS = 48000
nyq = FS / 2
x_old = np.array(np.arange(0, nyq, nyq/len_i))
fn_old = (x_old[i_index] * 2**(-1/2/ppo), x_old[i_index] * 2**(1/2/ppo))
sos_old = sig.butter(4, fn_old, btype="bandpass", output="sos", fs=FS)
freqs_old = np.abs(sig.sosfreqz(sos_old, x_old, fs=FS))


Wn = (i_index / len_i * 2**(-1/2/ppo), i_index / len_i * 2**(1/2/ppo))
Wn = [f / nyq for f in fn_old]  # same with above
sos = sig.butter(4, Wn, btype="bandpass", output="sos")
freqs = np.abs(sig.sosfreqz(sos, len_i))

plt.plot(freqs_old[1])
plt.plot(freqs[1])


plt.scatter(i_index, np.abs(freqs[1][i_index]))
plt.grid()

print(freqs_old[0])
print(freqs[0] / 2 / np.pi * FS)

# print(freqs_old[1])
# print(freqs[1])
print(freqs_old[1] / freqs[1])
print()
plt.show()



i_offset = 3

Wn = ((i_index - i_offset) / len_i * 2**(-1/2/ppo), (i_index - i_offset) / len_i * 2**(1/2/ppo))
# Wn = [f / nyq for f in fn_old]  # same with above
sos = sig.butter(4, Wn, btype="bandpass", output="sos")
freqs_2 = np.abs(sig.sosfreqz(sos, len_i))

plt.plot(freqs[1])


response = np.zeros(len_i)
i_write_start = max(0, i_offset)
i_write_end = min(len_i, len_i + i_offset)
i_read_start = max(0, -i_offset)
i_read_end = min(len_i, len_i - i_offset)

print(i_read_start, i_read_end)
print(i_write_start, i_write_end)

response[i_write_start:i_write_end] = freqs_2[1][i_read_start:i_read_end]
plt.plot(response)
plt.grid()

# print(freqs[1])
# print(response)
print(freqs[1] / response)