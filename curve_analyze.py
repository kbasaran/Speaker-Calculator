import os
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
            string1 = str(names[i])
            string2 = str(names[j])
            match = SequenceMatcher(None, string1, string2).find_longest_match(0, len(string1), 0, len(string2))
            matching_substring=string1[match.a:match.a+match.size]
            if(matching_substring not in substring_counts):
                substring_counts[matching_substring]=1
            else:
                substring_counts[matching_substring]+=1
    
    max_occurring_key = max(substring_counts, key=substring_counts.get)  # max looks at the output of get method

    return max_occurring_key.strip().strip("-").strip().strip("-").strip()


class CurveAnalyze(qtw.QWidget):

    signal_good_beep = qtc.Signal()
    signal_bad_beep = qtc.Signal()
    signal_update_graph_request = qtc.Signal()
    signal_reposition_curves = qtc.Signal(list)
    signal_flash_curve = qtc.Signal(int)

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
            {"import_curve": "Import curve",
             "import_table": "Import table",
             "auto_import": "Auto Import",
             "reset_indexes": "Reset Indexes",
             "reset_colors": "Reset Colors",
             "remove": "Remove",
             "rename": "Rename",
             "move_up": "Move up",
             "move_to_top": "Move to top",
             "hide": "Hide",
             "show": "Show",
             "processing": "Processing",
             "export_table": "Export table",
             "export_image": "Export image",
             "settings": "Settings",
             },
            {"import_curve": "Import 2D curve from clipboard",
             "auto_import": "Attempt an import whenever new data is found on the clipboard.",
             },
        )
        self.graph_buttons.user_values_storage(self._user_input_widgets)
        self._user_input_widgets["auto_import_pushbutton"].setCheckable(True)
        self._user_input_widgets["export_image_pushbutton"].setEnabled(False)

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
        self._user_input_widgets["reset_indexes_pushbutton"].clicked.connect(self._reset_indice_in_screen_name)
        self._user_input_widgets["reset_colors_pushbutton"].clicked.connect(self.graph.reset_colors)
        self._user_input_widgets["rename_pushbutton"].clicked.connect(self._rename_curve)
        self._user_input_widgets["move_up_pushbutton"].clicked.connect(self.move_up_1)
        self._user_input_widgets["move_to_top_pushbutton"].clicked.connect(self.move_to_top)
        self._user_input_widgets["hide_pushbutton"].clicked.connect(self._hide_curves)
        self._user_input_widgets["show_pushbutton"].clicked.connect(self._show_curves)
        self._user_input_widgets["export_table_pushbutton"].clicked.connect(self._export_table)
        self._user_input_widgets["export_image_pushbutton"].clicked.connect(self._export_image)
        self._user_input_widgets["auto_import_pushbutton"].toggled.connect(self._auto_importer_status_toggle)
        self._user_input_widgets["settings_pushbutton"].clicked.connect(self._open_settings_dialog)
        self._user_input_widgets["processing_pushbutton"].clicked.connect(self._open_processing_dialog)
        self._user_input_widgets["import_curve_pushbutton"].clicked.connect(
            lambda: self._import_curve(self._read_clipboard())
        )
        self._user_input_widgets["import_table_pushbutton"].clicked.connect(self._import_table)
        self.signal_update_graph_request.connect(self.graph.update_figure)
        self.signal_reposition_curves.connect(self.graph.change_lines_order)
        self.curve_list.itemActivated.connect(self._flash_curve)
        self.signal_flash_curve.connect(self.graph.flash_curve)

    def _export_table(self):
        if len(self.curve_list.selectedItems()) > 1:
            raise NotImplementedError("Can export only one curve at a time")
        else:
            list_item = self.curve_list.selectedItems()[0]
            curve = list_item.data(qtc.Qt.ItemDataRole.UserRole)["curve"]
            
        if settings.export_ppo == 0:
            xy = np.transpose(curve.get_xy(ndarray=True))
            pd.DataFrame(xy).to_clipboard(excel=True, index=False)
        else:
            x_intp, y_intp = signal_tools.interpolate_to_ppo(*curve.get_xy(), settings.export_ppo)
            xy_intp = np.column_stack((x_intp, y_intp))
            pd.DataFrame(xy_intp).to_clipboard(excel=True, index=False, header=False)

    def _export_image(self):
        raise NotImplementedError("Not ready yet")

    def _read_clipboard(self):
        data = pyperclip.paste()
        new_curve = signal_tools.Curve(data)
        if new_curve.is_curve():
            return new_curve
        else:
            logging.debug("Unrecognized curve object")

    def get_selected_curves(self, values, as_dict=False, **kwargs):
        selected_curves = self.curve_list.selectedItems()
        if values == ["q_list_items"] and not as_dict:
            return (self.curve_list.selectedItems(),)
        else:
            ix = [self.curve_list.row(list_item) for list_item in selected_curves]  # horribly slow!!!!!!!!!!!!!!!!!!!!!1
            return self.get_curves(values, rows=ix, as_dict=as_dict, **kwargs)

    def get_curves(self, values: list, rows: list=None, as_dict=False):
        q_list_items = {}
        for i in range(self.curve_list.count()):
            if not rows or (i in rows):
                q_list_items[i] = self.curve_list.item(i)

        return_list = []
        for value in values:
            match value:
                case "q_list_items":
                    result_dict = q_list_items
                case "indexes":
                    result_dict = dict(zip(q_list_items.keys(), q_list_items.keys()))
                case "screen_names":  # name with number as shown on screen
                    result_dict = {i: list_item.text() for (i, list_item) in q_list_items.items()}
                case "curves":  # signal_tools.Curve instances
                    result_dict = {i: list_item.data(qtc.Qt.ItemDataRole.UserRole)["curve"] for (i, list_item) in q_list_items.items()}
                case "curve_names":  # this is the name stored inside curve object. does not include screen number
                    result_dict = {i: list_item.data(qtc.Qt.ItemDataRole.UserRole)["curve"].get_name() for (i, list_item) in q_list_items.items()}
                case "xy_s":  # this is the name stored inside curve object. does not include screen number
                    result_dict = {i: list_item.data(qtc.Qt.ItemDataRole.UserRole)["curve"].get_xy(ndarray=False) for (i, list_item) in q_list_items.items()}
                case "user_data":
                    result_dict = {i: list_item.data(qtc.Qt.ItemDataRole.UserRole) for (i, list_item) in q_list_items.items()}
                case "visibilities":
                    result_dict = {i: list_item.data(qtc.Qt.ItemDataRole.UserRole)["visible"] for (i, list_item) in q_list_items.items()}
                case _:
                    raise KeyError(f"Unrecognized type '{value}' for value arg")
    
            if as_dict:
                return_list.append(result_dict)
            else:
                return_list.append(list(result_dict.values()))
        
        return tuple(return_list)

    def _move_curve_up(self, i_insert):
        new_positions = list(range(self.curve_list.count()))
        # each number in the list is the index before location change. index in the list is the new location. 
        curves, screen_names, visibilities = self.get_selected_curves(["curves", "screen_names", "visibilities"], as_dict=True)
        for i, i_curve in enumerate(curves.keys()):
            screen_name = screen_names[i_curve]
            visible = visibilities[i_curve]
            list_item = qtw.QListWidgetItem(screen_name)
            if not visible:
                font = list_item.font()
                font.setWeight(qtg.QFont.Thin)
                list_item.setFont(font)
            list_item.setData(qtc.Qt.ItemDataRole.UserRole, {"curve": copy.deepcopy(curves[i_curve]),
                                                             "visible": visible,
                                                             }
                              )
            self.curve_list.insertItem(i_insert + i, list_item)
            self.curve_list.takeItem(i_curve+1)
            new_positions.insert(i_insert+i, new_positions.pop(i_curve))

        self.signal_reposition_curves.emit(new_positions)

    def move_up_1(self):
        indexes, = self.get_selected_curves(["indexes"])
        i_insert = max(0, indexes[0] - 1)
        self._move_curve_up(i_insert)
        if len(indexes) == 1:
            self.curve_list.setCurrentRow(i_insert)

    def move_to_top(self):
        self._move_curve_up(0)
        self.curve_list.setCurrentRow(-1)

    def _reset_indice_in_screen_name(self):
        screen_names = {}
        curve_names, q_list_items = self.get_curves(["curve_names", "q_list_items"], as_dict=True)
        for i, list_item in q_list_items.items():
            screen_name = f"#{i:02d} - {curve_names[i]}"
            list_item.setText(screen_name)
            screen_names[i] = screen_name
        self.graph.update_labels(screen_names)

    def _rename_curve(self):
        if len(self.curve_list.selectedItems()) > 1:
            raise NotImplementedError("Can rename only one curve at a time")
        else:
            list_item = self.curve_list.currentItem()
            i = self.curve_list.currentRow()
            curve = list_item.data(qtc.Qt.ItemDataRole.UserRole)["curve"]

        text, ok = qtw.QInputDialog.getText(self,
                                            "Change curve name",
                                            "New name:", qtw.QLineEdit.Normal,
                                            curve.get_name(),
                                            )
        if ok and text != '':
            curve.set_name(text)
            list_item.setText(text)
            self.graph.update_labels({i: text})

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
        ix, = self.get_selected_curves(["indexes"])
        self.graph.remove_line2D(ix)

        for i in reversed(ix):
            self.curve_list.takeItem(i)

    def _import_table(self):
    
        file = qtw.QFileDialog.getOpenFileName(self, caption='Open dBExtract export file..',
                                               dir=self.app_settings.last_used_folder,
                                               filter='dBExtract XY_data (*.txt)',
                                               )[0]
        if file:
            try:
                os.path.isfile(file)
            except:
                raise FileNotFoundError()
                return
        else:
            raise KeyError("Not a file")

        self.app_settings.update_attr(
            "last_used_folder", os.path.dirname(file))
        

        with open(file, mode="rt") as extract_file:
            lines = extract_file.read().splitlines()
            """Read a Klippel dB extract export .txt file."""
            if lines[0] == "XY_data" and lines[1][:4] == "DUTs":
                extract_file.seek(0, 0)
                data = pd.read_csv(extract_file,
                                   delimiter=",",
                                   header=1,
                                   index_col="DUTs",
                                   encoding='unicode_escape',
                                   skipinitialspace=True,
                                   )
                data.columns = [float(i) for i in data.columns]
    
            elif "DUT" == lines[0][:3]:
                extract_file.seek(0, 0)
                data = pd.read_csv(extract_file,
                                   header=None,
                                   index_col=0,
                                   names=['DBTitle', 'Value'],
                                   encoding='unicode_escape',
                                   )
                data = data.sort_values(by=['DBTitle'])
    
            else:
                raise ValueError("Unable to parse the text file."
                                 " Format unrecognized. Did you use the correct DBExtract template?")
            
            if data.shape[1] > 1:  # means if there are more than 1 frequency points
                visible = True  # data.shape[0] < 20
                if not visible:
                    pop_up = qtw.QMessageBox(qtw.QMessageBox.Information,
                                             "Large table import",
                                             "Curves will be imported as hidden, so as not to bloat the legend.",
                                             )
                    pop_up.exec()
                for name, values in data.iterrows():
                    curve = signal_tools.Curve(np.column_stack((data.columns, values)))
                    curve.set_name(name)
                    self._add_curve(None, curve, visible=visible, update_figure=False)
                self.send_visibility_states_to_graph()
                self.signal_update_graph_request.emit()
              
    def _auto_importer_status_toggle(self, checked):
        if checked == 1:
            self.auto_importer = AutoImporter()
            self.auto_importer.new_import.connect(self._import_curve)
            self.auto_importer.start()
        else:
            self.auto_importer.requestInterruption()  

    def _add_curve(self, i, curve, visible=True, update_figure=True, **kwargs):
        if curve.is_curve():
            i_max = self.curve_list.count()
            i_insert = i if i is not None else i_max
            screen_name = f"#{i_max:02d} - {curve.get_name()}"
            list_item = qtw.QListWidgetItem(screen_name)
            list_item.setData(qtc.Qt.ItemDataRole.UserRole, {"curve": curve,
                                                             "visible": visible,
                                                             }
                              )
            self.curve_list.insertItem(i_insert, list_item)
            self.graph.add_line2D(i_insert, screen_name, curve.get_xy(), update_figure=update_figure, **kwargs)
        else:
            raise ValueError("Invalid curve")

    def _hide_curves(self, rows=None):
        if rows:
            items, = self.get_curves(["q_list_items"], rows=rows)
        else:
            items, = self.get_selected_curves(["q_list_items"])

        for item in items:
            font = item.font()
            font.setWeight(qtg.QFont.Thin)
            item.setFont(font)

            data = item.data(qtc.Qt.ItemDataRole.UserRole)
            data["visible"] = False
            item.setData(qtc.Qt.ItemDataRole.UserRole, data)

        self.send_visibility_states_to_graph()

    def _show_curves(self, rows=None):
        if rows:
            items, = self.get_curves(["q_list_items"], rows=rows)
        else:
            items, = self.get_selected_curves(["q_list_items"])

        for item in items:
            font = item.font()
            font.setWeight(qtg.QFont.Normal)
            item.setFont(font)

            data = item.data(qtc.Qt.ItemDataRole.UserRole)
            data["visible"] = True
            item.setData(qtc.Qt.ItemDataRole.UserRole, data)

        self.send_visibility_states_to_graph()

    def _flash_curve(self, item):
        i = self.curve_list.row(item)
        self.signal_flash_curve.emit(i)

    def send_visibility_states_to_graph(self):
        visibility_states, = self.get_curves(["visibilities"], as_dict=True)
        self.graph.hide_show_line2D(visibility_states)

    def _open_processing_dialog(self):
        processing_dialog = ProcessingDialog(self.get_selected_curves(["q_list_items"]))
        processing_dialog.signal_processing_request.connect(self._processing_dialog_return)

        return_value = processing_dialog.exec()
        if return_value:
            self.signal_bad_beep.emit()
            pass

    def _processing_dialog_return(self, processing_fun):
        to_insert = getattr(self, processing_fun)()

        for i, curve in reversed(sorted(to_insert.items())):  # sort the dict by highest key value first
            self._add_curve(i, curve, update_figure=False, color="k")
        self.signal_update_graph_request.emit()

    def _mean_and_median_analysis(self):
        curves_xy, curve_names, ix = self.get_selected_curves(["xy_s", "curve_names", "indexes"])
        if len(curves_xy) < 2:
            raise ValueError("A minimum of 2 curves is needed for this analysis.")
        mean_xy, median_xy = signal_tools.mean_and_median_of_curves(curves_xy)

        calculated_curve_name = find_longest_match_in_name(curve_names)
        mean_xy.set_name(calculated_curve_name + " - mean")
        median_xy.set_name(calculated_curve_name + " - median")

        i_insert = 0
        to_insert = {}
        if settings.mean_selected:
            to_insert[i_insert] = mean_xy
            i_insert += 1
        if settings.median_selected:
            to_insert[i_insert] = median_xy

        return to_insert

    def _smoothen_curves(self):
        curves, curve_names, ix = self.get_selected_curves(
            ["curves", "curve_names", "indexes"],
            as_dict=True,
            )

        i_insert = 0
        to_insert = {}

        for i_curve, curve in curves.items():

            if settings.smoothing_type == 0:
                xy = signal_tools.smooth_curve_butterworth(*curve.get_xy(),
                                                        ppo=settings.smoothing_ppo,
                                                        resolution=settings.smoothing_resolution,
                                                        order=8,
                                                        )

            elif settings.smoothing_type == 1:
                xy = signal_tools.smooth_curve_butterworth(*curve.get_xy(),
                                                        ppo=settings.smoothing_ppo,
                                                        resolution=settings.smoothing_resolution,
                                                        order=4,
                                                        )

            elif settings.smoothing_type == 2:
                xy = signal_tools.smooth_curve_gaussian(*curve.get_xy(),
                                                        ppo=settings.smoothing_ppo,
                                                        resolution=settings.smoothing_resolution,
                                                        )

            else:
                raise NotImplementedError("This smoothing type is not available")

            new_curve = signal_tools.Curve(xy)
            new_curve.set_name(str(curve_names[i_curve]) + f" - smoothed 1/{settings.smoothing_ppo}")
            to_insert[i_insert] = new_curve

        return to_insert

    def _open_settings_dialog(self):
        settings_dialog = SettingsDialog()
        settings_dialog.signal_settings_changed.connect(self._settings_dialog_return)

        return_value = settings_dialog.exec()
        if return_value:
            self.signal_bad_beep.emit()
            pass

    def _settings_dialog_return(self):
        self.signal_update_graph_request.emit()

