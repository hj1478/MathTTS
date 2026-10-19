// Picking, rotating and cropping the photo before upload.
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import * as ImagePicker from 'expo-image-picker';
import { Platform } from 'react-native';

import type { Picked } from './store';

export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024; // backend/limits.py
const MAX_SIDE = 2400; // plenty for OCR; keeps phone photos well under 5 MB

/** Why a chosen file can't be used; shown as a banner on the home screen. */
export type PickProblem =
  | { kind: 'not_image'; name: string }
  | { kind: 'too_large'; size: number }
  | { kind: 'denied' };

export type PickResult = { picked: Picked } | { problem: PickProblem } | null;

function fromAsset(a: ImagePicker.ImagePickerAsset): PickResult {
  const name = a.fileName ?? a.file?.name ?? 'photo.jpg';
  const mime = a.mimeType ?? a.file?.type ?? 'image/jpeg';
  if (!mime.startsWith('image/')) return { problem: { kind: 'not_image', name } };
  return {
    picked: {
      uri: a.uri,
      width: a.width,
      height: a.height,
      mimeType: mime,
      name,
      size: a.fileSize ?? a.file?.size,
    },
  };
}

/**
 * Web: a plain file input, so a wrong file type comes back as a PickProblem
 * (expo-image-picker throws an uncaught error for non-images on web).
 */
function pickWebFile(camera: boolean): Promise<PickResult> {
  return new Promise((resolve) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    if (camera) input.setAttribute('capture', 'environment');
    input.onchange = async () => {
      const f = input.files?.[0];
      resolve(f ? await fromFile(f) : null);
    };
    input.oncancel = () => resolve(null);
    input.click();
  });
}

export async function pickPhoto(source: 'camera' | 'library'): Promise<PickResult> {
  if (Platform.OS === 'web') return pickWebFile(source === 'camera');
  if (source === 'camera') {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) return { problem: { kind: 'denied' } };
  }
  const opts: ImagePicker.ImagePickerOptions = { mediaTypes: 'images', quality: 1 };
  const res =
    source === 'camera'
      ? await ImagePicker.launchCameraAsync(opts)
      : await ImagePicker.launchImageLibraryAsync(opts);
  if (res.canceled || !res.assets?.length) return null;
  return fromAsset(res.assets[0]);
}

/** A file dropped on the desktop drop zone (web only). */
export async function fromFile(file: File): Promise<PickResult> {
  if (!file.type.startsWith('image/')) return { problem: { kind: 'not_image', name: file.name } };
  const uri = URL.createObjectURL(file);
  const size = await new Promise<{ w: number; h: number }>((resolve) => {
    const img = new window.Image();
    img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight });
    img.onerror = () => resolve({ w: 0, h: 0 });
    img.src = uri;
  });
  return {
    picked: { uri, width: size.w, height: size.h, mimeType: file.type, name: file.name, size: file.size },
  };
}

async function render(ctx: ReturnType<typeof ImageManipulator.manipulate>, name: string): Promise<Picked> {
  const ref = await ctx.renderAsync();
  const web = Platform.OS === 'web';
  const out = await ref.saveAsync({ format: SaveFormat.JPEG, compress: 0.9, base64: web });
  // On web a data URL survives reloads, so history can keep it.
  const uri = web && out.base64 ? 'data:image/jpeg;base64,' + out.base64 : out.uri;
  const size = web && out.base64 ? Math.floor((out.base64.length * 3) / 4) : undefined;
  return { uri, width: out.width, height: out.height, mimeType: 'image/jpeg', name: name.replace(/\.\w+$/, '') + '.jpg', size };
}

export async function rotate90(p: Picked): Promise<Picked> {
  return render(ImageManipulator.manipulate(p.uri).rotate(90), p.name);
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Crop (in image pixels) and shrink to MAX_SIDE, re-encoded as JPEG. */
export async function prepareUpload(p: Picked, r: Rect | null): Promise<Picked> {
  const ctx = ImageManipulator.manipulate(p.uri);
  let w = p.width;
  let h = p.height;
  if (r && (r.x > 0 || r.y > 0 || r.w < p.width || r.h < p.height)) {
    ctx.crop({ originX: Math.round(r.x), originY: Math.round(r.y), width: Math.round(r.w), height: Math.round(r.h) });
    w = r.w;
    h = r.h;
  }
  if (Math.max(w, h) > MAX_SIDE) ctx.resize(w >= h ? { width: MAX_SIDE } : { height: MAX_SIDE });
  return render(ctx, p.name);
}
