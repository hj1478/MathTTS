"""One-off diagnostics for the OCR stage, as their own Modal app ("mathtts-diag").

Kept out of the production app (backend/modal_app.py: Worker, web, cleanup) so
a deploy never ships them. Nothing here is deployed; each check runs with
`modal run` and stops when it is done:

    modal run backend/diagnostics.py::selftest       # CPU only: hard kill of a fake hang
    modal run backend/diagnostics.py::fresh_test     # first OCR call in N fresh processes
        --gpu T4|L4  --allocator naive_best_fit|default  --n 10
    modal run backend/diagnostics.py::output_check   # golden images: OCR text vs output/
    modal run backend/diagnostics.py::stack_check    # native state of a default-allocator hang
    modal run backend/diagnostics.py::cpu_check      # one image, device="cpu", no GPU
    modal run backend/diagnostics.py::warm_timing    # load, 1 first call, N warm calls
        --gpu T4|L4  --n 5

The images are the production ones (modal_app.pipeline_image), plus
modal_app.py itself so this module can import it in the container. All use the
same OcrProcess as the worker. An OCR call still running after DIAG_HANG_S is
killed with its process group (the child dumps its own stacks to the log just
before), and the container is retired. retries=0 throughout. Background:
FINDINGS.md, 2026-10-16.
"""
import os
import time
from pathlib import Path

import modal

from modal_app import (REPO, STARTUP_TIMEOUT_S, _retire_container, pipeline_image,
                       worker_image)

app = modal.App("mathtts-diag")


def _with_app_module(image):
    return image.add_local_file(REPO / "backend" / "modal_app.py", "/root/modal_app.py")


gpu_image = _with_app_module(worker_image)               # the worker's image
cpu_image = _with_app_module(pipeline_image("cpu"))      # CPU paddle build, same versions
# CPU only: checks the hard kill on Modal with a fake hanging child (no paddle)
selftest_image = _with_app_module(
    modal.Image.debian_slim(python_version="3.11")
    .add_local_file(REPO / "backend" / "ocr_proc.py", "/root/backend/ocr_proc.py")
    .add_local_file(REPO / "tests" / "fake_ocr_child.py", "/root/tests/fake_ocr_child.py")
)

DIAG_HANG_S = 60
DIAG_PARALLEL = 4
DIAG_IMAGES = ["kr question 1.png", "kr question 2.png", "kr question 3.png",
               "kr question 4.png", "kr question 5.png", "page.png"]
DIAG_KW = dict(memory=16384, retries=0, startup_timeout=STARTUP_TIMEOUT_S,
               timeout=STARTUP_TIMEOUT_S + 8 * DIAG_HANG_S)


def _allocator_env(allocator):
    return {} if allocator == "default" else {"FLAGS_allocator_strategy": allocator}


def _nvidia_smi(query):
    import subprocess
    return subprocess.run(f"nvidia-smi --query-gpu={query} --format=csv,noheader,nounits",
                          shell=True, capture_output=True, text=True).stdout.strip() or "none"


def _first_call(i, image_bytes, ext, allocator):
    """Load the model and make ONE OCR call in a fresh child process, as a fresh
    worker would, then retire the container."""
    from backend.ocr_proc import OcrFailed, OcrProcess, OcrTimeout

    out = {"i": i, "container": os.environ.get("MODAL_TASK_ID"), "gpu": _nvidia_smi("name")}
    ocr = OcrProcess("gpu", env=_allocator_env(allocator))
    t = time.monotonic()
    try:
        ocr.start(timeout=STARTUP_TIMEOUT_S - 30)
        out["load_s"] = round(time.monotonic() - t, 1)
        out["child"] = ocr.info  # the allocator strategy paddle actually uses
        work = Path("/tmp/first_call")
        work.mkdir(parents=True, exist_ok=True)
        image = work / f"sample{ext}"
        image.write_bytes(image_bytes)
        t = time.monotonic()
        try:
            text, _ = ocr.run(image, work / "ocr", timeout=DIAG_HANG_S)
            out.update(result="ok", chars=len(text), gpu_used_mib=_nvidia_smi("memory.used"),
                       paddle_mem=ocr.stats())
        except OcrTimeout as e:
            out.update(result="hang", error=str(e))
        except OcrFailed as e:
            out.update(result="error", error=str(e))
        out["s"] = round(time.monotonic() - t, 1)
    except (OcrTimeout, OcrFailed) as e:
        out.update(result="load_failed", error=str(e))
    finally:
        ocr.close()
        out["child_gone"] = not ocr.alive()
        _retire_container()
    return out


