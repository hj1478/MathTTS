"""OCR in a child process that the worker kills outright at a cutoff.

On a T4, PaddleOCR-VL's first OCR call in a fresh container often never
returns: it blocks in a native op (_C_ops.embedding) with the GPU idle. Neither
Modal's timeout nor retiring the container reliably frees the GPU, because a
thread cannot be killed (FINDINGS.md, 2026-10-16). A process can. So the model
lives in a child process, every call waits with a cutoff, and on a hang the
worker SIGKILLs the child's whole process group. The GPU memory goes with it.

The parent side is stdlib only and never imports paddle, so after a kill it
holds no CUDA context and has no threads left running.

    ocr = OcrProcess()
    ocr.start(timeout=300)                      # loads the model in the child
    text, md_path = ocr.run(image, out_dir, timeout=60)   # OcrTimeout on a hang

The child is `python -m backend.ocr_proc <fd>` and talks over a socketpair, so
paddle's own prints on stdout/stderr never mix with the protocol.
"""
import os
import signal
import socket
import subprocess
import sys
from multiprocessing.connection import Connection
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class OcrTimeout(Exception):
    """The child did not answer within the cutoff and has been killed."""


class OcrFailed(Exception):
    """The OCR call raised in the child, or the child died."""


class OcrProcess:
    def __init__(self, device="gpu", child_module="backend.ocr_proc", env=None):
        self.device = device
        self.child_module = child_module  # tests swap in a fake child
        self.env = env or {}              # set in the child before paddle is imported
        self.info = None                  # what the child reported once loaded
        self._proc = None
        self._conn = None

    @property
    def pid(self):
        return self._proc.pid if self._proc else None

    def alive(self):
        return self._proc is not None and self._proc.poll() is None

    def start(self, timeout):
        """Start the child and wait until it reports the model loaded."""
        parent_sock, child_sock = socket.socketpair()
        fd = child_sock.fileno()
        self._proc = subprocess.Popen(
            [sys.executable, "-m", self.child_module, str(fd), self.device],
            cwd=str(ROOT), pass_fds=[fd], env={**os.environ, **self.env},
            start_new_session=True,  # its own process group: the kill takes grandchildren too
        )
        child_sock.close()
        self._conn = Connection(parent_sock.detach())
        _, self.info = self._wait(timeout, "model load")

    def run(self, image, out_dir, timeout):
        """One OCR call -> (text, md_path). Raises OcrTimeout or OcrFailed."""
        if not self.alive():
            raise OcrFailed("OCR process is not running")
        # the child dumps its own stacks just before the cutoff, for the logs
        self._conn.send((str(image), str(out_dir), max(timeout - 3, 1)))
        status, value = self._wait(timeout, "OCR call")
        if status == "error":
            raise OcrFailed(value)
        return value

    def stats(self, timeout=10):
        """Paddle's peak GPU memory in the child so far (MiB)."""
        self._conn.send("stats")
        return self._wait(timeout, "stats")[1]

    def _wait(self, timeout, what):
        try:
            if self._conn.poll(timeout):
                return self._conn.recv()
        except (EOFError, OSError):
            code = self._proc.poll()
            self.kill()
            raise OcrFailed(f"OCR process died during {what} (exit {code})") from None
        self.kill()
        raise OcrTimeout(f"{what} still running after {timeout}s; OCR process killed")

    def kill(self):
        """SIGKILL the child's process group and reap it. Returns True once it is gone."""
        if self._proc is None:
            return True
        if self._proc.poll() is None:
            try:
                os.killpg(self._proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                self._proc.wait(10)
            except subprocess.TimeoutExpired:
                print(f"[ocr] child {self._proc.pid} did not die after SIGKILL", flush=True)
                return False
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        return True

    def close(self):
        """Ask the child to exit; kill it if it does not."""
        if self.alive() and self._conn is not None:
            try:
                self._conn.send(None)
                self._proc.wait(10)
            except Exception:
                pass
        self.kill()


def _serve(conn, device):
    """Child: load the model once, then answer OCR requests until told to stop."""
    import faulthandler

    import ocr_vl
    ocr_vl.pipeline(device)
    import paddle
    flag = "FLAGS_allocator_strategy"
    info = {"allocator_strategy": paddle.get_flags([flag])[flag], "paddle": paddle.__version__}
    print(f"[ocr child] loaded; {info}", flush=True)
    conn.send(("ready", info))
    while True:
        req = conn.recv()
        if req is None:
            return
        if req == "stats":
            mib = 1024 * 1024
            conn.send(("stats", {
                "max_allocated_mib": round(paddle.device.cuda.max_memory_allocated() / mib),
                "max_reserved_mib": round(paddle.device.cuda.max_memory_reserved() / mib),
            }))
            continue
        image, out_dir, dump_after = req
        faulthandler.dump_traceback_later(dump_after, exit=False, file=sys.stderr)
        try:
            reply = ("ok", ocr_vl.run_image(image, out_dir, device))
        except Exception as e:
            reply = ("error", f"{type(e).__name__}: {e}")
        finally:
            faulthandler.cancel_dump_traceback_later()
        conn.send(reply)


if __name__ == "__main__":
    _serve(Connection(int(sys.argv[1])), sys.argv[2])
