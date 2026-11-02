"""Tests des outils : commandes produites, garde-fous de sécurité."""
from __future__ import annotations

import json

import pytest

from nova_ai.runner import Completed
from nova_ai.tools import Registry, ToolContext, default_registry
from nova_ai.tools import desktop, files, memory, packages, shell


def ctx_for(runner, config, home, backend="local"):
    return ToolContext(runner=runner, config=config, backend=backend, home=home, data_dir=home / ".local/share/nova")


def test_registry_and_confirmation_policy(config):
    registry = default_registry()
    names = {t.name for t in registry.for_backend("cloud")}
    assert {"launch_app", "run_command", "take_screenshot", "remember", "system_status"} <= names
    assert "take_screenshot" not in {t.name for t in registry.for_backend("local")}  # pas de vision en local
    run_command = registry.get("run_command")
    read_file = registry.get("read_text_file")
    launch = registry.get("launch_app")
    assert Registry.needs_confirmation(run_command, "local", config)
    assert not Registry.needs_confirmation(launch, "local", config)
    assert Registry.needs_confirmation(read_file, "cloud", config)  # données perso vers le cloud
    assert not Registry.needs_confirmation(read_file, "local", config)
    config["confirm"]["action"] = "always"
    assert Registry.needs_confirmation(launch, "local", config)
    # Tous les schémas sont stricts (exigé par le mode « strict » de Claude)
    for tool in registry.for_backend("cloud"):
        assert tool.parameters["additionalProperties"] is False
        assert "minimum" not in json.dumps(tool.parameters)


def test_launch_app_finds_localized_entries(tmp_path, runner, config, isolated_home, monkeypatch):
    apps = tmp_path / "share" / "applications"
    apps.mkdir(parents=True)
    (apps / "org.gnome.Nautilus.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Files\nName[fr]=Fichiers\nExec=nautilus --new-window %U\n", encoding="utf-8")
    (apps / "firefox.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Firefox\nGenericName=Web Browser\nGenericName[fr]=Navigateur web\nExec=firefox %u\n",
        encoding="utf-8")
    (apps / "hidden.desktop").write_text("[Desktop Entry]\nType=Application\nName=Caché\nNoDisplay=true\nExec=x\n", encoding="utf-8")
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "share"))
    ctx = ctx_for(runner, config, isolated_home)
    assert desktop.launch_app({"name": "fichiers"}, ctx).ok
    assert runner.spawned[-1] == ["gtk-launch", "org.gnome.Nautilus"]
    assert desktop.launch_app({"name": "navigateur"}, ctx).ok
    assert runner.spawned[-1] == ["gtk-launch", "firefox"]
    result = desktop.launch_app({"name": "caché"}, ctx)
    assert not result.ok
    runner.available = ()
    assert desktop.launch_app({"name": "firefox"}, ctx).ok
    assert runner.spawned[-1] == ["firefox"]  # Exec sans les codes %u


def test_volume_brightness_media(runner, config, isolated_home):
    ctx = ctx_for(runner, config, isolated_home)
    assert desktop.volume({"action": "set", "percent": 40}, ctx).ok
    assert runner.calls[0] == ["wpctl", "set-volume", "-l", "1.5", "@DEFAULT_AUDIO_SINK@", "40%"]
    desktop.volume({"action": "down"}, ctx)
    assert ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "10%-"] in runner.calls
    assert not desktop.volume({"action": "set", "percent": 400}, ctx).ok
    assert desktop.brightness({"action": "up", "percent": 20}, ctx).ok
    assert ["brightnessctl", "-e4", "-n2", "set", "20%+"] in runner.calls
    assert desktop.media_control({"action": "play_pause"}, ctx).ok
    assert ["playerctl", "play-pause"] in runner.calls


def test_window_action_builds_lua_dispatchers(config, isolated_home):
    from tests.conftest import FakeRunner

    clients = [{"class": "firefox", "title": "Wikipédia", "address": "0xabc", "workspace": {"name": "1"}},
               {"class": "com.mitchellh.ghostty", "title": "fish", "address": "0xdef", "workspace": {"name": "2"}}]
    runner = FakeRunner({("hyprctl", "-j", "clients"): json.dumps(clients)})
    ctx = ctx_for(runner, config, isolated_home)
    assert desktop.window_action({"action": "move_to_workspace", "target": "firefox", "workspace": 3}, ctx).ok
    assert runner.calls[-1] == ["hyprctl", "dispatch", 'hl.dsp.window.move({ workspace = 3, window = "address:0xabc" })']
    desktop.window_action({"action": "close", "target": "ghostty"}, ctx)
    assert runner.calls[-1][-1] == 'hl.dsp.window.close({window = "address:0xdef"})'
    desktop.window_action({"action": "switch_workspace", "workspace": 2}, ctx)
    assert runner.calls[-1][-1] == "hl.dsp.focus({ workspace = 2 })"
    assert not desktop.window_action({"action": "switch_workspace", "workspace": 42}, ctx).ok
    assert not desktop.window_action({"action": "focus", "target": "inexistant"}, ctx).ok


