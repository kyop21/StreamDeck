# TailDeck 2000 Professional



## 1. 프로젝트 기획 배경 및 목표

* **기존 기기를 활용한 무선 컨트롤러**: 별도의 스트림덱 장비 없이 스마트폰, 태블릿, 공기계에서 매크로 컨트롤러를 사용할 수 있습니다.
* **모바일 브라우저 연동**: 모바일 기기에 전용 앱을 설치하지 않고, 카메라로 PC 화면의 QR 코드를 스캔해 브라우저에서 접속합니다.
* **Tailscale 사설망 연결**: 라우터 포트 포워딩 없이 WireGuard 기반 사설망을 통해 외부 LTE/5G 환경에서 작업 PC에 접속할 수 있습니다.
* **Windows 2000 스타일 UI**: 클래식 Windows 스타일의 버튼과 34종 픽셀 아이콘을 제공합니다.

## 2. 시스템 아키텍처 (Layered Architecture)

```text
[Layer 1] 모바일 웹 클라이언트 (Vanilla JS / CSS3)
   - 브라우저 무설치 실행, CSS Grid 반응형 타일 렌더링, 포인터 이벤트 기반 햅틱 진동
            │ (WebSocket 통신)
[Layer 2] 네트워크 계층 (Tailscale Mesh VPN / aiohttp)
   - WireGuard 암호화 P2P 사설망 IP 자동 감지, 비동기 이벤트 루프 기반 실시간 동기화
            │ (Qt 시그널/슬롯을 이용한 서버 스레드와 GUI 간 통신)
[Layer 3] PC 데스크톱 GUI (PyQt5)
   - QThread로 서버를 별도 스레드에서 실행, 3x4 가상 덱 미리보기, LCD 및 로그 테이블
            │ (ctypes 윈도우 API 네이티브 호출)
[Layer 4] Windows 액션 제어 (Win32 API)
   - user32 / kernel32 기반 단축키, 미디어 볼륨, 클립보드를 이용한 텍스트 입력
```



## 3. 프로젝트 디렉터리 구조 및 파일별 역할

```text
StreamDeck/
├── config.json               # 3x4 버튼 배치 정보, 색상, 아이콘, 액션 페이로드 데이터 (JSON)
├── main.py                   # 프로그램 진입점 (High DPI 스케일링 설정, QThread 서버 및 메인 윈도우 구동)
├── requirements.txt          # 프로젝트 구동에 필요한 외부 의존성 패키지 목록
├── README.md                 # 프로젝트 상세 설계서 및 사용 설명서
├── core/
│   ├── actions.py            # Win32 ctypes API 기반 7가지 Windows 액션 실행
│   ├── config.py             # 버튼 설정 로드, 저장, 자동 마이그레이션 관리자
│   ├── network.py            # Tailscale 사설 IP 감지 및 QR 코드 생성
│   └── server.py             # aiohttp를 이용한 웹 파일 제공 및 WebSocket 서버 (QThread)
├── gui/
│   ├── dialog_action.py      # 버튼 속성 편집 다이얼로그 (커스텀 아이콘 등록 및 처리)
│   ├── log_model.py          # 실행 이력 관리 및 조건부 서식 적용 QAbstractTableModel
│   ├── main_window.py        # 메인 GUI (가상 덱 그리드, QR 연동 패널, 로그 테이블)
│   └── widgets.py            # 3D 베벨 스타일 가상 스트림덱 개별 버튼 위젯
└── web/
    ├── app.js                # 모바일 클라이언트 WebSocket 통신, 터치 제어 및 피드백 처리
    ├── index.html            # Windows 2000 창 스타일 모바일 웹 레이아웃
    ├── style.css             # Win2K 레트로 테마 스타일링 및 반응형 그리드 CSS
    └── icons/ / static/icons/# 34종 레트로 픽셀 아이콘 및 사용자 커스텀 등록 아이콘
```



## 4. PyQt5 이외 추가 설치 모듈 설명

본 프로젝트는 PyQt5 외에 비동기 네트워크 통신, 모바일 연동, 이미지 처리를 위해 다음 라이브러리를 사용합니다.

