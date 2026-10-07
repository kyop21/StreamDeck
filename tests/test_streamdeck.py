import unittest
import json
import asyncio
from pathlib import Path
import aiohttp

import sys
STREAM_DECK_DIR = Path(__file__).resolve().parent.parent
if str(STREAM_DECK_DIR) not in sys.path:
    sys.path.insert(0, str(STREAM_DECK_DIR))

from core.config import ConfigManager
from core.actions import ActionExecutor
from core.network import get_server_ip, generate_qr_png_bytes


class TestStreamDeckCore(unittest.TestCase):
    def test_config_manager(self):
        test_cfg_path = STREAM_DECK_DIR / "test_config.json"
        if test_cfg_path.exists():
            test_cfg_path.unlink()

        cm = ConfigManager(filepath=test_cfg_path)
        buttons = cm.get_buttons()
        self.assertEqual(len(buttons), 12)

        # Update button 0
        btn0 = cm.get_button(0)
        self.assertIsNotNone(btn0)
        self.assertEqual(btn0["title"], "Chrome")

        cm.update_button(0, {"title": "UpdatedChrome", "color": "#ff0000", "action_type": "url", "payload": "https://google.com"})
        btn0_updated = cm.get_button(0)
        self.assertEqual(btn0_updated["title"], "UpdatedChrome")

        if test_cfg_path.exists():
            test_cfg_path.unlink()

    def test_actions_validation(self):
        # Media volume up test
        success, msg = ActionExecutor.execute("media", "volume_up")
        self.assertTrue(success)

        # Invalid action test
        success, msg = ActionExecutor.execute("unknown_action", "payload")
        self.assertFalse(success)

        # Empty payload for app
        success, msg = ActionExecutor.execute("app", "")
        self.assertFalse(success)

    def test_network_and_qr(self):
        ip = get_server_ip()
        self.assertTrue(len(ip) > 0)
        print(f"\n[Test] Detected Server IP: {ip}")

        png_bytes = generate_qr_png_bytes(f"http://{ip}:8080")
        self.assertTrue(len(png_bytes) > 100)
        self.assertEqual(png_bytes[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
