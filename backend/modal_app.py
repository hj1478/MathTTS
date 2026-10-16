"""MathTTS as a web backend on Modal: image -> every stage's output + a wav.

    modal deploy backend/modal_app.py      # production
    modal serve  backend/modal_app.py      # dev, hot-reloading temporary URL

The pipeline itself is backend/job.py, which calls the existing stage code
unchanged. This file is only the hosting around it:

  Worker (T4)   runs job.run_job on one image. OCR model loaded once per
                container (@modal.enter). Scales to zero after SCALEDOWN_S idle;
                at most MAX_WORKERS containers, so extra jobs queue instead of
                renting more GPUs.
  web (CPU)     FastAPI: POST /jobs, GET /jobs/{id}, GET /audio/{id}.
                Validates the upload and applies the per-IP limit BEFORE a GPU
                job is spawned. Never sees the Azure secret.
  cleanup       hourly: deletes job folders (upload, audio, stage files) and
                job records older than RETENTION_S, and expired rate-limit slots.

State:
  Volume "mathtts-data"   /data/jobs/<id>/  upload.<ext>, ocr/, stitched/, audio.wav
  Dict   "mathtts-jobs"   job:<id> -> status record (what GET /jobs returns)
                          rl:<ip>|<hour>|<n> -> rate-limit slots (see limits.py)

Checked against the Modal Python SDK 1.6.2 (2026-10). Parameter names that
changed from older Modal versions: scaledown_window (was
container_idle_timeout), max_containers (was concurrency_limit),
@modal.concurrent (was allow_concurrent_inputs), add_local_* (was Mount).
"""
import os
import secrets
import shutil
import time
from pathlib import Path

import modal

# local: the repo, for add_local_* sources. In the container the repo files are
# copied to /root, which is already on sys.path.
REPO = Path(__file__).resolve().parent.parent if modal.is_local() else Path("/root")

# Module top level stays light: `modal deploy` imports this file on the laptop,
# and the weight-download build step imports it before backend/ is copied in.
# Pipeline, model and backend.* imports live inside the functions that use them.

# --- config ------------------------------------------------------------------
# Comma-separated browser origins allowed by CORS. Read at deploy/serve time and
# passed to the web container via env=, so this one value is the only setting:
#   MATHTTS_CORS_ORIGINS="https://app.example.com" modal deploy backend/modal_app.py
# Localhost dev servers are always added. Native mobile apps send no Origin and
# are unaffected.
DEV_ORIGINS = ["http://localhost:3000", "http://localhost:5173", "http://localhost:8081",
               "http://127.0.0.1:3000", "http://127.0.0.1:5173"]
CORS_ORIGINS = os.environ.get("MATHTTS_CORS_ORIGINS", "")

RATE_LIMIT_PER_HOUR = 10       # jobs per client IP per clock hour
MAX_WORKERS = 2                # concurrent GPU containers
SCALEDOWN_S = 90               # idle seconds before a worker container stops
# The OCR model runs in a child process (backend/ocr_proc.py). An OCR call
# still running after OCR_CUTOFF_S is a hang: the worker SIGKILLs the child,
# which frees the GPU, and retires the container (FINDINGS.md, 2026-10-16).
# Modal's own function timeout is only a backstop above that: it raises
# InputCancellation in the main thread and cannot stop a hung native call.
OCR_CUTOFF_S = 300
# Paddle's default auto_growth GPU allocator hangs the first OCR call in a fresh
# process most of the time; naive_best_fit went 10/10 on a T4 with identical
# output (PaddleOCR #17693, #17640; FINDINGS.md, 2026-10-16). Set in the OCR
# child's environment before paddle is imported.
OCR_ENV = {"FLAGS_allocator_strategy": "naive_best_fit"}
JOB_TIMEOUT_S = OCR_CUTOFF_S + 120   # + speech (speak.js has its own 120 s limit) + TTS
STARTUP_TIMEOUT_S = 300              # container start + model load in the child
RETENTION_S = 24 * 3600        # uploads, audio and job records
GPU = "T4"
# The image build step that bakes the weights only needs paddle importable with
# a GPU build; keep it on one GPU type so changing GPU doesn't rebuild that layer.
WEIGHTS_BUILD_GPU = "T4"

APP_NAME = "mathtts"
DATA = Path("/data")
JOBS_DIR = DATA / "jobs"

app = modal.App(APP_NAME)
volume = modal.Volume.from_name("mathtts-data", create_if_missing=True)
store = modal.Dict.from_name("mathtts-jobs", create_if_missing=True)
azure = modal.Secret.from_name("azure-speech")  # SPEECH_KEY, SPEECH_REGION

