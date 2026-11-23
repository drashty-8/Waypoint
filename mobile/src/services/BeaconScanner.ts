import { PermissionsAndroid, Platform } from 'react-native';
import { BleManager } from 'react-native-ble-plx';

export type NearbyBeacon = {
  uuid: string;
  major: number;
  minor: number;
  rssi: number;
};

let manager: BleManager | null = null;
function getManager(): BleManager {
  if (!manager) {
    manager = new BleManager();
  }
  return manager;
}

async function ensurePermissions(): Promise<boolean> {
  if (Platform.OS !== 'android') {
    return true;
  }
  if (typeof Platform.Version === 'number' && Platform.Version >= 31) {
    const result = await PermissionsAndroid.requestMultiple([
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
    ]);
    return Object.values(result).every((r) => r === PermissionsAndroid.RESULTS.GRANTED);
  }
  const result = await PermissionsAndroid.request(
    PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
  );
  return result === PermissionsAndroid.RESULTS.GRANTED;
}

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

function decodeBase64(input: string): number[] {
  const clean = input.replace(/[^A-Za-z0-9+/]/g, '');
  const bytes: number[] = [];
  let buffer = 0;
  let bits = 0;
  for (let i = 0; i < clean.length; i++) {
    buffer = (buffer << 6) | B64.indexOf(clean[i]);
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      bytes.push((buffer >> bits) & 0xff);
    }
  }
  return bytes;
}

function hex(bytes: number[]): string {
  return bytes.map((b) => b.toString(16).padStart(2, '0')).join('').toUpperCase();
}

// iBeacon packet: company id 4C 00, type 02 15, 16-byte UUID, major, minor, power.
function parseIBeacon(manufacturerData: string): Omit<NearbyBeacon, 'rssi'> | null {
  const b = decodeBase64(manufacturerData);
  if (b.length < 25 || b[0] !== 0x4c || b[1] !== 0x00 || b[2] !== 0x02 || b[3] !== 0x15) {
    return null;
  }
  const u = hex(b.slice(4, 20));
  const uuid = `${u.slice(0, 8)}-${u.slice(8, 12)}-${u.slice(12, 16)}-${u.slice(16, 20)}-${u.slice(20)}`;
  return {
    uuid,
    major: (b[20] << 8) | b[21],
    minor: (b[22] << 8) | b[23],
  };
}

// Scans for iBeacons for a few seconds. Returns each beacon once, strongest
// signal first. Throws an Error with a readable message if scanning can't start.
export async function scanNearby(durationMs = 5000): Promise<NearbyBeacon[]> {
  const allowed = await ensurePermissions();
  if (!allowed) {
    throw new Error(
      'Bluetooth permission was not granted. Allow it in Android Settings, Apps, Waypoint, Permissions.',
    );
  }

  const ble = getManager();
  const found = new Map<string, NearbyBeacon>();

  return new Promise<NearbyBeacon[]>((resolve, reject) => {
    const timer = setTimeout(() => {
      ble.stopDeviceScan();
      resolve([...found.values()].sort((a, b) => b.rssi - a.rssi));
    }, durationMs);

    ble.startDeviceScan(null, { allowDuplicates: true }, (error, device) => {
      if (error) {
        clearTimeout(timer);
        ble.stopDeviceScan();
        const text = error.message ?? '';
        reject(
          new Error(
            /off/i.test(text)
              ? 'Bluetooth is off. Turn it on and search again.'
              : `Could not scan: ${text}`,
          ),
        );
        return;
      }
      if (!device || !device.manufacturerData) {
        return;
      }
      const parsed = parseIBeacon(device.manufacturerData);
      if (!parsed) {
        return;
      }
      const rssi = device.rssi ?? -100;
      const key = `${parsed.uuid}/${parsed.major}/${parsed.minor}`;
      const prev = found.get(key);
      if (!prev || rssi > prev.rssi) {
        found.set(key, { ...parsed, rssi });
      }
    });
  });
}
