import dataclasses

from PySide6 import QtWidgets as qtw

from gui.input_section_tab_widget import InputSectionTabWidget


def update_coil_options_combobox(combo_box: qtw.QComboBox, input_form_tabbed: InputSectionTabWidget, name_to_motor: dict):
    try:
        last_selected = (
            combo_box.currentData()["coil"]["wire"]["name"],
            len(combo_box.currentData()["coil"]["N_windings"]),
            )
    except (KeyError, AttributeError, TypeError):
        last_selected = (None, None)

    combo_box.clear()

    index_to_select = -1
    # Add the coils to the combobox (with their userData)
    for i, (name, motor) in enumerate(name_to_motor.items()):
        # Make a string for the text to show on the combo box
        combo_box.addItem(name, dataclasses.asdict(motor))
        if motor.coil.get_wire_name_and_layers() == last_selected:
            index_to_select = i

    combo_box.setCurrentIndex(index_to_select)

    # if nothing to add to combobox
    if combo_box.count() == 0:
        combo_box.addItem("--no solution found--")
    elif index_to_select == -1:  # means a new coil needs to be selected by user
        input_form_tabbed.setCurrentIndex(1)
        combo_box.showPopup()
