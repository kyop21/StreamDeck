import re
from pathlib import Path
from typing import Dict, Any
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QPushButton,
    QColorDialog, QFileDialog, QDialogButtonBox, QMessageBox
)
from PyQt5.QtCore import Qt

ACTION_TYPES = [
    ("app", "응용 프로그램 실행 (.exe)"),
    ("url", "웹사이트 URL 열기"),
    ("media", "윈도우 미디어/볼륨 제어"),
    ("hotkey", "키보드 단축키/키조합"),
    ("system", "시스템 제어 (화면 잠금/절전)"),
    ("script", "쉘 스크립트 실행 (.bat/.ps1)"),
    ("typing", "텍스트 타이핑 매크로"),
]

AVAILABLE_ICONS = [
    ("", "(아이콘 없음)"),
    # 인터넷 & 네트워크
    ("ie.png", "인터넷 익스플로러 (지구본)"),
    ("mail.png", "아웃룩 익스프레스 (이메일)"),
    ("network.png", "네트워크 환경 (두 대의 PC)"),
    ("favorites.png", "즐겨찾기 / 북마크"),
    # 파일 & 탐색
    ("explorer.png", "윈도우 파일 탐색기"),
    ("folder.png", "폴더 (디렉터리)"),
    ("my_documents.png", "내 문서 (바인더)"),
    ("search.png", "파일 검색 / 찾기 (돋보기)"),
    ("trash.png", "휴지통 (Recycle Bin)"),
    # 저장 매체 & 하드웨어
    ("floppy.png", "플로피 디스켓 (저장 매크로)"),
    ("hard_disk.png", "로컬 하드 드라이브 (C:)"),
    ("printer.png", "프린터 / 인쇄"),
    # 시스템 & 관리
    ("desktop.png", "내 컴퓨터 / 바탕화면"),
    ("settings.png", "제어판 / 시스템 설정"),
    ("task_mgr.png", "작업 관리자 (성능)"),
    ("cmd.png", "MS-DOS 명령 프롬프트"),
    ("run.png", "프로그램 실행 (Run)"),
    ("lock.png", "시스템 보안 / 자물쇠"),
    ("shutdown.png", "컴퓨터 끄기 (시스템 종료)"),
    ("stop.png", "정지 / 중단 (STOP)"),
    # 멀티미디어 & 오디오
    ("media_player.png", "윈도우 미디어 플레이어"),
    ("play.png", "오디오 CD / 재생"),
    ("vol_mute.png", "스피커 음소거 (Mute)"),
    ("vol_up.png", "스피커 볼륨 올리기"),
    ("vol_down.png", "스피커 볼륨 내리기"),
    ("mic.png", "마이크 / 음성 입력"),
    ("camera.png", "카메라 / 화면 캡처"),
    # 유틸리티 & 생산성
    ("calc.png", "윈도우 계산기"),
    ("notepad.png", "윈도우 메모장"),
    ("typing.png", "워드패드 / 문서 편집"),
    ("paint.png", "그림판 / 그래픽"),
    ("clock.png", "시계 / 타이머"),
    ("game.png", "게임 / 조이스틱"),
    ("help.png", "도움말 책"),
]

MEDIA_OPTIONS = [
    ("volume_up", "볼륨 올리기 (Volume Up)"),
    ("volume_down", "볼륨 내리기 (Volume Down)"),
    ("volume_mute", "음소거 토글 (Mute)"),
    ("play_pause", "재생 / 일시정지 (Play/Pause)"),
    ("next_track", "다음 곡 (Next Track)"),
    ("prev_track", "이전 곡 (Prev Track)"),
]

SYSTEM_OPTIONS = [
    ("lock", "화면 잠금 (Lock Workstation)"),
    ("sleep", "절전 모드 (Sleep)"),
    ("shutdown", "1분 후 시스템 종료 (Shutdown)"),
    ("cancel_shutdown", "시스템 종료 예약 취소"),
]


