"""
Session Pointer — generate connection URL and QR code for remote clients.
"""

import socket
from typing import Optional


def get_local_ip() -> str:
    """Get the machine's local network IP (for same-WiFi connections)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def build_connection_url(port: int, token: str, host: str | None = None) -> str:
    """Build the WebSocket connection URL with embedded token."""
    ip = host or get_local_ip()
    return f"ws://{ip}:{port}?token={token}"


def build_web_url(port: int, host: str | None = None) -> str:
    """Build the HTTP URL for the web client."""
    ip = host or get_local_ip()
    return f"http://{ip}:{port}"


def generate_qr_text(url: str) -> str:
    """
    Generate a text-based QR code for terminal display.
    Falls back to a simple URL display if qrcode lib is not available.
    """
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1, box_size=1, border=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
        )
        qr.add_data(url)
        qr.make(fit=True)

        # Render as text using Unicode block characters
        lines = []
        matrix = qr.get_matrix()
        for row in matrix:
            line = ""
            for cell in row:
                line += "\u2588\u2588" if cell else "  "
            lines.append(line)
        return "\n".join(lines)

    except ImportError:
        # No qrcode library; return simple ASCII box
        return (
            f"  +{'─' * (len(url) + 2)}+\n"
            f"  | {url} |\n"
            f"  +{'─' * (len(url) + 2)}+\n"
            f"  (Install 'qrcode' for a scannable QR code)"
        )


def format_session_pointer(port: int, token: str) -> str:
    """Format a complete session pointer display for the terminal."""
    web_url = build_web_url(port)
    ws_url = build_connection_url(port, token)

    lines = [
        "━" * 50,
        "  Bridge Server Running",
        "━" * 50,
        f"  Web client:  {web_url}",
        f"  WebSocket:   ws://localhost:{port}",
        f"  Local IP:    {get_local_ip()}:{port}",
        "",
        "  Scan to connect from phone:",
        "",
    ]

    qr = generate_qr_text(web_url)
    for qr_line in qr.splitlines():
        lines.append(f"    {qr_line}")

    lines.extend([
        "",
        "━" * 50,
    ])
    return "\n".join(lines)