class ProcessingDialog(qtw.QDialog):
    global settings
    signal_processing_request = qtc.Signal(str)
    def __init__(self, curves):
        super().__init__()
        self.setWindowModality(qtc.Qt.WindowModality.ApplicationModal)
        layout = qtw.QVBoxLayout(self)
        self.tab_widget = qtw.QTabWidget()
        layout.addWidget(self.tab_widget)
        
        self.user_forms_and_recipient_functions = {}  # dict of tuples. key is index of tab. value is tuple with (UserForm, name of function to use for its calculation)

        # Statistics page
        user_form_0 = pwi.UserForm()
        self.tab_widget.addTab(user_form_0, "Statistics")  # tab page is the UserForm widget
        i = self.tab_widget.indexOf(user_form_0)
        self.user_forms_and_recipient_functions[i] = (user_form_0, "_mean_and_median_analysis")

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

        # Smoothing page
        user_form_1 = pwi.UserForm()
        self.tab_widget.addTab(user_form_1, "Smoothing")  # tab page is the UserForm widget
        i = self.tab_widget.indexOf(user_form_1)
        self.user_forms_and_recipient_functions[i] = (user_form_1, "_smoothen_curves")

        user_form_1.add_row(pwi.ComboBox("smoothing_type",
                                        None,
                                        [("Butterworth 8",),
                                         ("Butterworth 4",),
                                         ("Gaussian",),
                                         ]
                                        ),
                          "Type",
                          )
        # user_form_1._user_input_widgets["smoothing_type"].model().item(1).setEnabled(False)  # disable Klippel
        
        user_form_1.add_row(pwi.IntSpinBox("smoothing_resolution",
                                           "Parts per octave resolution for the operation"),
                            "Resolution (ppo)",
                            )        
        user_form_1.add_row(pwi.IntSpinBox("smoothing_ppo",
                                           "Width of the frequency bands in octaves."
                                           "\nFor Gaussion, bandwidth is 2x the standard deviation."
                                           "\nFor Butterworth, bandwidth is the distance between critical frequencies, e.g. -3dB points for a first order filter.",
                                           ),
                            "Bandwidth (ppo)",
                            )


        # Buttons for the dialog - common to self and not per tab
        button_group = pwi.PushButtonGroup({"run": "Run",
                                            "cancel": "Cancel",
                                            },
                                            {},
                                            )
        button_group.buttons()["run_pushbutton"].setDefault(True)
        layout.addWidget(button_group)

        # Update parameters from settings
        for i in range(self.tab_widget.count()):
            user_form = self.tab_widget.widget(i)
            for key, widget in user_form._user_input_widgets.items():
                saved_setting = getattr(settings, key)
                if isinstance(widget, qtw.QCheckBox):
                    widget.setChecked(saved_setting)
                elif isinstance(widget, qtw.QComboBox):
                    widget.setCurrentIndex(saved_setting)
                else:
                    widget.setValue(saved_setting)

        # Connections
        button_group.buttons()["cancel_pushbutton"].clicked.connect(self.reject)
        button_group.buttons()["run_pushbutton"].clicked.connect(self._save_and_close)

    def _save_and_close(self):
        active_tab_index = self.tab_widget.currentIndex()
        user_form, processing_fun = self.user_forms_and_recipient_functions[active_tab_index]

        for key, widget in user_form._user_input_widgets.items():
            if isinstance(widget, qtw.QCheckBox):
                settings.update_attr(key, widget.isChecked())
            elif isinstance(widget, qtw.QComboBox):
                settings.update_attr(key, widget.currentIndex())
            else:
                settings.update_attr(key, widget.value())        

        self.setWindowTitle("Calculating...")
        self.setEnabled(False)  # calculating
        self.repaint()
        self.signal_processing_request.emit(processing_fun)
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

        user_form.add_row(pwi.IntSpinBox("max_legend_size", "Limit the items that can be listed on the legend. Does not affect the shown curves in graph"),
                          "Maximum legend size in graph")

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
            # print("\nClipboard read:" + "\n" + str(type(cb_data)) + "\n" + cb_data)
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
    
    # mw._add_curve(None, signal_tools.Curve(np.array([[100, 200, 400], [80, 90, 90]])))
    # mw._add_curve(None, signal_tools.Curve(np.array([[100, 200, 400], [85, 80, 80]])))
    # mw._add_curve(None, signal_tools.Curve(np.array([[100, 200, 400], [70, 70, 80]])))
    # mw._add_curve(None, signal_tools.Curve(np.array([[100, 200, 400], [60, 70, 90]])))
    # mw._add_curve(None, signal_tools.Curve(np.array([[100, 200, 400], [90, 70, 60]])))

    # mw._add_curve(None, signal_tools.Curve(np.array([[0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512],
    #                                                   [80, 90, 80, 90, 80, 90, 100, 100, 100, 80, 90],
    #                                                   ])))

    # mw._add_curve(None, signal_tools.Curve(np.array([[0,512],
    #                                                   [0, 0],
    #                                                   ])))


    mw.show()
    app.exec()
