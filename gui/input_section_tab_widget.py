import os
import logging

from PySide6 import QtWidgets as qtw
from PySide6 import QtCore as qtc
from PySide6 import QtGui as qtg

import generictools.personalized_widgets as pwi

logger = logging.getLogger(__name__)


class InputSectionTabWidget(qtw.QTabWidget):
    signal_good_beep = qtc.Signal()
    signal_bad_beep = qtc.Signal()
    signal_file_dropped = qtc.Signal(str)

    TAB_NAMES = ("General", "Motor", "Enclosure", "System")

    def __init__(self):
        super().__init__()
        self.interactable_widgets = {}
        self._add_form_tabs()
        self.setAcceptDrops(True)

    def _add_form_tabs(self):
        forms = (
            self._make_form_for_general_tab(),
            self._make_form_for_motor_tab(),
            self._make_form_for_enclosure_tab(),
            self._make_form_for_system_tab(),
        )
        for tab_name, form in zip(self.TAB_NAMES, forms, strict=True):
            self.addTab(form, tab_name)
            self.interactable_widgets.update(form.interactable_widgets)

    def dragEnterEvent(self, event: qtg.QDragEnterEvent):
        """Accept file drag event if it contains URLs (files)."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: qtg.QDropEvent):
        """Handle file drop event and load file contents."""
        mime_data = event.mimeData()
        urls = mime_data.urls()
        if not urls:
            return

        paths = [url.toLocalFile().removesuffix("/") for url in urls]
        if os.name == "nt":
            paths = [path.removesuffix("/") for path in paths]

        for path in paths:
            logger.info(f"User dropped file '{path}' onto InputSectionTabWidget.")
            self.signal_file_dropped.emit(path)

    def _make_form_for_general_tab(self):
        form = pwi.UserForm()

        # ---- General specs
        form.add_row(pwi.Title("General specifications"))

        form.add_row(pwi.FloatSpinBox("fs",
                                      "Free-air resonance of the driver: the undamped natural frequency"
                                      "\nwhere moving mass and suspension stiffness cancel (f<sub>s</sub> = √(K<sub>ms</sub>/M<sub>ms</sub>)/2π)."
                                      "\nNote this is not the damped natural (ringing) frequency, nor the"
                                      "\nfrequency of the response peak; those sit lower and depend on damping."
                                      "\nUnit is Hertz.",
                                      decimals=1,
                                      min_max=(0.1, None),
                                      ),
                     description="f<sub>s</sub>",
                     )

        form.add_row(pwi.FloatSpinBox("Qms",
                                      "Quality factor of speaker, only the mechanical part."
                                      "\nUnitless quantity.",
                                      ),
                     description="Q<sub>ms</sub>",
                     )

        form.add_row(pwi.FloatSpinBox("Xpeak",
                                      "Peak excursion allowed, one way."
                                      "\nUnit is millimeter.",
                                      coeff_for_SI=1e-3,
                                      ),
                     description="X<sub>peak</sub>",
                     )

        form.add_row(pwi.FloatSpinBox("dead_mass", "Moving mass excluding the coil windings and the air load on the diaphragm."
                                                   "\n'Dead mass = Mmd - coil winding mass'"
                                                   "\nUnit is gram.",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Dead mass",
                     )

        form.add_row(pwi.FloatSpinBox("Sd",
                                      "Diaphragm effective surface area.\nUse a value of '0' if there is no diaphragm, e.g. a shaker."
                                      "Unit is cm².",
                                      coeff_for_SI=1e-4,
                                      min_max=(0, None),
                                      ),
                     description="S<sub>d</sub>"
                     )

        # ---- Electrical input
        form.add_row(pwi.SunkenLine())

        form.add_row(pwi.Title("Electrical Input"))


        form.add_row(pwi.ComboBox("excitation_type", "Choose which type of input excitation you want to define.",
                                  [("Volts", "V"),
                                   ("Watts @Re", "W"),
                                      ("Watts @Rnom", "Wn")
                                   ],
                                  ),
                     description="Unit",
                     )

        form.add_row(pwi.FloatSpinBox("excitation_value", "The value for input excitation.\nUnit is as chosen above.",
                                      ),
                     description="Value",
                     )

        form.add_row(pwi.FloatSpinBox("Rnom", "Nominal impedance of the system. This is necessary to calculate the voltage applied to the system"
                                      "\nwhen 'Watts @Rnom' is selected as the input excitation unit."
                                      "\nUnit is ohm.",
                                      ),
                     description="Nominal impedance",
                     )

        form.add_row(pwi.FloatSpinBox("Rext",
                                      "The resistance between the speaker terminal and the voltage source."
                                      "\nMay be due to cables in our outside the speaker housing, connectors, amplifier internals etc."
                                      "\nCauses resistive loss of voltage appearing at speaker terminals."
                                      "\nUnit is ohm.",
                                      min_max=(0, None),
                                      ),
                     description="External resistance",
                     )

        # ---- Form logic
        def adjust_form_for_excitation_type(chosen_index):
            is_Wn = \
                form.interactable_widgets["excitation_type"].itemData(chosen_index) == "Wn"
            form.interactable_widgets["Rnom"].setEnabled(is_Wn)

        form.interactable_widgets["excitation_type"].currentIndexChanged.connect(adjust_form_for_excitation_type)
        # adjustment at start
        adjust_form_for_excitation_type(form.interactable_widgets["excitation_type"].currentIndex())

        return form

    def _make_form_for_motor_tab(self):
        form = pwi.UserForm()

        # Motor spec type
        form.add_row(pwi.ComboBox("motor_spec_type",
                                  "Choose which parameters you want to provide to make a motor definition.",
                                  [("Define Coil Dimensions and Average B", "define_coil"),
                                   ("Define Bl, Re, Mmd", "define_Bl_Re_Mmd"),
                                   ("Define Bl, Re, Mms", "define_Bl_Re_Mms"),
                                   ],
                                  ))
        form.interactable_widgets["motor_spec_type"].setStyleSheet(
            "font-weight: bold")

        # Stacked widget for different motor definition types
        form.motor_definition_stacked = qtw.QStackedWidget()
        form.motor_definition_stacked.setSizePolicy(qtw.QSizePolicy.Preferred, qtw.QSizePolicy.Maximum)
        # expands and pushes the next form rows down if I don't do the above line
        form.interactable_widgets["motor_spec_type"].currentIndexChanged.connect(
            form.motor_definition_stacked.setCurrentIndex)

        form.add_row(form.motor_definition_stacked)

        # ---- First page: "Define Coil Dimensions and Average B"
        motor_definition_p1 = pwi.SubForm()
        form.motor_definition_stacked.addWidget(motor_definition_p1)

        form.add_row(pwi.FloatSpinBox("target_Re",
                                      "Desired Re value. Wire type and number of windings will be "
                                      "calculated so as to best approach this value."
                                      "\nUnit is ohm.",
                                      ),
                     description="Target R<sub>e</sub>",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.FloatSpinBox("former_ID",
                                      "Internal diameter of the coil former."
                                      "\nUnit is millimeter.",
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Coil former ID",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.IntSpinBox("t_former",
                                    "Thickness of the coil former."
                                    "\nUnit is micrometer (\u03BCm).",
                                    coeff_for_SI=1e-6,
                                      min_max=(0, None)
                                    ),
                     description="Former thickness",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.FloatSpinBox("h_winding_target",
                                      "Desired height of the coil winding."
                                      "\nUnit is millimeter.",
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Target winding height",
                     into_form=motor_definition_p1,
                     )


        form.add_row(pwi.FloatSpinBox("B_average",
                                      "Average of radial magnetic field across the coil winding."
                                      "\nNeeds to be calculated separately and input here."
                                      "\nE.g. a value of '0.9' would mean that a winding with a wire "
                                      "that is 5m long will have a Bl of 4.5Tm."
                                      "\nUnit is Tesla.",
                                      decimals=3,
                                      coeff_for_SI=1,
                                      min_max=(0, None),
                                      ),
                     description="Average B on coil",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.LineTextBox("N_layer_options", "Enter the number of winding layer options that are accepted."
                                     "\nUse integers with a comma in between, e.g.: '2, 4'",
                                     ),
                     description="Number of layer options",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.FloatSpinBox("w_stacking_coef",
                                      "Stacking coefficient for additional winding layers put on."
                                      "Applies only on thickness. For height, only the average height of the wire is used and this has no effect."
                                      "\nE.g. if this is set to 0.8 and the average wire thickness is 1mm,"
                                      "\nthickness of a winding that has 3 layers will be"
                                      "\n 1 + 0.8 + 0.8 = 2.6mm. (applies not on first layer but consecutive layers only)"
                                      "\nFor stacking of ideally circular wires this value is 'sin(60)=0.5'.",
                                      min_max=(0, 1.99),
                                      ),
                     description="Stacking coefficient",
                     into_form=motor_definition_p1,
                     )
        form.interactable_widgets["w_stacking_coef"].setValue(1)

        form.add_row(pwi.FloatSpinBox("Rlw",
                                      "Resistance between the coil and the speaker terminals, e.g. leadwire"
                                      "\nUnit is ohm.",
                                      min_max=(0, None),
                                      # took the automatically assigned maximum from another widget
                                      # instead of typing n an arbitrary number
                                      # 'None' was not expected by the underlying 'setRange' method
                                      ),
                     description="Leadwire resistance",
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.FloatSpinBox("reduce_per_layer",
                                    ("Reduce the number of windings on each consecutive winding layer by this number."
                                     "\nFor round coils suggested value is 1.5. For rectangular coils suggested value is 0.5."),
                                      min_max=(0, None),
                                      decimals=2,
                                    ),
                     description="Reduce windings per layer",
                     into_form=motor_definition_p1,
                     )


        update_coil_choices_button = pwi.PushButton("update_coil_choices",
                                                    "Update coil choices",
                                                    tooltip="Populate the below dropdown with possible coil choices based on given parameters.",
                                                    )

        form.add_row(update_coil_choices_button,
                     into_form=motor_definition_p1,
                     )

        form.add_row(pwi.ComboBox("coil_options", "Select coil winding to be used for calculations.",
                                  [],
                                  ),
                     into_form=motor_definition_p1,
                     )

        # ---- Second page: "Define Bl, Re, Mmd"
        motor_definition_p2 = pwi.SubForm()
        form.motor_definition_stacked.addWidget(motor_definition_p2)

        form.add_row(pwi.FloatSpinBox("Bl_p2",
                                      "Force factor"
                                      "\nUnit is Tesla meter.",
                                      ),
                     description="Bl",
                     into_form=motor_definition_p2,
                     )

        form.add_row(pwi.FloatSpinBox("Re_p2",
                                      "DC resistance"
                                      "\nUnit is ohm.",
                                    ),
                     description="R<sub>e</sub>",
                     into_form=motor_definition_p2,
                     )

        form.add_row(pwi.FloatSpinBox("Mmd_p2",
                                      "Moving mass, excluding coupled air mass"
                                      "\nUnit is gram.",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="M<sub>md</sub>",
                     into_form=motor_definition_p2,
                     )

        # ---- Third page: "Define Bl, Re, Mms"
        motor_definition_p3 = pwi.SubForm()
        form.motor_definition_stacked.addWidget(motor_definition_p3)

        form.add_row(pwi.FloatSpinBox("Bl_p3",
                                      "Force factor"
                                      "\nUnit is Tesla meter.",
                                      ),
                     description="Bl",
                     into_form=motor_definition_p3,
                     )

        form.add_row(pwi.FloatSpinBox("Re_p3",
                                      "DC resistance"
                                      "\nUnit is ohm.",
                                    ),
                     description="R<sub>e</sub>",
                     into_form=motor_definition_p3,
                     )

        form.add_row(pwi.FloatSpinBox("Mms_p3",
                                      "Moving mass, including coupled air mass"
                                      "\nUnit is gram.",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="M<sub>ms</sub>",
                     into_form=motor_definition_p3,
                     )

        # ---- Mechanical specs
        form.add_row(pwi.SunkenLine())

        form.add_row(pwi.Title("Motor mechanical specifications"))

        form.add_row(pwi.FloatSpinBox("h_top_plate",
                                      "Thickness of the top plate."
                                      "\nUnit is millimeter.",
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Top plate thickness",
                     )

        form.add_row(pwi.IntSpinBox("airgap_clearance_inner",
                                    "Clearance on the inner side of the coil former."
                                    "\nUnit is micrometer (\u03BCm).",
                                    coeff_for_SI=1e-6,
                                    ),
                     description="Airgap inner clearance",
                     )

        form.add_row(pwi.IntSpinBox("airgap_clearance_outer",
                                    "Clearance on the outer side of the coil windings."
                                    "\nUnit is micrometer (\u03BCm).",
                                    coeff_for_SI=1e-6,
                                    ),
                     description="Airgap outer clearance",
                     )

        form.add_row(pwi.FloatSpinBox("h_former_under_coil",
                                      "Extension of the coil former below the coil windings."
                                      "\nUnit is millimeter.",
                                      coeff_for_SI=1e-3,
                                      min_max=(0, None),
                                      ),
                     description="Former bottom ext.",
                     )

        # spacer = qtw.QSpacerItem(0, 0, qtw.QSizePolicy.Minimum, qtw.QSizePolicy.MinimumExpanding)
        # form.add_row(spacer)

        # ---- Form logic
        def adjust_form_for_motor_calc_type(chosen_index):
            is_define_coil = form.interactable_widgets["motor_spec_type"].itemData(chosen_index) == "define_coil"
            form.interactable_widgets["h_top_plate"].setEnabled(is_define_coil)
            form.interactable_widgets["airgap_clearance_inner"].setEnabled(is_define_coil)
            form.interactable_widgets["airgap_clearance_outer"].setEnabled(is_define_coil)
            form.interactable_widgets["h_former_under_coil"].setEnabled(is_define_coil)
            self.widget(0).interactable_widgets["dead_mass"].setEnabled(is_define_coil)

        form.interactable_widgets["motor_spec_type"].currentIndexChanged.connect(adjust_form_for_motor_calc_type)

        return form

    def _make_form_for_enclosure_tab(self):
        form = pwi.UserForm()

        # ---- Enclosure type
        form.add_row(pwi.Title("Enclosure type"))

        enclosue_type_choice_buttons = pwi.ChoiceButtonGroup("enclosure_type",
                                                        {0: "Free-air", 1: "Closed box", 2: "PR/Vented",},
                                                        {0: "Speaker assumed to be on an infinite baffle, with no acoustical loading on either side",
                                                         1: "Speaker rear side coupled to a sealed enclosure.",
                                                         2: "Speaker rear side coupled to an enclosure with a passive radiator or a bass-reflex vent.",
                                                         },
                                                        vertical=False,
                                                        )

        enclosue_type_choice_buttons.layout().setContentsMargins(0, 0, 0, 0)
        form.add_row(enclosue_type_choice_buttons)

        # ---- Closed box specs
        form.add_row(pwi.SunkenLine())

        form.add_row(pwi.Title("Closed box specifications"))

        form.add_row(pwi.FloatSpinBox("Vb",
                                      "Internal volume filled by air."
                                      "\nFor vented calculations, the air in the vent is included in this value."
                                      "\nUnit is liter.",
                                      decimals=3,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Net internal volume",
                     )

        form.add_row(pwi.FloatSpinBox("Qa",
                                      "Quality factor of the speaker in enclosure resulting from absorption losses inside the enclosure."
                                      "\nCalculated at f<sub>b</sub>."
                                      "\nUnitless quantity.",
                                      decimals=1,
                                      min_max=(0.1, None),
                                      ),
                     description="Q<sub>a</sub> - internal absorption",
                     )

        form.add_row(pwi.FloatSpinBox("Ql",
                                      "Quality factor of the speaker in enclosure resulting from leakage losses of the enclosure."
                                      "\nCalculated at f<sub>b</sub>."
                                      "\nSet a high value for a well-sealed box (no leakage)."
                                      "\nUnitless quantity.",
                                      decimals=1,
                                      min_max=(0.1, None),
                                      ),
                     description="Q<sub>l</sub> - leakage losses",
                     )

        # ---- PR/vent
        form.add_row(pwi.SunkenLine())

        form.add_row(pwi.Title("PR/Vented specifications"))

        form.add_row(pwi.ComboBox("dir_pr_vent",
                                  "Mounting orientation of the passive radiator (or reflex vent) relative"
                                  "\nto the driver."
                                  "\n'Same with driver': the radiator faces the same way as the driver,"
                                  "\nso their reaction forces on the cabinet add up."
                                  "\n'On opposite direction': the radiator is mounted facing the opposite"
                                  "\nway (opposed / force-cancelling), so its reaction force partly cancels"
                                  "\nthe driver's cabinet vibration.",
                                  [("Same with driver", 1),
                                   ("On opposite direction", -1),
                                   ],
                                  ),
                     description="Mounting orientation",
                     )

        form.add_row(pwi.FloatSpinBox("h_pr",
                                      "Ratio of the passive radiator's free-air resonance f<sub>p</sub> to the"
                                      "\ndriver's sealed-box resonance f<sub>b</sub>."
                                      "\nf<sub>p</sub> sets the notch in the system response."
                                      "\nValues below 1 place the notch below the sealed-box resonance."
                                      "\nUnitless quantity.",
                                      decimals=3,
                                      min_max=(0.1, None),
                                      ),
                     description="h - ratio (f<sub>p</sub> / f<sub>b</sub>)",
                     )

        # Resonator spec type
        form.add_row(pwi.ComboBox("resonator_spec_type",
                                  "Choose the type of resonator and which parameters to use to set it up.",
                                  [("PR - Define mass and damping ratio", "pr_1"),
                                        ("Bass reflex - Define port and Q", "br_1"),
                                   ],
                                  ))
        form.interactable_widgets["resonator_spec_type"].setStyleSheet(
            "font-weight: bold")

        # Stacked widget for different motor definition types
        form.resonator_definition_stacked = qtw.QStackedWidget()
        form.resonator_definition_stacked.setSizePolicy(qtw.QSizePolicy.Preferred, qtw.QSizePolicy.Maximum)
        # expands and pushes the next form rows down if I don't do the above line
        form.interactable_widgets["resonator_spec_type"].currentIndexChanged.connect(
            form.resonator_definition_stacked.setCurrentIndex)

        form.add_row(form.resonator_definition_stacked)

        # ---- First page: "Define PR"
        resonator_definition_pr1 = pwi.SubForm()
        form.resonator_definition_stacked.addWidget(resonator_definition_pr1)

        form.add_row(pwi.FloatSpinBox("area_ratio_pr",
                                      "Ratio of the passive radiator's surface area S<sub>p</sub>"
                                      "\nto the driver's surface area S<sub>d</sub>."
                                      "\nUnitless quantity.",
                                      decimals=2,
                                      min_max=(0.1, None),
                                      ),
                     description="Area ratio (S<sub>p</sub> / S<sub>d</sub>)",
                     into_form=resonator_definition_pr1
                     )

        form.add_row(pwi.FloatSpinBox("Mmdp",
                                      "Moving mass of the passive radiator, excluding the coupled air load."
                                      "\nUnit is gram.",
                                      decimals=2,
                                      coeff_for_SI=1e-3,
                                      ),
                     description="M<sub>md,p</sub> - moving mass (excl. air)",
                     into_form=resonator_definition_pr1
                     )

        form.add_row(pwi.FloatSpinBox("spring_damping_ratio_pr",
                                      "Ratio of the passive radiator's mechanical damping R<sub>p</sub>"
                                      "\nto its suspension stiffness K<sub>p</sub>."
                                      "\nUnit is seconds.",
                                      decimals=4,
                                      ),
                     description="Spring damping ratio (R<sub>p</sub> / K<sub>p</sub>)",
                     into_form=resonator_definition_pr1
                     )

        # ---- Second page: "Bass reflex"
        # A reflex vent is modelled as the same third degree of freedom as the
        # passive radiator, but with zero suspension stiffness (the air plug in the
        # tube has no restoring force of its own). It therefore reuses h_pr (=fp/fb)
        # and dir_pr_vent, and only needs the port-specific inputs below.
        resonator_definition_br1 = pwi.SubForm()
        form.resonator_definition_stacked.addWidget(resonator_definition_br1)

        form.add_row(pwi.FloatSpinBox("port_diameter",
                                      "Internal diameter of the reflex port (vent)."
                                      "\nSets the port cross-sectional area S<sub>v</sub> = π/4 · D<sub>v</sub>²."
                                      "\nLarger diameters lower the port air velocity (less chuffing)"
                                      "\nbut require a longer tube for the same tuning."
                                      "\nUnit is mm.",
                                      decimals=1,
                                      min_max=(0.1, None),
                                      coeff_for_SI=1e-3,
                                      ),
                     description="D<sub>v</sub> - port diameter",
                     into_form=resonator_definition_br1,
                     )

        form.add_row(pwi.FloatSpinBox("Qp",
                                      "Quality factor of the reflex port at the tuning frequency,"
                                      "\ncapturing the vent losses (turbulence, friction, leakage)."
                                      "\nHigher values mean a lower-loss, more sharply tuned port."
                                      "\nUnitless quantity.",
                                      decimals=1,
                                      min_max=(0.1, None),
                                      ),
                     description="Q<sub>p</sub> - port quality factor",
                     into_form=resonator_definition_br1,
                     )

        # End-correction coefficient k, expressed as a multiple of the port
        # diameter D_v: the total effective-length addition is k * D_v (sum of both
        # ends). Used only to convert the required acoustic mass into a physical
        # tube length for reporting -- it does not enter the acoustic model.
        # Classic values (Dickason): both ends flanged 0.850, one end flanged 0.732,
        # both ends free 0.614.
        form.add_row(pwi.ComboBox("exit_flare_type",
                                  "Termination geometry of the port ends, which sets the acoustic"
                                  "\nend correction used to compute the physical port length."
                                  "\nThe correction added to the tube length is k &middot; D<sub>v</sub>,"
                                  "\nwhere k depends on how each end is terminated.",
                                  [("Both ends flanged / flared", 0.850),
                                   ("One end flanged, one free", 0.732),
                                   ("Both ends free", 0.614),
                                   ],
                                  ),
                     description="Exit flare type",
                     into_form=resonator_definition_br1,
                     )


        # ---- Form logic
        # All resonator inputs are active only for the PR/Vented enclosure. The
        # resonator_definition_stacked widget already shows just the page for the
        # selected resonator_spec_type (PR vs bass reflex), so the enable state only
        # needs to follow the enclosure type; the shared inputs (dir_pr_vent, h_pr)
        # serve both the passive radiator and the vent.
        resonator_widget_keys = ("dir_pr_vent", "h_pr", "resonator_spec_type",
                                  "spring_damping_ratio_pr", "area_ratio_pr", "Mmdp",  # PR page
                                  "port_diameter", "Qp", "exit_flare_type",            # bass reflex page
                                  )

        def adjust_form_for_enclosure_type(*_):
            enclosure_type = form.interactable_widgets["enclosure_type"].checkedId()
            has_box = enclosure_type in (1, 2)  # closed box or PR/vented
            has_resonator = enclosure_type == 2

            form.interactable_widgets["Vb"].setEnabled(has_box)
            form.interactable_widgets["Qa"].setEnabled(has_box)
            form.interactable_widgets["Ql"].setEnabled(has_box)
            for key in resonator_widget_keys:
                form.interactable_widgets[key].setEnabled(has_resonator)

        form.interactable_widgets["enclosure_type"].idToggled.connect(adjust_form_for_enclosure_type)
        # adjustment at start
        adjust_form_for_enclosure_type()

        return form

    def _make_form_for_system_tab(self):
        form = pwi.UserForm()

        # ---- System type
        form.add_row(pwi.Title("Parent body"))

        dof_choice_buttons = pwi.ChoiceButtonGroup("parent_body",
                                                   {0: "Rigid", 1: "Mobile"},
                                                   {0: "1 degree of freedom - only the loudspeaker moving mass has mobility.",
                                                    1: "2 degrees of freedom - loudspeaker moving mass is attached to a parent lump mass that also has mobility."
                                                    },
                                                   vertical=False,
                                                   )
        dof_choice_buttons.layout().setContentsMargins(0, 0, 0, 0)
        form.add_row(dof_choice_buttons)

        # ---- Parent body

        form.add_row(pwi.FloatSpinBox("mpb",
                                      "Mass of the parent body."
                                      "\nUnit is gram.",
                                      min_max=(0.1, 999999),
                                      coeff_for_SI=1e-3,
                                      ),
                     description="Mass",
                     )

        form.add_row(pwi.FloatSpinBox("kpb",
                                      "Stiffness between the parent body and the reference frame."
                                      "\nUnit is Newtons per millimeter.",
                                      coeff_for_SI=1e3,
                                      ),
                     description="Stiffness",
                     )


        form.add_row(pwi.FloatSpinBox("rpb",
                                      "Damping coefficient between the parent body and the reference frame."
                                      "\nUnit is kilograms per second.",
                                      ),
                     description="Damping coefficient",
                     )

        # ---- Form logic
        def adjust_form_for_system_type(toggled_id, checked):
            form.interactable_widgets["kpb"].setEnabled(toggled_id == 1 and checked is True)
            form.interactable_widgets["mpb"].setEnabled(toggled_id == 1 and checked is True)
            form.interactable_widgets["rpb"].setEnabled(toggled_id == 1 and checked is True)

        form.interactable_widgets["parent_body"].idToggled.connect(adjust_form_for_system_type)
        # adjustment at start
        adjust_form_for_system_type(0, True)

        return form
