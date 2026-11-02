"""Processus vocal de Nova, lancé avec le Python de ~/.local/share/nova/voix/env.

  voice_worker.py prepare    --model small --models-dir DIR      télécharge le modèle de reconnaissance
  voice_worker.py transcribe FICHIER.wav --model small --models-dir DIR   → texte sur la sortie
  voice_worker.py speak      --voice VOIX.onnx --out FICHIER.wav  (texte lu sur l'entrée)

Ne dépend que de faster-whisper et piper-tts (pas du reste de Nova).
"""
from __future__ import annotations

import argparse
import os
import sys
import wave


def whisper(model: str, models_dir: str):
    from faster_whisper import WhisperModel

    threads = max(1, (os.cpu_count() or 4) - 1)
    return WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=threads, download_root=models_dir)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="voice_worker")
    parser.add_argument("action", choices=["prepare", "transcribe", "speak"])
    parser.add_argument("audio", nargs="?")
    parser.add_argument("--model", default="small")
    parser.add_argument("--models-dir", default=None)
    parser.add_argument("--voice")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    if args.action == "prepare":
        whisper(args.model, args.models_dir)
        return 0

    if args.action == "transcribe":
        model = whisper(args.model, args.models_dir)
        segments, _info = model.transcribe(args.audio, language="fr", beam_size=1, vad_filter=True,
                                           condition_on_previous_text=False)
        print(" ".join(segment.text.strip() for segment in segments).strip())
        return 0

    from piper import PiperVoice

    text = sys.stdin.read().strip()
    if not text or not args.voice or not args.out:
        return 2
    voice = PiperVoice.load(args.voice)
    with wave.open(args.out, "wb") as out:
        if hasattr(voice, "synthesize_wav"):  # piper-tts 1.3 et plus
            voice.synthesize_wav(text, out)
        else:  # piper-tts 1.2
            voice.synthesize(text, out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
