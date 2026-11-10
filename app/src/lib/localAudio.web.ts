// The MP3 to play, fetched whole into memory (web).
//
// Played straight from the server, Safari on a phone doesn't learn how long
// the MP3 is (the server answers without byte ranges), so the seek bar and the
// reading highlight have nothing to go by. A blob has a known length.
import { useEffect, useState } from 'react';

export interface LocalAudio {
  uri: string | null; // null while it downloads (or when there is no audio)
  seconds: number; // from the size, for when the player reports no duration; 0 if unknown
}

// The service's MP3s are 48 kbit/s, constant (backend/job.py): 6000 bytes a second.
const BYTES_PER_SECOND = 6000;
const NONE: LocalAudio = { uri: null, seconds: 0 };

// Blob URLs made this visit, so going back to a problem doesn't download it
// again. The oldest are dropped (and freed) past KEEP.
const KEEP = 40;
const made = new Map<string, Promise<LocalAudio>>();

function fetchLocal(url: string): Promise<LocalAudio> {
  if (!url.startsWith('http')) return Promise.resolve({ uri: url, seconds: 0 });
  let p = made.get(url);
  if (!p) {
    p = fetch(url)
      .then(async (res) => {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const blob = await res.blob();
        return { uri: URL.createObjectURL(blob), seconds: blob.size / BYTES_PER_SECOND };
      })
      .catch(() => {
        made.delete(url); // try again next time
        return { uri: url, seconds: 0 }; // play it from the server after all
      });
    made.set(url, p);
    if (made.size > KEEP) {
      const [oldest, gone] = made.entries().next().value!;
      made.delete(oldest);
      gone.then((a) => a.uri?.startsWith('blob:') && URL.revokeObjectURL(a.uri));
    }
  }
  return p;
}

/** `url` as something the player can load with a known length. */
export function useLocalAudio(url: string | null): LocalAudio {
  const [got, setGot] = useState<{ url: string; audio: LocalAudio } | null>(null);
  useEffect(() => {
    if (!url) return;
    let gone = false;
    fetchLocal(url).then((audio) => !gone && setGot({ url, audio }));
    return () => {
      gone = true;
    };
  }, [url]);
  return url && got?.url === url ? got.audio : NONE;
}
