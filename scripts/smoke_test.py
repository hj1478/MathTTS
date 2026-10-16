#!/usr/bin/env python3
"""Smoke-test the DEPLOYED MathTTS backend over HTTP.

Sends HTTP requests only: it never imports the pipeline, so it is safe to run on
any laptop. Needs `requests`.

    python scripts/smoke_test.py https://<workspace>--mathtts.<region>.modal.run
    python scripts/smoke_test.py <url> --image "kr question 2.png"
    python scripts/smoke_test.py <url> --repeat 2   # 1st = cold start, 2nd = warm

Each run submits the image, polls until the job finishes, checks that every
stage returned output, prints them, and downloads the wav. It also checks that
a non-image upload is rejected with 415 before any GPU work, which costs no
rate-limit slot.

Each submitted job uses 1 of the 10 jobs/hour for your IP and one Azure
synthesis. audio.status "quota_reached" is reported but is not a failure: the
backend is designed to return the text stages when the Azure quota runs out.

Exit code 0 means every check passed.
"""
import argparse
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
POLL_S = 1.5
TIMEOUT_S = 900  # covers a cold image pull + model load + the job


def fail(msg):
    sys.exit(f"FAIL: {msg}")


def check_rejects_non_image(base):
    r = requests.post(f"{base}/jobs", files={"image": ("note.txt", b"not an image", "image/png")},
                      timeout=60)
    if r.status_code != 415 or r.json().get("error", {}).get("code") != "unsupported_type":
        fail(f"non-image upload: expected 415 unsupported_type, got {r.status_code} {r.text[:200]}")
    print("ok   non-image upload rejected (415 unsupported_type)")


def run_once(base, image):
    t0 = time.monotonic()
    with open(image, "rb") as f:
        r = requests.post(f"{base}/jobs", files={"image": (image.name, f)}, timeout=60)
    if r.status_code != 202:
        fail(f"POST /jobs: expected 202, got {r.status_code} {r.text[:300]}")
    job_id = r.json()["id"]
    print(f"ok   POST /jobs -> 202, id {job_id}")

    last = None
    while True:
        r = requests.get(f"{base}/jobs/{job_id}", timeout=60)
        if r.status_code != 200:
            fail(f"GET /jobs/{job_id}: {r.status_code} {r.text[:300]}")
        body = r.json()
        state = (body["status"], body.get("stage"))
        if state != last:
            print(f"     {time.monotonic() - t0:6.1f}s  {body['status']}"
                  + (f" ({body['stage']})" if body.get("stage") else ""))
            last = state
        if body["status"] in ("done", "failed"):
            break
        if time.monotonic() - t0 > TIMEOUT_S:
            fail(f"job {job_id} not finished after {TIMEOUT_S}s")
        time.sleep(POLL_S)
    total = time.monotonic() - t0

    if body["status"] == "failed":
        fail(f"job failed: {body.get('error')}")

    s = body["stages"]
    checks = {
        "stages.ocr.text": s["ocr"]["text"].strip(),
        "stages.normalized.text": s["normalized"]["text"].strip(),
        "stages.math_spans": s["math_spans"],
        "stages.speech.text": s["speech"]["text"].strip(),
        "stages.speech.ssml": (s["speech"]["ssml"] or "").strip(),
    }
    for name, value in checks.items():
        if not value:
            fail(f"{name} is empty")
        print(f"ok   {name}")
    if not s["speech"]["strict_ok"]:
        fail("stages.speech.strict_ok is false (a formula stitched as salvage/placeholder)")

    audio = body["audio"]
    if audio["status"] == "ready":
        r = requests.get(audio["url"], timeout=60)
        if r.status_code != 200 or r.content[:4] != b"RIFF" or r.content[8:12] != b"WAVE":
            fail(f"GET {audio['url']}: expected a wav, got {r.status_code} "
                 f"{r.headers.get('content-type')} {r.content[:16]!r}")
        print(f"ok   GET /audio/{job_id} -> {len(r.content):,} B wav")
    elif audio["status"] == "quota_reached":
        print(f"WARN audio quota_reached: {audio['message']}")
    else:
        fail(f"audio.status {audio['status']}: {audio['message']}")

    return job_id, total, body


def print_stages(body):
    s = body["stages"]
    bar = "-" * 72
    print(f"\n{bar}\nSTAGE 1  OCR text\n{bar}\n{s['ocr']['text']}")
    print(f"\n{bar}\nSTAGE 2  normalized text\n{bar}\n{s['normalized']['text']}")
    print(f"\n{bar}\nmath spans ({len(s['math_spans'])})\n{bar}")
    for i, m in enumerate(s["math_spans"], 1):
        print(f"  {i:2}. {'[display] ' if m['display'] else ''}{m['latex']}")
    print(f"\n{bar}\nSTAGE 3  spoken text (SRE Korean, stitched)\n{bar}\n{s['speech']['text']}")
    print(f"\n{bar}\nSTAGE 3  SSML sent to Azure\n{bar}\n{s['speech']['ssml']}")
    print("\nspeak.js summary: " + " | ".join(s["speech"]["summary"]))
    a = body["audio"]
    print(f"\n{bar}\nSTAGE 4  audio: {a['status']} — {a['message']}\n  url: {a['url']}")
    print(f"server timings (s): {body['timings_s']}")


def main():
    ap = argparse.ArgumentParser(description="Smoke-test the deployed MathTTS backend.")
    ap.add_argument("base_url", help="e.g. https://<workspace>--mathtts.us-east.modal.run")
    ap.add_argument("--image", default=str(ROOT / "kr question 1.png"))
    ap.add_argument("--repeat", type=int, default=1,
                    help="submit the image this many times in a row (2 = cold then warm)")
    a = ap.parse_args()
    base = a.base_url.rstrip("/")
    image = Path(a.image)
    if not image.is_file():
        fail(f"no such image: {image}")

    check_rejects_non_image(base)
    times = []
    for n in range(1, a.repeat + 1):
        print(f"\n== request {n}/{a.repeat}: {image.name} ==")
        job_id, total, body = run_once(base, image)
        times.append(total)
        print(f"     total {total:.1f}s (submit -> done), server timings {body['timings_s']}")
    print_stages(body)

    print("\n== end-to-end time per request (submit -> done, as seen by this client) ==")
    for n, t in enumerate(times, 1):
        print(f"  request {n}: {t:6.1f}s")
    print("\nPASS")


if __name__ == "__main__":
    main()
