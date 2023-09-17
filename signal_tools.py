import os
import numpy as np
import acoustics as ac  # https://github.com/timmahrt/pyAcoustics
import soundfile as sf
import logging
from scipy import interpolate as intp
from scipy.ndimage import gaussian_filter
from scipy import signal as sig
import time


class TestSignal():
    """
    Create a signal object that bears methods to create the
    resulting signal together with its analyses.
    """

    def channel_count(self):
        """Give channel count for a signal in matrix form."""
        try:
            shape = self.time_sig.shape
        except Exception as e:
            raise KeyError("Cannot check the shape of generated time signal.", repr(e))

        if len(shape) == 1:
            return 1
        elif len(shape) > 1:
            return shape[1]
        else:
            raise ValueError("Unrecognized channel count.\n", f"Signal shape: {shape}")

    def __init__(self, sig_type, **kwargs):
        action_for_signal_type = {"Pink noise": "generate_pink_noise",
                                  "White noise": "generate_white_noise",
                                  "IEC 268": "generate_IEC_noise",
                                  "Sine wave": "generate_sine",
                                  "Imported": "import_file",
                                  }
        self.sig_type = sig_type
        self.applied_fade_in_duration = None
        try:
            getattr(self, action_for_signal_type[sig_type])(**kwargs)
            """ runs the correct method to create the time signal.
            (**kwargs) does the running. """
        except KeyError as e:
            raise KeyError("Unrecognized signal type. " + str(e))
        self.apply_processing(**kwargs)

    def reuse_existing(self, **kwargs):
        if kwargs["FS"] != self.FS:
            raise NotImplementedError("Resampling of signal not implemented.")
        self.apply_processing(**kwargs)

    def apply_processing(self, **kwargs):
        if "filters" in kwargs.keys():
            self.apply_filters(**kwargs)
        if "compression" in kwargs.keys():
            self.apply_compression(**kwargs)
        if "set_RMS" in kwargs.keys():
            self.normalize(**kwargs)
        if "fadeinout" in kwargs.keys() and kwargs["fadeinout"]:
            self.apply_fade_in_out()
        self.analyze(**kwargs)  # analyze the time signal

    def generate_pink_noise(self, **kwargs):
        self.make_time_array(**kwargs)
        self.time_sig = ac.generator.pink(len(self.t))

    def generate_white_noise(self, **kwargs):
        self.make_time_array(**kwargs)
        self.time_sig = ac.generator.white(len(self.t))

    def generate_IEC_noise(self, **kwargs):
        self.make_time_array(**kwargs)
        time_sig = ac.generator.pink(len(self.t))
        """
        Do IEC 268 filtering (filter parameters fixed by standard)
        Three first-order high-pass filters at 12.9, 32.4, and 38.5 Hz
        Two first-order low-pass filters at 3900, and 9420 Hz
        """
        time_sig = ac.signal.highpass(time_sig, 12.9, self.FS, order=1)
        time_sig = ac.signal.highpass(time_sig, 32.4, self.FS, order=1)
        time_sig = ac.signal.highpass(time_sig, 38.5, self.FS, order=1)
        time_sig = ac.signal.lowpass(time_sig, 3900, self.FS, order=1)
        time_sig = ac.signal.lowpass(time_sig, 9420, self.FS, order=1)
        self.time_sig = time_sig

    def generate_sine(self, **kwargs):
        self.freq = kwargs["frequency"]
        self.make_time_array(**kwargs)
        self.time_sig = np.sin(self.freq * 2 * np.pi * self.t)

    def import_file(self, **kwargs):
        self.import_file_name = os.path.basename(kwargs["import_file_path"])
        self.time_sig, self.FS = sf.read(kwargs["import_file_path"], always_2d=True)
        self.imported_channel_count = self.channel_count()
        self.imported_FS = self.FS

        if (type(self.FS) is not int) or (self.channel_count() < 1):
            self.time_sig, self.FS = None, None
            raise TypeError("Imported signal is invalid.")

        if "import_channel" in kwargs.keys():
            self.reduce_channels(kwargs["import_channel"])
        else:
            self.reduce_channels("downmix_all")

        self.make_time_array(**kwargs)

        self.initial_data_analysis = (f"File name: {self.import_file_name}"
                                      f"\nOriginal channel count: {self.imported_channel_count}"
                                      f"\nImported channel: {str(self.imported_channel + 1) if isinstance(self.imported_channel, int) else self.imported_channel}"
                                      # integer count for user, starting from 1
                                      f"\nOriginal sample rate: {self.imported_FS}"
                                      )

    def reduce_channels(self, channel_to_use):
        # Channel to use can be an integer starting from 1 or "downmix_all"
        if channel_to_use == 0:
            raise ValueError("Channel numbers start from 1. Channel: 0 is invalid.")
        elif channel_to_use == "downmix_all":
            if self.channel_count() == 1:
                self.time_sig = self.time_sig[:, 0]
                self.imported_channel = 0
                return
            elif self.channel_count() > 1:
                self.time_sig = np.mean(self.time_sig, axis=1)
                self.imported_channel = "downmix_all"
            else:
                raise KeyError(f"Unable to downmix. Channel count {self.channel_count()} is invalid.")

        elif isinstance(channel_to_use, int):
            if channel_to_use > self.channel_count():
                raise KeyError(f"Channel {channel_to_use} does not exist in the original signal.")
            else:
                self.time_sig = self.time_sig[:, channel_to_use - 1]
                self.imported_channel = int(channel_to_use) - 1

        else:
            raise TypeError(f"Invalid request for channel_to_use: {[channel_to_use, type(channel_to_use)]}")

    def analyze(self, **kwargs):
        self.neg_peak = np.min(self.time_sig)
        self.pos_peak = np.max(self.time_sig)
        if -self.neg_peak > self.pos_peak:
            self.peak = self.neg_peak
        else:
            self.peak = self.pos_peak
        self.RMS = ac.signal.rms(self.time_sig)
        self.CF = np.abs(self.peak) / self.RMS
        self.CFdB = 20 * np.log10(self.CF)
        self.mean = np.average(self.time_sig)
        self.analysis = (f"Signal type: {self.sig_type}")

        if self.sig_type == "Imported":
            self.analysis += ("\n" + self.initial_data_analysis)

        self.analysis += (f"\nCrest Factor: {self.CF:.4g}x, {self.CFdB:.2f}dB"
                          + f"\nRMS: {self.RMS:.5g}"
                          + f"\nPositive peak: {self.pos_peak:.5g}"
                          + f"\nNegative peak: {self.neg_peak:.5g}"
                          + f"\nMean: {self.mean:.5g}"
                          + f"\nSample rate: {self.FS} Hz"
                          + f"\nDuration: {self.T:.2f} seconds"
                          + f"\nCurrent channel count: {self.channel_count()}"
                          )

        if self.applied_fade_in_duration:
            self.analysis += ("\n\nSignal includes fade in/out of "
                              + self.applied_fade_in_duration + "."
                              )

    def apply_compression(self, **kwargs):
        """
        Based on AES standard noise generator, Aug. 9, 2007, Keele
        """
        k = 4  # shape factor recommended from the AES tool
        a = kwargs.get("compression")

        if a == 0:
            return
        elif a > 0:  # expand
            raise ValueError("Expansion has not implemented yet. "
                             + "Please only use compression values smaller than 0.")

        elif a < 0:  # compress
            self.time_sig = np.sign(self.time_sig) * (
                ((a * np.abs(self.time_sig + 1e-8))**k
                 / ((a*abs(self.time_sig + 1e-8))**k + 1))**(1 / k)) / ((a**k / (a**k + 1))**(1 / k))

    def make_time_array(self, **kwargs):
        if self.sig_type == "Imported":
            self.T = self.time_sig.shape[0] / self.FS
            self.t = np.arange(self.time_sig.shape[0]) / self.FS
        else:
            setattr(self, "T", kwargs.get("T", 5))
            setattr(self, "FS", kwargs.get("FS", 48000))
            # there are default values here. Careful.
            self.t = np.arange(self.T * self.FS) / self.FS

    def normalize(self, **kwargs):
        self.time_sig = self.time_sig / ac.signal.rms(self.time_sig) * kwargs.get("set_RMS", 1)

    def apply_filters(self, **kwargs):
        """
        Need to pass whole filter widget objects to this method.
        Better only pass a dictionary.
        """
        for filter in kwargs.get("filters"):
            filt_type = filter["type"].currentText()
            frequency = filter["frequency"].value()
            order = filter["order"].currentData()
            if filt_type == "HP":
                self.time_sig = ac.signal.highpass(self.time_sig, frequency,
                                                   self.FS, order, zero_phase=False)
            elif filt_type == "LP":
                self.time_sig = ac.signal.lowpass(self.time_sig, frequency,
                                                  self.FS, order, zero_phase=False)
            elif filt_type == "HP (zero phase)":
                self.time_sig = ac.signal.highpass(self.time_sig, frequency,
                                                   self.FS, order//2, zero_phase=True)  # workaround for bug
            elif filt_type == "LP (zero phase)":
                self.time_sig = ac.signal.lowpass(self.time_sig, frequency,
                                                  self.FS, order//2, zero_phase=True)  # workaround for bug
            elif filt_type == "Disabled":
                pass
            else:
                raise KeyError("Unable to apply filter\n", f"Filter type {filt_type} not recognized.")

    def apply_fade_in_out(self):
        n_fade_window = int(min(self.FS / 10, self.T * self.FS / 4))

        # Fade in
        self.time_sig[:n_fade_window] =\
            self.time_sig[:n_fade_window] * make_fade_window_n(0, 1, n_fade_window)

        # Fade out
        self.time_sig[len(self.time_sig) - n_fade_window:] =\
            self.time_sig[len(self.time_sig) - n_fade_window:] * make_fade_window_n(1, 0, n_fade_window)

        self.applied_fade_in_duration = f"{n_fade_window / self.FS * 1000:.0f}ms"


def make_fade_window_n(level_start, level_end, N_total, fade_start_end_idx=None):
    """
    Make a fade-in or fade-out window using information on sample amounts and not time.
    f_start_end defines between which start and stop indexes the fade happens.

    """
    if not fade_start_end_idx:
        fade_start_idx, fade_end_idx = 0, N_total
    else:
        fade_start_idx, fade_end_idx = fade_start_end_idx
    N_fade = fade_end_idx - fade_start_idx

    if N_fade < 0:
        raise ValueError("Fade slice is reverse :(")

    if N_total > 1:
        k = 1 / (N_fade - 1)
        fade_window = (level_start**2 + k * np.arange(N_fade) * (level_end**2 - level_start**2))**0.5
        total_window = np.empty(N_total)

        if fade_start_idx > 0:
            # there are some frames in our output that come before the fade starts
            total_window[:fade_start_idx].fill(level_start)

        if fade_end_idx < N_total:
            # there are some frames in our output that come after the fade ends
            if fade_end_idx > 0:
                total_window[fade_end_idx:].fill(level_end)
            else:
                total_window.fill(level_end)

        if fade_start_idx < N_total and fade_end_idx > 0:
            # some part of the fade window is falling into our [0:N_total] range
            if fade_start_idx >= 0:
                total_window[fade_start_idx:fade_end_idx] = fade_window[:N_total-fade_start_idx]
            elif N_total > fade_end_idx:
                # fade starts before our output starts and ends within our output
                total_window[:fade_end_idx] = fade_window[(0 - fade_start_idx):(fade_end_idx-fade_start_idx)]
            else:
                # fade starts before our output starts and extends further then the end of our output
                total_window[:] = fade_window[(0 - fade_start_idx):(N_total-fade_start_idx)]

    elif N_total <= 1:
        total_window = np.zeros(N_total)

    else:
        raise TypeError("Unknown fade type.")

    return total_window


def make_fade_window_t(level_start, level_end, N_total, FS, fade_start_end_time=None):
    """
    Make a fade-in or fade-out window using time information.
    f_start_end defines between which start and stop times the fade happens.
    All time data in seconds and float.

    """
    if not fade_start_end_time:
        fade_start_time, fade_end_time = 0, N_total / FS
    else:
        fade_start_time, fade_end_time = fade_start_end_time

    fade_start_idx = int(round(fade_start_time * FS))
    fade_end_idx = int(round(fade_end_time * FS))
    fade_start_end_idx = fade_start_idx, fade_end_idx

    return make_fade_window_n(level_start, level_end, N_total, fade_start_end_idx=fade_start_end_idx)


def test_make_fade_window_n():
    import matplotlib.pyplot as plt
    params = [[0.5, 1.5, 10, (-10, -5)],
              [0.5, 1.5, 10, (-5, 5)],
              [0.5, 1.5, 10, (-5, 10)],
              [0.5, 1.5, 10, (4, 6)],
              [0.5, 1.5, 10, (-10, 20)],
              [0.5, 1.5, 10, (5, 15)],
              [0.5, 1.5, 10, (15, 25)],
              [2.5, 1.5, 10, (-10, -5)],
              [2.5, 1.5, 10, (-5, 5)],
              [2.5, 1.5, 10, (4, 6)],
              [2.5, 1.5, 10, (-10, 20)],
              [2.5, 1.5, 10, (5, 15)],
              [2.5, 1.5, 10, (15, 25)],
              [2, 1, 10, (5, 25)],
              [2, 1, 10, (-5, 15)],
              [2, 1, 10, (-15, 5)],
              [1, 0, 10, (0, 10)],
              ]

    for i, param in enumerate(params):
        print(f"Calculating n for param {param}")
        a = make_fade_window_n(*param)
        plt.plot(a**2)
        plt.title(f"Test n {i + 1}: {param}")
        plt.grid()
        plt.show()


def test_make_fade_window_t():
    import matplotlib.pyplot as plt
    params = [[0.5, 1.5, 100, 10, (-10, -5)],
              [0.5, 1.5, 100, 10, (-5, 5)],
              [0.5, 1.5, 100, 10, (-5, 20)],
              [0.5, 1.5, 100, 10, (4, 6)],
              [0.5, 1.5, 100, 10, (-10, 20)],
              [0.5, 1.5, 100, 10, (5, 15)],
              [0.5, 1.5, 100, 10, (15, 25)],
              [2.5, 1.5, 100, 10, (-10, -5)],
              [2.5, 1.5, 100, 10, (-5, 5)],
              [2.5, 1.5, 100, 10, (4, 6)],
              [2.5, 1.5, 100, 10, (-10, 20)],
              [2.5, 1.5, 100, 10, (5, 15)],
              [2.5, 1.5, 100, 10, (15, 25)],
              ]

    for i, param in enumerate(params):
        print(f"Calculating t for param {param}")
        a = make_fade_window_t(*param)
        plt.plot(a**2)
        plt.title(f"Test t {i + 1}: {param}")
        plt.show()


class Curve:
    """
    Item holding a 2D line and information with it such as:
        a dictionary called identification, that holds name, prefix, suffix
    """  

    def __init__(self, initial_data):
        self._identification = {"prefix": "", "base": "", "suffixes": []}
        self._visible = True
        self._reference = False
        self._check_if_sorted_and_valid = check_if_sorted_and_valid
        if isinstance(initial_data, str):
            self._initial_data = initial_data.strip()
            if self.is_Klippel(self._initial_data):
                self._extract_klippel_parameters(self._initial_data)
            else:
                self.set_xy(initial_data)
        else:
            self._initial_data = initial_data
            self.set_xy(initial_data)

    def is_curve(self):
        xy = self.get_xy(ndarray=True)
        if (xy is not None) and (xy.shape[0] == 2) and (xy.shape[1] > 1):
            return True
        else:
            return False

    def is_Klippel(self, import_text):
        return (True if (import_text[:18] == "SourceDesc='dB-Lab") else False)

    def set_reference(self, reference:bool):
        self._reference = reference

    def is_reference(self):
        return self._reference

    def _extract_klippel_parameters(self, import_text):
        # Process the imported text
        self.klippel_attrs = {"unresolved_attrs": []}
        attrs = import_text.split(";")

        usable_attrs = [attr.strip() for attr in attrs if (isinstance(attr, str) and len(attr) > 1)]

        for attr in usable_attrs:
            # Process any comment lines in the text
            attr_mod = attr
            lines = attr_mod.splitlines()
            for i, line in enumerate(lines):
                if len(lines) == i or line[0] != "%":
                    attr_mod = "\n".join(lines[i:])
                    break
                else:
                    self.klippel_attrs["unresolved_attrs"].append(line)

            # Process the variables
            try:
                left, *rights = attr_mod.split("=")
                if len(left) > 1:  # Is it a valid parameter definition?
                    key = left.strip()
                    value = "=".join(rights).strip().strip("'")

                # Is it an array???
                if all([key in value for key in ("\n", "[", "]")]):
                    array = np.genfromtxt(value.removeprefix("[").removesuffix("]").strip().splitlines(),
                                          delimiter="\t",
                                          autostrip=True
                                          )
                    self.klippel_attrs[key] = array
                    logging.info(f"Array imported with shape: {array.shape}")
                elif key not in self.klippel_attrs.keys():
                    self.klippel_attrs[key] = value
                else:
                    logging.error("Key already exists among the parameters somehow...")

            except Exception as e:
                logging.info("Was not able to extract data from string. Error: " + str(e))
                logging.info("\nString:")
                logging.info("\n" + attr_mod)

        # Process the keys
        for key, val in self.klippel_attrs.items():
            if key == "Curve":
                self.set_xy(np.array(val)[:, :2])
                # randomize for testing
                # x, y = self.get_xy()
                # self.set_xy((x, y + np.random.randint(0, high=21)))
            elif key == "Data_Legend":
                self.set_name_base(val)

    def set_xy(self, xy):
        if isinstance(xy, np.ndarray):
            if xy.shape[0] == 2:
                self._check_if_sorted_and_valid(xy[0, :])
                setattr(self, "_x", xy[0, :])
                setattr(self, "_y", xy[1, :])
                setattr(self, "_xy", xy)
            elif xy.shape[1] == 2:
                self._check_if_sorted_and_valid(xy[:, 0])
                setattr(self, "_x", xy[:, 0])
                setattr(self, "_y", xy[:, 1])
                setattr(self, "_xy", np.transpose(xy))
            else:
                raise ValueError("xy is not an array with two columns or 2 rows")

        elif isinstance(xy, tuple) and len(xy[0]) == len(xy[1]):
            self._check_if_sorted_and_valid(np.array(xy[0]))
            setattr(self, "_x", np.array(xy[0]))
            setattr(self, "_y", np.array(xy[1]))
            setattr(self, "_xy", np.row_stack([self._x, self._y]))

        elif isinstance(xy, str):
            i_start, i_stop = 0, 0
            lines = xy.splitlines()

            for i, line in enumerate(lines):
                parts = line.split("\t")
                try:
                    parts = [float(part) for part in parts]
                    # print(parts)
                    assert len(parts) == 2
                    i_start = i
                    break
                except Exception:
                    # print("failed start " + str(i), str(e))
                    continue

            for i, line in enumerate(reversed(lines)):
                parts = line.split("\t")
                try:
                    parts = [float(part) for part in parts]
                    assert len(parts) == 2
                    i_stop = len(lines) - i
                    break
                except Exception:
                    # print("failed end " + str(i), str(e))
                    continue
            # print(i_start, i_stop)
            if i_stop - i_start > 1:
                parts = [line.split("\t") for line in lines[i_start:i_stop]]
                x = [float(part[0]) for part in parts]
                y = [float(part[1]) for part in parts]
                self._check_if_sorted_and_valid(x)
                setattr(self, "_x", np.array(x))
                setattr(self, "_y", np.array(y))
                setattr(self, "_xy", np.row_stack([self._x, self._y]))

            else:
                ValueError("xy input unrecognized")
        else:
            raise ValueError("xy input unrecognized")

    def get_xy(self, ndarray=False):
        if ndarray:
            # (2, N) shaped
            return getattr(self, "_xy", None)
        else:
            return getattr(self, "_x", None), getattr(self, "_y", None)

    def get_x(self):
        return getattr(self, "_x", None)

    def get_y(self):
        return getattr(self, "_y", None)

    def set_name_base(self, name):
        val = name if isinstance(name, str) else None
        self._identification["base"] = val

    def set_name_prefix(self, prefix):
        val = prefix if isinstance(prefix, str) else None
        self._identification["prefix"] = val

    def clear_name_suffixes(self):
        self._identification["suffixes"].clear()

    def has_name_prefix(self):
        prefix = self._identification["prefix"]
        return isinstance(prefix, str) and len(prefix) > 0

    def add_name_suffix(self, name):
        if isinstance(name, (str, int)):
            self._identification["suffixes"].append(name)

    def remove_name_suffix(self, name):
        suffixes = self._identification["suffixes"]
        self._identification["suffixes"] = [suffix for suffix in suffixes if suffix != name]

    def get_name_suffixes(self):
        suffixes = self._identification["suffixes"]
        return suffixes

    def get_name_base(self):
        self._identification["base"]
        if self._identification["base"] in (None, ""):
            x = self.get_xy()[0]
            self._identification["base"] = f"Curve with {len(x)} data points, {x[0]:.5g}Hz-{x[-1]:.5g}Hz"
        return self._identification["base"]

    def get_base_name_and_suffixes(self, joiner=" - "):
        full_name = self.get_name_base()
        for suffix in self.get_name_suffixes():
            full_name += (joiner + str(suffix))
        return full_name

    def get_full_name(self, joiner=" - "):
        base_name_and_suffixes = self.get_base_name_and_suffixes()
        if prefix := self._identification.get("prefix"):
            return joiner.join((prefix, base_name_and_suffixes))
        else:
            raise ValueError("Prefix was not defined")

    def set_visible(self, val):
        assert isinstance(val, bool)
        self._visible = val

    def is_visible(self):
        return self._visible


def check_if_sorted_and_valid(flat_array):
    # check if array of numbers
    array = np.array(flat_array, dtype=float)

    is_sorted = lambda a: np.all(a[:-1] < a[1:])
    if not is_sorted(array):
        raise ValueError("Frequency points are not sorted")
    if array[0] <= 0:
        raise ValueError("Negatives or zeros are not accepted as frequency points.")

def discover_fs_from_time_signature(curve):
    if not any(["[ms]" in string for string in curve.klippel_attrs["unresolved_parts"]]):
        raise TypeError("x array unit is not ms. Cannot process.")
    pos_0ms = np.where(curve.get_xy[0] == 0)
    pos_100ms = np.where(curve.get_xy[0] == 100)
    if any([len(array) != 1 for array in (pos_0ms, pos_100ms)]):
        raise ValueError("x array does not seem to be linear.")
    return int((pos_100ms[0] - pos_0ms[0]) * 10)


def convolve_with_signal(ir, my_sig, ir_FS=None, my_sig_FS=None, trim_zeros=True):
    # Input IR is an array
    if isinstance(ir, (list, np.ndarray)):
        if ir_FS is None:
            raise ValueError("You need to provide the sampling rate of the input signal array.")
        logging.info(f"Using a table from {type(ir)} as impulse response input.")
        y1 = np.array(ir)
        y1_FS = ir_FS

    # Input IR is a KlippelExportObject object
    elif isinstance(ir, Curve):
        if "Impulse Response".lower() not in ir.SourceDesc.lower():
            raise TypeError("Invalid impulse response data. Please use export tab in settings to export.")
        if not ir.klippel_attrs["SourceDesc"] == "Windowed Impulse Response":
            logging.warning("Suggested to use 'Windowed Impulse Response'"
                            f" instead of current '{ir.SourceDesc}'!"
                            )
        y1 = ir.get_xy[1]
        y1_FS = discover_fs_from_time_signature(ir)

    # Input my_sig is an array
    if isinstance(my_sig, (list, np.ndarray)):
        if my_sig_FS is None:
            raise ValueError("You need to provide the sampling rate of the input signal array.")
        logging.info(f"Using a table from {type(ir)} as user signal input.")
        y2 = np.array(my_sig)
        y2_FS = my_sig_FS

    # Input my_sig is a TestSignal object
    elif isinstance(my_sig, TestSignal):
        if my_sig_FS is not None:
            logging.warning(f"Ignoring my_sig_FS key argument and using attribute my_sig.FS : {my_sig_FS}")
        if my_sig.channel_count() > 1:
            raise TypeError("Invalid signal. Signal must have only one channel."
                            f"\nChannels: {my_sig.channel_count()}")
        y2 = my_sig.time_sig
        y2_FS = my_sig.FS

    # Check for FS match
    if y2_FS != y1_FS:
        raise ValueError(f"Sample rate mismatch! Sample rate of the IR is {y1_FS} while that of input"
                         f" signal is {y2_FS}."
                         )

    # Check if y1 is a 1-D vector
    if len(y1.shape) > 1:
        raise ValueError(f"IR input array is not a 1-D vector. Shape: {y1.shape}")

    # Check if y2  is a 1-D vector
    if len(y2.shape) > 1:
        raise ValueError(f"IR input array is not a 1-D vector. Shape: {y2.shape}")

    # Trim zeros from IR array
    if trim_zeros is True and y1[-1] == 0:
        y1 = np.append(np.trim_zeros(y1, 'b'), 0)

    # Check if signal length allows for full overlap
    if len(y2) < len(y1):
        raise ValueError("Input signal is not long enough to overlap completely with the impulse response."
                         " Use a shorter impulse response, longer signal file,"
                         " or activate 'trim_zeros' if you haven't."
                         )

    # Do convolve
    y_conv = np.convolve(y1, y2, mode="valid")

    return y_conv, y2_FS


def calculate_third_oct_power_from_pressure(p, FS):
    third_oct_freqs = ac.standards.iec_61672_1_2013.NOMINAL_THIRD_OCTAVE_CENTER_FREQUENCIES

    return third_oct_freqs, ac.signal.third_octaves(p, FS, frequencies=third_oct_freqs)[1]


def generate_log_spaced_freq_list(freq_start, freq_end, ppo, must_include_freq=1000, superset=False):
    """
    Create a numpy array for frequencies to use in calculation.
    ppo means points per octave
    makes sure all points fall within defined frequency range if superset is False.
    Otherwise 1 more point will be added to each end.
    """
    if freq_start * freq_end * must_include_freq == 0:
        raise ValueError("Cannot use 0 Hz as a valid frequency point for octave spacing.")
    if superset:
        numStart = np.floor(np.log2(freq_start/must_include_freq)*ppo)
        numEnd = np.ceil(np.log2(freq_end/must_include_freq)*ppo)
    else:
        numStart = np.ceil(np.log2(freq_start/must_include_freq)*ppo)
        numEnd = np.floor(np.log2(freq_end/must_include_freq)*ppo)
    freq_array = must_include_freq*np.array(2**(np.arange(numStart, numEnd + 1)/ppo))
    return freq_array


def smooth_curve_rectangular_no_interpolation(x, y, bandwidth=3, ndarray=False):
    y_filt = np.zeros(len(x), dtype=float)
    y_power = 10**(y / 10)
    for i, freq in enumerate(x):
        f_critical = freq * 2**(-1 / 2 / bandwidth), freq * 2**(1 / 2 / bandwidth)
        # https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.butter.html#scipy.signal.butter
        i_start = np.searchsorted(x, f_critical[0])
        i_end = np.searchsorted(x, f_critical[1], side="right")
        y_average_power = np.mean(y_power[i_start:i_end])
        y_filt[i] = 10 * np.log10(y_average_power)

    return np.column_stack((x, y_filt)) if ndarray else x, y_filt


def smooth_curve_gaussian(x, y, bandwidth=3, resolution=96, ndarray=False):
    x_intp, y_intp = interpolate_to_ppo(x, y, resolution, superset=False)
    sigma = resolution / bandwidth / 2  # one octave, divided by bandwidth
    y_filt = gaussian_filter(y_intp, sigma, mode="nearest")

    return np.column_stack((x_intp, y_filt)) if ndarray else x_intp, y_filt


def smooth_curve_butterworth(x, y, bandwidth=3, order=8, ndarray=False, FS=None):
    if not FS:
        FS = 48000 * 2**((x[-1] * 3) // 48000)  # no input frequencies above 2/3 of Nyquist freq.
    else:
        pass

    y_filt = np.zeros(len(x), dtype=float)
    for i, freq in enumerate(x):
        f_critical = freq * 2**(-1 / 2 / bandwidth), x[-1], freq * 2**(1 / 2 / bandwidth)
        if f_critical[0] < x[0] or f_critical[1] > x[-1]:
            y_filt[i] = np.nan
        else:
            # https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.butter.html#scipy.signal.butter
            sos = sig.butter(order, f_critical, btype="bandpass", output="sos", fs=FS)
            _, filtering_array = sig.sosfreqz(sos, x, fs=FS)
            filtering_array_abs = np.abs(filtering_array)
            filtered_array_of_power = 10**(y/10) * filtering_array_abs / np.sum(filtering_array_abs)
            # in above line instead of the division by the sum, division by "resolution * bandwidth"
            # should also have worked but has some offset in it..
            y_filt[i] = 10 * np.log10(np.sum(filtered_array_of_power))

    return np.column_stack((x, y_filt)) if ndarray else x, y_filt


def smooth_log_spaced_curve_butterworth(x, y, bandwidth=3, resolution=96, order=8, ndarray=False, FS=None):
    if not FS:
        FS = 48000 * 2**((x[-1] * 3) // 48000)  # no input frequencies above 2/3 of Nyquist freq.
    else:
        pass
    x_intp, y_intp = interpolate_to_ppo(x, y, resolution)

    y_filt = np.zeros(len(x_intp), dtype=float)
    for i, freq in enumerate(x_intp):
        f_critical = freq * 2**(-1 / 2 / bandwidth), freq * 2**(1 / 2 / bandwidth)
        if f_critical[0] < x_intp[0] or f_critical[1] > x_intp[-1]:
            y_filt[i] = np.nan
        else:
            # https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.butter.html#scipy.signal.butter
            sos = sig.butter(order, f_critical, btype="bandpass", output="sos", fs=FS)
            _, filtering_array = sig.sosfreqz(sos, x_intp, fs=FS)
            filtering_array_abs = np.abs(filtering_array)
            filtered_array_of_power = 10**(y_intp/10) * filtering_array_abs / np.sum(filtering_array_abs)
            # in above line instead of the division by the sum, division by "resolution * bandwidth"
            # should also have worked but has some offset in it..
            y_filt[i] = 10 * np.log10(np.sum(filtered_array_of_power))

    return np.column_stack((x_intp, y_filt)) if ndarray else x_intp, y_filt


def smooth_log_spaced_curve_butterworth_fast(x, y, bandwidth=3, resolution=96, order=8, ndarray=False, FS=None):
    if not FS:
        FS = 48000 * 2**((x[-1] * 3) // 48000)  # no input frequencies above 2/3 of Nyquist freq.
    else:
        pass
    x_intp, y_intp = interpolate_to_ppo(x, y, resolution)

    y_filt = np.zeros(len(x_intp), dtype=float)
    i_for_bandpass_calculation = int(len(y_filt) / 2)
    freq_for_bandpass_calculation = x_intp[i_for_bandpass_calculation]
    f_critical = (freq_for_bandpass_calculation * 2**(-1/2/bandwidth), freq_for_bandpass_calculation * 2**(1/2/bandwidth))
    sos = sig.butter(order, f_critical, btype="bandpass", output="sos", fs=FS)
    filter_response = np.abs(sig.sosfreqz(sos, x_intp, fs=FS)[1])
    filter_response = filter_response

    for i_filter_position in range(len(x_intp)):
        offset = i_filter_position - i_for_bandpass_calculation

        shifted_filter_response = np.zeros(len(x_intp))
        i_write_start = max(0, offset)
        i_write_end = min(len(x_intp), len(x_intp) + offset)
        i_read_start = max(0, -offset)
        i_read_end = min(len(x_intp), len(x_intp) - offset)

        shifted_filter_response[i_write_start:i_write_end] = filter_response[i_read_start:i_read_end]
        filtered_array_of_power = 10**(y_intp/10) * shifted_filter_response / np.sum(shifted_filter_response)
        
        y_filt[i_filter_position] = 10 * np.log10(np.sum(filtered_array_of_power))

    return np.column_stack((x_intp, y_filt)) if ndarray else x_intp, y_filt


def interpolate_to_ppo(x, y, ppo, must_include_freq=1000, superset=False):
    """
    Reduce a curve to lesser points
    """
    freq_start, freq_end = x[0], x[-1]
    freqs = generate_log_spaced_freq_list(freq_start,
                               freq_end,
                               ppo,
                               must_include_freq=must_include_freq,
                               superset=superset,
                               )

    f = intp.interp1d(np.log(x), y, assume_sorted=True, bounds_error=False)
    return freqs, f(np.log(freqs))


def arrays_are_equal(arrays):
    for i in range(1, len(arrays)):
        if not np.array_equal(arrays[0], arrays[i]):
            return False
    return True


def mean_and_median_of_curves(curves_xy: list):
    """
    Calculate median of curves

    Parameters
    ----------
    curves_xy : list
        Receives list of tuples where each tuple is an x,y array.

    Returns
    -------
    tuple for x and y

    """
    if arrays_are_equal([x for x, y in curves_xy]):
        y_arrays = np.column_stack([y for x, y in curves_xy])
        y_mean = np.mean(y_arrays, axis=1)
        y_median = np.median(y_arrays, axis=1)  # how about scipy.signal median filter??
    else:
        raise NotImplementedError("Curves do not have the exact same frequency points."
                                  "\nConsider interpolating to a common frequency array first.")

    return Curve((curves_xy[0][0], y_mean)), Curve((curves_xy[0][0], y_median))


def iqr_analysis(curves_xy: dict, outlier_fence_iqr):
    if not arrays_are_equal([x for x, y in curves_xy.values()]):
        raise NotImplementedError("Curves do not have the exact same frequency points."
                                  "\nConsider interpolating to a common frequency array first.")
    x_array = list(curves_xy.values())[0][0]
    y_arrays = np.column_stack([y for x, y in curves_xy.values()])

    q1, median, q3 = np.percentile(y_arrays, (25, 50, 75), axis=1, method='median_unbiased')
    iqr = q3 - q1
    lower_fence = median - iqr * outlier_fence_iqr
    upper_fence = median + iqr * outlier_fence_iqr

    outlier_down = np.any(y_arrays < lower_fence.reshape((-1, 1)), axis=0)
    outlier_up = np.any(y_arrays > upper_fence.reshape((-1, 1)), axis=0)
    outliers_all = outlier_up | outlier_down

    outlier_indexes = list(np.array(list(curves_xy.keys()), dtype=int)[outliers_all])

    return (
        Curve((x_array, lower_fence)),
        Curve((x_array, median)),
        Curve((x_array, upper_fence)),
        outlier_indexes
        )


def calculate_graph_limits(y_arrays, multiple=5, clearance_up_down=(2, 1)):

    def floor_to_multiple(number, multiple, clearance_down):
        return multiple * np.floor((number - clearance_down) / multiple)

    def ceil_to_multiple(number, multiple, clearance_up):
        return multiple * np.ceil((number + clearance_up) / multiple)

    if y_arrays:
        y_points = np.concatenate([y_array for y_array in y_arrays])
        y_points = y_points[np.isfinite(y_points)]
        y_max = ceil_to_multiple(np.max(y_points), multiple, clearance_up_down[0])
        y_min = floor_to_multiple(np.min(y_points), multiple, clearance_up_down[1])
        return y_min, y_max
    else:
        return None, None


if __name__ == "__main__":
    test_make_fade_window_n()
    # test_make_fade_window_t()
