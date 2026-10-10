// Root component. Keeps this minimal for now — a single capture screen
// and an in-memory photo queue. Swap the queue for persisted storage
// (e.g. MMKV or SQLite) before this needs to survive an app restart with
// pending uploads, which you'll want before Phase 1 wraps up.

import React, { useEffect, useState, useCallback } from 'react';
import { SafeAreaView, StatusBar } from 'react-native';
import CaptureScreen from './src/screens/CaptureScreen';
import { initBle } from './src/services/BleService';
import { retryPendingUploads } from './src/services/UploadService';
import type { CapturedPhoto } from './src/types';

const RETRY_INTERVAL_MS = 30000;

export default function App() {
  const [photos, setPhotos] = useState<CapturedPhoto[]>([]);

  useEffect(() => {
    initBle();
  }, []);

  const updatePhotoStatus = useCallback(
    (id: string, status: CapturedPhoto['uploadStatus']) => {
      setPhotos((prev) =>
        prev.map((p) => (p.id === id ? { ...p, uploadStatus: status } : p)),
      );
    },
    [],
  );

  useEffect(() => {
    const interval = setInterval(() => {
      retryPendingUploads(photos, updatePhotoStatus);
    }, RETRY_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [photos, updatePhotoStatus]);

  const handlePhotoCaptured = useCallback(
    (photo: CapturedPhoto) => {
      setPhotos((prev) => [...prev, photo]);
      // Try an immediate upload; if it fails, the retry loop above picks it up.
      retryPendingUploads([photo], updatePhotoStatus);
    },
    [updatePhotoStatus],
  );

  return (
    <SafeAreaView style={{ flex: 1 }}>
      <StatusBar barStyle="light-content" />
      <CaptureScreen onPhotoCaptured={handlePhotoCaptured} />
    </SafeAreaView>
  );
}
