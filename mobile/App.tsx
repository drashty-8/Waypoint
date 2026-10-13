import React, { useEffect, useState, useCallback } from 'react';
import { SafeAreaView, StatusBar, View, Text, Image, StyleSheet } from 'react-native';
import CaptureScreen from './src/screens/CaptureScreen';
import { initBle } from './src/services/BleService';
import { retryPendingUploads } from './src/services/UploadService';
import type { CapturedPhoto } from './src/types';

const RETRY_INTERVAL_MS = 30000;

const STATUS_LABELS: Record<CapturedPhoto['uploadStatus'], string> = {
  pending: 'Waiting to upload',
  uploading: 'Uploading...',
  uploaded: 'Uploaded to backend',
  failed: 'Upload failed, will retry',
};

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
      retryPendingUploads([photo], updatePhotoStatus);
    },
    [updatePhotoStatus],
  );

  const last = photos.length > 0 ? photos[photos.length - 1] : null;

  return (
    <SafeAreaView style={{ flex: 1 }}>
      <StatusBar barStyle="light-content" />
      <View style={{ flex: 1 }}>
        <CaptureScreen onPhotoCaptured={handlePhotoCaptured} />
        {last && (
          <View style={styles.preview}>
            <Image source={{ uri: last.localUri }} style={styles.thumb} />
            <View style={styles.info}>
              <Text style={styles.line}>Photos taken: {photos.length}</Text>
              <Text style={styles.line}>
                Time: {new Date(last.timestamp).toLocaleTimeString()}
              </Text>
              <Text style={styles.line}>
                Location: {last.beacon ? last.beacon.beaconId : 'No beacon found'}
              </Text>
              <Text style={styles.line}>{STATUS_LABELS[last.uploadStatus]}</Text>
            </View>
          </View>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  preview: {
    position: 'absolute',
    top: 16,
    left: 16,
    right: 16,
    flexDirection: 'row',
    backgroundColor: 'rgba(0,0,0,0.65)',
    borderRadius: 12,
    padding: 10,
  },
  thumb: { width: 80, height: 100, borderRadius: 8, marginRight: 12 },
  info: { flex: 1, justifyContent: 'center' },
  line: { color: 'white', fontSize: 14, marginVertical: 1 },
});