def test_reminder_uses_systemd_timer(runner, config, isolated_home):
    result = desktop.set_reminder({"minutes": 15, "text": "Sortir les pâtes"}, ctx_for(runner, config, isolated_home))
    assert result.ok and "Sortir les pâtes" in result.content
    argv = runner.calls[-1]
    assert argv[:3] == ["systemd-run", "--user", "--on-active=15m"] and argv[-1] == "Sortir les pâtes"
    assert not desktop.set_reminder({"minutes": 0, "text": "x"}, ctx_for(runner, config, isolated_home)).ok


@pytest.mark.parametrize("command", [
    "rm -rf /", "sudo rm -rf --no-preserve-root /", "rm -fr ~", ":(){ :|:& };:",
    "mkfs.ext4 /dev/nvme0n1p2", "dd if=/dev/zero of=/dev/sda bs=1M", "cat x > /dev/nvme0n1",
])
def test_shell_blocks_catastrophic_commands(command, runner, config, isolated_home):
    result = shell.run_command({"command": command, "reason": "test"}, ctx_for(runner, config, isolated_home))
    assert not result.ok and "refusée" in result.content
    assert runner.calls == []


def test_shell_runs_and_flags_risky(config, isolated_home):
    from tests.conftest import FakeRunner

    runner = FakeRunner({("bash", "-lc"): Completed(0, "hello\n", "")})
    result = shell.run_command({"command": "echo hello", "reason": "test"}, ctx_for(runner, config, isolated_home))
    assert result.ok and "hello" in result.content
    shell.run_command({"command": "systemctl restart bluetooth", "reason": "r", "as_root": True},
                      ctx_for(runner, config, isolated_home))
    assert runner.calls[-1][:2] == ["pkexec", "bash"]
    assert "⚠" in shell.TOOLS[0].confirmation_text({"command": "rm -r ~/tmp/vieux", "reason": "ménage"})
    assert "⚠" not in shell.TOOLS[0].confirmation_text({"command": "ls ~", "reason": "liste"})


def test_file_reading_guards(runner, config, isolated_home):
    (isolated_home / "notes.txt").write_text("Liste de courses : café", encoding="utf-8")
    (isolated_home / ".ssh").mkdir()
    (isolated_home / ".ssh" / "id_ed25519").write_text("SECRET", encoding="utf-8")
    (isolated_home / "image.bin").write_bytes(b"\x00\x01\x02")
    ctx = ctx_for(runner, config, isolated_home)
    assert files.read_text_file({"path": "~/notes.txt"}, ctx).content == "Liste de courses : café"
    secret = files.read_text_file({"path": "~/.ssh/id_ed25519"}, ctx)
    assert not secret.ok and "SECRET" not in secret.content
    assert not files.read_text_file({"path": "/root/.bashrc"}, ctx).ok
    assert not files.read_text_file({"path": "~/image.bin"}, ctx).ok
    assert not files.read_text_file({"path": "~/absent.txt"}, ctx).ok
    (isolated_home / "lien").symlink_to(isolated_home / ".ssh" / "id_ed25519")
    assert not files.read_text_file({"path": "~/lien"}, ctx).ok  # pas de contournement par lien


def test_search_files_uses_fd(config, isolated_home):
    from tests.conftest import FakeRunner

    runner = FakeRunner({("fd",): f"{isolated_home}/Documents/facture.pdf\n"})
    result = files.search_files({"query": "facture", "kind": "file"}, ctx_for(runner, config, isolated_home))
    assert result.content == "~/Documents/facture.pdf"
    assert runner.calls[-1][:6] == ["fd", "--ignore-case", "--max-results", "20", "--type", "f"]


def test_packages(config, isolated_home):
    from tests.conftest import FakeRunner

    output = "extra/firefox 144.0-1 [installed]\n    Fast, Private & Safe Web Browser\nextra/chromium 142.0-1\n    A web browser\n"
    runner = FakeRunner({("pacman", "-Ss"): output})
    ctx = ctx_for(runner, config, isolated_home)
    found = packages.search_packages({"query": "browser"}, ctx)
    assert "extra/firefox 144.0-1 [installé] — Fast, Private & Safe Web Browser" in found.content
    assert not packages.install_packages({"packages": ["vlc; rm -rf /"], "reason": "x"}, ctx).ok
    assert packages.install_packages({"packages": ["vlc", "obs-studio"], "reason": "vidéo"}, ctx).ok
    assert runner.calls[-1] == ["pkexec", "pacman", "-S", "--needed", "--noconfirm", "vlc", "obs-studio"]


def test_memory_tools(runner, config, isolated_home):
    ctx = ctx_for(runner, config, isolated_home)
    assert memory.remember({"fact": "L'utilisateur s'appelle Corentin"}, ctx).ok
    assert "déjà" in memory.remember({"fact": "l'utilisateur s'appelle corentin"}, ctx).content
    memory.remember({"fact": "Préfère le mode sombre"}, ctx)
    assert "Corentin" in memory.recall({"query": "appelle"}, ctx).content
    assert memory.forget({"query": "sombre"}, ctx).content.startswith("1")
    assert memory.recent_facts(path=isolated_home / ".local/share/nova/memory.json") == ["L'utilisateur s'appelle Corentin"]
