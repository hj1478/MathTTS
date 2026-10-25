// Native only: copy a saved reading's photo and MP3 into the app's documents,
// so history outlives the server's 24 h retention.
import { Directory, File, Paths } from 'expo-file-system';

import type { Reading } from './store';

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
  if (r.audioUrl?.startsWith('http')) {
    try {
      const mp3 = new File(dir, 'audio.mp3');
      if (!mp3.exists) {
        // Android writes straight into the target and can leave half a file
        // if the download breaks; only a finished download gets the real name.
        const part = new File(dir, 'audio.part');
        await File.downloadFileAsync(r.audioUrl, part, { idempotent: true });
        await part.move(mp3, { overwrite: true });
      }
      out.audioUrl = mp3.uri;
    } catch {
      // Keep the remote URL; it is served for 24 h.
    }
  }
  return out;
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
