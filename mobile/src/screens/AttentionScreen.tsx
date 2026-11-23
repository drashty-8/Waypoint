import React from 'react';
import {
  View,
  Text,
  Image,
  TouchableOpacity,
  ScrollView,
  StatusBar,
  StyleSheet,
} from 'react-native';
import { colors } from '../theme';
import type { CapturedPhoto } from '../types';

const STUCK_AFTER_MS = 5 * 60 * 1000;

export type AttentionKind = 'failed' | 'stuck';

// A photo needs attention when its upload failed, or it has been waiting or
// uploading for more than 5 minutes.
export function attentionKind(photo: CapturedPhoto, now: number): AttentionKind | null {
  if (photo.uploadStatus === 'failed') {
    return 'failed';
  }
  if (photo.uploadStatus === 'pending' || photo.uploadStatus === 'uploading') {
    const taken = new Date(photo.timestamp).getTime();
    if (!Number.isNaN(taken) && now - taken > STUCK_AFTER_MS) {
      return 'stuck';
    }
  }
  return null;
}

function stuckLabel(photo: CapturedPhoto, now: number): string {
  const minutes = Math.floor((now - new Date(photo.timestamp).getTime()) / 60000);
  if (minutes >= 60 * 24) {
    return `Stuck for ${Math.floor(minutes / (60 * 24))} d`;
  }
  if (minutes >= 60) {
    return `Stuck for ${Math.floor(minutes / 60)} h`;
  }
  return `Stuck for ${minutes} min`;
}

function formatTime(photo: CapturedPhoto): string {
  const d = new Date(photo.timestamp);
  if (Number.isNaN(d.getTime())) {
    return '';
  }
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

type Props = {
  photos: CapturedPhoto[];
  now: number;
  onRetry: (photo: CapturedPhoto) => void;
};

export default function AttentionScreen({ photos, now, onRetry }: Props) {
  const items = photos
    .map((photo) => ({ photo, kind: attentionKind(photo, now) }))
    .filter((x): x is { photo: CapturedPhoto; kind: AttentionKind } => x.kind !== null)
    .reverse();

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title} accessibilityRole="header">
          Needs attention
        </Text>
        <Text style={styles.subtitle}>
          {items.length === 0
            ? 'Everything is uploaded.'
            : items.length === 1
              ? '1 photo cannot be searched yet.'
              : `${items.length} photos cannot be searched yet.`}
        </Text>

        {items.map(({ photo, kind }) => (
          <View key={photo.id} style={styles.card}>
            <View style={styles.row}>
              <Image source={{ uri: photo.localUri }} style={styles.thumb} />
              <View style={styles.info}>
                <View
                  style={[
                    styles.tag,
                    { backgroundColor: kind === 'failed' ? colors.dangerSoft : colors.warnSoft },
                  ]}
                >
                  <Text
                    style={[
                      styles.tagText,
                      { color: kind === 'failed' ? colors.danger : colors.warn },
                    ]}
                  >
                    {kind === 'failed' ? 'Failed' : stuckLabel(photo, now)}
                  </Text>
                </View>
                <Text style={styles.room}>
                  {photo.beacon ? 'Beacon found' : 'Location unknown'}
                </Text>
                <Text style={styles.time}>{formatTime(photo)}</Text>
              </View>
            </View>
            <TouchableOpacity
              style={styles.retry}
              onPress={() => onRetry(photo)}
              accessibilityRole="button"
              accessibilityLabel={`Retry upload for photo taken ${formatTime(photo)}`}
            >
              <Text style={styles.retryText}>↻  Retry upload</Text>
            </TouchableOpacity>
          </View>
        ))}

        {items.length > 0 && (
          <Text style={styles.footnote}>
            Failed photos and photos stuck for more than 5 minutes appear here. Retrying sends the
            photo to the server again.
          </Text>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  content: {
    paddingHorizontal: 24,
    paddingTop: (StatusBar.currentHeight ?? 0) + 24,
    paddingBottom: 24,
  },
  title: { fontSize: 32, fontWeight: '800', color: colors.navy },
  subtitle: { fontSize: 16, color: colors.muted, marginTop: 6, marginBottom: 20 },
  card: {
    backgroundColor: 'white',
    borderRadius: 18,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    padding: 14,
    marginBottom: 14,
  },
  row: { flexDirection: 'row' },
  thumb: { width: 84, height: 84, borderRadius: 12, backgroundColor: '#DDE2EA' },
  info: { flex: 1, marginLeft: 14, justifyContent: 'center' },
  tag: { alignSelf: 'flex-start', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 3 },
  tagText: { fontSize: 13, fontWeight: '700' },
  room: { fontSize: 18, fontWeight: '700', color: colors.navy, marginTop: 6 },
  time: { fontSize: 15, color: colors.muted, marginTop: 2 },
  retry: {
    minHeight: 48,
    marginTop: 14,
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  retryText: { color: colors.primary, fontSize: 16, fontWeight: '700' },
  footnote: { fontSize: 14, color: colors.muted, lineHeight: 20, marginTop: 6 },
});
