# [인수인계] TailDeck 2000 멀티 프로필 시스템 구축 및 DietPi(라즈베리 파이 1) 초고속 프레임버퍼 렌더링 최적화

> 작성 일시: 2026-10-15 09:12
> 관련 워크스페이스: `C:\Users\Son\Downloads\TailDeck2000_PROFESSIONAL` (Git 관리 디렉터리) 및 `C:\workspace`
> 원격 장치: DietPi (Raspberry Pi 1 Model B/B+, Tailscale IP `100.72.170.44`, 계정 `root:1234`)

## 1. 작업 개요 (Background & Goal)
* 사용자의 요청에 따라 TailDeck 2000 시스템에 페이지(프로필) 전환 시스템을 설계 및 구현함.
* PC GUI(PyQt5) 및 DietPi 네이티브 프레임버퍼 클라이언트(`taildeck_fb.py`) 간 실시간 프로필 동기화 지원.
* 라즈베리 파이 1(ARMv6 700MHz) 하드웨어에서 상단 메뉴바 반응 지연(기존 572ms)의 원인을 실측 분석하고, RAM 서피스 캐싱 및 부분 블릿(Partial Blit) 기술을 통해 3.9ms로 단축(약 146배 성능 향상)하여 하단 3x4 버튼 그리드와 동일한 초고속 즉각 반응성을 확보함.

## 2. 완료된 작업 및 변경 파일 (Completed Work)

