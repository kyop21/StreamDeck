import json
import os
import copy
import shutil
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
LEGACY_PROFILES_PATH = Path(__file__).resolve().parent.parent / "profiles.json"

DEFAULT_BUTTONS = [
    {"id": 0, "title": "Chrome", "color": "#1A73E8", "icon": "ie.png", "action_type": "app", "payload": "chrome"},
    {"id": 1, "title": "YouTube", "color": "#EA4335", "icon": "media_player.png", "action_type": "url", "payload": "https://www.youtube.com"},
    {"id": 2, "title": "Ping Test", "color": "#008080", "icon": "network.png", "action_type": "script", "payload": "start cmd /k \"ping 8.8.8.8 -n 4\""},
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

DEFAULT_PROFILE_DATA = {
    "grid_rows": 3,
    "grid_cols": 4,
    "buttons": DEFAULT_BUTTONS
}

DEFAULT_CONFIG_DATA = {
    "schema_version": 2,
    "current_profile": "Default",
    "profiles": {
        "Default": copy.deepcopy(DEFAULT_PROFILE_DATA)
    }
}


class ConfigManager:
    """
    TailDeck 멀티 프로필 설정 관리자.
    - Thread-safe (threading.RLock)
    - schema_version 검증 및 하위 호환 자동 마이그레이션 (기존 루트 키 100% 보존, .bak 생성)
    - Atomic Write (임시 파일 + os.replace)
    """
    def __init__(self, filepath: Optional[Path] = None):
        self._lock = threading.RLock()
        self.filepath = filepath or DEFAULT_CONFIG_PATH
        self.data: Dict[str, Any] = {}
        self.load()

    def _sync_active_view(self):
        """현재 활성 프로필 데이터를 최상위 buttons/grid_rows/grid_cols 뷰와 일치시킴"""
        profiles = self.data.setdefault("profiles", {})
        cur_name = self.data.get("current_profile", "Default")
        if cur_name not in profiles:
            if "Default" in profiles:
                cur_name = "Default"
            elif profiles:
                cur_name = next(iter(profiles.keys()))
            else:
                profiles["Default"] = copy.deepcopy(DEFAULT_PROFILE_DATA)
                cur_name = "Default"
            self.data["current_profile"] = cur_name

        prof_data = profiles[cur_name]
        # 최상위 뷰 동기화 (기존 코드 하위 호환)
        self.data["buttons"] = prof_data.setdefault("buttons", copy.deepcopy(DEFAULT_BUTTONS))
        self.data["grid_rows"] = prof_data.setdefault("grid_rows", 3)
        self.data["grid_cols"] = prof_data.setdefault("grid_cols", 4)

    def load(self) -> Dict[str, Any]:
        with self._lock:
            target = self.filepath
            if not target.exists() and self.filepath == DEFAULT_CONFIG_PATH and LEGACY_PROFILES_PATH.exists():
                target = LEGACY_PROFILES_PATH

            if not target.exists():
                self.data = copy.deepcopy(DEFAULT_CONFIG_DATA)
                self._sync_active_view()
                self.save()
                return self.data

            try:
                with open(target, "r", encoding="utf-8") as f:
                    raw = json.load(f)

                schema_ver = raw.get("schema_version")
                # 마이그레이션 필요 여부 확인
                if schema_ver != 2:
                    # 1) 원본 .bak 백업 생성
                    try:
                        bak_path = self.filepath.with_suffix(".json.bak")
                        shutil.copy2(target, bak_path)
                    except Exception as be:
                        print(f"[ConfigManager] Backup warning: {be}")

                    # 2) 딥 머지 & 래핑 (기존 모든 키 보존)
                    migrated = copy.deepcopy(raw)
                    migrated["schema_version"] = 2
                    
                    if "profiles" in raw and isinstance(raw["profiles"], dict) and raw["profiles"]:
                        # 기존 profiles 딕셔너리 구조가 있던 경우
                        profiles = migrated["profiles"]
                        cur_name = migrated.get("current_profile", "Default")
                        if cur_name not in profiles:
                            cur_name = next(iter(profiles.keys()))
                        migrated["current_profile"] = cur_name
                    else:
                        # flat 구조 (최상위에 buttons가 있던 경우)
                        legacy_buttons = raw.get("buttons", DEFAULT_BUTTONS)
                        migrated["current_profile"] = "Default"
                        migrated["profiles"] = {
                            "Default": {
                                "grid_rows": raw.get("grid_rows", 3),
                                "grid_cols": raw.get("grid_cols", 4),
                                "buttons": legacy_buttons
                            }
                        }

                    self.data = migrated
                    self._sync_active_view()
                    self.save()
                else:
                    self.data = raw
                    self._sync_active_view()
                    if target != self.filepath:
                        self.save()

            except Exception as e:
                print(f"[ConfigManager] Failed to load config, resetting: {e}")
                self.data = copy.deepcopy(DEFAULT_CONFIG_DATA)
                self._sync_active_view()
                self.save()

            return self.data

    def save(self) -> bool:
        """원자적 쓰기 (Atomic write using tmp + os.replace)"""
        with self._lock:
            tmp_path = None
            try:
                self.filepath.parent.mkdir(parents=True, exist_ok=True)
                self._sync_active_view()
                tmp_path = self.filepath.with_name(f"{self.filepath.name}.tmp.{os.getpid()}")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self.filepath)
                return True
            except Exception as e:
                print(f"[ConfigManager] Save error: {e}")
                if tmp_path and tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass
                return False

    # --- Profile Management APIs ---
    def get_profiles(self) -> List[str]:
        with self._lock:
            return list(self.data.get("profiles", {}).keys())

    def get_current_profile_name(self) -> str:
        with self._lock:
            return self.data.get("current_profile", "Default")

    def switch_profile(self, name: str) -> bool:
        """프로필 전환 (유효성 검증 포함)"""
        with self._lock:
            if not name or name not in self.data.get("profiles", {}):
                return False
            self.data["current_profile"] = name
            self._sync_active_view()
            self.save()
            return True

    def create_profile(self, name: str, copy_from: Optional[str] = None) -> bool:
        """새 프로필 생성 (유효성 및 특수문자 검증)"""
        with self._lock:
            name = name.strip()
            if not name or len(name) > 50 or any(ord(c) < 32 for c in name):
                return False
            if name in self.data.get("profiles", {}):
                return False

            profiles = self.data.setdefault("profiles", {})
            if copy_from and copy_from in profiles:
                new_data = copy.deepcopy(profiles[copy_from])
            else:
                new_data = copy.deepcopy(DEFAULT_PROFILE_DATA)

            profiles[name] = new_data
            self.data["current_profile"] = name
            self._sync_active_view()
            self.save()
            return True

    def delete_profile(self, name: str) -> bool:
        """프로필 삭제 (마지막 1개는 삭제 불가)"""
        with self._lock:
            profiles = self.data.get("profiles", {})
            if name not in profiles or len(profiles) <= 1:
                return False

            del profiles[name]
            if self.data.get("current_profile") == name:
                self.data["current_profile"] = "Default" if "Default" in profiles else next(iter(profiles.keys()))

            self._sync_active_view()
            self.save()
            return True

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        """프로필 이름 변경 (유효성 검증 포함)"""
        with self._lock:
            new_name = new_name.strip()
            if not new_name or len(new_name) > 50 or any(ord(c) < 32 for c in new_name):
                return False
            profiles = self.data.get("profiles", {})
            if old_name not in profiles or new_name in profiles:
                return False

            profiles[new_name] = profiles.pop(old_name)
            if self.data.get("current_profile") == old_name:
                self.data["current_profile"] = new_name

            self._sync_active_view()
            self.save()
            return True

    # --- Button APIs (Active Profile Scoped) ---
    def get_buttons(self) -> list:
        with self._lock:
            self._sync_active_view()
            return self.data.get("buttons", [])

    def get_button(self, button_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            for b in self.get_buttons():
                if b.get("id") == button_id:
                    return b
            return None

    def update_button(self, button_id: int, button_data: Dict[str, Any]) -> bool:
        with self._lock:
            buttons = self.data.setdefault("buttons", [])
            button_data["id"] = button_id
            for idx, b in enumerate(buttons):
                if b.get("id") == button_id:
                    buttons[idx] = button_data
                    self.save()
                    return True
            buttons.append(button_data)
            self.save()
            return True
