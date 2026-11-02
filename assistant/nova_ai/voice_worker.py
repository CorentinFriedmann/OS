"""Processus vocal de Nova, lancé avec le Python de ~/.local/share/nova/voix/env.

  voice_worker.py prepare    --model small --models-dir DIR      télécharge le modèle de reconnaissance
  voice_worker.py transcribe FICHIER.wav --model small --models-dir DIR   → texte sur la sortie
  voice_worker.py speak      --voice VOIX.onnx --out FICHIER.wav  (texte lu sur l'entrée)

Ne dépend que de faster-whisper et piper-tts (pas du reste de Nova).
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
import wave

SAMPLE_RATE = 16000  # fréquence attendue par Whisper


def whisper(model: str, models_dir: str):
    from faster_whisper import WhisperModel

    threads = max(1, (os.cpu_count() or 4) - 1)
    return WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=threads, download_root=models_dir)


def load_wav(path: str):
    """Lit un WAV PCM 16 bits et le renvoie en mono 16 kHz (tableau numpy float32).

    Lecture directe du fichier (sans PyAV, dont les changements de version cassent
    faster-whisper) ; tolère un en-tête non finalisé, si l'enregistrement a été
    interrompu brutalement.
    """
    import numpy as np

    data = open(path, "rb").read()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("fichier WAV attendu")
    pos, rate, channels, bits, pcm = 12, 0, 1, 16, b""
    while pos + 8 <= len(data):
        chunk, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = pos + 8
        if chunk == b"fmt ":
            _fmt, channels, rate, _rate, _align, bits = struct.unpack("<HHIIHH", data[body:body + 16])
        elif chunk == b"data":
            end = body + size if 0 < size <= len(data) - body else len(data)  # en-tête non finalisé
            pcm = data[body:end]
            break
        pos = body + size + (size & 1)
    if not rate or bits != 16:
        raise ValueError(f"WAV PCM 16 bits attendu (reçu : {bits} bits, {rate} Hz)")
    audio = np.frombuffer(pcm[: len(pcm) - len(pcm) % (2 * channels)], dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE and len(audio):
        target = np.linspace(0, len(audio) - 1, int(round(len(audio) * SAMPLE_RATE / rate)))
        audio = np.interp(target, np.arange(len(audio)), audio).astype(np.float32)
    return audio


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="voice_worker")
    parser.add_argument("action", choices=["prepare", "transcribe", "speak"])
    parser.add_argument("audio", nargs="?")
    parser.add_argument("--model", default="small")
    parser.add_argument("--models-dir", default=None)
    parser.add_argument("--voice")
    parser.add_argument("--out")
    parser.add_argument("--no-vad", action="store_true", help="sans filtre de silence")
    args = parser.parse_args(argv)

    if args.action == "prepare":
        whisper(args.model, args.models_dir)
        return 0

    if args.action == "transcribe":
        model = whisper(args.model, args.models_dir)
        segments, _info = model.transcribe(load_wav(args.audio), language="fr", beam_size=1, vad_filter=not args.no_vad,
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
