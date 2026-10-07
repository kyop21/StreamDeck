import socket
import subprocess
import io
from typing import Optional
import qrcode
from PIL import Image


def get_tailscale_ip() -> Optional[str]:
    """Tailscale CLI를 통해 100.x.y.z 사설 IP를 조회합니다."""
    try:
        output = subprocess.check_output(
            ["tailscale", "ip", "-4"],
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        ).decode("utf-8").strip()
        if output:
            lines = output.splitlines()
            return lines[0].strip()
    except Exception:
        pass
    return None


def get_local_ip() -> str:
    """로컬 네트워크 IP (Fallback)를 조회합니다."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_server_ip() -> str:
    """Tailscale IP 우선 반환, 실패 시 로컬 IP 반환"""
    return get_tailscale_ip() or get_local_ip()


def generate_qr_image(url: str, box_size: int = 6, border: int = 2) -> Image.Image:
    """URL을 담은 QR 코드 PIL Image를 생성합니다."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img


def generate_qr_png_bytes(url: str) -> bytes:
    """URL의 QR 코드를 PNG 바이너리 바이트로 반환합니다."""
    img = generate_qr_image(url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
