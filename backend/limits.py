"""Upload validation, Azure quota detection and rate-limit slots for the web API.

Pure helpers with no Modal or FastAPI import, so tests/test_backend.py can
check them locally. backend/modal_app.py is the only caller.
"""
import io
import re

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# A multipart body carries the file plus a boundary and part headers; this is
# the slack allowed on top of MAX_UPLOAD_BYTES before the body is even parsed.
MULTIPART_SLACK = 64 * 1024
# Pillow's own decompression-bomb guard starts at ~89 MP; a worksheet photo is
# a fraction of that. Rejecting earlier keeps a crafted file off the GPU.
MAX_PIXELS = 40_000_000

# ext must be one ocr_vl.IMAGE_EXTS accepts — the worker saves the upload under
# it and the OCR stage reads it back by path.
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"BM", ".bmp"),
    (b"II*\x00", ".tif"),
    (b"MM\x00*", ".tif"),
)


def sniff_image(data):
    """Leading bytes -> file extension, or None for anything not supported.

    The declared Content-Type is client-controlled, so the bytes decide.
    """
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    for sig, ext in _SIGNATURES:
        if data.startswith(sig):
            return ext
    return None


def is_heic(data):
    """iPhone photos default to HEIC, which the OCR stage cannot open.

    Detected separately so the client can be told to convert, rather than
    getting a generic "unsupported type".
    """
    return data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"hevc", b"heim",
                                                    b"heis", b"mif1", b"msf1", b"avif")


def check_decodes(data):
    """Return None if Pillow can parse the image header and its size is sane,
    else a short reason. Runs on the cheap web container, before any GPU job.
    """
    from PIL import Image
    try:
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
            im.verify()
    except Exception as e:  # truncated / corrupt / not really an image
        return f"{type(e).__name__}"
    if w * h > MAX_PIXELS:
        return f"too many pixels ({w}x{h})"
    return None


# What the Speech SDK puts in cancellation_details.error_details when the F0
# quota (or F0's request-rate limit) is exhausted. tts_probe.synth folds that
# text into its detail string, which is all the worker sees. Matched loosely on
# purpose: the exact wording is not documented and has not been observed here
# against a real exhausted quota — only "429" / "Too many requests" is.
_QUOTA = re.compile(r"\b429\b|too many requests|quota", re.IGNORECASE)


def is_quota_error(detail):
    return bool(_QUOTA.search(detail or ""))


def slot_keys(ip, now, limit, window_s=3600):
    """The `limit` slot keys for `ip` in the current fixed window.

    A request is allowed if it can claim any one of them with an atomic
    put-if-absent (modal.Dict.put(..., skip_if_exists=True)). Each slot is its
    own key, so two containers racing for the last slot cannot both win it —
    a get-then-put counter could.
    """
    bucket = int(now // window_s)
    return [f"{ip}|{bucket}|{i}" for i in range(limit)]


def retry_after(now, window_s=3600):
    """Seconds until the current window ends (for the Retry-After header)."""
    return int((now // window_s + 1) * window_s - now) + 1


def take_slot(put_if_absent, ip, now, limit, window_s=3600):
    """Synchronous form of the slot claim -> (allowed, retry_after_seconds)."""
    for key in slot_keys(ip, now, limit, window_s):
        if put_if_absent(key):
            return True, 0
    return False, retry_after(now, window_s)


def slot_bucket(key):
    """Window number of a take_slot key (for cleanup), or None if not one."""
    parts = key.split("|")
    return int(parts[-2]) if len(parts) >= 3 and parts[-2].isdigit() else None
