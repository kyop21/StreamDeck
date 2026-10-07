import os
import sys
import time
import ctypes
import webbrowser
import subprocess
from typing import Tuple, Dict, Any

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

user32.OpenClipboard.restype = ctypes.c_bool
user32.OpenClipboard.argtypes = [ctypes.c_void_p]
user32.CloseClipboard.restype = ctypes.c_bool
user32.EmptyClipboard.restype = ctypes.c_bool
user32.SetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]


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


class ActionExecutor:
    """7대 액션 타입 실행 엔진"""

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
        # 클립보드에 복사 후 Ctrl+V 시뮬레이션
        if _set_clipboard_text(payload):
            time.sleep(0.05)
            _press_key(VK_MAP["ctrl"])
            _tap_key(ord('V'))
            _release_key(VK_MAP["ctrl"])
            return True, f"텍스트 타이핑 완료: {payload[:20]}..."
        return False, "클립보드 접근 실패"
