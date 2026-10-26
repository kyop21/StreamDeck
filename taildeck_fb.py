#!/usr/bin/env python3
"""
TailDeck 2000 Professional - Native Retro Framebuffer Client
Zero-Latency Partial Blit Architecture with Blinking Cursor Clock:
- Pre-rendered button surfaces (Normal & Pressed) cached in RAM
- Direct mmap slice memcpy (0.1ms frame latency)
- Snappy 75ms tactile click duration
- 0% CPU real-time clock with retro blinking cursor (_ /  )
"""

import os
import sys
import time
import random
import json
import threading
import glob
import mmap
import socket
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import evdev
from evdev import ecodes
import websocket

# sock_opt.timeout defaults to None, so a half-open peer can block connect() for
# ~130s on Linux and recv() forever on a partial frame - run_forever() then never
# returns and ws_loop never reaches its retry. Bound every socket operation.
websocket.setdefaulttimeout(5)

# Candidate server URLs in priority order:
# 1. Custom env var TAILDECK_WS_URL (if provided)
# 2. Tailscale PC IP: 100.86.114.58
DEFAULT_SERVER_URLS = [
    os.environ.get("TAILDECK_WS_URL", "ws://100.86.114.58:2000/ws")
]
SERVER_WS_URLS = list(dict.fromkeys(DEFAULT_SERVER_URLS))
SERVER_WS_URL = SERVER_WS_URLS[0]
FB_DEVICE = "/dev/fb0"
ICONS_DIR = "/root/icons"
FONT_PATH = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"

# Windows 2000 Color Palette
C_DESKTOP = (0, 128, 128)        # #008080 Classic Teal
C_FACE = (212, 208, 200)          # #d4d0c8 Win2K Gray
C_PRESSED = (223, 219, 210)       # #dfdbd2 Pressed Face
C_HIGHLIGHT = (255, 255, 255)     # #ffffff
C_LIGHT = (223, 223, 223)         # #dfdfdf
C_SHADOW = (128, 128, 128)        # #808080
C_DARK_SHADOW = (64, 64, 64)      # #404040
C_TITLE_START = (10, 36, 106)     # #0a246a Active Title Dark Blue
C_TITLE_END = (166, 202, 240)     # #a6caf0 Active Title Light Blue
C_TEXT = (0, 0, 0)                # #000000 Black text