# --- images ------------------------------------------------------------------
PADDLE_GPU_INDEX = "https://www.paddlepaddle.org.cn/packages/stable/cu126/"


def _download_weights():
    """Image build step: fetch the OCR weights into ~/.paddlex so cold starts don't.

    Same constructor arguments as ocr_vl.pipeline(), so it downloads exactly the
    models the worker will load.
    """
    from paddleocr import PaddleOCRVL
    PaddleOCRVL(vl_rec_backend="native", device="gpu",
                use_doc_orientation_classify=False, use_doc_unwarping=False,
                use_seal_recognition=False, use_chart_recognition=False)


worker_base = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("curl", "ca-certificates", "gnupg", "libgl1", "libglib2.0-0",
                 "libgomp1", "libssl3", "libasound2")
    # Node 22 LTS for sre-probe/speak.js (Debian's own nodejs is too old)
    .run_commands("curl -fsSL https://deb.nodesource.com/setup_22.x | bash -",
                  "apt-get install -y nodejs")
    # requirements.txt pins the CPU paddlepaddle==3.3.1; the worker needs the
    # CUDA build of the same version, which is published on Paddle's own index.
    .pip_install("paddlepaddle-gpu==3.3.1", extra_index_url=PADDLE_GPU_INDEX)
    .uv_pip_install("paddleocr==3.7.0", "paddlex[ocr]==3.7.2",
                    "azure-cognitiveservices-speech==1.50.0")
    .run_function(_download_weights, gpu=WEIGHTS_BUILD_GPU)
    # sre-probe dependencies, from the lockfile (temml, speech-rule-engine)
    .add_local_file(REPO / "sre-probe" / "package.json", "/root/sre-probe/package.json", copy=True)
    .add_local_file(REPO / "sre-probe" / "package-lock.json", "/root/sre-probe/package-lock.json",
                    copy=True)
    .run_commands("cd /root/sre-probe && npm ci --omit=dev")
)


def _with_pipeline_source(image):
    """Pipeline source last: editing it doesn't rebuild the layers above.
    Only the stage files job.py runs — never .env (tts_probe would load it)."""
    return (
        image
        .add_local_file(REPO / "sre-probe" / "speak.js", "/root/sre-probe/speak.js")
        .add_local_file(REPO / "normalize.py", "/root/normalize.py")
        .add_local_file(REPO / "ocr_vl.py", "/root/ocr_vl.py")
        .add_local_file(REPO / "tts_probe.py", "/root/tts_probe.py")
        .add_local_file(REPO / "backend" / "job.py", "/root/backend/job.py")
        .add_local_file(REPO / "backend" / "limits.py", "/root/backend/limits.py")
        .add_local_file(REPO / "backend" / "ocr_proc.py", "/root/backend/ocr_proc.py")
    )


worker_image = _with_pipeline_source(worker_base)

web_image = (
    modal.Image.debian_slim(python_version="3.11")
    .uv_pip_install("fastapi[standard]==0.115.12", "pillow==11.2.1")
    .add_local_file(REPO / "backend" / "limits.py", "/root/backend/limits.py")
)

# CPU-only: checks the hard kill on Modal with a fake hanging child (no paddle)
selftest_image = (
    modal.Image.debian_slim(python_version="3.11")
    .add_local_file(REPO / "backend" / "ocr_proc.py", "/root/backend/ocr_proc.py")
    .add_local_file(REPO / "tests" / "fake_ocr_child.py", "/root/tests/fake_ocr_child.py")
)


# --- job records -------------------------------------------------------------
def _key(job_id):
    return f"job:{job_id}"


def _call_key(job_id):
    # its own key: the worker is the only writer of job:<id> once spawned
    return f"call:{job_id}"


def _job_dir(job_id):
    return JOBS_DIR / job_id


def _record_failure(job_id, code, message):
    rec = store.get(_key(job_id)) or {}
    rec.update(status="failed", stage=None, updated=time.time(),
               error={"code": code, "message": message})
    store.put(_key(job_id), rec)


def _retire_container():
    """Take no more inputs: the container exits once the current input returns.

    Used instead of crashing it: Modal reschedules a crashed container's input
    (indefinitely, for a deployed app, whatever retries= says), while an input
    that returns is finished.
    """
    import modal.experimental
    modal.experimental.stop_fetching_inputs()


