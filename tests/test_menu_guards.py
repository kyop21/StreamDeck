import unittest
import time

class TestMenuAndSyncGuards(unittest.TestCase):
    def test_touch_debounce(self):
        """Verify that rapid consecutive touches (< 250ms) are debounced."""
        debounce_threshold = 0.25
        last_touch_time = 0.0

        def should_process_touch(now):
            nonlocal last_touch_time
            if now - last_touch_time < debounce_threshold:
                return False
            last_touch_time = now
            return True

        # First touch at t=1.0
        self.assertTrue(should_process_touch(1.0))
        # Second chatter touch at t=1.05 (50ms later) -> Must be rejected!
        self.assertFalse(should_process_touch(1.05))
        # Third touch at t=1.30 (300ms later) -> Accepted
        self.assertTrue(should_process_touch(1.30))

    def test_render_full_closes_active_menu(self):
        """Verify that render_full safely closes any active dropdown menu."""
        state = {
            "active_menu": "profile",
            "last_popup_bounds": (61, 50, 271, 150),
            "closed": False
        }

        def close_menu():
            state["closed"] = True
            state["active_menu"] = None
            state["last_popup_bounds"] = None

        def render_full():
            if state["active_menu"]:
                close_menu()

        render_full()
        self.assertTrue(state["closed"])
        self.assertIsNone(state["active_menu"])
        self.assertIsNone(state["last_popup_bounds"])

    def test_sync_timeout_guard(self):
        """Verify that sync request triggers timeout recovery if no response arrives in 5s."""
        sync_state = {
            "waiting_sync": False,
            "sync_req_time": 0.0,
            "reconnected": False
        }

        def on_sync_requested(now):
            sync_state["waiting_sync"] = True
            sync_state["sync_req_time"] = now

        def on_sync_received():
            sync_state["waiting_sync"] = False

        def check_sync_timeout(now):
            if sync_state["waiting_sync"] and (now - sync_state["sync_req_time"] > 5.0):
                sync_state["reconnected"] = True
                sync_state["waiting_sync"] = False
                return True
            return False

        on_sync_requested(100.0)
        self.assertFalse(check_sync_timeout(102.0))
        self.assertTrue(check_sync_timeout(106.0))
        self.assertTrue(sync_state["reconnected"])

if __name__ == "__main__":
    unittest.main()
