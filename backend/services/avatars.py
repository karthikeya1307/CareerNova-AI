"""Profile pictures: validation and private storage.

* Accepted: PNG, JPEG and WebP, detected from the file's own header (the name and the browser's
  content type are not trusted). SVG, GIF and anything else are refused (SVG can carry scripts).
* At most 2 MB and between 32 and 4096 pixels per side (read from the image header).
* Stored as uploads/avatars/<user id>/<random>.<ext>; the path never comes from user input.
* Served only to the signed-in owner (GET /profiles/me/avatar) with nosniff and no-store headers.
"""

from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
AVATAR_DIR = BASE_DIR / "uploads" / "avatars"
MAX_BYTES = 2 * 1024 * 1024
MIN_SIDE, MAX_SIDE = 32, 4096
TYPES = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}


class AvatarError(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message, self.status_code = message, status_code


@dataclass(frozen=True)
class ImageInfo:
    kind: str           # png | jpeg | webp
    width: int
    height: int

    @property
    def content_type(self) -> str:
        return TYPES[self.kind]


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height
        i += 2 + length
    return None


def inspect(data: bytes) -> ImageInfo:
    """Identify a PNG/JPEG/WebP from its header and read its size; AvatarError otherwise."""
    if not data:
        raise AvatarError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise AvatarError("The picture is larger than 2 MB.", 413)
    size = None
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        kind, size = "png", struct.unpack(">II", data[16:24])
    elif data[:3] == b"\xff\xd8\xff":
        kind, size = "jpeg", _jpeg_size(data)
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        kind, chunk = "webp", data[12:16]
        if chunk == b"VP8 " and len(data) >= 30:
            w, h = struct.unpack("<HH", data[26:30])
            size = (w & 0x3FFF, h & 0x3FFF)
        elif chunk == b"VP8L" and len(data) >= 25:
            bits = int.from_bytes(data[21:25], "little")
            size = ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        elif chunk == b"VP8X" and len(data) >= 30:
            size = (int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1)
    else:
        raise AvatarError("Use a PNG, JPEG or WebP picture.", 415)
    if size is None:
        raise AvatarError("The picture could not be read - the file may be damaged.")
    width, height = size
    if not (MIN_SIDE <= width <= MAX_SIDE and MIN_SIDE <= height <= MAX_SIDE):
        raise AvatarError(f"The picture must be between {MIN_SIDE} and {MAX_SIDE} pixels on each side "
                          f"(this one is {width}x{height}).")
    return ImageInfo(kind, width, height)


def user_dir(user_id: int) -> Path:
    return AVATAR_DIR / str(int(user_id))


def save(user_id: int, data: bytes, info: ImageInfo) -> str:
    """Write the picture under the user's folder; returns the stored relative path."""
    folder = user_dir(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{'jpg' if info.kind == 'jpeg' else info.kind}"
    target = folder / name
    target.write_bytes(data)
    return f"{int(user_id)}/{name}"


def resolve(user_id: int, stored: str | None) -> Path | None:
    """The file for a stored path, only if it is inside that user's own folder and exists."""
    if not stored:
        return None
    path = (AVATAR_DIR / stored).resolve()
    base = user_dir(user_id).resolve()
    if base not in path.parents or not path.is_file():
        return None
    return path


def remove(user_id: int, stored: str | None) -> None:
    path = resolve(user_id, stored)
    if path is not None:
        try:
            path.unlink()
        except OSError:
            pass