class Win2kThemeClient:
    def __init__(self):
        self.width = 800
        self.height = 480
        self.bpp = 16
        self.fb_file = None
        self.fb_mmap = None
        self.fb_size = 0
        
        self.grid_rows = 3
        self.grid_cols = 4
        self.buttons = []
        self.button_rects = {}  # {b_id: (x1, y1, x2, y2)}
        self.btn_normal_bytes = {}   # {b_id: bytes}
        self.btn_pressed_bytes = {}  # {b_id: bytes}
        self.button_blit_plans = {}  # {b_id: [(fb_pos, src_pos, line_bytes), ...]}
        self.active_pressed_button = None
        self.pressed_button_time = 0.0
        
        self.status_msg = "온라인"
        self.connected = False
        self.cursor_blink = True
        self.current_profile = "Default"
        self.cached_profiles = ["Default"]
        self.last_sync_seq = 0
        self.reconnect_attempt = 0
        self.server_urls = list(SERVER_WS_URLS)
        self.server_url_idx = 0
        self.reconnect_event = threading.Event()
        
        self.icon_cache = {}
        self.base_raw_bytes = None
        
        self.ws = None
        self.lock = threading.RLock()
        
        # Win2K Menu & Hardware State
        self.active_menu = None  # "file", "profile", "view", "play", "tools", "help", "about_dialog", or None
        self.menu_bar_rects = {}
        self.dropdown_item_rects = []
        self.dialog_ok_rect = (0, 0, 0, 0)
        self.current_brightness = 255
        self.screen_sleeping = False
        
        # High-Speed RAM Partial Blit Cache
        self.clean_base_bytes = None
        self.menu_cache = {}
        self.last_popup_bounds = None
        self.last_header_bounds = None
        self.last_touch_time = 0.0
        self.waiting_sync_since = 0.0
        self.menu_items = [
            ("file", "파일(F)", "F"),
            ("profile", "프로필(P)", "P"),
            ("view", "보기(V)", "V"),
            ("play", "재생(M)", "M"),
            ("tools", "도구(T)", "T"),
            ("help", "도움말(H)", "H")
        ]
        
        self.init_fonts()
        self.init_framebuffer()
        self.preload_icons()
        self.init_touch()
        
    def init_fonts(self):
        try:
            if os.path.exists(FONT_PATH):
                self.font_title = ImageFont.truetype(FONT_PATH, 12)
                self.font_menu = ImageFont.truetype(FONT_PATH, 12)
                self.font_btn = ImageFont.truetype(FONT_PATH, 13)
                self.font_status = ImageFont.truetype(FONT_PATH, 10)
            else:
                self.font_title = ImageFont.load_default()
                self.font_menu = self.font_title
                self.font_btn = self.font_title
                self.font_status = self.font_title
        except Exception:
            self.font_title = ImageFont.load_default()
            self.font_menu = self.font_title
            self.font_btn = self.font_title
            self.font_status = self.font_title

    def init_framebuffer(self):
        try:
            with open("/sys/class/graphics/fb0/bits_per_pixel", "r") as f:
                self.bpp = int(f.read().strip())
        except Exception:
            self.bpp = 16
            
        try:
            with open("/sys/class/graphics/fb0/virtual_size", "r") as f:
                parts = f.read().strip().split(",")
                self.width = int(parts[0])
                self.height = int(parts[1])
        except Exception:
            self.width = 800
            self.height = 480
            
        self.stride = self.width * (self.bpp // 8)
        self.fb_size = self.height * self.stride
        print(f"Win2K Framebuffer: {self.width}x{self.height} @ {self.bpp}bpp ({self.fb_size} bytes)")
        
        try:
            self.fb_file = open(FB_DEVICE, "r+b")
            self.fb_mmap = mmap.mmap(self.fb_file.fileno(), self.fb_size)
        except Exception as e:
            print(f"FB Open Error: {e}")
            sys.exit(1)

    def preload_icons(self):
        if not os.path.isdir(ICONS_DIR):
            return
        for f in os.listdir(ICONS_DIR):
            if f.endswith(".png"):
                full_path = os.path.join(ICONS_DIR, f)
                try:
                    img = Image.open(full_path).convert("RGBA")
                    self.icon_cache[f] = img
                    self.icon_cache[os.path.splitext(f)[0]] = img
                except Exception:
                    pass
        print(f"Preloaded {len(self.icon_cache)} icons")

    def init_touch(self):
        self.touch_dev = None
        for ev_path in sorted(glob.glob("/dev/input/event*")):
            try:
                dev = evdev.InputDevice(ev_path)
                name_lower = dev.name.lower()
                if "ts" in name_lower or "touch" in name_lower or "raspberrypi-ts" in name_lower:
                    self.touch_dev = dev
                    print(f"Touchscreen bound: {dev.name} ({ev_path})")
                    break
            except Exception:
                continue

    def img_to_rgb565(self, img):
        arr = np.array(img, dtype=np.uint16)
        r = (arr[:, :, 0] >> 3) << 11
        g = (arr[:, :, 1] >> 2) << 5
        b = arr[:, :, 2] >> 3
        return (r | g | b).astype(np.uint16).tobytes()

    def draw_3d_rect(self, draw, x1, y1, x2, y2, sunken=False):
        top_left_outer = C_DARK_SHADOW if sunken else C_HIGHLIGHT
        top_left_inner = C_TEXT if sunken else C_LIGHT
        bot_right_outer = C_HIGHLIGHT if sunken else C_DARK_SHADOW
        bot_right_inner = C_LIGHT if sunken else C_SHADOW
        
        draw.line([(x1, y1), (x2, y1)], fill=top_left_outer)
        draw.line([(x1, y1), (x1, y2)], fill=top_left_outer)
        draw.line([(x2, y1), (x2, y2)], fill=bot_right_outer)
        draw.line([(x1, y2), (x2, y2)], fill=bot_right_outer)
        
        draw.line([(x1 + 1, y1 + 1), (x2 - 1, y1 + 1)], fill=top_left_inner)
        draw.line([(x1 + 1, y1 + 1), (x1 + 1, y2 - 1)], fill=top_left_inner)
        draw.line([(x2 - 1, y1 + 1), (x2 - 1, y2 - 1)], fill=bot_right_inner)
        draw.line([(x1 + 1, y2 - 1), (x2 - 1, y2 - 1)], fill=bot_right_inner)

    def draw_text_with_underline(self, draw, x, y, text, underline_char, font, fill=C_TEXT):
        draw.text((x, y), text, fill=fill, font=font)
        if not underline_char:
            return
        pos = text.find(underline_char)
        if pos != -1:
            pre_bbox = draw.textbbox((0, 0), text[:pos], font=font)
            pre_w = pre_bbox[2] - pre_bbox[0]
            char_bbox = draw.textbbox((0, 0), underline_char, font=font)
            char_w = char_bbox[2] - char_bbox[0]
            t_bbox = draw.textbbox((0, 0), text, font=font)
            th = t_bbox[3] - t_bbox[1]
            line_y = y + th + 1
            draw.line([(x + pre_w, line_y), (x + pre_w + char_w - 1, line_y)], fill=fill)

    def set_backlight(self, val):
        try:
            with open("/sys/class/backlight/rpi_backlight/brightness", "w") as f:
                f.write(str(val))
            self.current_brightness = val
            if val == 0:
                self.screen_sleeping = True
                self.update_status_msg("화면 절전 모드 (터치 시 복귀)")
            else:
                self.screen_sleeping = False
                self.update_status_msg(f"화면 밝기: {int(val / 255 * 100)}%")
        except Exception as e:
            print(f"Backlight error: {e}")

    def get_cpu_temp(self):
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                return f"{int(f.read().strip()) / 1000.0:.1f}°C"
        except Exception:
            return "N/A"

    def get_current_server_url(self) -> str:
        return self.server_urls[self.server_url_idx % len(self.server_urls)]

    def rotate_server_url_on_fail(self):
        """Rotate to next candidate server URL on consecutive failures."""
        if len(self.server_urls) > 1:
            self.server_url_idx = (self.server_url_idx + 1) % len(self.server_urls)

    def do_ping_test(self):
        def _test():
            self.update_status_msg("지연시간 측정 중...")
            t0 = time.time()
            try:
                cur_url = self.get_current_server_url()
                host_part = cur_url.replace("ws://", "").replace("http://", "").split("/")[0]
                host, port = host_part.split(":") if ":" in host_part else (host_part, "2000")
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2.0)
                s.connect((host, int(port)))
                s.close()
                ms = int((time.time() - t0) * 1000)
                self.update_status_msg(f"PC 지연시간 ({host}): {ms}ms")
            except Exception:
                self.update_status_msg("핑 측정 실패")
        threading.Thread(target=_test, daemon=True).start()

    def send_pc_direct_action(self, act_type, payload):
        ok = self._safe_ws_send({
            "type": "trigger_direct",
            "action_type": act_type,
            "payload": payload
        })
        if ok:
            self.update_status_msg(f"PC 명령: {payload}")
        else:
            self.update_status_msg("명령 전송 실패")

    def render_single_button_image(self, btn_w, btn_h, btn_data, is_pressed=False):
        img = Image.new("RGB", (btn_w, btn_h), color=C_PRESSED if is_pressed else C_FACE)
        draw = ImageDraw.Draw(img)
        
        self.draw_3d_rect(draw, 0, 0, btn_w - 1, btn_h - 1, sunken=is_pressed)
        
        if not btn_data:
            return img
            
        color_hex = btn_data.get("color") or btn_data.get("bg_color") or "#000080"
        try:
            accent_c = tuple(int(color_hex.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
        except Exception:
            accent_c = (0, 0, 128)
            
        if is_pressed:
            draw.rectangle([3, 3, btn_w - 4, btn_h - 4], outline=accent_c, width=2)
            shift = 2
        else:
            draw.rectangle([3, 3, btn_w - 4, 6], fill=accent_c)
            shift = 0
            
        title = btn_data.get("title") or btn_data.get("name") or f"Btn {btn_data.get('id', '')}"
        icon_name = btn_data.get("icon")
        icon_img = None
        if icon_name:
            clean = os.path.basename(icon_name)
            icon_img = self.icon_cache.get(clean) or self.icon_cache.get(os.path.splitext(clean)[0])
            
        if icon_img:
            ic_size = min(36, btn_h // 2 - 2)
            if icon_img.size != (ic_size, ic_size):
                ic_draw = icon_img.resize((ic_size, ic_size), Image.NEAREST)
            else:
                ic_draw = icon_img
                
            ic_x = (btn_w - ic_size) // 2 + shift
            ic_y = 9 + shift
            img.paste(ic_draw, (ic_x, ic_y), ic_draw)
            
            if title:
                bbox = draw.textbbox((0, 0), title, font=self.font_btn)
                tw = bbox[2] - bbox[0]
                tx = (btn_w - tw) // 2 + shift
                ty = 9 + ic_size + 3 + shift
                draw.text((tx, ty), title, fill=C_TEXT, font=self.font_btn)
        else:
            if title:
                bbox = draw.textbbox((0, 0), title, font=self.font_btn)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                tx = (btn_w - tw) // 2 + shift
                ty = (btn_h - th) // 2 + shift
                draw.text((tx, ty), title, fill=C_TEXT, font=self.font_btn)
                
        action_type = btn_data.get("action_type")
        if action_type:
            badge_text = str(action_type).upper()
            b_box = draw.textbbox((0, 0), badge_text, font=self.font_status)
            bw = b_box[2] - b_box[0]
            bh = b_box[3] - b_box[1]
            bx = (btn_w - bw) // 2 + shift
            by = btn_h - bh - 6 + shift
            draw.rectangle([bx - 3, by - 1, bx + bw + 2, by + bh + 1], fill=(224, 222, 216))
            draw.text((bx, by), badge_text, fill=(64, 64, 64), font=self.font_status)
            
        return img

    def build_and_cache_surfaces(self):
        img = Image.new("RGB", (self.width, self.height), color=C_DESKTOP)
        draw = ImageDraw.Draw(img)
        
        # 1. Window Frame
        wx1, wy1, wx2, wy2 = 3, 3, self.width - 4, self.height - 4
        draw.rectangle([wx1, wy1, wx2, wy2], fill=C_FACE)
        self.draw_3d_rect(draw, wx1, wy1, wx2, wy2, sunken=False)
        
        # 2. Title Bar Gradient (NumPy Vectorized: 1.5ms vs 162.8ms loop)
        tx1, ty1, tx2, ty2 = wx1 + 3, wy1 + 3, wx2 - 3, wy1 + 24
        tw = (tx2 - tx1 + 1)
        th = (ty2 - ty1 + 1)
        r = np.linspace(C_TITLE_START[0], C_TITLE_END[0], tw, dtype=np.uint8)
        g = np.linspace(C_TITLE_START[1], C_TITLE_END[1], tw, dtype=np.uint8)
        b = np.linspace(C_TITLE_START[2], C_TITLE_END[2], tw, dtype=np.uint8)
        grad_row = np.stack([r, g, b], axis=-1)
        grad_2d = np.tile(grad_row, (th, 1, 1))
        grad_img = Image.fromarray(grad_2d, mode="RGB")
        img.paste(grad_img, (tx1, ty1))
            
        # Media Player Icon (16x16)
        icon_img = self.icon_cache.get("media_player.png") or self.icon_cache.get("media_player")
        if icon_img:
            ic_title = icon_img.resize((16, 16), Image.NEAREST)
            img.paste(ic_title, (tx1 + 5, ty1 + 3), ic_title)
            title_text_x = tx1 + 25
        else:
            title_text_x = tx1 + 6
            
        draw.text((title_text_x, ty1 + 4), f"Windows Media Player - [{self.current_profile}]", fill=C_HIGHLIGHT, font=self.font_title)
        
        ctrl_w, ctrl_h = 16, 14
        bx = tx2 - 3 - ctrl_w
        by = ty1 + 4
        for label in ["X", "ㅁ", "_"]:
            draw.rectangle([bx, by, bx + ctrl_w, by + ctrl_h], fill=C_FACE)
            self.draw_3d_rect(draw, bx, by, bx + ctrl_w, by + ctrl_h, sunken=False)
            t_bb = draw.textbbox((0, 0), label, font=self.font_status)
            draw.text((bx + (ctrl_w - (t_bb[2] - t_bb[0])) // 2, by + 1), label, fill=C_TEXT, font=self.font_status)
            bx -= (ctrl_w + 2)
            
        # 3. Menu Bar (파일(F) 프로필(P) 보기(V) 재생(M) 도구(T) 도움말(H))
        my1, my2 = ty2 + 2, ty2 + 23
        draw.rectangle([wx1 + 3, my1, wx2 - 3, my2], fill=C_FACE)
        
        self.menu_bar_rects.clear()
        cur_mx = wx1 + 8
        for key, m_text, u_char in self.menu_items:
            bbox = draw.textbbox((0, 0), m_text, font=self.font_menu)
            mw = bbox[2] - bbox[0]
            
            bx1, by1, bx2, by2 = cur_mx - 3, my1 + 1, cur_mx + mw + 3, my2 - 1
            self.menu_bar_rects[key] = {
                "touch": (cur_mx - 5, my1, cur_mx + mw + 5, my2 + 2),
                "header": (bx1, by1, bx2, by2),
                "popup_pos": (bx1, my2),
                "text": m_text,
                "uchar": u_char,
                "text_pos": (cur_mx, my1 + 3)
            }
            self.draw_text_with_underline(draw, cur_mx, my1 + 3, m_text, u_char, self.font_menu, fill=C_TEXT)
            cur_mx += mw + 16
        
        # Connection Status LED at right
        led_color = (0, 220, 0) if self.connected else (220, 0, 0)
        draw.ellipse([wx2 - 18, my1 + 5, wx2 - 10, my1 + 13], fill=led_color)
        draw.ellipse([wx2 - 18, my1 + 5, wx2 - 10, my1 + 13], outline=C_SHADOW)
        draw.line([(wx1 + 3, my2), (wx2 - 3, my2)], fill=C_SHADOW)
        
        # 4. Status Bar
        sy1, sy2 = wy2 - 22, wy2 - 3
        draw.rectangle([wx1 + 3, sy1, wx2 - 3, sy2], fill=C_FACE)
        self.draw_3d_rect(draw, wx1 + 3, sy1, wx2 - 3, sy2, sunken=True)
        draw.text((wx1 + 8, sy1 + 4), f"상태: {self.status_msg}", fill=C_TEXT, font=self.font_status)
        cur_t = time.strftime("%H:%M:%S")
        draw.text((wx2 - 62, sy1 + 4), cur_t, fill=C_TEXT, font=self.font_status)
        
        # 5. Buttons Grid
        gx1 = wx1 + 8
        gy1 = my2 + 8
        gx2 = wx2 - 8
        gy2 = sy1 - 8
        self.draw_3d_rect(draw, gx1 - 2, gy1 - 2, gx2 + 2, gy2 + 2, sunken=True)
        
        rows = max(1, self.grid_rows)
        cols = max(1, self.grid_cols)
        gap = 8
        avail_w = (gx2 - gx1) - (gap * (cols - 1))
        avail_h = (gy2 - gy1) - (gap * (rows - 1))
        btn_w = avail_w // cols
        btn_h = avail_h // rows
        
        self.button_rects.clear()
        self.btn_normal_bytes.clear()
        self.btn_pressed_bytes.clear()
        self.button_blit_plans.clear()
        total_slots = rows * cols
        
        stride = self.stride
        line_bytes = btn_w * 2
        for idx in range(total_slots):
            r = idx // cols
            c = idx % cols
            bx1 = gx1 + c * (btn_w + gap)
            by1 = gy1 + r * (btn_h + gap)
            bx2 = bx1 + btn_w
            by2 = by1 + btn_h
            
            btn_data = self.buttons[idx] if idx < len(self.buttons) else None
            btn_id = btn_data.get("id") if btn_data else None
            
            normal_img = self.render_single_button_image(btn_w, btn_h, btn_data, is_pressed=False)
            pressed_img = self.render_single_button_image(btn_w, btn_h, btn_data, is_pressed=True)
            
            img.paste(normal_img, (bx1, by1))
            
            if btn_id is not None:
                self.button_rects[btn_id] = (bx1, by1, bx2, by2)
                self.btn_normal_bytes[btn_id] = self.img_to_rgb565(normal_img)
                self.btn_pressed_bytes[btn_id] = self.img_to_rgb565(pressed_img)
                self.button_blit_plans[btn_id] = [
                    ((by1 + row) * stride + (bx1 * 2), row * line_bytes, line_bytes)
                    for row in range(btn_h)
                ]
                
        self.base_raw_bytes = self.img_to_rgb565(img)
        self.clean_base_bytes = bytearray(self.base_raw_bytes)

    def blit_rect(self, x1, y1, w, h, raw_bytes, update_base=False):
        if not self.fb_mmap:
            return
        stride = self.stride
        line_bytes = w * 2
        mv = memoryview(raw_bytes)
        with self.lock:
            for row in range(h):
                fb_pos = (y1 + row) * stride + (x1 * 2)
                src_pos = row * line_bytes
                chunk = mv[src_pos : src_pos + line_bytes]
                self.fb_mmap[fb_pos : fb_pos + line_bytes] = chunk
                if update_base and self.clean_base_bytes:
                    self.clean_base_bytes[fb_pos : fb_pos + line_bytes] = chunk

    def restore_rect_from_base(self, x1, y1, x2, y2):
        if not self.fb_mmap or not self.clean_base_bytes:
            return
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(self.width, x2)
        y2 = min(self.height, y2)
        w = x2 - x1
        h = y2 - y1
        if w <= 0 or h <= 0:
            return
        stride = self.stride
        line_bytes = w * 2
        base_mv = memoryview(self.clean_base_bytes)
        with self.lock:
            for row in range(h):
                pos = (y1 + row) * stride + (x1 * 2)
                self.fb_mmap[pos : pos + line_bytes] = base_mv[pos : pos + line_bytes]

    def update_status_msg(self, msg):
        self.status_msg = msg
        wx1 = 3
        wy2 = self.height - 4
        sy1, sy2 = wy2 - 22, wy2 - 3
        txt_x = wx1 + 7
        txt_y = sy1 + 3
        txt_w = 380
        txt_h = sy2 - sy1 - 5
        if txt_h <= 0:
            return

        img = Image.new("RGB", (txt_w, txt_h), color=C_FACE)
        draw = ImageDraw.Draw(img)
        draw.text((2, 0), f"상태: {msg}", fill=C_TEXT, font=self.font_status)

        raw = self.img_to_rgb565(img)
        self.blit_rect(txt_x, txt_y, txt_w, txt_h, raw, update_base=True)

    def get_menu_items(self, menu_key):
        if menu_key == "file":
            return [
                ("새로 고침 (동기화)(&S)", "S", "sync", None),
                ("서버 재연결(&R)", "R", "reconnect", None),
                ("---", "", "", None),
                ("파이 재부팅(&B)", "B", "pi_reboot", None),
                ("파이 시스템 종료(&U)", "U", "pi_poweroff", None),
                ("---", "", "", None),
                ("닫기(&C)", "C", "close", None),
            ]
        elif menu_key == "profile":
            p_items = []
            for p_name in self.cached_profiles:
                prefix = "* " if p_name == self.current_profile else "  "
                p_items.append((f"{prefix}{p_name}", "", "switch_profile", p_name))
            p_items.append(("---", "", "", None))
            p_items.append(("새로 고침(&R)", "R", "request_profiles", None))
            p_items.append(("닫기(&C)", "C", "close", None))
            return p_items
        elif menu_key == "view":
            return [
                ("화면 밝기 100% (&H)", "H", "brightness", 255),
                ("화면 밝기 50% (&M)", "M", "brightness", 128),
                ("화면 밝기 20% (&L)", "L", "brightness", 50),
                ("화면 끄기 (절전)(&O)", "O", "brightness", 0),
                ("---", "", "", None),
                ("닫기(&C)", "C", "close", None),
            ]
        elif menu_key == "play":
            return [
                ("재생 / 일시정지(&P)", "P", "pc_action", ("media", "play_pause")),
                ("음소거 (Mute)(&M)", "M", "pc_action", ("media", "volume_mute")),
                ("볼륨 올리기(&U)", "U", "pc_action", ("media", "volume_up")),
                ("볼륨 내리기(&D)", "D", "pc_action", ("media", "volume_down")),
                ("---", "", "", None),
                ("닫기(&C)", "C", "close", None),
            ]
        elif menu_key == "tools":
            return [
                ("바탕화면 보기(&D)", "D", "pc_action", ("hotkey", "win+d")),
                ("작업 관리자(&T)", "T", "pc_action", ("hotkey", "ctrl+shift+esc")),
                ("PC 화면 잠금(&L)", "L", "pc_action", ("system", "lock")),
                ("---", "", "", None),
                ("Tailscale 지연시간 테스트(&P)", "P", "ping_test", None),
                ("---", "", "", None),
                ("닫기(&C)", "C", "close", None),
            ]
        elif menu_key == "help":
            return [
                ("TailDeck 2000 정보(&A)...", "A", "about_dialog", None),
                ("---", "", "", None),
                ("닫기(&C)", "C", "close", None),
            ]
        return []

    def get_menu_cache(self, key):
        if key in self.menu_cache:
            return self.menu_cache[key]

        items = self.get_menu_items(key)
        menu_w = 210
        item_h = 36
        total_menu_h = 8
        for it in items:
            total_menu_h += 6 if it[0] == "---" else item_h

        img = Image.new("RGB", (menu_w, total_menu_h), color=C_FACE)
        draw = ImageDraw.Draw(img)
        self.draw_3d_rect(draw, 0, 0, menu_w - 1, total_menu_h - 1, sunken=False)

        item_rects = []
        cur_iy = 4
        m_info = self.menu_bar_rects[key]
        dx1, dy1 = m_info["popup_pos"][0], m_info["popup_pos"][1]
        if dx1 + menu_w > self.width - 6:
            dx1 = self.width - 6 - menu_w

        for label, u_char, act_type, act_val in items:
            if label == "---":
                draw.line([(4, cur_iy + 2), (menu_w - 4, cur_iy + 2)], fill=C_SHADOW)
                draw.line([(4, cur_iy + 3), (menu_w - 4, cur_iy + 3)], fill=C_HIGHLIGHT)
                cur_iy += 6
            else:
                iy1 = cur_iy
                iy2 = iy1 + item_h
                ix1 = 4
                ix2 = menu_w - 4
                screen_rect = (dx1 + ix1, dy1 + iy1, dx1 + ix2, dy1 + iy2)
                item_rects.append((screen_rect, act_type, act_val))
                self.draw_text_with_underline(draw, ix1 + 10, iy1 + 10, label, u_char, self.font_menu, fill=C_TEXT)
                cur_iy += item_h

        raw_bytes = self.img_to_rgb565(img)
        res = (raw_bytes, dx1, dy1, menu_w, total_menu_h, item_rects)
        self.menu_cache[key] = res
        return res

    def open_menu(self, key):
        with self.lock:
            if self.active_menu:
                self.close_menu()

            self.active_menu = key
            # Highlight menu bar header (sunken)
            if key in self.menu_bar_rects:
                m_info = self.menu_bar_rects[key]
                bx1, by1, bx2, by2 = m_info["header"]
                hw = bx2 - bx1
                hh = by2 - by1
                h_img = Image.new("RGB", (hw, hh), color=C_FACE)
                h_draw = ImageDraw.Draw(h_img)
                self.draw_3d_rect(h_draw, 0, 0, hw - 1, hh - 1, sunken=True)
                self.draw_text_with_underline(h_draw, m_info["text_pos"][0] - bx1, m_info["text_pos"][1] - by1, m_info["text"], m_info["uchar"], self.font_menu, fill=C_TEXT)
                h_raw = self.img_to_rgb565(h_img)
                self.blit_rect(bx1, by1, hw, hh, h_raw)
                self.last_header_bounds = (bx1, by1, bx2, by2)

            # Blit Dropdown Surface (Instant ~3.9ms)
            raw_bytes, dx1, dy1, mw, mh, item_rects = self.get_menu_cache(key)
            self.dropdown_item_rects = item_rects
            self.last_popup_bounds = (dx1, dy1, dx1 + mw, dy1 + mh)
            self.blit_rect(dx1, dy1, mw, mh, raw_bytes)

    def close_menu(self):
        with self.lock:
            if not self.active_menu:
                return
            if self.last_popup_bounds:
                self.restore_rect_from_base(*self.last_popup_bounds)
                self.last_popup_bounds = None
            if self.last_header_bounds:
                self.restore_rect_from_base(*self.last_header_bounds)
                self.last_header_bounds = None
            self.active_menu = None
            self.dropdown_item_rects.clear()
            self.dialog_ok_rect = (0, 0, 0, 0)

    def open_about_dialog(self):
        if self.active_menu:
            self.close_menu()
        self.active_menu = "about_dialog"
        dw, dh = 360, 220
        dx1 = (self.width - dw) // 2
        dy1 = (self.height - dh) // 2
        dx2 = dx1 + dw
        dy2 = dy1 + dh

        img = Image.new("RGB", (dw, dh), color=C_FACE)
        draw = ImageDraw.Draw(img)
        self.draw_3d_rect(draw, 0, 0, dw - 1, dh - 1, sunken=False)

        draw.rectangle([3, 3, dw - 4, 22], fill=C_TITLE_START)
        draw.text((9, 3), "TailDeck 2000 정보", fill=C_HIGHLIGHT, font=self.font_title)

        ic = self.icon_cache.get("media_player.png") or self.icon_cache.get("media_player")
        if ic:
            ic_dlg = ic.resize((32, 32), Image.NEAREST)
            img.paste(ic_dlg, (16, 36), ic_dlg)

        draw.text((58, 34), "TailDeck 2000 Professional", fill=C_TEXT, font=self.font_btn)
        draw.text((58, 54), "버전 2.0 (Win2K Native Framebuffer)", fill=(80, 80, 80), font=self.font_status)

        draw.line([(16, 78), (dw - 16, 78)], fill=C_SHADOW)
        draw.line([(16, 79), (dw - 16, 79)], fill=C_HIGHLIGHT)

        temp_str = self.get_cpu_temp()
        draw.text((20, 88), "호스트: DietPi (Raspberry Pi 1 armv6l)", fill=C_TEXT, font=self.font_menu)
        draw.text((20, 108), "Tailscale IP: 100.72.170.44", fill=C_TEXT, font=self.font_menu)
        draw.text((20, 128), f"파이 CPU 온도: {temp_str} | 화면 밝기: {int(self.current_brightness / 255 * 100)}%", fill=C_TEXT, font=self.font_menu)
        draw.text((20, 148), f"서버 연결 상태: {'온라인' if self.connected else '오프라인'}", fill=(0, 128, 0) if self.connected else (180, 0, 0), font=self.font_menu)

        bw, bh = 75, 26
        bx1 = dw - 16 - bw
        by1 = dh - 14 - bh
        bx2 = bx1 + bw
        by2 = by1 + bh
        self.dialog_ok_rect = (dx1 + bx1, dy1 + by1, dx1 + bx2, dy1 + by2)

        draw.rectangle([bx1, by1, bx2, by2], fill=C_FACE)
        self.draw_3d_rect(draw, bx1, by1, bx2, by2, sunken=False)
        draw.text((bx1 + 24, by1 + 6), "확인", fill=C_TEXT, font=self.font_menu)

        raw = self.img_to_rgb565(img)
        self.last_popup_bounds = (dx1, dy1, dx2, dy2)
        self.blit_rect(dx1, dy1, dw, dh, raw)

    def blit_button_rect(self, b_id, raw_btn_bytes):
        if not self.fb_mmap:
            return
        plan = self.button_blit_plans.get(b_id)
        if not plan:
            if b_id not in self.button_rects:
                return
            x1, y1, x2, y2 = self.button_rects[b_id]
            btn_w = x2 - x1
            btn_h = y2 - y1
            line_bytes = btn_w * 2
            stride = self.stride
            plan = [((y1 + row) * stride + (x1 * 2), row * line_bytes, line_bytes) for row in range(btn_h)]
            self.button_blit_plans[b_id] = plan

        mv = memoryview(raw_btn_bytes)
        fb = self.fb_mmap
        for fb_pos, src_pos, lb in plan:
            fb[fb_pos : fb_pos + lb] = mv[src_pos : src_pos + lb]

    def flash_button(self, b_id, success: bool):
        """0.05ms lightweight visual flash on action completion without PIL/NumPy overhead"""
        if b_id not in self.button_rects or not self.fb_mmap:
            return
        x1, y1, x2, y2 = self.button_rects[b_id]
        bar_x1 = x1 + 3
        bar_y1 = y1 + 3
        bar_w = (x2 - x1) - 7
        bar_h = 4
        if bar_w <= 0:
            return

        color_565 = 0x07E0 if success else 0xF800  # Bright Green or Red
        c_bytes = (color_565).to_bytes(2, byteorder="little")
        flash_raw = (c_bytes * bar_w) * bar_h

        with self.lock:
            self.blit_rect(bar_x1, bar_y1, bar_w, bar_h, flash_raw)

        def _revert():
            time.sleep(0.12)
            with self.lock:
                if self.active_pressed_button != b_id and b_id in self.btn_normal_bytes:
                    self.blit_button_rect(b_id, self.btn_normal_bytes[b_id])

        threading.Thread(target=_revert, daemon=True).start()

    def update_clock(self):
        """0% CPU ultra-lightweight real-time clock partial blit"""
        if not self.fb_mmap:
            return
        cw, ch = 65, 16
        cx1 = self.width - 4 - 3 - cw - 2
        cy1 = self.height - 4 - 22 + 4
        
        cur_t = time.strftime("%H:%M:%S")
        img = Image.new("RGB", (cw, ch), color=C_FACE)
        draw = ImageDraw.Draw(img)
        draw.text((2, 0), cur_t, fill=C_TEXT, font=self.font_status)
        raw_clock = self.img_to_rgb565(img)
        
        stride = self.stride
        line_bytes = cw * 2
        with self.lock:
            for row in range(ch):
                fb_pos = (cy1 + row) * stride + (cx1 * 2)
                src_pos = row * line_bytes
                self.fb_mmap[fb_pos : fb_pos + line_bytes] = raw_clock[src_pos : src_pos + line_bytes]

    def render_full(self):
        with self.lock:
            if self.active_menu:
                self.close_menu()
            self.build_and_cache_surfaces()
            try:
                self.fb_mmap.seek(0)
                self.fb_mmap.write(self.base_raw_bytes)
            except Exception as e:
                print(f"FB write error: {e}")

    def on_touch_down(self, x, y):
        now = time.time()
        if now - self.last_touch_time < 0.05:
            return
        self.last_touch_time = now

        # 0. Wake up from sleep if screen was off
        if self.screen_sleeping:
            self.set_backlight(255)
            self.render_full()
            return

        # 1. Handle clicks when About Dialog is active
        if self.active_menu == "about_dialog":
            self.close_menu()
            return

        # 2. Handle clicks when a Dropdown Menu is open
        if self.active_menu in ("file", "profile", "view", "play", "tools", "help"):
            clicked_action = None
            for rect, act_type, act_val in self.dropdown_item_rects:
                rx1, ry1, rx2, ry2 = rect
                if rx1 <= x <= rx2 and ry1 <= y <= ry2:
                    clicked_action = (act_type, act_val)
                    break
                    
            if clicked_action:
                act_type, act_val = clicked_action
                print(f"[MENU ACTION] {act_type}: {act_val}")
                
                # Close dropdown immediately via partial restore (3ms)
                self.close_menu()

                if act_type == "sync":
                    self.update_status_msg("동기화 요청 중...")
                    self.waiting_sync_since = time.time()
                    self._safe_ws_send({"type": "request_sync"})
                elif act_type == "reconnect":
                    self.update_status_msg("재연결 시도 중...")
                    self.force_abort_ws()
                elif act_type == "switch_profile":
                    target_name = act_val
                    self.update_status_msg(f"프로필 전환 중: {target_name}")
                    self._safe_ws_send({
                        "type": "switch_profile",
                        "name": target_name
                    })
                elif act_type == "request_profiles":
                    self.update_status_msg("프로필 목록 갱신 중...")
                    self._safe_ws_send({"type": "get_profiles"})
                elif act_type == "pi_reboot":
                    self.update_status_msg("파이 재부팅 중...")
                    os.system("reboot &")
                    return
                elif act_type == "pi_poweroff":
                    self.update_status_msg("파이 시스템 종료 중...")
                    os.system("poweroff &")
                    return
                elif act_type == "brightness":
                    self.set_backlight(act_val)
                elif act_type == "pc_action":
                    cat, payload = act_val
                    self.send_pc_direct_action(cat, payload)
                elif act_type == "ping_test":
                    self.do_ping_test()
                elif act_type == "about_dialog":
                    self.open_about_dialog()
                    return
                elif act_type == "close":
                    pass

                return

            # Check if user clicked another top menu bar item while dropdown is open
            with self.lock:
                menu_bar_items = list(self.menu_bar_rects.items())
            for key, m_info in menu_bar_items:
                mx1, my1, mx2, my2 = m_info["touch"]
                if mx1 <= x <= mx2 and my1 <= y <= my2:
                    if self.active_menu == key:
                        self.close_menu()
                    else:
                        self.open_menu(key)
                    return

            # Clicked outside menu -> Close dropdown (3ms partial restore!)
            self.close_menu()
            return

        # 3. Check Menu Bar Clicks (Open Menu when none open)
        with self.lock:
            menu_bar_items = list(self.menu_bar_rects.items())
        for key, m_info in menu_bar_items:
            mx1, my1, mx2, my2 = m_info["touch"]
            if mx1 <= x <= mx2 and my1 <= y <= my2:
                print(f"[MENU] {key} opened")
                self.open_menu(key)
                return

        # 4. Normal Button Grid Handling
        clicked_id = None
        with self.lock:
            button_items = list(self.button_rects.items())
        for b_id, rect in button_items:
            x1, y1, x2, y2 = rect
            if x1 <= x <= x2 and y1 <= y <= y2:
                clicked_id = b_id
                break
                
        if clicked_id is None:
            return

        print(f"[WIN2K] Button #{clicked_id} Triggered")

        # 1. INSTANT 0.1ms partial blit FIRST (Visual response before network)
        if clicked_id in self.btn_pressed_bytes:
            with self.lock:
                self.blit_button_rect(clicked_id, self.btn_pressed_bytes[clicked_id])
                self.active_pressed_button = clicked_id
                self.pressed_button_time = now

        # 2. Network transmission immediately following visual feedback
        self._safe_ws_send({"type": "trigger_button", "button_id": clicked_id})

    def on_touch_up(self, x, y):
        with self.lock:
            b_id = self.active_pressed_button
            if b_id is None:
                return
            self.active_pressed_button = None
            elapsed = time.time() - self.pressed_button_time

        if elapsed < 0.06:
            # 찰나의 탭(초단기 클릭) 시 시각적 인지를 위해 60ms까지 유지 후 복원
            def snappy_release():
                time.sleep(0.06 - elapsed)
                with self.lock:
                    if b_id in self.btn_normal_bytes:
                        self.blit_button_rect(b_id, self.btn_normal_bytes[b_id])
            threading.Thread(target=snappy_release, daemon=True).start()
        else:
            # 손을 누르고 있다가 뗀 경우 즉시 0.1ms 복원 (스레드 생성 0회!)
            with self.lock:
                if b_id in self.btn_normal_bytes:
                    self.blit_button_rect(b_id, self.btn_normal_bytes[b_id])

    def touch_loop(self):
        if not self.touch_dev:
            print("No touch device bound.")
            return
            
        cur_x = 0
        cur_y = 0
        touch_down = False
        pending_touch = False
        pending_release = False
        
        while True:
            try:
                for event in self.touch_dev.read_loop():
                    try:
                        if event.type == ecodes.EV_ABS:
                            if event.code in (ecodes.ABS_MT_POSITION_X, ecodes.ABS_X):
                                cur_x = event.value
                            elif event.code in (ecodes.ABS_MT_POSITION_Y, ecodes.ABS_Y):
                                cur_y = event.value
                        elif event.type == ecodes.EV_KEY and event.code == ecodes.BTN_TOUCH:
                            if event.value == 1 and not touch_down:
                                touch_down = True
                                pending_touch = True
                                pending_release = False
                            elif event.value == 0:
                                touch_down = False
                                pending_touch = False
                                pending_release = True
                        elif event.type == ecodes.EV_SYN and event.code == ecodes.SYN_REPORT:
                            if pending_touch:
                                pending_touch = False
                                self.on_touch_down(cur_x, cur_y)
                            elif pending_release:
                                pending_release = False
                                self.on_touch_up(cur_x, cur_y)
                    except Exception as e:
                        print(f"Touch event exception: {e}")
            except Exception as e:
                print(f"Touch loop exception: {e}")
                time.sleep(1.0)

    def on_ws_message(self, ws, message):
        if ws is not self.ws:
            return
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            if msg_type in ("sync_buttons", "sync_profile"):
                with self.lock:
                    self.waiting_sync_since = 0.0
                    seq = data.get("seq", 0)
                    if seq:
                        self.last_sync_seq = seq

                    self.current_profile = data.get("profile", self.current_profile)
                    if "profiles" in data and isinstance(data["profiles"], list) and data["profiles"]:
                        self.cached_profiles = list(data["profiles"])
                    elif self.current_profile and self.current_profile not in self.cached_profiles:
                        self.cached_profiles.append(self.current_profile)
                    self.buttons = data.get("buttons", [])
                    self.grid_rows = data.get("grid_rows", 3)
                    self.grid_cols = data.get("grid_cols", 4)
                    self.status_msg = f"온라인 [{self.current_profile}]"
                    self.menu_cache.clear()
                    self.render_full()
            elif msg_type == "profile_list":
                with self.lock:
                    self.cached_profiles = data.get("profiles", self.cached_profiles)
                    self.current_profile = data.get("current", self.current_profile)
                    self.menu_cache.pop("profile", None)
                    if self.active_menu == "profile":
                        self.open_menu("profile")
                    else:
                        self.update_status_msg(f"프로필: {self.current_profile}")
            elif msg_type == "error":
                code = data.get("code")
                msg = data.get("message", "오류 발생")
                self.update_status_msg(f"[{code}] {msg}")
            elif msg_type == "action_result":
                b_id = data.get("button_id")
                status = data.get("status")
                if b_id is not None and b_id >= 0:
                    self.flash_button(b_id, status == "success")
                self.update_status_msg(f"버튼 #{b_id} {status}")
        except Exception as e:
            print(f"WS parse error: {e}")

    def on_ws_open(self, ws):
        if ws is not self.ws:
            return
        self.waiting_sync_since = 0.0
        print("Connected to PC TailDeck Server")
        try:
            s = getattr(ws, 'sock', None)
            real_sock = getattr(s, 'sock', s)
            if real_sock and hasattr(real_sock, 'setsockopt'):
                real_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                real_sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                if hasattr(socket, 'TCP_KEEPIDLE'):
                    real_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 10)
                if hasattr(socket, 'TCP_KEEPINTVL'):
                    real_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 3)
                if hasattr(socket, 'TCP_KEEPCNT'):
                    real_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        except Exception:
            pass
            
        self.connected = True
        self.last_sync_seq = 0
        self.reconnect_attempt = 0
        self.status_msg = "온라인"
        self._safe_ws_send({"type": "get_profiles"})
        self.render_full()

    def on_ws_close(self, ws, code, msg):
        if ws is not self.ws:
            return
        print(f"WebSocket disconnected")
        self.waiting_sync_since = 0.0
        self.connected = False
        self.update_status_msg("연결 끊김 (재시도 중...)")

    def on_ws_error(self, ws, error):
        if ws is not self.ws:
            return
        print(f"WebSocket error: {error}")

    def force_abort_ws(self):
        """Thread-safe wake-up for a stalled run_forever and instant retry.

        close() sends a CLOSE frame (blocking send on a dead socket) then waits up
        to 3s in recv_frame() without readlock, racing the dispatcher that owns the
        same fd. abort() only calls shutdown(SHUT_RDWR), so it never blocks.
        """
        self.reconnect_attempt = 0
        self.reconnect_event.set()
        ws = self.ws
        if not ws:
            return
        try:
            ws.keep_running = False
            if ws.sock is not None:
                ws.sock.abort()
        except Exception as e:
            print(f"WS abort error: {e}")

    def _safe_ws_send(self, payload_dict):
        """Unified, thread-safe WebSocket send helper with auto-recovery on failure.

        On exception: logs error, sets connected=False, triggers non-blocking
        force_abort_ws() to unstick the dispatcher, updates status, and returns False.
        """
        if not self.ws or not self.connected:
            return False
        try:
            msg_str = json.dumps(payload_dict)
            self.ws.send(msg_str)
            return True
        except Exception as e:
            print(f"WS send error ({payload_dict.get('type', 'unknown')}): {e}")
            self.connected = False
            self.force_abort_ws()
            self.update_status_msg("연결 끊김 (재시도 중...)")
            return False

    def ws_loop(self):
        while True:
            target_url = self.get_current_server_url()
            print(f"Connecting to TailDeck Server: {target_url}")
            try:
                self.ws = websocket.WebSocketApp(
                    target_url,
                    on_open=self.on_ws_open,
                    on_message=self.on_ws_message,
                    on_close=self.on_ws_close,
                    on_error=self.on_ws_error
                )
                self.ws.run_forever(ping_interval=10, ping_timeout=5)
            except Exception as e:
                print(f"WS loop exception: {e}")

            # Connection lost or failed - rotate to next candidate host (Tailscale -> LAN -> Localhost)
            self.rotate_server_url_on_fail()

            attempt = getattr(self, "reconnect_attempt", 0)
            backoff = min(15.0, 1.0 * (2 ** min(attempt, 4))) + random.uniform(0.0, 1.0)
            self.reconnect_attempt = attempt + 1
            sleep_time = min(15.0, backoff)
            print(f"WS retry backoff: {sleep_time:.2f}s (next: {self.get_current_server_url()})")
            self.reconnect_event.clear()
            self.reconnect_event.wait(timeout=sleep_time)

    def clock_worker(self):
        """Updates only the 2KB clock area each second with 0% CPU consumption and guards sync timeout"""
        last_sec = ""
        while True:
            cur_sec = time.strftime("%H:%M:%S")
            now = time.time()
            if self.waiting_sync_since > 0 and (now - self.waiting_sync_since > 5.0):
                print("Sync response timed out (zombie socket detected), forcing reconnect...")
                self.waiting_sync_since = 0.0
                self.update_status_msg("동기화 타임아웃 (재연결 중...)")
                self.force_abort_ws()

            if cur_sec != last_sec and self.base_raw_bytes:
                last_sec = cur_sec
                try:
                    self.update_clock()
                except Exception:
                    pass
            time.sleep(0.3)

    def run(self):
        self.render_full()
        
        ws_thread = threading.Thread(target=self.ws_loop, daemon=True)
        ws_thread.start()
        
        # Start blinking cursor clock thread (every 500ms)
        clk_thread = threading.Thread(target=self.clock_worker, daemon=True)
        clk_thread.start()
        
        print("TailDeck 2000 Pro Blinking Cursor Clock Client Running!")
        self.touch_loop()

if __name__ == "__main__":
    client = Win2kThemeClient()
    client.run()
