"""Tests for several identical drivers in one system (n_speaker / coupling).

Run from the repository root:
    python -m unittest tests.test_speaker_array
"""

import copy
import unittest

import numpy as np

from core.components import Enclosure
from core.factories import _driver_sealed_fb, construct_PassiveRadiator
from core.speaker_driver import SpeakerDriver
from core.speaker_system import SpeakerSystem
from utils.version_convert import V08_NEW_KEY_DEFAULTS, convert_v07_to_v08

FREQS = np.geomspace(5, 3000, 120)
V = 2.83  # RMS source voltage

FS, SD, QMS, BL, RE, MMS, LE = 111, 53.5e-4, 6.51, 4.78, 4.18, 5.09e-3, 0.5e-3
VB, QA, QL = 5e-3, 10, 50


def make_driver(**overrides) -> SpeakerDriver:
    params = dict(fs=FS, Sd=SD, Qms=QMS, Bl=BL, Re=RE, Mms=MMS, Le=LE, Xpeak=4e-3)
    params.update(overrides)
    return SpeakerDriver(**params)


def assert_close(test, a, b, rtol=1e-9):
    np.testing.assert_allclose(np.asarray(a), np.asarray(b), rtol=rtol, atol=0)


class TestCombinedDriver(unittest.TestCase):
    "The lumping rules of SpeakerDriver.combined."

    def setUp(self):
        self.spk = make_driver()

    def test_single_driver_is_unscaled_exactly(self):
        # Bit-for-bit equality keeps every single-driver result unchanged.
        for coupling in (None, "parallel", "serial"):
            c = self.spk.combined(1, coupling)
            self.assertEqual((c.Mms, c.Kms, c.Rms, c.Sd, c.Bl, c.Re, c.Le),
                             (self.spk.Mms, self.spk.Kms, self.spk.Rms, self.spk.Sd,
                              self.spk.Bl, self.spk.Re, self.spk.Le))

    def test_parallel(self):
        c = self.spk.combined(3, "parallel")
        self.assertAlmostEqual(c.Mms, 3 * self.spk.Mms)
        self.assertAlmostEqual(c.Kms, 3 * self.spk.Kms)
        self.assertAlmostEqual(c.Rms, 3 * self.spk.Rms)
        self.assertAlmostEqual(c.Sd, 3 * self.spk.Sd)
        self.assertAlmostEqual(c.Bl, self.spk.Bl)
        self.assertAlmostEqual(c.Re, self.spk.Re / 3)
        self.assertAlmostEqual(c.Le, self.spk.Le / 3)

    def test_serial(self):
        c = self.spk.combined(3, "serial")
        self.assertAlmostEqual(c.Mms, 3 * self.spk.Mms)
        self.assertAlmostEqual(c.Sd, 3 * self.spk.Sd)
        self.assertAlmostEqual(c.Bl, 3 * self.spk.Bl)
        self.assertAlmostEqual(c.Re, 3 * self.spk.Re)
        self.assertAlmostEqual(c.Le, 3 * self.spk.Le)

    def test_q_factors_unchanged(self):
        # Bl²/Re scales by N like Mms and Kms, so Qes (and Qts) stay those of one driver.
        for coupling in ("parallel", "serial"):
            c = self.spk.combined(4, coupling)
            qes = (c.Mms * c.Kms)**0.5 / (c.Bl**2 / c.Re)
            qts = (c.Mms * c.Kms)**0.5 / (c.Rms + c.Bl**2 / c.Re)
            self.assertAlmostEqual(qes, self.spk.Qes)
            self.assertAlmostEqual(qts, self.spk.Qts)

    def test_missing_coupling_raises(self):
        with self.assertRaises(ValueError):
            self.spk.combined(2, None)
        with self.assertRaises(ValueError):
            self.spk.combined(2, "series")