# --- worker ------------------------------------------------------------------
@app.cls(image=worker_image, gpu=GPU, secrets=[azure], volumes={DATA: volume},
         max_containers=MAX_WORKERS, scaledown_window=SCALEDOWN_S, timeout=JOB_TIMEOUT_S,
         startup_timeout=STARTUP_TIMEOUT_S, retries=0, memory=16384)
class Worker:
    @modal.enter()
    def load(self):
        # tts_probe.make_config reads AZURE_SPEECH_*; the Modal secret is named
        # SPEECH_*. Map once here so the stage code stays unchanged.
        os.environ["AZURE_SPEECH_KEY"] = os.environ.get("SPEECH_KEY", "")
        os.environ["AZURE_SPEECH_REGION"] = os.environ.get("SPEECH_REGION", "")
        os.environ.pop("AZURE_SPEECH_ENDPOINT", None)
        from backend.ocr_proc import OcrProcess
        # the model loads once per container, in the child; killed if loading hangs
        self.ocr = OcrProcess("gpu", env=OCR_ENV)
        self.ocr.start(timeout=STARTUP_TIMEOUT_S - 30)
        print(f"[worker] OCR process ready: {self.ocr.info}", flush=True)

    @modal.exit()
    def unload(self):
        self.ocr.close()

    @modal.method()
    def run(self, job_id, image_bytes, ext):
        from modal.exception import InputCancellation

        from backend import job
        from backend.ocr_proc import OcrTimeout

        def update(**fields):
            rec = store.get(_key(job_id)) or {}
            rec.update(fields, updated=time.time())
            store.put(_key(job_id), rec)

        # Run once. A job that already started reaches here again only if Modal
        # rescheduled it after its container crashed; report that, don't re-run.
        rec = store.get(_key(job_id)) or {}
        if rec.get("started"):
            print(f"[job {job_id}] rescheduled after a crash; not re-running")
            if rec.get("status") != "failed":
                _record_failure(job_id, "worker_lost", job.JOB_ERROR_MESSAGES["worker_lost"])
            return

        workdir = _job_dir(job_id)
        workdir.mkdir(parents=True, exist_ok=True)
        image = workdir / f"upload{ext}"
        image.write_bytes(image_bytes)
        update(status="running", stage="ocr", started=time.time())

        def ocr(img, out_dir, device):  # ocr_vl.run_image, in the killable child
            return self.ocr.run(img, out_dir, timeout=OCR_CUTOFF_S)

        try:
            result = job.run_job(image, workdir, "gpu", ocr=ocr,
                                 on_stage=lambda s: update(stage=s))
        except InputCancellation:  # Modal's backstop timeout, or a cancel
            print(f"[job {job_id}] cancelled; killing OCR and retiring this container")
            self.ocr.kill()
            _record_failure(job_id, "timeout", job.JOB_ERROR_MESSAGES["timeout"])
            _retire_container()
            return
        except job.JobError as e:
            code = "timeout" if isinstance(e.__cause__, OcrTimeout) else e.code
            print(f"[job {job_id}] failed: {code}: {e.detail}")
            update(status="failed", stage=None,
                   error={"code": code, "message": job.JOB_ERROR_MESSAGES[code]})
            if not self.ocr.alive():  # killed at the cutoff, or crashed: no model here now
                _retire_container()
            return
        except Exception as e:
            print(f"[job {job_id}] internal error: {type(e).__name__}: {e}")
            update(status="failed", stage=None,
                   error={"code": "internal_error",
                          "message": job.JOB_ERROR_MESSAGES["internal_error"]})
            return
        finally:
            volume.commit()  # the web container reads audio.wav from the volume

        detail = result["audio"].pop("_detail", "")
        if result["audio"]["status"] != "ready":
            print(f"[job {job_id}] audio {result['audio']['status']}: {detail}")
        update(status="done", stage=None, result=result)


# --- diagnostics ---------------------------------------------------------------
# One-off checks, run before (re)deploying:
#   modal run backend/modal_app.py::selftest       # CPU only: hard kill of a fake hang
#   modal run backend/modal_app.py::fresh_test     # first OCR call in N fresh processes
#       --gpu T4|L4  --allocator naive_best_fit|default  --n 10
#   modal run backend/modal_app.py::output_check   # golden images: OCR text vs output/
#   modal run backend/modal_app.py::stack_check    # native state of a default-allocator hang
#   modal run backend/modal_app.py::cpu_check      # one image, device="cpu" (GPU unused)
# All use the same OcrProcess as the worker. An OCR call still running after
# DIAG_HANG_S is killed with its process group (the child dumps its own stacks
# to the log just before), and the container is retired. retries=0 throughout.
DIAG_HANG_S = 60
DIAG_PARALLEL = 4
DIAG_IMAGES = ["kr question 1.png", "kr question 2.png", "kr question 3.png",
               "kr question 4.png", "kr question 5.png", "page.png"]