@app.function(image=gpu_image, gpu="T4", max_containers=DIAG_PARALLEL, **DIAG_KW)
def first_call_t4(i, image_bytes, ext, allocator):
    return _first_call(i, image_bytes, ext, allocator)


@app.function(image=gpu_image, gpu="L4", max_containers=DIAG_PARALLEL, **DIAG_KW)
def first_call_l4(i, image_bytes, ext, allocator):
    return _first_call(i, image_bytes, ext, allocator)


def _warm_calls(image_bytes, ext, n):
    """Load the model once, make one first call, then n warm calls on the same
    image, as a warm worker would. Times are the worker's view (OcrProcess.run)."""
    from backend.ocr_proc import OcrProcess

    from modal_app import OCR_ENV
    out = {"gpu": _nvidia_smi("name")}
    ocr = OcrProcess("gpu", env=OCR_ENV)
    t = time.monotonic()
    try:
        ocr.start(timeout=STARTUP_TIMEOUT_S - 30)
        out["load_s"] = round(time.monotonic() - t, 2)
        work = Path("/tmp/warm")
        work.mkdir(parents=True, exist_ok=True)
        image = work / f"sample{ext}"
        image.write_bytes(image_bytes)
        times, chars = [], set()
        for i in range(n + 1):
            t = time.monotonic()
            text, _ = ocr.run(image, work / f"ocr{i}", timeout=DIAG_HANG_S)
            times.append(round(time.monotonic() - t, 2))
            chars.add(len(text))
        out.update(first_s=times[0], warm_s=times[1:], chars=sorted(chars))
    finally:
        ocr.close()
        _retire_container()
    return out


@app.function(image=gpu_image, gpu="T4", **DIAG_KW)
def warm_calls_t4(image_bytes, ext, n):
    return _warm_calls(image_bytes, ext, n)


@app.function(image=gpu_image, gpu="L4", **DIAG_KW)
def warm_calls_l4(image_bytes, ext, n):
    return _warm_calls(image_bytes, ext, n)


@app.function(image=gpu_image, gpu="T4", **DIAG_KW)
def ocr_outputs_t4(images, allocator, attempts=3):
    """OCR every image in one child process -> {name: markdown}, plus what happened.

    The first call in a process can hang (FINDINGS.md, 2026-10-16); then the
    child is killed and a fresh one tried, up to `attempts` processes.
    """
    from backend.ocr_proc import OcrFailed, OcrProcess, OcrTimeout

    log, outputs = [], {}
    for attempt in range(1, attempts + 1):
        ocr = OcrProcess("gpu", env=_allocator_env(allocator))
        try:
            ocr.start(timeout=STARTUP_TIMEOUT_S - 30)
            log.append(f"process {attempt}: {ocr.info}")
            for name, data in images.items():
                if name in outputs:
                    continue
                image = Path("/tmp/golden") / str(attempt) / name
                image.parent.mkdir(parents=True, exist_ok=True)
                image.write_bytes(data)
                t = time.monotonic()
                text, md_path = ocr.run(image, image.parent / "ocr", timeout=DIAG_HANG_S)
                md = Path(md_path) if md_path else None
                outputs[name] = md.read_text(encoding="utf-8") if md and md.exists() else text
                log.append(f"  {name}: {time.monotonic() - t:.1f}s")
            ocr.close()
            break
        except (OcrTimeout, OcrFailed) as e:
            log.append(f"  process {attempt}: {type(e).__name__}: {e}")
            ocr.close()
    _retire_container()
    return {"outputs": outputs, "log": log}