class TestSpeakerSystemArray(unittest.TestCase):
    """System-level behaviour. Building the symbolic model is slow, so one system is
    built per class and reconfigured with update_values."""

    @classmethod
    def setUpClass(cls):
        cls.spk = make_driver()
        cls.sys = SpeakerSystem(cls.spk)

    def configure(self, n=1, coupling=None, speaker=None, enclosure=None, passive_radiator=None, Rext=0):
        self.sys.update_values(speaker=speaker or self.spk, n_speaker=n, coupling=coupling,
                               enclosure=enclosure, passive_radiator=passive_radiator,
                               parent_body=None, Rext=Rext)
        return self.sys

    def responses(self, sys):
        "Copies of the responses, since the system object is reused."
        return {"x1": sys.get_displacements(V, FREQS)["Diaphragm, RMS"].copy(),
                "i": sys.get_currents(V, FREQS)["Coil, RMS"].copy(),
                "Z": sys.get_Z(FREQS)["Impedance speaker"].copy(),
                }

    def test_matches_hand_built_equivalent_driver(self):
        # N drivers equal one driver built with the lumped parameters by hand.
        # fs and Qms do not change under the mechanical scaling.
        for n, coupling, bl, re, le in ((2, "parallel", BL, RE / 2, LE / 2),
                                        (3, "serial", 3 * BL, 3 * RE, 3 * LE)):
            for enclosure in (None, Enclosure(VB, QA, QL)):
                with self.subTest(n=n, coupling=coupling, enclosure=enclosure):
                    combined = self.responses(self.configure(n, coupling, enclosure=enclosure))
                    big = make_driver(Sd=n * SD, Mms=n * MMS, Bl=bl, Re=re, Le=le)
                    hand = self.responses(self.configure(speaker=big, enclosure=enclosure))
                    for key in combined:
                        assert_close(self, combined[key], hand[key])

    def test_free_air_impedance_scales(self):
        single = self.configure()
        Z1 = single.get_Z(FREQS)["Impedance speaker"].copy()
        for n in (2, 4):
            Zs = self.configure(n, "serial").get_Z(FREQS)["Impedance speaker"]
            assert_close(self, Zs, n * Z1)
            Zp = self.configure(n, "parallel").get_Z(FREQS)["Impedance speaker"]
            assert_close(self, Zp, Z1 / n)

    def test_free_air_spl_at_equal_voltage(self):
        # Total volume velocity: parallel doubles it (+6.02 dB), serial keeps it
        # (each driver gets half the voltage, but there are two of them).
        def U(sys):
            return sys.combined.Sd * sys.get_velocities(V, FREQS)["Diaphragm, RMS"]

        U1 = U(self.configure()).copy()
        assert_close(self, U(self.configure(2, "parallel")), 2 * U1)
        assert_close(self, U(self.configure(2, "serial")), U1)

    def test_closed_box_is_one_driver_in_a_share_of_the_volume(self):
        # In parallel every driver sees the full voltage and 1/N of the box, so fb,
        # Qtc and the cone motion are those of one driver in a box of Vb/N.
        # fb and Qtc do not depend on the wiring.
        n = 3
        single = self.configure(enclosure=Enclosure(VB / n, QA, QL))
        fb1, qtc1, x1 = single.fb, single.Qtc, single.get_displacements(V, FREQS)["Diaphragm, RMS"].copy()

        for coupling in ("parallel", "serial"):
            sys = self.configure(n, coupling, enclosure=Enclosure(VB, QA, QL))
            self.assertAlmostEqual(sys.fb, fb1, places=9)
            self.assertAlmostEqual(sys.Qtc, qtc1, places=9)

        sys = self.configure(n, "parallel", enclosure=Enclosure(VB, QA, QL))
        assert_close(self, sys.get_displacements(V, FREQS)["Diaphragm, RMS"], x1)

    def test_fb_matches_closed_form(self):
        n = 4
        sys = self.configure(n, "parallel", enclosure=Enclosure(VB, QA, QL))
        K1 = Enclosure(VB, QA, QL).K(SD)  # box stiffness on a single driver
        fb = ((self.spk.Kms + n * K1) / self.spk.Mms)**0.5 / 2 / np.pi
        self.assertAlmostEqual(sys.fb, fb, places=9)

    def test_driver_forces_are_per_driver(self):
        # In free air every driver in parallel sees the full voltage, so it moves and
        # pushes exactly like a single driver; in serial each driver sees V/N.
        names = ("Lorentz force, RMS", "Force from speaker to parent body, RMS")
        single = self.configure().get_forces(V, FREQS)
        single = {k: single[k].copy() for k in names}
        single_at_V_over_3 = self.configure().get_forces(V / 3, FREQS)
        single_at_V_over_3 = {k: single_at_V_over_3[k].copy() for k in names}

        parallel = self.configure(3, "parallel").get_forces(V, FREQS)
        serial = self.configure(3, "serial").get_forces(V, FREQS)
        for k in names:
            k_multi = k.replace(", RMS", ", single driver, RMS")
            assert_close(self, parallel[k_multi], single[k])
            assert_close(self, serial[k_multi], single_at_V_over_3[k])

    def test_parent_body_force_is_system_total(self):
        # The cabinet carries all the drivers: compare with one hand-built big driver.
        from core.components import ParentBody
        pb = ParentBody(0.5, 25e3, 4)
        key = "Force from parent body to reference frame, RMS"
        key_multi = "Force from parent body to reference frame, total, RMS"

        self.sys.update_values(speaker=self.spk, n_speaker=2, coupling="parallel",
                               enclosure=None, passive_radiator=None, parent_body=pb, Rext=0)
        combined = self.sys.get_forces(V, FREQS)[key_multi].copy()

        big = make_driver(Sd=2 * SD, Mms=2 * MMS, Re=RE / 2, Le=LE / 2)
        self.sys.update_values(speaker=big, n_speaker=1, coupling=None,
                               enclosure=None, passive_radiator=None, parent_body=pb, Rext=0)
        assert_close(self, combined, self.sys.get_forces(V, FREQS)[key])

    def test_diaphragm_curves_marked_single_driver(self):
        from gui.plot_builders import build_displacements, build_velocities
        for builder in (build_displacements, build_velocities):
            single = builder(self.configure(), FREQS, V, V, 1).curves
            self.assertIn("Diaphragm, RMS", single)

            multi = builder(self.configure(2, "parallel"), FREQS, V, V, 1).curves
            self.assertIn("Diaphragm, single driver, RMS", multi)
            self.assertFalse([k for k in multi if k.startswith("Diaphragm") and "single driver" not in k])

    def test_shaker_acceleration_marked_single_driver(self):
        from gui.plot_builders import build_spl
        shaker = make_driver(Sd=0)
        self.assertEqual(list(build_spl(self.configure(speaker=shaker), FREQS, V, V, 1).curves),
                         ["Moving mass, RMS"])
        self.assertEqual(list(build_spl(self.configure(2, "parallel", speaker=shaker), FREQS, V, V, 1).curves),
                         ["Moving mass, single driver, RMS"])

    def test_summary_headings_mark_single_driver(self):
        single = self.configure().get_summary(V)
        self.assertIn("<h2>Speaker unit</h2>", single)
        self.assertNotIn("Drivers combined", single)

        multi = self.configure(2, "parallel").get_summary(V)
        self.assertIn("<h2>Speaker unit, single driver</h2>", multi)
        self.assertIn("<h4>Drivers combined</h4>", multi)

    def test_box_stiffness_and_alpha_in_summary(self):
        # K_enc,s is the box stiffness each driver feels, N * Kair * Sd² / Vb;
        # alpha uses the V_as of all the drivers together.
        n = 2
        enclosure = Enclosure(VB, QA, QL)
        sys = self.configure(n, "parallel", enclosure=enclosure)
        k_each = n * enclosure.K(SD)
        self.assertIn(f"K<sub>enc,s</sub>, single driver : {k_each / 1000:.4g} N/mm", sys.get_summary(V))
        self.assertAlmostEqual(sys._combined_Vas(), n * self.spk.Vas())

    def test_excitation_and_identity_say_total(self):
        from gui import labels
        sys = self.configure()
        self.assertNotIn("total", labels.voltage_line(sys, V, *labels.excitation_at_speaker(sys, V)))
        identity = labels.design_identity(sys, V, 1000)
        self.assertNotIn("Per driver:", identity)
        self.assertNotIn("System:", identity)

        sys = self.configure(2, "serial", Rext=1)
        line = labels.voltage_line(sys, V, *labels.excitation_at_speaker(sys, V))
        self.assertIn("Drivers:", line)
        self.assertIn("Watt total @ Re", line)
        identity = labels.design_identity(sys, V, 1000)
        self.assertTrue(identity.startswith("2× serial    Per driver:    "))
        self.assertIn("    System:    ", identity)

    def test_summary_states_excitation_as_graph_titles(self):
        from gui import labels
        for n, coupling, Rext in ((1, None, 0), (2, "serial", 1)):
            sys = self.configure(n, coupling, Rext=Rext)
            line = labels.voltage_line(sys, V, *labels.excitation_at_speaker(sys, V))
            self.assertIn(f"<h2>System</h2>Excitation : {line}<br>", sys.get_summary(V))
        self.assertNotIn("Excitation", sys.get_summary())  # no drive level given

    def test_summary_mentions_drivers_only_when_several(self):
        self.assertNotIn("wiring", self.configure().get_summary(V))
        summary = self.configure(2, "serial").get_summary(V)
        self.assertIn("2 drivers, serial wiring", summary)


