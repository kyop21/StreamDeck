import sys
import os
from pathlib import Path

# StreamDeck 디렉토리를 sys.path에 추가하여 모듈 임포트 보장
STREAM_DECK_DIR = Path(__file__).resolve().parent
if str(STREAM_DECK_DIR) not in sys.path:
    sys.path.insert(0, str(STREAM_DECK_DIR))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

from core.config import ConfigManager
from core.server import StreamDeckServerThread
from gui.main_window import MainWindow


def main():
    # 고해상도 DPI 스케일링 활성화
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("TailDeck")

    # 1. 설정 관리자 로드
    config_mgr = ConfigManager()

    # 2. 백그라운드 웹 및 WebSocket 서버 스레드 시작
    server_thread = StreamDeckServerThread(config_mgr=config_mgr, host="0.0.0.0", port=8080)
    server_thread.start()

    # 3. 메인 GUI 스튜디오 윈도우 생성 및 표시
    main_window = MainWindow(config_mgr=config_mgr, server_thread=server_thread)
    main_window.show()

    # 4. 애플리케이션 실행 및 종료 동기화
    exit_code = app.exec_()

    # 5. 스레드 안전 종료 대기
    if server_thread.isRunning():
        server_thread.stop()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
