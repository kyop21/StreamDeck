import os
import sys
import time
import ctypes
import webbrowser
import subprocess
import threading
from typing import Tuple, Dict, Any, Optional

user32 = ctypes.windll.user32

# Virtual Key Codes for Windows
VK_MAP = {
    "volume_mute": 0xAD,
    "volume_down": 0xAE,
    "volume_up": 0xAF,
    "next_track": 0xB0,
    "prev_track": 0xB1,
    "stop_media": 0xB2,
    "play_pause": 0xB3,
    "ctrl": 0x11,
    "control": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "win": 0x5B,
    "windows": 0x5B,
    "enter": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "tab": 0x09,
    "backspace": 0x08,
    "delete": 0x2E,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}

KEYEVENTF_KEYUP = 0x0002


def _press_key(vk_code: int):
    user32.keybd_event(vk_code, 0, 0, 0)


def _release_key(vk_code: int):
    user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


def _tap_key(vk_code: int):
    _press_key(vk_code)
    time.sleep(0.02)
    _release_key(vk_code)


# 64비트 Windows API ctypes 시그니처 명시 (포인터 잘림 방지)
kernel32 = ctypes.windll.kernel32
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalSize.argtypes = [ctypes.c_void_p]

user32.OpenClipboard.restype = ctypes.c_bool
user32.OpenClipboard.argtypes = [ctypes.c_void_p]
user32.CloseClipboard.restype = ctypes.c_bool
user32.EmptyClipboard.restype = ctypes.c_bool
user32.SetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
user32.GetClipboardData.restype = ctypes.c_void_p
user32.GetClipboardData.argtypes = [ctypes.c_uint]
user32.IsClipboardFormatAvailable.restype = ctypes.c_bool
user32.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]


def _set_clipboard_text(text: str) -> bool:
    """Windows API를 사용하여 외부 패키지 없이 64비트 호환 유니코드 클립보드 복사"""
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    # 일시적인 클립보드 점유 경합에 대비해 최대 5회 재시도
    opened = False
    for _ in range(5):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.02)

    if not opened:
        # 폴백: PyQt5 클립보드 시도
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.clipboard().setText(text)
                return True
        except Exception:
            pass
        return False

    try:
        user32.EmptyClipboard()
        encoded = (text + '\0').encode('utf-16le')
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not h_mem:
            return False

        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            kernel32.GlobalFree(h_mem)
            return False

        ctypes.memmove(p_mem, encoded, len(encoded))
        kernel32.GlobalUnlock(h_mem)
        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        return True
    finally:
        user32.CloseClipboard()


def _get_clipboard_text() -> Optional[str]:
    """Windows API를 사용하여 현재 클립보드의 유니코드 텍스트를 읽어옴"""
    CF_UNICODETEXT = 13

    opened = False
    for _ in range(5):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.02)

    if not opened:
        return None

    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        h_mem = user32.GetClipboardData(CF_UNICODETEXT)
        if not h_mem:
            return None
        size_bytes = kernel32.GlobalSize(h_mem)
        if size_bytes == 0:
            return None
        if size_bytes < 2:
            return ""

        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            return None
        try:
            max_chars = size_bytes // 2
            raw_str = ctypes.wstring_at(p_mem, max_chars)
            null_idx = raw_str.find('\0')
            if null_idx != -1:
                return raw_str[:null_idx]
            return raw_str
        finally:
            kernel32.GlobalUnlock(h_mem)
    finally:
        user32.CloseClipboard()


class ClipboardRestorer:
    """타이핑 매크로 실행 시 클립보드 원본 텍스트를 안전하게 보존하고 복원하는 관리자"""
    _lock = threading.Lock()
    _pending_orig_text: Optional[str] = None
    _has_pending: bool = False
    _timer: Optional[threading.Timer] = None

    @classmethod
    def begin_typing(cls) -> Optional[str]:
        """타이핑 세션 시작: 현재 클립보드 원본을 캡처하거나 진행 중인 세션의 최초 원본 유지"""
        with cls._lock:
            if cls._timer is not None:
                cls._timer.cancel()
                cls._timer = None

            if not cls._has_pending:
                cls._pending_orig_text = _get_clipboard_text()
                cls._has_pending = True
            return cls._pending_orig_text

    @classmethod
    def rollback(cls) -> None:
        """클립보드 쓰기 실패 등 비정상 중단 시 세션 취소"""
        with cls._lock:
            if cls._timer is not None:
                cls._timer.cancel()
                cls._timer = None
            cls._has_pending = False
            cls._pending_orig_text = None

    @classmethod
    def schedule_restore(cls, delay: float = 0.35) -> None:
        """타이핑 완료 후 지정된 딜레이(초) 후 원본 텍스트 복원 스케줄링 (단일 디바운스)"""
        with cls._lock:
            if cls._timer is not None:
                cls._timer.cancel()

            def _restore_callback():
                with cls._lock:
                    orig = cls._pending_orig_text

                if orig is not None:
                    _set_clipboard_text(orig)

                with cls._lock:
                    if cls._timer is current_timer:
                        cls._has_pending = False
                        cls._pending_orig_text = None
                        cls._timer = None

            current_timer = threading.Timer(delay, _restore_callback)
            current_timer.daemon = True
            cls._timer = current_timer
            current_timer.start()

    @classmethod
    def reset(cls) -> None:
        """테스트 및 상태 강제 초기화용"""
        cls.rollback()