class TestPassiveRadiatorSizing(unittest.TestCase):

    def test_area_ratio_refers_to_total_sd(self):
        spk = make_driver()
        enclosure = Enclosure(VB, QA, QL)
        vals = {"area_ratio_pr": 2.0, "Mmdp": 0.01, "h_pr": 0.7, "spring_damping_ratio_pr": 0.005}
        for n in (1, 3):
            combined = spk.combined(n, "parallel")
            pr = construct_PassiveRadiator(vals, combined, enclosure)
            self.assertAlmostEqual(pr.S, 2.0 * n * SD)
            # The PR is tuned against the fb of the whole set of drivers.
            fb = _driver_sealed_fb(combined, enclosure)
            self.assertAlmostEqual(pr.f_free(), 0.7 * fb, places=9)


class TestMigration(unittest.TestCase):

    def test_old_state_gets_single_driver_defaults(self):
        state = convert_v07_to_v08({"fs": 100.0})
        self.assertEqual(state["n_speaker"], 1)
        self.assertEqual(state["coupling"], V08_NEW_KEY_DEFAULTS["coupling"])

    def test_idempotent_and_keeps_existing_values(self):
        state = {"n_speaker": 4, "coupling": {"current_data": "serial", "current_text": "Serial"}}
        before = copy.deepcopy(state)
        convert_v07_to_v08(state)
        convert_v07_to_v08(state)
        self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
