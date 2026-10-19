import type { UploadImage } from './api';

// The last uploaded image, kept in memory so a job screen can offer "retry"
// without asking for the photo again. Lost on a page refresh; the job screen
// then sends the user back to pick a photo.
let last: UploadImage | null = null;

export function setLastImage(image: UploadImage) {
  last = image;
}

export function getLastImage(): UploadImage | null {
  return last;
}
