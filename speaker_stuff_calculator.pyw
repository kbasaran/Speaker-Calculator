# -*- coding: utf-8 -*-
"""
Speaker Stuff Calculator main module.
hosted on "github.com/kbasaran/Speaker-Stuff-Calculator"
"""
import sys
import numpy as np
import pandas as pd
from scipy import signal
from dataclasses import dataclass
import pickle
from PySide2.QtCore import SIGNAL, SLOT, QObject, Qt  # Qt is necessary for alignment of titles
from PySide2 import QtWidgets as qtw
from PySide2 import QtGui as qtg

from functools import partial
from pathlib import Path
import sounddevice as sd

from matplotlib.backends.backend_qt5agg import (
        FigureCanvasQTAgg as FigureCanvas)
from matplotlib.backends.backend_qt5agg import (
        NavigationToolbar2QT as NavigationToolbar)
from matplotlib.figure import Figure

import logging
logging.basicConfig(level=logging.INFO)

version = "0.2.0rc"


def generate_freq_list(freq_start, freq_end, ppo):
    """
    Create a numpy array for frequencies to use in calculation.

    ppo means points per octave
    """
    numStart = np.floor(np.log2(freq_start/1000)*ppo)
    numEnd = np.ceil(np.log2(freq_end/1000)*ppo)
    freq_array = 1000*np.array(2**(np.arange(numStart, numEnd + 1)/ppo))
    return freq_array


def find_nearest_freq(array: np.array, desired: (int, float)):
    """
    Lookup a table to find the nearest frequency to argument 'desired'.

    Parameters
    ----------
    array : np.array
    value : int, float

    Returns
    -------
    closest_val
        Closest value found.
    idx : int
        Index of closest value.
    """
    err = [np.abs(i-desired) for i in array]
    idx = err.index(min(err))
    return array[idx], idx


def read_clipboard():
    try:
        return(0, pd.read_clipboard(header=None))
    except Exception:
        return(1, None)


def analyze_clipboard_data(err, clpd):
    """Check clipboard data and try to extract a 2D plot from it."""

    def is_number(val):
        try:
            float(val)
            return True
        except (ValueError, TypeError):
            return False

    title = ""
    if (err == 0) and isinstance(clpd, pd.core.frame.DataFrame):
        pddf, data_type = clpd, type(clpd)
        if len(pddf.columns) == 2 and len(pddf.index) > 1:
            row_content = {"title": set(),
                           "array": set(),
                           }
            for row_id, row_data in pddf.iterrows():
                # row_data is a tuple of each column
                if all([is_number(data) for data in row_data]):
                    row_content["array"].add(row_id)
                else:  # there are non-numeric values in the row
                    if len(row_content["array"]) == 0:
                        # didn't find the array yet, must still be the title
                        row_content["title"].add(row_id)
                        if row_data[0].split(" = ")[0] == "GraphTitle":
                            title = row_data[0].rstrip("';").lstrip("GraphTitle = '")
                    else:
                        # array is finished
                        break  # don't look any further

            array_data = pddf.iloc[sorted(row_content["array"])].reset_index(drop=True).astype(float)
            return data_type, title, array_data
        else:
            return data_type, title, None
    else:
        return None, None, None


class Record(object):
    """Make a simple object to store attributes."""

    def setattrs(self, **dictionary):
        """Add attributes to the object in a loop."""
        for k, v in dictionary.items():
            setattr(self, k, v)


# Put some constants in a Record object
cons = Record()
cons.setattrs(GAMMA=1.401,  # adiabatic index of air
              P0=101325,
              RHO=1.1839,  # 25 degrees celcius
              Kair=101325 * 1.401,  # could not find a way to refer to RHO here
              c_air=(101325 * 1.401 / 1.1839)**0.5,
              vc_table_file=Path.cwd().joinpath('SSC_data', 'WIRE_TABLE.csv')
              )
setattr(cons, "VC_TABLE", pd.read_csv(cons.vc_table_file, index_col="Name"))
setattr(cons, "f", generate_freq_list(10, 3000, 48*8))
setattr(cons, "w", 2*np.pi*cons.f)
setattr(cons, "FS", 48000)


def beep(frequency=1175, requested_duration=60):
    """Beep without a click in the end."""
    FS = cons.FS
    N_wave = round(frequency * requested_duration / 1e3, 0)  # made integer to avoid clicking end of signal
    N_sample = int(N_wave * FS / frequency) + 1
    signal = (0.5 * np.sin(frequency * 2 * np.pi * (np.arange(N_sample)) / FS)).astype(np.float32)
    sd.play(signal, FS)


def beep_bad():
    beep(frequency=int(1175/2))


def calculate_air_mass(Sd):
    """Air mass on diaphragm; the difference between Mms and Mmd."""
    return 1.13*(Sd)**(3/2)  # m2 in, kg out


def calculate_Lm(Bl, Re, Mms, Sd):
    """Calculate Lm@Re, 1W, 1m."""
    w_ref = 10**-12
    I_1W_per_m2 = cons.RHO * Bl**2 * Sd**2 / cons.c_air / Re / Mms**2 / 2 / np.pi
    P_over_I_half_space = 1/2/np.pi  # m²
    return 10 * np.log10(I_1W_per_m2 * P_over_I_half_space / w_ref)


def calculate_Xmech(Xmax):
    """Proposed Xmech value for given Xmax value.

    All values in basic SI units.
    """
    Xclearance = 1e-3 + (Xmax - 3e-3) / 5
    return Xmax + Xclearance


def calculate_windings(wire_type, N_layers, former_OD, h_winding):
    """Calculate coil mass, Rdc and l for a given coil."""
    global cons
    w_wire = cons.VC_TABLE.loc[wire_type, "width, m*e-6, avg"] / 1e6
    w_wire_max = cons.VC_TABLE.loc[wire_type, "width, m*e-6, max"] / 1e6
    h_wire = cons.VC_TABLE.loc[wire_type, "height, m*e-6, avg"] / 1e6
    stacking_coef = cons.VC_TABLE.loc[wire_type, "stacking coeff."]

    def calc_N_winding_per_layer(i_layer):
        """Calculate the number of windings that fit on one layer of coil."""
        val = h_winding / h_wire - i_layer * 2  # 2 windings less on each stacked layer
        return -1 if val < 1 else val

    def calc_length_of_one_turn_per_layer(i_layer):
        """Calculate the length of one turn of wire on a given coil layer."""
        if i_layer == 1:
            turn_mean_radius = former_OD/2 + w_wire/2
        if i_layer > 1:
            turn_mean_radius = former_OD/2 + w_wire/2 + (stacking_coef * (i_layer - 1) * w_wire)
        # pi/4 is stacking coefficient
        return 2*np.pi*turn_mean_radius

    # Windings amount for each layer
    N_windings = [calc_N_winding_per_layer(i)
                  for i in range(N_layers)]

    # Wire length for one full turn around for a given layer
    l_one_turn = [calc_length_of_one_turn_per_layer(i_layer) for i_layer in range(1, N_layers+1)]

    total_length_wire_per_layer = [N_windings[i] * l_one_turn[i]
                                   for i in range(N_layers)]

    l_wire = sum(total_length_wire_per_layer)
    Rdc = l_wire * cons.VC_TABLE.loc[wire_type, "ohm/m"]
    w_coil_max = w_wire_max * (1 + (N_layers - 1) * stacking_coef)
    coil_mass = l_wire * cons.VC_TABLE.loc[wire_type, "g/m"] / 1000

    N_windings_rounded = [int(np.round(i)) for i in N_windings]
    return(Rdc, N_windings_rounded, l_wire, w_coil_max, coil_mass)


