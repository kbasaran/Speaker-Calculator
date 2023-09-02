import sys
import numpy as np
import pandas as pd
from difflib import SequenceMatcher
import copy

# from matplotlib.backends.qt_compat import QtWidgets as qtw
from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc
from PySide6 import QtGui as qtg

from graphing import MatplotlibWidget
import signal_tools
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
    signal_update_graph_request = qtc.Signal()
    signal_reposition_curves = qtc.Signal(list)

    def __init__(self, settings):
        super().__init__()
        self.app_settings = settings
        self._create_core_objects()
        self._create_widgets()
        self._place_widgets()
        self._make_connections()

    def _create_core_objects(self):
        self._user_input_widgets = dict()

    def _create_widgets(self):
        self.graph = MatplotlibWidget(self.app_settings)
        self.graph_buttons = pwi.PushButtonGroup(
            {"import": "Import",
             "auto_import": "Auto Import",
             "reset_indices": "Reset Indexes",
             "remove": "Remove",
             "rename": "Rename",
             "move_up": "Move up",
             "move_to_top": "Move to top",
             "hide": "Hide",
             "show": "Show",
             "analysis": "Analysis",
             "export": "Export",
             "settings": "Settings",
             },
            {"import": "Import 2D graph data from clipboard"},
        )
        self.graph_buttons.user_values_storage(self._user_input_widgets)
        self._user_input_widgets["auto_import_pushbutton"].setCheckable(True)
        # self._user_input_widgets["move_to_top_pushbutton"].setEnabled(False)

        self.curve_list = qtw.QListWidget()
        self.curve_list.setSelectionMode(qtw.QAbstractItemView.ExtendedSelection)
        # self.curve_list.setDragDropMode(qtw.QAbstractItemView.InternalMove)  # crashes the application

    def _place_widgets(self):
        self.setLayout(qtw.QVBoxLayout())
        self.layout().addWidget(self.graph, 2)
        self.layout().addWidget(self.graph_buttons)
        self.layout().addWidget(self.curve_list)

    def _make_connections(self):
        self._user_input_widgets["remove_pushbutton"].clicked.connect(self.remove_curves)
        self._user_input_widgets["reset_indices_pushbutton"].clicked.connect(self._reset_indices)
        self._user_input_widgets["rename_pushbutton"].clicked.connect(self._rename_curve)
        self._user_input_widgets["move_up_pushbutton"].clicked.connect(self.move_up_1)
        self._user_input_widgets["move_to_top_pushbutton"].clicked.connect(self.move_to_top)
        self._user_input_widgets["hide_pushbutton"].clicked.connect(self._hide_curves)
        self._user_input_widgets["show_pushbutton"].clicked.connect(self.show_curves)
        self._user_input_widgets["export_pushbutton"].clicked.connect(self._export_to_clipboard)
        self._user_input_widgets["auto_import_pushbutton"].toggled.connect(self._auto_importer_status_toggle)
        self._user_input_widgets["settings_pushbutton"].clicked.connect(self._open_settings_dialog)
        self._user_input_widgets["analysis_pushbutton"].clicked.connect(self._open_analysis_dialog)
        self._user_input_widgets["import_pushbutton"].clicked.connect(
            lambda: self._import_curve(self._read_clipboard())
        )
        self.signal_update_graph_request.connect(self.graph.update_figure)
        self.signal_reposition_curves.connect(self.graph.set_curves_zorder)

    def _export_to_clipboard(self):
        if len(self.curve_list.selectedItems()) > 1:
            raise NotImplementedError("Can export only one curve at a time")
        else:
            list_item = self.curve_list.selectedItems()[0]
            curve = list_item.data(qtc.Qt.ItemDataRole.UserRole)["curve"]
            
        if settings.export_ppo == 0:
            xy = np.transpose(curve.get_xy(ndarray=True))
            pd.DataFrame(xy, columns=["frequency", "value"]).to_clipboard(excel=True, index=False)
        else:
            x_intp, y_intp = signal_tools.interpolate_to_ppo(*curve.get_xy(), settings.export_ppo)
            xy_intp = np.column_stack((x_intp, y_intp))
            pd.DataFrame(xy_intp).to_clipboard(excel=True, index=False, header=False)

    def _read_clipboard(self):
        data = pyperclip.paste()
        new_curve = signal_tools.Curve(data)
        if new_curve.is_curve():
            return new_curve
        else:
            logging.debug("Unrecognized curve object")

    def get_selected_curves(self, value, **kwargs):
        ix = []
        for list_item in self.curve_list.selectedItems():
            ix.append(self.curve_list.row(list_item))  # wow this will be slow..
        return self.get_curves(value, rows=ix, **kwargs)


    def get_curves(self, value:str, rows:list=None, as_dict=False):
        q_list_items = {}
        for i in range(self.curve_list.count()):
            if not rows or (i in rows):
                q_list_items[i] = self.curve_list.item(i)

        match value:
            case "q_list_items":
                result_dict = q_list_items
            case "ix":
                result_dict = dict(zip(q_list_items.keys(), q_list_items.keys()))
            case "screen_name":  # name with number as shown on screen
                result_dict = {i: list_item.text() for (i, list_item) in q_list_items.items()}
            case "curves":  # signal_tools.Curve instances
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

    def _move_curve_up(self, i_insert):
        new_positions = list(range(self.curve_list.count()))
        # each number in the list is the index before location change. index in the list is the new location. 
        curves = self.get_selected_curves("curves", as_dict=True)
        screen_names = self.get_selected_curves("screen_name", as_dict=True)
        for i, i_curve in enumerate(curves.keys()):
            screen_name = screen_names[i_curve]
            list_item = qtw.QListWidgetItem(screen_name)
            list_item.setData(qtc.Qt.ItemDataRole.UserRole, {"curve": copy.deepcopy(curves[i_curve]),
                                                             "visible": True,
                                                             }
                              )
            self.curve_list.insertItem(i_insert + i, list_item)
            self.curve_list.takeItem(i_curve+1)
            new_positions.insert(i_insert+i, new_positions.pop(i_curve))

        self.signal_reposition_curves.emit(new_positions)

    def move_up_1(self):
        i_insert = max(0, self.get_selected_curves("ix")[0] - 1)
        self._move_curve_up(i_insert)
        if len(self.get_selected_curves("q_list_items")) == 1:
            self.curve_list.setCurrentRow(i_insert)

    def move_to_top(self):
        self._move_curve_up(0)
        self.curve_list.setCurrentRow(-1)

    def _reset_indices(self):
        labels = {}
        curve_names = self.get_curves("curve_names", as_dict=True)
        for i, list_item in self.get_curves("q_list_items", as_dict=True).items():
            screen_name = f"#{i:02d} - {curve_names[i]}"
            list_item.setText(screen_name)
            labels[i] = screen_name
        self.graph.update_labels(labels)

    def _rename_curve(self):
        if len(self.curve_list.selectedItems()) > 1:
            raise NotImplementedError("Can rename only one curve at a time")
        else:
            list_item = self.curve_list.selectedItems()[0]
            i = self.curve_list.row(list_item)
            curve = list_item.data(qtc.Qt.ItemDataRole.UserRole)["curve"]
        
        text, ok = qtw.QInputDialog.getText(self,
                                            "Change curve name",
                                            "New name:", qtw.QLineEdit.Normal,
                                            curve.get_name(),
                                            )
        if ok and text != '':
            curve.set_name(text)
            list_item.setText(text)
            self.graph.update_labels_and_colors({i: text})

    def _add_curve(self, i_insert, curve):
        if curve.is_curve():
            i = self.curve_list.count()
            screen_name = f"#{i:02d} - {curve.get_name()}"
            list_item = qtw.QListWidgetItem(screen_name)
            list_item.setData(qtc.Qt.ItemDataRole.UserRole, {"curve": curve,
                                                             "visible": True,
                                                             }
                              )
            if i_insert:
                self.curve_list.insertItem(i_insert, list_item)
            else:
                self.curve_list.insertItem(self.curve_list.count(), list_item)
            self.graph.add_line2D(i, screen_name, curve.get_xy())
        else:
            raise ValueError("Invalid curve")

    def _hide_curves(self, rows=None):
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
        self.graph.hide_show_line2D(visibility_states)

    def _open_analysis_dialog(self):
        analysis_dialog = AnalysisDialog(self.get_selected_curves("q_list_items"))
        analysis_dialog.signal_analysis_request.connect(self._analysis_dialog_return)

        return_value = analysis_dialog.exec()
        if return_value:
            self.signal_bad_beep.emit()
            pass

    def _analysis_dialog_return(self, analysis_fun):
        to_insert = getattr(self, analysis_fun)()

        for index_and_curve in to_insert:
            self._add_curve(*index_and_curve)

    def _mean_and_median_analysis(self):
        curves_xy = self.get_selected_curves("xy_s")
        if len(curves_xy) < 2:
            raise ValueError("A minimum of 2 curves is needed for this analysis.")
        mean_xy, median_xy = signal_tools.mean_and_median_of_curves(curves_xy)

        calculated_curve_name = find_longest_match_in_name(self.get_selected_curves("curve_names"))  # .strip().strip("-").strip()
        mean_xy.set_name(calculated_curve_name + " - mean")
        median_xy.set_name(calculated_curve_name + " - median")

        i_insert = max(self.get_selected_curves("ix")) + 1
        to_insert = []
        if settings.mean_selected:
            to_insert.append((i_insert, mean_xy))
            i_insert += 1
        if settings.median_selected:
            to_insert.append((i_insert, median_xy))

        return to_insert

    def _auto_importer_status_toggle(self, checked):
        if checked == 1:
            self.auto_importer = AutoImporter()
            self.auto_importer.new_import.connect(self._import_curve)
            self.auto_importer.start()
        else:
            self.auto_importer.requestInterruption()

    def _open_settings_dialog(self):
        settings_dialog = SettingsDialog()
        settings_dialog.signal_settings_changed.connect(self._settings_dialog_return)

        return_value = settings_dialog.exec()
        if return_value:
            self.signal_bad_beep.emit()
            pass

    def _settings_dialog_return(self):
        self.signal_update_graph_request.emit()

    @qtc.Slot(signal_tools.Curve)
    def _import_curve(self, curve):

        try:
            if settings.import_ppo > 0:
                x, y = curve.get_xy()
                x_intp, y_intp = signal_tools.interpolate_to_ppo(x, y, settings.import_ppo)
                curve.set_xy((x_intp, y_intp))
    
            if curve.is_curve():
                self._add_curve(None, curve)
                self.signal_good_beep.emit()

        except Exception as e:
            self.signal_bad_beep.emit()
            raise e

    def remove_curves(self):
        ix = self.get_selected_curves("ix")
        self.graph.remove_line2D(ix)

        for i in reversed(ix):
            self.curve_list.takeItem(i)


