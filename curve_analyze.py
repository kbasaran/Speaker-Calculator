import sys
import numpy as np
import pandas as pd
from difflib import SequenceMatcher

# from matplotlib.backends.qt_compat import QtWidgets as qtw
from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc
from PySide6 import QtGui as qtg

from graphing import MatplotlibWidget
from signal_tools import Curve, interpolate_to_ppo, median_of_curves
import personalized_widgets as pwi
import pyperclip  # must install xclip on Linux together with this!!
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
    signal_bad_beep = qtc.Signal()

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
             "process": "Process",
             "rename": "Rename",
             "hide": "Hide",
             "show": "Show",
             "calculate": "Calculate",
             "export": "Export",
             "settings": "Settings",
             },
            {"import": "Import 2D graph data from clipboard"},
        )
        self._graph_buttons.user_values_storage(self._user_input_widgets)
        self._user_input_widgets["auto_import_pushbutton"].setCheckable(True)
        # self._user_input_widgets["auto_import_pushbutton"].setEnabled(False)
        self._user_input_widgets["process_pushbutton"].setEnabled(False)

        self._curve_list = qtw.QListWidget()
        self._curve_list.setSelectionMode(qtw.QAbstractItemView.ExtendedSelection)
        self._curve_list.setDragDropMode(qtw.QAbstractItemView.InternalMove)

    def _place_widgets(self):
        self.setLayout(qtw.QVBoxLayout())
        self.layout().addWidget(self._graph, 2)
        self.layout().addWidget(self._graph_buttons)
        self.layout().addWidget(self._curve_list)

    def _make_connections(self):
        self._user_input_widgets["remove_pushbutton"].clicked.connect(self.remove_curves)
        self._user_input_widgets["reset_indices_pushbutton"].clicked.connect(self._reset_indices)
        self._user_input_widgets["rename_pushbutton"].clicked.connect(self._rename_curve)
        self._user_input_widgets["process_pushbutton"].clicked.connect(self.hide_curves)
        self._user_input_widgets["hide_pushbutton"].clicked.connect(self.hide_curves)
        self._user_input_widgets["show_pushbutton"].clicked.connect(self.show_curves)
        self._user_input_widgets["export_pushbutton"].clicked.connect(self._export_to_clipboard)
        self._user_input_widgets["auto_import_pushbutton"].toggled.connect(self._auto_importer_status_toggle)
        self._user_input_widgets["settings_pushbutton"].clicked.connect(self._open_settings)
        self._user_input_widgets["calculate_pushbutton"].clicked.connect(partial(self._calculate_curve, median_of_curves))
        self._user_input_widgets["import_pushbutton"].clicked.connect(
            lambda: self._import_curve(self._read_clipboard())
        )

    def _export_to_clipboard(self):
        if len(self._curve_list.selectedItems()) > 1:
            raise NotImplementedError("Can export only one curve at a time")
        else:
            list_item = self._curve_list.selectedItems()[0]
            curve = list_item.data(qtc.Qt.ItemDataRole.UserRole)["curve"]
            
        if self._global_settings.export_ppo == 0:
            xy = np.transpose(curve.get_xy(ndarray=True))
            pd.DataFrame(xy, columns=["frequency", "value"]).to_clipboard(excel=True, index=False)
        else:
            x_intp, y_intp = interpolate_to_ppo(*curve.get_xy(), self._global_settings.export_ppo)
            xy_intp = np.column_stack((x_intp, y_intp))
            pd.DataFrame(xy_intp).to_clipboard(excel=True, index=False, header=False)

    def _read_clipboard(self):
        data = pyperclip.paste()
        new_curve = Curve(data)
        if new_curve.is_curve():
            return new_curve
        else:
            logging.debug("Unrecognized curve object")

    def get_selected_curves(self, value, **kwargs):
        ix = []
        for list_item in self._curve_list.selectedItems():
            ix.append(self._curve_list.row(list_item))  # wow this will be slow..
        return self.get_curves(value, rows=ix, **kwargs)

    def _move_up(self):
        currentRow = self._curve_list.listWidget.currentRow()
        currentItem = self._curve_list.listWidget.takeItem(currentRow)
        self._curve_list.listWidget.insertItem(currentRow - 1, currentItem)
        # And for the Down Button it's the same, except that in the third line the "-" sign is changed by a "+".
        # https://stackoverflow.com/questions/10957392/moving-items-up-and-down-in-a-qlistwidget

    def get_curves(self, value:str, rows:list=None, as_dict=False):
        q_list_items = {}
        for i in range(self._curve_list.count()):
            if not rows or (i in rows):
                q_list_items[i] = self._curve_list.item(i)

        match value:
            case "q_list_items":
                result_dict = q_list_items
            case "ix":
                result_dict = list(q_list_items.keys())
            case "screen_name":  # name with number as shown on screen
                result_dict = {i: list_item.text() for (i, list_item) in q_list_items.items()}
            case "curves":  # Curve instances
                result_dict = {i: list_item.data(qtc.Qt.ItemDataRole.UserRole)["curve"] for (i, list_item) in q_list_items.items()}
            case "curve_names":  # this is the name stored inside curve object. does not include screen number
                result_dict = {i: list_item.data(qtc.Qt.ItemDataRole.UserRole)["curve"].get_name() for (i, list_item) in q_list_items.items()}
            case "xy_s":  # this is the name stored inside curve object. does not include screen number
                result_dict = {i: list_item.data(qtc.Qt.ItemDataRole.UserRole)["curve"].get_xy(ndarray=False) for (i, list_item) in q_list_items.items()}
            case "user_data":
                result_dict = {i: list_item.data(qtc.Qt.ItemDataRole.UserRole) for (i, list_item) in q_list_items.items()}
            case "visibility":
                result_dict = {i: list_item.data(qtc.Qt.ItemDataRole.UserRole)["visible"] for (i, list_item) in q_list_items.items()}
            case _:
                raise KeyError("Unrecognized type for value arg")

        if as_dict:
            return result_dict
        else:
            return list(result_dict.values())

    def _reset_indices(self):
        labels = {}
        curve_names = self.get_curves("curve_names", as_dict=True)
        for i, list_item in self.get_curves("q_list_items", as_dict=True).items():
            screen_name = f"#{i:02d} - {curve_names[i]}"
            list_item.setText(screen_name)
            labels[i] = screen_name
        self._graph.update_labels(labels)

    def _rename_curve(self):
        if len(self._curve_list.selectedItems()) > 1:
            raise NotImplementedError("Can rename only one curve at a time")
        else:
            list_item = self._curve_list.selectedItems()[0]
            i = self._curve_list.row(list_item)
            curve = list_item.data(qtc.Qt.ItemDataRole.UserRole)["curve"]
        
        text, ok = qtw.QInputDialog.getText(self,
                                            "Change curve name",
                                            "New name:", qtw.QLineEdit.Normal,
                                            curve.get_name(),
                                            )
        if ok and text != '':
            curve.set_name(text)
            list_item.setText(text)
            self._graph.update_labels({i: text})
                      
    def _add_curve(self, curve):
        if curve.is_curve():
            i = self._curve_list.count()
            screen_name = f"#{i:02d} - {curve.get_name()}"
            list_item = qtw.QListWidgetItem(screen_name)
            list_item.setData(qtc.Qt.ItemDataRole.UserRole, {"curve": curve,
                                                             "processed": False,
                                                             "visible": True,
                                                             }
                              )
            self._curve_list.addItem(list_item)
            self._graph.add_line2D(i, screen_name, curve.get_xy())
        else:
            raise ValueError("Invalid curve")

    def hide_curves(self, rows=None):
        if rows:
            items = self.get_curves("q_list_items", rows=rows)
        else:
            items = self.get_selected_curves("q_list_items")

        for item in items:
            font = item.font()
            font.setWeight(qtg.QFont.Thin)
            item.setFont(font)

            data = item.data(qtc.Qt.ItemDataRole.UserRole)
            data["visible"] = False
            item.setData(qtc.Qt.ItemDataRole.UserRole, data)

        self.send_visibility_states_to_graph()

    def show_curves(self, rows=None):
        if rows:
            items = self.get_curves("q_list_items", rows=rows)
        else:
            items = self.get_selected_curves("q_list_items")

        for item in items:
            font = item.font()
            font.setWeight(qtg.QFont.Normal)
            item.setFont(font)

            data = item.data(qtc.Qt.ItemDataRole.UserRole)
            data["visible"] = True
            item.setData(qtc.Qt.ItemDataRole.UserRole, data)

        self.send_visibility_states_to_graph()

    def send_visibility_states_to_graph(self):
        visibility_states = self.get_curves("visibility", as_dict=True)
        self._graph.hide_show_line2D(visibility_states)

    def _calculate_curve(self, generate_fun, **kwargs):
        calculated_curve = generate_fun(self.get_selected_curves("xy_s"))
        calculated_curve_name = (find_longest_match_in_name(self.get_selected_curves("curve_names")).strip().strip("-").strip()
                                 + " - "
                                 + generate_fun.__name__
                                 )
        calculated_curve.set_name(calculated_curve_name)

        self._add_curve(calculated_curve)
        self._graph.update_canvas()

    def _auto_importer_status_toggle(self, checked):
        if checked == 1:
            self.auto_importer = AutoImporter()
            self.auto_importer.new_import.connect(self._import_curve)
            self.auto_importer.start()
        else:
            self.auto_importer.requestInterruption()

    def _open_settings(self):
        settings_dialog = SettingsDialog(self._global_settings)
        return_value = settings_dialog.exec()
        if return_value:
            # beep_good
            pass
            
    def _process_curve(self, process_fun, **kwargs):
        user_data = self.get_selected_curves("user_data")
        for i, list_item in self.get_selected_curves("q_list_item").items():
            curve = user_data[i]["curve"]
            screen_name_after_processing = list_item.text() + " - processed"  # change this to applied function name

            data = user_data[i]
            data["curve_processed"] = True
            list_item.setData(qtc.Qt.ItemDataRole.UserRole, data)
            
            curve.set_xy(process_fun(*curve.get_xy(), **kwargs))
            self._graph.update_line2D(i,
                                      screen_name_after_processing,
                                      curve.get_xy(ndarray=True),
                                      update_canvas=False,
                                      )
            list_item.setText(screen_name_after_processing)
        self._graph.update_canvas()

    @qtc.Slot(Curve)
    def _import_curve(self, curve):

        try:
            if settings.import_ppo > 0:
                x, y = curve.get_xy()
                x_intp, y_intp = interpolate_to_ppo(x, y, settings.import_ppo)
                curve.set_xy((x_intp, y_intp))
    
            if curve.is_curve():
                self._add_curve(curve)
                self.signal_good_beep.emit()

        except Exception as e:
            self.signal_bad_beep.emit()
            raise e

    def remove_curves(self):
        for list_item in self._curve_list.selectedItems():
            i = self._curve_list.row(list_item)
            self._curve_list.takeItem(i)
            self._graph.remove_line2D(i, update_canvas=False)
        self._graph.update_canvas()


