"""Leaving the computer to the game: the companion works in the game's gaps, not in its way.

Since 0.4.0 the race voices run through ONNX Runtime: the denoising steps on the video card (CUDA on
NVIDIA, else DirectML - the same Direct3D 12 the game draws with) and Vocos (mel to sound) on the
processor.
ONNX Runtime takes every core for a CPU graph by default, and its threads spin after each run, waiting
for more: a burst on all eight cores at each line, just when the game wants one - the game stuttered
now and then while chat was read (it did not with torch, where Vocos ran on the card).

So: ONNX sessions get a few threads that sleep when idle (every session in the process - RUAccent's
too, made inside that library - by wrapping onnxruntime.InferenceSession before anything makes one),
and the process a below-normal priority on the processor and on the video card's scheduler. The game
goes first; a line may take a little longer when the game is busy.
"""
from __future__ import annotations

import sys

BELOW_NORMAL_PRIORITY_CLASS = 0x4000
D3DKMT_BELOW_NORMAL = 1         # D3DKMT_SCHEDULINGPRIORITYCLASS_BELOW_NORMAL


def tune(options, threads: int, make):
    """Session options with at most `threads` threads in a graph, one between graphs, none spinning
    (`make` makes new options when there are none). A count set on purpose is kept."""
    options = options if options is not None else make()
    if not options.intra_op_num_threads:
        options.intra_op_num_threads = threads
    if not options.inter_op_num_threads:
        options.inter_op_num_threads = 1
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    options.add_session_config_entry("session.inter_op.allow_spinning", "0")
    return options


def limit_onnx(threads: int = 2) -> bool:
    """Every ONNX Runtime session made from now on tuned so; False without ONNX Runtime."""
    try:
        import onnxruntime as ort
    except ImportError:
        return False
    if getattr(ort.InferenceSession, "_bv_tuned", False):
        return True
    base = ort.InferenceSession

    class Tuned(base):
        _bv_tuned = True

        def __init__(self, path_or_bytes, sess_options=None, providers=None, provider_options=None, **kw):
            super().__init__(path_or_bytes, tune(sess_options, threads, ort.SessionOptions), providers,
                             provider_options, **kw)

    ort.InferenceSession = Tuned
    return True


def lower_priority(log) -> None:
    """This process below normal on the processor and on the video card (Windows' GPU scheduler)."""
    if sys.platform != "win32":
        return
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    me = kernel32.GetCurrentProcess()
    cpu = bool(kernel32.SetPriorityClass(ctypes.c_void_p(me), BELOW_NORMAL_PRIORITY_CLASS))
    try:
        gdi32 = ctypes.windll.gdi32
        gdi32.D3DKMTSetProcessSchedulingPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_int]
        gpu = gdi32.D3DKMTSetProcessSchedulingPriorityClass(ctypes.c_void_p(me), D3DKMT_BELOW_NORMAL) == 0
    except (AttributeError, OSError):
        gpu = False
    log("приоритет ниже игры: процессор " + ("да" if cpu else "нет") + ", видеокарта " + ("да" if gpu else "нет"))
