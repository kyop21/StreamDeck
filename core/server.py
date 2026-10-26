import asyncio
import json
import logging
from pathlib import Path
from typing import Set, Dict, Any, Optional
from aiohttp import web
from PyQt5.QtCore import QThread, pyqtSignal

from core.actions import ActionExecutor
from core.config import ConfigManager

logger = logging.getLogger("StreamDeckServer")


class StreamDeckServerThread(QThread):
    """
    aiohttp 기반 비동기 HTTP 및 WebSocket 서버를 구동하는 QThread.
    PyQt 메인 GUI와 시그널/슬롯으로 완전히 스레드 안전하게 통신합니다.
    """
    # [Signals to GUI]
    log_signal = pyqtSignal(str, int, str, str, str)  # (time, button_id, title, action_type, status)
    client_count_signal = pyqtSignal(int)             # 현재 접속된 모바일 클라이언트 수
    button_executed_signal = pyqtSignal(int, bool)    # (button_id, success)
    profile_changed_signal = pyqtSignal(str)          # (profile_name) 외부에서 프로필 변경 시 GUI 동기화

    def __init__(self, config_mgr: ConfigManager, host: str = "0.0.0.0", port: int = 2000, parent=None):
        super().__init__(parent)
        self.config_mgr = config_mgr
        self.host = host
        self.port = port
        self.web_dir = Path(__file__).resolve().parent.parent / "web"
        self._sync_seq = 0

        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._active_sockets: Set[web.WebSocketResponse] = set()
        self._is_running = False

    def run(self):
        """QThread 실행 루프 - 전용 비동기 이벤트 루프 생성 및 구동"""
        self._is_running = True
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.app = web.Application()
        self.app.router.add_get("/", self._handle_index)
        self.app.router.add_get("/ws", self._handle_ws)
        icons_dir = self.web_dir / "icons"
        if icons_dir.exists():
            self.app.router.add_static("/icons", path=str(icons_dir), name="icons")
        self.app.router.add_static("/static", path=str(self.web_dir), name="static")

        self.runner = web.AppRunner(self.app)
        self.loop.run_until_complete(self.runner.setup())
        site = web.TCPSite(self.runner, self.host, self.port)
        self.loop.run_until_complete(site.start())

        print(f"[Server] TailDeck Server started on http://{self.host}:{self.port}")

        try:
            self.loop.run_forever()
        finally:
            self.loop.run_until_complete(self._cleanup())
            self.loop.close()
            print("[Server] TailDeck Server stopped cleanly.")

    async def _cleanup(self):
        # 활성 소켓 정리
        for ws in list(self._active_sockets):
            await ws.close()
        self._active_sockets.clear()
        if self.runner:
            await self.runner.cleanup()

    def stop(self):
        """메인 스레드에서 서버를 안전하게 종료 요청"""
        self._is_running = False
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.wait()

    # --- HTTP Handlers ---
    async def _handle_index(self, request):
        index_path = self.web_dir / "index.html"
        if index_path.exists():
            return web.FileResponse(index_path)
        return web.Response(text="<h1>StreamDeck web files missing</h1>", content_type="text/html")

    # --- WebSocket Handlers ---
    async def _handle_ws(self, request):
        ws = web.WebSocketResponse(heartbeat=15.0)
        await ws.prepare(request)

        self._active_sockets.add(ws)
        self.client_count_signal.emit(len(self._active_sockets))

        # 접속 즉시 현재 버튼 목록 동기화 전송
        await self._send_sync_buttons(ws)

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._process_ws_message(ws, data)
                    except Exception as e:
                        print(f"[Server] WS parse error: {e}")
                elif msg.type == web.WSMsgType.ERROR:
                    print(f"[Server] WS error: {ws.exception()}")
        finally:
            self._active_sockets.discard(ws)
            self.client_count_signal.emit(len(self._active_sockets))

        return ws

    async def _safe_send_str(self, ws: web.WebSocketResponse, data: str, timeout: float = 3.0) -> bool:
        """Safely send string to a WebSocket client with strict timeout to prevent event loop stalls.

        If send times out or encounters an error (e.g. half-open TCP zombie socket),
        immediately discards the client from _active_sockets and closes it.
        """
        try:
            await asyncio.wait_for(ws.send_str(data), timeout=timeout)
            return True
        except Exception:
            self._active_sockets.discard(ws)
            self.client_count_signal.emit(len(self._active_sockets))
            try:
                await ws.close()
            except Exception:
                pass
            return False

    def _make_sync_payload(self) -> Dict[str, Any]:
        self._sync_seq += 1
        return {
            "type": "sync_buttons",
            "seq": self._sync_seq,
            "profile": self.config_mgr.get_current_profile_name(),
            "profiles": self.config_mgr.get_profiles(),
            "grid_rows": self.config_mgr.data.get("grid_rows", 3),
            "grid_cols": self.config_mgr.data.get("grid_cols", 4),
            "buttons": self.config_mgr.get_buttons()
        }

    async def _send_sync_buttons(self, ws: web.WebSocketResponse):
        payload = self._make_sync_payload()
        await self._safe_send_str(ws, json.dumps(payload))

    # 하위 호환성
    _send_sync_profile = _send_sync_buttons

    async def _process_ws_message(self, ws: web.WebSocketResponse, data: Dict[str, Any]):
        msg_type = data.get("type")

        if msg_type == "trigger_button":
            button_id = data.get("button_id")
            if button_id is not None:
                await self._execute_and_notify(button_id, source="mobile")
        elif msg_type in ("request_sync", "get_buttons", "sync_buttons"):
            await self._send_sync_buttons(ws)
        elif msg_type == "get_profiles":
            await self._safe_send_str(ws, json.dumps({
                "type": "profile_list",
                "profiles": self.config_mgr.get_profiles(),
                "current": self.config_mgr.get_current_profile_name()
            }))
        elif msg_type == "switch_profile":
            target_name = data.get("name")
            profiles = self.config_mgr.get_profiles()
            if not target_name or target_name not in profiles:
                # NACK: 미존재 프로필 거절
                await self._safe_send_str(ws, json.dumps({
                    "type": "error",
                    "code": "PROFILE_NOT_FOUND",
                    "message": f"Profile '{target_name}' not found",
                    "current_profile": self.config_mgr.get_current_profile_name()
                }))
            else:
                if self.config_mgr.get_current_profile_name() != target_name:
                    self.config_mgr.switch_profile(target_name)
                    self.profile_changed_signal.emit(target_name)
                self.broadcast_buttons()
        elif msg_type == "trigger_direct":
            act_type = data.get("action_type", "")
            payload = data.get("payload", "")
            if act_type:
                success, msg = await asyncio.to_thread(ActionExecutor.execute, act_type, payload)
                await self._safe_send_str(ws, json.dumps({
                    "type": "action_result",
                    "button_id": -1,
                    "status": "success" if success else "failed",
                    "message": msg
                }))

    async def _execute_and_notify(self, button_id: int, source: str = "mobile"):
        btn = self.config_mgr.get_button(button_id)
        if not btn:
            return

        act_type = btn.get("action_type", "")
        if not act_type:
            return

        payload = btn.get("payload", "")
        title = btn.get("title", f"Btn {button_id}")

        import datetime
        now_str = datetime.datetime.now().strftime("%H:%M:%S")

        success, msg = await asyncio.to_thread(ActionExecutor.execute, act_type, payload)

        status_str = "SUCCESS" if success else f"FAIL: {msg}"
        self.log_signal.emit(now_str, button_id, title, act_type, status_str)
        self.button_executed_signal.emit(button_id, success)

        # 모바일 클라이언트에 결과 피드백 브로드캐스트
        res_payload = json.dumps({
            "type": "action_result",
            "button_id": button_id,
            "status": "success" if success else "fail",
            "message": msg
        })
        for ws in list(self._active_sockets):
            await self._safe_send_str(ws, res_payload)

    def trigger_button_from_pc(self, button_id: int):
        """PC GUI에서 직접 버튼을 클릭했을 때 비동기 루프로 실행 위임"""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._execute_and_notify(button_id, source="pc"), self.loop
            )

    def broadcast_buttons(self):
        """GUI에서 버튼이 수정되었을 때 모바일에 즉시 전송"""
        if not self.loop or not self.loop.is_running():
            return

        payload = json.dumps(self._make_sync_payload())

        async def _broadcast():
            for ws in list(self._active_sockets):
                await self._safe_send_str(ws, payload)

        asyncio.run_coroutine_threadsafe(_broadcast(), self.loop)

    # 하위 호환성 alias
    broadcast_profile = broadcast_buttons
