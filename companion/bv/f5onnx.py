"""F5-TTS through ONNX Runtime (0.4.0): the race voices without torch, on any DirectX 12 card (DirectML).

The models are the Russian F5 (Misha24-10/F5-TTS_RUSSIAN) exported by DakeQQ/F5-TTS-ONNX: four graphs
in one folder - Metadata (sample rates, hop, the steps), Preprocess (reference audio and text to the
starting noise and the conditions), Transformer (one denoising step; 16 of them, fixed at export with
CFG 2 and sway -1, as the torch F5 the companion used), Decode (Vocos: mel to audio). Preprocess and
the Transformer run on the card; Decode on the CPU - on DirectML it gives silence (the exporter says so).

The length of the speech is the caller's, as with the torch engine's `fix_duration`: the total seconds
(reference and line) become the frames of `max_duration`.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np

PUNCTUATION = str.maketrans({";": ",", "“": '"', "”": '"', "‘": "'", "’": "'"})


def read_vocab(path: Path) -> dict[str, int]:
    """F5's vocab.txt read as F5 reads it: one symbol per line (the line without its line break, so a
    line holding a space is the space), its index the line's number."""
    out: dict[str, int] = {}
    lines = Path(path).read_text(encoding="utf-8").split("\n")   # only "\n": a file is read line by line
    if lines and lines[-1] == "":
        lines.pop()
    for i, line in enumerate(lines):
        out[line] = i
    return out


def text_ids(text: str, vocab: dict[str, int]) -> np.ndarray:
    """The text as the model's symbol indices, as F5 makes them for text with no Chinese in it: one per
    character (after its few punctuation replacements); a symbol the vocabulary lacks is index 0."""
    return np.array([[vocab.get(ch, 0) for ch in text.translate(PUNCTUATION)]], dtype=np.int32)


class F5Onnx:
    def __init__(self, model_dir: Path, vocab_path: Path, provider: str = "DmlExecutionProvider", log=print,
                 session_config: dict | None = None):
        self.model_dir, self.vocab_path, self.provider, self.log = Path(model_dir), Path(vocab_path), provider, log
        self.session_config = dict(session_config or {})
        self.lock = threading.Lock()
        self.loaded = False

    def load(self) -> None:
        if self.loaded:
            return
        import onnxruntime as ort
        meta = ort.InferenceSession(str(self.model_dir / "F5_Metadata.onnx"),
                                    providers=["CPUExecutionProvider"]).get_modelmeta().custom_metadata_map
        self.sample_rate = int(meta["sample_rate"])
        self.in_rate = int(meta["in_sample_rate"])
        self.out_rate = int(meta["out_sample_rate"])
        self.hop = int(meta["hop_length"])
        self.steps = int(meta["nfe_step"])
        self.max_frames = int(meta["max_signal_length"])
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        if self.provider == "DmlExecutionProvider":
            options.enable_mem_pattern = False           # DirectML's own requirements
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        for key, value in self.session_config.items():
            options.add_session_config_entry(key, str(value))
        card = [(self.provider, {"device_id": 0, "performance_preference": "high_performance"})
                if self.provider == "DmlExecutionProvider" else self.provider, "CPUExecutionProvider"]
        cpu = ["CPUExecutionProvider"]
        self.pre = ort.InferenceSession(str(self.model_dir / meta["model_file_name_preprocess"]), options, providers=card)
        self.net = ort.InferenceSession(str(self.model_dir / meta["model_file_name_transformer"]), options, providers=card)
        self.dec = ort.InferenceSession(str(self.model_dir / meta["model_file_name_decode"]), providers=cpu)
        types = {"tensor(float)": np.float32, "tensor(float16)": np.float16, "tensor(int16)": np.int16}
        self.audio_type = types[self.pre.get_inputs()[0].type]
        self.vocab = read_vocab(self.vocab_path)
        self.device = "dml" if self.provider == "DmlExecutionProvider" else "cpu"
        self.loaded = True
        self.log(f"F5 (ONNX, {self.net.get_providers()[0]}) готов: {self.steps} шагов")

    def frames(self, seconds: float) -> int:
        return int(seconds * self.sample_rate / self.hop)

    def synth(self, ref_audio: np.ndarray, ref_text: str, text: str, total_seconds: float) -> tuple[np.ndarray, int]:
        """The line in the reference's voice: `ref_audio` mono float at `in_rate`, `total_seconds` the
        length of reference and line together. Returns (audio, sample rate) of the line alone."""
        self.load()
        if not ref_text.endswith(". ") and not ref_text.endswith("。"):   # as F5's own preprocessing
            ref_text += " " if ref_text.endswith(".") else ". "
        ids = text_ids(ref_text + text, self.vocab)
        if self.audio_type == np.int16:
            audio = np.clip(ref_audio * 32767, -32768, 32767).astype(np.int16)
        else:
            audio = ref_audio.astype(self.audio_type)
        ref_frames = int(len(ref_audio) * self.sample_rate / self.in_rate) // self.hop
        duration = max(ids.shape[1], ref_frames + 1) + 1
        duration = min(max(duration, self.frames(total_seconds)), self.max_frames)
        with self.lock:
            started = time.perf_counter()
            noise, cos, sin, cond, cond_drop, ref_len, rms, tail = self.pre.run(None, {
                "audio": audio.reshape(1, 1, -1), "text_ids": ids, "max_duration": np.array([duration], np.int64)})
            prepared = time.perf_counter()
            fixed = {"rope_cos": cos, "rope_sin": sin, "cat_mel_text": cond, "cat_mel_text_drop": cond_drop}
            noise = self._denoise(noise, fixed)
            denoised = time.perf_counter()
            out = self.dec.run(None, {"denoised": noise, "ref_signal_len": ref_len, "rms_scale": rms,
                                      "ref_mel_tail": tail})[0]
            # where the time goes: preparing, the denoising steps, Vocos (seconds), and the frames
            self.timings = (prepared - started, denoised - prepared, time.perf_counter() - denoised, duration)
        return np.asarray(out, dtype=np.float32).reshape(-1), self.out_rate

    def _denoise(self, noise: np.ndarray, fixed: dict) -> np.ndarray:
        """The denoising steps. On the card the conditions go there once and the noise stays there,
        handed between two buffers from step to step (IO binding): sending them each step cost more
        than the steps themselves (2.3-4.1 s a line instead of the exporter's 1.3-3.2 s)."""
        import onnxruntime as ort
        if self.device == "cpu":
            for step in range(self.steps):
                noise = self.net.run(None, {"noise": noise, **fixed, "time_step": np.array([step], np.int32)})[0]
            return noise
        on_card = {k: ort.OrtValue.ortvalue_from_numpy(np.ascontiguousarray(v), self.device, 0) for k, v in fixed.items()}
        buffers = (ort.OrtValue.ortvalue_from_numpy(np.ascontiguousarray(noise), self.device, 0),
                   ort.OrtValue.ortvalue_from_shape_and_type(noise.shape, noise.dtype, self.device, 0))
        steps = [ort.OrtValue.ortvalue_from_numpy(np.array([s], np.int32)) for s in range(self.steps)]
        bindings = []
        for i in range(2):
            b = self.net.io_binding()
            for name, value in on_card.items():
                b.bind_ortvalue_input(name, value)
            b.bind_ortvalue_input("noise", buffers[i])
            b.bind_ortvalue_output("denoised", buffers[1 - i])
            bindings.append(b)
        for step in range(self.steps):
            b = bindings[step & 1]
            b.bind_ortvalue_input("time_step", steps[step])
            self.net.run_with_iobinding(b)
        return buffers[self.steps & 1].numpy()
