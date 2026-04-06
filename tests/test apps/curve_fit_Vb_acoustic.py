# -*- coding: utf-8 -*-
"""
Created on Wed Sep 25 11:56:53 2024

@author: kerem.basaran
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
plt.rcParams["figure.dpi"] = 300


def func(x, a):
    return a / x + 1


# values in Unibox for Vb acoustic for Vb of 10_000
# keys are Qa
data_dict = {
    1: 19000,
    2: 14823,
    3: 13348.4,
    4: 12584.6,
    5: 12114.3,
    6: 11794.3,
    7: 11561.9,
    8: 11385,
    9: 11245.7,
    10: 11133,
    12: 10961.6,
    14: 10837,
    16: 10742.2,
    18: 10667.6,
    20: 10607.2,
    25: 10496.7,
    30: 10421.5,
    35: 10366.9,
    40: 10325.4,
    50: 10266.2,
    60: 10225.9,
    70: 10196.6,
    80: 10174.4,
    90: 10156.8,
    100: 10142.6,
    200: 10076.4,
    300: 10053.1,
    400: 10041,
    500: 10033.5,
    1000: 10018,
    2000: 10009.6,
    5000: 10004.2,
}

xdata = np.array([int(val) for val in data_dict.keys()])
ydata = np.array([float(val) for val in data_dict.values()]) / 10_000

bounds = [(0),
          (np.inf)
          ]

popt, pcov = curve_fit(func, xdata, ydata, bounds=bounds)

plt.semilogx(xdata, ydata)
plt.semilogx(xdata, func(xdata, *popt), 'r--', label='fit: a=%5.3f' % tuple(popt))
print(popt)
