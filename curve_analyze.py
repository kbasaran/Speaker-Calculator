import sys
import numpy as np
import pandas as pd
from difflib import SequenceMatcher

# from matplotlib.backends.qt_compat import QtWidgets as qtw
from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc

from graphing import MatplotlibWidget
from signal_tools import Curve, interpolate_to_ppo, median_of_curves
import personalized_widgets as pwi
import pyperclip  # requires also xclip on Linux
from functools import partial

import logging
logging.basicConfig(level=logging.INFO)

# https://matplotlib.org/stable/gallery/user_interfaces/embedding_in_qt_sgskip.html

def find_longest_match_in_name(names):
    """
    https://stackoverflow.com/questions/58585052/find-most-common-substring-in-a-list-of-strings
    https://www.adamsmith.haus/python/docs/difflib.SequenceMatcher.get_matching_blocks

    Parameters
    ----------
    names : list
        A list of names, each one a string.

    Returns
    -------
    max_occurring_substring : str
        The piece of string that accurs most commonly in the beginning of names.

    """
    substring_counts={}

    for i in range(0, len(names)):
        for j in range(i+1,len(names)):
            string1 = names[i]
            string2 = names[j]
            match = SequenceMatcher(None, string1, string2).find_longest_match(0, len(string1), 0, len(string2))
            matching_substring=string1[match.a:match.a+match.size]
            if(matching_substring not in substring_counts):
                substring_counts[matching_substring]=1
            else:
                substring_counts[matching_substring]+=1
    
    max_occurring_key = max(substring_counts, key=substring_counts.get)  # max looks at the output of get method

    return max_occurring_key


class CurveAnalyze(qtw.QWidget):

    signal_good_beep = qtc.Signal()

    def __init__(self, settings=None):
        super().__init__()
        self._global_settings = settings
        self._create_core_objects()
        self._create_widgets()
        self._place_widgets()
        self._make_connections()

    def _create_core_objects(self):
        self._user_input_widgets = dict()

    def _create_widgets(self):
        self._graph = MatplotlibWidget()
        self._graph_buttons = pwi.PushButtonGroup(
            {"import": "Import",
             "auto_import": "Auto Import",
             "reset_indices": "Reset Indexes",
             "remove": "Remove",
             "duplicate": "Duplicate",
             "process": "Process",
             "calculate": "Calculate",
             "export": "Export",
             "settings": "Settings",
             },
            {"import": "Import 2D graph data from clipboard"},
        )
        self._graph_buttons.user_values_storage(self._user_input_widgets)
        self._user_input_widgets["auto_import_pushbutton"].setCheckable(True)
        self._user_input_widgets["auto_import_pushbutton"].setEnabled(False)
        self._user_input_widgets["duplicate_pushbutton"].setEnabled(False)
        # self._user_input_widgets["settings_pushbutton"].setEnabled(False)

        self._curve_list = qtw.QListWidget()
        self._curve_list.setSelectionMode(qtw.QAbstractItemView.ExtendedSelection)

    def _place_widgets(self):
        self.setLayout(qtw.QVBoxLayout())
        self.layout().addWidget(self._graph, 2)
        self.layout().addWidget(self._graph_buttons)
        self.layout().addWidget(self._curve_list)

    def _make_connections(self):
        self._user_input_widgets["remove_pushbutton"].clicked.connect(self.remove_curves)
        self._user_input_widgets["reset_indices_pushbutton"].clicked.connect(self._reset_indices)
        self._user_input_widgets["process_pushbutton"].clicked.connect(partial(self._process_curve, interpolate_to_ppo, ppo=48))
        self._user_input_widgets["export_pushbutton"].clicked.connect(self._export_to_clipboard)
        self._user_input_widgets["settings_pushbutton"].clicked.connect(self._open_settings)
        self._user_input_widgets["calculate_pushbutton"].clicked.connect(partial(self._calculate_curve, median_of_curves))
        self._user_input_widgets["import_pushbutton"].clicked.connect(
            partial(self._import_curve, self._read_clipboard)
        )

    def _export_to_clipboard(self):
        if len(self._curve_list.selectedItems()) > 1:
            raise NotImplementedError("Can export only one curve at a time")
        else:
            list_item = self._curve_list.selectedItems()[0]
            curve = list_item.data(qtc.Qt.ItemDataRole.UserRole)["curve"]
            xy = np.transpose(curve.get_xy())
            pd.DataFrame(xy, columns=["frequency", "value"]).to_clipboard(excel=True, index=False)

    def _read_clipboard(self):
        data = pyperclip.paste()
        new_curve = Curve(data)
        if new_curve.is_curve():
            return new_curve
        else:
            logging.debug("Unrecognized curve object")

    def _reset_indices(self):
        labels = []
        for i in range(self._curve_list.count()):
            list_item = self._curve_list.item(i)
            name = list_item.data(qtc.Qt.ItemDataRole.UserRole)["name"]
            name_with_number = f"#{i:02d} - {name}"
            labels.append(name_with_number)
            list_item.setText(name_with_number)
        self._graph.update_labels(labels)

    def _add_curve(self, curve):
        i = self._curve_list.count()
        name_with_number = f"#{i:02d} - {curve.get_name()}"
        list_item = qtw.QListWidgetItem(name_with_number)
        list_item.setData(qtc.Qt.ItemDataRole.UserRole, {"name": curve.get_name(),
                                                         "curve": curve,
                                                         "processed": False,
                                                         }
                          )
        self._curve_list.addItem(list_item)
        self._graph.add_line2D(i, name_with_number, curve.get_xy())

    def _calculate_curve(self, generate_fun, **kwargs):
        curves_xy = []
        curves_name = []
        for list_item in self._curve_list.selectedItems():
            list_item_user_data = list_item.data(qtc.Qt.ItemDataRole.UserRole)
            curves_name.append(list_item_user_data["name"])
            curves_xy.append(list_item_user_data["curve"].get_xy())

        calculated_curve_name = find_longest_match_in_name(curves_name) + " - " + generate_fun.__name__

        calculated_curve = generate_fun(curves_xy)
        calculated_curve.set_name(calculated_curve_name)

        self._add_curve(calculated_curve)
        self._graph.update_canvas()


    def _open_settings(self):
        settings_dialog = SettingsDialog()
        return_value = settings_dialog.exec()
        print(return_value)

    def _process_curve(self, process_fun, **kwargs):
        for list_item in self._curve_list.selectedItems():
            i = self._curve_list.row(list_item)
            name_with_number_after_processing = list_item.text() + " - processed"  # change this to applied function name
            list_item_user_data = list_item.data(qtc.Qt.ItemDataRole.UserRole)
            
            list_item_user_data["curve_processed"] = True
            curve = list_item_user_data["curve"]
            
            curve.set_xy(process_fun(*curve.get_xy(), **kwargs))
            self._graph.update_line2D(i,
                                      name_with_number_after_processing,
                                      curve.get_xy(ndarray=True),
                                      update_canvas=False,
                                      )
            list_item.setText(name_with_number_after_processing)
        self._graph.update_canvas()

    def _import_curve(self, import_fun):
        new_curve = import_fun()
        if new_curve:
            self._add_curve(new_curve)
        else:
            # beep bad
            pass

    def remove_curves(self):
        for list_item in self._curve_list.selectedItems():
            i = self._curve_list.row(list_item)
            self._curve_list.takeItem(i)
            self._graph.remove_line2D(i, update_canvas=False)
        self._graph.update_canvas()


