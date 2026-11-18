// Wraps react-native-ble-plx to answer one question at capture time:
// "which beacon is closest right now?" — using nearest-beacon-wins (strongest RSSI),
// per the project's location-tagging decision. No trilateration, no distance math.
//
// Install first: npm install react-native-ble-plx
// iOS: add NSBluetoothAlwaysUsageDescription to Info.plist
// Android: request BLUETOOTH_SCAN, BLUETOOTH_CONNECT, ACCESS_FINE_LOCATION at runtime

import { BleManager, Device } from 'react-native-ble-plx';
import type { BeaconReading } from '../types';
import { decode } from 'base-64';

const bleManager = new BleManager();

// How long to scan before picking the best reading. Tune this once you've
// tested real beacons — too short and you might miss the room's beacon,
// too long and capture feels slow.
const SCAN_WINDOW_MS = 10000;

function parseIBeacon(device: Device): BeaconReading | null {

    const manufacturerData = device.manufacturerData;

    if (!manufacturerData || device.rssi == null){
        return null;
        }

    try {

        console.log('Parser entered for device: ', {
          name: device.name,
          localName: device.localName,
          id: device.id,
          manufacturerData,
          atobType: typeof decode === 'function' ? 'function' : typeof decode,
        });

        const binary = decode(manufacturerData);

        const bytes = Array.from(
          binary,
          char => char.charCodeAt(0)
        );

        console.log('Manufacturer data: ', {
          name: device.name,
          localName: device.localName,
          id: device.id,
          rssi: device.rssi,
          length: bytes.length,
          hex: bytes.map(b => b.toString(16).padStart(2, '0')).join(' ')
        });

        console.log('Decoded ble data: ', {
          name: device.name,
          localName: device.localName,
          id: device.id,
          rssi: device.rssi,
          length: bytes.length,
          hex: bytes.map(b => b.toString(16).padStart(2, '0')).join(' ')
    });
        //For Debugging
        // console.log(
        //   'DECODED:',
        //   device.name,
        //   bytes.map (b => b.toString(16).padStart(2, '0')).join(' ')
        // );

       const isAppleIbeacon =
        bytes[0] === 0x4c &&
        bytes[1] === 0x00;

        const isDXBeacon =
        bytes[0] === 0x58 &&
        bytes[1] === 0x44;

        if (
          bytes.length < 25 ||
          (!isAppleIbeacon && !isDXBeacon) || bytes[2] !== 0x02 ||
          bytes[3] !== 0x15
        ){
          return null;
        }

        const uuidBytes = bytes.slice(4, 20);

        // get uuid in standard 8-4-4-4-12 format
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

            //get major minor values
        const major = (bytes[20] << 8) | bytes[21];
        const minor = (bytes[22] << 8) | bytes[23];

        console.log('VALID IBEACON:', {
          uuid,
          major,
          minor,
          rssi: device.rssi,
          deviceId: device.id,
    });

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

        function median(values: number[]): number {
          const sorted = [...values].sort((a, b) => a - b);
          const mid = Math.floor(sorted.length / 2);
          if (sorted.length % 2 === 0) {
            return (sorted[mid - 1] + sorted[mid]) / 2;
          }
          return sorted[mid];
        }
/**
 * Scans for nearby BLE devices for SCAN_WINDOW_MS and returns the one with
 * the strongest (least negative) RSSI, or null if nothing was found.
 *
 * Caller is responsible for having already requested Bluetooth + location
 * permissions — this function assumes they're already granted.
 */
export async function scanForBeacons():
 Promise<BeaconReading []> {

  if(scanInProgress) {
    console.warn('scanForBeacons called while scan already in progress');
    return [];
  }

  scanInProgress = true;

  return new Promise((resolve) => {
    const readings = new Map<
      string,
      {
        beacon: BeaconReading;
        rssiValues: number[];
      }
    >();

    let finished = false;

    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const finish = () => {
      if (finished) return;
      finished = true;

      if (timeoutId !== null) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }

      bleManager.stopDeviceScan();
      scanInProgress = false;

     /*let bestBeacon: BeaconReading | null = null;
      let bestRssi = -Infinity;
      */

      const discovered: BeaconReading [] = [];

      readings.forEach(({ beacon, rssiValues }) => {
        discovered.push({
          ...beacon,
          rssi: median(rssiValues)
        });
      });

      discovered.sort((a, b) => b.rssi - a.rssi);

      console.log('Discovered beacons:', discovered);
      resolve(discovered);
    };

//ble scan

try{
  bleManager.startDeviceScan(
    null,
    { allowDuplicates: true },
    (error, device) => {
      if (finished) return;

      if (error) {
        console.warn('BLE scan error:', error.message);
        finish();
        return;
      }

      if (!device) return;


      const beacon = parseIBeacon(device);
      if (!beacon) return;

      const key = `${beacon.uuid}-${beacon.major}-${beacon.minor}`;

      const existing = readings.get(key);

      if (existing) {
        existing.rssiValues.push(beacon.rssi);
      } else {
        readings.set(key, {
          beacon,
          rssiValues: [beacon.rssi],
        });
      }
    }
  );

  if (!finished) {
    timeoutId = setTimeout(finish, SCAN_WINDOW_MS);
  }
}catch (error) {
  console.warn('Failed to start BLE scan:', error);
  finish();
}
});
}

export async function scanForNearestBeacon(): Promise<BeaconReading | null> {

 /* const beacons = await scanForBeacons();

  return beacons.length > 0 ? beacons[0] : null;
}*/
console.log('CAMERA: Starting scan for nearest beacon...');
  const beacons = await scanForBeacons();

console.log('CAMERA: Scan complete. Found beacons:', beacons);

const nearestBeacon = beacons.length > 0 ? beacons[0] : null;

console.log('CAMERA: Nearest beacon:', nearestBeacon);
  return nearestBeacon;
}
let scanInProgress = false;

export function initBle(): void {
  bleManager.onStateChange((state) => {
    if (state === 'PoweredOn') {
      console.log('Bluetooth is powered on');
    } else {
      console.log('Bluetooth state changed to:', state);
    }
  }, true);
}