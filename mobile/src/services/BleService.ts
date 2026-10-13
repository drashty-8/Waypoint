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
const SCAN_WINDOW_MS = 5000;

function parseIBeacon(device: Device): BeaconReading | null {
    const manufacturerData = device.manufacturerData;

    if (!manufacturerData || device.rssi == null){
        return null;
        }

    try {

        const binary = globalThis.atob(manufacturerData);

        const bytes = Array.from(binary, char => char.charCodeAt(0));


        //For Debugging
        // console.log(
        //   'DECODED:',
        //   device.name,
        //   bytes.map (b => b.toString(16).padStart(2, '0')).join(' ')
        // );

        if (
            bytes.length < 25 ||
            bytes[0] !== 0x4c ||
            bytes[1] !== 0x00 ||
            bytes[2] !== 0x02 ||
            bytes[3] !== 0x15
            ) {
                return null;
                }
        const uuidBytes = bytes.slice(4, 20);

        const hex = uuidBytes
            .map(byte => byte.toString(16).padStart(2, '0'))
            .join('')
            .toUpperCase();

            const uuid =
            `${hex.slice(0, 8)}-` +
            `${hex.slice(8, 12)}-` +
            `${hex.slice(12, 16)}-` +
            `${hex.slice(16, 20)}-` +
            `${hex.slice(20)}`;

        const major = (bytes[20] << 8) | bytes[21];
        const minor = (bytes[22] << 8) | bytes[23];

        return {
            uuid,
            major,
            minor,
            rssi: device.rssi,
            };
        }catch (error) {
            console.warn('Failed to parseIBeacon:', error);
            return null;
            }
        }

/**
 * Scans for nearby BLE devices for SCAN_WINDOW_MS and returns the one with
 * the strongest (least negative) RSSI, or null if nothing was found.
 *
 * Caller is responsible for having already requested Bluetooth + location
 * permissions — this function assumes they're already granted.
 */
export function scanForNearestBeacon(): Promise<BeaconReading | null> {
  return new Promise((resolve) => {
    let best: BeaconReading | null = null;

    const subscription = bleManager.startDeviceScan(
      null, // null = don't filter by service UUID; narrow this once your beacons have a known UUID
      { allowDuplicates: true },
      (error, device) => {
        if (error) {
          console.warn('BLE scan error:', error.message);
          return;
        }
    if(device){
    //For Debugging
    if (
      device.name === 'room 1' ||
      device.name === 'room 2' ||
      device.name === 'room 3'
    ) {
      console.log('OUR BEACON FULL DATA:', {
        name: device.name,
        id: device.id,
        rssi: device.rssi,
        manufacturerData: device.manufacturerData,
        serviceData: device.serviceData,
        serviceUUIDs: device.serviceUUIDs,
        localName: device.localName,
        txPowerLevel: device.txPowerLevel,
      });
    }

        const beacon = parseIBeacon(device);

        if(!beacon){
            return;
            }

        console.log('iBeacon Found:',
            beacon.uuid,
            'Major:',
            beacon.major,
            'Minor:',
            beacon.minor,
            'RSSI:',
            beacon.rssi
            );

        if (!best || beacon.rssi > best.rssi) {
            best = beacon;
            }
        }
//         if (device && device.rssi != null) {
//           if (!best || device.rssi > best.rssi) {
//             best = { device, rssi: device.rssi };
//           }
//         }
      },
    );

    setTimeout(() => {
      bleManager.stopDeviceScan();
      subscription; // no-op reference; startDeviceScan doesn't return an unsubscribe handle itself

         resolve(best);
//       if (best) {
//         resolve({ beaconId: best.device.id, rssi: best.rssi });
//       } else {
//         resolve(null);
//       }
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
