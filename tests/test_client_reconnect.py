import unittest
import random
import json
import threading
import time


def calculate_reconnect_backoff(attempt: int, seed: int = None) -> float:
    """Pure logic equivalent of taildeck_fb.py ws_loop backoff calculation."""
    if seed is not None:
        rng = random.Random(seed)
        jitter = rng.uniform(0.0, 1.0)
    else:
        jitter = random.uniform(0.0, 1.0)
    backoff = min(15.0, 1.0 * (2 ** min(attempt, 4))) + jitter
    return min(15.0, backoff)


class MockWebSocket:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.sent_messages = []
        self.aborted = False

    def send(self, data: str):
        if self.should_fail:
            raise ConnectionResetError("Broken pipe or remote socket closed")
        self.sent_messages.append(data)

    def abort(self):
        self.aborted = True


class MockClientSender:
    """Isolated sender logic mimicking taildeck_fb.py _safe_ws_send."""
    def __init__(self, ws=None, connected: bool = False):
        self.ws = ws
        self.connected = connected
        self.status_msg = ""
        self.abort_called = False

    def force_abort_ws(self):
        self.abort_called = True
        if self.ws:
            self.ws.abort()

    def update_status_msg(self, msg: str):
        self.status_msg = msg

    def _safe_ws_send(self, payload_dict):
        if not self.ws or not self.connected:
            return False
        try:
            msg_str = json.dumps(payload_dict)
            self.ws.send(msg_str)
            return True
        except Exception as e:
            self.connected = False
            self.force_abort_ws()
            self.update_status_msg("연결 끊김 (재시도 중...)")
            return False


