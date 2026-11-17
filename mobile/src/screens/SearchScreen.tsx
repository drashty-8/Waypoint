import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  Image,
  ActivityIndicator,
  StyleSheet,
  Keyboard,
} from 'react-native';

const BACKEND_URL = 'https://waypoint-backend.fly.dev';

type QueryResult =
  | { matched: false; message: string }
  | {
      matched: true;
      answer: string;
      image_url: string;
      description: string;
      room_name: string;
      captured_at: string;
    };

export default function SearchScreen() {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch() {
    const trimmed = question.trim();
    if (trimmed === '' || loading) return;

    Keyboard.dismiss();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`${BACKEND_URL}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmed }),
      });

      if (!response.ok) {
        setError(`The server returned an error (${response.status}). Please try again.`);
        return;
      }

      setResult((await response.json()) as QueryResult);
    } catch (err) {
      setError('Could not reach the server. Check your internet connection and try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <Text style={styles.title}>Ask about your photos</Text>

      <TextInput
        style={styles.input}
        placeholder="Where did I leave my charger?"
        placeholderTextColor="#888"
        value={question}
        onChangeText={setQuestion}
        onSubmitEditing={handleSearch}
        returnKeyType="search"
      />

      <TouchableOpacity
        style={[styles.button, (loading || question.trim() === '') && styles.buttonDisabled]}
        onPress={handleSearch}
        disabled={loading || question.trim() === ''}
      >
        <Text style={styles.buttonText}>Search</Text>
      </TouchableOpacity>

      {loading && <ActivityIndicator size="large" style={styles.spinner} />}

      {error && <Text style={styles.error}>{error}</Text>}

      {result && result.matched === false && (
        <Text style={styles.noMatch}>No matching photo found.</Text>
      )}

      {result && result.matched === true && (
        <View style={styles.card}>
          <Text style={styles.answer}>{result.answer}</Text>
          <Image
            source={{ uri: result.image_url }}
            style={styles.photo}
            resizeMode="contain"
          />
          <Text style={styles.meta}>Room: {result.room_name}</Text>
          <Text style={styles.meta}>
            Taken: {new Date(result.captured_at).toLocaleString()}
          </Text>
          <Text style={styles.description}>{result.description}</Text>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: 'white' },
  content: { padding: 20 },
  title: { fontSize: 22, fontWeight: '600', marginBottom: 16, color: '#111' },
  input: {
    borderWidth: 1,
    borderColor: '#bbb',
    borderRadius: 10,
    padding: 12,
    fontSize: 16,
    color: '#111',
  },
  button: {
    backgroundColor: '#1F2E4D',
    borderRadius: 10,
    padding: 14,
    alignItems: 'center',
    marginTop: 12,
  },
  buttonDisabled: { opacity: 0.5 },
  buttonText: { color: 'white', fontSize: 16, fontWeight: '600' },
  spinner: { marginTop: 24 },
  error: { color: '#B00020', marginTop: 20, fontSize: 15 },
  noMatch: { marginTop: 20, fontSize: 16, color: '#444' },
  card: { marginTop: 20 },
  answer: { fontSize: 18, fontWeight: '600', color: '#111', marginBottom: 12 },
  photo: { width: '100%', height: 320, backgroundColor: '#eee', borderRadius: 10 },
  meta: { fontSize: 14, color: '#333', marginTop: 8 },
  description: { fontSize: 14, color: '#666', marginTop: 8 },
});
