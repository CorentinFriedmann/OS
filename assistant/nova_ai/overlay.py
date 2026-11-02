"""Nova IA — fenêtre flottante néon (Super+Espace).

`nova-assistant [toggle|show|hide|welcome|setup]` : une seule instance
(Gtk.Application), les appels suivants la pilotent.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402
except (ValueError, ImportError):
    LayerShell = None

from .client import DaemonUnavailable, NovaClient  # noqa: E402

APP_ID = "os.nova.Assistant"
DEBUG = bool(os.environ.get("NOVA_DEBUG"))
LOGO = next((p for p in ("/usr/share/pixmaps/nova-logo.png",
                         str(Path(__file__).resolve().parents[2] / "branding/logo/nova-64.png")) if os.path.exists(p)), "")
SUGGESTIONS = ["Passe en mode éco", "Ouvre Firefox", "Quel temps fera-t-il demain ?", "Que vois-tu sur mon écran ?"]
MODES = ["auto", "local", "cloud"]
MODE_LABELS = {"auto": "Auto", "local": "Local", "cloud": "Cloud"}

CSS = """
window.nova-overlay { background: transparent; }
.nova-card {
  background: rgba(8, 10, 22, 0.88);
  border-radius: 24px;
  border: 1px solid rgba(0, 240, 255, 0.35);
  box-shadow: 0 0 26px rgba(0, 240, 255, 0.18), 0 0 70px rgba(138, 92, 255, 0.16);
  padding: 16px 18px 18px 18px;
  margin: 28px;
}
.nova-title {
  font-family: "Orbitron", sans-serif; font-weight: 900; font-size: 16px;
  letter-spacing: 4px; color: #e6f1ff;
  text-shadow: 0 0 8px rgba(0, 240, 255, 0.9);
}
.nova-badge { border-radius: 999px; padding: 2px 10px; font-size: 11px; font-weight: 700; }
.nova-badge.local { background: rgba(61, 255, 168, 0.10); color: #3dffa8; border: 1px solid rgba(61, 255, 168, 0.4); }
.nova-badge.cloud { background: rgba(255, 43, 214, 0.10); color: #ff2bd6; border: 1px solid rgba(255, 43, 214, 0.45); }
.nova-badge.offline { background: rgba(74, 83, 120, 0.2); color: #8b95b8; border: 1px solid rgba(74, 83, 120, 0.6); }
button.nova-flat {
  background: rgba(255, 255, 255, 0.04); color: #8b95b8; border-radius: 10px;
  border: 1px solid rgba(138, 92, 255, 0.25); min-height: 28px; padding: 0 10px; font-size: 12px;
}
button.nova-flat:hover { color: #e6f1ff; border-color: rgba(0, 240, 255, 0.5); background: rgba(0, 240, 255, 0.08); }
.bubble { border-radius: 16px; padding: 10px 14px; font-size: 14px; }
.bubble.user {
  background: linear-gradient(135deg, rgba(255, 43, 214, 0.22), rgba(138, 92, 255, 0.22));
  border: 1px solid rgba(255, 43, 214, 0.35); color: #ffffff;
}
.bubble.nova { background: rgba(0, 240, 255, 0.05); border: 1px solid rgba(0, 240, 255, 0.20); color: #e6f1ff; }
.meta { color: #4a5378; font-size: 11px; }
.chip { border-radius: 10px; padding: 3px 10px; background: rgba(138, 92, 255, 0.14); color: #c8b8ff; font-size: 12px; }
.chip.ok { color: #3dffa8; background: rgba(61, 255, 168, 0.08); }
.chip.fail { color: #ff3860; background: rgba(255, 56, 96, 0.08); }
.chip.web { color: #00f0ff; background: rgba(0, 240, 255, 0.08); }
.notice { color: #ffd23f; font-size: 12px; }
.error { color: #ff3860; font-size: 13px; }
.thinking { color: #00f0ff; font-size: 13px; letter-spacing: 3px; }
.confirm { border-radius: 14px; padding: 12px 14px; background: rgba(255, 210, 63, 0.07); border: 1px solid rgba(255, 210, 63, 0.5); }
.confirm.sensitive { background: rgba(255, 56, 96, 0.07); border-color: rgba(255, 56, 96, 0.6); }
.confirm-title { font-weight: 800; color: #ffd23f; }
.confirm.sensitive .confirm-title { color: #ff3860; }
.confirm-body { font-family: "JetBrainsMono Nerd Font", monospace; font-size: 12px; color: #e6f1ff; }
button.allow { background: linear-gradient(135deg, #00f0ff, #8a5cff); color: #05060d; font-weight: 800; border-radius: 10px; border: none; }
button.deny { background: rgba(255, 255, 255, 0.05); color: #e6f1ff; border-radius: 10px; border: 1px solid rgba(255, 56, 96, 0.5); }
button.suggestion {
  background: rgba(0, 240, 255, 0.06); color: #9fe9ff; border-radius: 999px;
  border: 1px solid rgba(0, 240, 255, 0.25); padding: 2px 12px; font-size: 12px; min-height: 26px;
}
button.suggestion:hover { background: rgba(0, 240, 255, 0.16); color: #ffffff; }
entry.nova-entry {
  min-height: 46px; border-radius: 14px; background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(0, 240, 255, 0.30); color: #e6f1ff; font-size: 15px; padding: 0 14px;
  caret-color: #00f0ff; box-shadow: none; outline: none;
}
entry.nova-entry:focus-within { border-color: #00f0ff; box-shadow: 0 0 14px rgba(0, 240, 255, 0.35); }
button.nova-send {
  min-width: 46px; min-height: 46px; border-radius: 14px; border: none;
  background: linear-gradient(135deg, #00f0ff, #8a5cff); color: #05060d; font-size: 18px; font-weight: 900;
}
button.nova-mic {
  min-width: 46px; min-height: 46px; border-radius: 14px; color: #ff2bd6;
  background: rgba(255, 43, 214, 0.08); border: 1px solid rgba(255, 43, 214, 0.35); font-size: 17px;
}
button.nova-mic.recording { background: rgba(255, 43, 214, 0.35); color: #ffffff; }
"""


def markdown_to_pango(text: str) -> str:
    """Markdown léger (gras, italique, code, listes, titres) vers le balisage Pango."""
    parts = re.split(r"```[^\n]*\n?(.*?)```", text, flags=re.S)
    out: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 1:  # bloc de code
            code = GLib.markup_escape_text(part.rstrip("\n"))
            out.append(f'<span font_family="JetBrainsMono Nerd Font" background="#0d1124" foreground="#9fe9ff">{code}</span>')
            continue
        escaped = GLib.markup_escape_text(part)
        escaped = re.sub(r"`([^`\n]+)`", r'<span font_family="JetBrainsMono Nerd Font" foreground="#00f0ff">\1</span>', escaped)
        escaped = re.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", escaped)
        escaped = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?!\w)", r"<i>\1</i>", escaped)
        escaped = re.sub(r"(?m)^#{1,6}\s+(.+)$", r'<span foreground="#ff2bd6"><b>\1</b></span>', escaped)
        escaped = re.sub(r"(?m)^\s*[-*]\s+", "  • ", escaped)
        out.append(escaped)
    return "".join(out).strip()


class Turn:
    """Réponse en cours de Nova (texte en flux + puces d'outils)."""

    def __init__(self, window: "AssistantWindow"):
        self.window = window
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.meta = Gtk.Label(xalign=0, css_classes=["meta"])
        self.box.append(self.meta)
        self.thinking = Gtk.Label(label="● ● ●", xalign=0, css_classes=["thinking"])
        self.box.append(self.thinking)
        self.text = ""
        self.label: Gtk.Label | None = None
        self.chips: dict[str, Gtk.Label] = {}

    def _ensure_label(self) -> Gtk.Label:
        if self.label is None:
            holder, self.label = self.window.bubble("", "nova")
            self.box.append(holder)
        return self.label

    def append_text(self, delta: str) -> None:
        self.thinking.set_visible(False)
        self.text += delta
        self._ensure_label().set_text(self.text)

    def seal(self) -> None:
        """Termine la bulle en cours : le texte suivant (après une action) ira dans une nouvelle bulle."""
        if self.label is not None and self.text:
            self.label.set_markup(markdown_to_pango(self.text))
        self.label, self.text = None, ""

    def chip(self, key: str, text: str, css: str = "") -> None:
        if key not in self.chips:
            self.seal()
        label = self.chips.get(key)
        if label is None:
            label = Gtk.Label(xalign=0, halign=Gtk.Align.START, css_classes=["chip"] + ([css] if css else []))
            self.chips[key] = label
            self.box.append(label)
        else:
            label.set_css_classes(["chip"] + ([css] if css else []))
        label.set_text(text)

    def message(self, text: str, css: str) -> None:
        self.thinking.set_visible(False)
        self.box.append(Gtk.Label(label=text, xalign=0, wrap=True, css_classes=[css]))

    def finish(self) -> None:
        self.thinking.set_visible(False)
        self.seal()


class AssistantWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Nova IA", css_classes=["nova-overlay"])
        self.set_default_size(760, -1)
        self.set_decorated(False)
        self.client = NovaClient()
        self.mode = "auto"
        self.busy = False
        self.turn: Turn | None = None
        self.welcomed = False
        self._setup_layer_shell()
        self._build()

    # --- construction -------------------------------------------------------------
    def _setup_layer_shell(self) -> None:
        if LayerShell is None or not LayerShell.is_supported():
            return
        LayerShell.init_for_window(self)
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
        LayerShell.set_namespace(self, "nova-assistant")
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.EXCLUSIVE)
        LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
        LayerShell.set_margin(self, LayerShell.Edge.TOP, 90)

    def _build(self) -> None:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["nova-card"])
        card.set_size_request(720, -1)
        header = Gtk.Box(spacing=10)
        if LOGO:
            logo = Gtk.Image.new_from_file(LOGO)
            logo.set_pixel_size(30)
            header.append(logo)
        header.append(Gtk.Label(label="NOVA", css_classes=["nova-title"]))
        self.badge = Gtk.Label(label="…", css_classes=["nova-badge", "offline"], valign=Gtk.Align.CENTER)
        header.append(self.badge)
        header.append(Gtk.Box(hexpand=True))
        self.mode_button = Gtk.Button(label="Mode : Auto", css_classes=["nova-flat"])
        self.mode_button.set_tooltip_text("Auto : local par défaut, Claude quand c'est utile")
        self.mode_button.connect("clicked", self._cycle_mode)
        header.append(self.mode_button)
        new_button = Gtk.Button(label="Nouvelle discussion", css_classes=["nova-flat"])
        new_button.connect("clicked", lambda *_: self.new_conversation())
        header.append(new_button)
        card.append(header)

        self.messages = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.scroller = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=480,
                                           hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scroller.set_child(self.messages)
        # Défilement automatique : on suit le bas tant que l'utilisateur n'est pas remonté lire
        self._stick_bottom = True
        adjustment = self.scroller.get_vadjustment()
        adjustment.connect("notify::upper", self._on_content_grow)
        adjustment.connect("value-changed", self._on_user_scroll)
        card.append(self.scroller)

        row = Gtk.Box(spacing=8)
        self.entry = Gtk.Entry(hexpand=True, placeholder_text="Demande-moi n'importe quoi…", css_classes=["nova-entry"])
        self.entry.connect("activate", lambda *_: self.send(self.entry.get_text()))
        row.append(self.entry)
        self.mic = Gtk.Button(label="\U000F036C", css_classes=["nova-mic"], tooltip_text="Dicter (voix)")
        self.mic.connect("clicked", self._toggle_voice)
        row.append(self.mic)
        send = Gtk.Button(label="➜", css_classes=["nova-send"], tooltip_text="Envoyer (Entrée)")
        send.connect("clicked", lambda *_: self.send(self.entry.get_text()))
        row.append(send)
        card.append(row)
        self.set_child(card)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

    # --- interactions -----------------------------------------------------------------
    def _on_key(self, _controller, keyval, _keycode, state) -> bool:
        if keyval == Gdk.KEY_Escape:
            if self.busy:
                threading.Thread(target=lambda: self._safe(self.client.request, "cancel"), daemon=True).start()
            else:
                self.set_visible(False)
            return True
        if keyval in (Gdk.KEY_l, Gdk.KEY_L) and state & Gdk.ModifierType.CONTROL_MASK:
            self.new_conversation()
            return True
        return False

    def _cycle_mode(self, *_args) -> None:
        self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
        self.mode_button.set_label(f"Mode : {MODE_LABELS[self.mode]}")

    def _safe(self, func, *args):
        try:
            return func(*args)
        except (DaemonUnavailable, OSError, ValueError):
            return None

    def bubble(self, text: str, kind: str) -> tuple[Gtk.Box, Gtk.Label]:
        """Bulle de discussion. On renvoie aussi le conteneur : en GTK 4, un widget
        sans référence est détruit, il faut donc l'ajouter à l'interface tout de suite."""
        label = Gtk.Label(label=text, xalign=0, wrap=True, selectable=True, css_classes=["bubble", kind])
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        holder = Gtk.Box(halign=Gtk.Align.END if kind == "user" else Gtk.Align.FILL)
        if kind == "user":
            label.set_max_width_chars(60)
        holder.append(label)
        return holder, label

    def _on_content_grow(self, adjustment, _pspec) -> None:
        # Appelé pendant la mise en page : on défile juste après, sinon GTK ignore le changement.
        if self._stick_bottom:
            GLib.idle_add(self._jump_to_bottom)

    def _jump_to_bottom(self) -> bool:
        adjustment = self.scroller.get_vadjustment()
        adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
        return False

    def _on_user_scroll(self, adjustment) -> None:
        bottom = adjustment.get_upper() - adjustment.get_page_size()
        self._stick_bottom = adjustment.get_value() >= bottom - 24

    def scroll_to_end(self) -> None:
        self._stick_bottom = True
        GLib.idle_add(self._jump_to_bottom)

    def refresh_status(self) -> None:
        def work():
            status = self._safe(self.client.request, "status") or {}
            GLib.idle_add(self._apply_status, status)
        threading.Thread(target=work, daemon=True).start()

    def _apply_status(self, status: dict) -> bool:
        local, cloud = status.get("local", {}), status.get("cloud", {})
        if not status:
            self.badge.set_text("hors ligne")
            self.badge.set_css_classes(["nova-badge", "offline"])
        elif local.get("ok"):
            self.badge.set_text(f"🔒 {local.get('model', 'local')}" + ("  ·  ☁ Claude" if cloud.get("ok") else ""))
            self.badge.set_css_classes(["nova-badge", "local"])
        elif cloud.get("ok"):
            self.badge.set_text("☁ Claude")
            self.badge.set_css_classes(["nova-badge", "cloud"])
        else:
            self.badge.set_text("IA non configurée")
            self.badge.set_css_classes(["nova-badge", "offline"])
        return False

    def welcome(self) -> None:
        if self.welcomed:
            return
        self.welcomed = True
        holder, label = self.bubble("", "nova")
        label.set_markup(markdown_to_pango(
            "Salut, je suis **Nova** ✦\n"
            "Je pilote ton PC (applications, son, luminosité, modes de performance), je cherche sur le web, "
            "j'analyse ton écran et je retiens tes préférences. Je travaille en **local** quand c'est possible, "
            "et je fais appel à **Claude** dans le cloud quand c'est utile."))
        self.messages.append(holder)
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4, column_spacing=6, row_spacing=6)
        for suggestion in SUGGESTIONS:
            button = Gtk.Button(label=suggestion, css_classes=["suggestion"])
            button.connect("clicked", lambda _b, s=suggestion: self.send(s))
            flow.append(button)
        self.messages.append(flow)

    def new_conversation(self) -> None:
        if self.busy:
            return
        threading.Thread(target=lambda: self._safe(self.client.request, "reset"), daemon=True).start()
        child = self.messages.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self.messages.remove(child)
            child = following
        self.welcomed = False
        self.welcome()

    def show_now(self) -> None:
        self.set_visible(True)
        self.present()
        self.entry.grab_focus()
        self.refresh_status()

    # --- envoi d'une demande ------------------------------------------------------------
    def send(self, text: str) -> None:
        text = text.strip()
        if not text or self.busy:
            return
        self.entry.set_text("")
        self.busy = True
        holder, _label = self.bubble(text, "user")
        self.messages.append(holder)
        self.turn = Turn(self)
        self.messages.append(self.turn.box)
        self.scroll_to_end()
        mode = None if self.mode == "auto" else self.mode
        threading.Thread(target=self._worker, args=(text, mode), daemon=True).start()

    def _worker(self, text: str, mode: str | None) -> None:
        try:
            self.client.ask(text, lambda event: GLib.idle_add(self.handle_event, event), self._ask_confirmation, mode)
        except (DaemonUnavailable, OSError, ValueError) as error:
            GLib.idle_add(self.handle_event, {"type": "error", "message": str(error)})
            GLib.idle_add(self.handle_event, {"type": "done"})

    def _ask_confirmation(self, request: dict) -> bool:
        decided = threading.Event()
        answer = {"approved": False}
        GLib.idle_add(self._show_confirmation, request, decided, answer)
        decided.wait()
        return answer["approved"]

    def _show_confirmation(self, request: dict, decided: threading.Event, answer: dict) -> bool:
        if DEBUG:
            print(f"[nova-overlay] confirmation demandée : {request}", file=sys.stderr, flush=True)
        sensitive = request.get("risk") == "sensitive"
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["confirm"] + (["sensitive"] if sensitive else []))
        card.append(Gtk.Label(label="Nova demande ton accord", xalign=0, css_classes=["confirm-title"]))
        card.append(Gtk.Label(label=request.get("summary", ""), xalign=0, wrap=True, selectable=True, css_classes=["confirm-body"]))
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        deny = Gtk.Button(label="Refuser", css_classes=["deny"])
        allow = Gtk.Button(label="Autoriser", css_classes=["allow"])

        def decide(approved: bool) -> None:
            answer["approved"] = approved
            card.set_sensitive(False)
            buttons.set_visible(False)
            card.append(Gtk.Label(label="✓ Autorisé" if approved else "✗ Refusé", xalign=0,
                                  css_classes=["chip", "ok" if approved else "fail"]))
            decided.set()

        deny.connect("clicked", lambda *_: decide(False))
        allow.connect("clicked", lambda *_: decide(True))
        buttons.append(deny)
        buttons.append(allow)
        card.append(buttons)
        if self.turn:
            self.turn.seal()
            self.turn.box.append(card)
        allow.grab_focus()
        self.scroll_to_end()
        return False

    def handle_event(self, event: dict) -> bool:
        if DEBUG:
            print(f"[nova-overlay] {event}", file=sys.stderr, flush=True)
        turn, kind = self.turn, event.get("type")
        if turn is None:
            return False
        if kind == "turn_start":
            badge = "🔒 local" if event["backend"] == "local" else "☁ cloud"
            turn.meta.set_text(f"{badge} · {event['model']} — {event.get('reason', '')}")
            css = "local" if event["backend"] == "local" else "cloud"
            self.badge.set_text(f"{'🔒' if css == 'local' else '☁'} {event['model']}")
            self.badge.set_css_classes(["nova-badge", css])
        elif kind == "text":
            turn.append_text(event["text"])
        elif kind == "web_search":
            turn.chip("web", "🌐 Recherche sur le web…", "web")
        elif kind == "tool_start":
            turn.chip(event["id"], f"⚙ {event['label']}…")
        elif kind == "tool_end":
            state = "✓" if event.get("ok") else ("✗ refusé" if event.get("denied") else "✗")
            turn.chip(event["id"], f"⚙ {event['label']}  {state}", "ok" if event.get("ok") else "fail")
        elif kind == "progress":
            turn.chip("progress", event["text"])
        elif kind == "notice":
            turn.message(event["text"], "notice")
        elif kind == "error":
            turn.message(f"✗ {event['message']}", "error")
        elif kind == "done":
            turn.finish()
            self.busy = False
        self.scroll_to_end()
        return False

    # --- voix ---------------------------------------------------------------------------
    def _toggle_voice(self, *_args) -> None:
        from . import voice

        recorder = getattr(self, "_recorder", None)
        if recorder is None:
            ok, why = voice.available()
            if not ok:
                if self.turn is None:
                    self.turn = Turn(self)
                    self.messages.append(self.turn.box)
                self.turn.message(why, "notice")
                return
            self._recorder = voice.Recorder()
            self._recorder.start()
            self.mic.add_css_class("recording")
            return
        self._recorder = None
        self.mic.remove_css_class("recording")

        def work():
            text = recorder.stop_and_transcribe()
            GLib.idle_add(lambda: (self.send(text) if text else None) and False)
        threading.Thread(target=work, daemon=True).start()


class NovaApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window: AssistantWindow | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        if hasattr(provider, "load_from_string"):
            provider.load_from_string(CSS)
        else:
            provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.hold()  # reste en mémoire : réouverture instantanée

    def do_command_line(self, command_line) -> int:
        args = command_line.get_arguments()[1:]
        action = args[0] if args else "toggle"
        if action == "setup":
            subprocess.Popen(["ghostty", "-e", "nova", "setup"], start_new_session=True)
            return 0
        if self.window is None:
            self.window = AssistantWindow(self)
        window = self.window
        if action == "hide" or (action == "toggle" and window.get_visible()):
            window.set_visible(False)
        else:
            window.welcome()
            window.show_now()
            if action == "ask" and len(args) > 1:
                window.send(" ".join(args[1:]))
        return 0


def main() -> int:
    return NovaApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
