import os
import sys
import json
import copy
import time
import shutil
import asyncio
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Headless 모드 설정 (CI/CLI 환경 지원)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

STREAM_DECK_DIR = Path(__file__).resolve().parent.parent
if str(STREAM_DECK_DIR) not in sys.path:
    sys.path.insert(0, str(STREAM_DECK_DIR))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSignalBlocker
from core.config import ConfigManager, DEFAULT_BUTTONS, DEFAULT_PROFILE_DATA
from core.server import StreamDeckServerThread
from gui.main_window import MainWindow


class TestProfileSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def setUp(self):
        self.test_dir = STREAM_DECK_DIR / "test_scratch_profiles"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.cfg_file = self.test_dir / "config.json"
        if self.cfg_file.exists():
            self.cfg_file.unlink()
        bak_file = self.test_dir / "config.json.bak"
        if bak_file.exists():
            bak_file.unlink()

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_default_config_schema(self):
        """1) 기본 설정 생성 시 schema_version 2 및 Default 프로필 포함 검증"""
        cm = ConfigManager(filepath=self.cfg_file)
        self.assertEqual(cm.data.get("schema_version"), 2)
        self.assertEqual(cm.get_current_profile_name(), "Default")
        self.assertIn("Default", cm.get_profiles())
        self.assertEqual(len(cm.get_buttons()), 12)

    def test_legacy_migration_and_backup(self):
        """2) schema_version 없는 레거시 flat config 로드 시 백업 생성 및 래핑 마이그레이션 검증"""
        legacy_data = {
            "custom_metadata": "important_value",
            "grid_rows": 3,
            "grid_cols": 4,
            "buttons": [
                {"id": 0, "title": "LegacyBtn", "action_type": "app", "payload": "notepad"}
            ]
        }
        with open(self.cfg_file, "w", encoding="utf-8") as f:
            json.dump(legacy_data, f, indent=2)

        cm = ConfigManager(filepath=self.cfg_file)

        # 백업 파일 존재 확인
        bak_file = self.test_dir / "config.json.bak"
        self.assertTrue(bak_file.exists(), ".bak 백업 파일이 생성되어야 함")

        # 마이그레이션 결과 확인
        self.assertEqual(cm.data.get("schema_version"), 2)
        self.assertEqual(cm.data.get("custom_metadata"), "important_value")
        self.assertEqual(cm.get_current_profile_name(), "Default")
        buttons = cm.get_buttons()
        self.assertEqual(buttons[0]["title"], "LegacyBtn")

    def test_profile_crud_operations(self):
        """3) 프로필 생성, 전환, 이름변경, 삭제 및 단일 프로필 삭제 방지 가드 검증"""
        cm = ConfigManager(filepath=self.cfg_file)

        # 1. 생성
        res = cm.create_profile("Gaming")
        self.assertTrue(res)
        self.assertIn("Gaming", cm.get_profiles())
        self.assertEqual(cm.get_current_profile_name(), "Gaming")

        # 2. 프로필별 버튼 격리 수정
        cm.update_button(0, {"id": 0, "title": "GameLauncher", "action_type": "app", "payload": "game.exe"})
        self.assertEqual(cm.get_button(0)["title"], "GameLauncher")

        # 3. Default로 전환 후 버튼 격리 확인
        cm.switch_profile("Default")
        self.assertEqual(cm.get_current_profile_name(), "Default")
        self.assertEqual(cm.get_button(0)["title"], "Chrome")

        # 4. 다시 Gaming으로 전환 시 버튼 유지 확인
        cm.switch_profile("Gaming")
        self.assertEqual(cm.get_button(0)["title"], "GameLauncher")

        # 5. 프로필 이름 변경
        res_rename = cm.rename_profile("Gaming", "Workstation")
        self.assertTrue(res_rename)
        self.assertIn("Workstation", cm.get_profiles())
        self.assertNotIn("Gaming", cm.get_profiles())
        self.assertEqual(cm.get_current_profile_name(), "Workstation")

        # 6. 프로필 삭제
        res_del = cm.delete_profile("Workstation")
        self.assertTrue(res_del)
        self.assertNotIn("Workstation", cm.get_profiles())
        self.assertEqual(cm.get_current_profile_name(), "Default")

        # 7. 마지막 1개 프로필은 삭제 거부
        res_del_last = cm.delete_profile("Default")
        self.assertFalse(res_del_last, "마지막 남은 프로필은 삭제할 수 없어야 함")
        self.assertIn("Default", cm.get_profiles())

    def test_multithreading_concurrency_safety(self):
        """4) 멀티스레드 환경에서 프로필 전환 및 버튼 갱신 시 race condition 안전성 검증"""
        cm = ConfigManager(filepath=self.cfg_file)
        cm.create_profile("Worker1")
        cm.create_profile("Worker2")

        errors = []

        def worker_task(prof_name, thread_id):
            try:
                for i in range(10):
                    cm.switch_profile(prof_name)
                    cm.update_button(i % 12, {
                        "id": i % 12,
                        "title": f"T{thread_id}_{i}",
                        "action_type": "script",
                        "payload": "echo 1"
                    })
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker_task, args=("Worker1", 1)),
            threading.Thread(target=worker_task, args=("Worker2", 2)),
            threading.Thread(target=worker_task, args=("Default", 3)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent thread errors: {errors}")

    def test_gui_profile_signal_blocker_and_sync(self):
        """5) GUI 프로필 콤보박스와 외부 신호 수신 시 시그널 루프 차단(QSignalBlocker) 검증"""
        cm = ConfigManager(filepath=self.cfg_file)
        cm.create_profile("SubProfile")
        cm.switch_profile("Default")

        mock_server = MagicMock()
        window = MainWindow(cm, server_thread=mock_server)

        # 1. 콤보박스에 프로필 항목이 정상 채워졌는지 확인
        combo_items = [window.combo_profile.itemText(i) for i in range(window.combo_profile.count())]
        self.assertIn("Default", combo_items)
        self.assertIn("SubProfile", combo_items)
        self.assertEqual(window.combo_profile.currentText(), "Default")

        # 2. PC GUI에서 사용자가 직접 프로필 변경
        mock_server.reset_mock()
        window.combo_profile.setCurrentText("SubProfile")
        self.assertEqual(cm.get_current_profile_name(), "SubProfile")
        mock_server.broadcast_buttons.assert_called_once()

        # 3. 외부 기기(DietPi)로부터 프로필 변경 시그널 도달 -> on_external_profile_changed
        # QSignalBlocker가 작동하여 on_profile_combo_changed가 재호출되지 않고 broadcast_buttons도 중복 호출 안 됨
        mock_server.reset_mock()
        cm.switch_profile("Default")  # 서버단에서 먼저 스위치됨
        window.on_external_profile_changed("Default")

        self.assertEqual(window.combo_profile.currentText(), "Default")
        # broadcast_buttons는 외부 변경 슬롯에서는 호출되지 않아야 함 (서버가 이미 브로드캐스트함)
        mock_server.broadcast_buttons.assert_not_called()

        window.close()

    def test_profile_validation(self):
        """6) 프로필 이름 유효성 검증: 50자 초과 또는 제어문자 포함 시 거부"""
        cm = ConfigManager(filepath=self.cfg_file)
        self.assertFalse(cm.create_profile("A" * 51))
        self.assertFalse(cm.create_profile("Bad\x00Name"))
        self.assertFalse(cm.create_profile("Bad\nName"))
        self.assertTrue(cm.create_profile("Valid Profile"))
        self.assertFalse(cm.rename_profile("Valid Profile", "TooLong" * 10))

    def test_server_sync_payload_contains_profiles(self):
        """7) 서버 동기화 페이로드에 profiles 전체 목록이 포함되어 원격 클라이언트가 즉시 갱신 가능한지 검증"""
        cm = ConfigManager(filepath=self.cfg_file)
        cm.create_profile("Work")
        server = StreamDeckServerThread(cm)
        payload = server._make_sync_payload()
        self.assertEqual(payload["type"], "sync_buttons")
        self.assertIn("profiles", payload)
        self.assertIn("Default", payload["profiles"])
        self.assertIn("Work", payload["profiles"])
        self.assertEqual(payload["profile"], "Work")

    def test_gui_load_buttons_slot_reset(self):
        """8) 프로필 전환 시 누락된 버튼 슬롯이 이전 프로필 데이터로 남지 않고 초기화되는지 검증"""
        cm = ConfigManager(filepath=self.cfg_file)
        # 0번 버튼만 있는 프로필 생성
        cm.create_profile("Sparse")
        cm.data["profiles"]["Sparse"]["buttons"] = [
            {"id": 0, "title": "OnlyButton", "action_type": "app", "payload": "notepad"}
        ]
        cm._sync_active_view()
        window = MainWindow(cm)
        window.load_buttons_ui()

        # 0번은 OnlyButton
        self.assertEqual(window.btn_widgets[0].lbl_title.text(), "OnlyButton")
        # 1번은 빈 버튼으로 초기화되어야 함
        self.assertEqual(window.btn_widgets[1].lbl_badge.text(), "EMPTY")
        window.close()


if __name__ == "__main__":
    unittest.main()
