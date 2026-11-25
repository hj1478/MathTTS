"""Azure Neural TTS client: credentials, a SpeechConfig, and one checked synthesis.

Stage 4 (tts_full.py), the web backend (backend/job.py) and the listening
scripts all synthesize through this module.

Verified against Azure Speech SDK 1.50.0 docs (2026-07):
  - auth: SpeechConfig(subscription=key, region=...) still supported; MS docs now
    prefer endpoint auth, so AZURE_SPEECH_ENDPOINT is honored when set
  - voices: ko-KR-SunHiNeural / ko-KR-InJoonNeural both current; HD variants
    exist (e.g. "ko-KR-SunHi:DragonHDLatestNeural")
  - SSML: speak_ssml_async(); plain: speak_text_async(); success is
    ResultReason.SynthesizingAudioCompleted, failure details on .cancellation_details

Env (required, never hardcoded). Read from the process environment, else from
the .env file in the repo root (KEY=VALUE lines; real env always wins):
  AZURE_SPEECH_KEY                       resource key
  AZURE_SPEECH_ENDPOINT                  e.g. https://<resource>.cognitiveservices.azure.com
  AZURE_SPEECH_REGION                    alternative to endpoint, e.g. koreacentral
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse


def load_dotenv():
    """Tiny .env loader (no dependency): KEY=VALUE lines, # comments, real env wins."""
    env_file = Path(__file__).resolve().parent.parent / ".env"  # the repo root
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("'\"")
        if k and v and k not in os.environ:
            os.environ[k] = v


def make_config(voice):
    import azure.cognitiveservices.speech as speechsdk
    load_dotenv()
    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION")
    endpoint = os.environ.get("AZURE_SPEECH_ENDPOINT")
    if not key or not (region or endpoint):
        sys.exit(
            "Missing Azure credentials. Either export them:\n"
            "  export AZURE_SPEECH_KEY=<your speech resource key>\n"
            "  export AZURE_SPEECH_ENDPOINT=<https://<resource>.cognitiveservices.azure.com>\n"
            "  (or AZURE_SPEECH_REGION instead of the endpoint)\n"
            "or fill in the .env file in the repo root (AZURE_SPEECH_KEY= is\n"
            "currently blank there). Keys are never hardcoded."
        )
    if endpoint:
        # normalize to scheme://host (tolerates trailing slash or a pasted path)
        p = urlparse(endpoint)
        cfg = speechsdk.SpeechConfig(subscription=key, endpoint=f"{p.scheme}://{p.netloc}")
    else:
        cfg = speechsdk.SpeechConfig(subscription=key, region=region)
    cfg.speech_synthesis_voice_name = voice
    cfg.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm)
    return cfg


def synth(cfg, path, text=None, ssml=None):
    """Synthesize one utterance to path. Returns (ok, detail)."""
    import azure.cognitiveservices.speech as speechsdk
    audio = speechsdk.audio.AudioOutputConfig(filename=str(path))
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=audio)
    result = (synthesizer.speak_ssml_async(ssml) if ssml
              else synthesizer.speak_text_async(text)).get()
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        size = path.stat().st_size if path.exists() else 0
        if size <= 44:  # nothing beyond a bare WAV header = silent failure
            return False, f"reported success but file is empty ({size} B)"
        return True, f"{size:,} B"
    if result.reason == speechsdk.ResultReason.Canceled:
        c = result.cancellation_details
        return False, f"canceled: {c.reason}; {c.error_details or '(no details)'}"
    return False, f"unexpected result: {result.reason}"
