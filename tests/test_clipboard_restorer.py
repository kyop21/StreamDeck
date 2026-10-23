import os
import sys
import time
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.actions import (
    ActionExecutor,
    ClipboardRestorer,
    _get_clipboard_text,
    _set_clipboard_text,
)


@pytest.fixture(autouse=True)
def cleanup_clipboard():
    """테스트 실행 전/후 클립보드 복원기 리셋"""
    ClipboardRestorer.reset()
    yield
    ClipboardRestorer.reset()


def test_clipboard_get_and_set():
    """클립보드 텍스트 쓰기 및 읽기가 유니코드(한글, 특수문자)를 완벽히 지원하는지 검증"""
    test_str = "TailDeck 유니코드 테스트 🚀 123 !@#"
    ok = _set_clipboard_text(test_str)
    assert ok is True
    time.sleep(0.05)
    read_str = _get_clipboard_text()
    assert read_str == test_str


def test_single_typing_macro_restores_original_clipboard():
    """단일 매크로 실행 후 0.35초 뒤 원래 클립보드 텍스트가 정상 복원되는지 검증"""
    orig_text = "이것은_원래_사용자가_복사해둔_텍스트입니다"
    _set_clipboard_text(orig_text)
    time.sleep(0.05)
    assert _get_clipboard_text() == orig_text

    # 타이핑 매크로 실행
    macro_text = "매크로_입력_텍스트"
    success, msg = ActionExecutor.execute("typing", macro_text)
    assert success is True
    assert "매크로_입력_텍스트" in msg

    # 타이핑 직후: 클립보드에는 매크로 텍스트가 들어있어야 대상 창이 붙여넣을 수 있음
    assert _get_clipboard_text() == macro_text

    # 0.4초 후: 복원 타이머(0.35s)가 작동하여 원래 클립보드 텍스트로 자동 원복되어야 함
    time.sleep(0.45)
    assert _get_clipboard_text() == orig_text


def test_rapid_consecutive_typing_preserves_true_original_text():
    """빠른 연속 타이핑(연타) 시 중간 매크로 텍스트로 오염되지 않고 최초 원본이 복원되는지 검증"""
    orig_text = "진짜_사용자_원본_텍스트"
    _set_clipboard_text(orig_text)
    time.sleep(0.05)

    # 1번째 매크로 실행 (t = 0s)
    success1, _ = ActionExecutor.execute("typing", "1차_매크로")
    assert success1 is True

    # 100ms 후 2번째 매크로 실행 (1차 타이머 0.35s 끝나기 전)
    time.sleep(0.1)
    success2, _ = ActionExecutor.execute("typing", "2차_매크로")
    assert success2 is True

    # 100ms 후 3번째 매크로 실행
    time.sleep(0.1)
    success3, _ = ActionExecutor.execute("typing", "3차_매크로")
    assert success3 is True

    # 현재 클립보드는 마지막 매크로 텍스트여야 함
    assert _get_clipboard_text() == "3차_매크로"

    # 최종 매크로 실행 후 0.45초 대기 (모든 디바운스 완료)
    time.sleep(0.45)

    # 최종 결과: 중간 매크로("1차_매크로", "2차_매크로")가 아닌 "진짜_사용자_원본_텍스트"가 복원되어야 함!
    restored = _get_clipboard_text()
    assert restored == orig_text, f"기대값: {orig_text}, 실제 복원값: {restored}"


def test_typing_with_empty_payload():
    """빈 문자열 입력 시 실행 거부 검증"""
    success, msg = ActionExecutor.execute("typing", "")
    assert success is False
    assert "입력할 텍스트가 없습니다" in msg


def test_clipboard_restorer_rollback():
    """rollback 호출 시 대기 중인 복원 상태가 안전하게 초기화되는지 검증"""
    _set_clipboard_text("롤백_테스트_원본")
    time.sleep(0.05)

    ClipboardRestorer.begin_typing()
    assert ClipboardRestorer._has_pending is True
    assert ClipboardRestorer._pending_orig_text == "롤백_테스트_원본"

    ClipboardRestorer.rollback()
    assert ClipboardRestorer._has_pending is False
    assert ClipboardRestorer._pending_orig_text is None
    assert ClipboardRestorer._timer is None
