#!/usr/bin/env bash
# CI : essai réel de la voix de Nova. Piper prononce une phrase en français, puis
# faster-whisper doit la retrouver (installation complète dans un dossier temporaire).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
export XDG_DATA_HOME="$work/data" XDG_CONFIG_HOME="$work/config"
python3 - "$work/phrase.wav" <<'PY'
import subprocess, sys
sys.path.insert(0, "assistant")
from nova_ai import voice

assert voice.install(lambda text: print(text, flush=True)), "installation de la voix impossible"
onnx, _meta = voice.voice_files(voice.DEFAULT_VOICE)
phrase = "Bonjour Nova, ouvre le navigateur et baisse le son."
subprocess.run([str(voice.env_python()), str(voice.WORKER), "speak", "--voice", str(onnx), "--out", sys.argv[1]],
               input=phrase, text=True, check=True)
heard = voice.transcribe(voice.Path(sys.argv[1]))
print(f"Phrase prononcée : {phrase}\nPhrase comprise  : {heard}")
words = [w for w in ("nova", "navigateur", "son") if w in heard.lower()]
assert len(words) >= 2, f"transcription trop éloignée : {heard!r}"
print("✓ La voix de Nova parle et comprend le français")
PY
