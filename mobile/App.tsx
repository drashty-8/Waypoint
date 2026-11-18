import React, { useEffect, useState, useCallback } from 'react';
import {
  SafeAreaView,
  StatusBar,
  View,
  Text,
  Image,
  TouchableOpacity,
  StyleSheet,
  BackHandler,
} from 'react-native';
import CaptureScreen from './src/screens/CaptureScreen';
import SearchScreen from './src/screens/SearchScreen';
import GalleryScreen from './src/screens/GalleryScreen';
import { initBle } from './src/services/BleService';
import { retryPendingUploads } from './src/services/UploadService';
import { loadPhotos, savePhotos } from './src/services/PhotoStore';
import type { CapturedPhoto } from './src/types';
import BeaconRegistrationScreen from './src/screens/BeaconRegistrationScreen';

const RETRY_INTERVAL_MS = 30000;

type Screen = 'camera' | 'gallery' | 'search' | 'beacons';

const STATUS_LABELS: Record<CapturedPhoto['uploadStatus'], string> = {
  pending: 'Waiting to upload',
  uploading: 'Uploading...',
  uploaded: 'Uploaded',
  failed: 'Upload failed, will retry',
};

const STATUS_COLORS: Record<CapturedPhoto['uploadStatus'], string> = {
  pending: '#FFA000',
  uploading: '#2979FF',
  uploaded: '#4CAF50',
  failed: '#FF5252',
};

