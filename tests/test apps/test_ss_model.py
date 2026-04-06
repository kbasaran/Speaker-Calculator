#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Oct 16 11:15:49 2024

@author: kerem
"""

import numpy as np
from scipy import signal
import matplotlib.pyplot as plt

def generate_freq_list(freq_start, freq_end, ppo):
    """
    Create a numpy array for frequencies to use in calculation.

    ppo means points per octave
    """
    numStart = np.floor(np.log2(freq_start/1000)*ppo)
    numEnd = np.ceil(np.log2(freq_end/1000)*ppo)
    freq_array = 1000*np.array(2**(np.arange(numStart, numEnd + 1)/ppo))
    return freq_array

Mms = 0.008423724385892528
Sd = 52e-4
Vb = 1e-3
Qms = 8
fs = 100
Bl = 4
Rdc = 4
V_in = 1
Qa = 99

GAMMA=1.401  # adiabatic index of air
P0=101325
RHO=1.1839  # 25 degrees celcius
Kair=101325 * 1.401  # could not find a way to refer to RHO here
c_air=(101325 * 1.401 / 1.1839)**0.5
f = generate_freq_list(10, 3000, 48*8)
w = 2*np.pi * f
Kms = Mms * (fs * 2 * np.pi)**2
Rms = (Mms * Kms)**0.5 / Qms
Kbox = Sd**2*Kair/Vb
Rbox = ((Kms + Kbox) * Mms)**0.5 / Qa


ass = np.array([
    [0, 1],
    [-Kbox/Mms-Kms/Mms, -Bl**2/Rdc/Mms-Rms/Mms-Rbox/Mms]
    ])
bss = np.array([[0], [Bl/Rdc/Mms]])
cssx1 = np.array([1, 0])
dss = np.array([0])



sysx1 = signal.StateSpace(ass, bss, cssx1, dss)

# Output arrays
_, x1_1V = signal.freqresp(sysx1, w=w)  # hata veriyo
x1 = np.abs(x1_1V * V_in)

plt.semilogx(x1)
print(x1[0])
