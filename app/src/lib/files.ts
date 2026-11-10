// Native only: copy a saved reading's photo and MP3 into the app's documents,
// so history outlives the server's 24 h retention.
import { Directory, File, Paths } from 'expo-file-system';

import type { Reading, Spoken } from './store';

/**
 * A stored file URI under this install's folders. iOS moves the app's
 * container on every update (…/Application/<new id>/…), so the part up to
 * Documents/ or Library/Caches/ is replaced with where those are now.
 */
export function relocate(uri: string): string {
  if (!uri.startsWith('file:')) return uri;
  for (const [marker, root] of [
    ['/Documents/', Paths.document.uri],
    ['/Library/Caches/', Paths.cache.uri],
  ] as const) {
    const at = uri.indexOf(marker);
    if (at >= 0 && root.includes(marker.slice(0, -1))) return root.replace(/\/?$/, '/') + uri.slice(at + marker.length);
  }
  return uri;
}

function dirFor(id: string) {
  return new Directory(Paths.document, 'history', id);
}

export async function keepFiles(r: Reading): Promise<Reading> {
  const dir = dirFor(r.id);
  dir.create({ intermediates: true, idempotent: true });
  const out = { ...r };
  try {
    const img = new File(dir, 'photo.jpg');
    if (!img.exists) await new File(r.imageUri).copy(img);
    out.imageUri = img.uri;
  } catch {
    // Keep the cache URI; it still works until the OS clears the cache.
  }
  Object.assign(out, await keptAudio(dir, 'audio', r));
  if (r.problems) {
    out.problems = [];
    for (const [i, p] of r.problems.entries()) out.problems.push({ ...p, ...(await keptAudio(dir, `audio-${i + 1}`, p)) });
  }
  return out;
}

type Kept = Pick<Reading, 'audioUrl' | 'audioStatus'>;

/** The audio fields after keepAudio (the formal reading's too): a local MP3 that is gone is no audio, not 'ready'. */
async function keptAudio(dir: Directory, name: string, x: Kept & { formal?: Spoken }) {
  const one = async (file: string, a: Kept) => {
    const audioUrl = await keepAudio(dir, file, a.audioUrl);
    return { audioUrl, audioStatus: a.audioStatus === 'ready' && !audioUrl ? ('expired' as const) : a.audioStatus };
  };
  return { ...(await one(name, x)), formal: x.formal && { ...x.formal, ...(await one(name + '-formal', x.formal)) } };
}

/** The on-device copy of a remote MP3, or `url` unchanged if it can't be made;
 * null for a local file that no longer exists. */
async function keepAudio(dir: Directory, name: string, url: string | null): Promise<string | null> {
  if (!url) return null;
  if (!url.startsWith('http')) {
    try {
      return new File(url).exists ? url : null;
    } catch {
      return null;
    }
  }
  try {
    const mp3 = new File(dir, name + '.mp3');
    if (!mp3.exists) {
      // Android writes straight into the target and can leave half a file
      // if the download breaks; only a finished download gets the real name.
      const part = new File(dir, name + '.part');
      await File.downloadFileAsync(url, part, { idempotent: true });
      await part.move(mp3, { overwrite: true });
    }
    return mp3.uri;
  } catch {
    return url; // the remote URL is served for 24 h
  }
}

export function dropFiles(r: Reading): void {
  try {
    const dir = dirFor(r.id);
    if (dir.exists) dir.delete();
  } catch {
    // Nothing to clean up.
  }
}

/** Delete every history/<id> folder whose id isn't in `keep`. */
export function dropFilesExcept(keep: Set<string>): void {
  try {
    const root = new Directory(Paths.document, 'history');
    if (!root.exists) return;
    for (const d of root.list()) if (d instanceof Directory && !keep.has(d.name)) d.delete();
  } catch {
    // Leave them for next time.
  }
}
