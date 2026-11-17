import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  Image,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  useWindowDimensions,
  BackHandler,
  Alert,
} from 'react-native';
import type { CapturedPhoto } from '../types';

interface Props {
  photos: CapturedPhoto[];
  onClose: () => void;
  onDelete: (id: string) => void;
}

const COLUMNS = 3;
const GAP = 2;

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

interface ViewerProps {
  photos: CapturedPhoto[];
  startIndex: number;
  onBack: () => void;
  onDelete: (id: string) => void;
}

function Viewer({ photos, startIndex, onBack, onDelete }: ViewerProps) {
  const { width } = useWindowDimensions();
  const [index, setIndex] = useState(startIndex);
  const current = photos[index];

  function confirmDelete() {
    Alert.alert(
      'Delete photo?',
      'This removes it from the app. If it was already uploaded, the copy on the server stays.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete', style: 'destructive', onPress: () => onDelete(current.id) },
      ],
    );
  }

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <TouchableOpacity onPress={onBack} style={styles.backButton}>
          <Text style={styles.backText}>‹</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>
          {index + 1} of {photos.length}
        </Text>
      </View>

      <FlatList
        style={{ flex: 1 }}
        horizontal
        pagingEnabled
        data={photos}
        keyExtractor={(p) => p.id}
        initialScrollIndex={startIndex}
        getItemLayout={(_, i) => ({ length: width, offset: width * i, index: i })}
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={(e) =>
          setIndex(Math.round(e.nativeEvent.contentOffset.x / width))
        }
        renderItem={({ item }) => (
          <View style={{ width, justifyContent: 'center' }}>
            <Image
              source={{ uri: item.localUri }}
              style={{ width, height: '100%' }}
              resizeMode="contain"
            />
          </View>
        )}
      />

      {current && (
        <View style={styles.infoBar}>
          <View style={{ flex: 1 }}>
            <Text style={styles.infoTime}>
              {new Date(current.timestamp).toLocaleString()}
            </Text>
            <Text style={styles.infoMeta}>
              {current.beacon ? 'Beacon found' : 'No beacon found'}
            </Text>
            <Text style={[styles.infoStatus, { color: STATUS_COLORS[current.uploadStatus] }]}>
              {STATUS_LABELS[current.uploadStatus]}
            </Text>
          </View>
          <TouchableOpacity style={styles.deleteButton} onPress={confirmDelete}>
            <Text style={styles.deleteText}>Delete</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

export default function GalleryScreen({ photos, onClose, onDelete }: Props) {
  const { width } = useWindowDimensions();
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);

  // Newest first, like a normal gallery.
  const sorted = [...photos].reverse();
  const cell = (width - GAP * (COLUMNS - 1)) / COLUMNS;

  // Android back button: close the full-screen view first, then the gallery.
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (viewerIndex !== null) {
        setViewerIndex(null);
      } else {
        onClose();
      }
      return true;
    });
    return () => sub.remove();
  }, [viewerIndex, onClose]);

  if (viewerIndex !== null && sorted.length > 0) {
    return (
      <Viewer
        photos={sorted}
        startIndex={Math.min(viewerIndex, sorted.length - 1)}
        onBack={() => setViewerIndex(null)}
        onDelete={(id) => {
          setViewerIndex(null);
          onDelete(id);
        }}
      />
    );
  }

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <TouchableOpacity onPress={onClose} style={styles.backButton}>
          <Text style={styles.backText}>‹</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Photos</Text>
      </View>

      {sorted.length === 0 ? (
        <View style={styles.empty}>
          <Text style={styles.emptyText}>No photos yet. Take one with the camera.</Text>
        </View>
      ) : (
        <FlatList
          data={sorted}
          numColumns={COLUMNS}
          keyExtractor={(p) => p.id}
          renderItem={({ item, index }) => (
            <TouchableOpacity
              activeOpacity={0.8}
              onPress={() => setViewerIndex(index)}
              style={{
                width: cell,
                height: cell,
                marginRight: index % COLUMNS === COLUMNS - 1 ? 0 : GAP,
                marginBottom: GAP,
              }}
            >
              <Image
                source={{ uri: item.localUri }}
                style={{ width: '100%', height: '100%', backgroundColor: '#222' }}
              />
              {item.uploadStatus !== 'uploaded' && (
                <View
                  style={[styles.dot, { backgroundColor: STATUS_COLORS[item.uploadStatus] }]}
                />
              )}
            </TouchableOpacity>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: 'black' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    paddingHorizontal: 8,
  },
  backButton: { paddingHorizontal: 14, paddingVertical: 2 },
  backText: { color: 'white', fontSize: 34, lineHeight: 38 },
  headerTitle: { color: 'white', fontSize: 20, fontWeight: '600', marginLeft: 4 },
  empty: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },
  emptyText: { color: '#aaa', fontSize: 16, textAlign: 'center' },
  dot: {
    position: 'absolute',
    top: 6,
    right: 6,
    width: 12,
    height: 12,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: 'white',
  },
  infoBar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#111',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  infoTime: { color: 'white', fontSize: 15, fontWeight: '600' },
  infoMeta: { color: '#bbb', fontSize: 13, marginTop: 2 },
  infoStatus: { fontSize: 13, fontWeight: '600', marginTop: 2 },
  deleteButton: {
    backgroundColor: '#3A1D1D',
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  deleteText: { color: '#FF8A80', fontSize: 15, fontWeight: '600' },
});