@app.function(image=cpu_image, cpu=8, **DIAG_KW)
def ocr_cpu(image_bytes, name):
    """The same pipeline and settings with device="cpu", in a CPU-only container.
    The image has the CPU paddlepaddle build of the same version: the GPU build
    cannot even be imported without the NVIDIA driver (libcuda.so.1)."""
    from backend.ocr_proc import OcrFailed, OcrProcess, OcrTimeout

    out = {"cpu_count": os.cpu_count()}
    ocr = OcrProcess("cpu")
    t = time.monotonic()
    try:
        ocr.start(timeout=STARTUP_TIMEOUT_S - 30)
        out.update(load_s=round(time.monotonic() - t, 1), child=ocr.info)
        image = Path("/tmp/cpu") / name
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(image_bytes)
        t = time.monotonic()
        text, md_path = ocr.run(image, image.parent / "ocr", timeout=DIAG_HANG_S)
        md = Path(md_path) if md_path else None
        out.update(result="ok", s=round(time.monotonic() - t, 1),
                   markdown=md.read_text(encoding="utf-8") if md and md.exists() else text)
    except (OcrTimeout, OcrFailed) as e:
        out.update(result=type(e).__name__, error=str(e), s=round(time.monotonic() - t, 1))
    finally:
        ocr.close()
        _retire_container()
    return out


STACK_AT_S = 25  # a first call takes ~7 s; still running at 25 s means hung


@app.function(gpu="T4", image=gpu_image, memory=16384, retries=0,
              startup_timeout=STARTUP_TIMEOUT_S, timeout=STARTUP_TIMEOUT_S + 6 * DIAG_HANG_S)
def native_stack(image_bytes, ext, attempts=4):
    """Default allocator: fresh OCR processes until one hangs, then what each
    thread of the hung child is doing natively. ptrace is not permitted in a
    Modal container (gdb: "ptrace: Operation not permitted", py-spy: permission
    denied), so this reads /proc/<pid>/task/*/{stat,wchan,syscall} instead,
    3 samples 2 s apart. x86_64 syscall 16 is ioctl. The 60 s kill still applies."""
    import threading
    from backend.ocr_proc import OcrFailed, OcrProcess, OcrTimeout

    def read(path):
        try:
            return Path(path).read_text(errors="replace").strip()
        except OSError as e:
            return f"<{type(e).__name__}: {e.strerror}>"

    def threads(pid):
        rows = []
        for task in sorted(Path(f"/proc/{pid}/task").iterdir(), key=lambda p: int(p.name)):
            stat = read(task / "stat")
            state = stat.rsplit(")", 1)[-1].split()[0] if ")" in stat else stat
            rows.append(f"{task.name:>7} {read(task / 'comm')[:15]:<15} state={state} "
                        f"wchan={read(task / 'wchan')} syscall={read(task / 'syscall').split(' ')[0]}")
        return rows

    log = []
    image = Path("/tmp/stack") / f"sample{ext}"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(image_bytes)
    for attempt in range(1, attempts + 1):
        ocr = OcrProcess("gpu")
        ocr.start(timeout=STARTUP_TIMEOUT_S - 30)
        result = {}

        def call():
            try:
                ocr.run(image, image.parent / "ocr", timeout=DIAG_HANG_S)
                result["r"] = "ok"
            except (OcrTimeout, OcrFailed) as e:
                result["r"] = f"{type(e).__name__}: {e}"

        t = threading.Thread(target=call)
        t.start()
        t.join(STACK_AT_S)
        if not t.is_alive():
            log.append(f"process {attempt} ({ocr.info}): {result['r']}, no hang")
            ocr.close()
            continue
        pid = ocr.pid
        out = {"attempt": attempt, "child": ocr.info, "gpu_util": _nvidia_smi("utilization.gpu"),
               "samples": []}
        for _ in range(3):
            try:
                out["samples"].append(threads(pid))
            except OSError as e:
                out["samples"].append([f"<{type(e).__name__}: {e}>"])
            time.sleep(2)
        t.join()
        out["after"] = result.get("r")
        out["log"] = log
        ocr.close()
        _retire_container()
        return out
    _retire_container()
    return {"log": log, "note": f"no hang in {attempts} fresh processes"}