export default function App() {
  const [photos, setPhotos] = useState<CapturedPhoto[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [screen, setScreen] = useState<Screen>('camera');

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

  // On start: load saved photos, then retry any that never finished uploading.
  useEffect(() => {
    loadPhotos().then((saved) => {
      setPhotos(saved);
      setLoaded(true);
      retryPendingUploads(saved, updatePhotoStatus);
    });
  }, [updatePhotoStatus]);

  // Save the list every time it changes (only after the first load, so an
  // empty list never overwrites what was saved).
  useEffect(() => {
    if (loaded) {
      savePhotos(photos);
    }
  }, [photos, loaded]);

  useEffect(() => {
    const interval = setInterval(() => {
      retryPendingUploads(photos, updatePhotoStatus);
    }, RETRY_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [photos, updatePhotoStatus]);

  // Android back button from the search or beacons screen returns to the camera.
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (screen === 'search' || screen === 'beacons') {
        setScreen('camera');
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [screen]);

  const handlePhotoCaptured = useCallback(
    (photo: CapturedPhoto) => {
      setPhotos((prev) => [...prev, photo]);
      retryPendingUploads([photo], updatePhotoStatus);
    },
    [updatePhotoStatus],
  );

  const handleDelete = useCallback((id: string) => {
    setPhotos((prev) => prev.filter((p) => p.id !== id));
  }, []);

  const last = photos.length > 0 ? photos[photos.length - 1] : null;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: 'black' }}>
      <StatusBar barStyle="light-content" />

      {screen === 'camera' && (
        <View style={{ flex: 1 }}>
          <CaptureScreen onPhotoCaptured={handlePhotoCaptured} />

          <TouchableOpacity
            style={styles.beaconButton}
            onPress={() => setScreen('beacons')}
            accessibilityRole="button"
            accessibilityLabel="Manage beacons"
          >
            <Text style={styles.beaconButtonText}>Beacons</Text>
          </TouchableOpacity>

          {last && (
            <View style={styles.statusWrap} pointerEvents="none">
              <View
                style={styles.statusPill}
                accessible
                accessibilityLiveRegion="polite"
                accessibilityLabel={`Last photo: ${STATUS_LABELS[last.uploadStatus]}`}
              >
                <View
                  style={[
                    styles.statusDot,
                    { backgroundColor: STATUS_COLORS[last.uploadStatus] },
                  ]}
                />
                <Text style={styles.statusText}>{STATUS_LABELS[last.uploadStatus]}</Text>
              </View>
            </View>
          )}

          <TouchableOpacity
            style={styles.thumbButton}
            onPress={() => setScreen('gallery')}
            accessibilityRole="button"
            accessibilityLabel="Open photos"
          >
            {last ? (
              <Image source={{ uri: last.localUri }} style={styles.thumbImage} />
            ) : (
              <View style={[styles.thumbImage, styles.thumbEmpty]} />
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.searchButton}
            onPress={() => setScreen('search')}
            accessibilityRole="button"
            accessibilityLabel="Search your photos"
          >
            <Text style={styles.searchButtonText}>Search</Text>
          </TouchableOpacity>
        </View>
      )}

      {screen === 'gallery' && (
        <GalleryScreen
          photos={photos}
          onClose={() => setScreen('camera')}
          onDelete={handleDelete}
        />
      )}

      {screen === 'beacons' && (
        <View style={{ flex: 1, backgroundColor: 'white' }}>
          <View style={styles.beaconHeader}>
            <TouchableOpacity
              onPress={() => setScreen('camera')}
              style={styles.backButton}
              accessibilityRole="button"
              accessibilityLabel="Go back to camera"
            >
              <Text style={styles.backText}>‹ Back</Text>
            </TouchableOpacity>
            <Text style={styles.beaconHeaderTitle}>Manage Beacons</Text>
          </View>
          <BeaconRegistrationScreen />
        </View>
      )}

      {screen === 'search' && (
        <View style={{ flex: 1, backgroundColor: 'white' }}>
          <View style={styles.searchHeader}>
            <TouchableOpacity
              onPress={() => setScreen('camera')}
              style={styles.backButton}
              accessibilityRole="button"
              accessibilityLabel="Go back to camera"
            >
              <Text style={styles.backText}>‹ Back</Text>
            </TouchableOpacity>
            <Text style={styles.searchHeaderTitle}>Search</Text>
          </View>
          <SearchScreen />
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  // Upload status: centered pill just above the shutter button.
  statusWrap: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 128,
    alignItems: 'center',
  },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.75)',
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  statusDot: { width: 10, height: 10, borderRadius: 5, marginRight: 8 },
  statusText: { color: 'white', fontSize: 15, fontWeight: '600' },

  // Bottom row: thumbnail (left), shutter (center, from CaptureScreen), Search (right).
  thumbButton: { position: 'absolute', bottom: 48, left: 32 },
  thumbImage: {
    width: 56,
    height: 56,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: 'white',
  },
  thumbEmpty: { backgroundColor: 'rgba(255,255,255,0.15)' },
  searchButton: {
    position: 'absolute',
    bottom: 52,
    right: 24,
    minHeight: 48,
    minWidth: 88,
    paddingHorizontal: 16,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.75)',
    borderRadius: 24,
    borderWidth: 2,
    borderColor: 'white',
  },
  searchButtonText: { color: 'white', fontSize: 16, fontWeight: '600' },

  // Search screen header.
  searchHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2E4D',
    paddingTop: (StatusBar.currentHeight ?? 0) + 8,
    paddingBottom: 8,
    paddingHorizontal: 8,
  },
  backButton: {
    minHeight: 48,
    minWidth: 48,
    paddingHorizontal: 12,
    justifyContent: 'center',
  },
  backText: { color: 'white', fontSize: 20, fontWeight: '600' },
  searchHeaderTitle: { color: 'white', fontSize: 20, fontWeight: '600', marginLeft: 4 },

  // Beacons screen header and camera-screen button (Tommy's branch).
  beaconHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2E4D',
    paddingTop: (StatusBar.currentHeight ?? 0) + 8,
    paddingBottom: 8,
    paddingHorizontal: 8,
  },
  beaconHeaderTitle: { color: 'white', fontSize: 20, fontWeight: '600', marginLeft: 4 },
  beaconButton: {
    position: 'absolute',
    top: 16,
    right: 20,
    backgroundColor: 'rgba(0,0,0,0.75)',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 24,
    borderWidth: 1,
    borderColor: 'white',
  },
  beaconButtonText: { color: 'white', fontSize: 16, fontWeight: '600' },
});