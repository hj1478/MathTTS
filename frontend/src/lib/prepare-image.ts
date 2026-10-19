import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { Platform } from 'react-native';

import type { UploadImage } from './api';

// The backend takes at most 5 MB and rejects HEIC (docs/API.md, POST /jobs).
// Re-encoding every photo as a JPEG no larger than MAX_SIDE avoids both: a
// phone photo is often 4000+ px and several MB, and iPhones save HEIC.
const MAX_SIDE = 2400;

export async function prepareImage(uri: string, width: number, height: number): Promise<UploadImage> {
  const context = ImageManipulator.manipulate(uri);
  const longest = Math.max(width, height);
  if (longest > MAX_SIDE) {
    context.resize(width >= height ? { width: MAX_SIDE } : { height: MAX_SIDE });
  }
  const rendered = await context.renderAsync();
  const saved = await rendered.saveAsync({ format: SaveFormat.JPEG, compress: 0.85 });
  const image: UploadImage = { uri: saved.uri, name: 'photo.jpg', type: 'image/jpeg' };
  if (Platform.OS === 'web') {
    image.blob = await (await fetch(saved.uri)).blob();
  }
  return image;
}
