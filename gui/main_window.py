import copy
import io
import webbrowser
from typing import List, Dict, Any

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QTableView, QHeaderView,
    QGroupBox, QLCDNumber, QMessageBox, QApplication, QInputDialog
)
from PyQt5.QtCore import Qt, pyqtSlot, QSignalBlocker
from PyQt5.QtGui import QPixmap, QImage, QFont

from core.config import ConfigManager
from core.network import get_server_ip, generate_qr_png_bytes
from gui.widgets import DeckButtonWidget
from gui.dialog_action import ActionEditDialog
from gui.log_model import LogTableModel


class MainWindow(QMainWindow):
    """
    TailDeck PC 스트림덱 스튜디오 메인 윈도우.
    가상 3x4 덱 조작, QR 코드 서빙, 실시간 모바일 동기화 및 실행 로그 관리.
    """
    def __init__(self, config_mgr: ConfigManager, server_thread=None, parent=None):
        super().__init__(parent)
        self.config_mgr = config_mgr
        self.server_thread = server_thread
        self.btn_widgets: List[DeckButtonWidget] = []

        self.server_ip = get_server_ip()
        self.server_port = 2000
        self.mobile_url = f"http://{self.server_ip}:{self.server_port}"

        self.init_ui()
        self.load_buttons_ui()

        # 서버 시그널 바인딩
        if self.server_thread:
            self.server_thread.log_signal.connect(self.on_server_log)
            self.server_thread.client_count_signal.connect(self.on_client_count_changed)
            self.server_thread.profile_changed_signal.connect(self.on_external_profile_changed)

    def init_ui(self):
        self.setWindowTitle("TailDeck 2000 Professional - [Tailscale Remote]")
        self.resize(1080, 720)
        self.setStyleSheet("""
            QMainWindow { background-color: #d4d0c8; }
            QWidget { color: #000000; font-family: 'Tahoma', 'MS Sans Serif', sans-serif; font-size: 11px; }
            QGroupBox {
                background-color: #d4d0c8;
                border: 2px groove #ffffff;
                border-radius: 0px;
                margin-top: 10px;
                padding: 12px;
                font-weight: bold;
                color: #000080;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QTableView {
                background-color: #ffffff;
                border-top: 2px solid #808080;
                border-left: 2px solid #808080;
                border-right: 2px solid #ffffff;
                border-bottom: 2px solid #ffffff;
                gridline-color: #d4d0c8;
                color: #000000;
                selection-background-color: #0a246a;
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background-color: #d4d0c8;
                color: #000000;
                padding: 4px;
                border-top: 1px solid #ffffff;
                border-left: 1px solid #ffffff;
                border-right: 1px solid #404040;
                border-bottom: 1px solid #404040;
                font-weight: bold;
            }
            QPushButton {
                background-color: #d4d0c8;
                border-top: 2px solid #ffffff;
                border-left: 2px solid #ffffff;
                border-right: 2px solid #404040;
                border-bottom: 2px solid #404040;
                border-radius: 0px;
                padding: 4px 12px;
                font-weight: bold;
                color: #000000;
            }
            QPushButton:hover { background-color: #dfdbd2; }
            QPushButton:pressed {
                border-top: 2px solid #404040;
                border-left: 2px solid #404040;
                border-right: 2px solid #ffffff;
                border-bottom: 2px solid #ffffff;
                padding: 5px 11px 3px 13px;
            }
            QComboBox {
                background-color: #ffffff;
                border-top: 2px solid #808080;
                border-left: 2px solid #808080;
                border-right: 2px solid #ffffff;
                border-bottom: 2px solid #ffffff;
                padding: 2px 6px;
                color: #000000;
            }
            QStatusBar {
                background-color: #d4d0c8;
                color: #000000;
                border-top: 1px solid #808080;
            }
        """)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 1. 상단 바 (브랜드 + 상태)
        top_bar = QHBoxLayout()
        lbl_brand = QLabel("TAILDECK 2000 PROFESSIONAL", self)
        lbl_brand.setStyleSheet("font-size: 14px; font-weight: bold; color: #000080; letter-spacing: 1px;")
        top_bar.addWidget(lbl_brand)

        top_bar.addStretch()

        # 모바일 접속자 수 인디케이터
        top_bar.addWidget(QLabel("온라인 클라이언트:", self))
        self.lcd_clients = QLCDNumber(self)
        self.lcd_clients.setDigitCount(2)
        self.lcd_clients.display(0)
        self.lcd_clients.setFixedSize(50, 24)
        self.lcd_clients.setStyleSheet("background: #000000; color: #00ff00; border: 2px inset #808080;")
        top_bar.addWidget(self.lcd_clients)

        main_layout.addLayout(top_bar)

        # 2. 중앙 메인 분할 (좌: 가상 스트림덱 그리드 / 우: Tailscale 접속 패널)
        mid_layout = QHBoxLayout()
        mid_layout.setSpacing(16)

        # [좌측] 3x4 가상 스트림덱 패널
        deck_box = QGroupBox("가상 스트림덱 (3x4)", self)
        deck_layout = QVBoxLayout(deck_box)
        deck_layout.setContentsMargins(14, 16, 14, 14)

        # 프로필 관리 툴바
        profile_bar = QHBoxLayout()
        profile_bar.setSpacing(6)
        lbl_profile = QLabel("프로필:", self)
        lbl_profile.setStyleSheet("font-weight: bold; color: #000080;")
        profile_bar.addWidget(lbl_profile)

        self.combo_profile = QComboBox(self)
        self.combo_profile.setMinimumWidth(140)
        profile_bar.addWidget(self.combo_profile, stretch=1)

        btn_add_profile = QPushButton("추가...", self)
        btn_add_profile.setToolTip("새 프로필 추가 (현재 프로필 복제)")
        btn_add_profile.clicked.connect(self.on_add_profile)
        profile_bar.addWidget(btn_add_profile)

        btn_del_profile = QPushButton("삭제", self)
        btn_del_profile.setToolTip("현재 프로필 삭제")
        btn_del_profile.clicked.connect(self.on_delete_profile)
        profile_bar.addWidget(btn_del_profile)

        deck_layout.addLayout(profile_bar)

        self.refresh_profiles_ui()
        self.combo_profile.currentTextChanged.connect(self.on_profile_combo_changed)

        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(10)

        # 12개 버튼 생성 및 그리드 배치
        for i in range(12):
            btn = DeckButtonWidget(i, self)
            btn.clicked.connect(self.on_btn_clicked)
            btn.edit_requested.connect(self.on_btn_edit)
            btn.copy_requested.connect(self.on_btn_copy)
            btn.paste_requested.connect(self.on_btn_paste)
            btn.clear_requested.connect(self.on_btn_clear)
            r = i // 4
            c = i % 4
            self.grid_layout.addWidget(btn, r, c)
            self.btn_widgets.append(btn)

        deck_layout.addLayout(self.grid_layout)

        lbl_guide = QLabel("안내: 좌클릭 = PC에서 실행 | 우클릭 = 설정 메뉴 (편집 / 복사 / 붙여넣기 / 초기화)", self)
        lbl_guide.setStyleSheet("color: #555555; font-size: 11px;")
        deck_layout.addWidget(lbl_guide)

        mid_layout.addWidget(deck_box, stretch=6)

        # [우측] Tailscale 연동 및 QR 코드 패널
        qr_box = QGroupBox("스마트폰 원격 연동 (Tailscale)", self)
        qr_layout = QVBoxLayout(qr_box)
        qr_layout.setContentsMargins(14, 16, 14, 14)
        qr_layout.setSpacing(10)

        # QR 코드 이미지 표시 라벨
        self.lbl_qr = QLabel(self)
        self.lbl_qr.setAlignment(Qt.AlignCenter)
        self.lbl_qr.setFixedSize(180, 180)
        self.lbl_qr.setStyleSheet("background: #ffffff; border-top: 2px solid #808080; border-left: 2px solid #808080; border-right: 2px solid #ffffff; border-bottom: 2px solid #ffffff; padding: 4px;")
        qr_layout.addWidget(self.lbl_qr, alignment=Qt.AlignCenter)

        # 접속 주소 라벨
        self.lbl_url = QLabel(self.mobile_url, self)
        self.lbl_url.setAlignment(Qt.AlignCenter)
        self.lbl_url.setStyleSheet("font-size: 11px; font-weight: bold; color: #000000; background: #ffffff; border-top: 2px solid #808080; border-left: 2px solid #808080; border-right: 2px solid #ffffff; border-bottom: 2px solid #ffffff; padding: 4px;")
        qr_layout.addWidget(self.lbl_url)

        # URL 복사 & 브라우저 열기 버튼
        btn_bar = QHBoxLayout()
        btn_copy = QPushButton("URL 복사", self)
        btn_copy.clicked.connect(self._copy_url)
        btn_open_browser = QPushButton("브라우저 열기", self)
        btn_open_browser.clicked.connect(lambda: webbrowser.open(self.mobile_url))

        btn_bar.addWidget(btn_copy)
        btn_bar.addWidget(btn_open_browser)
        qr_layout.addLayout(btn_bar)

        desc_label = QLabel(
            "스마트폰 카메라로 위 QR 코드를 스캔하세요.\n"
            "Tailscale 사설망에 연결된 기기라면\n"
            "앱 설치 없이 브라우저로 즉시 제어됩니다.",
            self
        )
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setStyleSheet("color: #404040; font-size: 11px; line-height: 1.4;")
        qr_layout.addWidget(desc_label)

        qr_layout.addStretch()
        mid_layout.addWidget(qr_box, stretch=4)

        main_layout.addLayout(mid_layout, stretch=6)

        # 3. 하단 실시간 실행 로그 패널
        log_box = QGroupBox("실시간 실행 로그 (Real-time Log)", self)
        log_layout = QVBoxLayout(log_box)
        log_layout.setContentsMargins(12, 14, 12, 10)

        self.log_model = LogTableModel(self)
        self.table_log = QTableView(self)
        self.table_log.setModel(self.log_model)
        self.table_log.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_log.setSelectionBehavior(QTableView.SelectRows)
        self.table_log.setAlternatingRowColors(True)
        log_layout.addWidget(self.table_log)

        # 로그 클리어 바
        log_bar = QHBoxLayout()
        log_bar.addStretch()
        btn_clear = QPushButton("로그 지우기", self)
        btn_clear.clicked.connect(self.log_model.clear)
        log_bar.addWidget(btn_clear)
        log_layout.addLayout(log_bar)

        main_layout.addWidget(log_box, stretch=4)

        # QR 코드 렌더링
        self._render_qr()

        # 하단 상태표시줄
        self.statusBar().showMessage(f"TailDeck 서버 실행 중: {self.mobile_url}")

    def _render_qr(self):
        try:
            png_bytes = generate_qr_png_bytes(self.mobile_url)
            qimg = QImage.fromData(png_bytes)
            pixmap = QPixmap.fromImage(qimg).scaled(170, 170, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_qr.setPixmap(pixmap)
        except Exception as e:
            self.lbl_qr.setText("QR 생성 실패")
            print(f"QR Error: {e}")

    def _copy_url(self):
        QApplication.clipboard().setText(self.mobile_url)
        self.statusBar().showMessage("접속 URL이 클립보드에 복사되었습니다!", 3000)

    def load_buttons_ui(self):
        """현재 활성 프로필의 버튼 데이터를 그리드 위젯 전체에 반영 (빈 슬롯 클리어 포함)"""
        buttons = self.config_mgr.get_buttons()
        btn_dict = {b.get("id"): b for b in buttons if "id" in b}
        for bid, widget in enumerate(self.btn_widgets):
            btn_data = btn_dict.get(bid, {
                "id": bid,
                "title": f"Btn {bid}",
                "color": "#000080",
                "icon": "",
                "action_type": "",
                "payload": ""
            })
            widget.update_data(btn_data)

    # 하위 호환용 alias
    load_profile_ui = load_buttons_ui

    def refresh_profiles_ui(self):
        """프로필 콤보박스 목록 갱신 (시그널 루프 방지 블로킹 적용)"""
        with QSignalBlocker(self.combo_profile):
            self.combo_profile.clear()
            profiles = self.config_mgr.get_profiles()
            self.combo_profile.addItems(profiles)
            cur = self.config_mgr.get_current_profile_name()
            idx = self.combo_profile.findText(cur)
            if idx != -1:
                self.combo_profile.setCurrentIndex(idx)

    @pyqtSlot(str)
    def on_profile_combo_changed(self, profile_name: str):
        """PC GUI 콤보박스에서 사용자가 프로필을 직접 변경했을 때"""
        if not profile_name:
            return
        cur_name = self.config_mgr.get_current_profile_name()
        if profile_name == cur_name:
            return
        if self.config_mgr.switch_profile(profile_name):
            self.load_buttons_ui()
            if self.server_thread:
                self.server_thread.broadcast_buttons()
            self.statusBar().showMessage(f"프로필이 '{profile_name}'(으)로 변경되었습니다.", 3000)

    @pyqtSlot(str)
    def on_external_profile_changed(self, profile_name: str):
        """외부(DietPi / 모바일) WebSocket에서 프로필 변경 시 PC GUI 동기화 (루프백 방지)"""
        with QSignalBlocker(self.combo_profile):
            idx = self.combo_profile.findText(profile_name)
            if idx == -1:
                self.refresh_profiles_ui()
                idx = self.combo_profile.findText(profile_name)
            if idx != -1:
                self.combo_profile.setCurrentIndex(idx)
        self.load_buttons_ui()
        self.statusBar().showMessage(f"원격 기기 요청으로 프로필이 '{profile_name}'(으)로 변경되었습니다.", 3000)

    def on_add_profile(self):
        """새 프로필 추가 다이얼로그 (현재 프로필 복제)"""
        cur_profile = self.config_mgr.get_current_profile_name()
        name, ok = QInputDialog.getText(
            self, "새 프로필 추가",
            f"새 프로필 이름을 입력하세요 (현재 '{cur_profile}' 복제):"
        )
        if ok and name.strip():
            name = name.strip()
            if name in self.config_mgr.get_profiles():
                QMessageBox.warning(self, "경고", f"프로필 '{name}'이(가) 이미 존재합니다.")
                return
            if self.config_mgr.create_profile(name, copy_from=cur_profile):
                self.refresh_profiles_ui()
                self.load_buttons_ui()
                if self.server_thread:
                    self.server_thread.broadcast_buttons()
                self.statusBar().showMessage(f"새 프로필 '{name}'이(가) 생성되었습니다.", 3000)

    def on_delete_profile(self):
        """현재 프로필 삭제 다이얼로그 (최소 1개 유지 가드)"""
        profiles = self.config_mgr.get_profiles()
        if len(profiles) <= 1:
            QMessageBox.warning(self, "삭제 불가", "최소 1개의 프로필은 유지되어야 합니다.")
            return
        cur_profile = self.config_mgr.get_current_profile_name()
        reply = QMessageBox.question(
            self, "프로필 삭제",
            f"현재 프로필 '{cur_profile}'을(를) 정말 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if self.config_mgr.delete_profile(cur_profile):
                self.refresh_profiles_ui()
                self.load_buttons_ui()
                if self.server_thread:
                    self.server_thread.broadcast_buttons()
                new_current = self.config_mgr.get_current_profile_name()
                self.statusBar().showMessage(f"프로필 '{cur_profile}'이(가) 삭제되었습니다. (현재: {new_current})", 3000)

    @pyqtSlot(int)
    def on_btn_clicked(self, button_id: int):
        # PC에서 직접 클릭 -> 서버 스레드로 위임 실행
        if self.server_thread:
            self.server_thread.trigger_button_from_pc(button_id)

    def _apply_button_update(self, button_id: int, data: Dict[str, Any], status_msg: str):
        self.config_mgr.update_button(button_id, data)
        if 0 <= button_id < len(self.btn_widgets):
            self.btn_widgets[button_id].update_data(data)
        if self.server_thread:
            self.server_thread.broadcast_buttons()
        self.statusBar().showMessage(status_msg, 3000)

    @pyqtSlot(int)
    def on_btn_edit(self, button_id: int):
        btn_data = self.config_mgr.get_button(button_id) or {"id": button_id}
        dlg = ActionEditDialog(btn_data, self)
        if dlg.exec_() == ActionEditDialog.Accepted:
            updated = dlg.get_data()
            self._apply_button_update(
                button_id, updated,
                f"버튼 #{button_id} 설정이 저장 및 모바일에 동기화되었습니다."
            )

    @pyqtSlot(int)
    def on_btn_copy(self, button_id: int):
        btn_data = self.config_mgr.get_button(button_id)
        if not btn_data or not btn_data.get("action_type"):
            self.statusBar().showMessage(f"버튼 #{button_id}은(는) 설정되지 않은 빈 버튼이므로 복사할 수 없습니다.", 3000)
            return
        DeckButtonWidget.clipboard_data = copy.deepcopy(btn_data)
        title = btn_data.get("title", f"Btn {button_id}")
        self.statusBar().showMessage(f"버튼 #{button_id} ('{title}') 설정이 클립보드에 복사되었습니다.", 3000)

    @pyqtSlot(int)
    def on_btn_paste(self, button_id: int):
        if not DeckButtonWidget.clipboard_data:
            return
        new_data = copy.deepcopy(DeckButtonWidget.clipboard_data)
        new_data["id"] = button_id
        title = new_data.get("title", f"Btn {button_id}")
        self._apply_button_update(
            button_id, new_data,
            f"버튼 #{button_id}에 복사된 설정('{title}')을 붙여넣었습니다."
        )

    @pyqtSlot(int)
    def on_btn_clear(self, button_id: int):
        btn_data = self.config_mgr.get_button(button_id) or {}
        title = btn_data.get("title", f"Btn {button_id}")
        reply = QMessageBox.question(
            self,
            "버튼 초기화",
            f"버튼 #{button_id} ('{title}') 설정을 비우시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            empty_data = {
                "id": button_id,
                "title": f"Btn {button_id}",
                "color": "#000080",
                "icon": "",
                "action_type": "",
                "payload": ""
            }
            self._apply_button_update(
                button_id, empty_data,
                f"버튼 #{button_id} 설정이 초기화되었습니다."
            )

    @pyqtSlot(str, int, str, str, str)
    def on_server_log(self, time_str, button_id, title, act_type, status):
        self.log_model.add_log(time_str, button_id, title, act_type, status)

    @pyqtSlot(int)
    def on_client_count_changed(self, count: int):
        self.lcd_clients.display(count)
        self.statusBar().showMessage(f"모바일 연결 상태 변경: 현재 {count}명 접속 중", 3000)

    def closeEvent(self, event):
        # 창 닫을 때 백그라운드 서버 스레드 안전 종료
        if self.server_thread:
            self.server_thread.stop()
        event.accept()