class AnalysisDialog(qtw.QDialog):
    global settings
    signal_analysis_request = qtc.Signal(str)
    def __init__(self, curves):
        super().__init__()
        self.setWindowModality(qtc.Qt.WindowModality.ApplicationModal)
        layout = qtw.QVBoxLayout(self)
        tab_widget = qtw.QTabWidget()
        layout.addWidget(tab_widget)
        
        user_forms_and_recipient_functions = {}  # dict of tuples. key is index of tab. value is tuple with (UserForm, name of function to use for its calculation)

        # Statistics page
        user_form_0 = pwi.UserForm()
        tab_widget.addTab(user_form_0, "Statistics")  # tab page is the UserForm widget
        i = tab_widget.indexOf(user_form_0)
        user_forms_and_recipient_functions[i] = (user_form_0, "_mean_and_median_analysis")
        
        user_form_0.add_row(pwi.CheckBox("mean_selected",
                                        "Mean value per frequency point.",
                                        ),
                          "Calculate mean",
                          )

        user_form_0.add_row(pwi.CheckBox("median_selected",
                                        "Median value per frequency point. Less sensitive to outliers.",
                                        ),
                          "Calculate median",
                          )


        # Buttons - common to self. not per tab.
        button_group = pwi.PushButtonGroup({"run": "Run",
                                            "cancel": "Cancel",
                                            },
                                            {},
                                            )
        button_group.buttons()["run_pushbutton"].setDefault(True)
        layout.addWidget(button_group)


        for i in range(tab_widget.count()):
            user_form = tab_widget.widget(i)
            # read values from settings
            for key, widget in user_form._user_input_widgets.items():
                saved_setting = getattr(settings, key)
                if isinstance(widget, qtw.QCheckBox):
                    widget.setChecked(saved_setting)
                else:
                    widget.setValue(saved_setting)

        # Connections
        button_group.buttons()["cancel_pushbutton"].clicked.connect(self.reject)
        button_group.buttons()["run_pushbutton"].clicked.connect(partial(self._save_and_close,
                                                                         *user_forms_and_recipient_functions[tab_widget.currentIndex()],
                                                                         ))

    def _save_and_close(self, active_user_form, analysis_fun: str):
        for key, widget in active_user_form._user_input_widgets.items():
            if isinstance(widget, qtw.QCheckBox):
                settings.update_attr(key, widget.isChecked())
            else:
                settings.update_attr(key, widget.value())
        self.signal_analysis_request.emit(analysis_fun)
        self.accept()


