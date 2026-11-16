---
license: cc-by-nc-4.0
language:
- ru
base_model: Misha24-10/F5-TTS_RUSSIAN
pipeline_tag: text-to-speech
library_name: onnx
tags:
- f5-tts
- onnx
- directml
- cuda
- voice-cloning
---

# F5-TTS Russian in ONNX (10 steps) for Barrens Voice

The Russian fine-tune of F5-TTS, [Misha24-10/F5-TTS_RUSSIAN](https://huggingface.co/Misha24-10/F5-TTS_RUSSIAN) (`F5TTS_v1_Base_v2`), exported to ONNX for [Barrens Voice](https://github.com/rgeraskin/barrens-voice) — a World of Warcraft mod that reads the chat aloud, each player in a voice of their race. It runs with ONNX Runtime, without PyTorch: on NVIDIA through CUDA (`onnxruntime-gpu`), on other DirectX 12 video cards through DirectML (there the game stutters while a line is made: DirectML holds the card for each whole step).

## Files

- `F5_Preprocess.onnx` — reference audio and text to the starting noise and the conditions.
- `F5_Transformer.onnx` — one denoising step (float16). 10 steps, CFG strength 2 and sway sampling −1 are fixed at export.
- `F5_Decode.onnx` — the mel spectrogram to 24 kHz audio (Vocos). Run it on the CPU: on DirectML it gives silence.
- `F5_Metadata.onnx` — sample rates, hop length, the number of steps.

The vocabulary is the base model's (`F5TTS_v1_Base/vocab.txt` in Misha24-10/F5-TTS_RUSSIAN). The length of the speech is an input (`max_duration`, in frames), as F5's `fix_duration`. The exported Vocos ends every line with a few dozen samples at full scale: drop the last two frames (2 × 256 samples) and fade out the rest — see `clean_tail` in [`f5onnx.py`](https://github.com/rgeraskin/barrens-voice/blob/master/companion/bv/f5onnx.py), which shows the whole inference loop.

On an RTX 5070 Ti a chat line takes 1.0–1.3 s through CUDA, about 1.2 s through DirectML (IO binding for the steps).

## How it was made

Exported with [DakeQQ/F5-TTS-ONNX](https://github.com/DakeQQ/F5-TTS-ONNX) (Apache-2.0, commit 427f545d) from the checkpoint `F5TTS_v1_Base_v2/model_last_inference.safetensors`, with the steps set to 10.

## License and credits

- The weights are a derivative of Misha24-10/F5-TTS_RUSSIAN and keep its license, [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/): non-commercial use, with attribution.
- F5-TTS — Yushen Chen et al., [SWivid/F5-TTS](https://github.com/SWivid/F5-TTS) (code MIT).
- Russian fine-tune — Misha24-10.
- Vocos — [charactr-platform/vocos](https://github.com/charactr-platform/vocos) (MIT), inside `F5_Decode.onnx`.
- ONNX export — DakeQQ/F5-TTS-ONNX (Apache-2.0).
