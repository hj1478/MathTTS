"""Stand-in for backend.ocr_proc's child, for tests/test_ocr_proc.py. No paddle, no GPU.

Same protocol as the real child; the "device" argument picks the behaviour:
  ok         answers every request
  hang       answers nothing, ignores SIGTERM, and holds a grandchild (sleep) too
  hang_load  never reports ready
  error      every call raises
  crash      exits mid-call
"""
import os
import signal
import subprocess
import sys
import time
from multiprocessing.connection import Connection


def main(conn, mode):
    if mode == "hang_load":
        time.sleep(3600)
    conn.send(("ready", None))
    while True:
        req = conn.recv()
        if req is None:
            return
        image, out_dir, _ = req
        if mode == "ok":
            conn.send(("ok", (f"text of {os.path.basename(image)}", f"{out_dir}/x.md")))
        elif mode == "error":
            conn.send(("error", "RuntimeError: fake OCR failure"))
        elif mode == "crash":
            os._exit(3)
        elif mode == "hang":
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            grandchild = subprocess.Popen(["sleep", "3600"])
            print(f"GRANDCHILD {grandchild.pid}", flush=True)
            time.sleep(3600)


if __name__ == "__main__":
    main(Connection(int(sys.argv[1])), sys.argv[2])
