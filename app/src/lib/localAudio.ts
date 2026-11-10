// The MP3 to play, as a file on the device (native).
//
// Played straight from the server, a player may not know how long the MP3 is
// (the server answers without byte ranges, and the MP3 has no length header):
// then the seek bar and the reading highlight have nothing to go by. A
// downloaded file has a known length, and plays again without the network.
import { Directory, File, Paths } from 'expo-file-system';
import { useEffect, useState } from 'react';

export interface LocalAudio {
  uri: string | null; // null while it downloads (or when there is no audio)
  seconds: number; // from the file size, for when the player reports no duration; 0 if unknown
}

// The service's MP3s are 48 kbit/s, constant (backend/job.py): 6000 bytes a second.
const BYTES_PER_SECOND = 6000;
const NONE: LocalAudio = { uri: null, seconds: 0 };

async function fetchLocal(url: string): Promise<LocalAudio> {
  if (!url.startsWith('http')) {
    try {
      return { uri: url, seconds: (new File(url).size ?? 0) / BYTES_PER_SECOND }; // a saved reading's own file
    } catch {
      return { uri: url, seconds: 0 };
    }
  }
  try {
    const dir = new Directory(Paths.cache, 'audio');
    dir.create({ intermediates: true, idempotent: true });
    const name = url.replace(/^https?:\/\//, '').replace(/[^A-Za-z0-9]+/g, '_').slice(-96);
    const mp3 = new File(dir, name + '.mp3');
    if (!mp3.exists) {
      // only a finished download gets the real name (as in files.ts)
      const part = new File(dir, name + '.part');
      await File.downloadFileAsync(url, part, { idempotent: true });
      await part.move(mp3, { overwrite: true });
    }
    return { uri: mp3.uri, seconds: (mp3.size ?? 0) / BYTES_PER_SECOND };
  } catch {
    return { uri: url, seconds: 0 }; // play it from the server after all
  }
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
