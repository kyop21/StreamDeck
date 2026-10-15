// TailDeck Mobile Client Application
(function () {
  const gridEl = document.getElementById("deckGrid");
  const beaconEl = document.getElementById("statusBeacon");
  const feedbackMsgEl = document.getElementById("feedbackMsg");

  let ws = null;
  let reconnectTimer = null;
  let buttonsData = [];
  const flashTimers = {};

  function getWsUrl() {
    const loc = window.location;
    const proto = loc.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${loc.host}/ws`;
  }

  function connect() {
    clearTimeout(reconnectTimer);
    updateStatus(false, "연결 중...");

    try {
      ws = new WebSocket(getWsUrl());
    } catch (e) {
      scheduleReconnect();
      return;
    }

    ws.onopen = function () {
      updateStatus(true, "Tailscale 연결 완료! 준비됨");
      try {
        ws.send(JSON.stringify({ type: "get_profiles" }));
      } catch (e) {}
    };

    ws.onclose = function () {
      updateStatus(false, "연결 끊김. 2초 후 재연결...");
      scheduleReconnect();
    };

    ws.onerror = function () {
      updateStatus(false, "소켓 오류 발생");
    };

    ws.onmessage = function (event) {
      try {
        const msg = JSON.parse(event.data);
        handleServerMessage(msg);
      } catch (err) {
        console.error("Message parse error:", err);
      }
    };
  }

  function scheduleReconnect() {
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connect, 2000);
  }

  const connTextEl = document.getElementById("connText");

  function updateStatus(connected, text) {
    if (connected) {
      beaconEl.className = "status-led connected";
      if (connTextEl) connTextEl.innerText = "연결됨";
    } else {
      beaconEl.className = "status-led disconnected";
      if (connTextEl) connTextEl.innerText = "오프라인";
    }
    feedbackMsgEl.innerText = text;
  }

  const dropdownProfileEl = document.getElementById("dropdownProfile");
  let currentProfileName = "Default";

  function updateProfileMenu(currentProfile, profilesList) {
    if (currentProfile) currentProfileName = currentProfile;
    if (!dropdownProfileEl) return;
    dropdownProfileEl.innerHTML = "";

    const list = (profilesList && profilesList.length > 0) ? profilesList : [currentProfileName];
    list.forEach(pName => {
      const itemEl = document.createElement("div");
      const isCurrent = (pName === currentProfileName);
      itemEl.className = "dropdown-item" + (isCurrent ? " active" : "");
      itemEl.innerText = (isCurrent ? "✓ " : "  ") + pName;
      itemEl.addEventListener("click", (e) => {
        e.stopPropagation();
        if (!isCurrent) {
          switchProfile(pName);
        }
        closeAllDropdowns();
      });
      dropdownProfileEl.appendChild(itemEl);
    });
  }

  function switchProfile(profileName) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    feedbackMsgEl.innerText = `프로필 전환 요청: ${profileName}...`;
    ws.send(JSON.stringify({ type: "switch_profile", name: profileName }));
  }

  function handleServerMessage(msg) {
    if (msg.type === "sync_buttons" || msg.type === "sync_profile") {
      buttonsData = msg.buttons || [];
      renderGrid(buttonsData, msg.grid_rows || 3, msg.grid_cols || 4);
      if (msg.profile) {
        updateProfileMenu(msg.profile, msg.profiles || []);
      }
    } else if (msg.type === "profile_list") {
      updateProfileMenu(msg.current, msg.profiles || []);
    } else if (msg.type === "action_result") {
      flashButton(msg.button_id, msg.status === "success");
      feedbackMsgEl.innerText = msg.message || (msg.status === "success" ? "성공" : "실패");
    } else if (msg.type === "error") {
      feedbackMsgEl.innerText = msg.message || "오류 발생";
    }
  }

  function renderGrid(buttons, rows, cols) {
    gridEl.innerHTML = "";
    gridEl.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
    gridEl.style.gridTemplateRows = `repeat(${rows}, auto)`;

    const total = rows * cols;
    for (let i = 0; i < total; i++) {
      const btnData = buttons.find(b => b.id === i) || {
        id: i,
        title: `Btn ${i}`,
        color: "#000080",
        action_type: "",
        payload: ""
      };

      const btnEl = document.createElement("button");
      btnEl.className = "deck-btn";
      btnEl.dataset.id = i;
      const accentColor = btnData.color || "#000080";
      btnEl.style.setProperty("--btn-accent", accentColor);

      const iconImgHtml = btnData.icon
        ? `<img class="btn-icon-img" src="/static/icons/${escapeHtml(btnData.icon)}" onerror="if(!this.dataset.retried){this.dataset.retried='1';this.src='/icons/${escapeHtml(btnData.icon)}';}" alt="" width="38" height="38">`
        : "";

      btnEl.innerHTML = `
        <div class="btn-accent-bar" style="background-color: ${accentColor};"></div>
        <div class="btn-content">
          ${iconImgHtml}
          <span class="btn-title">${escapeHtml(btnData.title || `Btn ${i}`)}</span>
        </div>
        <span class="btn-badge">${escapeHtml((btnData.action_type || "EMPTY").toUpperCase())}</span>
      `;

      // Touch / Click interactions with theme highlight
      btnEl.addEventListener("pointerdown", function (e) {
        btnEl.classList.add("btn-pressed");
        triggerButton(i);
      });
      btnEl.addEventListener("pointerup", function () {
        btnEl.classList.remove("btn-pressed");
      });
      btnEl.addEventListener("pointercancel", function () {
        btnEl.classList.remove("btn-pressed");
      });
      btnEl.addEventListener("pointerleave", function () {
        btnEl.classList.remove("btn-pressed");
      });

      gridEl.appendChild(btnEl);
    }
  }

  function triggerButton(buttonId) {
    // 햅틱 진동 피드백
    if (navigator.vibrate) {
      navigator.vibrate(30);
    }

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "trigger_button",
        button_id: buttonId
      }));
      feedbackMsgEl.innerText = `버튼 #${buttonId} 실행 요청 중...`;
    } else {
      feedbackMsgEl.innerText = "서버와 연결되어 있지 않습니다!";
    }
  }

  function flashButton(buttonId, success) {
    const btnEl = gridEl.querySelector(`.deck-btn[data-id="${buttonId}"]`);
    if (btnEl) {
      if (flashTimers[buttonId]) {
        clearTimeout(flashTimers[buttonId]);
      }
      btnEl.classList.remove("btn-pressed", "flash-success", "flash-fail");
      void btnEl.offsetWidth; // force reflow
      const cls = success ? "flash-success" : "flash-fail";
      btnEl.classList.add(cls);

      // 하이라이트 자동 꺼짐 복원 (350ms)
      flashTimers[buttonId] = setTimeout(() => {
        btnEl.classList.remove(cls, "btn-pressed");
        delete flashTimers[buttonId];
      }, 350);
    }
  }

  function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // --- Zoom & Fullscreen Controls ---
  const btnZoomIn = document.getElementById("btnZoomIn");
  const btnZoomOut = document.getElementById("btnZoomOut");
  const btnZoomReset = document.getElementById("btnZoomReset");
  const zoomLabel = document.getElementById("zoomLabel");
  const btnFullscreen = document.getElementById("btnFullscreen");

  let currentScale = parseFloat(localStorage.getItem("taildeck_zoom")) || 1.0;

  function applyZoom(scale) {
    currentScale = Math.min(1.5, Math.max(0.6, scale));
    document.documentElement.style.setProperty("--deck-scale", currentScale);
    if (zoomLabel) {
      zoomLabel.innerText = Math.round(currentScale * 100) + "%";
    }
    localStorage.setItem("taildeck_zoom", currentScale);
  }

  function toggleFullscreen() {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  }

  if (btnZoomIn) {
    btnZoomIn.addEventListener("click", () => applyZoom(currentScale + 0.1));
  }
  if (btnZoomOut) {
    btnZoomOut.addEventListener("click", () => applyZoom(currentScale - 0.1));
  }
  if (btnZoomReset) {
    btnZoomReset.addEventListener("click", () => applyZoom(1.0));
  }
  if (btnFullscreen) {
    btnFullscreen.addEventListener("click", toggleFullscreen);
  }

  // --- Retro Menu Bar Dropdown Interactions ---
  const menuWrappers = document.querySelectorAll(".menu-item-wrapper");

  function closeAllDropdowns() {
    menuWrappers.forEach(w => {
      const dd = w.querySelector(".win2k-dropdown");
      const item = w.querySelector(".menu-item");
      if (dd) dd.classList.remove("open");
      if (item) item.classList.remove("active");
    });
  }

  menuWrappers.forEach(wrapper => {
    const item = wrapper.querySelector(".menu-item");
    const dropdown = wrapper.querySelector(".win2k-dropdown");
    if (!item || !dropdown) return;

    item.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = dropdown.classList.contains("open");
      closeAllDropdowns();
      if (!isOpen) {
        dropdown.classList.add("open");
        item.classList.add("active");
      }
    });
  });

  document.addEventListener("click", () => {
    closeAllDropdowns();
  });

  // View Dropdown actions
  const menuZoomIn = document.getElementById("menuZoomIn");
  const menuZoomOut = document.getElementById("menuZoomOut");
  const menuZoomReset = document.getElementById("menuZoomReset");
  const menuFullscreen = document.getElementById("menuFullscreen");

  if (menuZoomIn) {
    menuZoomIn.addEventListener("click", (e) => {
      e.stopPropagation();
      applyZoom(currentScale + 0.1);
      closeAllDropdowns();
    });
  }
  if (menuZoomOut) {
    menuZoomOut.addEventListener("click", (e) => {
      e.stopPropagation();
      applyZoom(currentScale - 0.1);
      closeAllDropdowns();
    });
  }
  if (menuZoomReset) {
    menuZoomReset.addEventListener("click", (e) => {
      e.stopPropagation();
      applyZoom(1.0);
      closeAllDropdowns();
    });
  }
  if (menuFullscreen) {
    menuFullscreen.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleFullscreen();
      closeAllDropdowns();
    });
  }

  const menuReload = document.getElementById("menuActionReload");
  if (menuReload) {
    menuReload.addEventListener("click", () => window.location.reload());
  }

  const menuClose = document.getElementById("menuActionClose");
  if (menuClose) {
    menuClose.addEventListener("click", () => {
      feedbackMsgEl.innerText = "브라우저 탭을 닫아주세요.";
      closeAllDropdowns();
    });
  }

  const menuAbout = document.getElementById("menuActionAbout");
  if (menuAbout) {
    menuAbout.addEventListener("click", () => {
      alert("TailDeck 2000 Professional\n버전 1.0 (Build 2026)\n\nTailscale 원격 스트림덱");
      closeAllDropdowns();
    });
  }

  // 초기 줌 적용
  applyZoom(currentScale);

  // Start connection
  connect();
})();