class ActionEditDialog(QDialog):
    """
    스트림덱 버튼의 동작 및 비주얼 속성을 편집하는 모달 대화상자.
    4장 표준 및 사용자 다이얼로그 기법 적용.
    """
    def __init__(self, button_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.button_data = dict(button_data)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f"버튼 #{self.button_data.get('id', 0)} 설정 편집")
        self.setMinimumWidth(440)
        self.setStyleSheet("""
            QDialog { background-color: #d4d0c8; color: #000000; font-family: 'Tahoma', sans-serif; font-size: 11px; }
            QLabel { color: #000000; font-weight: bold; }
            QLineEdit, QComboBox {
                background-color: #ffffff;
                border-top: 2px solid #808080;
                border-left: 2px solid #808080;
                border-right: 2px solid #ffffff;
                border-bottom: 2px solid #ffffff;
                padding: 4px;
                color: #000000;
            }
            QPushButton {
                background-color: #d4d0c8;
                border-top: 2px solid #ffffff;
                border-left: 2px solid #ffffff;
                border-right: 2px solid #404040;
                border-bottom: 2px solid #404040;
                padding: 4px 12px;
                color: #000000;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #dfdbd2; }
            QPushButton:pressed {
                border-top: 2px solid #404040;
                border-left: 2px solid #404040;
                border-right: 2px solid #ffffff;
                border-bottom: 2px solid #ffffff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        # 1. 버튼 제목
        self.edit_title = QLineEdit(self.button_data.get("title", ""), self)
        form.addRow("버튼 제목:", self.edit_title)

        # 2. 테마 색상 선택
        color_layout = QHBoxLayout()
        self.current_color = self.button_data.get("color", "#00f0ff")
        self.btn_color_preview = QPushButton(self.current_color, self)
        self.btn_color_preview.setStyleSheet(f"background-color: {self.current_color}; color: #000000; font-weight: bold;")
        self.btn_color_preview.clicked.connect(self._choose_color)
        color_layout.addWidget(self.btn_color_preview)
        form.addRow("테마 색상:", color_layout)

        # 3. 아이콘 선택 (Win2K 레트로 + 커스텀 파일 찾아보기)
        icon_layout = QHBoxLayout()
        self.combo_icon = QComboBox(self)
        for ico_file, ico_label in AVAILABLE_ICONS:
            self.combo_icon.addItem(ico_label, ico_file)
        cur_icon = self.button_data.get("icon", "")
        idx_ico = self.combo_icon.findData(cur_icon)
        if idx_ico >= 0:
            self.combo_icon.setCurrentIndex(idx_ico)
        elif cur_icon:
            self.combo_icon.addItem(f"[사용자 정의] {cur_icon}", cur_icon)
            self.combo_icon.setCurrentIndex(self.combo_icon.count() - 1)

        self.btn_browse_icon = QPushButton("찾아보기...", self)
        self.btn_browse_icon.clicked.connect(self._browse_custom_icon)

        icon_layout.addWidget(self.combo_icon, stretch=1)
        icon_layout.addWidget(self.btn_browse_icon)
        form.addRow("아이콘:", icon_layout)

        # 4. 액션 종류
        self.combo_action = QComboBox(self)
        for act_code, act_name in ACTION_TYPES:
            self.combo_action.addItem(act_name, act_code)
        
        current_act = self.button_data.get("action_type", "app")
        idx = self.combo_action.findData(current_act)
        if idx >= 0:
            self.combo_action.setCurrentIndex(idx)
        self.combo_action.currentIndexChanged.connect(self._on_action_type_changed)
        form.addRow("액션 종류:", self.combo_action)

        # 5. 페이로드 (동작 상세 내용)
        self.payload_layout = QHBoxLayout()
        self.edit_payload = QLineEdit(self.button_data.get("payload", ""), self)
        self.combo_payload = QComboBox(self)
        self.btn_browse = QPushButton("찾아보기...", self)
        self.btn_browse.clicked.connect(self._browse_file)

        self.payload_layout.addWidget(self.edit_payload)
        self.payload_layout.addWidget(self.combo_payload)
        self.payload_layout.addWidget(self.btn_browse)

        form.addRow("동작 내용:", self.payload_layout)
        layout.addLayout(form)

        # 힌트 라벨
        self.lbl_hint = QLabel(self)
        self.lbl_hint.setStyleSheet("color: #78909c; font-size: 11px;")
        layout.addWidget(self.lbl_hint)

        # 표준 확인/취소 버튼 박스
        self.btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.btn_box.accepted.connect(self._validate_and_accept)
        self.btn_box.rejected.connect(self.reject)
        layout.addWidget(self.btn_box)

        # 초기 필드 뷰 갱신
        self._on_action_type_changed()

    def _choose_color(self):
        col = QColorDialog.getColor(parent=self, title="테마 색상 선택")
        if col.isValid():
            self.current_color = col.name()
            self.btn_color_preview.setText(self.current_color)
            self.btn_color_preview.setStyleSheet(f"background-color: {self.current_color}; color: #000000; font-weight: bold;")

    def _on_action_type_changed(self):
        act = self.combo_action.currentData()
        current_val = self.edit_payload.text()

        if act in ("app", "script"):
            self.edit_payload.show()
            self.combo_payload.hide()
            self.btn_browse.show()
            self.lbl_hint.setText("실행할 프로그램(.exe) 또는 스크립트 파일의 전체 경로를 선택하세요.")

        elif act == "url":
            self.edit_payload.show()
            self.combo_payload.hide()
            self.btn_browse.hide()
            self.lbl_hint.setText("열고 싶은 웹사이트 URL을 입력하세요 (예: https://youtube.com)")

        elif act == "media":
            self.edit_payload.hide()
            self.combo_payload.show()
            self.btn_browse.hide()
            self.combo_payload.clear()
            for opt_val, opt_lbl in MEDIA_OPTIONS:
                self.combo_payload.addItem(opt_lbl, opt_val)
            idx = self.combo_payload.findData(current_val)
            if idx >= 0:
                self.combo_payload.setCurrentIndex(idx)
            self.lbl_hint.setText("윈도우 시스템 볼륨 또는 재생/일시정지 명령을 선택하세요.")

        elif act == "system":
            self.edit_payload.hide()
            self.combo_payload.show()
            self.btn_browse.hide()
            self.combo_payload.clear()
            for opt_val, opt_lbl in SYSTEM_OPTIONS:
                self.combo_payload.addItem(opt_lbl, opt_val)
            idx = self.combo_payload.findData(current_val)
            if idx >= 0:
                self.combo_payload.setCurrentIndex(idx)
            self.lbl_hint.setText("윈도우 화면 잠금이나 절전 모드 등 시스템 제어를 선택하세요.")

        elif act == "hotkey":
            self.edit_payload.show()
            self.combo_payload.hide()
            self.btn_browse.hide()
            self.lbl_hint.setText("단축키 조합을 '+'로 구분하여 입력하세요 (예: win+d, ctrl+c, alt+tab)")

        elif act == "typing":
            self.edit_payload.show()
            self.combo_payload.hide()
            self.btn_browse.hide()
            self.lbl_hint.setText("원터치로 자동 타이핑할 텍스트 문장을 입력하세요.")

    def _browse_custom_icon(self):
        """내 컴퓨터에서 임의의 이미지 파일을 선택하여 32x32 아이콘으로 자동 최적화 등록"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "커스텀 아이콘 선택",
            "",
            "이미지 파일 (*.png *.jpg *.jpeg *.ico *.bmp *.webp);;모든 파일 (*.*)"
        )
        if not file_path:
            return

        src_path = Path(file_path)
        safe_stem = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', src_path.stem)
        dest_filename = f"custom_{safe_stem}.png"

        base_dir = Path(__file__).resolve().parent.parent / "web"
        dest_dirs = [base_dir / "icons", base_dir / "static" / "icons"]
        for d in dest_dirs:
            d.mkdir(parents=True, exist_ok=True)

        try:
            from PIL import Image
            im = Image.open(src_path)

            # ICO 파일 중 적절한 원본 프레임 추출
            if getattr(im, 'ico', None) and hasattr(im.ico, 'sizes'):
                sizes = im.ico.sizes()
                best_size = (48, 48) if (48, 48) in sizes else ((32, 32) if (32, 32) in sizes else list(sizes)[0])
                im = im.ico.getimage(best_size)

            im = im.convert("RGBA")

            # 1. 투명 여백 자동 크롭 (Auto Crop - 알맹이 피사체만 정밀 추출)
            bbox = im.getbbox()
            if bbox:
                w_crop = bbox[2] - bbox[0]
                h_crop = bbox[3] - bbox[1]
                if w_crop > 4 and h_crop > 4:
                    im = im.crop(bbox)

            # 2. 64x64 캔버스에 최대 크기(94% 이상)로 꽉 차게 비율 유지 리사이즈 & 중앙 배치
            target_size = 64
            padding = 2
            max_dim = target_size - (padding * 2)  # 60px
            w, h = im.size
            scale = max_dim / max(w, h)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))

            im_resized = im.resize((new_w, new_h), Image.Resampling.LANCZOS)

            canvas = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
            paste_x = (target_size - new_w) // 2
            paste_y = (target_size - new_h) // 2
            canvas.paste(im_resized, (paste_x, paste_y), im_resized)

            for d in dest_dirs:
                canvas.save(str(d / dest_filename), format="PNG")

            existing_idx = self.combo_icon.findData(dest_filename)
            if existing_idx >= 0:
                self.combo_icon.setCurrentIndex(existing_idx)
            else:
                label_text = f"[사용자 정의] {src_path.name}"
                self.combo_icon.addItem(label_text, dest_filename)
                self.combo_icon.setCurrentIndex(self.combo_icon.count() - 1)

            QMessageBox.information(
                self,
                "아이콘 등록 성공",
                f"커스텀 아이콘 '{src_path.name}'이(가)\n여백 자동 제거 및 꽉 찬 고해상도(64×64) 규격으로 등록되었습니다."
            )
        except Exception as e:
            QMessageBox.warning(self, "아이콘 등록 오류", f"이미지 처리 중 오류가 발생했습니다:\n{str(e)}")

    def _browse_file(self):
        act = self.combo_action.currentData()
        if act == "app":
            path, _ = QFileDialog.getOpenFileName(self, "실행 파일 선택", "", "실행 파일 (*.exe *.bat *.cmd);;모든 파일 (*.*)")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "스크립트 선택", "", "스크립트 (*.bat *.cmd *.ps1);;모든 파일 (*.*)")

        if path:
            self.edit_payload.setText(path)

    def _validate_and_accept(self):
        title = self.edit_title.text().strip()
        if not title:
            QMessageBox.warning(self, "입력 오류", "버튼 제목을 입력해 주세요.")
            self.edit_title.setFocus()
            return

        act = self.combo_action.currentData()
        if act in ("media", "system"):
            payload = self.combo_payload.currentData() or ""
        else:
            payload = self.edit_payload.text().strip()

        self.button_data["title"] = title
        self.button_data["color"] = self.current_color
        self.button_data["icon"] = self.combo_icon.currentData() or ""
        self.button_data["action_type"] = act
        self.button_data["payload"] = payload

        self.accept()

    def get_data(self) -> Dict[str, Any]:
        return self.button_data
