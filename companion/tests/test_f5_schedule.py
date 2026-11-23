"""F5 in fewer steps (bv/f5_schedule.py): the grids, the tables, the rewritten model."""
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bv import f5_schedule  # noqa: E402

try:
    import numpy as np
except ImportError:
    np = None
try:
    import onnx
except ImportError:          # the lab's own package, not the program's: the rewrite itself is checked where it is
    onnx = None


class Grids(unittest.TestCase):
    def test_every_grid_runs_from_the_start_to_the_10th_step_s_end(self):
        for steps, points in f5_schedule.BOUNDARIES.items():
            self.assertEqual(len(points), steps + 1, steps)
            self.assertEqual((points[0], points[-1]), (0, 10), steps)
            self.assertEqual(list(points), sorted(set(points)), steps)
        self.assertEqual(f5_schedule.STEPS, (4, 5, 6, 8))


@unittest.skipIf(np is None, "numpy")
class Tables(unittest.TestCase):
    def test_embeddings_at_the_grid_s_points_and_increments_summed_between_them(self):
        embeddings = np.arange(11, dtype=np.float16).reshape(1, 11, 1).repeat(3, axis=2)   # row i holds i
        increments = (np.arange(10, dtype=np.float16) + 1).reshape(10, 1)                  # step i adds i+1
        points = f5_schedule.BOUNDARIES[6]
        kept, summed = f5_schedule.tables(embeddings, increments, points)
        self.assertEqual(kept.shape, (1, 7, 3))
        self.assertEqual(kept[0, :, 0].tolist(), list(points))
        self.assertEqual(summed.dtype, increments.dtype)
        self.assertEqual(summed[:, 0].tolist(), [1, 2, 3, 4, 5 + 6, 7 + 8 + 9 + 10])
        self.assertEqual(float(summed.sum()), float(increments.sum()))    # it ends where the 10 steps did


class Refusal(unittest.TestCase):
    def test_an_unknown_model_is_refused_and_nothing_written(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(folder, ignore_errors=True))
        other = folder / "F5_Transformer.onnx"
        other.write_bytes(b"another export")
        with self.assertRaises(ValueError):
            f5_schedule.transformer(other, folder / "f5-steps", 6)
        self.assertFalse((folder / "f5-steps").exists())


@unittest.skipIf(np is None or onnx is None, "numpy and onnx")
class Rewrite(unittest.TestCase):
    """A model with the export's two Constant nodes: the rewrite changes them and nothing else."""

    def model(self, path: Path) -> None:
        from onnx import TensorProto, helper, numpy_helper
        embeddings = np.arange(11, dtype=np.float16).reshape(1, 11, 1)
        increments = np.full((10, 1), 0.1, dtype=np.float16)
        nodes = [helper.make_node("Constant", [], ["e"], name=f5_schedule.EMBEDDINGS,
                                  value=numpy_helper.from_array(embeddings, "e")),
                 helper.make_node("Constant", [], ["d"], name=f5_schedule.INCREMENTS,
                                  value=numpy_helper.from_array(increments, "d")),
                 helper.make_node("Identity", ["x"], ["y"], name="other")]
        graph = helper.make_graph(nodes, "g", [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1])],
                                  [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1])])
        onnx.save(helper.make_model(graph), str(path))

    def test_the_tables_rewritten_once_and_reused(self):
        from onnx import numpy_helper
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(folder, ignore_errors=True))
        source = folder / "F5_Transformer.onnx"
        self.model(source)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        with mock.patch.object(f5_schedule, "SOURCE", digest):
            made = f5_schedule.transformer(source, folder / "f5-steps", 6)
            # made: the source's note beside it, and the source not read again (its hash not taken) while it is the same
            with mock.patch("hashlib.file_digest", side_effect=AssertionError("read again")):
                again = f5_schedule.transformer(source, folder / "f5-steps", 6)
            os.utime(source, ns=(1, 1))                                     # the source changed: checked again
            with self.assertRaises(AssertionError):
                with mock.patch("hashlib.file_digest", side_effect=AssertionError("read again")):
                    f5_schedule.transformer(source, folder / "f5-steps", 6)
        self.assertEqual(made, again)
        # a file there without this source's note (another export's, the same grid): made again, not taken
        (made.with_name(made.name + ".source")).unlink()
        made.write_bytes(b"another export's rewrite")
        with mock.patch.object(f5_schedule, "SOURCE", digest):
            f5_schedule.transformer(source, folder / "f5-steps", 6)
        self.assertEqual(len(onnx.load(str(made)).graph.node), 3)
        self.assertEqual(sorted(p.name for p in (folder / "f5-steps").iterdir()),
                         [made.name, made.name + ".source"])                          # no .part left
        nodes = {n.name: numpy_helper.to_array(n.attribute[0].t) for n in onnx.load(str(made)).graph.node
                 if n.op_type == "Constant"}
        self.assertEqual(nodes[f5_schedule.EMBEDDINGS][0, :, 0].tolist(), [0, 1, 2, 3, 4, 6, 10])
        self.assertEqual(nodes[f5_schedule.INCREMENTS].shape, (6, 1))
        self.assertAlmostEqual(float(nodes[f5_schedule.INCREMENTS].sum()), 1.0, places=2)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)          # the shipped one untouched


if __name__ == "__main__":
    unittest.main()
