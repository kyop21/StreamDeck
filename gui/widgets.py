from typing import Dict, Any
from pathlib import Path
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel, QMenu, QAction
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QCursor, QPixmap


class DeckButtonWidget(QFrame):
    """
    스트림덱 개별 가상 버튼 위젯 (Windows 2000 레트로 스타일).
    좌클릭: PC에서 액션 직접 실행
    우클릭: 액션 편집 다이얼로그 호출
    """
    clicked = pyqtSignal(int)
    edit_requested = pyqtSignal(int)

    def __init__(self, button_id: int, parent=None):
        super().__init__(parent)
        self.button_id = button_id
        self.data: Dict[str, Any] = {}
        self.init_ui()

    def init_ui(self):
        self.setFixedSize(110, 105)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        # 상단 테마 컬러 스트립 바 (테마 색상 시각화)
        self.accent_bar = QFrame(self)
        self.accent_bar.setFixedHeight(4)
        self.accent_bar.setStyleSheet("background-color: #000080; border: 1px inset #808080;")

        # 중앙 Windows 2000 픽셀 아이콘
        self.lbl_icon = QLabel(self)
        self.lbl_icon.setAlignment(Qt.AlignCenter)
        self.lbl_icon.setFixedHeight(30)
        self.lbl_icon.setStyleSheet("background: transparent;")

        # 중앙 제목 라벨 (Win2K Tahoma 볼드 폰트)
        self.lbl_title = QLabel(f"Btn {self.button_id}", self)
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #000000; font-family: Tahoma; background: transparent;")

        # 하단 액션 타입 뱃지 라벨
        self.lbl_badge = QLabel("EMPTY", self)
        self.lbl_badge.setAlignment(Qt.AlignCenter)
        self.lbl_badge.setStyleSheet("font-size: 8px; color: #404040; background: #e0ded8; border: 1px dotted #808080; padding: 1px 3px;")

        layout.addWidget(self.accent_bar)
        layout.addWidget(self.lbl_icon)
        layout.addWidget(self.lbl_title)
        layout.addStretch()
        layout.addWidget(self.lbl_badge)

        self.update_style("#00f0ff")

    def update_data(self, data: Dict[str, Any]):
        self.data = data
        title = data.get("title", f"Btn {self.button_id}")
        act_type = data.get("action_type", "")
        color = data.get("color", "#000080")
        icon_name = data.get("icon", "")

        self.lbl_title.setText(title)
        self.lbl_badge.setText(act_type.upper() if act_type else "EMPTY")
        self.accent_bar.setStyleSheet(f"background-color: {color}; border: 1px inset #404040;")

        # Windows 2000 레트로 아이콘 로드
        if icon_name:
            icon_path = Path(__file__).resolve().parent.parent / "web" / "icons" / icon_name
            if not icon_path.exists():
                icon_path = Path(__file__).resolve().parent.parent / "web" / "static" / "icons" / icon_name
            if icon_path.exists():
                pix = QPixmap(str(icon_path)).scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.lbl_icon.setPixmap(pix)
                self.lbl_icon.show()
            else:
                self.lbl_icon.clear()
        else:
            self.lbl_icon.clear()

        self.update_style(color)

    def update_style(self, accent_color: str):
        self.setStyleSheet(f"""
            DeckButtonWidget {{
                background-color: #d4d0c8;
                border-top: 2px solid #ffffff;
                border-left: 2px solid #ffffff;
                border-right: 2px solid #404040;
                border-bottom: 2px solid #404040;
                border-radius: 0px;
            }}
            DeckButtonWidget:hover {{
                background-color: #dfdbd2;
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.button_id)
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPos())
        super().mousePressEvent(event)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        act_exec = QAction("지금 바로 실행", self)
        act_exec.triggered.connect(lambda: self.clicked.emit(self.button_id))

        act_edit = QAction("버튼 설정 편집...", self)
        act_edit.triggered.connect(lambda: self.edit_requested.emit(self.button_id))

        menu.addAction(act_exec)
        menu.addSeparator()
        menu.addAction(act_edit)
        menu.exec_(pos)
