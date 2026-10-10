// Wraps react-native-ble-plx to answer one question at capture time:
// "which beacon is closest right now?" — using nearest-beacon-wins (strongest RSSI),
// per the project's location-tagging decision. No trilateration, no distance math.
//
// Install first: npm install react-native-ble-plx
// iOS: add NSBluetoothAlwaysUsageDescription to Info.plist
// Android: request BLUETOOTH_SCAN, BLUETOOTH_CONNECT, ACCESS_FINE_LOCATION at runtime

import { BleManager, Device } from 'react-native-ble-plx';
import type { BeaconReading } from '../types';

const bleManager = new BleManager();

// How long to scan before picking the best reading. Tune this once you've
// tested real beacons — too short and you might miss the room's beacon,
// too long and capture feels slow.
const SCAN_WINDOW_MS = 2000;

/**
 * Scans for nearby BLE devices for SCAN_WINDOW_MS and returns the one with
 * the strongest (least negative) RSSI, or null if nothing was found.
 *
 * Caller is responsible for having already requested Bluetooth + location
 * permissions — this function assumes they're already granted.
 */
export function scanForNearestBeacon(): Promise<BeaconReading | null> {
  return new Promise((resolve) => {
    let best: { device: Device; rssi: number } | null = null;

    const subscription = bleManager.startDeviceScan(
      null, // null = don't filter by service UUID; narrow this once your beacons have a known UUID
      { allowDuplicates: true },
      (error, device) => {
        if (error) {
          console.warn('BLE scan error:', error.message);
          return;
        }
        if (device && device.rssi != null) {
          if (!best || device.rssi > best.rssi) {
            best = { device, rssi: device.rssi };
          }
        }
      },
    );

    setTimeout(() => {
      bleManager.stopDeviceScan();
      subscription; // no-op reference; startDeviceScan doesn't return an unsubscribe handle itself

      if (best) {
        resolve({ beaconId: best.device.id, rssi: best.rssi });
      } else {
        resolve(null);
      }
    }, SCAN_WINDOW_MS);
  });
}

/**
 * Call once, early in app lifecycle (e.g. in App.tsx), to make sure the
 * BleManager's native module is initialized before the first scan attempt.
 */
export function initBle(): void {
  bleManager.onStateChange((state) => {
    console.log('BLE adapter state:', state);
  }, true);
}
