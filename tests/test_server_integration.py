import sys
import json
import asyncio
from pathlib import Path
import aiohttp

STREAM_DECK_DIR = Path(__file__).resolve().parent.parent
if str(STREAM_DECK_DIR) not in sys.path:
    sys.path.insert(0, str(STREAM_DECK_DIR))

from PyQt5.QtCore import QCoreApplication
from core.config import ConfigManager
from core.server import StreamDeckServerThread


TEST_PORT = 8089


async def _async_client_test(port: int = TEST_PORT):
    url_http = f"http://127.0.0.1:{port}/"
    url_ws = f"http://127.0.0.1:{port}/ws"

    async with aiohttp.ClientSession() as session:
        # 1. Test HTTP GET /
        async with session.get(url_http) as resp:
            assert resp.status == 200, f"HTTP status failed: {resp.status}"
            text = await resp.text()
            assert "taildeck" in text.lower(), "Index HTML missing TailDeck brand"
            print("[PASS] HTTP GET / returned index.html successfully.")

        # 2. Test WebSocket /ws
        async with session.ws_connect(url_ws) as ws:
            # First message should be sync_buttons (or sync_profile)
            msg = await ws.receive_json(timeout=5.0)
            assert msg["type"] in ("sync_buttons", "sync_profile"), f"Expected sync_buttons, got {msg}"
            assert len(msg["buttons"]) == 12, f"Expected 12 buttons, got {len(msg['buttons'])}"
            print(f"[PASS] WebSocket handshake OK: received {msg['type']} with {len(msg['buttons'])} buttons.")

            # Send trigger_button for button 3 (Vol Mute)
            await ws.send_json({"type": "trigger_button", "button_id": 3})

            # Receive action_result
            res_msg = await ws.receive_json(timeout=5.0)
            assert res_msg["type"] == "action_result", f"Expected action_result, got {res_msg}"
            assert res_msg["button_id"] == 3
            assert res_msg["status"] == "success"
            print(f"[PASS] WebSocket trigger_button OK: {res_msg}")


def main():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    cfg = ConfigManager(filepath=STREAM_DECK_DIR / "test_config.json")
    server = StreamDeckServerThread(config_mgr=cfg, host="127.0.0.1", port=TEST_PORT)
    server.start()

    import time
    time.sleep(1.0)  # wait for server to bind

    try:
        asyncio.run(_async_client_test(port=TEST_PORT))
        print("\n>>> ALL INTEGRATION TESTS PASSED! <<<")
    finally:
        server.stop()
        if (STREAM_DECK_DIR / "test_config.json").exists():
            (STREAM_DECK_DIR / "test_config.json").unlink()


def test_server_integration():
    """Integration test runnable by pytest / test runners"""
    main()


if __name__ == "__main__":
    main()
