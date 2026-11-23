import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  BackHandler,
  StatusBar,
  StyleSheet,
} from 'react-native';
import { colors } from '../theme';
import {
  addBeacon,
  loadBeacons,
  sameBeacon,
  type Beacon,
  type BeaconInput,
} from '../services/BeaconStore';
import { scanNearby, type NearbyBeacon } from '../services/BeaconScanner';

type View_ = 'list' | 'register' | 'nearby';

type Props = {
  // Called when the user leaves the beacons pages entirely.
  onExit: () => void;
};

const EMPTY_FORM: BeaconInput = { room: '', uuid: '', major: '', minor: '' };

function shortUuid(uuid: string): string {
  return `${uuid.slice(0, 8)}…`;
}

export default function BeaconsScreen({ onExit }: Props) {
  const [view, setView] = useState<View_>('list');
  const [beacons, setBeacons] = useState<Beacon[]>([]);
  const [form, setForm] = useState<BeaconInput>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [scanning, setScanning] = useState(false);
  const [scanDone, setScanDone] = useState(false);
  const [results, setResults] = useState<NearbyBeacon[]>([]);
  const [scanError, setScanError] = useState<string | null>(null);

  useEffect(() => {
    loadBeacons().then(setBeacons);
  }, []);

  const runScan = useCallback(async () => {
    if (scanning) {
      return;
    }
    setScanning(true);
    setScanDone(false);
    setScanError(null);
    try {
      setResults(await scanNearby(5000));
      setScanDone(true);
    } catch (e) {
      setResults([]);
      setScanError(e instanceof Error ? e.message : 'Could not scan for beacons.');
    } finally {
      setScanning(false);
    }
  }, [scanning]);

  const goBack = useCallback(() => {
    if (view === 'nearby') {
      setView('register');
    } else if (view === 'register') {
      setFormError(null);
      setView('list');
    } else {
      onExit();
    }
  }, [view, onExit]);

  // Android back button steps back one page at a time.
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      goBack();
      return true;
    });
    return () => sub.remove();
  }, [goBack]);

  const registeredName = useCallback(
    (b: NearbyBeacon): string | null => {
      const match = beacons.find((r) => sameBeacon(r, b));
      return match ? match.room : null;
    },
    [beacons],
  );

  // Strongest beacon that is not registered yet.
  const nearest = useMemo(
    () => results.find((r) => registeredName(r) === null) ?? null,
    [results, registeredName],
  );

  const openRegister = () => {
    setForm(EMPTY_FORM);
    setFormError(null);
    setView('register');
    runScan();
  };

  const openNearby = () => {
    setView('nearby');
    runScan();
  };

  const chooseBeacon = (b: NearbyBeacon) => {
    setForm((f) => ({
      ...f,
      uuid: b.uuid,
      major: String(b.major),
      minor: String(b.minor),
    }));
    setFormError(null);
    setView('register');
  };

  const save = async () => {
    setFormError(null);
    setSaving(true);
    try {
      setBeacons(await addBeacon(form));
      setForm(EMPTY_FORM);
      setView('list');
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Could not save the beacon.');
    } finally {
      setSaving(false);
    }
  };

  // ------------------------------------------------------------------ list
  if (view === 'list') {
    return (
      <View style={styles.root}>
        <ScrollView contentContainerStyle={styles.content}>
          <BackLink label="‹ Back" onPress={goBack} />
          <Text style={styles.title} accessibilityRole="header">
            Registered beacons
          </Text>
          <Text style={styles.subtitle}>
            These rooms appear in the room picker when the camera cannot find a beacon.
          </Text>

          {beacons.length === 0 && (
            <Text style={styles.empty}>No beacons registered yet. Tap Add beacon to start.</Text>
          )}

          {beacons.map((b) => (
            <View key={b.id} style={styles.card}>
              <View style={styles.row}>
                <View style={styles.iconCircle}>
                  <Text style={styles.iconText}>◉</Text>
                </View>
                <View style={{ flex: 1, marginLeft: 14 }}>
                  <Text style={styles.cardTitle}>{b.room}</Text>
                  <Text style={styles.small}>
                    Major {b.major}, Minor {b.minor}
                  </Text>
                </View>
              </View>
            </View>
          ))}
        </ScrollView>

        <View style={styles.footer}>
          <TouchableOpacity
            style={styles.primaryButton}
            onPress={openRegister}
            accessibilityRole="button"
            accessibilityLabel="Add beacon"
          >
            <Text style={styles.primaryText}>+  Add beacon</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // -------------------------------------------------------------- register
  if (view === 'register') {
    return (
      <View style={styles.root}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <BackLink label="‹ Back" onPress={goBack} />
          <Text style={styles.title} accessibilityRole="header">
            Register beacon
          </Text>
          <Text style={styles.subtitle}>
            Link a beacon to a room so photos taken nearby are labeled with it.
          </Text>

          {scanning && !nearest && (
            <View style={[styles.card, styles.row]}>
              <ActivityIndicator color={colors.primary} />
              <Text style={[styles.small, { marginLeft: 12 }]}>Looking for beacons nearby…</Text>
            </View>
          )}

          {nearest && (
            <View style={[styles.card, styles.row]}>
              <View style={styles.iconCircleBlue}>
                <Text style={styles.iconTextBlue}>◉</Text>
              </View>
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={styles.small}>Nearest beacon, signal {nearest.rssi} dBm</Text>
                <Text style={styles.mono} numberOfLines={1}>
                  {nearest.uuid}
                </Text>
                <Text style={styles.small}>
                  Major {nearest.major}, Minor {nearest.minor}
                </Text>
              </View>
              <TouchableOpacity
                style={styles.outlineSmall}
                onPress={() => chooseBeacon(nearest)}
                accessibilityRole="button"
                accessibilityLabel="Use the nearest beacon"
              >
                <Text style={styles.outlineSmallText}>Use this</Text>
              </TouchableOpacity>
            </View>
          )}

          <TouchableOpacity
            style={styles.outlineButton}
            onPress={openNearby}
            accessibilityRole="button"
            accessibilityLabel="Search nearby beacons"
          >
            <Text style={styles.outlineText}>⌕  Search nearby beacons</Text>
          </TouchableOpacity>

          <Text style={styles.label}>Room name</Text>
          <TextInput
            style={styles.input}
            value={form.room}
            onChangeText={(room) => setForm((f) => ({ ...f, room }))}
            placeholder="For example, Bedroom"
            placeholderTextColor="#7A8496"
            accessibilityLabel="Room name"
          />

          <Text style={styles.label}>UUID</Text>
          <TextInput
            style={[styles.input, styles.monoInput]}
            value={form.uuid}
            onChangeText={(uuid) => setForm((f) => ({ ...f, uuid }))}
            placeholder="E2C56DB5-DFFB-48D2-B060-D0F5A71096E0"
            placeholderTextColor="#7A8496"
            autoCapitalize="characters"
            autoCorrect={false}
            accessibilityLabel="UUID"
          />

          <View style={styles.twoCol}>
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>Major</Text>
              <TextInput
                style={styles.input}
                value={form.major}
                onChangeText={(major) => setForm((f) => ({ ...f, major }))}
                keyboardType="number-pad"
                placeholder="1"
                placeholderTextColor="#7A8496"
                accessibilityLabel="Major"
              />
            </View>
            <View style={{ width: 14 }} />
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>Minor</Text>
              <TextInput
                style={styles.input}
                value={form.minor}
                onChangeText={(minor) => setForm((f) => ({ ...f, minor }))}
                keyboardType="number-pad"
                placeholder="5"
                placeholderTextColor="#7A8496"
                accessibilityLabel="Minor"
              />
            </View>
          </View>

          <Text style={styles.footnote}>
            A beacon is identified by its UUID, Major and Minor together. Values range from 0 to
            65535.
          </Text>

          {formError && (
            <Text style={styles.error} accessibilityLiveRegion="polite">
              {formError}
            </Text>
          )}
        </ScrollView>

        <View style={styles.footer}>
          <TouchableOpacity
            style={[styles.primaryButton, saving && styles.disabled]}
            onPress={save}
            disabled={saving}
            accessibilityRole="button"
            accessibilityLabel="Save beacon"
          >
            {saving ? (
              <ActivityIndicator color="white" />
            ) : (
              <Text style={styles.primaryText}>Save beacon</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // ---------------------------------------------------------------- nearby
  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={styles.content}>
        <BackLink label="‹ Back" onPress={goBack} />
        <Text style={styles.title} accessibilityRole="header">
          Nearby beacons
        </Text>
        <Text style={styles.subtitle}>
          Choose the beacon to register. Move closer to a beacon to raise its signal.
        </Text>

        <View style={styles.statusRow}>
          <View style={{ flex: 1, paddingRight: 12 }} accessibilityLiveRegion="polite">
            {scanning ? (
              <View style={styles.row}>
                <ActivityIndicator color={colors.primary} />
                <Text style={[styles.statusText, { marginLeft: 10 }]}>Searching…</Text>
              </View>
            ) : scanError ? (
              <Text style={styles.error}>{scanError}</Text>
            ) : scanDone ? (
              <Text style={styles.statusDone}>
                ✓  Search finished, {results.length}{' '}
                {results.length === 1 ? 'beacon' : 'beacons'} found
              </Text>
            ) : null}
          </View>
          <TouchableOpacity
            style={[styles.outlineSmall, scanning && styles.disabled]}
            onPress={runScan}
            disabled={scanning}
            accessibilityRole="button"
            accessibilityLabel="Search again"
          >
            <Text style={styles.outlineSmallText}>↻  Search again</Text>
          </TouchableOpacity>
        </View>

        {results.map((b, index) => {
          const taken = registeredName(b);
          const closest = index === 0;
          return (
            <View
              key={`${b.uuid}/${b.major}/${b.minor}`}
              style={[styles.card, styles.row, closest && styles.cardHighlight]}
            >
              <View style={styles.iconCircle}>
                <Text style={styles.iconText}>◉</Text>
              </View>
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={styles.cardTitle}>
                  Major {b.major}, Minor {b.minor}
                </Text>
                <Text style={styles.small}>
                  UUID {shortUuid(b.uuid)} · {b.rssi} dBm
                </Text>
                {closest && <Text style={styles.closest}>Closest</Text>}
                {taken && <Text style={styles.small}>Already registered as {taken}</Text>}
              </View>
              {!taken && (
                <TouchableOpacity
                  style={closest ? styles.primarySmall : styles.outlineSmall}
                  onPress={() => chooseBeacon(b)}
                  accessibilityRole="button"
                  accessibilityLabel={`Use beacon major ${b.major} minor ${b.minor}`}
                >
                  <Text style={closest ? styles.primarySmallText : styles.outlineSmallText}>
                    Use
                  </Text>
                </TouchableOpacity>
              )}
            </View>
          );
        })}

        {scanDone && results.length === 0 && (
          <Text style={styles.empty}>
            No beacons found. Move closer to a beacon, make sure it is switched on, and search
            again.
          </Text>
        )}

        <Text style={styles.footnote}>
          Beacons are listed from strongest to weakest signal. A beacon registered earlier cannot
          be added twice.
        </Text>
      </ScrollView>
    </View>
  );
}

function BackLink({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <TouchableOpacity
      onPress={onPress}
      style={styles.backButton}
      accessibilityRole="button"
      accessibilityLabel="Go back"
    >
      <Text style={styles.backText}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  content: {
    paddingHorizontal: 24,
    paddingTop: (StatusBar.currentHeight ?? 0) + 8,
    paddingBottom: 24,
  },
  backButton: {
    minHeight: 48,
    minWidth: 48,
    justifyContent: 'center',
    alignSelf: 'flex-start',
    marginBottom: 12,
  },
  backText: { color: colors.muted, fontSize: 18, fontWeight: '600' },
  title: { fontSize: 32, fontWeight: '800', color: colors.navy },
  subtitle: { fontSize: 16, color: colors.muted, marginTop: 8, marginBottom: 20, lineHeight: 22 },
  empty: { fontSize: 16, color: colors.muted, lineHeight: 22, marginVertical: 12 },

  card: {
    backgroundColor: 'white',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    padding: 14,
    marginBottom: 12,
  },
  cardHighlight: { borderColor: colors.primary, borderWidth: 1.5 },
  row: { flexDirection: 'row', alignItems: 'center' },
  cardTitle: { fontSize: 18, fontWeight: '700', color: colors.navy },
  small: { fontSize: 14, color: colors.muted, marginTop: 2 },
  closest: { fontSize: 14, color: colors.primary, fontWeight: '700', marginTop: 2 },
  mono: { fontFamily: 'monospace', fontSize: 13, color: colors.navy, marginVertical: 2 },

  iconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconText: { fontSize: 18, color: colors.primary },
  iconCircleBlue: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconTextBlue: { fontSize: 18, color: colors.primary },

  label: { fontSize: 14, fontWeight: '600', color: colors.navy, marginBottom: 6, marginTop: 6 },
  input: {
    minHeight: 52,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    paddingHorizontal: 14,
    fontSize: 16,
    color: colors.navy,
    backgroundColor: 'white',
    marginBottom: 10,
  },
  monoInput: { fontFamily: 'monospace', fontSize: 14 },
  twoCol: { flexDirection: 'row' },
  footnote: { fontSize: 14, color: colors.muted, lineHeight: 20, marginTop: 6 },
  error: { fontSize: 15, color: colors.danger, marginTop: 10, lineHeight: 21 },

  statusRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 14 },
  statusText: { fontSize: 15, color: colors.muted },
  statusDone: { fontSize: 15, color: '#1B7F3B', fontWeight: '600' },

  footer: { paddingHorizontal: 24, paddingBottom: 24, paddingTop: 8 },
  primaryButton: {
    minHeight: 58,
    borderRadius: 16,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryText: { color: 'white', fontSize: 18, fontWeight: '700' },
  disabled: { opacity: 0.55 },

  outlineButton: {
    minHeight: 52,
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: colors.primary,
    backgroundColor: 'white',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 14,
  },
  outlineText: { color: colors.primary, fontSize: 16, fontWeight: '700' },

  outlineSmall: {
    minHeight: 48,
    minWidth: 72,
    paddingHorizontal: 12,
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: colors.primary,
    backgroundColor: 'white',
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 8,
  },
  outlineSmallText: { color: colors.primary, fontSize: 15, fontWeight: '700' },
  primarySmall: {
    minHeight: 48,
    minWidth: 72,
    paddingHorizontal: 12,
    borderRadius: 14,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 8,
  },
  primarySmallText: { color: 'white', fontSize: 15, fontWeight: '700' },
});
