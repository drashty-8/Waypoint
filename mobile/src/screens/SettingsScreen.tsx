import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Linking,
  ScrollView,
  StatusBar,
  StyleSheet,
} from 'react-native';
import { colors } from '../theme';

type Props = {
  email: string;
  onSignOut: () => void;
  onOpenBeacons: () => void;
};

export default function SettingsScreen({ email, onSignOut, onOpenBeacons }: Props) {
  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title} accessibilityRole="header">
          Settings
        </Text>

        <View style={styles.card}>
          <View style={styles.accountRow}>
            <View style={styles.avatar}>
              <Text style={styles.avatarText}>☺</Text>
            </View>
            <View style={{ flex: 1, marginLeft: 14 }}>
              <Text style={styles.small}>Signed in as</Text>
              <Text style={styles.email} numberOfLines={1}>
                {email}
              </Text>
            </View>
          </View>
          <TouchableOpacity
            style={styles.signOut}
            onPress={onSignOut}
            accessibilityRole="button"
            accessibilityLabel="Sign out"
          >
            <Text style={styles.signOutText}>Sign out</Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity
          style={styles.card}
          onPress={onOpenBeacons}
          accessibilityRole="button"
          accessibilityLabel="Registered beacons"
        >
          <View style={styles.accountRow}>
            <View style={styles.iconCircle}>
              <Text style={styles.iconText}>◉</Text>
            </View>
            <View style={{ flex: 1, marginLeft: 14 }}>
              <Text style={styles.rowTitle}>Registered beacons</Text>
              <Text style={styles.small}>Add and manage rooms</Text>
            </View>
            <Text style={styles.chevron}>›</Text>
          </View>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.card}
          onPress={() => Linking.openSettings()}
          accessibilityRole="button"
          accessibilityLabel="Permissions, opens Android settings"
        >
          <View style={styles.accountRow}>
            <View style={styles.iconCircle}>
              <Text style={styles.iconText}>✓</Text>
            </View>
            <View style={{ flex: 1, marginLeft: 14 }}>
              <Text style={styles.rowTitle}>Permissions</Text>
              <Text style={styles.small}>Camera and nearby devices</Text>
            </View>
            <Text style={styles.chevron}>›</Text>
          </View>
        </TouchableOpacity>
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
  title: { fontSize: 32, fontWeight: '800', color: colors.navy, marginBottom: 20 },
  card: {
    backgroundColor: 'white',
    borderRadius: 18,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    padding: 16,
    marginBottom: 14,
  },
  accountRow: { flexDirection: 'row', alignItems: 'center', minHeight: 48 },
  avatar: {
    width: 50,
    height: 50,
    borderRadius: 25,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { fontSize: 24, color: colors.primary },
  iconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#EEF1F6',
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconText: { fontSize: 18, color: colors.muted },
  small: { fontSize: 14, color: colors.muted },
  email: { fontSize: 18, fontWeight: '700', color: colors.navy },
  rowTitle: { fontSize: 18, fontWeight: '700', color: colors.navy },
  chevron: { fontSize: 28, color: colors.muted, marginLeft: 8 },
  signOut: {
    minHeight: 48,
    marginTop: 14,
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  signOutText: { fontSize: 16, fontWeight: '700', color: colors.navy },
});
