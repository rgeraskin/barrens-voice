"""How F5 on a runtime makes the game stutter: a stand-in for the game on the video card, F5 at a number of steps,
and what the stand-in's frames did meanwhile (DEVELOPMENT.md, «CUDA, а не DirectML»).

Three parts, run on the Windows machine with the install whose runtime is measured (DirectML: a separate install,
`install.py --runtime directml --root <folder>`; never the player's), game and companion closed. BV_DATA and BV_CACHE
must be copies too: the bench saves its cast into assignments.json and makes or removes cache\f5-steps.

  probe  <frames.csv> <stop file>   a "frame" on the card (six MatMul 1536x1536, ~6 ms) 60 times a second, each
                                    frame's start (wall clock) and length to the CSV, until the stop file appears
                                    (one left from a run before is removed first).
                                    The frame's data stay in memory and go to the card each run: with them kept on
                                    the card (an OrtValue on "dml") DirectML stopped with 887A0005 at the first frame
                                    and the NVIDIA driver logged errors (nvlddmkm 153), twice.
  bench  <steps> <out.json>         the companion's F5 (bv from BV_CODE, data from BV_DATA: config.json and the
                                    voice bank; ONNX Runtime's threads and the priorities as the companion sets them,
                                    bv/share.py) at that many steps, the same 12 chat lines - each a whole line in one
                                    _synth, not cut as render() cuts it - timed, and F5's calls counted: a take whose
                                    speech runs to its very end is made again (f5_end_check "silence"), two calls.
  report <frames.csv> <out.json>... per run: synthesis time, F5's calls, frames over 33 and 100 ms (a hitch: about
                                    one a step of each call), their lengths, and the frames while the voices load.
                                    A run the probe's frames do not cover is an error, not a clean result.

A run, in PowerShell, with BV_DATA, BV_CACHE (the f5-steps model) and HF_HOME/HF_HUB_OFFLINE set:
  $p = Start-Process python -ArgumentList f5_stutter.py, probe, frames.csv, stop -PassThru
  foreach ($s in 10, 8, 6) { python f5_stutter.py bench $s "steps-$s.json" }
  New-Item stop; $p.WaitForExit()
  python f5_stutter.py report frames.csv steps-10.json steps-8.json steps-6.json
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

LINES = ["Нужен хил в Пещеры Стенаний, ласт слот.", "Кто идёт в Мёртвые копи? Нам нужен танк.",
         "Продам сумки на 14 слотов, недорого, пишите в личку.", "Привет всем.",
         "Собираю пати на Рагфаер, нужен ещё один дд и хил, пишите.", "Го в Степи, там вторжение.",
         "Спасибо за помощь, ребята, вы лучшие!", "Ищу гильдию для рейдов, играю хилом уже давно.",
         "А где тут учитель кожевничества?", "Ну всё, я спать, всем пока.",
         "Ищем танка и хила в Глубины Чёрной горы, остальные есть.", "Кто знает, когда откроют Ан-Кираж?"]
CAST = [("Громмаш", "Orc", "2"), ("Джайна", "Human", "3"), ("Брэнн", "Dwarf", "2"), ("Тиранда", "NightElf", "3"),
        ("Вол'джин", "Troll", "2"), ("Сильвана", "Scourge", "3")]
HITCH_MS, LONG_MS = 33, 100      # a frame later than two at 60 fps; one the eye cannot miss


def probe(out: str, stop: str, provider: str = "DmlExecutionProvider") -> None:
    import numpy as np
    import onnxruntime as ort
    from onnx import TensorProto, helper, numpy_helper
    n = 1536
    rng = np.random.default_rng(1)
    weights = [numpy_helper.from_array(rng.random((n, n), dtype=np.float32) / n, f"w{i}") for i in range(6)]
    nodes, prev = [], "x"
    for i in range(6):
        nodes.append(helper.make_node("MatMul", [prev, f"w{i}"], [f"y{i}"]))
        prev = f"y{i}"
    graph = helper.make_graph(nodes, "frame", [helper.make_tensor_value_info("x", TensorProto.FLOAT, [n, n])],
                              [helper.make_tensor_value_info(prev, TensorProto.FLOAT, [n, n])], weights)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    options = ort.SessionOptions()
    options.enable_mem_pattern = False
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    session = ort.InferenceSession(model.SerializeToString(), options, providers=[provider])
    if session.get_providers()[0] != provider:
        raise SystemExit(f"{provider} not taken: {session.get_providers()}")
    x = rng.random((n, n), dtype=np.float32)
    if os.path.exists(stop):                             # left from a run before: it would end this one at once
        os.remove(stop)
    for _ in range(20):
        session.run(None, {"x": x})
    rows, period = [], 1 / 60
    due = time.perf_counter()
    wall = time.time() - time.perf_counter()
    while not os.path.exists(stop):
        a = time.perf_counter()
        session.run(None, {"x": x})
        b = time.perf_counter()
        rows.append((wall + a, (b - a) * 1000))
        due = max(due + period, b)
        time.sleep(max(0.0, due - time.perf_counter()))
    Path(out).write_text("".join(f"{t:.4f},{ms:.2f}\n" for t, ms in rows), encoding="utf-8")


def bench(steps: int, out: str) -> None:
    sys.path.insert(0, os.environ["BV_CODE"])            # the install's companion folder
    from bv import f5engine
    from bv.text import numbers_to_words
    data = Path(os.environ["BV_DATA"])
    config = json.loads((data / "config.json").read_text(encoding="utf-8"))
    config.update(f5_steps=steps, f5_end_check="silence")
    from bv import share
    if config.get("share_with_game", True):            # as the companion's main()
        share.limit_onnx(int(config.get("onnx_threads", 2)))
        share.lower_priority(print)
    started = time.time()
    speaker = f5engine.F5Speaker(config, lambda m: print(m, flush=True), data)
    speaker._load()
    loaded = time.time()
    calls = []
    synth = speaker.onnx.synth

    def counted(*args, **kwargs):
        calls.append(1)
        return synth(*args, **kwargs)
    speaker.onnx.synth = counted
    time.sleep(3)
    lines = []
    for i, text in enumerate(LINES):
        name, race, sex = CAST[i % len(CAST)]
        slot = speaker.assigner.slot_for(name, race, sex)
        accented = speaker.accentor.accent(numbers_to_words(text))
        calls.clear()
        a = time.time()
        wav, rate = speaker._synth(slot, accented, 100, name)
        b = time.time()
        lines.append({"start": a, "end": b, "audio": len(wav) / rate, "calls": len(calls)})
        print(f"{steps} steps, line {i}: {b - a:.2f} s for {len(wav) / rate:.1f} s of speech", flush=True)
        time.sleep(1.0)
    Path(out).write_text(json.dumps({"steps": steps, "device": speaker.device, "load": [started, loaded],
                                     "lines": lines}, indent=1), encoding="utf-8")


def frames(path: str) -> list[tuple[float, float]]:
    return [tuple(map(float, line.split(","))) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")]


def summary(frame_rows: list[tuple[float, float]], run: dict) -> dict:
    """What the frames did while the run's lines were made (a frame counts by its start): how long that took, F5's
    calls, how many frames came over HITCH_MS and LONG_MS, their median, the longest frame, how long the frames stood
    in all, and the longest while the voices loaded. A run the frames do not cover (no probe, or one that ended
    early) is an error: its zeros would read as a card that never stutters."""
    windows = [(line["start"], line["end"]) for line in run["lines"]]
    times = [t for t, _ in frame_rows]
    if not times or min(times) > windows[0][0] or max(times) < windows[-1][1]:
        raise ValueError(f"{run['steps']} steps: the probe's frames do not cover the run")
    inside = [ms for t, ms in frame_rows if any(a <= t <= b for a, b in windows)]
    hitches = [ms for ms in inside if ms > HITCH_MS]
    counted = all("calls" in line for line in run["lines"])   # a bench before the count: no per-call figure
    calls = sum(line["calls"] for line in run["lines"]) if counted else None
    loading = [ms for t, ms in frame_rows if run["load"][0] <= t <= run["load"][1]]
    return {"steps": run["steps"], "seconds": round(sum(b - a for a, b in windows), 1), "frames": len(inside),
            "calls": calls, "hitches": len(hitches), "per_call": round(len(hitches) / calls, 1) if calls else None,
            "long": sum(1 for ms in hitches if ms > LONG_MS),
            "median_hitch_ms": round(statistics.median(hitches)) if hitches else 0,
            "longest_ms": round(max(inside)) if inside else 0, "stood_s": round(sum(hitches) / 1000, 1),
            "loading_longest_ms": round(max(loading)) if loading else None}


def between_lines(frame_rows: list[tuple[float, float]], run: dict) -> list[float]:
    """The frames in the run's pauses between lines (the bench sleeps a second after each): the card with F5 loaded
    and idle. The pause also holds the next line's accent() on the processor, just before its start."""
    gaps = [(a["end"] + 0.2, b["start"] - 0.1) for a, b in zip(run["lines"], run["lines"][1:])]
    return [ms for t, ms in frame_rows if any(a <= t <= b for a, b in gaps)]