class SettingsDialog(qtw.QDialog):
    def __init__(self, settings):
        super().__init__()
        self.setWindowModality(qtc.Qt.WindowModality.ApplicationModal)
        layout = qtw.QVBoxLayout(self)
        
        # Form
        user_form = pwi.UserForm()
        layout.addWidget(user_form)

        user_form.add_row(pwi.IntSpinBox("import_ppo",
                                        "Interpolate the curve to here defined points per octave in import"
                                        "\nThis is used to simplify curves with too many points, such as Klippel graph imports."
                                        "\nSet to '0' to do no modification to curve."
                                        "\nDefault value: 384",
                                        ),
                          "Interpolate during import (ppo)",
                          )

        user_form.add_row(pwi.IntSpinBox("export_ppo",
                                        "Interpolate the curve to here defined points per octave while exporting"
                                        "\nThis is used to simplify curves with too many points, such as Klippel graph imports."
                                        "\nSet to '0' to do no modifications to curve."
                                        "\nDefault value: 96",
                                        ),
                          "Interpolate before export (ppo)",
                          )
        user_form._user_input_widgets["export_ppo"].setValue(96)

        # Buttons
        button_group = pwi.PushButtonGroup({"save": "Save",
                                            "cancel": "Cancel",
                                            },
                                            {},
                                            )
        button_group.buttons()["save_pushbutton"].setDefault(True)
        layout.addWidget(button_group)

        # read values from settings
        for key, widget in user_form._user_input_widgets.items():
            widget.setValue(getattr(settings, key))

        # Connections
        button_group.buttons()["cancel_pushbutton"].clicked.connect(self.reject)
        button_group.buttons()["save_pushbutton"].clicked.connect(partial(self._save_and_close,  user_form._user_input_widgets, settings))

    def _save_and_close(self, user_data_widgets, settings):
        for key, widget in user_data_widgets.items():
            settings.update_attr(key, widget.value())
        self.accept()


class AutoImporter(qtc.QThread):
    new_import = qtc.Signal(Curve)
    def __init__(self):
        super().__init__()
    
    def run(self):
        while not self.isInterruptionRequested():
            cb_data = pyperclip.waitForNewPaste()
            print("\nClipboard read:" + "\n" + str(type(cb_data)) + "\n" + cb_data)
            try:
                new_curve = Curve(cb_data)
                if new_curve.is_curve():
                    self.new_import.emit(new_curve)
            except Exception as e:
                logging.warning(e)


if __name__ == "__main__":
    
    if not (app := qtw.QApplication.instance()):
        app = qtw.QApplication(sys.argv)
        # there is a new recommendation with qApp but how to dod the sys.argv with that?

    settings = pwi.Settings()

    mw = CurveAnalyze(settings)

    mw.show()
    app.exec()
