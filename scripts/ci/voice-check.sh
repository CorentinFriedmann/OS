#!/usr/bin/env bash
# CI : essai réel de la voix de Nova. Piper prononce une phrase en français, puis
# faster-whisper doit la retrouver (installation complète dans un dossier temporaire).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
export XDG_DATA_HOME="$work/data" XDG_CONFIG_HOME="$work/config"
python3 - "$work/phrase.wav" <<'PY'
import subprocess, sys, wave
sys.path.insert(0, "assistant")
from nova_ai import voice

assert voice.install(lambda text: print(text, flush=True)), "installation de la voix impossible"
onnx, _meta = voice.voice_files(voice.DEFAULT_VOICE)
phrase = "Bonjour Nova, ouvre le navigateur et baisse le son."
spoken = subprocess.run([str(voice.env_python()), str(voice.WORKER), "speak", "--voice", str(onnx), "--out", sys.argv[1]],
                        input=phrase, text=True, capture_output=True)
print(f"Synthèse : code {spoken.returncode}\n{spoken.stderr[-2000:]}")
with wave.open(sys.argv[1]) as wav:
    seconds = wav.getnframes() / wav.getframerate()
    print(f"Audio : {seconds:.1f} s, {wav.getframerate()} Hz, {wav.getnchannels()} canal(aux), {8 * wav.getsampwidth()} bits")
assert seconds > 1, "la synthèse vocale n'a rien produit"

heard = voice.transcribe(voice.Path(sys.argv[1]))
print(f"Phrase prononcée : {phrase}\nPhrase comprise  : {heard!r}")
if not heard:
    print(f"Erreur : {voice.last_error or 'aucune'}")
    print((voice.voice_dir() / "derniere-erreur.txt").read_text()[-3000:] if (voice.voice_dir() / "derniere-erreur.txt").exists() else "")
    heard = voice.transcribe(voice.Path(sys.argv[1]), vad=False)
    print(f"Sans filtre de silence : {heard!r} {voice.last_error}")
words = [w for w in ("nova", "navigateur", "son") if w in heard.lower()]
assert len(words) >= 2, f"transcription trop éloignée : {heard!r}"
print("✓ La voix de Nova parle et comprend le français")
PY
