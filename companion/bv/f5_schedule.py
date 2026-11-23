"""F5 in fewer steps from the shipped 10-step Transformer: the voice lab's `--steps`, to hear before anything else.

After sokol-rc/barrens-voice (its f5schedule.py and ADR 0009, MIT). Our export keeps two tables indexed by `time_step`:
the time embedding at each step's start (11 rows, 0..10) and each step's Euler increment (10 rows). A coarser grid
takes the embeddings at its boundaries and sums the increments between them, so the last step still ends where the
10th did; the weights, CFG and the duration stay. The grids are F5-TTS's EPSS ones put on the 10-step grid
(github.com/SWivid/F5-TTS, src/f5_tts/model/utils.py). The `onnx` package rewrites the file: the lab's own
(tools/voicelab_remote.py installs it beside the lab), not the program's.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

# F5_Transformer.onnx of our export (rgeraskin/barrens-voice-f5-onnx): the tables below are its own; another file is
# refused, not guessed at
SOURCE = "6b332c05f060f9b7ac40064aec141ee24e572bc55bc2416839b3ca827dfed526"
EMBEDDINGS, INCREMENTS = "Constant_254", "/Constant"    # the two Constant nodes holding them
BOUNDARIES = {
    4: (0, 1, 2, 6, 10),               # the fork heard words lost at 4 (Whisper's word match 0.39)
    5: (0, 1, 2, 4, 6, 10),            # EPSS [0, 2, 4, 8, 16, 32]
    6: (0, 1, 2, 3, 4, 6, 10),         # EPSS [0, 2, 4, 6, 8, 16, 32]
    8: (0, 1, 2, 3, 4, 5, 6, 8, 10),
}
STEPS = tuple(sorted(BOUNDARIES))


def tables(embeddings, increments, boundaries):
    """The two tables for the grid `boundaries`: the embeddings at its points (axis 1, as the export has them) and
    the increments summed over each of its intervals (axis 0)."""
    import numpy as np
    sums = [increments[a:b].sum(axis=0, dtype=np.float32) for a, b in zip(boundaries, boundaries[1:])]
    return embeddings[:, list(boundaries)], np.array(sums, dtype=increments.dtype)


def transformer(source: Path, folder: Path, steps: int) -> Path:
    """`source` (the shipped Transformer) made to run in `steps` steps, kept in `folder` (made once, then reused).
    Beside the made file a note of the source's size and time: while they are the same the 660 MB source is not read
    again (its SHA-256 checked once). ValueError: a source this module does not know."""
    boundaries = BOUNDARIES[steps]
    target = folder / f"F5_Transformer-{'-'.join(map(str, boundaries))}.onnx"
    note = target.with_name(target.name + ".source")
    stat = source.stat()
    seen = f"{stat.st_size} {stat.st_mtime_ns} {SOURCE}"
    if target.is_file() and note.is_file() and note.read_text(encoding="utf-8") == seen:
        return target
    with source.open("rb") as f:
        if hashlib.file_digest(f, "sha256").hexdigest() != SOURCE:
            raise ValueError(f"{source.name}: не та модель F5, под которую считается сокращённое расписание")
    # no note of this source beside it: a file already there is of another export (or of none known) - made again
    import onnx
    from onnx import numpy_helper

    model = onnx.load(str(source))
    nodes = {n.name: n for n in model.graph.node}
    held = [nodes[EMBEDDINGS].attribute[0].t, nodes[INCREMENTS].attribute[0].t]
    for tensor, values in zip(held, tables(*(numpy_helper.to_array(t) for t in held), boundaries)):
        tensor.CopyFrom(numpy_helper.from_array(values, name=tensor.name))
    folder.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")          # a stopped run leaves no half file under the real name
    onnx.save(model, str(part))
    os.replace(part, target)
    note.write_text(seen, encoding="utf-8")
    return target
