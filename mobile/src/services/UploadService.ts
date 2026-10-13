import type { CapturedPhoto } from '../types';

const BACKEND_URL = 'https://waypoint-backend.fly.dev';

/**
 * Uploads one photo to the backend's POST /photos endpoint.
 * Returns true on success, false on failure (the caller retries later).
 */
export async function uploadPhoto(photo: CapturedPhoto): Promise<boolean> {
  try {
    const formData = new FormData();
    formData.append('image', {
      uri: photo.localUri,
      name: `${photo.id}.jpg`,
      type: 'image/jpeg',
    } as any);
    formData.append('captured_at', photo.timestamp);

    // The backend wants all three beacon fields together, or none of them.
    const beacon = photo.beacon;
    if (beacon && beacon.uuid && beacon.major != null && beacon.minor != null) {
      formData.append('beacon_uuid', beacon.uuid);
      formData.append('beacon_major', String(beacon.major));
      formData.append('beacon_minor', String(beacon.minor));
    }

    const response = await fetch(`${BACKEND_URL}/photos`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      console.warn('Upload rejected:', response.status, await response.text());
      return false;
    }

    console.log('Uploaded:', await response.json());
    return true;
  } catch (err) {
    console.warn('Upload failed, will retry later:', err);
    return false;
  }
}

/**
 * Tries to upload any photos still marked 'pending' or 'failed'.
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
