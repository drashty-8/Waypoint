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
import { signIn, type Session } from '../services/AuthService';

type Props = {
  onSignedIn: (session: Session) => void;
  onCreateAccount: () => void;
};

export default function SignInScreen({ onSignedIn, onCreateAccount }: Props) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const submit = async () => {
    setMessage(null);
    setBusy(true);
    try {
      onSignedIn(await signIn(email, password));
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not sign in.');
      setBusy(false);
    }
  };

  return (
    <View style={styles.root}>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.brandRow}>
          <View style={styles.logo}>
            <Text style={styles.logoText}>◉</Text>
          </View>
          <Text style={styles.brand}>Waypoint</Text>
        </View>

        <Text style={styles.title} accessibilityRole="header">
          Sign in
        </Text>
        <Text style={styles.subtitle}>See the photos you have taken and ask about them.</Text>

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
          placeholder="Your password"
          placeholderTextColor="#7A8496"
          secureTextEntry
          autoCapitalize="none"
          autoComplete="password"
          accessibilityLabel="Password"
          onSubmitEditing={submit}
        />

        <TouchableOpacity
          style={styles.linkButton}
          onPress={() => setMessage('Password reset is not available yet.')}
          accessibilityRole="button"
        >
          <Text style={styles.link}>Forgot password?</Text>
        </TouchableOpacity>

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
          accessibilityLabel="Sign in"
        >
          {busy ? (
            <ActivityIndicator color="white" />
          ) : (
            <Text style={styles.primaryText}>Sign in</Text>
          )}
        </TouchableOpacity>
        <View style={styles.switchRow}>
          <Text style={styles.switchText}>New to Waypoint?</Text>
          <TouchableOpacity
            onPress={onCreateAccount}
            style={styles.switchButton}
            accessibilityRole="button"
          >
            <Text style={styles.link}>Create account</Text>
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
    paddingTop: (StatusBar.currentHeight ?? 0) + 32,
    paddingBottom: 16,
  },
  brandRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 32 },
  logo: {
    width: 50,
    height: 50,
    borderRadius: 12,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoText: { color: 'white', fontSize: 24 },
  brand: { fontSize: 24, fontWeight: '700', color: colors.navy, marginLeft: 14 },
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
  linkButton: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start' },
  link: { color: colors.primary, fontSize: 15, fontWeight: '700' },
  error: { color: colors.danger, fontSize: 15, marginTop: 8 },
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
