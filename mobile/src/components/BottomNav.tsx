import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { colors } from '../theme';

export type Tab = 'capture' | 'search' | 'attention' | 'settings';

const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: 'capture', label: 'Capture', icon: '◎' },
  { key: 'search', label: 'Search', icon: '⌕' },
  { key: 'attention', label: 'Attention', icon: '⚠' },
  { key: 'settings', label: 'Settings', icon: '⚙' },
];

type Props = {
  tab: Tab;
  onChange: (tab: Tab) => void;
  attentionCount: number;
};

export default function BottomNav({ tab, onChange, attentionCount }: Props) {
  return (
    <View style={styles.bar} accessibilityRole="tablist">
      {TABS.map((t) => {
        const selected = t.key === tab;
        const badge = t.key === 'attention' && attentionCount > 0;
        return (
          <TouchableOpacity
            key={t.key}
            style={styles.item}
            onPress={() => onChange(t.key)}
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            accessibilityLabel={
              badge ? `${t.label}, ${attentionCount} need attention` : t.label
            }
          >
            <View style={[styles.pill, selected && styles.pillSelected]}>
              <Text style={[styles.icon, selected && styles.iconSelected]}>{t.icon}</Text>
              {badge && (
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>
                    {attentionCount > 9 ? '9+' : attentionCount}
                  </Text>
                </View>
              )}
            </View>
            <Text style={[styles.label, selected && styles.labelSelected]}>{t.label}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    backgroundColor: 'white',
    borderTopWidth: 1,
    borderTopColor: colors.cardBorder,
    paddingTop: 8,
    paddingBottom: 12,
  },
  item: { flex: 1, alignItems: 'center', minHeight: 56 },
  pill: {
    minWidth: 56,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pillSelected: { backgroundColor: colors.primarySoft },
  icon: { fontSize: 20, color: colors.muted },
  iconSelected: { color: colors.primary },
  label: { fontSize: 12, marginTop: 2, color: colors.muted, fontWeight: '500' },
  labelSelected: { color: colors.navy, fontWeight: '700' },
  badge: {
    position: 'absolute',
    top: -4,
    right: 6,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    paddingHorizontal: 4,
    backgroundColor: colors.badge,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: { color: 'white', fontSize: 11, fontWeight: '700' },
});
