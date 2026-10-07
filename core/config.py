import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
LEGACY_PROFILES_PATH = Path(__file__).resolve().parent.parent / "profiles.json"

DEFAULT_BUTTONS = [
    {"id": 0, "title": "Chrome", "color": "#1A73E8", "icon": "ie.png", "action_type": "app", "payload": "chrome"},
    {"id": 1, "title": "YouTube", "color": "#EA4335", "icon": "media_player.png", "action_type": "url", "payload": "https://www.youtube.com"},
    {"id": 2, "title": "GitHub", "color": "#24292E", "icon": "cmd.png", "action_type": "url", "payload": "https://github.com"},
    {"id": 3, "title": "Vol Mute", "color": "#757575", "icon": "vol_mute.png", "action_type": "media", "payload": "volume_mute"},
    {"id": 4, "title": "Vol Down", "color": "#5F6368", "icon": "vol_down.png", "action_type": "media", "payload": "volume_down"},
    {"id": 5, "title": "Vol Up", "color": "#34A853", "icon": "vol_up.png", "action_type": "media", "payload": "volume_up"},
    {"id": 6, "title": "Play/Pause", "color": "#FBBC04", "icon": "play.png", "action_type": "media", "payload": "play_pause"},
    {"id": 7, "title": "Calculator", "color": "#8E24AA", "icon": "calc.png", "action_type": "app", "payload": "calc"},
    {"id": 8, "title": "Notepad", "color": "#00897B", "icon": "notepad.png", "action_type": "app", "payload": "notepad"},
    {"id": 9, "title": "Typing Macro", "color": "#E91E63", "icon": "typing.png", "action_type": "typing", "payload": "Hello from TailDeck!"},
    {"id": 10, "title": "Show Desktop", "color": "#3949AB", "icon": "desktop.png", "action_type": "hotkey", "payload": "win+d"},
    {"id": 11, "title": "Lock PC", "color": "#D32F2F", "icon": "lock.png", "action_type": "system", "payload": "lock"},
]

DEFAULT_CONFIG_DATA = {
    "grid_rows": 3,
    "grid_cols": 4,
    "buttons": DEFAULT_BUTTONS
}


class ConfigManager:
    def __init__(self, filepath: Optional[Path] = None):
        self.filepath = filepath or DEFAULT_CONFIG_PATH
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        target = self.filepath
        # filepath가 기본값이고 아직 없는데 레거시 profiles.json이 존재하는 경우 마이그레이션
        if not target.exists() and self.filepath == DEFAULT_CONFIG_PATH and LEGACY_PROFILES_PATH.exists():
            target = LEGACY_PROFILES_PATH

        if not target.exists():
            self.data = json.loads(json.dumps(DEFAULT_CONFIG_DATA))
            self.save()
        else:
            try:
                with open(target, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                # 이전 버전의 profiles 구조가 있는 경우 마이그레이션
                if "profiles" in raw:
                    pname = raw.get("current_profile", "Default")
                    pdata = raw["profiles"].get(pname, raw["profiles"].get("Default", {}))
                    self.data = {
                        "grid_rows": pdata.get("grid_rows", 3),
                        "grid_cols": pdata.get("grid_cols", 4),
                        "buttons": pdata.get("buttons", DEFAULT_BUTTONS)
                    }
                    self.save()
                else:
                    self.data = raw
                    if target != self.filepath:
                        self.save()
            except Exception as e:
                print(f"[ConfigManager] Failed to load config, resetting: {e}")
                self.data = json.loads(json.dumps(DEFAULT_CONFIG_DATA))
                self.save()
        return self.data

    def save(self) -> bool:
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[ConfigManager] Save error: {e}")
            return False

    def get_buttons(self) -> list:
        return self.data.get("buttons", [])

    def get_button(self, button_id: int) -> Optional[Dict[str, Any]]:
        for b in self.data.get("buttons", []):
            if b.get("id") == button_id:
                return b
        return None

    def update_button(self, button_id: int, button_data: Dict[str, Any]) -> bool:
        buttons = self.data.setdefault("buttons", [])
        for idx, b in enumerate(buttons):
            if b.get("id") == button_id:
                button_data["id"] = button_id
                buttons[idx] = button_data
                self.save()
                return True
        # 없으면 추가
        button_data["id"] = button_id
        buttons.append(button_data)
        self.save()
        return True
