// Core capture flow: live camera preview -> tap to capture -> tag with
// timestamp + nearest beacon -> queue for upload.
//
// Install first: npm install react-native-vision-camera react-native-uuid
// iOS: add NSCameraUsageDescription to Info.plist
// Android: request CAMERA permission at runtime (handled below)

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  PermissionsAndroid,
  Platform,
  Alert,
} from 'react-native';
import {
  Camera,
  useCameraDevice,
  useCameraPermission,
} from 'react-native-vision-camera';
import uuid from 'react-native-uuid';
import { scanForNearestBeacon } from '../services/BleService';
import type { CapturedPhoto } from '../types';

interface Props {
  onPhotoCaptured: (photo: CapturedPhoto) => void;
}

export default function CaptureScreen({ onPhotoCaptured }: Props) {
  const camera = useRef<Camera>(null);
  const device = useCameraDevice('back');
  const { hasPermission, requestPermission } = useCameraPermission();
  const [isCapturing, setIsCapturing] = useState(false);

  useEffect(() => {
    if (!hasPermission) {
      requestPermission();
    }
    if (Platform.OS === 'android') {
      requestAndroidBlePermissions();
    }
  }, [hasPermission, requestPermission]);

  async function requestAndroidBlePermissions() {
    // Android 12+ split Bluetooth into its own runtime permissions; older
    // versions rely on location permission for BLE scanning instead.
    await PermissionsAndroid.requestMultiple([
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
      PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
    ]);
  }

  const handleCapture = useCallback(async () => {
    if (!camera.current || isCapturing) return;
    setIsCapturing(true);

    try {
      const photoFile = await camera.current.takePhoto();
      const beacon = await scanForNearestBeacon();

      const captured: CapturedPhoto = {
        id: uuid.v4() as string,
        localUri: `file://${photoFile.path}`,
        timestamp: new Date().toISOString(),
        beacon,
        uploadStatus: 'pending',
      };

      onPhotoCaptured(captured);
    } catch (err) {
      console.error('Capture failed:', err);
      Alert.alert('Capture failed', 'Please try again.');
    } finally {
      setIsCapturing(false);
    }
  }, [isCapturing, onPhotoCaptured]);

  if (!hasPermission) {
    return (
      <View style={styles.centered}>
        <Text>Camera permission is required to use Waypoint.</Text>
      </View>
    );
  }

  if (!device) {
    return (
      <View style={styles.centered}>
        <Text>No camera device found.</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Camera
        ref={camera}
        style={StyleSheet.absoluteFill}
        device={device}
        isActive={true}
        photo={true}
      />
      <View style={styles.captureBar}>
        <TouchableOpacity
          style={[styles.captureButton, isCapturing && styles.captureButtonDisabled]}
          onPress={handleCapture}
          disabled={isCapturing}
        >
          <View style={styles.captureButtonInner} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: 'black' },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },
  captureBar: {
    position: 'absolute',
    bottom: 40,
    alignSelf: 'center',
  },
  captureButton: {
    width: 72,
    height: 72,
    borderRadius: 36,
    borderWidth: 4,
    borderColor: 'white',
    justifyContent: 'center',
    alignItems: 'center',
  },
  captureButtonDisabled: { opacity: 0.5 },
  captureButtonInner: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: 'white',
  },
});