class SettingsDialog(qtw.QDialog):
    global settings
    signal_settings_changed = qtc.Signal()
    def __init__(self):
        super().__init__()
        self.setWindowModality(qtc.Qt.WindowModality.ApplicationModal)
        layout = qtw.QVBoxLayout(self)
        
        # Form
        user_form = pwi.UserForm()
        layout.addWidget(user_form)
        
        user_form.add_row(pwi.CheckBox("show_legend", "Show legend on the graph"),
                          "Show legend")

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
            saved_setting = getattr(settings, key)
            if isinstance(widget, qtw.QCheckBox):
                widget.setChecked(saved_setting)
            else:
                widget.setValue(saved_setting)

        # Connections
        button_group.buttons()["cancel_pushbutton"].clicked.connect(self.reject)
        button_group.buttons()["save_pushbutton"].clicked.connect(partial(self._save_and_close,  user_form._user_input_widgets, settings))

    def _save_and_close(self, user_input_widgets, settings):
        for key, widget in user_input_widgets.items():
            if isinstance(widget, qtw.QCheckBox):
                settings.update_attr(key, widget.isChecked())
            else:
                settings.update_attr(key, widget.value())
        self.signal_settings_changed.emit()
        self.accept()


class AutoImporter(qtc.QThread):
    new_import = qtc.Signal(signal_tools.Curve)
    def __init__(self):
        super().__init__()
    
    def run(self):
        while not self.isInterruptionRequested():
            cb_data = pyperclip.waitForNewPaste()
            print("\nClipboard read:" + "\n" + str(type(cb_data)) + "\n" + cb_data)
            try:
                new_curve = signal_tools.Curve(cb_data)
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
    
    mw._add_curve(None, signal_tools.Curve(np.array([[100, 200, 400], [80, 90, 90]])))
    mw._add_curve(None, signal_tools.Curve(np.array([[100, 200, 400], [85, 80, 80]])))
    mw._add_curve(None, signal_tools.Curve(np.array([[100, 200, 400], [70, 70, 80]])))
    mw._add_curve(None, signal_tools.Curve(np.array([[100, 200, 400], [60, 70, 90]])))
    mw._add_curve(None, signal_tools.Curve(np.array([[100, 200, 400], [90, 70, 60]])))


    mw.show()
    app.exec()