DIAG_KW = dict(image=worker_image, memory=16384, retries=0, startup_timeout=STARTUP_TIMEOUT_S,
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


@app.function(gpu="T4", max_containers=DIAG_PARALLEL, **DIAG_KW)
def first_call_t4(i, image_bytes, ext, allocator):
    return _first_call(i, image_bytes, ext, allocator)


@app.function(gpu="L4", max_containers=DIAG_PARALLEL, **DIAG_KW)
def first_call_l4(i, image_bytes, ext, allocator):
    return _first_call(i, image_bytes, ext, allocator)


@app.function(gpu="T4", **DIAG_KW)
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


@app.function(gpu="T4", cpu=8, **DIAG_KW)
def ocr_cpu(image_bytes, name):
    """The same pipeline and settings with device="cpu". On a T4 container only
    because paddlepaddle-gpu cannot even import without the NVIDIA driver
    (libcuda.so.1); the GPU sits unused."""
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


@app.function(gpu="T4", image=worker_image, memory=16384, retries=0,
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


# --- web API -----------------------------------------------------------------
def _origins():
    extra = [o.strip().rstrip("/") for o in CORS_ORIGINS.split(",") if o.strip()]
    return list(dict.fromkeys(extra + DEV_ORIGINS))


@app.function(image=web_image, volumes={DATA: volume},
              env={"MATHTTS_CORS_ORIGINS": CORS_ORIGINS}, scaledown_window=300)
@modal.concurrent(max_inputs=50)
@modal.asgi_app(label=APP_NAME)
def web():
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse

    from backend import limits

    api = FastAPI(title="MathTTS", docs_url=None, redoc_url=None, openapi_url=None)
    api.add_middleware(CORSMiddleware, allow_origins=_origins(),
                       allow_methods=["GET", "POST"], allow_headers=["*"],
                       expose_headers=["Retry-After"])

    def error(status, code, message, headers=None):
        return JSONResponse({"error": {"code": code, "message": message}},
                            status_code=status, headers=headers)

    async def take_slot(ip):
        now = time.time()
        for key in limits.slot_keys(ip, now, RATE_LIMIT_PER_HOUR):
            if await store.put.aio(f"rl:{key}", now, skip_if_exists=True):
                return True, 0
        return False, limits.retry_after(now)

    @api.post("/jobs", status_code=202)
    async def create_job(request: Request):
        # 1. size: refuse on the declared length before reading the body
        # (no length = chunked upload, whose size is unknown until it is all read)
        declared = request.headers.get("content-length", "")
        if not declared.isdigit():
            return error(411, "length_required", "Content-Length 헤더가 필요합니다.")
        if int(declared) > limits.MAX_UPLOAD_BYTES + limits.MULTIPART_SLACK:
            return error(413, "file_too_large", "이미지는 5MB 이하만 올릴 수 있습니다.")
        try:
            form = await request.form(max_files=1, max_fields=1)
        except Exception:
            return error(400, "bad_request", "multipart/form-data 형식의 'image' 필드가 필요합니다.")
        upload = form.get("image")
        if upload is None or not hasattr(upload, "read"):
            return error(400, "bad_request", "multipart/form-data 형식의 'image' 필드가 필요합니다.")
        data = await upload.read(limits.MAX_UPLOAD_BYTES + 1)
        await form.close()
        if len(data) > limits.MAX_UPLOAD_BYTES:
            return error(413, "file_too_large", "이미지는 5MB 이하만 올릴 수 있습니다.")
        if not data:
            return error(400, "empty_file", "빈 파일입니다.")

        # 2. type: the bytes decide, not the declared Content-Type
        ext = limits.sniff_image(data)
        if ext is None:
            if limits.is_heic(data):
                return error(415, "heic_not_supported",
                             "HEIC 사진은 지원하지 않습니다. JPEG 또는 PNG로 저장해 다시 올려 주세요.")
            return error(415, "unsupported_type", "PNG, JPEG, WebP, BMP, TIFF 이미지만 올릴 수 있습니다.")
        reason = limits.check_decodes(data)
        if reason:
            print(f"[upload] rejected undecodable image: {reason}")
            return error(422, "invalid_image", "이미지를 열 수 없습니다. 다른 파일로 다시 시도해 주세요.")

        # 3. per-IP limit, shared across web containers via the Dict
        ip = request.client.host if request.client else "unknown"
        allowed, wait = await take_slot(ip)
        if not allowed:
            return error(429, "rate_limited",
                         f"요청이 너무 많습니다. 한 시간에 {RATE_LIMIT_PER_HOUR}개까지 처리할 수 있습니다.",
                         headers={"Retry-After": str(wait)})

        # 4. only now: a GPU job
        job_id = secrets.token_hex(12)
        now = time.time()
        await store.put.aio(_key(job_id), {"status": "queued", "stage": None,
                                           "created": now, "updated": now})
        call = await Worker().run.spawn.aio(job_id, data, ext)
        await store.put.aio(_call_key(job_id), {"id": call.object_id, "created": now})
        return {"id": job_id, "status": "queued", "status_url": f"/jobs/{job_id}"}

    async def call_ended(job_id):
        """True once the spawned call has finished, by return or by crash
        (out-of-memory, timeout, lost container)."""
        call = await store.get.aio(_call_key(job_id))
        if not call:
            return False  # spawn in flight
        try:
            await modal.FunctionCall.from_id(call["id"]).get.aio(timeout=0)
        except TimeoutError:
            return False  # still queued or running
        except Exception:
            pass
        return True

    @api.get("/jobs/{job_id}")
    async def get_job(job_id: str, request: Request):
        rec = await store.get.aio(_key(job_id)) if job_id.isalnum() else None
        if rec is None:
            return error(404, "not_found", "작업을 찾을 수 없습니다. 24시간이 지나 삭제되었을 수 있습니다.")
        status = rec.get("status")
        if status in ("queued", "running") and await call_ended(job_id):
            # the worker writes its outcome before returning, so re-read first
            rec = await store.get.aio(_key(job_id)) or rec
            status = rec.get("status")
            if status in ("queued", "running"):
                # same wording as job.JOB_ERROR_MESSAGES (job.py is not in this image)
                rec.update(status="failed", stage=None, error={
                    "code": "worker_lost", "message": "처리가 중단되었습니다. 다시 시도해 주세요."})
                await store.put.aio(_key(job_id), rec)
                status = "failed"
        body = {"id": job_id, "status": status, "stage": rec.get("stage"),
                "created_at": int(rec["created"]),
                "expires_at": int(rec["created"] + RETENTION_S)}
        if status == "done":
            result = rec["result"]
            audio = dict(result["audio"])
            url = request.url_for("get_audio", job_id=job_id)
            proto = request.headers.get("x-forwarded-proto")
            if proto:
                url = url.replace(scheme=proto)
            audio["url"] = str(url) if audio["status"] == "ready" else None
            body.update(stages=result["stages"], audio=audio, timings_s=result["timings_s"])
        elif status == "failed":
            body["error"] = rec.get("error")
        return body

    @api.get("/audio/{job_id}", name="get_audio")
    async def get_audio(job_id: str):
        if not job_id.isalnum():
            return error(404, "not_found", "음성 파일이 없습니다.")
        path = _job_dir(job_id) / "audio.wav"
        if not path.exists():
            try:
                await volume.reload.aio()  # the worker committed after this container mounted
            except Exception as e:
                print(f"[audio] volume reload skipped: {type(e).__name__}")
        if not path.exists():
            return error(404, "not_found", "음성 파일이 없습니다. 24시간이 지나 삭제되었을 수 있습니다.")
        return FileResponse(path, media_type="audio/wav", filename=f"mathtts-{job_id}.wav")

    return api


# --- retention -----------------------------------------------------------------
@app.function(image=web_image, volumes={DATA: volume}, schedule=modal.Period(hours=1))
def cleanup():
    from backend import limits

    now = time.time()
    cutoff = now - RETENTION_S
    removed = 0
    if JOBS_DIR.exists():
        for d in JOBS_DIR.iterdir():
            rec = store.get(_key(d.name))
            created = rec["created"] if rec else max(
                (p.stat().st_mtime for p in d.rglob("*")), default=d.stat().st_mtime)
            if created < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        volume.commit()
    current = int(now // 3600)
    stale = []
    for key in store.keys():
        if key.startswith(("job:", "call:")):
            rec = store.get(key)
            if rec and rec.get("created", 0) < cutoff:
                stale.append(key)
        elif key.startswith("rl:"):
            bucket = limits.slot_bucket(key)
            if bucket is not None and bucket < current:
                stale.append(key)
    for key in stale:
        store.pop(key, None)
    print(f"[cleanup] removed {removed} job folder(s), {len(stale)} record(s)")
