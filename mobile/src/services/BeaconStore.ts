import AsyncStorage from "@react-native-async-storage/async-storage";
import type { RegisteredBeacon } from "../types/RegisteredBeacon";

const BEACON_STORAGE_KEY = "registeredBeacons";

export async function loadRegisteredBeacons(): Promise<RegisteredBeacon[]> {
  try {
    const json = await AsyncStorage.getItem(BEACON_STORAGE_KEY);
    if (!json) return [];
    return JSON.parse(json) as RegisteredBeacon[];
  } catch (err) {
    console.warn("Failed to load registered beacons:", err);
    return [];
  }
}

export async function saveRegisteredBeacons(
    beacons: RegisteredBeacon[]
): Promise<void> {
  const json = JSON.stringify(beacons);
  await AsyncStorage.setItem(BEACON_STORAGE_KEY, json);
}

export async function registerBeacon(beacon: RegisteredBeacon): Promise<void> {
  const beacons = await loadRegisteredBeacons();

  const existingIndex = beacons.findIndex(
    (b) =>
      b.uuid.toUpperCase() === beacon.uuid.toUpperCase() &&
      b.major === beacon.major &&
      b.minor === beacon.minor
  );

  if(existingIndex !== -1) {
    // Update existing beacon
    beacons[existingIndex] = beacon;
  } else {
    // Add new beacon
    beacons.push(beacon);
  }

  await saveRegisteredBeacons(beacons);
}




export async function removeBeacon(
    uuid: string,
    major: number,
    minor: number
): Promise<void> {
    const beacons = await loadRegisteredBeacons();

    const updatedBeacons = beacons.filter(
        (b) =>
            !(
                b.uuid.toUpperCase() === uuid.toUpperCase() &&
                b.major === major &&
                b.minor === minor
            )
    );

    await saveRegisteredBeacons(updatedBeacons);
}
