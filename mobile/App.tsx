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
import BeaconRegistrationScreen from './src/screens/BeaconRegistrationScreen';
import SignInScreen from './src/screens/SignInScreen';
import CreateAccountScreen from './src/screens/CreateAccountScreen';
import AttentionScreen, { attentionKind } from './src/screens/AttentionScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import BottomNav, { type Tab } from './src/components/BottomNav';
import { initBle } from './src/services/BleService';
import { retryPendingUploads } from './src/services/UploadService';
import { loadPhotos, savePhotos } from './src/services/PhotoStore';
import { loadSession, signOut, type Session } from './src/services/AuthService';
import { colors } from './src/theme';
import type { CapturedPhoto } from './src/types';

const RETRY_INTERVAL_MS = 30000;

// Screens that cover the whole app (no bottom bar).
type Overlay = 'none' | 'gallery' | 'beacons';

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
  const [now, setNow] = useState(Date.now());

  // Sign-in state. `undefined` while the saved session is still loading.
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [authScreen, setAuthScreen] = useState<'signin' | 'create'>('signin');

  const [tab, setTab] = useState<Tab>('capture');
  const [overlay, setOverlay] = useState<Overlay>('none');

  useEffect(() => {
    initBle();
    loadSession().then(setSession);
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
      setNow(Date.now());
    }, RETRY_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [photos, updatePhotoStatus]);

  // Android back button: close a full-screen page, or go back to the Capture tab.
  // (The photo viewer handles its own back button.)
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (overlay === 'beacons') {
        setOverlay('none');
        return true;
      }
      if (overlay === 'none' && session && tab !== 'capture') {
        setTab('capture');
        return true;
      }
      if (session === null && authScreen === 'create') {
        setAuthScreen('signin');
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [overlay, tab, session, authScreen]);

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

  const handleRetry = useCallback(
    (photo: CapturedPhoto) => {
      updatePhotoStatus(photo.id, 'pending');
      retryPendingUploads([{ ...photo, uploadStatus: 'pending' }], updatePhotoStatus);
    },
    [updatePhotoStatus],
  );

  const handleSignOut = useCallback(async () => {
    await signOut();
    setSession(null);
    setAuthScreen('signin');
    setTab('capture');
    setOverlay('none');
  }, []);

  const handleSignedIn = useCallback((s: Session) => {
    setSession(s);
    setTab('capture');
  }, []);

  const last = photos.length > 0 ? photos[photos.length - 1] : null;
  const attentionCount = photos.filter((p) => attentionKind(p, now) !== null).length;

  // ---- Waiting for the saved session to load ----
  if (session === undefined) {
    return <View style={{ flex: 1, backgroundColor: colors.bg }} />;
  }

  // ---- Signed out ----
  if (session === null) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }}>
        <StatusBar barStyle="dark-content" backgroundColor={colors.bg} />
        {authScreen === 'signin' ? (
          <SignInScreen
            onSignedIn={handleSignedIn}
            onCreateAccount={() => setAuthScreen('create')}
          />
        ) : (
          <CreateAccountScreen
            onCreated={handleSignedIn}
            onBack={() => setAuthScreen('signin')}
          />
        )}
      </SafeAreaView>
    );
  }

  // ---- Full-screen pages (no bottom bar) ----
  if (overlay === 'gallery') {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: 'black' }}>
        <StatusBar barStyle="light-content" backgroundColor="black" />
        <GalleryScreen
          photos={photos}
          onClose={() => setOverlay('none')}
          onDelete={handleDelete}
        />
      </SafeAreaView>
    );
  }

  if (overlay === 'beacons') {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: 'white' }}>
        <StatusBar barStyle="light-content" backgroundColor="#1F2E4D" />
        <View style={styles.beaconHeader}>
          <TouchableOpacity
            onPress={() => setOverlay('none')}
            style={styles.backButton}
            accessibilityRole="button"
            accessibilityLabel="Go back"
          >
            <Text style={styles.backText}>‹ Back</Text>
          </TouchableOpacity>
          <Text style={styles.beaconHeaderTitle}>Manage Beacons</Text>
        </View>
        <BeaconRegistrationScreen />
      </SafeAreaView>
    );
  }

  // ---- Main app: current tab + bottom bar ----
  const dark = tab === 'capture';

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: dark ? 'black' : colors.bg }}>
      <StatusBar
        barStyle={dark ? 'light-content' : 'dark-content'}
        backgroundColor={dark ? 'black' : colors.bg}
      />

      <View style={{ flex: 1 }}>
        {tab === 'capture' && (
          <View style={{ flex: 1 }}>
            <CaptureScreen onPhotoCaptured={handlePhotoCaptured} />

            <TouchableOpacity
              style={styles.beaconButton}
              onPress={() => setOverlay('beacons')}
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
              onPress={() => setOverlay('gallery')}
              accessibilityRole="button"
              accessibilityLabel="Open photos"
            >
              {last ? (
                <Image source={{ uri: last.localUri }} style={styles.thumbImage} />
              ) : (
                <View style={[styles.thumbImage, styles.thumbEmpty]} />
              )}
            </TouchableOpacity>
          </View>
        )}

        {tab === 'search' && (
          <View style={{ flex: 1, backgroundColor: 'white' }}>
            <View style={styles.searchTitleWrap}>
              <Text style={styles.searchTitle} accessibilityRole="header">
                Search
              </Text>
              <Text style={styles.searchSubtitle}>Ask about something you photographed.</Text>
            </View>
            <SearchScreen />
          </View>
        )}

        {tab === 'attention' && (
          <AttentionScreen photos={photos} now={now} onRetry={handleRetry} />
        )}

        {tab === 'settings' && (
          <SettingsScreen
            email={session.email}
            onSignOut={handleSignOut}
            onOpenBeacons={() => setOverlay('beacons')}
          />
        )}
      </View>

      <BottomNav tab={tab} onChange={setTab} attentionCount={attentionCount} />
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

  // Thumbnail (bottom-left) sits beside the shutter button from CaptureScreen.
  thumbButton: { position: 'absolute', bottom: 48, left: 32 },
  thumbImage: {
    width: 56,
    height: 56,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: 'white',
  },
  thumbEmpty: { backgroundColor: 'rgba(255,255,255,0.15)' },

  // Search tab title.
  searchTitleWrap: {
    paddingHorizontal: 24,
    paddingTop: (StatusBar.currentHeight ?? 0) + 24,
    paddingBottom: 8,
  },
  searchTitle: { fontSize: 32, fontWeight: '800', color: colors.navy },
  searchSubtitle: { fontSize: 16, color: colors.muted, marginTop: 4 },

  // Back button used on the Manage Beacons page.
  backButton: {
    minHeight: 48,
    minWidth: 48,
    paddingHorizontal: 12,
    justifyContent: 'center',
  },
  backText: { color: 'white', fontSize: 20, fontWeight: '600' },

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
    top: (StatusBar.currentHeight ?? 24) + 16,
    right: 20,
    backgroundColor: 'rgba(0,0,0,0.75)',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 24,
    borderWidth: 1,
    borderColor: 'white',
    minHeight: 48,
    minWidth: 90,
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 10,
    elevation: 10,
  },
  beaconButtonText: { color: 'white', fontSize: 16, fontWeight: '600' },
});