def calculate_input_voltage(excitation, Rdc, nominal_impedance):
    """Simplify electrical input definition to input voltage."""
    val, type = excitation
    if type == "Wn":
        input_voltage = (val * nominal_impedance) ** 0.5
    elif type == "W":
        input_voltage = (val * Rdc) ** 0.5
    elif type == "V":
        input_voltage = val
    else:
        print("Input options are [float, ""V""], \
              [float, ""W""], [float, ""Wn"", float]")
        return None
    return input_voltage


@dataclass
class UserForm():

    def __post_init__(self):
        """Post-init the form."""
        self.user_curves = []
        my_path = "C:\\Users\\kerem.basaran\\OneDrive - PremiumSoundSolutions\\Documents\\_Python\\SSC files"
        if Path(my_path).exists():
            self.pickles_path = Path(my_path)
        else:
            self.pickles_path = Path.cwd()

    def load_pickle(self, file=None):  # this function is messed up, improve it
        try:
            if not file.exists():
                raise Exception("File not found")
        except Exception:
            file = Path(qtw.QFileDialog.getOpenFileName(None, caption='Open file',
                                                        dir=str(self.pickles_path),
                                                        filter='Speaker stuff calculator files (*.sscf)')[0])

        self.pickles_path = file.parent  # remember what folder was used last time

        with file.open(mode="rb") as handle:
            form_dict = pickle.load(handle)
            print("Loaded file %s" % file.name)

            setattr(self, "coil_options_table", form_dict.pop("coil_options_table"))
            form.coil_choice_box["obj"].clear()
            if form_dict["motor_spec_type"]["userData"] == "define_coil":
                coil_choice = (form_dict["coil_choice_box"]["name"],
                               form_dict["coil_choice_box"]["userData"])
                form.coil_choice_box["obj"].addItem(*coil_choice)

            items_to_skip = ["result_sys", "pickles_path"]
            for item_name, value in form_dict.items():
                if item_name not in items_to_skip:
                    self.set_value(item_name, value)

        update_model()

    def save_to_pickle(self):  # add save dialog
        """Save design to a file."""
        # Need to add error handling to avoid invalid saves
        form_dict = {"result_sys": result_sys}
        for key, value in self.__dict__.items():
            obj_value = self.get_value(key)
            form_dict[key] = obj_value

        file = Path(qtw.QFileDialog.getSaveFileName(None, caption='Save to file',
                                                    dir=str(self.pickles_path),
                                                    filter='Speaker stuff calculator files (*.sscf)')[0])
        self.pickles_path = file.parent  # remember what folder was used

        with file.open('wb') as handle:
            pickle.dump(form_dict, handle)
            print("Saved to file %s" % file.name)

    # Convenience functions to add rows to input_form_layout layout
    def add_line(self, to_layout):
        """Add a separator line in the form layout."""
        line = qtw.QFrame()
        line.setFrameShape(qtw.QFrame.HLine)
        line.setFrameShadow(qtw.QFrame.Sunken)
        line.setContentsMargins(0, 10, 0, 10)
        to_layout.addRow(line)

    def add_title(self, to_layout, string):
        """Add a title to different user input form groups."""
        title = qtw.QLabel()
        title.setText(string)
        title.setStyleSheet("font-weight: bold")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        to_layout.addRow(title)

    def add_double_float_var(self, to_layout, var_name, description, min_val=0,
                             max_val=1e5, default=0, unit_to_SI=1):
        """Add a row for double float user variable input."""
        item = {"obj": qtw.QDoubleSpinBox(), "unit_to_SI": unit_to_SI}
        item["obj"].setMinimumSize(52, 18)
        item["obj"].setRange(min_val, max_val)
        item["obj"].setStepType(qtw.QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        setattr(self, var_name, item)
        self.set_value(var_name, default*unit_to_SI)
        to_layout.addRow(description,  getattr(self, var_name)["obj"])

    def add_combo_box(self, to_layout, combo_box_name, combo_list, combo_box_screen_name=False):
        """Make a combo box.

        combo_box_name is the attribute name under form object
        item_list contains tuples as list items. first is visible name second is user_data.
        """
        item = {"obj": qtw.QComboBox()}
        item["obj"].setMaxVisibleItems(19)
        item["obj"].setMinimumSize(52, 18)
        for choice in combo_list:
            item["obj"].addItem(*choice)  # sometimes contains userData, therefore *
        setattr(self, combo_box_name, item)
        if combo_box_screen_name:
            to_layout.addRow(combo_box_screen_name, getattr(self, combo_box_name)["obj"])
        else:
            to_layout.addRow(getattr(self, combo_box_name)["obj"])

    def add_integer_var(self, to_layout, var_name, description, min_val=1,
                        max_val=1e6, default=0, unit_to_SI=1):
        """Add a row for integer value user variable input."""
        item = {"obj": qtw.QSpinBox(), "unit_to_SI": unit_to_SI}
        item["obj"].setMinimumSize(52, 18)
        item["obj"].setRange(min_val, max_val)
        setattr(self, var_name, item)
        self.set_value(var_name, default*unit_to_SI)
        to_layout.addRow(description,  getattr(self, var_name)["obj"])

    def add_string_var(self, to_layout, var_name, description, default=""):
        """Add string var."""
        item = {"obj": qtw.QLineEdit()}
        item["obj"].setMinimumSize(52, 18)
        setattr(self, var_name, item)
        self.set_value(var_name, default)
        to_layout.addRow(description, getattr(self, var_name)["obj"])

    def set_value(self, item_name, value):
        """Set value of a form item."""
        item = getattr(self, item_name)
        try:
            if isinstance(item["obj"], QObject):
                qwidget_obj = item["obj"]
                if isinstance(qwidget_obj, qtw.QLineEdit):
                    if isinstance(value, str):
                        qwidget_obj.setText(value)
                    else:
                        raise Exception(f"Incorrect data type {type(value)} for {qwidget_obj}")

                elif isinstance(qwidget_obj, qtw.QPlainTextEdit):
                    if isinstance(value, str):
                        qwidget_obj.setPlainText(value)
                    else:
                        raise Exception(f"Incorrect data type {type(value)} for {qwidget_obj}")

                elif isinstance(qwidget_obj, (qtw.QDoubleSpinBox, qtw.QSpinBox)):
                    if isinstance(value, (float, int)):
                        qwidget_obj.setValue(value / item["unit_to_SI"])
                    else:
                        raise Exception(f"Incorrect data type {type(value)} for {qwidget_obj}")

                elif isinstance(qwidget_obj, qtw.QComboBox):  # recevies dict with entry_name
                    if isinstance(value, str):
                        qwidget_obj.setCurrentText(value)
                    elif isinstance(value, dict):
                        qwidget_obj.setCurrentText(value["name"])
                        # qwidget_obj.setCurrentData(value["userData"])
                    else:
                        raise Exception(f"Incorrect type {type(value)} of {value} for combobox.set_value")

                elif isinstance(qwidget_obj, qtw.QButtonGroup):
                    for button in qwidget_obj.buttons():
                        button.setChecked(button.text() == value)
                else:
                    raise Exception(f"Don't know how to set {item_name} with value {value}")

        except Exception:
            setattr(self, item_name, value)
            return

    def get_value(self, item_name):
        """Get value of a form item."""
        item = getattr(self, item_name)
        try:
            qwidget_object = item["obj"]
            if isinstance(qwidget_object, qtw.QLineEdit):
                return qwidget_object.text()
            elif isinstance(qwidget_object, qtw.QPlainTextEdit):
                return qwidget_object.toPlainText()
            elif isinstance(qwidget_object, (qtw.QDoubleSpinBox, qtw.QSpinBox)):
                return qwidget_object.value() * item["unit_to_SI"]
            elif isinstance(qwidget_object, qtw.QComboBox):  # returns dict (name, userData)
                return {"name": qwidget_object.currentText(), "userData": qwidget_object.currentData()}
            elif isinstance(qwidget_object, qtw.QButtonGroup):
                return qwidget_object.checkedButton().text()
        except Exception:
            if not isinstance(item, qtw.QWidget):
                return item
                raise Exception(f"Don't know how to read {item_name} with type {type(item)}")

    def update_coil_choice_box(self):
        """Scan best matching speaker coil options."""
        self.coil_choice_box["obj"].clear()
        try:  # try to read the N_layer_options string
            layer_options = [int(str) for str in self.N_layer_options["obj"].text().replace(" ", "").split(",")]
        except Exception:
            self.error = "Invalid input in number of layer options"
            self.coil_choice_box["obj"].addItem("--" + self.error + "--")
            beep_bad()
            return
        table_columns = ["N_layers", "wire_type", "Bl", "Rdc", "Lm", "Qts", "former_ID",
                         "t_former", "h_winding", "N_windings", "l_wire", "w_coil_max", "coil_mass"]
        self.coil_options_table = pd.DataFrame(columns=table_columns)  # make a dataframe to store viable winding options

        # Scan through winding options
        winding = Record()
        for k in ["target_Rdc", "former_ID", "t_former", "h_winding"]:
            setattr(winding, k, self.get_value(k))

        for N_layers in layer_options:
            for wire_type, row in cons.VC_TABLE.iterrows():
                Rdc, N_windings, l_wire, w_coil_max, coil_mass = calculate_windings(wire_type,
                                                                                    N_layers,
                                                                                    winding.former_ID + winding.t_former * 2,
                                                                                    winding.h_winding)
        # if Rdc is usable, add to DataFrame
                if winding.target_Rdc / 1.1 < Rdc < winding.target_Rdc * 1.15 and all(i > 0 for i in N_windings):
                    winding_name = (str(N_layers) + "x " + wire_type).strip()
                    winding_data = {}
                    for k in ["wire_type", "N_layers", "Rdc", "N_windings", "l_wire", "w_coil_max", "coil_mass"]:
                        winding_data[k] = locals()[k]
                    coil_choice = (winding_name, winding_data)
                    speaker = SpeakerDriver(coil_choice)
                    self.coil_options_table.loc[winding_name] = [getattr(speaker, i) for i in table_columns]  # add all the parameters of this speaker to a new dataframe row
        self.coil_options_table.sort_values("Lm", ascending=False)

        # Add the coils in dataframe to the combobox (with their userData)
        for winding_name in self.coil_options_table.index:
            # Make a string for the text to show on the combo box
            Rdc_string = "Rdc=%.2f, " % self.coil_options_table.Rdc[winding_name]
            Lm_string = "Lm=%.2f, " % self.coil_options_table.Lm[winding_name]
            Qes_string = "Qts=%.2f" % self.coil_options_table.Qts[winding_name]
            name_in_combo_box = winding_name + ", " + Rdc_string + Lm_string + Qes_string
            userData = self.coil_options_table.to_dict("index")[winding_name]
            self.coil_choice_box["obj"].addItem(name_in_combo_box, userData)
        # if nothing to add to combobox
        if self.coil_choice_box["obj"].count() == 0:
            beep_bad()
            self.coil_choice_box["obj"].addItem("--no solution found--")
        else:
            beep()


@dataclass
class SpeakerDriver():
    """Speaker driver class."""

    coil_choice: tuple  # (winding_name (e.g.4x SV160), user data dictionary that includes variables for that winding)
    global form, cons

    def __post_init__(self):
        """Post-init speaker."""
        self.error = str()
        motor_spec_choice = form.get_value("motor_spec_type")["userData"]
        read_from_form = ["fs", "Qms", "Xmax", "dead_mass", "Sd"]
        for k in read_from_form:
            setattr(self, k, form.get_value(k))

        if motor_spec_choice == "define_coil":
            B_average = form.get_value("B_average")
            former_ID = form.get_value("former_ID")
            t_former = form.get_value("t_former")
            h_winding = form.get_value("h_winding")
            winding_name, winding_data = self.coil_choice
            wire_type = winding_data["wire_type"]
            N_layers = winding_data["N_layers"]
            Rdc = winding_data["Rdc"]
            N_windings = winding_data["N_windings"]
            l_wire = winding_data["l_wire"]
            w_coil_max = winding_data["w_coil_max"]
            coil_mass = winding_data["coil_mass"]
            Bl = B_average * l_wire
            Mmd = self.dead_mass + coil_mass
            attributes = ["Rdc", "Bl", "Mmd", "Mms", "Kms", "Rms", "Ces",
                          "Qts", "Qes", "Lm", "coil_mass", "w_coil_max",
                          "l_wire", "wire_type", "N_layers", "N_windings"]

        elif motor_spec_choice == "define_Bl_Re":
            try:
                Rdc = form.get_value("Rdc")
                Bl = form.get_value("Bl")
                Mmd = form.get_value("Mmd")
                attributes = ["Rdc", "Bl", "Mmd", "Mms", "Kms", "Rms", "Ces",
                              "Qts", "Qes", "Lm"]
            except Exception:
                self.error += "Unable to get Bl, Re and Mmd values from user form"
        else:
            raise Exception("Unknown motor specification type")

        # Calculate more acoustical parameters using Bl, Rdc and Mmd
        Mms = Mmd + calculate_air_mass(self.Sd)
        Kms = Mms * (self.fs * 2 * np.pi)**2
        Rms = (Mms * Kms)**0.5 / self.Qms
        Ces = Bl**2 / Rdc
        Qts = (Mms*Kms)**0.5/(Rms+Ces)
        Qes = (Mms*Kms)**0.5/(Ces)
        zeta_speaker = 1 / 2 / Qts

        fs_damped = self.fs * (1 - 2 * zeta_speaker**2)**0.5
        if np.iscomplex(fs_damped):
            fs_damped = None

        Lm = calculate_Lm(Bl, Rdc, Mms, self.Sd)

        # Add all the calculated parameters as attribute to the object
        for v in attributes:
            setattr(self, v, locals()[v])

        # Make a string for acoustical summary
        self.summary_ace = "Rdc: %.2f ohm    Lm: %.2f dBSPL    Bl: %.4g Tm"\
            % (Rdc, Lm, Bl)
        self.summary_ace += "\r\nQts: %.3g    Qes: %.3g"\
            % (Qts, Qes)

        if fs_damped:
            self.summary_ace += f"    fs: {fs_damped:.3g} Hz (damped)"
        else:
            self.summary_ace += f"    fs: {self.fs:.3g} Hz (overdamped)"

        self.summary_ace += "\r\nKms: %.4g N/mm    Rms: %.3g kg/s    Mms: %.4g g"\
            % (Kms/1000, Rms, Mms*1000)
        if motor_spec_choice == "define_coil":
            self.summary_ace += "\r\nMmd: %.4g g    Windings: %.2f g" % (self.Mmd*1000, self.coil_mass*1000)

        self.summary_ace += \
            "\r\nXmax: %.2f mm    Bl² / Re: %.3g N²/W" % (self.Xmax*1000, Bl**2 / Rdc)

        # Make a string for mechanical summary
        self.Xmech = calculate_Xmech(self.Xmax)
        self.summary_mec = \
            "Xmech ≥ %.2f mm (recommended)" % (self.Xmech*1000)

        if motor_spec_choice == "define_coil":
            # Add mechanical variables from user form as instance variables
            read_from_form = ["airgap_clearance_inner",
                              "airgap_clearance_outer",
                              "t_former",
                              "former_ID",
                              "h_winding",
                              "former_extension_under_coil",
                              "h_washer"]
            for k in read_from_form:
                setattr(self, k, form.get_value(k))

            self.air_gap_width = (self.airgap_clearance_inner + self.t_former
                                  + self.w_coil_max + self.airgap_clearance_outer)

            self.air_gap_dims = [self.former_ID/2 - self.airgap_clearance_inner,
                                 self.air_gap_width,
                                 self.former_ID/2 - self.airgap_clearance_inner
                                 + self.air_gap_width]

            self.overhang = (self.h_winding - self.h_washer) / 2

            self.washer_to_bottom_plate = (self.h_winding / 2
                                           + self.former_extension_under_coil
                                           + calculate_Xmech(self.Xmax)
                                           - self.h_washer / 2)

            self.summary_mec += \
                "\r\nOverhang + 15%%: %.2f mm" % float(self.overhang*1.15*1000)
            self.summary_mec += \
                "\r\nAirgap dims: %s mm" \
                % (str(np.round([i*1000 for i in self.air_gap_dims], 2)))
            self.summary_mec += \
                "\r\nWindings per layer: %s" % (str(self.N_windings))
            self.summary_mec += \
                "\r\nTop plate to bottom plate ≥ %.2f mm (recommended)" \
                % (self.washer_to_bottom_plate*1000)



@dataclass
class SpeakerSystem():
    """
    One or two degree of freedom acoustical system class.

    Can be two types: ["Closed box", "Free-air"]
    """

    spk: SpeakerDriver
    global cons

    def __post_init__(self):
        """Add more attributes."""
        self.error = self.spk.error
        Bl = self.spk.Bl
        Rdc = self.spk.Rdc
        Mms = self.spk.Mms
        Rms = self.spk.Rms
        Kms = self.spk.Kms
        Sd = self.spk.Sd
        excitation = [form.get_value("excitation_value"), form.get_value("excitation_unit")["userData"]]
        nominal_impedance = form.get_value("nominal_impedance")
        self.V_in = calculate_input_voltage(excitation, Rdc, nominal_impedance)
        self.box_type = form.get_value("box_type")
        self.dof = int(form.get_value("dof")[0])

        # Read box parameters
        if self.box_type == "Closed box":
            self.Vb, self.Qa = form.get_value("Vb"), form.get_value("Qa")
        else:
            self.Vb, self.Qa = [np.inf] * 2

        # Read dof
        if self.dof > 1:
            m2, k2, c2 = form.get_value("m2"), form.get_value("k2"), form.get_value("c2")

        self.Kbox = Kbox = Sd**2*cons.Kair/self.Vb

        Rbox = ((Kms + Kbox) * Mms)**0.5 / self.Qa
        zeta_boxed_speaker = (Rbox + Rms + Bl**2/Rdc) / 2 / ((Kms+Kbox) * Mms)**0.5
        self.Qtc = 1 / 2 / zeta_boxed_speaker

        self.fb = 1 / 2 / np.pi * ((Kms+Kbox) / Mms)**0.5
        self.fb_d = self.fb * (1 - 2 * zeta_boxed_speaker**2)**0.5

        if np.iscomplex(self.fb_d):
            self.fb_d = None

        self.Vas = cons.Kair / Kms * Sd**2

        # State space model
        if not hasattr(self, "sysx1"):
            # State, input, output and feed-through matrices and state space system definitions
            if self.dof == 1:
                ass = np.array([
                    [0, 1],
                    [-Kbox/Mms-Kms/Mms, -Bl**2/Rdc/Mms-Rms/Mms-Rbox/Mms]
                    ])
                bss = np.array([[0], [Bl/Rdc/Mms]])
                cssx1 = np.array([1, 0])
                cssx1t = np.array([0, 1])
                dss = np.array([0])
            if self.dof == 2:
                ass = np.array([
                    [0, 1, 0, 0],
                    [-(Kms+Kbox)/Mms, -(Rms+Rbox+Bl**2/Rdc)/Mms, (Kms+Kbox)/Mms, (Rms+Rbox+Bl**2/Rdc)/Mms],
                    [0, 0, 0, 1],
                    [(Kms+Kbox)/m2, (Rms+Rbox+Bl**2/Rdc)/m2, -(Kms+Kbox+k2)/m2, -(Rms+Rbox+Bl**2/Rdc+c2)/m2]
                    ])
                bss = np.array([[0], [Bl/Rdc/Mms], [0], [-Bl/Rdc/m2]])
                cssx1 = np.array([1, 0, 0, 0])
                cssx1t = np.array([0, 1, 0, 0])
                cssx2 = np.array([0, 0, 1, 0])
                cssx2t = np.array([0, 0, 0, 1])
                dss = np.array([0])

            self.sysx1 = signal.StateSpace(ass, bss, cssx1, dss)
            self.sysx1t = signal.StateSpace(ass, bss, cssx1t, dss)
            if self.dof > 1:
                self.sysx2 = signal.StateSpace(ass, bss, cssx2, dss)
                self.sysx2t = signal.StateSpace(ass, bss, cssx2t, dss)

        # Output arrays
        _, self.x1_1V = signal.freqresp(self.sysx1, w=cons.w)  # hata veriyo
        _, self.x1t_1V = signal.freqresp(self.sysx1t, w=cons.w)
        self.x1 = self.x1_1V * self.V_in
        self.x1t = self.x1 * cons.w

        if self.dof > 1:
            _, self.x2_1V = signal.freqresp(self.sysx2, w=cons.w)
            _, self.x2t_1V = signal.freqresp(self.sysx2t, w=cons.w)
            self.x2 = self.x2_1V * self.V_in
            self.x2t = self.x2 * cons.w

        # SPL calculation with simplified radiation impedance * acceleration
        a = np.sqrt(Sd/np.pi)  # piston radius
        p0_1V = 0.5 * 1j * cons.w * cons.RHO * a**2 * self.x1t_1V
        pref = 2e-5
        SPL_1V = 20*np.log10(np.abs(p0_1V)/pref)

        # Xmax limited SPL calculation
        x1_max_rms_array = [np.array(self.spk.Xmax/2**0.5)] * len(cons.f)
        x1t_max_rms_array = np.abs(x1_max_rms_array * cons.w * 1j)
        p0_xmax_limited = 0.5 * 1j * cons.w * cons.RHO * a**2 * x1t_max_rms_array
        self.SPL_Xmax_limited = 20*np.log10(np.abs(p0_xmax_limited)/pref)

        self.SPL = SPL_1V + 20*np.log10(self.V_in)
        self.P_real = self.V_in ** 2 / Rdc
        self.Z = Rdc / (1 - Bl*self.x1t_1V)

        # Calculate some extra parameters
        self.x1tt_1V = self.x1t_1V * cons.w * 1j
        self.x1tt = self.x1tt_1V * self.V_in
        self.force_1 = - self.x1tt * Mms  # inertial force
        self.force_coil = Bl * np.real(self.V_in / self.Z)

        if self.dof > 1:
            self.x2tt_1V = self.x2t_1V * cons.w * 1j
            self.x2tt = self.x2tt_1V * self.V_in
            self.force_2 = - self.x2tt * m2  # inertial force

        if self.box_type == "Closed box" and self.fb_d:
            interested_frequency = self.fb_d * 4
        elif self.box_type == "Closed box":
            interested_frequency = self.fb * 4
        else:
            interested_frequency = self.spk.fs * 4

        f_interest, f_inter_idx = find_nearest_freq(cons.f, interested_frequency)

        self.summary = "SPL at %iHz: %.1f dB" %\
            (f_interest, self.SPL[f_inter_idx])

        # Info over closed box
        if self.box_type == "Closed box":

            self.summary += "\r\n"

            if self.fb_d:  # not overdamped
                self.summary += "\r\nQtc: %.3g    fb: %.3g Hz / %.3g Hz (damped / undamped)" \
                                % (self.Qtc, self.fb_d, self.fb)
            else:  # overdamped
                self.summary += "\r\nQtc: %.3g    fb: %.3g Hz (overdamped)" \
                                % (self.Qtc, self.fb)

            self.summary += "\r\nVas: %.3g l    Kbox: %.4g N/mm" \
                            % (self.Vas * 1e3, self.Kbox/1000)

        # Info over second degree of freedom damping and invalid loudsp
        if self.dof == 2:

            zeta2_free = c2 / 2 / ((Mms + m2) * k2)**0.5
            if c2 > 0:
                q2_free = 1 / 2 / zeta2_free
            else:
                q2_free = np.inf

            f2_undamped = 1 / 2 / np.pi * (k2 / (Mms + m2))**0.5
            f2_damped = f2_undamped * (1 - 2 * zeta2_free**2)**0.5
            if np.iscomplex(f2_damped):
                f2_damped = None

            self.summary += "\r\n"

            self.summary += ("\r\n" + "While M2 is rigidly coupled with Mms;")

            self.summary += ("\r\n" + "ζ2: %.3g    Q2: %.3g" %
                             (zeta2_free, q2_free))

            if f2_damped:  # not overdamped
                self.summary += ("\r\n" + "f2: %.3g Hz / %.3g Hz (damped / undamped)" %
                                 (f2_damped, f2_undamped))
            else:  # overdamped
                self.summary += ("\r\n" + "f2: %.3g Hz (overdamped)" %
                                 (f2_undamped))

        # Info over displacements
        self.summary += "\r\n"

        if self.dof == 1:
            self.summary += "\r\nPeak displacement at %iHz: %.3g mm" %\
                (f_interest, np.abs(self.x1)[f_inter_idx] * 1e3 * 2**0.5)

            self.summary += "\r\nPeak displacement overall: %.3g mm" %\
                np.max(np.abs(self.x1) * 1e3 * 2**0.5)

        elif self.dof == 2:
            self.summary += "\r\nPeak relative displacement at %iHz: %.3g mm" %\
                (f_interest, np.abs(self.x1[f_inter_idx]-self.x2[f_inter_idx])*1e3*2**0.5)

            self.summary += "\r\nPeak relative displacement overall: %.3g mm" %\
                np.max(np.abs(self.x1-self.x2) * 1e3 * 2**0.5)

        else:
            self.summary += "Unable to identify the total degrees of freedom"

        # Suspension feasibility
        self.summary += "\r\nF_motor(V_in) / F_suspension(Xmax/2) = {:.0%}".format(
            Bl * self.V_in / Rdc / Kms / self.spk.Xmax * 2)


def update_model():
    """Update the mathematical model of the speaker."""
    global result_sys, form, cons, error_message
    motor_spec_choice = form.get_value("motor_spec_type")["userData"]
    if motor_spec_choice == "define_coil":
        try:
            winding_name = form.get_value("coil_choice_box")["name"]
            winding_data = form.get_value("coil_choice_box")["userData"]
            coil_choice = winding_name, winding_data
            speaker = SpeakerDriver(coil_choice)
        except Exception as e:
            error_message = f"--Invalid loudspeaker driver-- \r\n {e}"
            update_view()
            beep_bad()
            return
    if motor_spec_choice == "define_Bl_Re":
        try:
            speaker = SpeakerDriver((None, None))
        except Exception as e:
            error_message = f"--Invalid loudspeaker driver-- \r\n {e}"
            update_view()
            beep_bad()
            return
    try:
        result_sys = SpeakerSystem(speaker)
        if hasattr(result_sys, "x1tt"):  # this checks if the result_sys is calculated and ready
            update_available_graph_buttons()
            error_message = result_sys.error
        else:
            error_message = "--Invalid loudspeaker system--"
            beep_bad()
    except Exception as exception_message:
        error_message = "--Update failed with message: %s--" % str(exception_message)
        beep_bad()
    update_view()


if __name__ == "__main__":

    # %% Initiate PyQT Application
    app = qtw.QApplication.instance()
    if app is None:
        app = qtw.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    app.setWindowIcon(qtg.QIcon('.\\SSC_data\\ssc.png'))
    form = UserForm()  # initiate an object to hold all user form items

    # %% Add a Save/Load widget
    crud = qtw.QHBoxLayout()
    crud_load_button = qtw.QPushButton("Load")
    crud_load_button.clicked.connect(partial(form.load_pickle))
    crud_save_button = qtw.QPushButton("Save")
    crud_save_button.clicked.connect(partial(form.save_to_pickle))
    crud.addWidget(crud_load_button)
    crud.addWidget(crud_save_button)

    # %% Start a form widget for the left side of GUI
    form_1_layout = qtw.QFormLayout()
    form_1_layout.setVerticalSpacing(5)

    # %% Add basic speaker parameters to form
    form.add_title(form_1_layout, "General speaker specifications")

    form.add_double_float_var(form_1_layout, "fs", "fs (Hz, undamped)", default=111)
    form.fs["obj"].setDecimals(1)
    form.add_double_float_var(form_1_layout, "Qms", "Qms", default=6.51)
    form.add_double_float_var(form_1_layout, "Xmax", "Xmax (mm)", default=4, unit_to_SI=1e-3)
    form.Xmax["obj"].setToolTip("Peak excursion allowed, one way.")
    form.add_double_float_var(form_1_layout, "dead_mass", "Dead mass (g)", default=3.54, unit_to_SI=1e-3)
    form.dead_mass["obj"].setDecimals(3)
    form.add_double_float_var(form_1_layout, "Sd", "Sd (cm²)", default=53.5, unit_to_SI=1e-4)

    form.add_line(form_1_layout)

    # %% Add motor input choice combobox to form
    combo_box_data = [("Define Coil Dimensions and Average B", "define_coil"),
                      ("Define Bl and Rdc", "define_Bl_Re")
                      ]
    form.add_combo_box(form_1_layout, "motor_spec_type", combo_box_data)
    form.motor_spec_type["obj"].setStyleSheet("font-weight: bold")
    # form.motor_spec_type["obj"].setFixedHeight(20)

    # %% Add widget for "define coil and B_Average"
    motor_form_1 = qtw.QWidget()
    motor_form_1_layout = qtw.QFormLayout()
    motor_form_1_layout.setContentsMargins(0, 0, 0, 0)
    motor_form_1_layout.setVerticalSpacing(form_1_layout.verticalSpacing())
    motor_form_1.setLayout(motor_form_1_layout)
    form.add_double_float_var(motor_form_1_layout, "target_Rdc", "Target Rdc (ohm)", default=3.9)
    form.add_double_float_var(motor_form_1_layout, "former_ID", "Coil Former ID (mm)",
                              default=25,
                              unit_to_SI=1e-3)
    form.add_integer_var(motor_form_1_layout, "t_former", "Former thickness (\u03BCm)",
                         default=100,
                         unit_to_SI=1e-6)
    form.add_double_float_var(motor_form_1_layout, "h_winding", "Coil winding height (mm)",
                              default=6.2,
                              unit_to_SI=1e-3)
    form.add_double_float_var(motor_form_1_layout, "B_average", "Average B field on coil (T)",
                              default=0.69)
    form.B_average["obj"].setDecimals(3)
    form.B_average["obj"].setMinimum(0.001)
    form.add_string_var(motor_form_1_layout, "N_layer_options", "Number of layer options", default="2, 4")
    form.N_layer_options["obj"].setToolTip("Enter the winding layer options as "
                                           "integers with a comma in between\n"
                                           "e.g.: 4, 6")
    button_coil_choices_update = qtw.QPushButton("Update coil choices")
    button_coil_choices_update.setMaximumWidth(160)
    motor_form_1_layout.addRow(button_coil_choices_update)

    form.add_combo_box(motor_form_1_layout, "coil_choice_box", [("--empty--", "")])

    # %% Add widget for "define Bl and Rdc"
    motor_form_2 = qtw.QWidget()
    motor_form_2_layout = qtw.QFormLayout()
    motor_form_2_layout.setVerticalSpacing(form_1_layout.verticalSpacing())
    motor_form_2_layout.setContentsMargins(0, 0, 0, 0)
    motor_form_2.setLayout(motor_form_2_layout)
    form.add_double_float_var(motor_form_2_layout, "Bl", "Bl (Tm)", default=3.43)
    form.Bl["obj"].setMinimum(0.01)
    form.add_double_float_var(motor_form_2_layout, "Rdc", "Rdc (ohm)", default=3.77)
    form.add_double_float_var(motor_form_2_layout, "Mmd", "Mmd (g)", default=3.98, unit_to_SI=1e-3)
    form.Mmd["obj"].setDecimals(3)

    # %% Make a stacked widget to show the right motor input form based
    # on motor input choice combobox
    motor_data_input = qtw.QStackedWidget()
    motor_data_input.setMaximumHeight(250)
    motor_data_input.addWidget(motor_form_1)
    motor_data_input.addWidget(motor_form_2)
    # motor_data_input.setFixedHeight(200)
    QObject.connect(form.motor_spec_type["obj"], SIGNAL(
        "currentIndexChanged(int)"), motor_data_input, SLOT("setCurrentIndex(int)"))
    # input_form_layout.addRow(motor_data_input)

    # %% Start a form widget for left side of GUI
    form_2_layout = qtw.QFormLayout()
    form_2_layout.setVerticalSpacing(form_1_layout.verticalSpacing())  # necessaqry?????????

    # %% Add mechanical info to form
    form.add_line(form_2_layout)
    form.add_title(form_2_layout, "Motor mechanical specifications")

    form.add_double_float_var(form_2_layout, "h_washer", "Top plate thickness (mm)",
                              default=3, unit_to_SI=1e-3)
    form.add_integer_var(form_2_layout, "airgap_clearance_inner", "Airgap inner clearance (\u03BCm)", default=300, unit_to_SI=1e-6)
    form.add_integer_var(form_2_layout, "airgap_clearance_outer", "Airgap outer clearance (\u03BCm)", default=300, unit_to_SI=1e-6)
    form.add_double_float_var(form_2_layout, "former_extension_under_coil", "Former bottom ext. (mm)", default=0.5, unit_to_SI=1e-3)
    form.former_extension_under_coil["obj"].setToolTip("Additional length of former below the windings.")

    # %% Add closed box info to form
    form.add_line(form_2_layout)
    form.add_title(form_2_layout, "Closed box specifications")

    form.add_double_float_var(form_2_layout, "Vb", "Box internal volume (l)", default=1, unit_to_SI=1e-3)
    form.Vb["obj"].setDecimals(3)
    form.add_double_float_var(form_2_layout, "Qa", "Qa - box absorption", default=40)
    form.Qa["obj"].setMinimum(0.01)

    # %% Add second dof parameters to form
    form.add_line(form_2_layout)
    form.add_title(form_2_layout, "Second degree of freedom")

    form.add_double_float_var(form_2_layout, "k2", "Stiffness (N/mm)", default=25, unit_to_SI=1e3)
    form.k2["obj"].setMinimum(0.01)
    form.add_double_float_var(form_2_layout, "m2", "Mass (g)", default=1000, unit_to_SI=1e-3)
    form.m2["obj"].setMinimum(0.01)
    form.add_double_float_var(form_2_layout, "c2", "Damping coefficient (kg/s)", default=5)

    # %% Add excitation parameters to form
    form.add_line(form_2_layout)
    form.add_title(form_2_layout, "Excitation")

    excitation_combo_box_choices = ([("Volts", "V"),
                                     ("W@Rdc", "W"),
                                     ("W@Rnom", "Wn")
                                     ])
    form.add_combo_box(form_2_layout, "excitation_unit", excitation_combo_box_choices, combo_box_screen_name="Unit")
    form.excitation_unit["obj"].setToolTip("Choose input value in\n"
                                           "Volts\n"
                                           "Watts into Rdc (V_in² / Rdc)\n"
                                           "Watts into nominal impedance (V_in² / Rnom)")
    form.set_value("excitation_unit", "V")
    form.add_double_float_var(form_2_layout, "excitation_value", "Excitation value", default=2.83)
    form.excitation_value["obj"].setDecimals(3)

    form.add_double_float_var(form_2_layout, "nominal_impedance", "Nominal impedance", default=4)

    # %% Create layout for system type selection radio buttons (Closed, free-air, 1dof 2dof etc.)
    form.add_line(form_2_layout)
    form.add_title(form_2_layout, "System type")
    sys_type_selection = qtw.QVBoxLayout()
    box_buttons_layout = qtw.QHBoxLayout()
    dof_buttons_layout = qtw.QHBoxLayout()
    sys_type_selection.addLayout(box_buttons_layout)
    sys_type_selection.addLayout(dof_buttons_layout)

    # %% Add box type radio buttons
    setattr(form, "box_type", {"obj": qtw.QButtonGroup()})
    rb_box = [qtw.QWidget] * 5
    rb_box[1] = qtw.QRadioButton("Free-air")
    rb_box[1].setChecked(True)
    box_buttons_layout.addWidget(rb_box[1])

    rb_box[2] = qtw.QRadioButton("Closed box")
    box_buttons_layout.addWidget(rb_box[2])

    form.box_type["obj"].addButton(rb_box[1])
    form.box_type["obj"].addButton(rb_box[2])

    # %% Add DOF choice radio buttons
    setattr(form, "dof", {"obj": qtw.QButtonGroup()})
    rb_dof = [qtw.QWidget] * 5
    rb_dof[1] = qtw.QRadioButton("1 dof")
    rb_dof[1].setChecked(True)
    dof_buttons_layout.addWidget(rb_dof[1])

    rb_dof[2] = qtw.QRadioButton("2 dof")
    dof_buttons_layout.addWidget(rb_dof[2])

    form.dof["obj"].addButton(rb_dof[1])
    form.dof["obj"].addButton(rb_dof[2])

    # %% Create the graph choice buttons
    plot_data_selection = qtw.QWidget()
    layout = qtw.QHBoxLayout()
    plot_data_selection.setLayout(layout)
    plot_data_selection.setFixedHeight(40)
    rb_screen_names = ["SPL",
                       "Impedance",
                       "Displacement",
                       "Relative",
                       "Forces",
                       "Accelerations",
                       "Phase",
                       ]

    rb_graph_group = qtw.QButtonGroup()
    for id, screen_name in enumerate(rb_screen_names):
        button = qtw.QRadioButton(screen_name)
        rb_graph_group.addButton(button, id)
        layout.addWidget(button)
        if screen_name == "SPL":
            button.setChecked(True)

    # %% Message_box to show calculated values
    message_box = qtw.QPlainTextEdit()
    message_box.setFixedHeight(366)
    message_box.setFixedWidth(360)
    message_box.setReadOnly(True)

    # %% User notes box to take notes etc.
    setattr(form, "user_notes", {"obj": qtw.QPlainTextEdit()})
    form.user_notes["obj"].setPlainText("Notes here")

    # %% Plotting with Matplotlib
    def graph_ceil(x, step=5):
        """Define axis highest value based on curve highest value."""
        return step * np.ceil(x/step)

    def update_view():
        """Update the graphs and the calculated values in message box."""
        global result_sys, error_message, user_curve
        ax = figure.gca()
        ax.clear()
        if error_message == "":
            message_box.setPlainText(result_sys.spk.summary_ace
                                     + "\n\r" + result_sys.spk.summary_mec
                                     + "\n\r" + result_sys.summary)
            chosen_graph = rb_graph_group.checkedId()
            if chosen_graph == 0:
                curve = result_sys.SPL
                curve_2 = result_sys.SPL_Xmax_limited
                upper_limit = graph_ceil(np.max(curve) + 5, 10)
                lower_limit = upper_limit - 50
                ax.semilogx(cons.f, curve)
                ax.semilogx(cons.f, curve_2, "m", label="Xmax limited")
                ax.legend()
                ax.set_title("SPL@1m, Half-space, %.2f Volt, %.2f Watt@Rdc"
                             % (result_sys.V_in, result_sys.P_real))
                ax.set_xbound(lower=10, upper=3000)
                ax.set_ybound(lower=lower_limit, upper=upper_limit)

            if chosen_graph == 1:
                curve = np.real(result_sys.Z)
                ax.semilogx(cons.f, curve)
                ax.set_title("Electrical Impedance (no inductance)")
                ax.set_xbound(lower=10, upper=3000)
                ax.set_ybound(lower=0, upper=(graph_ceil(np.max(curve) + 2, 10)))

            if chosen_graph == 2:
                curve = np.abs(result_sys.x1) * 1000
                ax.semilogx(cons.f, curve, label="dof 1, RMS")
                ax.semilogx(cons.f, curve * 2**0.5, "m", label="dof 1, Peak")
                # ax.set_ybound(lower=0, upper=(graph_ceil(np.max(curve) * 1.5, 1)))

                if result_sys.dof > 1:
                    curve = np.abs(result_sys.x2) * 1000
                    ax.semilogx(cons.f, curve, label="dof 2, RMS")
                    ax.semilogx(cons.f, curve * 2**0.5, label="dof 2, Peak")

                ax.set_title("Absolute Displacement, mm, One-way")
                ax.set_xbound(lower=10, upper=3000)
                ax.legend()

            if chosen_graph == 3:
                curve = np.abs(result_sys.x1 - result_sys.x2) * 1000
                ax.semilogx(cons.f, curve, label="RMS")
                ax.semilogx(cons.f, curve * 2**0.5, "m", label="Peak")
                ax.set_title("Relative Displacement, mm, One-way")
                ax.set_xbound(lower=10, upper=3000)
                ax.legend()
                # ax.set_ybound(lower=0, upper=(graph_ceil(np.max(curve) * 1.5, 1)))

            if chosen_graph == 4:  # Forces
                curve_1 = np.abs(result_sys.force_coil)
                ax.semilogx(cons.f, curve_1, label="Lorentz force")
                curve_2 = - np.abs(result_sys.force_1)
                ax.semilogx(cons.f, curve_2, label="Inertial force from first mass")
                if result_sys.dof == 1:
                    curve_3 = np.abs(result_sys.force_1)
                    ax.semilogx(cons.f, curve_3, label="Reaction force from reference frame")
                if result_sys.dof > 1:
                    curve_4 = np.abs(result_sys.force_2)
                    curve_6 = np.abs(result_sys.force_2+result_sys.force_1)
                    ax.semilogx(cons.f, curve_4, label="Inertial force from second mass")
                    ax.semilogx(cons.f, curve_6, label="Reaction force from reference frame")
                ax.legend()
                ax.set_title("Forces, N, RMS")
                ax.set_xbound(lower=10, upper=3000)

            if chosen_graph == 5:
                curve = np.abs(result_sys.x1tt)
                ax.semilogx(cons.f, curve, label="dof 1, RMS")
                ax.semilogx(cons.f, curve * 2**0.5, "m", label="dof 1, Peak")
                # ax.set_ybound(lower=0, upper=(graph_ceil(np.max(curve) * 1.5, 1)))

                if result_sys.dof > 1:
                    curve = np.abs(result_sys.x2tt)
                    ax.semilogx(cons.f, curve, label="dof 2, RMS")
                    ax.semilogx(cons.f, curve * 2**0.5, label="dof 2, Peak")

                ax.set_title("Acceleration, m/s²")
                ax.set_xbound(lower=10, upper=3000)
                ax.legend()

            if chosen_graph == 6:
                curve = np.angle(result_sys.x1, deg=True)
                ax.semilogx(cons.f, curve, label="dof 1")
                if result_sys.dof > 1:
                    curve_2 = np.angle(result_sys.x2, deg=True)
                    ax.semilogx(cons.f, curve_2, label="dof 2")
                ax.legend()
                ax.set_yticks(range(-180, 180+1, 90))
                ax.set_title("Absolute phase, °")
                ax.set_xbound(lower=10, upper=3000)
                ax.set_ybound(lower=-180, upper=180)

            if len(form.user_curves) * (chosen_graph == 0):  # works only with SPL graph
                ax.autoscale(enable=False)
                for idx, curve in enumerate(form.user_curves):
                    ax.semilogx(*curve, ":r", label="User import %i" % (idx + 1))
                ax.legend()

            ax.grid(True, which="both")
            button24.setEnabled(chosen_graph == 0)
            button25.setEnabled(chosen_graph == 0)
            canvas.draw()  # refresh canvas

            beep()  # plot successful

        else:
            message_box.setPlainText(error_message)

    # %% Functions for buttons under the graph
    def import_user_curve():
        global cons, form
        err, clpd = read_clipboard()
        if err != 0:
            print("Unable to read clipboard")
            beep_bad()
            return
        else:
            data_type, title, curve_data = analyze_clipboard_data(err, clpd)
            print(data_type)
            if isinstance(curve_data, pd.DataFrame) and len(curve_data.columns == 2):
                # not using the title yet. to be implemented
                print(curve_data.iloc[:,0])
                form.user_curves.append([curve_data[0].to_numpy(), curve_data[1].to_numpy()])
                update_view()
                return
            beep_bad()

    def clear_user_curve():
        try:
            global form
            form.user_curves.pop()
            update_view()
        except IndexError:
            beep_bad()

    def export_results_to_clipboard():
        global result_sys, cons
        update_model()
        pdall = pd.DataFrame(dtype=np.float32, index=cons.f)
        pdall.index.name = "frequency, Hz"
        pdall["dBSPL, Half-space"] = result_sys.SPL
        pdall["dBSPL, Half-space, Xmax limited"] = result_sys.SPL_Xmax_limited
        pdall["x1, Displacement, RMS, mm"] = np.abs(result_sys.x1)*1000
        pdall["x1, Displacement, peak, mm"] = np.abs(result_sys.x1)*1000*2**0.5
        pdall["x1t, Velocity, RMS, m/s"] = np.abs(result_sys.x1t)
        pdall["x1tt, Acceleration, RMS, m/s²"] = np.abs(result_sys.x1t)
        pdall["Electrical Impedance, real part, no inductance"] = np.real(result_sys.Z)
        pdall["Inertial force from first mass, N, RMS"] = np.abs(result_sys.force_1)

        if result_sys.dof == 2:
            pdall["x2, Displacement, RMS, mm"] = np.abs(result_sys.x2)*1000
            pdall["x2, Displacement, peak, mm"] = np.abs(result_sys.x2)*1000*2**0.5
            pdall["x2t, Velocity, RMS, m/s"] = np.abs(result_sys.x2t)
            pdall["x2tt, Acceleration, RMS, m/s²"] = np.abs(result_sys.x2t)
            pdall["Inertial force from second mass, N, RMS"] = np.abs(result_sys.force_2)
            pdall["Force exerted from second mass on to reference frame, N, RMS"] = -np.abs(result_sys.force_2 + result_sys.force_1)

        pdall.to_clipboard()

    def export_diagnose_data():
        global result_sys
        try:
            table_spk = dict()
            for key in vars(result_sys.spk).keys():
                table_spk["spk.%s" % key] = str(getattr(result_sys.spk, key))

            table_result_sys = dict()
            for key in vars(result_sys).keys():
                if key != "spk":
                    table_result_sys["result_sys.%s" % key] = str(getattr(result_sys, key))

            df_to_export = pd.DataFrame.from_dict(table_spk, orient="index")
            df_to_export = df_to_export.append(pd.DataFrame.from_dict(table_result_sys, orient="index"))
            for idx, curve in enumerate(form.user_curves):
                df_to_export.loc["User import %i" % (idx + 1)] = str(form.user_curves[idx])
            df_to_export.to_clipboard()
            beep()
        except Exception:
            beep_bad()

    # %% Buttons under the graph
    button21 = qtw.QPushButton('Update results')
    button21.clicked.connect(update_model)
    button21.setFixedHeight(42)

    button22 = qtw.QPushButton("Export graph\nvalues")
    button22.setToolTip("Export graph values to clipboard as a table")
    button22.clicked.connect(export_results_to_clipboard)
    button22.setFixedHeight(42)

    button23 = qtw.QPushButton("Export diagnose\ndata")
    button23.setToolTip("Export all calculation data to clipboard for diagnosis purposes")
    button23.clicked.connect(export_diagnose_data)
    button23.setFixedHeight(42)

    button24 = qtw.QPushButton("Import curve")
    button24.setToolTip("Import a table from clipboard and add it to the graph")
    button24.clicked.connect(import_user_curve)
    button24.setFixedHeight(42)

    button25 = qtw.QPushButton("Remove\nimported curve")
    button25.clicked.connect(clear_user_curve)
    button25.setFixedHeight(42)

# %% Create the canvas and the navigation toolbar
    graphs = qtw.QWidget()
    # a figure instance to plot on
    figure = Figure(figsize=(5, 7), dpi=72, tight_layout=True)

    # this is the Canvas Widget that displays `figure`
    canvas = FigureCanvas(figure)

    # this is the Navigation widget. arguments are Canvas widget and a parent
    toolbar = NavigationToolbar(canvas, parent=graphs)  # this crashes in Spyder........
    toolbar.setMinimumWidth(400)


# %% Do the main layout

    # Make a QGroupbox frame around all the around the user form
    input_group_box = qtw.QGroupBox("Inputs")
    input_group_box.setFixedWidth(280)

    input_group_box_layout = qtw.QVBoxLayout()
    input_group_box.setLayout(input_group_box_layout)

    input_group_box_layout.addLayout(crud)
    input_group_box_layout.addLayout(form_1_layout)
    input_group_box_layout.addWidget(motor_data_input)
    input_group_box_layout.addLayout(form_2_layout)
    input_group_box_layout.addLayout(sys_type_selection)
    input_group_box_layout.addStretch()

    # Lay things into the main layout
    main_layout = qtw.QHBoxLayout()
    left_layout = qtw.QVBoxLayout()
    right_layout = qtw.QVBoxLayout()

    main_win = qtw.QWidget()
    main_win.setLayout(main_layout)
    main_layout.addLayout(left_layout)
    main_layout.addLayout(right_layout)
    main_win.setWindowTitle("Speaker stuff calculator {}".format(version))

    left_layout.addWidget(input_group_box)
    left_layout.addSpacerItem(qtw.QSpacerItem(0, 0, hPolicy=qtw.QSizePolicy.Minimum, vPolicy=qtw.QSizePolicy.Ignored))

    right_layout.addWidget(toolbar)
    right_layout.addWidget(canvas)
    right_layout.addWidget(plot_data_selection)

    graph_buttons = qtw.QHBoxLayout()
    graph_buttons.addWidget(button21)
    graph_buttons.addWidget(button22)
    graph_buttons.addWidget(button23)
    graph_buttons.addWidget(button24)
    graph_buttons.addWidget(button25)

    right_layout.addLayout(graph_buttons)
    text_boxes = qtw.QHBoxLayout()
    text_boxes.addWidget(message_box)
    text_boxes.addWidget(form.user_notes["obj"])
    form.user_notes["obj"].setFixedHeight(message_box.height())
    right_layout.addLayout(text_boxes)

    # %% Assign functions to changing calculation type
    def adjust_form_for_calc_type():
        form.h_washer["obj"].setEnabled(form.get_value("motor_spec_type")["userData"] == "define_coil")
        form.airgap_clearance_inner["obj"].setEnabled(form.get_value("motor_spec_type")["userData"] == "define_coil")
        form.airgap_clearance_outer["obj"].setEnabled(form.get_value("motor_spec_type")["userData"] == "define_coil")
        form.former_extension_under_coil["obj"].setEnabled(form.get_value("motor_spec_type")["userData"] == "define_coil")
        form.dead_mass["obj"].setEnabled(form.get_value("motor_spec_type")["userData"] == "define_coil")
    button_coil_choices_update.clicked.connect(partial(form.update_coil_choice_box))

    # %% Assign functions to changing graph type
    rb_graph_group.buttonClicked.connect(update_view)

    # %% Assign functions to changing excitation type
    def update_nominal_impedance_disability():
        form.nominal_impedance["obj"].setEnabled(form.get_value("excitation_unit")["userData"] == "Wn")
    form.excitation_unit["obj"].currentIndexChanged.connect(update_nominal_impedance_disability)

    # %% Assign functions to changing system type
    def adjust_form_for_system_type():
        """Update which buttons are enabled based on box type and dof."""
        form.Vb["obj"].setEnabled(rb_box[2].isChecked())
        form.Qa["obj"].setEnabled(rb_box[2].isChecked())
        form.k2["obj"].setEnabled(rb_dof[2].isChecked())
        form.m2["obj"].setEnabled(rb_dof[2].isChecked())
        form.c2["obj"].setEnabled(rb_dof[2].isChecked())

    form.box_type["obj"].buttonToggled.connect(adjust_form_for_system_type)
    form.dof["obj"].buttonToggled.connect(adjust_form_for_system_type)
    form.motor_spec_type["obj"].currentIndexChanged.connect(adjust_form_for_calc_type)

    def update_available_graph_buttons():
        """Update the rb enabled statuses for graph."""
        try:
            dof2_calculated = hasattr(result_sys, "x2")
        except NameError:
            dof2_calculated = False
        rb_graph_group.button(3).setEnabled(dof2_calculated)  # x1-x2 button

    # %% Initiate application
    adjust_form_for_calc_type()
    adjust_form_for_system_type()
    update_nominal_impedance_disability()

    if len(app.arguments()) > 1 and isinstance(app.arguments()[1], str):
        file_name = app.arguments()[1]
        try:
            file = Path(file_name)
            print(f"Requested to open file: {file}")
            form.load_pickle(file)
        except Exception as e:
            message_box.setPlainText(f"Error loading file {file}.\nReason: {str(e)}")
    elif (file := Path.cwd().joinpath("default.sscf")).exists():
        # Load "default.sscf" on startup if found in folder
        print("I found a default file.")
        form.load_pickle(file)

    main_win.show()
    sys.exit(app.exec_())
