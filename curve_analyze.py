import os
import sys
import numpy as np
import pandas as pd
from difflib import SequenceMatcher

# from matplotlib.backends.qt_compat import QtWidgets as qtw
from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc
from PySide6 import QtGui as qtg

from graphing import MatplotlibWidget
import signal_tools
import personalized_widgets as pwi
import pyperclip  # must install xclip on Linux together with this!!
from functools import partial
import matplotlib as mpl
from tabulate import tabulate
from io import StringIO

import logging
logging.basicConfig(level=logging.INFO)

# https://matplotlib.org/stable/gallery/user_interfaces/embedding_in_qt_sgskip.html

version = "XXX"


def find_longest_match_in_name(names: list) -> str:
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
        The piece of string that accurs most commonly in the received list of names.

    """
    substring_counts = {}
    names_list = list(names)
    for i in range(0, len(names)):
        for j in range(i+1, len(names)):
            string1 = str(names_list[i])
            string2 = str(names_list[j])
            match = SequenceMatcher(None, string1, string2).find_longest_match(
                0, len(string1), 0, len(string2))
            matching_substring = string1[match.a:match.a+match.size]
            if(matching_substring not in substring_counts):
                substring_counts[matching_substring] = 1
            else:
                substring_counts[matching_substring] += 1

    # max looks at the output of get method
    max_occurring_key = max(substring_counts, key=substring_counts.get)

    return max_occurring_key.strip().strip("-").strip().strip("-").strip()


class CurveAnalyze(qtw.QWidget):
    global settings

    signal_good_beep = qtc.Signal()
    signal_bad_beep = qtc.Signal()
    signal_update_graph_request = qtc.Signal()
    signal_reposition_curves = qtc.Signal(list)
    signal_flash_curve = qtc.Signal(int)
    signal_graph_settings_changed = qtc.Signal()
    signal_successful_table_import = qtc.Signal()
    # signal_key_pressed = qtc.Signal(str)

    def __init__(self):
        super().__init__()
        self._create_core_objects()
        self._create_widgets()
        self._place_widgets()
        self._make_connections()

    def keyPressEvent(self, keyEvent):
        # overwriting method inherited from class
        # Sequence names: https://doc.qt.io/qtforpython-6/PySide6/QtGui/QKeySequence.html
        if keyEvent.matches(qtg.QKeySequence.Delete):
            self.remove_curves()
        if keyEvent.matches(qtg.QKeySequence.Cancel):
            self.qlistwidget_for_curves.setCurrentRow(-1)

    def _create_core_objects(self):
        self._user_input_widgets = dict()
        self.curves = []
        self.reference_curve = None

    def _create_widgets(self):
        self.graph = MatplotlibWidget(settings)
        self.graph_buttons = pwi.PushButtonGroup(
            {
            "import_curve": "Import curve",
            "import_table": "Import table",
            "auto_import": "Auto import",
            "reset_indexes": "Reset indexes",
             "reset_colors": "Reset colors",
             "remove": "Remove",
             "rename": "Rename",
             "move_up": "Move up",
             "move_to_top": "Move to top",
             "hide": "Hide",
             "show": "Show",
             "set_reference": "Set reference",
             "processing": "Processing",
             "export_table": "Export table",
             # "export_image": "Export image",
             "settings": "Settings",
             "load": "Load",
             "save": "Save",
             },
            {"import_curve": "Import 2D curve from clipboard",
             "auto_import": "Attempt an import whenever new data is found on the clipboard.",
             },
        )
        self.graph_buttons.user_values_storage(self._user_input_widgets)
        self.graph_buttons.user_values_storage(self._user_input_widgets)
        self._user_input_widgets["auto_import_pushbutton"].setCheckable(True)
        self._user_input_widgets["set_reference_pushbutton"].setCheckable(True)
        self._user_input_widgets["load_pushbutton"].setEnabled(False)
        self._user_input_widgets["save_pushbutton"].setEnabled(False)
        # self._user_input_widgets["export_image_pushbutton"].setEnabled(False)

        self.qlistwidget_for_curves = qtw.QListWidget()
        self.qlistwidget_for_curves.setSelectionMode(
            qtw.QAbstractItemView.ExtendedSelection)
        # self.qlistwidget_for_curves.setDragDropMode(qtw.QAbstractItemView.InternalMove)  # crashes the application

        # set size policies
        self.graph.setSizePolicy(
            qtw.QSizePolicy.MinimumExpanding, qtw.QSizePolicy.MinimumExpanding)

    def _place_widgets(self):
        self.setLayout(qtw.QVBoxLayout())
        # self.layout().setSpacing(0)
        self.layout().addWidget(self.graph, 3)
        self.layout().addWidget(self.graph_buttons)
        self.layout().addWidget(self.qlistwidget_for_curves, 1)

    def _make_connections(self):
        self._user_input_widgets["remove_pushbutton"].clicked.connect(
            self.remove_curves)
        self._user_input_widgets["reset_indexes_pushbutton"].clicked.connect(
            self._reset_indexes)
        self._user_input_widgets["reset_colors_pushbutton"].clicked.connect(
            self._reset_colors_of_curves)
        self._user_input_widgets["rename_pushbutton"].clicked.connect(
            self._rename_curve_clicked)
        self._user_input_widgets["move_up_pushbutton"].clicked.connect(
            self.move_up_1)
        self._user_input_widgets["move_to_top_pushbutton"].clicked.connect(
            self.move_to_top)
        self._user_input_widgets["hide_pushbutton"].clicked.connect(
            self._hide_curves)
        self._user_input_widgets["show_pushbutton"].clicked.connect(
            self._show_curves)
        self._user_input_widgets["export_table_pushbutton"].clicked.connect(
            self._export_table)
        # self._user_input_widgets["export_image_pushbutton"].clicked.connect(
        #     self._export_image)
        self._user_input_widgets["auto_import_pushbutton"].toggled.connect(
            self._auto_importer_status_toggle)
        self._user_input_widgets["set_reference_pushbutton"].toggled.connect(
            self._reference_curve_status_toggle)
        self._user_input_widgets["settings_pushbutton"].clicked.connect(
            self._open_settings_dialog)
        self._user_input_widgets["processing_pushbutton"].clicked.connect(
            self._open_processing_dialog)
        self._user_input_widgets["import_curve_pushbutton"].clicked.connect(
            self.import_single_curve)
        self._user_input_widgets["import_table_pushbutton"].clicked.connect(
            self._import_table_clicked)
        self._user_input_widgets["load_pushbutton"].clicked.connect(
            self._load_clicked)
        self._user_input_widgets["save_pushbutton"].clicked.connect(
            self._save_clicked)        
        self.signal_update_graph_request.connect(self.graph.update_figure)
        self.signal_reposition_curves.connect(self.graph.change_lines_order)
        self.qlistwidget_for_curves.itemActivated.connect(self._flash_curve)
        self.signal_flash_curve.connect(self.graph.flash_curve)
        self.signal_graph_settings_changed.connect(self.graph.set_grid_type)

    def _export_table(self):
        """Export selected curves to clipboard as a table."""
        if self.no_curve_selected():
            return
        if len(self.qlistwidget_for_curves.selectedItems()) > 1:
            raise NotImplementedError("Can export only one curve at a time")
        else:
            curve = self.get_selected_curves()[0]

        if settings.export_ppo == 0:
            xy_export = np.transpose(curve.get_xy(ndarray=True))
        else:
            x_intp, y_intp = signal_tools.interpolate_to_ppo(
                *curve.get_xy(),
                settings.export_ppo,
                settings.interpolate_must_contain_hz,
            )
            if signal_tools.arrays_are_equal((x_intp, curve.get_xy()[0])):
                xy_export = np.transpose(curve.get_xy(ndarray=True))
            else:
                xy_export = np.column_stack((x_intp, y_intp))

        pd.DataFrame(xy_export).to_clipboard(
            excel=True, index=False, header=False)

    def _read_clipboard(self):
        """Read a signal_tools.Curve object from clipboard."""
        data = pyperclip.paste()
        new_curve = signal_tools.Curve(data)
        if new_curve.is_curve():
            return new_curve
        else:
            logging.debug("Unrecognized curve object")

    def get_selected_curve_indexes(self) -> list:
        selected_list_items = self.qlistwidget_for_curves.selectedItems()
        indexes = [self.qlistwidget_for_curves.row(
            list_item) for list_item in selected_list_items]
        return indexes

    def get_selected_curves(self, as_dict: bool = False) -> (list, dict):
        selected_indexes = self.get_selected_curve_indexes()

        if as_dict:
            return {i: self.curves[i] for i in selected_indexes}
        else:
            return [self.curves[i] for i in selected_indexes]

    def count_selected_curves(self) -> int:
        selected_indexes = self.get_selected_curve_indexes()
        return len(selected_indexes)

    def no_curve_selected(self) -> bool:
        if self.qlistwidget_for_curves.selectedItems():
            return False
        else:
            self.signal_bad_beep.emit()
            return True

    def _move_curve_up(self, i_insert: int):
        selected_indexes_and_curves = self.get_selected_curves(as_dict=True)

        new_indexes = [*range(len(self.curves))]
        # each number in the list is the index before location change. index in the list is the new location.
        for i_within_selected, (i_before, curve) in enumerate(selected_indexes_and_curves.items()):
            # i_within_selected is the index within the selected curves
            # i_before is the index on the complete curves list
            i_after = i_insert + i_within_selected

            # do the self.curves list (single source of truth)
            curve = self.curves.pop(i_before)
            self.curves.insert(i_after, curve)

            # do the QListWidget
            new_list_item = qtw.QListWidgetItem(curve.get_full_name())
            print(curve.get_full_name())
            if not curve.is_visible():
                font = new_list_item.font()
                font.setWeight(qtg.QFont.Thin)
                new_list_item.setFont(font)

            self.qlistwidget_for_curves.insertItem(i_after, new_list_item)
            self.qlistwidget_for_curves.takeItem(i_before + 1)

            # do the changes dictionary to send to the graph
            new_indexes.insert(i_after, new_indexes.pop(i_before))

        # send the changes dictionary to the graph
        self.signal_reposition_curves.emit(new_indexes)

    def move_up_1(self):
        if self.no_curve_selected():
            self.signal_bad_beep.emit()
        selected_indexes = self.get_selected_curve_indexes()
        i_insert = max(0, selected_indexes[0] - 1)
        self._move_curve_up(i_insert)
        if len(selected_indexes) == 1:
            self.qlistwidget_for_curves.setCurrentRow(i_insert)

    def move_to_top(self):
        if self.no_curve_selected():
            self.signal_bad_beep.emit()
        self._move_curve_up(0)
        self.qlistwidget_for_curves.setCurrentRow(-1)

    def _reset_indexes(self):
        if not len(self.curves):
            self.signal_bad_beep.emit()
        else:
            for i, curve in enumerate(self.curves):
                curve.set_name_prefix(f"#{i:02d}")
                self.qlistwidget_for_curves.item(
                    i).setText(curve.get_full_name())
            returned = self.graph.update_labels(
                {i: curve.get_full_name() for i, curve in enumerate(self.curves)})
            if not returned:
                self.signal_good_beep.emit()

    def _reset_colors_of_curves(self):
        if not len(self.curves):
            self.signal_bad_beep.emit()
        else:
            returned = self.graph.reset_colors()
            if not returned:
                self.signal_good_beep.emit()


    def _rename_curve_clicked(self):
        """
        Update the curve and the screen name. Does not store the index part of the screen name.
        """
        new_names = {}
        
        if self.no_curve_selected():
            self.signal_bad_beep.emit()
            return

        elif len(self.qlistwidget_for_curves.selectedItems()) > 1:
            indexes_and_curves = self.get_selected_curves(as_dict=True)
            text, ok = qtw.QInputDialog.getText(self,
                                                "Add suffix to multiple names",
                                                "Add suffix:", qtw.QLineEdit.Normal,
                                                "",
                                                )
            if not ok or text == '':
                return

            for index, curve in indexes_and_curves.items():
                curve.add_name_suffix(text)
                list_item = self.qlistwidget_for_curves.item(index)
                list_item.setText(curve.get_full_name())
                new_names[index] = curve.get_full_name()

        else:
            index = self.qlistwidget_for_curves.currentRow()
            curve = self.curves[index]

            text, ok = qtw.QInputDialog.getText(self,
                                                "Change curve name",
                                                "New name:", qtw.QLineEdit.Normal,
                                                curve.get_base_name_and_suffixes(),
                                                )
            if not ok or text == '':
                return

            curve.clear_name_suffixes()
            curve.set_name_base(text)
            list_item = self.qlistwidget_for_curves.item(index)
            list_item.setText(curve.get_full_name())
            new_names[index] = curve.get_full_name()
        
        self.graph.update_labels(new_names)

    @qtc.Slot(signal_tools.Curve)
    def import_single_curve(self, curve: signal_tools.Curve = None):
        if curve in (None, False):
            curve = self._read_clipboard()
        try:
            if settings.import_ppo > 0:
                x, y = curve.get_xy()
                x_intp, y_intp = signal_tools.interpolate_to_ppo(
                    x, y,
                    settings.import_ppo,
                    settings.interpolate_must_contain_hz,
                )
                curve.set_xy((x_intp, y_intp))

            if curve.is_curve():
                i_insert = self._add_single_curve(None, curve)
                self.qlistwidget_for_curves.setCurrentRow(i_insert)
                self.signal_good_beep.emit()

        except:
            self.signal_bad_beep.emit()

    def remove_curves(self, indexes: list = None):
        if isinstance(indexes, (list, np.ndarray)):
            if len(indexes) == 0:  # received empty list
                self.signal_bad_beep.emit()
                return
            else:
                indexes_to_act_on = indexes

        elif indexes in (False, None) and self.no_curve_selected():
            return

        elif indexes in (False, None):
            indexes_to_act_on = self.get_selected_curve_indexes()

        self.graph.remove_line2d(indexes_to_act_on)
        for i in reversed(indexes_to_act_on):
            self.qlistwidget_for_curves.takeItem(i)
            self.curves.pop(i)

    def _import_table_clicked(self):
        import_table_dialog = ImportDialog()
        import_table_dialog.signal_import_table_request.connect(
            self._import_table_requested)
        self.signal_successful_table_import.connect(import_table_dialog.reject)
        import_table_dialog.show()

    def _import_table_requested(self, source, import_settings):
        # get the input
        if source == "file":
            file = qtw.QFileDialog.getOpenFileName(self, caption='Open dBExtract export file..',
                                                   dir=settings.last_used_folder,
                                                   filter='dBExtract XY_data (*.txt)',
                                                   )[0]
            if file:
                try:
                    if os.path.isfile(file):
                        import_file = file
                    else:
                        raise Exception
                except:
                    raise FileNotFoundError
            else:
                return
    
            settings.update_attr("last_used_folder", os.path.dirname(import_file))

        elif source == "clipboard":
            import_file = StringIO(pyperclip.paste())

        # setup how to read it
        if import_settings["no_header"] == 0:
            skiprows = None
            header = None
        else:
            skiprows = [*range(import_settings["no_header"] - 1)] if import_settings["no_header"] > 1 else None
            header = 0
        
        if import_settings["no_index"] == 0:
            index_col = None
        else:
            index_col = import_settings["no_index"] - 1

        # read it
        try:
            df = pd.read_csv(import_file,
                               delimiter=import_settings["delimiter"],
                               decimal=import_settings["decimal_separator"],
                               skiprows=skiprows,
                               header=header,
                               index_col=index_col,
                               # skip_blank_lines=True,
                               # encoding='unicode_escape',
                               skipinitialspace=True,  # since we only have numbers
                               )
        except IndexError:
            raise IndexError("Check your import settings and if all your rows and columns have the same length in the imported text.")
            return


        # Transpose if frequencies are in indexes
        if import_settings["layout_type"] == 1:
            df = df.transpose()

        # validate headers
        try:
            signal_tools.check_if_sorted_and_valid(df.columns)
            df.columns = df.columns.astype(float)
        except ValueError as e:
            raise e
            return

        # Validate size
        if len(df.columns) < 2:
            raise ValueError("Curve needs to have more than one frequency point."
                             f"Frequency points: {df.columns}")
            return
        if len(df.index) < 1:
            raise ValueError("Import does not have any curves to put on graph.")
            return
        
        # validate datatype
        try:
            df = df.astype(float)
        except ValueError:
            raise ValueError("Your dataset contains values that could not be interpreted as numbers.")
            return
        
        logging.info(df.info)

        # Put on the graph
        for name, values in df.iterrows():
            curve = signal_tools.Curve(np.column_stack((df.columns, values)))
            curve.set_name_base(name)
            _ = self._add_single_curve(None, curve, update_figure=False)

        self.signal_update_graph_request.emit()
        self.signal_successful_table_import.emit()
        self.signal_good_beep.emit()        


    def _import_table_old(self):

        file = qtw.QFileDialog.getOpenFileName(self, caption='Open dBExtract export file..',
                                               dir=settings.last_used_folder,
                                               filter='dBExtract XY_data (*.txt)',
                                               )[0]
        if file:
            try:
                os.path.isfile(file)
            except:
                raise FileNotFoundError()
        else:
            return

        settings.update_attr(
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
                too_large = False  # data.shape[0] < 20
                if too_large:
                    pop_up = qtw.QMessageBox(qtw.QMessageBox.Information,
                                             "Very large table import",
                                             "\nCurves will be reduced somehow to not bloat the canvas."
                                             "\nI don't know how yet.",
                                             )
                    pop_up.exec()

                else:
                    for name, values in data.iterrows():
                        curve = signal_tools.Curve(
                            np.column_stack((data.columns, values)))
                        curve.set_name_base(name)
                        _ = self._add_single_curve(
                            None, curve, update_figure=False)

                self.signal_update_graph_request.emit()
                self.signal_good_beep.emit()

    def _auto_importer_status_toggle(self, checked: bool):
        if checked == 1:
            self.auto_importer = AutoImporter()
            self.auto_importer.signal_new_import.connect(
                self.import_single_curve)
            self.auto_importer.start()
        else:
            self.auto_importer.requestInterruption()

    def _reference_curve_status_toggle(self, checked: bool):
        """
        Reference curve is marked in the Curve class instances with "_visible"
        Also in the graph object, there is an attribute to store if there is a reference and if so which one it is.
        """
        if checked == True:
            # Block precessing options
            indexes_and_curves = self.get_selected_curves(as_dict=True)
            if len(indexes_and_curves) == 1:
                self._user_input_widgets["processing_pushbutton"].setEnabled(
                    False)
                index, curve = list(indexes_and_curves.items())[0]

                # mark it as reference
                curve.add_name_suffix("reference")
                curve.set_reference(True)

                # Update the names in list
                reference_item = self.qlistwidget_for_curves.item(index)
                reference_item.setText(curve.get_full_name())

                # Update graph
                self.graph.toggle_reference_curve([index, curve])

            else:
                # multiple selections
                self.signal_bad_beep.emit()
                self._user_input_widgets["set_reference_pushbutton"].setChecked(
                    False)

        elif checked == False:
            # find back the reference curve
            reference_curves = [(index, curve) for index, curve in enumerate(
                self.curves) if curve.is_reference()]
            if len(reference_curves) == 0:
                pass
            elif len(reference_curves) > 1:
                raise ValueError(
                    "Multiple reference curves are in the list somehow..")
            else:
                index, curve = reference_curves[0]

                # revert it
                curve.remove_name_suffix("reference")
                curve.set_reference(False)

                # Update the names in list
                reference_item = self.qlistwidget_for_curves.item(index)
                reference_item.setText(curve.get_full_name())

                # Update graph
                self.graph.toggle_reference_curve(None)

            # Release processing options
            self._user_input_widgets["processing_pushbutton"].setEnabled(True)

    def _add_single_curve(self, i: int, curve: signal_tools.Curve, update_figure: bool = True, line2d_kwargs={}):
        if curve.is_curve():
            i_max = len(self.curves)
            i_insert = i if i is not None else i_max
            curve.set_name_prefix(f"#{i_max:02d}")
            self.curves.insert(i_insert, curve)

            list_item = qtw.QListWidgetItem(curve.get_full_name())
            if not curve.is_visible():
                font = list_item.font()
                font.setWeight(qtg.QFont.Thin)
                list_item.setFont(font)

            self.qlistwidget_for_curves.insertItem(i_insert, list_item)

            self.graph.add_line2d(i_insert, curve.get_full_name(), curve.get_xy(
            ), update_figure=update_figure, line2d_kwargs=line2d_kwargs)

            return i_insert
        else:
            raise ValueError("Invalid curve")

    def _hide_curves(self, indexes: list = None):
        if isinstance(indexes, (list, np.ndarray)):
            indexes_and_curves = {i: self.curves[i] for i in indexes}
        elif self.no_curve_selected():
            return
        else:
            indexes_and_curves = self.get_selected_curves(as_dict=True)

        for index, curve in indexes_and_curves.items():
            item = self.qlistwidget_for_curves.item(index)
            font = item.font()
            font.setWeight(qtg.QFont.Thin)
            item.setFont(font)
            curve.set_visible(False)

        self.send_visibility_states_to_graph()

    def _show_curves(self, indexes: list = None):
        if isinstance(indexes, (list, np.ndarray)):
            indexes_and_curves = {i: self.curves[i] for i in indexes}
        elif self.no_curve_selected():
            return
        else:
            indexes_and_curves = self.get_selected_curves(as_dict=True)

        for index, curve in indexes_and_curves.items():
            item = self.qlistwidget_for_curves.item(index)
            font = item.font()
            font.setWeight(qtg.QFont.Normal)
            item.setFont(font)

            curve.set_visible(True)

        self.send_visibility_states_to_graph()

    def _flash_curve(self, item: qtw.QListWidgetItem):
        index = self.qlistwidget_for_curves.row(item)
        self.signal_flash_curve.emit(index)

    def send_visibility_states_to_graph(self):
        visibility_states = {i: curve.is_visible()
                             for i, curve in enumerate(self.curves)}
        self.graph.hide_show_line2d(visibility_states)

    def _open_processing_dialog(self):
        if self.no_curve_selected():
            return

        processing_dialog = ProcessingDialog(
            self.get_selected_curves())
        processing_dialog.signal_processing_request.connect(
            self._processing_dialog_return)

        processing_dialog.exec()

    def _processing_dialog_return(self, processing_function_name):
        results = getattr(self, processing_function_name)()
        to_beep = False

        if "to_insert" in results.keys():
            # sort the dict by highest key value first
            for i, curve in sorted(results["to_insert"].items()):
                _ = self._add_single_curve(
                    i, curve, update_figure=False, line2d_kwargs=results["line2d_kwargs"])
            self.signal_update_graph_request.emit()
            to_beep = True

        if "result_text" in results.keys():
            result_text_box = ResultTextBox(results["title"], results["result_text"], parent=self)
            result_text_box.show()
            to_beep = True
            
        if to_beep:
            self.signal_good_beep.emit()

    def _mean_and_median_analysis(self):
        curves = self.get_selected_curves()
        if len(curves) < 2:
            raise ValueError(
                "A minimum of 2 curves is needed for this analysis.")
        curve_mean, curve_median = signal_tools.mean_and_median_of_curves(
            [curve.get_xy() for curve in curves]
        )

        representative_base_name = find_longest_match_in_name(
            [curve.get_base_name_and_suffixes() for curve in curves]
        )

        for curve in (curve_mean, curve_median):
            curve.set_name_base(representative_base_name)

        curve_mean.add_name_suffix("mean per frequency point")
        curve_median.add_name_suffix("mean per frequency point")

        i_insert = 0
        to_insert = {}
        if settings.mean_selected:
            to_insert[i_insert] = curve_mean
            i_insert += 1
        if settings.median_selected:
            to_insert[i_insert] = curve_median

        line2d_kwargs = {"color": "k", "linestyle": "-"}

        return {"to_insert": to_insert, "line2d_kwargs": line2d_kwargs}

    def _outlier_detection(self):
        curves = self.get_selected_curves(as_dict=True)
        if len(curves) < 3:
            raise ValueError(
                "A minimum of 3 curves is needed for this analysis.")

        lower_fence, curve_median, upper_fence, outlier_indexes = signal_tools.iqr_analysis(
            {i: curve.get_xy() for i, curve in curves.items()},
            settings.outlier_fence_iqr,
        )

        representative_base_name = find_longest_match_in_name(
            [curve.get_base_name_and_suffixes() for curve in curves.values()]
        )

        for curve in (lower_fence, upper_fence, curve_median):
            curve.set_name_base(representative_base_name)
        lower_fence.add_name_suffix(f"-{settings.outlier_fence_iqr:.1f}xIQR")
        upper_fence.add_name_suffix(f"+{settings.outlier_fence_iqr:.1f}xIQR")
        curve_median.add_name_suffix("median")

        if settings.outlier_action == 1 and outlier_indexes:  # Hide
            self._hide_curves(indexes=outlier_indexes)
            for curve in (lower_fence, upper_fence, curve_median):
                curve.add_name_suffix("calculated before hiding outliers")
        elif settings.outlier_action == 2 and outlier_indexes:  # Remove
            self.remove_curves(indexes=outlier_indexes)
            for curve in (lower_fence, upper_fence, curve_median):
                curve.add_name_suffix("calculated before removing outliers")

        to_insert = {}
        to_insert[0] = upper_fence
        # to_insert[1] = curve_median
        to_insert[1] = lower_fence

        line2d_kwargs = {"color": "k", "linestyle": "--"}

        return {"to_insert": to_insert, "line2d_kwargs": line2d_kwargs}

    def _show_best_fits(self):
        curves = self.get_selected_curves(as_dict=True)
        if len(curves) != 1:
            warning = qtw.QMessageBox(qtw.QMessageBox.Warning,
                                      "Multiple curves found in selection",
                                      "For this operation you need to choose a single curve from the list.",
                                      qtw.QMessageBox.Ok,
                                      )
            warning.exec()
            return {}
        
        else:
            i_ref_curve, ref_curve = list(curves.items())[0]
            ref_freqs, ref_curve_interpolated = signal_tools.interpolate_to_ppo(
                *ref_curve.get_xy(), settings.best_fit_calculation_resolution_ppo)
            other_curves = {i: self.curves[i] for i in range(
                len(self.curves)) if i != i_ref_curve}
            differences_to_ref = {curve.get_full_name(): \
                                  np.abs(np.interp(np.log(ref_freqs), np.log(curve.get_x()), curve.get_y(), left=np.nan, right=np.nan) - ref_curve_interpolated)\
                                      for curve in other_curves.values()}

            df = pd.DataFrame.from_dict(differences_to_ref,
                                        orient='index',
                                        columns=ref_freqs,
                                        dtype=float,
                                        )

            # Apply weighing
            critical_columns = [column for column in df.columns if column >= settings.best_fit_critical_range_start_freq and column < settings.best_fit_critical_range_end_freq]
            if critical_columns:
                weighing_normalizer = (len(df.columns) + len(critical_columns) * (settings.best_fit_critical_range_weight - 1)) / len(df.columns)
                weighing_critical = settings.best_fit_critical_range_weight / weighing_normalizer
                df[critical_columns].apply(lambda x: x * weighing_critical)
                df = df / weighing_normalizer
            else:
                logging.warning("Critical frequency range does not contain any of the frequency points used in best fit")

            df.loc[:, "mean"] = df.mean(axis=1, skipna=True)
            df.sort_values(by=["mean"], ascending=True, inplace=True)
            result_text = f"Reference curve name: '{ref_curve.get_full_name()}'"
            result_text += f"\nAmount of frequency points: {len(ref_freqs)}"
            result_text += "\n\n"
            result_text += tabulate(df[["mean"]], headers=("Item name", "Weighted average error"))

        return {"title": "Best fits", "result_text": result_text}

    def _interpolate_curves(self):
        curves = self.get_selected_curves(as_dict=True)

        to_insert = {}

        for i_curve, curve in curves.items():
            xy = signal_tools.interpolate_to_ppo(
                *curve.get_xy(), settings.processing_interpolation_ppo)

            new_curve = signal_tools.Curve(xy)
            new_curve.set_name_base(curves[i_curve].get_name_base())
            for suffix in curve.get_name_suffixes():
                new_curve.add_name_suffix(suffix)
            new_curve.add_name_suffix(
                f"interpolated to {settings.processing_interpolation_ppo} ppo")
            to_insert[i_curve + len(to_insert) + 1] = new_curve

        line2d_kwargs = {"color": "k", "linestyle": "-"}

        return {"to_insert": to_insert, "line2d_kwargs": line2d_kwargs}

    def _smoothen_curves(self):
        curves = self.get_selected_curves(as_dict=True)

        to_insert = {}

        for i_curve, curve in curves.items():

            if settings.smoothing_type == 0:
                xy = signal_tools.smooth_log_spaced_curve_butterworth_fast(*curve.get_xy(),
                                                                           bandwidth=settings.smoothing_bandwidth,
                                                                           resolution=settings.smoothing_resolution_ppo,
                                                                           order=8,
                                                                           )

            elif settings.smoothing_type == 1:
                xy = signal_tools.smooth_log_spaced_curve_butterworth_fast(*curve.get_xy(),
                                                                           bandwidth=settings.smoothing_bandwidth,
                                                                           resolution=settings.smoothing_resolution_ppo,
                                                                           order=4,
                                                                           )

            elif settings.smoothing_type == 2:
                xy = signal_tools.smooth_curve_rectangular_no_interpolation(*curve.get_xy(),
                                                                            bandwidth=settings.smoothing_bandwidth,
                                                                            )

            elif settings.smoothing_type == 3:
                xy = signal_tools.smooth_curve_gaussian(*curve.get_xy(),
                                                        bandwidth=settings.smoothing_bandwidth,
                                                        resolution=settings.smoothing_resolution_ppo,
                                                        )

            else:
                raise NotImplementedError(
                    "This smoothing type is not available")

            new_curve = signal_tools.Curve(xy)
            new_curve.set_name_base(curves[i_curve].get_name_base())
            for suffix in curve.get_name_suffixes():
                new_curve.add_name_suffix(suffix)
            new_curve.add_name_suffix(
                f"smoothed 1/{settings.smoothing_bandwidth}")
            to_insert[i_curve + len(to_insert) + 1] = new_curve

        line2d_kwargs = {"color": "k", "linestyle": "-"}

        return {"to_insert": to_insert, "line2d_kwargs": line2d_kwargs}

    def _open_settings_dialog(self):
        settings_dialog = SettingsDialog()
        settings_dialog.signal_settings_changed.connect(
            self._settings_dialog_return)

        return_value = settings_dialog.exec()
        if return_value:
            pass
            # self.signal_good_beep.emit()

    def _settings_dialog_return(self):
        #### What to do if matplotlib style changes ####
        self.signal_graph_settings_changed.emit()
        self.signal_update_graph_request.emit()

    def _load_clicked(self):
        pass

    def _save_clicked(self):
        pass


class ResultTextBox(qtw.QDialog):
    def __init__(self, title, result_text, parent=None):
        super().__init__(parent=parent)
        # self.setWindowModality(qtc.Qt.WindowModality.NonModal)

        layout = qtw.QVBoxLayout(self)
        self.setWindowTitle(title)
        self.setMinimumSize(900, 600)
        text_box = qtw.QTextEdit()
        text_box.setReadOnly(True)
        text_box.setText(result_text)

        font = text_box.font()
        font.setFamily("Monospace")
        text_box.setFont(font)

        layout.addWidget(text_box)

        # Buttons
        button_group = pwi.PushButtonGroup({"ok": "OK",
                                            },
                                           {},
                                           )
        button_group.buttons()["ok_pushbutton"].setDefault(True)
        layout.addWidget(button_group)
        
        # Connections
        button_group.buttons()["ok_pushbutton"].clicked.connect(
            self.accept)


class ProcessingDialog(qtw.QDialog):
    global settings
    signal_processing_request = qtc.Signal(str)

    def __init__(self, curves):
        super().__init__()
        self.setWindowModality(qtc.Qt.WindowModality.ApplicationModal)
        self.setWindowTitle("Processing Menu")
        layout = qtw.QVBoxLayout(self)
        self.tab_widget = qtw.QTabWidget()
        layout.addWidget(self.tab_widget)

        # dict of tuples. key is index of tab. value is tuple with (UserForm, name of function to use for its calculation)
        self.user_forms_and_recipient_functions = {}

        # Statistics page
        user_form_0 = pwi.UserForm()
        # tab page is the UserForm widget
        self.tab_widget.addTab(user_form_0, "Statistics")
        i = self.tab_widget.indexOf(user_form_0)
        self.user_forms_and_recipient_functions[i] = (
            user_form_0, "_mean_and_median_analysis")

        user_form_0.add_row(pwi.CheckBox("mean_selected",
                                         "Returns a curve showing the mean value of level in dB, per frequency point.",
                                         ),
                            "Calculate mean",
                            )

        user_form_0.add_row(pwi.CheckBox("median_selected",
                                         "Returns a curve showing the median value per frequency point.",
                                         ),
                            "Calculate median",
                            )

        # Smoothing page
        user_form_1 = pwi.UserForm()
        # tab page is the UserForm widget
        self.tab_widget.addTab(user_form_1, "Smoothing")
        i = self.tab_widget.indexOf(user_form_1)
        self.user_forms_and_recipient_functions[i] = (
            user_form_1, "_smoothen_curves")

        user_form_1.add_row(pwi.ComboBox("smoothing_type",
                                         None,
                                         [("Butterworth 8th, log spaced",),
                                          ("Butterworth 4th, log spaced",),
                                          ("Rectangular, w/o interpolation",),
                                          ("Gaussian, log spaced",),
                                          ]
                                         ),
                            "Type",
                            )
        # user_form_1._user_input_widgets["smoothing_type"].model().item(1).setEnabled(False)  # disable Klippel

        user_form_1.add_row(pwi.IntSpinBox("smoothing_resolution_ppo",
                                           "Parts per octave resolution for the operation"),
                            "Resolution (ppo)",
                            )
        user_form_1.add_row(pwi.IntSpinBox("smoothing_bandwidth",
                                           "Width of the frequency band in 1/octave."
                                           "\nFor Gaussion, bandwidth defines 2x the standard deviation of distribution."
                                           "\nFor Butterworth, bandwidth is the distance between critical frequencies, i.e. -3dB points for a first order filter.",
                                           ),
                            "Bandwidth (1/octave)",
                            )

        def set_availability_of_resolution_option(smoothing_type_index):
            available = True if smoothing_type_index in (0, 1, 3) else False
            user_form_1._user_input_widgets["smoothing_resolution_ppo"].setEnabled(
                available)

        user_form_1._user_input_widgets["smoothing_type"].currentIndexChanged.connect(
            set_availability_of_resolution_option)

        # Outlier detection page
        user_form_2 = pwi.UserForm()
        # tab page is the UserForm widget
        self.tab_widget.addTab(user_form_2, "Outliers")
        i = self.tab_widget.indexOf(user_form_2)
        self.user_forms_and_recipient_functions[i] = (
            user_form_2, "_outlier_detection")

        user_form_2.add_row(pwi.FloatSpinBox("outlier_fence_iqr",
                                             "Fence post for outlier detection using IQR method. Unit is the interquartile range of the data points for given frequency.",
                                             decimals=1,
                                             ),
                            "Outlier fence (IQR)",
                            )

        user_form_2.add_row(pwi.ComboBox("outlier_action",
                                         "Action to carry out on curves that fall partly or fully outside the fence.",
                                         [("None",),
                                          ("Hide",),
                                          ("Remove",),
                                          ]
                                         ),
                            "Action on outliers",
                            )

        # Interpolation page
        user_form_3 = pwi.UserForm()
        # tab page is the UserForm widget
        self.tab_widget.addTab(user_form_3, "Interpolation")
        i = self.tab_widget.indexOf(user_form_3)
        self.user_forms_and_recipient_functions[i] = (
            user_form_3, "_interpolate_curves")

        user_form_3.add_row(pwi.IntSpinBox("processing_interpolation_ppo",
                                           None,
                                           ),
                            "Points per octave",
                            )

        # Show best fits
        user_form_4 = pwi.UserForm()
        # tab page is the UserForm widget
        self.tab_widget.addTab(user_form_4, "Best fit to current")
        i = self.tab_widget.indexOf(user_form_4)
        self.user_forms_and_recipient_functions[i] = (
            user_form_4, "_show_best_fits")

        user_form_4.add_row(pwi.IntSpinBox("best_fit_calculation_resolution_ppo",
                                           "How many calculation points per octave to use for the calculation"
                                           " of the differences between the reference curve and the candidates."),
                            "Resolution (ppo)",
                            )

        user_form_4.add_row(pwi.IntSpinBox("best_fit_critical_range_start_freq",
                                           "Start frequency for range where weighing will be applied."),
                            "Critical range start (Hz)",
                            )

        user_form_4.add_row(pwi.IntSpinBox("best_fit_critical_range_end_freq",
                                           "End frequency for range where weighing will be applied."),
                            "Critical range end (Hz)",
                            )

        user_form_4.add_row(pwi.IntSpinBox("best_fit_critical_range_weight",
                                           "Multiplier to increase the weighting of the selected frequency range."
                                           "Setting to 1 means there will be no weighting."
                                           "Setting to 0 means the range will not be considered in the calculation"),
                            "Critical range weight",
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
        self.tab_widget.setCurrentIndex(settings.processing_selected_tab)
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
        button_group.buttons()["cancel_pushbutton"].clicked.connect(
            self.reject)
        button_group.buttons()["run_pushbutton"].clicked.connect(
            self._save_and_close)

    def _save_and_close(self):
        active_tab_index = self.tab_widget.currentIndex()
        user_form, processing_function_name = self.user_forms_and_recipient_functions[
            active_tab_index]
        settings.update_attr("processing_selected_tab",
                             self.tab_widget.currentIndex())

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
        self.signal_processing_request.emit(processing_function_name)
        self.accept()


class ImportDialog(qtw.QDialog):
    global settings
    signal_import_table_request = qtc.Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        # self.setWindowModality(qtc.Qt.WindowModality.ApplicationModal)
        layout = qtw.QVBoxLayout(self)
        self.setWindowTitle("Import table with curve(s)")

        # Form
        user_form = pwi.UserForm()
        layout.addWidget(user_form)

        user_form.add_row(pwi.ComboBox("import_table_layout_type",
                                       "Choose how the data is laid out in the raw imported data.",
                                       [("Headers are frequencies, indexes are names", 0),
                                        ("Indexes are frequencies, headers are names", 1),
                                        ],
                                       ),
                          "Layout type",
                          )

        user_form.add_row(pwi.IntSpinBox("import_table_no_line_headers",
                                         "Which line in the imported data contains the headers of the table."
                                         "\nHeaders correspond to column names in a spreadsheet; "
                                         "'1' means column A, '2' means column B and so on."
                                         "\n'0' means there is no header column in the import data."),
                          "Line number of headers",
                          )

        user_form.add_row(pwi.IntSpinBox("import_table_no_columns",
                                         "Which column in the imported data are the indexes."
                                         "\nIndexes correspond to row names in a spreadsheet."
                                         "\n'0' means there is no index column in the import data."),
                          "Column number of indexes",
                          )



        user_form.add_row(pwi.ComboBox("import_table_delimiter",
                                       "Delimiter character that separates the data into columns.",
                                       [(", (comma)", ","),
                                        ("; (semi-colon)", ";"),
                                        ("Tab", "\t"),
                                        ("Space", " "),
                                        ],
                                       ),
                          "Delimiter",
                          )

        user_form.add_row(pwi.ComboBox("import_table_decimal_separator",
                                       "Decimal separator. '.' as default."
                                       "Europe should use ',' officially but scientific community sticks to '.' as far as I understand.",
                                       [(". (dot)", "."),
                                        (", (comma)", ","),
                                        ],
                                       ),
                          "Decimal separator",
                          )

        # Buttons
        button_group = pwi.PushButtonGroup({"open_file": "Open file..",
                                            "read_clipboard": "Read clipboard",
                                            "close": "Close",
                                            },
                                           {},
                                           )
        button_group.buttons()["open_file_pushbutton"].setDefault(True)
        layout.addWidget(button_group)

        # read values from settings
        values_new = {}
        for key, widget in user_form._user_input_widgets.items():
            if isinstance(widget, qtw.QComboBox):
                values_new[key] = {"current_index": getattr(settings, key)}
            else:
                values_new[key] = getattr(settings, key)
        user_form.update_form_values(values_new)

        # Connections
        button_group.buttons()["close_pushbutton"].clicked.connect(self.reject)
        button_group.buttons()["open_file_pushbutton"].clicked.connect(partial(self._import_requested, "file", user_form))
        button_group.buttons()["read_clipboard_pushbutton"].clicked.connect(partial(self._import_requested, "clipboard", user_form))

    def _save_form_values_to_settings(self, user_form: pwi.UserForm):
        values = user_form.get_form_values()
        for widget_name, value in values.items():
            if isinstance(value, dict) and "current_index" in value.keys():
                settings.update_attr(widget_name, value["current_index"])
            else:
                settings.update_attr(widget_name, value)


    def _import_requested(self, source, user_form: pwi.UserForm):
        # Pass to easier names
        form_values = user_form.get_form_values()

        no_header = form_values["import_table_no_line_headers"]
        no_index =  form_values["import_table_no_columns"]
        
        layout_type_current_index = form_values["import_table_layout_type"]["current_index"]
        layout_type = form_values["import_table_layout_type"]["items"][layout_type_current_index][1]

        delimiter_current_index = form_values["import_table_delimiter"]["current_index"]
        delimiter = form_values["import_table_delimiter"]["items"][delimiter_current_index][1]

        decimal_separator_current_index = form_values["import_table_decimal_separator"]["current_index"]
        decimal_separator = form_values["import_table_decimal_separator"]["items"][decimal_separator_current_index][1]
        
        
        # Do validations
        if decimal_separator == delimiter:
            raise ValueError("Cannot have the same character for delimiter and decimal separator.")
        elif layout_type == 0 and no_header == 0:
            raise ValueError("Header line cannot be zero. Since you have selected"
                             " headers as frequencies, there needs to be a line for headers.")
        elif layout_type == 1 and no_index == 0:
            raise ValueError("Index column cannot be zero. Since you have selected"
                             " indexes as frequencies, there needs to be a column for indexes.")
        else:
            # Validations passed. Save settings.
            self._save_form_values_to_settings(user_form)
        
        user_settings = {}
        for key in ["no_header", "no_index", "layout_type", "delimiter", "decimal_separator"]:
            user_settings[key] = locals().get(key)
        
        self.signal_import_table_request.emit(source, user_settings)


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
                          "Nmax for graph legend")

        mpl_styles = [
            style_name for style_name in mpl.style.available if style_name[0] != "_"]
        user_form.add_row(pwi.ComboBox("matplotlib_style",
                                       "Style for the canvas. To see options, web search: 'matplotlib style sheets reference'",
                                       [(style_name, style_name)
                                        for style_name in mpl_styles],
                                       ),
                          "Matplotlib style",
                          )

        user_form.add_row(pwi.ComboBox("graph_grids",
                                       None,
                                       [("Style default", "default"),
                                        ("Major only", "major only"),
                                        ("Major and minor", "major and minor"),
                                        ],
                                       ),
                          "Graph grid view",
                          )

        user_form.add_row(pwi.SunkenLine())

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

        user_form.add_row(pwi.IntSpinBox("interpolate_must_contain_hz",
                                         "Frequency that will always be a point within interpolated frequency array."
                                         "\nDefault value: 1000",
                                         ),
                          "Interpolate must contain frequency (Hz)",
                          )

        user_form.add_row(pwi.SunkenLine())

        user_form.add_row(pwi.FloatSpinBox("A_beep",
                                           "Amplitude of the beep. Not in dB. 0 is off, 1 is maximum amplitude",
                                           min_max=(0, 1),
                                           ),
                          "Beep amplitude",
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
        for widget_name, widget in user_form._user_input_widgets.items():
            saved_setting = getattr(settings, widget_name)
            if isinstance(widget, qtw.QCheckBox):
                widget.setChecked(saved_setting)

            elif widget_name == "matplotlib_style":
                try:
                    index_from_settings = mpl_styles.index(saved_setting)
                except IndexError:
                    index_from_settings = 0
                widget.setCurrentIndex(index_from_settings)

            elif widget_name == "graph_grids":
                try:
                    index_from_settings = [widget.itemData(i) for i in range(
                        widget.count())].index(settings.graph_grids)
                except IndexError:
                    index_from_settings = 0
                widget.setCurrentIndex(index_from_settings)

            else:
                widget.setValue(saved_setting)

        # Connections
        button_group.buttons()["cancel_pushbutton"].clicked.connect(
            self.reject)
        button_group.buttons()["save_pushbutton"].clicked.connect(
            partial(self._save_and_close,  user_form._user_input_widgets, settings))

    def _save_and_close(self, user_input_widgets, settings):
        mpl_styles = [
            style_name for style_name in mpl.style.available if style_name[0] != "_"]
        if user_input_widgets["matplotlib_style"].currentIndex() != mpl_styles.index(settings.matplotlib_style):
            message_box = qtw.QMessageBox(qtw.QMessageBox.Information,
                                          "Information",
                                          "Application needs to be restarted to be able to use the new Matplotlib style.",
                                          )
            message_box.setStandardButtons(
                qtw.QMessageBox.Cancel | qtw.QMessageBox.Ok)
            returned = message_box.exec()

            if returned == qtw.QMessageBox.Cancel:
                return

        for widget_name, widget in user_input_widgets.items():
            if isinstance(widget, qtw.QCheckBox):
                settings.update_attr(widget_name, widget.isChecked())
            elif widget_name == "matplotlib_style":
                settings.update_attr(widget_name, widget.currentData())
            elif widget_name == "graph_grids":
                settings.update_attr(widget_name, widget.currentData())
            else:
                settings.update_attr(widget_name, widget.value())
        self.signal_settings_changed.emit()
        self.accept()


class AutoImporter(qtc.QThread):
    global settings
    signal_new_import = qtc.Signal(signal_tools.Curve)

    def __init__(self):
        super().__init__()

    def run(self):
        while not self.isInterruptionRequested():
            cb_data = pyperclip.waitForNewPaste()
            # print("\nClipboard read:" + "\n" + str(type(cb_data)) + "\n" + cb_data)
            try:
                new_curve = signal_tools.Curve(cb_data)
                if new_curve.is_curve():
                    self.signal_new_import.emit(new_curve)
            except Exception as e:
                logging.warning(e)


def main():
    global settings

    if not (app := qtw.QApplication.instance()):
        app = qtw.QApplication(sys.argv)
        # there is a new recommendation with qApp but how to dod the sys.argv with that?

    settings = pwi.Settings()
    error_handler = pwi.ErrorHandlerDeveloper(app)
    sys.excepthook = error_handler.excepthook
    mw = CurveAnalyze()
    mw.setWindowTitle("Linecraft Qt - {}".format(version))

    sound_engine = pwi.SoundEngine(settings)
    sound_engine_thread = qtc.QThread()
    sound_engine.moveToThread(sound_engine_thread)
    sound_engine_thread.start(qtc.QThread.HighPriority)
    mw.signal_bad_beep.connect(sound_engine.bad_beep)
    mw.signal_good_beep.connect(sound_engine.good_beep)

    # mw._add_single_curve(None, signal_tools.Curve(
    #     np.array([[125, 250, 500], [50, 50, 50]])))
    # mw._add_single_curve(None, signal_tools.Curve(
    #     np.array([[125, 250, 500], [70, 85, 70]])))
    # mw._add_single_curve(None, signal_tools.Curve(
    #     np.array([[125, 250, 500], [75, 70, 80]])))
    # mw._add_single_curve(None, signal_tools.Curve(
    #     np.array([[125, 250, 500], [60, 75, 90]])))
    # mw._add_single_curve(None, signal_tools.Curve(
    #     np.array([[125, 250, 500], [90, 70, 65]])))
    # mw._add_single_curve(None, signal_tools.Curve(
    #     np.array([[125, 250, 500], [85, 80, 80]])))
    # mw._add_single_curve(None, signal_tools.Curve(
    #     np.array([[125, 250, 500], [70, 70, 80]])))
    # mw._add_single_curve(None, signal_tools.Curve(
    #     np.array([[125, 250, 500], [60, 70, 90]])))
    # mw._add_single_curve(None, signal_tools.Curve(
    #     np.array([[125, 250, 500], [90, 70, 60]])))
    # mw._add_single_curve(None, signal_tools.Curve(
    #     np.array([[125, 250, 500], [20, 70, 60]])))
    # mw._add_single_curve(None, signal_tools.Curve(
    #     np.array([[125, 250, 500], [90, 70, 160]])))

    # mw._add_single_curve(None, signal_tools.Curve(np.array([[0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512],
    #                                                   [55, 90, 80, 90, 80, 90, 100, 100, 100, 80, 90],
    #                                                   ])))

    mw.show()
    app.exec()


if __name__ == "__main__":
    main()
