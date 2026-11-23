import AsyncStorage from '@react-native-async-storage/async-storage';

// ---------------------------------------------------------------------------
// TEMPORARY sign-in. The backend does not have accounts yet (it uses one
// hardcoded placeholder user), so this only checks the form and remembers the
// email on this phone. It does NOT verify a password and it is NOT secure.
//
// When the backend adds accounts, replace the bodies of signIn() and
// createAccount() with calls to it (for example POST /auth/login and
// POST /auth/signup), keep the returned token in the Session, and send it in
// the Authorization header from UploadService and SearchScreen.
// ---------------------------------------------------------------------------

const SESSION_KEY = 'waypoint.session';

export type Session = { email: string };

export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}

export async function loadSession(): Promise<Session | null> {
  try {
    const raw = await AsyncStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

async function saveSession(session: Session): Promise<Session> {
  await AsyncStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

export async function signIn(email: string, password: string): Promise<Session> {
  if (!isValidEmail(email)) {
    throw new Error('Enter a valid email address.');
  }
  if (password.length === 0) {
    throw new Error('Enter your password.');
  }
  // TODO: call the backend here.
  return saveSession({ email: email.trim().toLowerCase() });
}

export async function createAccount(
  email: string,
  password: string,
  confirm: string,
): Promise<Session> {
  if (!isValidEmail(email)) {
    throw new Error('Enter a valid email address.');
  }
  if (password.length < 8) {
    throw new Error('Password must be at least 8 characters.');
  }
  if (password !== confirm) {
    throw new Error('Passwords do not match.');
  }
  // TODO: call the backend here.
  return saveSession({ email: email.trim().toLowerCase() });
}

export async function signOut(): Promise<void> {
  await AsyncStorage.removeItem(SESSION_KEY);
}
