// Handles sending a captured photo to the backend's ingest endpoint.
// Photos that fail to upload (weak network, backend down) stay queued
// locally and retry automatically — this maps to the "reliable capture
// under weak network" user story.

import type { CapturedPhoto } from '../types';

// TODO: point this at the real backend once the ingest endpoint exists.
// Use your machine's local network IP (not localhost) when testing from
// a physical phone against a backend running on your laptop.
const INGEST_URL = 'http://REPLACE_WITH_BACKEND_IP:8000/ingest';

/**
 * Attempts to upload one photo. Returns true on success, false on failure
 * (caller should leave the photo's status as 'pending' and retry later).
 */
export async function uploadPhoto(photo: CapturedPhoto): Promise<boolean> {
  try {
    const formData = new FormData();
    formData.append('photo', {
      uri: photo.localUri,
      name: `${photo.id}.jpg`,
      type: 'image/jpeg',
    } as any);
    formData.append('timestamp', photo.timestamp);
    if (photo.beacon) {
      formData.append('beaconId', photo.beacon.beaconId);
      formData.append('rssi', String(photo.beacon.rssi));
    }

    const response = await fetch(INGEST_URL, {
      method: 'POST',
      body: formData,
      headers: { 'Content-Type': 'multipart/form-data' },
    });

    return response.ok;
  } catch (err) {
    console.warn('Upload failed, will retry later:', err);
    return false;
  }
}

/**
 * Walks a list of photos and attempts to upload any still marked 'pending'
 * or 'failed'. Call this on app foreground and periodically (e.g. every
 * 30s) while there's a pending queue — wire it up wherever you're keeping
 * photo state (Context, Redux, Zustand, etc.).
 */
export async function retryPendingUploads(
  photos: CapturedPhoto[],
  onStatusChange: (id: string, status: CapturedPhoto['uploadStatus']) => void,
): Promise<void> {
  const pending = photos.filter(
    (p) => p.uploadStatus === 'pending' || p.uploadStatus === 'failed',
  );

  for (const photo of pending) {
    onStatusChange(photo.id, 'uploading');
    const success = await uploadPhoto(photo);
    onStatusChange(photo.id, success ? 'uploaded' : 'failed');
  }
}