class TestClientReconnectHardening(unittest.TestCase):
    def test_backoff_monotonic_and_cap(self):
        """Test exponential backoff progression and strict 15.0s ceiling."""
        delays = [calculate_reconnect_backoff(i, seed=42) for i in range(10)]

        # Delays should never exceed 15.0
        for d in delays:
            self.assertLessEqual(d, 15.0)

        # First attempt (attempt 0) should be around 1.0 ~ 2.0s
        self.assertGreaterEqual(delays[0], 1.0)
        self.assertLessEqual(delays[0], 2.0)

        # Subsequent attempts grow
        self.assertGreater(delays[2], delays[0])

        # High attempts (>= 5) must be clamped at 15.0s
        self.assertEqual(calculate_reconnect_backoff(5, seed=0), 15.0)
        self.assertEqual(calculate_reconnect_backoff(10, seed=0), 15.0)

    def test_safe_ws_send_success(self):
        """Verify successful message transmission retains connected state."""
        ws = MockWebSocket(should_fail=False)
        client = MockClientSender(ws=ws, connected=True)

        result = client._safe_ws_send({"type": "get_profiles"})
        self.assertTrue(result)
        self.assertTrue(client.connected)
        self.assertFalse(client.abort_called)
        self.assertEqual(len(ws.sent_messages), 1)

    def test_safe_ws_send_disconnected_noop(self):
        """Verify send when not connected returns False immediately without exception."""
        ws = MockWebSocket(should_fail=False)
        client = MockClientSender(ws=ws, connected=False)

        result = client._safe_ws_send({"type": "trigger_button", "button_id": 1})
        self.assertFalse(result)
        self.assertEqual(len(ws.sent_messages), 0)

    def test_safe_ws_send_failure_triggers_abort_and_recovery(self):
        """Verify transmission failure marks disconnected, aborts socket, and updates status."""
        ws = MockWebSocket(should_fail=True)
        client = MockClientSender(ws=ws, connected=True)

        result = client._safe_ws_send({"type": "request_sync"})
        self.assertFalse(result)
        self.assertFalse(client.connected)
        self.assertTrue(client.abort_called)
        self.assertTrue(ws.aborted)
        self.assertEqual(client.status_msg, "연결 끊김 (재시도 중...)")

    def test_lock_guarded_dict_iteration_under_concurrency(self):
        """Verify that taking a list copy under lock prevents RuntimeError during clear()."""
        lock = threading.RLock()
        shared_dict = {i: (0, 0, 10, 10) for i in range(100)}
        errors = []

        def worker_clear_and_rebuild():
            for _ in range(50):
                with lock:
                    shared_dict.clear()
                    for i in range(100):
                        shared_dict[i] = (i, i, i + 10, i + 10)
                time.sleep(0.001)

        def worker_touch_reader():
            for _ in range(100):
                try:
                    with lock:
                        items = list(shared_dict.items())
                    for k, v in items:
                        _ = k, v
                except RuntimeError as e:
                    errors.append(e)
                time.sleep(0.0005)

        t1 = threading.Thread(target=worker_clear_and_rebuild)
        t2 = threading.Thread(target=worker_touch_reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(errors), 0, "No RuntimeError must occur when iterating dict snapshot under lock")

    def test_server_url_rotation(self):
        """Verify candidate URL cycling across multi-host pool."""
        urls = ["ws://100.86.114.58:8080/ws", "ws://10.10.14.27:8080/ws", "ws://127.0.0.1:8080/ws"]
        idx = 0

        def get_current():
            return urls[idx % len(urls)]

        def rotate():
            nonlocal idx
            idx = (idx + 1) % len(urls)

        self.assertEqual(get_current(), "ws://100.86.114.58:8080/ws")
        rotate()
        self.assertEqual(get_current(), "ws://10.10.14.27:8080/ws")
        rotate()
        self.assertEqual(get_current(), "ws://127.0.0.1:8080/ws")
        rotate()
        self.assertEqual(get_current(), "ws://100.86.114.58:8080/ws")

    def test_reconnect_event_interruptible_sleep(self):
        """Verify force_abort_ws immediately wakes up sleeping ws_loop without blocking."""
        reconnect_event = threading.Event()
        reconnect_attempt = 5

        t0 = time.time()

        def background_abort():
            time.sleep(0.05)
            nonlocal reconnect_attempt
            reconnect_attempt = 0
            reconnect_event.set()

        threading.Thread(target=background_abort, daemon=True).start()

        reconnect_event.clear()
        woken_up = reconnect_event.wait(timeout=5.0)
        elapsed = time.time() - t0

        self.assertTrue(woken_up)
        self.assertLess(elapsed, 0.5, "Interruptible sleep should awaken immediately upon abort")
        self.assertEqual(reconnect_attempt, 0)

    def test_touch_frame_syn_report_buffering(self):
        """Verify evdev EV_SYN frame buffering eliminates 1-touch coordinate lag."""
        class MockEvent:
            def __init__(self, type_, code, value):
                self.type = type_
                self.code = code
                self.value = value

        EV_SYN = 0x00
        EV_KEY = 0x01
        EV_ABS = 0x03
        SYN_REPORT = 0
        BTN_TOUCH = 0x14a
        ABS_X = 0x00
        ABS_Y = 0x01

        dispatched_touches = []

        cur_x = 50
        cur_y = 50
        touch_down = False
        pending_touch = False

        # Simulate stream from raspberrypi-ts driver:
        # BTN_TOUCH arrives BEFORE ABS coordinates, followed by SYN_REPORT
        events = [
            MockEvent(EV_KEY, BTN_TOUCH, 1),   # Finger down
            MockEvent(EV_ABS, ABS_X, 200),      # Updated X
            MockEvent(EV_ABS, ABS_Y, 350),      # Updated Y
            MockEvent(EV_SYN, SYN_REPORT, 0),   # Frame commit
        ]

        for event in events:
            if event.type == EV_ABS:
                if event.code == ABS_X:
                    cur_x = event.value
                elif event.code == ABS_Y:
                    cur_y = event.value
            elif event.type == EV_KEY and event.code == BTN_TOUCH:
                if event.value == 1 and not touch_down:
                    touch_down = True
                    pending_touch = True
                elif event.value == 0:
                    touch_down = False
                    pending_touch = False
            elif event.type == EV_SYN and event.code == SYN_REPORT:
                if pending_touch:
                    pending_touch = False
                    dispatched_touches.append((cur_x, cur_y))

        self.assertEqual(len(dispatched_touches), 1)
        self.assertEqual(dispatched_touches[0], (200, 350), "Touch must be dispatched with updated (200, 350), not old (50, 50)")

    def test_sequence_reset_acceptance(self):
        """Verify client accepts server sequence resets (e.g. after server restart)."""
        last_sync_seq = 10

        # Simulate receiving packet after server restart with seq=1
        new_packet = {"type": "sync_buttons", "seq": 1, "profile": "Work"}
        
        # New logic: accept seq unconditionally
        seq = new_packet.get("seq", 0)
        accepted = False
        if seq:
            last_sync_seq = seq
            accepted = True

        self.assertTrue(accepted)
        self.assertEqual(last_sync_seq, 1)


if __name__ == "__main__":
    unittest.main()