| 모듈명 | 최소 버전 | 도입 목적 및 역할 상세 설명 |
| :--- | :--- | :--- |
| **aiohttp** | `>=3.8.0` | **HTTP 정적 파일 서빙 및 WebSocket 통신**<br>- 모바일 브라우저에 웹 클라이언트 리소스(HTML/CSS/JS/아이콘)를 제공합니다.<br>- 버튼 명령을 받고 PC 실행 결과를 WebSocket으로 전송합니다.<br>- `QThread` 내부의 `asyncio` 이벤트 루프에서 실행되어 GUI와 서버 작업을 분리합니다. |
| **qrcode** | `>=7.0` | **접속 QR 코드 생성**<br>- 서버 IP(Tailscale 사설망 우선, 로컬 IP 폴백)와 포트를 조합한 웹 접속 URL을 QR 코드로 변환합니다. |
| **Pillow (PIL)** | `>=9.0.0` | **QR 코드 및 이미지 처리**<br>- `qrcode` 모듈이 만든 QR 코드를 GUI 표시용 PNG 바이트로 변환합니다.<br>- 사용자가 등록한 이미지(PNG, JPG, ICO 등)의 투명 여백을 제거하고, 비율을 유지해 64×64 크기로 조정합니다. |


## 5. 실행 및 사용 방법 (Quick Start)

### 1) 실행 환경 준비
* 운영체제: Windows 10 / 11 (64-bit 권장)
* Python 버전: Python 3.9 이상

```bash
# 가상환경 생성 (선택 사항)
python -m venv venv
venv\Scripts\activate

# 의존성 패키지 설치
pip install -r requirements.txt
```

### 2) 프로그램 실행
```bash
python main.py
```

### 3) 모바일 기기 접속 및 조작
1. 프로그램 실행 시 메인 윈도우 우측에 접속 URL과 QR 코드가 자동으로 렌더링됩니다.
2. 스마트폰 카메라로 QR 코드를 스캔하여 브라우저로 접속합니다. (동일 로컬 Wi-Fi 또는 Tailscale 망 연결 필요)
3. 모바일 화면에서 버튼을 터치하면 햅틱 진동과 함께 PC에서 해당 액션이 실행되며, PC 메인 창 좌측의 가상 버튼을 직접 클릭하여 테스트할 수도 있습니다.
4. PC 화면의 가상 버튼을 마우스 우클릭하면 버튼 제목, 테마 색상, 34종 레트로 아이콘 및 사용자 커스텀 아이콘, 액션 내용을 자유롭게 변경할 수 있습니다.



## 6. 주요 기능 및 제어 스펙

1. **7가지 Windows 액션**:
   * `app`: 크롬, 메모장, 계산기 등 Windows 등록 앱 및 임의 실행 파일(.exe) 백그라운드 호출
   * `url`: 기본 웹 브라우저를 통해 지정된 웹사이트 열기
   * `media`: 시스템 볼륨 올리기/내리기, 음소거 토글, 미디어 재생/일시정지, 다음/이전 트랙 제어
   * `hotkey`: 복합 키보드 단축키 전송 (`win+d`, `ctrl+c`, `alt+tab` 등)
   * `system`: 화면 잠금(Lock), 절전 모드(Sleep), 시스템 종료 예약 및 취소
   * `script`: 배치 파일(.bat, .cmd) 및 파워쉘(.ps1) 스크립트 실행
   * `typing`: Windows 클립보드를 이용한 유니코드 텍스트 입력

2. **아이콘 시스템**:
   * Windows 2000/98 스타일의 32x32 픽셀 아이콘 34종 기본 제공
   * 사용자 정의 이미지 등록 시 여백 자동 크롭 및 64x64 정규화 자동 처리

3. **실시간 모니터링**:
   * 상단 녹색 LCD 인디케이터를 통한 실시간 동시 접속자 수 카운팅
   * `QTableView` 기반 실시간 명령 실행 이력(시각, 버튼 ID, 제목, 액션 타입, 성공/실패) 테이블 기록