@app.function(image=selftest_image, retries=0, timeout=120)
def hardkill_selftest(cutoff_s=5):
    """Fake child that hangs, ignores SIGTERM and has a grandchild: is it gone at the cutoff?"""
    from backend.ocr_proc import OcrProcess, OcrTimeout

    ocr = OcrProcess(device="hang", child_module="tests.fake_ocr_child")
    ocr.start(timeout=10)
    pgid = ocr.pid
    t = time.monotonic()
    try:
        ocr.run("/tmp/sample.png", "/tmp/out", timeout=cutoff_s)
        timed_out = False
    except OcrTimeout:
        timed_out = True
    elapsed = round(time.monotonic() - t, 1)
    try:
        os.killpg(pgid, 0)
        group_gone = False
    except ProcessLookupError:
        group_gone = True
    _retire_container()
    return {"timed_out": timed_out, "cutoff_s": cutoff_s, "elapsed_s": elapsed,
            "child_alive": ocr.alive(), "process_group_gone": group_gone}


@app.local_entrypoint()
def cpu_check(image: str = str(REPO / "kr question 2.png")):
    """One image through OCR on CPU, printed next to the saved output/<stem>.md."""
    path = Path(image)
    r = ocr_cpu.remote(path.read_bytes(), path.name)
    saved = REPO / "output" / f"{path.stem}.md"
    print(f"\n===== CPU OCR: {path.name} =====")
    print({k: v for k, v in r.items() if k != "markdown"})
    print(f"[cpu]   {r.get('markdown')!r}")
    print(f"[saved] {saved.read_text(encoding='utf-8') if saved.exists() else None!r}")


@app.local_entrypoint()
def stack_check(report: str = ""):
    """What the threads of a hung first call (default allocator) are doing natively."""
    import json
    r = native_stack.remote((REPO / "kr question 1.png").read_bytes(), ".png")
    print("\n===== native stack of a hung first call (default allocator, T4) =====")
    for line in r.get("log", []):
        print(line)
    for k in ("note", "attempt", "child", "gpu_util", "after"):
        if k in r:
            print(f"{k}: {r[k]}")
    for n, sample in enumerate(r.get("samples", []), 1):
        print(f"\n--- sample {n} (tid, comm, state, wchan, syscall nr; 16 = ioctl) ---")
        print("\n".join(sample))
    if report:
        Path(report).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"full report: {report}")


@app.local_entrypoint()
def selftest():
    t = time.monotonic()
    print(hardkill_selftest.remote())
    print(f"round trip incl. container start: {time.monotonic() - t:.1f}s")


