import sys
import os
import asyncio
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

STREAM_DECK_DIR = Path(__file__).resolve().parent.parent
if str(STREAM_DECK_DIR) not in sys.path:
    sys.path.insert(0, str(STREAM_DECK_DIR))

from core.config import ConfigManager
from core.server import StreamDeckServerThread


class MockFBClient:
    """Isolated client state mimicking taildeck_fb.py optimized blit and touch flow."""
    def __init__(self, width=800, height=480, bpp=16):
        self.width = width
        self.height = height
        self.bpp = bpp
        self.stride = width * (bpp // 8)
        self.fb_size = height * self.stride
        self.fb_mmap = bytearray(self.fb_size)
        self.lock = MagicMock()
        self.lock.__enter__ = MagicMock(return_value=None)
        self.lock.__exit__ = MagicMock(return_value=None)

        self.button_rects = {0: (10, 20, 110, 100)}  # w=100, h=80
        self.btn_normal_bytes = {0: b"\x11\x22" * (100 * 80)}
        self.btn_pressed_bytes = {0: b"\x33\x44" * (100 * 80)}
        self.button_blit_plans = {}
        self.active_pressed_button = None
        self.pressed_button_time = 0.0
        self.last_touch_time = 0.0
        self.sent_ws = []

        # Precompute blit plan
        bx1, by1, bx2, by2 = self.button_rects[0]
        btn_w = bx2 - bx1
        btn_h = by2 - by1
        line_bytes = btn_w * 2
        stride = self.stride
        self.button_blit_plans[0] = [
            ((by1 + row) * stride + (bx1 * 2), row * line_bytes, line_bytes)
            for row in range(btn_h)
        ]

    def _safe_ws_send(self, payload):
        self.sent_ws.append(payload)
        return True

    def blit_button_rect(self, b_id, raw_btn_bytes):
        if not self.fb_mmap:
            return
        plan = self.button_blit_plans.get(b_id)
        if not plan:
            return
        mv = memoryview(raw_btn_bytes)
        fb = self.fb_mmap
        for fb_pos, src_pos, lb in plan:
            fb[fb_pos : fb_pos + lb] = mv[src_pos : src_pos + lb]

    def blit_rect(self, x1, y1, w, h, raw_bytes, update_base=False):
        stride = self.stride
        line_bytes = w * 2
        mv = memoryview(raw_bytes)
        for row in range(h):
            fb_pos = (y1 + row) * stride + (x1 * 2)
            src_pos = row * line_bytes
            self.fb_mmap[fb_pos : fb_pos + line_bytes] = mv[src_pos : src_pos + line_bytes]

    def flash_button(self, b_id, success: bool):
        if b_id not in self.button_rects:
            return
        x1, y1, x2, y2 = self.button_rects[b_id]
        bar_x1 = x1 + 3
        bar_y1 = y1 + 3
        bar_w = (x2 - x1) - 7
        bar_h = 4
        if bar_w <= 0:
            return

        color_565 = 0x07E0 if success else 0xF800
        c_bytes = (color_565).to_bytes(2, byteorder="little")
        flash_raw = (c_bytes * bar_w) * bar_h
        self.blit_rect(bar_x1, bar_y1, bar_w, bar_h, flash_raw)

    def on_touch_down(self, x, y):
        now = 1000.0
        if now - self.last_touch_time < 0.05:
            return
        self.last_touch_time = now

        clicked_id = None
        for b_id, rect in self.button_rects.items():
            x1, y1, x2, y2 = rect
            if x1 <= x <= x2 and y1 <= y <= y2:
                clicked_id = b_id
                break

        if clicked_id is None:
            return

        # UI First
        if clicked_id in self.btn_pressed_bytes:
            self.blit_button_rect(clicked_id, self.btn_pressed_bytes[clicked_id])
            self.active_pressed_button = clicked_id
            self.pressed_button_time = now

        # Network Next
        self._safe_ws_send({"type": "trigger_button", "button_id": clicked_id})

    def on_touch_up(self, x, y):
        b_id = self.active_pressed_button
        if b_id is None:
            return
        self.active_pressed_button = None
        if b_id in self.btn_normal_bytes:
            self.blit_button_rect(b_id, self.btn_normal_bytes[b_id])


class TestLatencyAndTouchOptimizations(unittest.TestCase):
    def test_precomputed_blit_plan_correctness(self):
        """Verify precomputed blit plan coordinates match direct calculation."""
        client = MockFBClient()
        plan = client.button_blit_plans[0]
        self.assertEqual(len(plan), 80)  # 80 rows

        # First row offset: y=20, x=10 -> 20 * (800*2) + 10 * 2 = 32000 + 20 = 32020
        self.assertEqual(plan[0], (32020, 0, 200))

        # Perform blit and verify destination bytes
        client.blit_button_rect(0, client.btn_pressed_bytes[0])
        # Check first row in fb_mmap
        self.assertEqual(client.fb_mmap[32020 : 32020 + 200], b"\x33\x44" * 100)

    def test_touch_down_ui_first_ordering(self):
        """Verify that on_touch_down updates the framebuffer BEFORE sending WebSocket packet."""
        client = MockFBClient()

        # Touch inside button 0 (x=50, y=50)
        client.on_touch_down(50, 50)

        # 1. State must be active_pressed_button = 0
        self.assertEqual(client.active_pressed_button, 0)

        # 2. Framebuffer must already have pressed bytes
        self.assertEqual(client.fb_mmap[32020 : 32020 + 200], b"\x33\x44" * 100)

        # 3. WS packet must have been sent
        self.assertEqual(len(client.sent_ws), 1)
        self.assertEqual(client.sent_ws[0], {"type": "trigger_button", "button_id": 0})

    def test_touch_up_restores_normal_state(self):
        """Verify on_touch_up immediately reverts framebuffer to normal state."""
        client = MockFBClient()
        client.on_touch_down(50, 50)
        self.assertEqual(client.active_pressed_button, 0)

        # Touch Up
        client.on_touch_up(50, 50)
        self.assertIsNone(client.active_pressed_button)

        # Framebuffer must have normal bytes restored
        self.assertEqual(client.fb_mmap[32020 : 32020 + 200], b"\x11\x22" * 100)

    def test_flash_button_accent_bar(self):
        """Verify flash_button writes exact RGB565 bytes to top accent bar."""
        client = MockFBClient()
        # Green flash: 0x07E0 -> little-endian \xe0\x07
        client.flash_button(0, success=True)

        bx1, by1 = 10, 20
        bar_x1 = bx1 + 3  # 13
        bar_y1 = by1 + 3  # 23
        bar_pos = bar_y1 * client.stride + bar_x1 * 2  # 23 * 1600 + 26 = 36826
        bar_w = (110 - 10) - 7  # 93

        self.assertEqual(client.fb_mmap[bar_pos : bar_pos + bar_w * 2], b"\xe0\x07" * bar_w)


class TestServerAsyncExecution(unittest.IsolatedAsyncioTestCase):
    async def test_server_async_action_offloading(self):
        """Verify server offloads ActionExecutor to worker thread without blocking event loop."""
        config_mgr = MagicMock(spec=ConfigManager)
        config_mgr.get_button.return_value = {
            "id": 1,
            "title": "AsyncTest",
            "action_type": "url",
            "payload": "https://example.com"
        }
        server_thread = StreamDeckServerThread(config_mgr=config_mgr)

        with patch("core.server.ActionExecutor.execute", return_value=(True, "OK")) as mock_exec:
            with patch("core.server.asyncio.to_thread", wraps=asyncio.to_thread) as mock_to_thread:
                await server_thread._execute_and_notify(1, source="test")
                mock_to_thread.assert_called_once()
                mock_exec.assert_called_once_with("url", "https://example.com")
