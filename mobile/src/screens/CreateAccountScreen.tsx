import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  ScrollView,
  StatusBar,
  StyleSheet,
} from 'react-native';
import { colors } from '../theme';
import { createAccount, type Session } from '../services/AuthService';

type Props = {
  onCreated: (session: Session) => void;
  onBack: () => void;
};

export default function CreateAccountScreen({ onCreated, onBack }: Props) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const submit = async () => {
    setMessage(null);
    setBusy(true);
    try {
      onCreated(await createAccount(email, password, confirm));
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not create the account.');
      setBusy(false);
    }
  };

  return (
    <View style={styles.root}>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <TouchableOpacity
          onPress={onBack}
          style={styles.backButton}
          accessibilityRole="button"
          accessibilityLabel="Back to sign in"
        >
          <Text style={styles.backText}>‹ Back</Text>
        </TouchableOpacity>

        <Text style={styles.title} accessibilityRole="header">
          Create account
        </Text>
        <Text style={styles.subtitle}>Your photos stay private to your account.</Text>

        <Text style={styles.label}>Email</Text>
        <TextInput
          style={styles.input}
          value={email}
          onChangeText={setEmail}
          placeholder="you@example.com"
          placeholderTextColor="#7A8496"
          keyboardType="email-address"
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="email"
          accessibilityLabel="Email"
        />

        <Text style={styles.label}>Password</Text>
        <TextInput
          style={styles.input}
          value={password}
          onChangeText={setPassword}
          placeholder="At least 8 characters"
          placeholderTextColor="#7A8496"
          secureTextEntry
          autoCapitalize="none"
          accessibilityLabel="Password"
        />

        <Text style={styles.label}>Confirm password</Text>
        <TextInput
          style={styles.input}
          value={confirm}
          onChangeText={setConfirm}
          placeholder="Repeat your password"
          placeholderTextColor="#7A8496"
          secureTextEntry
          autoCapitalize="none"
          accessibilityLabel="Confirm password"
          onSubmitEditing={submit}
        />

        {message && (
          <Text style={styles.error} accessibilityLiveRegion="polite">
            {message}
          </Text>
        )}
      </ScrollView>

      <View style={styles.footer}>
        <TouchableOpacity
          style={[styles.primaryButton, busy && styles.disabled]}
          onPress={submit}
          disabled={busy}
          accessibilityRole="button"
          accessibilityLabel="Create account"
        >
          {busy ? (
            <ActivityIndicator color="white" />
          ) : (
            <Text style={styles.primaryText}>Create account</Text>
          )}
        </TouchableOpacity>
        <View style={styles.switchRow}>
          <Text style={styles.switchText}>Already have an account?</Text>
          <TouchableOpacity onPress={onBack} style={styles.switchButton} accessibilityRole="button">
            <Text style={styles.link}>Sign in</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  content: {
    paddingHorizontal: 24,
    paddingTop: (StatusBar.currentHeight ?? 0) + 8,
    paddingBottom: 16,
  },
  backButton: { minHeight: 48, minWidth: 48, justifyContent: 'center', alignSelf: 'flex-start', marginBottom: 16 },
  backText: { color: colors.muted, fontSize: 18, fontWeight: '600' },
  title: { fontSize: 32, fontWeight: '800', color: colors.navy },
  subtitle: { fontSize: 16, color: colors.muted, marginTop: 8, marginBottom: 28, lineHeight: 22 },
  label: { fontSize: 14, fontWeight: '600', color: colors.navy, marginBottom: 6 },
  input: {
    minHeight: 52,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    paddingHorizontal: 14,
    fontSize: 16,
    color: colors.navy,
    backgroundColor: 'white',
    marginBottom: 18,
  },
  link: { color: colors.primary, fontSize: 15, fontWeight: '700' },
  error: { color: colors.danger, fontSize: 15, marginTop: 4 },
  footer: { paddingHorizontal: 24, paddingBottom: 24 },
  primaryButton: {
    minHeight: 58,
    borderRadius: 16,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  disabled: { opacity: 0.6 },
  primaryText: { color: 'white', fontSize: 18, fontWeight: '700' },
  switchRow: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', marginTop: 10 },
  switchText: { color: colors.muted, fontSize: 15 },
  switchButton: { minHeight: 44, justifyContent: 'center', marginLeft: 8 },
});
