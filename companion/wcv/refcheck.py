"""Whisper for the voice bank: it hears the client's voice lines for their text (the client has no
subtitles for them) and checks each joined reference clip against that text - a reference whose
text is off makes F5 say the wrong words before every line. Used only while the bank is built."""
from __future__ import annotations

import difflib
import re

MODEL = "openai/whisper-large-v3-turbo"


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower().replace("ё", "е").replace("+", ""))


def similarity(expected: str, heard: str) -> float:
    """How alike the words are (0..1); extra or missing words lower it."""
    return difflib.SequenceMatcher(None, words(expected), words(heard)).ratio()


class Checker:
    def __init__(self, log):
        self.log = log
        self.pipe = None

    def load(self) -> bool:
        try:
            import torch
            from transformers import pipeline
            self.pipe = pipeline("automatic-speech-recognition", model=MODEL, torch_dtype=torch.float16,
                                 device="cuda")
            return True
        except Exception as e:  # noqa: BLE001 - reported; the bank cannot be made without it
            self.log(f"Whisper недоступен: {e}")
            return False

    def transcribe(self, samples, rate: int) -> str:
        out = self.pipe({"raw": samples, "sampling_rate": rate},
                        generate_kwargs={"language": "russian", "task": "transcribe"})
        return out.get("text", "")

    def score(self, samples, rate: int, expected: str) -> tuple[float, str]:
        heard = self.transcribe(samples, rate)
        return similarity(expected, heard), heard
