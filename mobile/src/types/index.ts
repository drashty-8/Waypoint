// Shared types for Waypoint's mobile app.
// Keep this in sync with whatever shape the backend's ingest endpoint expects —
// check with the backend owner before changing field names here.

export interface BeaconReading {
  beaconId: string;
  rssi: number;
}

export interface CapturedPhoto {
  id: string; // local UUID, generated on-device at capture time
  localUri: string; // file:// path on the phone before upload
  timestamp: string; // ISO 8601, e.g. new Date().toISOString()
  beacon: BeaconReading | null; // null if no beacon was in range at capture time
  uploadStatus: 'pending' | 'uploading' | 'uploaded' | 'failed';
}