class SettingsDialog(qtw.QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowModality(qtc.Qt.WindowModality.WindowModal)
        
        user_data_widgets = {}
        layout = qtw.QVBoxLayout(self)
        
        # Form
        user_form = qtw.QFormLayout(self)
        layout.addLayout(user_form)

        user_form.addRow("Interpolate during import (ppo)",
                         pwi.IntSpinBox("ppo_import",
                                        "Interpolate the curve to here defined points per octave in import"
                                        "\nThis is used to simplify curves with too many points, such as Klippel graph imports."
                                        "\nSet to '0' to do no modification to curve.",
                                        user_data_widgets=user_data_widgets,
                                        ),
                         )

        user_form.addRow("Interpolate before export (ppo)",
                         pwi.IntSpinBox("ppo_export",
                                        "Interpolate the curve to here defined points per octave while exporting"
                                        "\nThis is used to simplify curves with too many points, such as Klippel graph imports."
                                        "\nSet to '0' to do no modifications to curve.",
                                        user_data_widgets=user_data_widgets,
                                        ),
                         )
        user_data_widgets["ppo_export"].setValue(96)

        # Buttons
        button_group = pwi.PushButtonGroup({"save": "Save",
                                            "cancel": "Cancel",
                                            },
                                           {},
                                           )
        button_group.buttons()["save_pushbutton"].setDefault(True)
        
        layout.addWidget(button_group)
        

class AutoImporter(qtc.QThread):
    def __init__(self):
        super().__init__()
    
    def run(self):
        while True:
            self.sleep(1)
            print("hop")

if __name__ == "__main__":

    if not (app := qtw.QApplication.instance()):
        app = qtw.QApplication(sys.argv)
        # there is a new recommendation with qApp but how to dod the sys.argv with that?

    mw = CurveAnalyze()

    mw.show()
    app.exec()
