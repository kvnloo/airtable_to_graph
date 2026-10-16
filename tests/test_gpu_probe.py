import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "experiments" / "bend-crossover" / "gpu_probe.py"
spec = importlib.util.spec_from_file_location("gpu_probe", path)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProbeTests(unittest.TestCase):
    def test_exact_pin(self):
        self.assertEqual(probe.BEND_VERSION, "bend 2.0.36")

    def test_expected_cpu_gpu_match(self):
        self.assertTrue(probe.validate_output("1048576", "1048576"))

    def test_mismatch_rejected(self):
        for a, b in [("1048576", "1"), ("1", "1048576"), ("", "")]:
            with self.assertRaises(ValueError):
                probe.validate_output(a, b)


if __name__ == "__main__":
    unittest.main()
