import os
import sys
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

def create_deck_presentation(output_path: str):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # Color Palette (Modern Clean Tech & Windows 2000 Legacy)
    C_DARK = RGBColor(15, 23, 42)        # Slate 900
    C_NAVY = RGBColor(10, 37, 100)       # Deep Win2K Navy
    C_BLUE = RGBColor(37, 99, 235)       # Accent Blue
    C_CARD_BG = RGBColor(248, 250, 252)  # Slate 50
    C_CARD_BORDER = RGBColor(203, 213, 225) # Slate 300
    C_TEXT_MAIN = RGBColor(30, 41, 59)   # Slate 800
    C_TEXT_MUTED = RGBColor(100, 116, 139) # Slate 500
    C_WHITE = RGBColor(255, 255, 255)
    C_ACCENT_BG = RGBColor(239, 246, 255) # Light Blue 50
    C_ACCENT_BORDER = RGBColor(191, 219, 254)

    FONT_TITLE = "Malgun Gothic"
    FONT_BODY = "Malgun Gothic"

    def add_header(slide, title_text, category_text="Physical AI 로봇 SW 개발"):
        # Header Accent Line
        accent = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(0.55), Inches(0.12), Inches(0.7))
        accent.fill.solid()
        accent.fill.fore_color.rgb = C_BLUE
        accent.line.fill.background()

        # Header Text Box
        tx_box = slide.shapes.add_textbox(Inches(1.05), Inches(0.48), Inches(11.0), Inches(0.85))
        tf = tx_box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

        p_sub = tf.paragraphs[0]
        p_sub.text = category_text.upper()
        p_sub.font.name = FONT_TITLE
        p_sub.font.size = Pt(10.5)
        p_sub.font.bold = True
        p_sub.font.color.rgb = C_BLUE

        p_main = tf.add_paragraph()
        p_main.text = title_text
        p_main.font.name = FONT_TITLE
        p_main.font.size = Pt(21)
        p_main.font.bold = True
        p_main.font.color.rgb = C_DARK

    def add_card(slide, left, top, width, height, title, items, badge="", bg_color=C_CARD_BG, border_color=C_CARD_BORDER):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        card.fill.solid()
        card.fill.fore_color.rgb = bg_color
        card.line.color.rgb = border_color
        card.line.width = Pt(1.2)

        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.28)
        tf.margin_right = Inches(0.28)
        tf.margin_top = Inches(0.24)
        tf.margin_bottom = Inches(0.2)

        p_title = tf.paragraphs[0]
        p_title.text = f"{title}"
        if badge:
            p_title.text += f"  [{badge}]"
        p_title.font.name = FONT_TITLE
        p_title.font.size = Pt(14)
        p_title.font.bold = True
        p_title.font.color.rgb = C_NAVY
        p_title.space_after = Pt(8)

        for item in items:
            p = tf.add_paragraph()
            p.text = f"•  {item}"
            p.font.name = FONT_BODY
            p.font.size = Pt(11)
            p.font.color.rgb = C_TEXT_MAIN
            p.space_after = Pt(4.5)

    # =========================================================================
    # SLIDE 1: Cover Slide
    # =========================================================================
    s1 = prs.slides.add_slide(blank_layout)

    # Background Top Banner
    bg_top = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(4.5))
    bg_top.fill.solid()
    bg_top.fill.fore_color.rgb = C_NAVY
    bg_top.line.fill.background()

    # Title & Subtitle in Banner
    tb_cov = s1.shapes.add_textbox(Inches(1.2), Inches(1.1), Inches(11.0), Inches(2.6))
    tf_cov = tb_cov.text_frame
    tf_cov.word_wrap = True

    p_c1 = tf_cov.paragraphs[0]
    p_c1.text = "Physical AI 로봇 소프트웨어 엔지니어링 결과보고서"
    p_c1.font.name = FONT_TITLE
    p_c1.font.size = Pt(15)
    p_c1.font.color.rgb = RGBColor(147, 197, 253) # Light Blue
    p_c1.space_after = Pt(10)

    p_c2 = tf_cov.add_paragraph()
    p_c2.text = "TailDeck 2000 Professional"
    p_c2.font.name = FONT_TITLE
    p_c2.font.size = Pt(36)
    p_c2.font.bold = True
    p_c2.font.color.rgb = C_WHITE
    p_c2.space_after = Pt(12)

    p_c3 = tf_cov.add_paragraph()
    p_c3.text = "Tailscale 보안 사설망 기반 초저지연 무선 가상 스트림덱 시스템 구축"
    p_c3.font.name = FONT_TITLE
    p_c3.font.size = Pt(17)
    p_c3.font.color.rgb = RGBColor(226, 232, 240)

    # Bottom Metadata Card
    meta_card = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.2), Inches(4.9), Inches(10.933), Inches(1.8))
    meta_card.fill.solid()
    meta_card.fill.fore_color.rgb = C_WHITE
    meta_card.line.color.rgb = C_CARD_BORDER
    meta_card.line.width = Pt(1)

    tf_m = meta_card.text_frame
    tf_m.margin_left = Inches(0.4)
    tf_m.margin_top = Inches(0.3)
    tf_m.margin_right = Inches(0.4)

    p_m1 = tf_m.paragraphs[0]
    p_m1.text = "프로젝트 주요 산출물 요약"
    p_m1.font.name = FONT_TITLE
    p_m1.font.size = Pt(13)
    p_m1.font.bold = True
    p_m1.font.color.rgb = C_DARK
    p_m1.space_after = Pt(6)

    p_m2 = tf_m.add_paragraph()
    p_m2.text = "• 핵심 아키텍처: PyQt5 데스크톱 스튜디오 + aiohttp / WebSocket 비동기 서버 + Win32 ctypes 제어 엔진"
    p_m2.font.name = FONT_BODY
    p_m2.font.size = Pt(11)
    p_m2.font.color.rgb = C_TEXT_MAIN
    p_m2.space_after = Pt(3)

    p_m3 = tf_m.add_paragraph()
    p_m3.text = "• 클라이언트 환경: 스마트폰 QR 즉시 접속 무설치 웹앱 | Windows 2000 레트로 3D 인터페이스 (34종 전용 픽셀 아이콘)"
    p_m3.font.name = FONT_BODY
    p_m3.font.size = Pt(11)
    p_m3.font.color.rgb = C_TEXT_MAIN
    p_m3.space_after = Pt(3)

    p_m4 = tf_m.add_paragraph()
    p_m4.text = "• 제출자: 홍길동  |  개발 환경: Windows 11, Python 3.11, PyQt5, Tailscale Mesh VPN"
    p_m4.font.name = FONT_BODY
    p_m4.font.size = Pt(11)
    p_m4.font.bold = True
    p_m4.font.color.rgb = C_BLUE

    # =========================================================================
    # SLIDE 2: Background & Objective
    # =========================================================================
    s2 = prs.slides.add_slide(blank_layout)
    add_header(s2, "1. 프로젝트 기획 배경 및 개발 목표")

    add_card(s2, Inches(0.8), Inches(1.6), Inches(3.64), Inches(5.2),
             "기존 하드웨어 한계",
             [
                 "고가의 전용 하드웨어 비용 부담: 수십만 원 상당의 물리 스트림덱 기기 필요",
                 "물리적 휴대성 및 공간 제약: 이동형 작업 공간 및 협소한 로봇 연구 환경에서 배치 어려움",
                 "플랫폼 종속적 드라이버: 폐쇄적 전용 소프트웨어 설치 필수 및 확장성 한계",
                 "장치 간 연결 케이블 복잡도: USB 유선 연결 필수"
             ],
             badge="Problem")

    add_card(s2, Inches(4.84), Inches(1.6), Inches(3.64), Inches(5.2),
             "핵심 개발 목표",
             [
                 "무설치(Zero-Install) 모바일 연동: 스마트폰 카메라로 QR 스캔 즉시 실행",
                 "Tailscale 기반 보안 사설망 통신: 복잡한 포트포워딩 없이 외부 LTE/5G에서도 암호화 P2P 연결",
                 "초저지연 양방향 동기화: WebSocket 프로토콜 기반 30ms 이내 반응속도",
                 "Windows 2000 레트로 UI/UX: 3D 베벨 버튼, Tahoma 볼드 폰트, 34종 픽셀 아이콘"
             ],
             badge="Goal", bg_color=C_ACCENT_BG, border_color=C_ACCENT_BORDER)

    add_card(s2, Inches(8.88), Inches(1.6), Inches(3.64), Inches(5.2),
             "기대 효과 및 실용성",
             [
                 "비용 100% 절감: 공기계 스마트폰이나 태블릿을 완전한 매크로 패드로 전환",
                 "다양한 매크로 통합 제어: 앱 실행, 웹 열기, 미디어 제어, 단축키, 클립보드 타이핑 일원화",
                 "로봇/AI 연구 생산성 극대화: 자주 쓰는 터미널 명령어, 빌드 스크립트, 모니터링 즉각 호출",
                 "안정적인 Windows OS 자동화: Win32 API 직접 후킹으로 높은 제어 신뢰성"
             ],
             badge="Benefit")

    # =========================================================================
    # SLIDE 3: System Architecture
    # =========================================================================
    s3 = prs.slides.add_slide(blank_layout)
    add_header(s3, "2. 시스템 아키텍처 및 기술 스택")

    add_card(s3, Inches(0.8), Inches(1.6), Inches(5.7), Inches(5.2),
             "계층별 시스템 구조 (Layered Architecture)",
             [
                 "[Layer 1] 모바일 웹 클라이언트 (Vanilla JS / CSS3):",
                 "  - 별도 앱 없이 Safari/Chrome 등 모든 브라우저 호환",
                 "  - CSS Grid 반응형 정사각형 타일 + 3D 베벨 음각/양각 렌더링",
                 "  - 터치 포인터 이벤트 기반 즉각 반응 및 30ms 햅틱 진동",
                 "[Layer 2] 통신 & 보안 계층 (Tailscale / WebSocket):",
                 "  - Tailscale WireGuard 사설망 IP (100.x.y.z) 자동 감지",
                 "  - aiohttp 기반 비동기 웹서버 + 양방향 WebSocket 통신",
                 "[Layer 3] PC 데스크톱 관리 계층 (PyQt5 Studio):",
                 "  - QThread 기반 백그라운드 서버 분리 (UI Freeze 방지)",
                 "  - 실시간 LCD 접속자 카운터 및 QTableView 로그 모니터",
                 "[Layer 4] 윈도우 OS 액션 제어 엔진 (Win32 API):",
                 "  - ctypes.windll.user32 / kernel32를 통한 직접 키/마우스 제어",
                 "  - 클립보드 GlobalAlloc 메모리 매핑 기반 고속 타이핑 매크로"
             ])

    add_card(s3, Inches(6.8), Inches(1.6), Inches(5.7), Inches(5.2),
             "핵심 기술 스택 및 라이브러리 역할",
             [
                 "PyQt5 (GUI Framework):",
                 "  - 메인 스튜디오 대시보드 및 커스텀 액션 다이얼로그 구현",
                 "  - QThread, Signal & Slot을 활용한 비동기 이벤트 안전 처리",
                 "aiohttp (Asynchronous HTTP / WebSocket Server):",
                 "  - 비동기 코루틴 기반 정적 파일 서빙 및 양방향 WebSocket 전송",
                 "qrcode & Pillow (PIL):",
                 "  - 스마트폰 접속 주소를 고해상도 QR 이미지로 인메모리 버퍼 생성",
                 "  - 34종 Windows 2000 클래식 아이콘의 32x32 픽셀 규격 정밀 추출",
                 "ctypes (Standard Win32 API Bridge):",
                 "  - 외부 서드파티 의존성 없이 순수 Windows 핵심 DLL(user32 등) 호출",
                 "  - Volume Mute, Play/Pause, Hotkey 시뮬레이션, 화면 잠금 지원"
             ],
             bg_color=C_ACCENT_BG, border_color=C_ACCENT_BORDER)

    # =========================================================================
    # SLIDE 4: PC Studio Features
    # =========================================================================
    s4 = prs.slides.add_slide(blank_layout)
    add_header(s4, "3. 주요 기능 (1) - PC 데스크톱 관리 스튜디오")

    add_card(s4, Inches(0.8), Inches(1.6), Inches(5.7), Inches(2.45),
             "가상 스트림덱 그리드 프리뷰",
             [
                 "3x4 총 12개 가상 버튼 실시간 렌더링 (모바일 화면과 1:1 동기화)",
                 "좌클릭: PC 화면에서 즉시 액션 직접 실행 및 테스트",
                 "우클릭: 해당 버튼의 상세 속성 설정 다이얼로그 호출"
             ])

    add_card(s4, Inches(6.8), Inches(1.6), Inches(5.7), Inches(2.45),
             "버튼 속성 편집 및 34종 레트로 아이콘",
             [
                 "버튼 제목, 액션 타입, 실행 페이로드, 테마 컬러 팔레트 편집",
                 "Windows 2000/98 정품 32x32 픽셀 아이콘 34종 드롭다운 선택",
                 "수정 즉시 WebSocket 브로드캐스트로 모바일 기기에 실시간 반영"
             ])

    add_card(s4, Inches(0.8), Inches(4.35), Inches(5.7), Inches(2.45),
             "Tailscale 연동 및 QR 원터치 페어링",
             [
                 "Tailscale CLI 자동 질의를 통한 100.x.y.z 사설망 IP 우선 감지",
                 "접속 URL을 담은 고해상도 QR 코드 자동 생성 및 라벨 표시",
                 "클립보드 URL 복사 및 기본 웹 브라우저 열기 편의 버튼 제공"
             ])

    add_card(s4, Inches(6.8), Inches(4.35), Inches(5.7), Inches(2.45),
             "실시간 실행 로그 & 클라이언트 모니터링",
             [
                 "상단 고전 녹색 LCD 인디케이터를 통한 동시 접속자 수 표시",
                 "QTableView 및 QAbstractTableModel 기반 실시간 실행 로그 기록",
                 "실행 시각, 버튼 번호, 버튼 제목, 액션 종류, 성공/실패 상태 추적"
             ])

    # =========================================================================
    # SLIDE 5: Mobile Web Deck Features
    # =========================================================================
    s5 = prs.slides.add_slide(blank_layout)
    add_header(s5, "4. 주요 기능 (2) - 모바일 웹 스트림덱 인터페이스")

    add_card(s5, Inches(0.8), Inches(1.6), Inches(5.7), Inches(2.45),
             "완벽한 Windows 2000 레트로 UI/UX",
             [
                 "Win2K 특유의 3D 양각/음각 테두리 및 클래식 그레이(#d4d0c8) 질감",
                 "상단 테마 컬러 스트립 바 + 중앙 픽셀 아이콘 + 하단 액션 뱃지",
                 "버튼 높이 대비 시각적 무게중심을 완벽히 보정한 중앙 하향 정렬"
             ])

    add_card(s5, Inches(6.8), Inches(1.6), Inches(5.7), Inches(2.45),
             "실시간 인터랙션 및 피드백",
             [
                 "포인터 다운 시 3D 물리 버튼 함몰 애니메이션(inset 1px) 즉시 적용",
                 "스마트폰 햅틱 진동 피드백(30ms Vibration) 동시 발생",
                 "명령 결과에 따른 플래시 효과 (성공: 연녹색, 실패: 빨간색, 350ms)"
             ])

    add_card(s5, Inches(0.8), Inches(4.35), Inches(5.7), Inches(2.45),
             "메뉴바 연동 화면 제어 (View/File)",
             [
                 "View 메뉴 드롭다운을 통한 화면 확대(+), 축소(-), 100% 원래 크기 복원",
                 "모바일 전체화면(Full Screen) 토글 버튼을 메뉴바 내부에 통합",
                 "File 메뉴를 통한 새로고침 및 세션 관리 기능"
             ])

    add_card(s5, Inches(6.8), Inches(4.35), Inches(5.7), Inches(2.45),
             "안정적인 연결 상태 모니터링",
             [
                 "하단 음각 상태표시줄(Sunken Status Bar)을 통한 실시간 정보 제공",
                 "LED 비콘(녹색: 온라인, 빨간색: 오프라인) 자동 전환",
                 "버튼 실행 요청 및 서버 응답 상태 메시지 실시간 텍스트 알림"
             ])

    # =========================================================================
    # SLIDE 6: Windows Action Automation
    # =========================================================================
    s6 = prs.slides.add_slide(blank_layout)
    add_header(s6, "5. 주요 기능 (3) - 윈도우 OS 액션 자동화 엔진")

    add_card(s6, Inches(0.8), Inches(1.6), Inches(3.64), Inches(2.45),
             "앱 실행 및 URL 열기",
             [
                 "app: Chrome, 메모장, 계산기 등 시스템 앱 및 임의 .exe 백그라운드 호출",
                 "url: YouTube, GitHub 등 기본 웹 브라우저 탭 즉시 열기"
             ],
             badge="App / URL")

    add_card(s6, Inches(4.84), Inches(1.6), Inches(3.64), Inches(2.45),
             "멀티미디어 및 볼륨 제어",
             [
                 "volume_up / volume_down: 윈도우 마스터 볼륨 정밀 조절",
                 "volume_mute: 음소거 원클릭 토글",
                 "play_pause / next / prev: 음악/영상 미디어 트랙 제어"
             ],
             badge="Media")

    add_card(s6, Inches(8.88), Inches(1.6), Inches(3.64), Inches(2.45),
             "복합 단축키 시뮬레이션",
             [
                 "hotkey: win+d (바탕화면 보기), ctrl+c, alt+f4 등",
                 "가상 키 코드(VK) 순차 누름/해제 로직을 통한 정확한 핫키 전달"
             ],
             badge="Hotkey")

    add_card(s6, Inches(0.8), Inches(4.35), Inches(3.64), Inches(2.45),
             "클립보드 고속 타이핑 매크로",
             [
                 "typing: 자주 쓰는 상용구, 코드 템플릿 즉각 입력",
                 "Win32 클립보드 GlobalAlloc 바인딩 + Ctrl+V 조합으로 한글 깨짐 없이 초고속 입력"
             ],
             badge="Typing")

    add_card(s6, Inches(4.84), Inches(4.35), Inches(3.64), Inches(2.45),
             "시스템 제어 및 전원 관리",
             [
                 "system: LockWorkStation을 통한 즉시 화면 잠금",
                 "절전 모드 전환 및 1분 후 시스템 종료 예약 / 취소 지원"
             ],
             badge="System")

    add_card(s6, Inches(8.88), Inches(4.35), Inches(3.64), Inches(2.45),
             "스크립트 백그라운드 실행",
             [
                 "script: PowerShell(.ps1), 배치파일(.bat) 비동기 실행",
                 "로봇 시뮬레이터 실행, ROS 노드 기동 등 복잡한 워크플로우 연계"
             ],
             badge="Script")

    # =========================================================================
    # SLIDE 7: UI/UX & Icons Detail
    # =========================================================================
    s7 = prs.slides.add_slide(blank_layout)
    add_header(s7, "6. UI/UX 디자인 디테일 및 34종 픽셀 아이콘 세트")

    add_card(s7, Inches(0.8), Inches(1.6), Inches(5.7), Inches(5.2),
             "34종 Windows 2000/98 전용 아이콘 라이브러리",
             [
                 "철저한 규격 통일: 모든 아이콘을 32x32 픽셀 아트 정품 프레임으로 통일",
                 "카테고리별 풍부한 아이콘 구성:",
                 "  - 인터넷/네트워크: IE 지구본, 아웃룩 메일, 네트워크 PC, 즐겨찾기",
                 "  - 파일/스토리지: 윈도우 탐색기, 폴더, 내 문서, 3.5 플로피 디스크,",
                 "                 C: 하드 드라이브, 휴지통, 파일 검색 돋보기",
                 "  - 시스템/관리: 내 컴퓨터, 제어판 기어, 작업 관리자, 명령 프롬프트,",
                 "                실행(Run), 보안 자물쇠, 종료, 정지(Stop)",
                 "  - 멀티미디어: 미디어 플레이어, 오디오 CD, 스피커 음소거, 볼륨,",
                 "               마이크 입력, 화면 캡처 카메라",
                 "  - 생산성/유틸: 계산기, 메모장, 워드패드, 그림판, 시계, 조이스틱, 도움말",
                 "고해상도 디스플레이 대응: image-rendering: pixelated 설정으로 레트로 픽셀 질감 완벽 보존"
             ])

    add_card(s7, Inches(6.8), Inches(1.6), Inches(5.7), Inches(5.2),
             "사용자 중심 세부 UX 최적화 내역",
             [
                 "1. 버튼 내부 시각적 무게중심 안정화:",
                 "  - 하단 액션 뱃지(14px)로 인해 아이콘이 상단으로 쏠리던 현상 분석",
                 "  - .btn-content 컨테이너에 padding-top: 6px를 부여하여 상하 황금비율 정중앙 안착",
                 "2. 메뉴바 통합 뷰 컨트롤러:",
                 "  - 거추장스러운 별도 툴바를 제거하고 고전 윈도우 View 메뉴 안에 확대/축소 및 전체화면 통합",
                 "3. 하이라이트 잔상 버그 해결:",
                 "  - 모바일 터치 후 색상 하이라이트가 꺼지지 않던 이슈를 reflow 및 타이머 재설정으로 해결",
                 "4. 한글 타이핑 매크로 클립보드 보호:",
                 "  - 64비트 Windows API 구조체 시그니처를 명시하여 한글 누락/충돌 원천 차단"
             ],
             bg_color=C_ACCENT_BG, border_color=C_ACCENT_BORDER)

    # =========================================================================
    # SLIDE 8: Conclusion & Future Work
    # =========================================================================
    s8 = prs.slides.add_slide(blank_layout)
    add_header(s8, "7. 과제 수행 결과 및 결론")

    add_card(s8, Inches(0.8), Inches(1.6), Inches(5.7), Inches(5.2),
             "프로젝트 수행 성과 요약",
             [
                 "1. 고품질 무선 스트림덱 완성:",
                 "  - 물리 기기 구매 없이 스마트폰만으로 전문 매크로 제어 패널 완벽 구현",
                 "2. 엔지니어링 완성도 확보:",
                 "  - PyQt5(스레드 분리) + aiohttp(비동기 I/O) + Win32 API(네이티브 제어)의 견고한 연계 구조",
                 "3. 무설치 원격 보안 연결 실현:",
                 "  - Tailscale WireGuard VPN 연동으로 보안성과 접근성을 동시 달성",
                 "4. 레트로 감성과 현대적 사용성의 조화:",
                 "  - 2000년대 윈도우 감성을 충실히 재현하면서도 모바일 터치 햅틱 및 실시간 반응형 UX 극대화"
             ])

    add_card(s8, Inches(6.8), Inches(1.6), Inches(5.7), Inches(5.2),
             "향후 로봇 SW 연계 확장 방안",
             [
                 "1. ROS 2 / DDS 통신 노드 연동:",
                 "  - 버튼 터치로 ROS 2 Topic 발행(Emergency Stop, 모터 활성화, Waypoint 주행)",
                 "2. 실시간 로봇 텔레메트리 모니터링:",
                 "  - 스트림덱 버튼 화면에 로봇 배터리 잔량, CPU 온도, 센서 상태 실시간 표기",
                 "3. 다중 프로필(Multi-Profile) 시스템:",
                 "  - 일반 개발용 / 로봇 제어용 / 미디어 편집용 원클릭 프로필 스위칭",
                 "4. 하드웨어 스탠드 3D 프린팅 연계:",
                 "  - 스마트폰 거치용 전용 3D 케이스 모델링을 통한 완성도 높은 물리 패널 구축"
             ],
             bg_color=C_ACCENT_BG, border_color=C_ACCENT_BORDER)

    # Save Presentation
    prs.save(output_path)
    print(f"[OK] Presentation successfully saved to: {output_path}")

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "Physical_AI_로봇_SW개발_결과보고서(홍길동).pptx"
    create_deck_presentation(out)
