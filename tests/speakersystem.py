# This file is part of Speaker Calculator - Loudspeaker design and calculations tool
# Copyright (C) 2026 - Kerem Basaran
# https://github.com/kbasaran
__email__ = "kbasaran@gmail.com"

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import numpy as np
from scipy import signal

from core.models import Enclosure, ParentBody
from core.speaker_system import SpeakerSystem
from core.speaker_driver import SpeakerDriver


def test():
    def generate_freq_list(freq_start, freq_end, ppo):
        """
        Create a numpy array for frequencies to use in calculation.

        ppo means points per octave
        """
        numStart = np.floor(np.log2(freq_start/1000)*ppo)
        numEnd = np.ceil(np.log2(freq_end/1000)*ppo)
        freq_array = 1000*np.array(2**(np.arange(numStart, numEnd + 1)/ppo))
        return freq_array

    freqs = generate_freq_list(10, 3000, 48*8)


    # ---- do default model of 0.1.6
    enclosure = Enclosure(1e-3, 200)
    parent_body = ParentBody(0.1, 25e3, 4)
    my_speaker = SpeakerDriver(111, 53.5e-4, 6.51, Bl=4.78, Re=4.18, Mms=5.09e-3)
    my_system = SpeakerSystem(my_speaker,
                              parent_body=None,
                              enclosure=None,
                              passive_radiator=None,
                              )

    my_system.update_values(speaker=my_speaker, Rext=1, enclosure=enclosure, parent_body=None)

    my_system.update_values(speaker=my_speaker, Rext=1, enclosure=None, parent_body=parent_body)

    my_system.update_values(speaker=my_speaker, Rext=1, enclosure=None, parent_body=None)

    my_system.update_values(speaker=my_speaker, Rext=1, enclosure=None, parent_body=parent_body, passive_radiator=None)

    my_system.update_values(speaker=my_speaker, Rext=0, enclosure=enclosure, parent_body=None, passive_radiator=None)

    # do test model for unibox - Qa / Ql
    # enclosure = Enclosure(0.05, 9999)
    # my_speaker = SpeakerDriver(100, 52e-4, 8, Bl=3, Re=4, Mms=7.7e-3)
    # my_system = SpeakerSystem(my_speaker, enclosure=enclosure)
    # x1 = signal.freqresp(my_system.ss_model, w=np.array([100, 200]))

    import matplotlib.pyplot as plt

    # ---- Time signal
    t = np.arange(0, 0.1, 1/100000)
    u = 2**0.5 * np.sin(25 * 2 * np.pi * t)
    youts = {}
    for i, (key, model) in enumerate(my_system.ss_models.items()):
        _, _, yout = signal.lsim(model, U=u, T=t)
        youts[key] = yout[:, i]

    relative_disp = youts['x1(t)'] - youts['x2(t)']
    if not (min(relative_disp), max(relative_disp) == -0.00024944613211834703, 0.0002494474248713049):
        print("relative displacements NOT PASS test")
    else:
        print("relative displacements PASS")
    print("relative disp min, max:")
    print(min(relative_disp), max(relative_disp))
    plt.plot(t, youts['x1(t)'])
    plt.plot(t, youts['x2(t)'])
    plt.plot(t, youts['x1(t)'] - youts['x2(t)'])
    plt.plot(t, youts['x_pr(t)'])
    plt.grid()
    plt.show()

    # ---- Print out values at frequencies

    # disps = my_system.get_displacements(1, 25)
    # disp_x1 = disps["Diaphragm, peak"]
    # # disp_x2 = disps["Parent body, RMS"] * 2**0.5
    # print("disps: real, abs")
    # print(np.real(disp_x1 - disp_x2), np.abs(disp_x1 - disp_x2))


    # forces = my_system.get_forces(1, 25)
    # print("forces: real, abs")
    # print(np.real(forces["Force from parent body to reference frame, RMS"]), np.abs(forces["Force from parent body to reference frame, RMS"]))

    w, y = signal.freqresp(my_system.ss_models["x1(t)"], w=2*np.pi*freqs)
    y_rms_for_10Vrms = np.abs(y) * 10
    y_for_10Vrms = y_rms_for_10Vrms * 2**0.5
    plt.semilogx(freqs, y_rms_for_10Vrms)
    plt.grid()
    plt.title("x1(t), RMS")
    for i, freq in enumerate(freqs):
        if int(freq) == 200 or i==0 or i==len(freqs)-1:
            print(f"{freqs[i]:.5g}Hz: {y_rms_for_10Vrms[i] * 1e3:.5g}mm RMS")

    return my_system


if __name__ == "__main__":
    test()