### 2.1 PC 서버 및 코어 로직
* [core/config.py](file:///C:/Users/Son/Downloads/TailDeck2000_PROFESSIONAL/core/config.py):
  - `schema_version: 2` 멀티 프로필 스키마 정의 (`current_profile`, `profiles: { <name>: { grid_rows, grid_cols, buttons } }`).
  - 구버전 평면 `config.json` 자동 감지 및 무손실 마이그레이션 로직 구현 (기존 설정은 `Default` 프로필로 흡수).
  - 저장 시 `.bak` 백업 생성 및 원자적 파일 쓰기(`tempfile` + `os.replace`), `deep_merge`를 통한 데이터 무결성 보장.
  - 프로필 생성(`create_profile`), 삭제(`delete_profile`), 전환(`switch_profile`), 목록 조회(`get_profile_names`) API 구현.
* [core/server.py](file:///C:/Users/Son/Downloads/TailDeck2000_PROFESSIONAL/core/server.py):
  - WebSocket 프로토콜 확장: `get_profiles` (목록 요청), `switch_profile` (프로필 전환 요청) 핸들러 추가.
  - 프로필 전환 시 순서 보장을 위한 단조 증가 시퀀스 번호(`seq`) 패킷 헤더 적용 및 전체 클라이언트에 `sync_buttons` 브로드캐스트.
* [gui/main_window.py](file:///C:/Users/Son/Downloads/TailDeck2000_PROFESSIONAL/gui/main_window.py):
  - 상단 툴바에 Win2K 스타일 프로필 선택 드롭다운(`QComboBox`) 및 프로필 추가(`+`), 삭제(`-`) 버튼 추가.
  - 사용자 피드백(스크린샷)을 반영하여 `+`, `-` 버튼 스타일 및 툴팁을 시각적으로 명확히 분리/강화.
  - 프로필 전환 시 그리드 위젯 및 서버 동기화 자동 연동.
* [gui/widgets.py](file:///C:/Users/Son/Downloads/TailDeck2000_PROFESSIONAL/gui/widgets.py) 및 [gui/dialog_action.py](file:///C:/Users/Son/Downloads/TailDeck2000_PROFESSIONAL/gui/dialog_action.py):
  - Win2K 스타일 일관성 유지 및 액션 편집 다이얼로그 개선.
* [tests/test_profiles.py](file:///C:/Users/Son/Downloads/TailDeck2000_PROFESSIONAL/tests/test_profiles.py):
  - 스키마 마이그레이션, 원자적 백업, 프로필 CRUD, 시퀀스 번호 검증 단위 테스트 작성 (13개 전체 통과).

### 2.2 DietPi 네이티브 프레임버퍼 클라이언트 (Raspberry Pi 1)
* 로컬 파일: [scratch/taildeck_fb.py](file:///C:/Users/Son/.gemini/antigravity-cli/brain/b45b02ba-6a21-4401-a4c8-7f044717fe4c/scratch/taildeck_fb.py)
* 원격 배포 경로: DietPi(`/root/taildeck_fb.py`) via systemd (`taildeck.service`)
* **핵심 최적화 내역**:
  1. **RAM 서피스 캐싱 및 부분 블릿 (Partial Blit)**:
     - 768KB의 기본 배경화면(`clean_base_bytes`)을 RAM에 항시 보존.
     - 상단 메뉴(파일, 프로필, 보기, 재생, 도구, 도움말)를 독립된 210x180 RGB565 서피스로 캐싱(`menu_cache`).
     - 메뉴 터치 시 해당 좌표만 mmap 직복사 (`blit_rect`): **3.91ms** 소요.
     - 메뉴 닫기 시 배경 버퍼에서 해당 영역만 복원 (`restore_rect_from_base`): **3.25ms** 소요.
  2. **타이틀바 그라데이션 벡터화**:
     - 기존 PIL 라인 루프(162.8ms 소요)를 NumPy 선형 보간(`np.linspace` + `np.tile`)으로 전면 교체하여 **1.5ms**로 단축.
  3. **웹소켓 피드백 분리**:
     - 버튼 누름 시 PC 서버가 반환하는 `action_result` 및 `error` 메시지 수신 시 전체 화면 재렌더링(`render_full`)을 제거하고, 하단 상태바만 부분 갱신(`update_status_msg`, 약 1.5ms)하도록 분리.
     - `profile_list` 수신 시 상단 메뉴가 열려 있는 상태에서도 끊김 없이 프로필 목록만 갱신되도록 개선.

## 3. 현재 상태 및 검증 결과 (Current State)

### 3.1 PC 서버 상태
* 단위 테스트 결과: `python -m unittest discover -s tests` 실행 시 **13 passed in 0.896s** (All Green).
* Git 워킹 트리 상태 (`C:\Users\Son\Downloads\TailDeck2000_PROFESSIONAL`):
  - 수정됨(`M`): `config.json`, `core/config.py`, `core/server.py`, `gui/dialog_action.py`, `gui/main_window.py`, `gui/widgets.py`, `web/app.js`, `web/style.css`
  - 기존 삭제 상태 유지(`D`): `create_presentation.py`
  - 신규 파일(`??`): `tests/test_profiles.py`, `tests/test_deck_guards.py`, `config.json.bak`, `start_taildeck.bat`, `README.md`
  - 파괴적 Git 연산 없이 모든 기존 작업 및 백업 보존됨.

### 3.2 DietPi 하드웨어 및 서비스 상태
* 호스트: DietPi (Raspberry Pi 1 armv6l, 512MB RAM, 단일 코어 700MHz)
* 네트워크: Tailscale 가상 사설망 연결 정상 (`100.72.170.44`)
* systemd 상태: `taildeck.service` 정상 동작 중 (`active (running)`)
  - 터치 디바이스: `/dev/input/event5` (raspberrypi-ts) 정상 바인딩
  - 프레임버퍼: `/dev/fb0` (800x480 @ 16bpp RGB565) 정상 연동
  - 원격 파이썬 컴파일: `python3 -m py_compile /root/taildeck_fb.py` 성공

## 4. 다음 세션 작업 계획 (Next Steps)

1. [ ] **[우선순위 1] PC 메인 서버(`main.py`) 실구동 및 하드웨어 연동 최종 확인**
   - PC에서 `python main.py` 실행 후, DietPi의 `taildeck.service`가 PC 서버(포트 8080)에 정상 접속하여 `온라인 [Default]` 상태로 연결되는지 확인.
   - PC GUI에서 프로필 추가(`새 프로필`) 및 전환 시, DietPi 화면의 프로필 메뉴와 버튼 배치가 실시간으로 갱신되는지 실물 터치 검증.
2. [ ] **[우선순위 2] 워킹 트리 커밋 및 정리**
   - 검증 완료 후 `git add` 및 커밋 (`feat: multi-profile support and win2k native framebuffer partial blit optimization`).
3. [ ] **[우선순위 3] 웹 인터페이스(Web UI) 프로필 전환 기능 연동 검토**
   - 현재 PC GUI 및 네이티브 파이 프레임버퍼에는 프로필 전환이 완전 연동되었으나, 웹 인터페이스(`web/app.js`) 상단에도 프로필 선택 드롭다운 추가 여부 검토.

## 5. 새 세션 진입 프롬프트 가이드 (Prompt for Next Session)

다음 새 대화 세션에서 아래 프롬프트를 복사하여 붙여넣으세요:
```text
@HANDOFF_taildeck_multi_profile_fb_opt.md 읽고 4번 항목의 '다음 세션 작업 계획'부터 이어서 진행해줘.
```