class ActionExecutor:
    """7대 액션 타입 실행 엔진"""
    _typing_lock = threading.Lock()

    @classmethod
    def execute(cls, action_type: str, payload: str) -> Tuple[bool, str]:
        """
        액션을 실행하고 (성공 여부, 결과 메시지)를 반환합니다.
        """
        try:
            handler = getattr(cls, f"_act_{action_type.lower()}", None)
            if not handler:
                return False, f"알 수 없는 액션 타입: {action_type}"
            return handler(payload.strip())
        except Exception as e:
            return False, f"실행 중 예외 발생: {str(e)}"

    @classmethod
    def _act_app(cls, payload: str) -> Tuple[bool, str]:
        if not payload:
            return False, "실행할 프로그램 경로가 지정되지 않았습니다."
        # 실행 파일(.exe) 또는 윈도우 등록 앱(chrome, notepad, calc 등)
        cmd = payload
        if not (" " in payload or "\\" in payload or "/" in payload):
            cmd = f'start "" "{payload}"'
        subprocess.Popen(cmd, shell=True)
        return True, f"프로그램 실행: {payload}"

    @classmethod
    def _act_url(cls, payload: str) -> Tuple[bool, str]:
        if not payload:
            return False, "열기 위한 URL이 지정되지 않았습니다."
        url = payload
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url
        webbrowser.open(url)
        return True, f"브라우저 URL 열기: {url}"

    @classmethod
    def _act_media(cls, payload: str) -> Tuple[bool, str]:
        cmd = payload.lower()
        if cmd in VK_MAP:
            _tap_key(VK_MAP[cmd])
            return True, f"미디어 제어 실행: {cmd}"
        return False, f"알 수 없는 미디어 명령: {payload}"

    @classmethod
    def _act_hotkey(cls, payload: str) -> Tuple[bool, str]:
        """예: 'ctrl+c', 'win+d', 'alt+f4'"""
        parts = [p.strip().lower() for p in payload.split("+")]
        vks = []
        for p in parts:
            if p in VK_MAP:
                vks.append(VK_MAP[p])
            elif len(p) == 1 and p.isalnum():
                # 영문자 또는 숫자 (대문자 ASCII 코드가 Virtual Key Code)
                vks.append(ord(p.upper()))
            else:
                return False, f"해석할 수 없는 키: {p}"

        # 순차적으로 누르기
        for vk in vks:
            _press_key(vk)
            time.sleep(0.01)

        time.sleep(0.05)

        # 역순으로 떼기
        for vk in reversed(vks):
            _release_key(vk)

        return True, f"단축키 입력: {payload}"

    @classmethod
    def _act_system(cls, payload: str) -> Tuple[bool, str]:
        cmd = payload.lower()
        if cmd == "lock":
            user32.LockWorkStation()
            return True, "화면 잠금 실행"
        elif cmd == "sleep":
            ctypes.windll.PowrProf.SetSuspendState(0, 1, 0)
            return True, "절전 모드 전환"
        elif cmd == "shutdown":
            subprocess.run("shutdown /s /t 60", shell=True)
            return True, "1분 후 시스템 종료 예약"
        elif cmd == "cancel_shutdown":
            subprocess.run("shutdown /a", shell=True)
            return True, "시스템 종료 예약 취소"
        return False, f"알 수 없는 시스템 명령: {payload}"

    @classmethod
    def _act_script(cls, payload: str) -> Tuple[bool, str]:
        if not payload:
            return False, "실행할 스크립트 명령이 없습니다."
        subprocess.Popen(payload, shell=True)
        return True, f"스크립트 실행: {payload}"

    @classmethod
    def _act_typing(cls, payload: str) -> Tuple[bool, str]:
        if not payload:
            return False, "입력할 텍스트가 없습니다."
        with cls._typing_lock:
            # 1. 원본 클립보드 보존 세션 시작 (연속 호출 시 최초 원본 보존)
            ClipboardRestorer.begin_typing()

            # 2. 클립보드에 매크로 텍스트 복사
            if not _set_clipboard_text(payload):
                ClipboardRestorer.rollback()
                return False, "클립보드 접근 실패"

            try:
                time.sleep(0.05)
                _press_key(VK_MAP["ctrl"])
                try:
                    _tap_key(ord('V'))
                finally:
                    _release_key(VK_MAP["ctrl"])

                # 3. 대상 앱이 Ctrl+V를 처리할 수 있도록 0.35초 후 원본 비동기 복원
                ClipboardRestorer.schedule_restore(delay=0.35)

                preview = payload[:20] + "..." if len(payload) > 20 else payload
                return True, f"텍스트 타이핑 완료: {preview}"
            except Exception as e:
                ClipboardRestorer.rollback()
                return False, f"타이핑 실행 중 오류 발생: {e}"