def report(frames_csv: str, runs: list[str]) -> None:
    rows = frames(frames_csv)
    loaded = [json.loads(Path(r).read_text(encoding="utf-8")) for r in runs]
    idle = [ms for run in loaded for ms in between_lines(rows, run)]
    if idle:
        print(f"between lines (no synthesis): {len(idle)} frames, median {statistics.median(idle):.1f} ms, "
              f"longest {max(idle):.0f} ms")
    for run in loaded:
        try:
            s = summary(rows, run)
        except ValueError as e:
            raise SystemExit(str(e)) from e
        calls = (f"by {s['calls']} F5 calls" if s["calls"] is not None else "F5 calls not recorded")
        per_call = f"{s['per_call']} a call; " if s["per_call"] is not None else ""
        loading = (f"longest frame {s['loading_longest_ms']} ms" if s["loading_longest_ms"] is not None
                   else "no frame recorded")
        print(f"{s['steps']} steps: lines made in {s['seconds']} s {calls}, {s['frames']} frames; "
              f"over {HITCH_MS} ms {s['hitches']} ({per_call}over {LONG_MS} ms {s['long']}), median "
              f"{s['median_hitch_ms']} ms, longest {s['longest_ms']} ms; the frame stood {s['stood_s']} s; "
              f"loading the voices: {loading}")


if __name__ == "__main__":
    command, args = sys.argv[1], sys.argv[2:]
    if command == "probe":
        probe(*args)
    elif command == "bench":
        bench(int(args[0]), args[1])
    elif command == "report":
        report(args[0], args[1:])
    else:
        raise SystemExit(__doc__)
