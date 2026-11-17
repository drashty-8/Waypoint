// Saves the photo list on the phone so it survives closing the app.
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { CapturedPhoto } from '../types';

const STORAGE_KEY = 'waypoint.photos';

export async function loadPhotos(): Promise<CapturedPhoto[]> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return [];

    const saved = JSON.parse(raw) as CapturedPhoto[];

    // An upload that was running when the app closed never finished,
    // so mark it pending and it will be retried.
    return saved.map(
      (p): CapturedPhoto =>
        p.uploadStatus === 'uploading' ? { ...p, uploadStatus: 'pending' } : p,
    );
  } catch (err) {
    console.warn('Could not load saved photos:', err);
    return [];
  }
}

export async function savePhotos(photos: CapturedPhoto[]): Promise<void> {
  try {
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(photos));
  } catch (err) {
    console.warn('Could not save photos:', err);
  }
}
