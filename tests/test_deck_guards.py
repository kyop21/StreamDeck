import sys
import copy
import os
import asyncio
import unittest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# Headless 모드 설정 (CI/CLI 환경 지원)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

STREAM_DECK_DIR = Path(__file__).resolve().parent.parent
if str(STREAM_DECK_DIR) not in sys.path:
    sys.path.insert(0, str(STREAM_DECK_DIR))

from PyQt5.QtWidgets import QApplication
from core.config import ConfigManager
from core.server import StreamDeckServerThread
from gui.widgets import DeckButtonWidget
from gui.main_window import MainWindow


class TestDeckGuardsAndHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def setUp(self):
        DeckButtonWidget.clipboard_data = None
        self.test_cfg_path = STREAM_DECK_DIR / "test_guards_config.json"
        if self.test_cfg_path.exists():
            self.test_cfg_path.unlink()
        self.config_mgr = ConfigManager(filepath=self.test_cfg_path)

    def tearDown(self):
        DeckButtonWidget.clipboard_data = None
        if self.test_cfg_path.exists():
            self.test_cfg_path.unlink()

    def test_clipboard_guard_truthiness_in_widgets(self):
        """1) widgets.py: clipboard_data truthiness 가드 조건 검증"""
        DeckButtonWidget.clipboard_data = None
        self.assertFalse(bool(DeckButtonWidget.clipboard_data))

        DeckButtonWidget.clipboard_data = {}
        self.assertFalse(bool(DeckButtonWidget.clipboard_data))

        DeckButtonWidget.clipboard_data = {"id": 0, "action_type": "url", "payload": "https://example.com"}
        self.assertTrue(bool(DeckButtonWidget.clipboard_data))

    def test_copy_guard_prevents_empty_button_copy(self):
        """2) main_window.py: 미설정(action_type 부재/None) 버튼 복사 시 차단 검증"""
        # button 11번을 빈 버튼으로 설정
        empty_button = {
            "id": 11,
            "title": "EmptyBtn",
            "action_type": "",
            "payload": ""
        }
        self.config_mgr.update_button(11, empty_button)

        window = MainWindow(self.config_mgr)

        # 1. 미설정 버튼 복사 시도
        DeckButtonWidget.clipboard_data = None
        window.on_btn_copy(11)
        self.assertIsNone(DeckButtonWidget.clipboard_data, "action_type 없는 버튼은 복사 차단되어야 함")
        self.assertIn("빈 버튼이므로 복사할 수 없습니다", window.statusBar().currentMessage())

        # 2. 존재하지 않는 버튼 id 복사 시도
        window.on_btn_copy(999)
        self.assertIsNone(DeckButtonWidget.clipboard_data, "존재하지 않는 버튼은 복사 차단되어야 함")

        # 3. 정상 설정 버튼(0번: Chrome) 복사 시도
        window.on_btn_copy(0)
        self.assertIsNotNone(DeckButtonWidget.clipboard_data, "설정된 버튼은 정상 복사되어야 함")
        self.assertEqual(DeckButtonWidget.clipboard_data["action_type"], "app")
        window.close()

    def test_paste_guard_truthiness_in_main_window(self):
        """1) & 2) main_window.py: clipboard_data truthiness 가드 및 정상 붙여넣기 동작 검증"""
        window = MainWindow(self.config_mgr)

        target_btn_before = copy.deepcopy(self.config_mgr.get_button(5))

        # None일 때 붙여넣기 시도 -> 변화 없음
        DeckButtonWidget.clipboard_data = None
        window.on_btn_paste(5)
        self.assertEqual(self.config_mgr.get_button(5), target_btn_before)

        # 빈 dict {}일 때 붙여넣기 시도 -> 변화 없음
        DeckButtonWidget.clipboard_data = {}
        window.on_btn_paste(5)
        self.assertEqual(self.config_mgr.get_button(5), target_btn_before)

        # 유효 데이터 있을 때 붙여넣기 -> 정상 반영
        DeckButtonWidget.clipboard_data = {
            "id": 0,
            "title": "CopiedApp",
            "action_type": "app",
            "payload": "notepad.exe",
            "color": "#123456",
            "icon": ""
        }
        window.on_btn_paste(5)
        target_btn_after = self.config_mgr.get_button(5)
        self.assertEqual(target_btn_after["id"], 5)
        self.assertEqual(target_btn_after["title"], "CopiedApp")
        self.assertEqual(target_btn_after["action_type"], "app")
        window.close()

    def test_server_execute_empty_action_type_early_return(self):
        """3) core/server.py: action_type 공백 시 _execute_and_notify 조기 반환 검증"""
        server = StreamDeckServerThread(self.config_mgr)

        # 빈 액션 버튼 세팅
        empty_button = {
            "id": 9,
            "title": "Blank",
            "action_type": "",
            "payload": ""
        }
        self.config_mgr.update_button(9, empty_button)

        log_events = []
        exec_events = []
        server.log_signal.connect(lambda *args: log_events.append(args))
        server.button_executed_signal.connect(lambda *args: exec_events.append(args))

        # 비동기 함수 직접 실행
        asyncio.run(server._execute_and_notify(9))

        # early return 되어 어떠한 시그널도 발생하지 않아야 함 (FAIL 로그 방지)
        self.assertEqual(len(log_events), 0, "빈 action_type은 로그 시그널이 발생하지 않아야 함")
        self.assertEqual(len(exec_events), 0, "빈 action_type은 실행 시그널이 발생하지 않아야 함")

        # 정상 액션 버튼(3번: media vol_mute) 실행 시에는 시그널 발생 확인
        asyncio.run(server._execute_and_notify(3))
        self.assertEqual(len(log_events), 1, "정상 버튼은 로그 시그널이 발생해야 함")
        self.assertEqual(len(exec_events), 1, "정상 버튼은 실행 시그널이 발생해야 함")

    def test_apply_button_update_helper(self):
        """5) main_window.py: _apply_button_update 헬퍼 함수 통합 호출 검증"""
        window = MainWindow(self.config_mgr)

        # Mock server_thread
        mock_server = MagicMock()
        window.server_thread = mock_server

        new_data = {
            "id": 2,
            "title": "HelperTest",
            "action_type": "url",
            "payload": "https://test.com",
            "color": "#00ff00",
            "icon": ""
        }
        test_msg = "테스트 상태 메시지"

        window._apply_button_update(2, new_data, test_msg)

        # 1. config_mgr 갱신 확인
        saved = self.config_mgr.get_button(2)
        self.assertEqual(saved["title"], "HelperTest")

        # 2. 위젯 UI 갱신 확인
        self.assertEqual(window.btn_widgets[2].lbl_title.text(), "HelperTest")

        # 3. broadcast_buttons 호출 확인
        mock_server.broadcast_buttons.assert_called_once()

        # 4. statusBar 메시지 확인
        self.assertEqual(window.statusBar().currentMessage(), test_msg)
        window.close()

    def test_server_safe_send_str_success(self):
        """5) StreamDeckServerThread._safe_send_str 정상 전송 성공 검증"""
        server = StreamDeckServerThread(config_mgr=self.config_mgr)
        mock_ws = MagicMock()
        mock_ws.send_str = AsyncMock(return_value=None)

        server._active_sockets.add(mock_ws)
        res = asyncio.run(server._safe_send_str(mock_ws, '{"type": "ping"}', timeout=1.0))
        self.assertTrue(res)
        self.assertIn(mock_ws, server._active_sockets)

    def test_server_safe_send_str_timeout_drops_client(self):
        """6) StreamDeckServerThread._safe_send_str 타임아웃 발생 시 좀비 클라이언트 제거 검증"""
        server = StreamDeckServerThread(config_mgr=self.config_mgr)
        mock_ws = MagicMock()

        async def _hanging_send(data):
            await asyncio.sleep(2.0)

        mock_ws.send_str = _hanging_send
        mock_ws.close = AsyncMock(return_value=None)

        server._active_sockets.add(mock_ws)
        res = asyncio.run(server._safe_send_str(mock_ws, '{"type": "ping"}', timeout=0.05))
        self.assertFalse(res)
        self.assertNotIn(mock_ws, server._active_sockets)


if __name__ == "__main__":
    unittest.main()
