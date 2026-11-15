"""How alike the text Whisper heard is to the text expected, for the voice bank: Whisper hears the
client's voice lines for their text (the client has no subtitles for them) and checks each joined
reference clip against that text - a reference whose text is off makes F5 say the wrong words before
every line. Whisper itself is bv/whisper_onnx.py (until 0.3.0 it ran through torch here)."""
from __future__ import annotations

import difflib
import re


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower().replace("ё", "е").replace("+", ""))


def similarity(expected: str, heard: str) -> float:
    """How alike the words are (0..1); extra or missing words lower it."""
    return difflib.SequenceMatcher(None, words(expected), words(heard)).ratio()
