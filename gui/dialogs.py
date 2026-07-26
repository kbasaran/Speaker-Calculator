from functools import partial

from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc

import generictools.personalized_widgets as pwi

import matplotlib as mpl

from config.app_config import singleton_settings

app_settings = singleton_settings()


class CurveExportMenu(qtw.QMenu):
    def __init__(self, curves, position, parent):
        super().__init__(parent=parent)
        for curve in curves:
            self.addAction(curve.get_full_name(), partial(self._export_and_beep, curve, self.parent().signal_good_beep))
        self.popup(position)

    @staticmethod
    def _export_and_beep(curve, good_beeper):
        curve.export_to_clipboard(ppo=app_settings.get_value("export_ppo"), must_include_freq=app_settings.get_value("interpolate_must_contain_hz"))
        good_beeper.emit()


class SettingsDialog(qtw.QDialog):

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowModality(qtc.Qt.WindowModality.ApplicationModal)
        layout = qtw.QVBoxLayout(self)

        # ---- Form
        user_form = pwi.UserForm()
        layout.addWidget(user_form)

        # user_form.add_row(pwi.IntSpinBox("max_legend_size", "Limit the items that can be listed on the legend. Does not affect the shown curves in graph"),
        #                   "Nmax for graph legend")

        mpl_styles = [
            style_name for style_name in mpl.style.available if style_name[0] != "_"]
        user_form.add_row(pwi.ComboBox("matplotlib_style",
                                       "Style for the canvas. To see options, web search: 'matplotlib style sheets reference'",
                                       [(style_name, None)
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

        user_form.add_row(pwi.FloatSpinBox("A_beep",
                                           "Amplitude of the beep. Not in dB. 0 is off, 1 is maximum amplitude",
                                           min_max=(0, 1),
                                           ),
                          "Beep amplitude",
                          )

        user_form.add_row(pwi.SunkenLine())

        user_form.add_row(pwi.IntSpinBox("export_ppo",
                                         "Resolution of the exported curve in points per octave",
                                         min_max=(1, app_settings.get_value("calc_ppo")),
                                         ),
                          "Export curve resolution (ppo)",
                          )


        user_form.add_row(pwi.IntSpinBox("interpolate_must_contain_hz",
                                         "Frequency that will always be a point within interpolated frequency array."
                                         "\nDefault value: 1000",
                                         min_max=(1, 999999),
                                         ),
                          "Interpolate must contain frequency (Hz)",
                          )

        # ---- Buttons
        button_group = pwi.PushButtonGroup({"save": "Save",
                                            "cancel": "Cancel",
                                            },
                                           {},
                                           )
        button_group.buttons()["save_pushbutton"].setDefault(True)
        layout.addWidget(button_group)

        # ---- read values from settings
        all_app_settings = app_settings.get_all_as_dict()
        app_settings_in_form = {key: all_app_settings[key] for key in user_form.interactable_widgets.keys()}
        user_form.update_complete_form(app_settings_in_form)

        # Connections
        button_group.buttons()["cancel_pushbutton"].clicked.connect(
            self.reject)
        button_group.buttons()["save_pushbutton"].clicked.connect(
            partial(self._save_and_close,  user_form))

    def _save_and_close(self, user_form):
        vals = user_form.get_form_values()
        if vals["matplotlib_style"]["current_text"] != app_settings.get_value("matplotlib_style"):
            message_box = qtw.QMessageBox(qtw.QMessageBox.Information,
                                          "Information",
                                          "Application needs to be restarted to be able to use the new Matplotlib style.",
                                          )
            message_box.setStandardButtons(
                qtw.QMessageBox.Cancel | qtw.QMessageBox.Ok)
            returned = message_box.exec()

            if returned == qtw.QMessageBox.Cancel:
                return

        for widget_name, value in vals.items():
            app_settings.set_value(widget_name, value, signal=False)

        app_settings.settings_changed.emit()
        self.accept()
