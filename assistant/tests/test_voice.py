from __future__ import annotations

import subprocess
import sys

from nova_ai import voice


class Recorded:
    """Remplace subprocess.run : garde les commandes, peut renvoyer une sortie."""

    def __init__(self, stdout: str = "", fail_on: str | None = None):
        self.calls: list[list[str]] = []
        self.stdout = stdout
        self.fail_on = fail_on

    def __call__(self, argv, **kwargs):
        self.calls.append([str(a) for a in argv])
        if self.fail_on and any(self.fail_on in str(a) for a in argv):
            raise subprocess.CalledProcessError(1, argv)
        return subprocess.CompletedProcess(argv, 0, self.stdout, "")


def fake_install(home):
    python = voice.env_python()
    python.parent.mkdir(parents=True)
    python.write_text("")
    onnx, meta = voice.voice_files(voice.DEFAULT_VOICE)
    onnx.parent.mkdir(parents=True)
    onnx.write_text("")
    meta.write_text("{}")


def test_speech_text_drops_code_links_and_markup():
    text = ("**Voici** la [doc](https://exemple.fr) :\n```python\nprint(1)\n```\n"
            "- point un\n- `ls -l` puis https://x.y/z")
    spoken = voice.speech_text(text)
    assert "print" not in spoken and "https" not in spoken and "*" not in spoken and "`" not in spoken
    assert "Voici la doc" in spoken and "voir le code à l'écran" in spoken and "ls -l" in spoken


def test_speech_text_is_cut_at_a_sentence():
    text = "Première phrase. " * 80
    spoken = voice.speech_text(text, limit=200)
    assert len(spoken) < 260 and spoken.endswith("La suite est à l'écran.")


def test_piper_voice_url():
    assert voice._voice_url("fr_FR-siwis-medium", ".onnx") == (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx")


def test_model_follows_memory(isolated_home, monkeypatch):
    monkeypatch.setattr(voice, "total_memory_gb", lambda: 8.0)
    assert voice.stt_model() == "base"
    monkeypatch.setattr(voice, "total_memory_gb", lambda: 16.0)
    assert voice.stt_model() == "small"


def test_install_creates_env_downloads_voice_and_model(isolated_home, monkeypatch):
    downloads = []
    monkeypatch.setattr(voice, "_download", lambda url, target, progress: (downloads.append(url), target.parent.mkdir(parents=True, exist_ok=True), target.write_text("x")))
    monkeypatch.setattr(voice, "total_memory_gb", lambda: 16.0)
    runner = Recorded()
    messages = []
    assert voice.install(messages.append, runner=runner)
    assert runner.calls[0][:3] == [sys.executable, "-m", "venv"]
    assert "faster-whisper>=1.1,<2" in runner.calls[1] and "piper-tts>=1.2,<2" in runner.calls[1]
    assert runner.calls[2][1].endswith("voice_worker.py") and runner.calls[2][2] == "prepare" and "small" in runner.calls[2]
    assert {url.rsplit("/", 1)[1] for url in downloads} == {"fr_FR-siwis-medium.onnx", "fr_FR-siwis-medium.onnx.json"}
    assert messages[-1].startswith("✓")


def test_install_failure_is_reported(isolated_home, monkeypatch):
    messages = []
    assert not voice.install(messages.append, runner=Recorded(fail_on="pip"))
    assert messages[-1].startswith("✗")


def test_transcribe_uses_worker_only_when_installed(isolated_home, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"")
    runner = Recorded(stdout="  ouvre   Firefox \n")
    assert voice.transcribe(wav, runner=runner) == "" and runner.calls == []
    fake_install(isolated_home)
    assert voice.transcribe(wav, runner=runner) == "ouvre Firefox"
    assert runner.calls[0][2:4] == ["transcribe", str(wav)]
