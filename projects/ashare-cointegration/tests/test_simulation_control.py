import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import run_simulation


class SimulationControlTests(unittest.TestCase):
    def test_user_hold_prevents_pool_and_preserves_progress(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            path=root/"results"/"simulation"/"S2_status.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(dict(stage="S2",status="held_by_user",completed=0,planned=2000)))
            before=path.read_bytes()
            with patch.object(run_simulation,"ROOT",root),patch(
                "sys.argv",["run_simulation.py","--stage","S2"]),patch.object(
                    run_simulation,"ProcessPoolExecutor") as pool:
                run_simulation.main()
            pool.assert_not_called()
            self.assertEqual(path.read_bytes(),before)