@app.local_entrypoint()
def fresh_test(gpu: str = "T4", allocator: str = "naive_best_fit", n: int = 10,
               image: str = str(REPO / "kr question 1.png"), report: str = ""):
    import json
    import statistics
    fn = {"T4": first_call_t4, "L4": first_call_l4}[gpu]
    path = Path(image)
    results = list(fn.map(range(n), kwargs={"image_bytes": path.read_bytes(),
                                            "ext": path.suffix.lower(), "allocator": allocator},
                          return_exceptions=True))
    rows = [r for r in results if isinstance(r, dict)]
    by = {k: [r for r in rows if r["result"] == k] for k in ("ok", "hang", "error", "load_failed")}
    print(f"\n===== fresh-process test: {gpu}, allocator={allocator}, {n} calls =====")
    print(f"GPU: {sorted({r['gpu'] for r in rows})} | distinct containers: "
          f"{len({r['container'] for r in rows})}")
    print(f"allocator reported by the child: "
          f"{sorted({str((r.get('child') or {}).get('allocator_strategy')) for r in rows})}")
    print(" | ".join(f"{k} {len(v)}" for k, v in by.items())
          + f" | exceptions {len(results) - len(rows)}")
    if by["ok"]:
        times = sorted(r["s"] for r in by["ok"])
        print(f"first-call OCR time (s): min {times[0]}, median {statistics.median(times)}, "
              f"max {times[-1]} | all: {times}")
        print(f"model load (s): {sorted(r['load_s'] for r in by['ok'])} | chars: "
              f"{sorted({r['chars'] for r in by['ok']})}")
        print(f"GPU memory used, nvidia-smi (MiB): {sorted({r['gpu_used_mib'] for r in by['ok']})}")
        print(f"paddle peak (MiB): {sorted({str(r['paddle_mem']) for r in by['ok']})}")
    print(f"OCR child gone at the end, every container: {all(r['child_gone'] for r in rows)}")
    for r in rows:
        if r["result"] != "ok":
            print(f"  #{r['i']} {r['result']}: {r.get('error')}")
    for r in results:
        if not isinstance(r, dict):
            print(f"  exception: {r!r}")
    if report:
        Path(report).write_text(json.dumps([r if isinstance(r, dict) else repr(r)
                                            for r in results], ensure_ascii=False, indent=2),
                                encoding="utf-8")
        print(f"full report: {report}")


@app.local_entrypoint()
def output_check(allocator: str = "naive_best_fit", report: str = ""):
    """Golden images on T4 with `allocator`, vs the saved output/<stem>.md and vs
    the default allocator on the same GPU."""
    import difflib
    import json
    images = {name: (REPO / name).read_bytes() for name in DIAG_IMAGES}
    runs = {a: ocr_outputs_t4.remote(images, a) for a in (allocator, "default")}
    differs = False

    def compare(name, la, a, lb, b):
        nonlocal differs
        if a == b:
            print(f"  IDENTICAL  {la} == {lb}")
            return
        differs = True
        print(f"  DIFFERS    {la} != {lb}")
        print("".join(difflib.unified_diff((a or "").splitlines(keepends=True),
                                           (b or "").splitlines(keepends=True),
                                           fromfile=f"{name} [{la}]", tofile=f"{name} [{lb}]")))

    print("\n===== OCR output check (T4) =====")
    for a, r in runs.items():
        print(f"[{a}] " + " | ".join(r["log"]))
    for name in DIAG_IMAGES:
        print(name)
        flag_md = runs[allocator]["outputs"].get(name)
        default_md = runs["default"]["outputs"].get(name)
        saved = REPO / "output" / f"{Path(name).stem}.md"
        saved_md = saved.read_text(encoding="utf-8") if saved.exists() else None
        if flag_md is None:
            differs = True
            print(f"  {allocator}: no output")
            continue
        compare(name, allocator, flag_md, "output/ (saved)", saved_md)
        if default_md is None:
            print("  default: no output (hung in every process tried)")
        else:
            compare(name, allocator, flag_md, "default allocator", default_md)
    print("\nRESULT:", "DIFFERENCES FOUND" if differs else "all identical")
    if report:
        Path(report).write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"full report: {report}")


@app.local_entrypoint()
def warm_timing(gpu: str = "L4", n: int = 5, image: str = str(REPO / "kr question 1.png")):
    import statistics
    fn = {"T4": warm_calls_t4, "L4": warm_calls_l4}[gpu]
    path = Path(image)
    r = fn.remote(path.read_bytes(), path.suffix.lower(), n)
    print(f"\n===== warm OCR timing: {gpu} ({r['gpu']}), {path.name} =====")
    print(f"model load {r['load_s']}s | first call {r['first_s']}s | warm calls {r['warm_s']} "
          f"| median {statistics.median(r['warm_s'])}s | chars {r['chars']}")
