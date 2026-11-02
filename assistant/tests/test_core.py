"""Tests : validation, routage, conversation, configuration."""
from __future__ import annotations

import os

from nova_ai import config as cfgmod
from nova_ai import router
from nova_ai.conversation import Conversation
from nova_ai.schema import obj, validate


def test_schema_validation():
    schema = obj({"action": {"type": "string", "enum": ["up", "down"]}, "percent": {"type": "integer"},
                  "tags": {"type": "array", "items": {"type": "string"}}}, ["action"])
    assert validate({"action": "up", "percent": 10, "tags": ["a"]}, schema) == []
    assert any("requis" in e for e in validate({}, schema))
    assert any("hors de" in e for e in validate({"action": "left"}, schema))
    assert any("inattendu" in e for e in validate({"action": "up", "evil": 1}, schema))
    assert any("type attendu integer" in e for e in validate({"action": "up", "percent": True}, schema))
    assert any("[1]" in e for e in validate({"action": "up", "tags": ["a", 2]}, schema))
    assert validate("pas un objet", schema)


def test_router_auto_mode(config):
    choose = router.choose
    assert choose("ouvre firefox", config, True, True).backend == "local"
    assert choose("monte le son", config, True, True).backend == "local"
    assert choose("cherche la météo de demain à Lyon", config, True, True).backend == "cloud"
    assert choose("écris-moi un script python qui trie des fichiers", config, True, True).backend == "cloud"
    assert choose("qu'est-ce que tu vois sur mon écran ?", config, True, True).backend == "cloud"
    assert choose("x" * 600, config, True, True).backend == "cloud"
    # suite d'une discussion cloud récente
    assert choose("et en plus court ?", config, True, True, "cloud", 30).backend == "cloud"
    assert choose("et en plus court ?", config, True, True, "cloud", 3600).backend == "local"


def test_router_availability_and_overrides(config):
    assert router.choose("cherche les news", config, True, False).backend == "local"  # pas de clé
    assert router.choose("ouvre firefox", config, False, True).backend == "cloud"  # Ollama absent
    decision = router.choose("/cloud ouvre firefox", config, True, True)
    assert decision.backend == "cloud" and decision.text == "ouvre firefox"
    assert router.choose("/local cherche les news", config, True, True).backend == "local"
    strict = {**config, "privacy": {"strict_local": True}}
    assert router.choose("cherche les news", strict, True, True).backend == "local"
    assert router.choose("bonjour", {**config, "mode": "cloud"}, True, True).backend == "cloud"


def test_conversation_claude_format_is_append_only_and_valid():
    conv = Conversation()
    conv.add_user("monte le son", "Contexte : lundi")
    raw = [{"type": "thinking", "thinking": "", "signature": "sig=="},
           {"type": "tool_use", "id": "toolu_1", "name": "volume", "input": {"action": "up"}}]
    conv.add_assistant("cloud", "", [{"id": "toolu_1", "name": "volume", "arguments": {"action": "up"}}],
                       raw=raw, final=False)
    conv.add_tool_results("cloud", [{"id": "toolu_1", "name": "volume", "ok": True, "content": "ok"}])
    conv.add_assistant("cloud", "C'est fait !", raw=[{"type": "text", "text": "C'est fait !"}])
    conv.add_user("ouvre steam", "Contexte : lundi bis")
    conv.add_assistant("local", "", [{"id": "local_0", "name": "launch_app", "arguments": {"name": "steam"}}], final=False)
    conv.add_tool_results("local", [{"id": "local_0", "name": "launch_app", "ok": True, "content": "Steam est lancé."}])
    conv.add_assistant("local", "Steam démarre !")
    conv.add_user("merci", "Contexte : lundi ter")

    messages = conv.to_claude(supports_system_messages=True)
    roles = [m["role"] for m in messages]
    assert roles == ["user", "system", "assistant", "user", "assistant", "user", "system", "assistant", "user", "system"]
    assert messages[2]["content"] is raw  # blocs de Claude renvoyés tels quels (signature incluse)
    assert messages[3]["content"][0] == {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}
    assert "launch_app" in messages[7]["content"]  # tour local résumé pour Claude
    # chaque message « system » suit un message utilisateur
    for index, message in enumerate(messages):
        if message["role"] == "system":
            assert messages[index - 1]["role"] == "user"

    no_sys = conv.to_claude(supports_system_messages=False)
    assert all(m["role"] != "system" for m in no_sys)
    assert no_sys[0]["content"].startswith("[Contexte : lundi]")


def test_conversation_ollama_format():
    conv = Conversation()
    conv.add_user("ouvre steam", "ctx1")
    conv.add_assistant("local", "", [{"id": "local_0", "name": "launch_app", "arguments": {"name": "steam"}}], final=False)
    conv.add_tool_results("local", [{"id": "local_0", "name": "launch_app", "ok": True, "content": "Steam est lancé."}])
    conv.add_assistant("local", "C'est parti.")
    conv.add_user("et la météo ?", "ctx2")
    messages = conv.to_ollama("SYSTEM")
    assert messages[0] == {"role": "system", "content": "SYSTEM"}
    assert {"role": "system", "content": "ctx1"} not in messages  # seul le contexte actuel est gardé
    assert {"role": "system", "content": "ctx2"} in messages
    tool_msg = next(m for m in messages if m["role"] == "tool")
    assert tool_msg == {"role": "tool", "content": "Steam est lancé.", "tool_name": "launch_app"}
    assistant = next(m for m in messages if m.get("tool_calls"))
    assert assistant["tool_calls"][0]["function"] == {"name": "launch_app", "arguments": {"name": "steam"}}
    trimmed = conv.to_ollama("S", max_messages=2)
    assert trimmed[1]["role"] in ("user", "system")


def test_config_roundtrip_and_secrets(tmp_path):
    cfg = cfgmod.load_config(tmp_path / "absent.toml")
    assert cfg["mode"] == "auto" and cfg["cloud"]["model"] == "claude-opus-5-5"
    cfg["mode"] = "cloud"
    cfg["local"]["model"] = 'qwen3:"8b"'
    path = cfgmod.save_config(cfg, tmp_path / "a.toml")
    again = cfgmod.load_config(path)
    assert again["mode"] == "cloud" and again["local"]["model"] == 'qwen3:"8b"'
    assert again["privacy"]["confirm_private_in_cloud"] is True
    key_path = cfgmod.save_api_key("sk-ant-test-123")
    assert oct(os.stat(key_path).st_mode & 0o777) == "0o600"
    assert cfgmod.get_api_key() == "sk-ant-test-123"
    (tmp_path / "broken.toml").write_text("mode = [", encoding="utf-8")
    assert cfgmod.load_config(tmp_path / "broken.toml")["mode"] == "auto"


def test_recommended_model():
    assert cfgmod.recommended_local_model(8) == "qwen3:1.7b"
    assert cfgmod.recommended_local_model(16) == "qwen3:4b"
    assert cfgmod.recommended_local_model(32) == "qwen3:8b"
