#!/usr/bin/env python3
"""Fetch the transcript of a YouTube video and save it to a .txt file.

Usage:
    python3 yt_transcript.py <youtube-url-or-id> [-o output.txt] [--lang ko en] [--timestamps]

Examples:
    python3 yt_transcript.py https://www.youtube.com/watch?v=dQw4w9WgXcQ
    python3 yt_transcript.py https://youtu.be/dQw4w9WgXcQ --lang ko --timestamps
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)


def extract_video_id(url: str) -> str:
    """Accept full URLs (watch, youtu.be, shorts, embed) or a bare 11-char ID."""
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname in ("youtu.be",):
        return parsed.path.lstrip("/").split("/")[0]
    if parsed.hostname and "youtube.com" in parsed.hostname:
        if parsed.path == "/watch":
            vid = urllib.parse.parse_qs(parsed.query).get("v", [None])[0]
            if vid:
                return vid
        m = re.match(r"^/(shorts|embed|live)/([A-Za-z0-9_-]{11})", parsed.path)
        if m:
            return m.group(2)
    raise ValueError(f"Could not extract a video ID from: {url}")


def fetch_title(video_id: str) -> str | None:
    """Get the video title via the keyless oEmbed endpoint (best effort)."""
    try:
        oembed = (
            "https://www.youtube.com/oembed?format=json&url="
            + urllib.parse.quote(f"https://www.youtube.com/watch?v={video_id}")
        )
        with urllib.request.urlopen(oembed, timeout=10) as resp:
            return json.load(resp).get("title")
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Save a YouTube video's transcript to a txt file.")
    ap.add_argument("url", help="YouTube URL or video ID")
    ap.add_argument("-o", "--output", help="Output txt path (default: transcript_<id>.txt)")
    ap.add_argument(
        "--lang",
        nargs="+",
        default=["en", "ko"],
        help="Preferred transcript languages in priority order (default: en ko)",
    )
    ap.add_argument("--timestamps", action="store_true", help="Prefix each line with [mm:ss]")
    args = ap.parse_args()

    try:
        video_id = extract_video_id(args.url)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    api = YouTubeTranscriptApi()

    try:
        transcript = api.fetch(video_id, languages=args.lang)
    except NoTranscriptFound:
        # Fall back to whatever language exists (manual first, then generated).
        transcript_list = api.list(video_id)
        available = list(transcript_list)
        if not available:
            print(f"No transcripts exist for {video_id}", file=sys.stderr)
            return 1
        chosen = next((t for t in available if not t.is_generated), available[0])
        print(
            f"Note: none of {args.lang} available; using '{chosen.language_code}'"
            f"{' (auto-generated)' if chosen.is_generated else ''}",
            file=sys.stderr,
        )
        transcript = chosen.fetch()
    except TranscriptsDisabled:
        print(f"Transcripts are disabled for video {video_id}", file=sys.stderr)
        return 1
    except VideoUnavailable:
        print(f"Video {video_id} is unavailable", file=sys.stderr)
        return 1
    except CouldNotRetrieveTranscript as e:  # IpBlocked, RequestBlocked, ...
        print(f"Could not retrieve a transcript for {video_id}: {e}", file=sys.stderr)
        return 1

    lines = []
    for snippet in transcript:
        text = snippet.text.replace("\n", " ").strip()
        if not text:
            continue
        if args.timestamps:
            total = int(snippet.start)
            h, rem = divmod(total, 3600)
            m, s = divmod(rem, 60)
            stamp = f"[{h}:{m:02d}:{s:02d}]" if h else f"[{m:02d}:{s:02d}]"
            lines.append(f"{stamp} {text}")
        else:
            lines.append(text)

    out_path = args.output or f"transcript_{video_id}.txt"
    title = fetch_title(video_id)
    header = []
    if title:
        header.append(f"Title: {title}")
    header.append(f"Video: https://www.youtube.com/watch?v={video_id}")
    header.append(f"Language: {transcript.language_code}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(header) + "\n\n" + "\n".join(lines) + "\n")

    print(f"Saved {len(lines)} lines to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
