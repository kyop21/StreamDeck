import unittest


class SyncSequenceTracker:
    """라즈베리 파이 클라이언트와 동일한 시퀀스 번호 및 프로필 동기화 엔진"""
    def __init__(self):
        self.last_sync_seq = 0
        self.cached_profiles = ["Default"]
        self.buttons = []
        self.current_profile = "Default"

    def on_ws_open(self):
        self.last_sync_seq = 0

    def process_sync_message(self, data):
        seq = data.get("seq", 0)
        if seq:
            if seq < self.last_sync_seq:
                if self.last_sync_seq - seq > 20 or self.last_sync_seq > 50:
                    self.last_sync_seq = seq
                else:
                    return False  # Dropped out of order
            else:
                self.last_sync_seq = seq

        self.current_profile = data.get("profile", self.current_profile)
        if "profiles" in data and isinstance(data["profiles"], list) and data["profiles"]:
            self.cached_profiles = list(data["profiles"])
        elif self.current_profile and self.current_profile not in self.cached_profiles:
            self.cached_profiles.append(self.current_profile)

        self.buttons = data.get("buttons", [])
        return True


class TestSyncPacketLogic(unittest.TestCase):
    def setUp(self):
        self.tracker = SyncSequenceTracker()

    def test_reconnect_resets_sequence(self):
        """1) 새 소켓 연결(on_ws_open) 시 이전 누적 시퀀스 번호가 0으로 리셋되어야 함"""
        self.tracker.last_sync_seq = 126
        self.tracker.on_ws_open()
        self.assertEqual(self.tracker.last_sync_seq, 0)

    def test_accepts_sync_when_server_restarts(self):
        """2) PC 서버 재시작으로 seq가 126에서 6으로 재시작되어도 드롭되지 않고 수용되어야 함"""
        self.tracker.last_sync_seq = 126
        accepted = self.tracker.process_sync_message({
            "type": "sync_buttons",
            "seq": 6,
            "profile": "Default",
            "buttons": [{"id": 0, "title": "Chrome"}]
        })
        self.assertTrue(accepted, "서버 재시작으로 리셋된 seq는 정상 수용되어야 함")
        self.assertEqual(self.tracker.last_sync_seq, 6)
        self.assertEqual(len(self.tracker.buttons), 1)

    def test_drops_actual_out_of_order_packets(self):
        """3) 정상 스트림 중 단편적 역전 패킷(예: seq 15 수신 후 지연된 seq 14 도달)은 정상 드롭"""
        self.tracker.last_sync_seq = 15
        accepted = self.tracker.process_sync_message({
            "type": "sync_buttons",
            "seq": 14,
            "profile": "Default",
            "buttons": []
        })
        self.assertFalse(accepted, "미세한 역전 패킷은 드롭되어야 함")
        self.assertEqual(self.tracker.last_sync_seq, 15)

    def test_updates_profile_list_from_sync(self):
        """4) sync_buttons 페이로드의 profiles 목록이 클라이언트 캐시에 실시간 반영되어야 함"""
        self.tracker.cached_profiles = ["Default"]
        self.tracker.process_sync_message({
            "type": "sync_buttons",
            "seq": 1,
            "profile": "Work",
            "profiles": ["Default", "Work", "Media"],
            "buttons": []
        })
        self.assertEqual(self.tracker.cached_profiles, ["Default", "Work", "Media"])


if __name__ == "__main__":
    unittest.main()
