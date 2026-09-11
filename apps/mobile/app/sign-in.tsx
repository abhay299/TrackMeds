import { useState } from 'react';
import { KeyboardAvoidingView, Platform, StyleSheet } from 'react-native';
import { Button, HelperText, Text, TextInput } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';

import { supabase } from '@/lib/supabase';

export default function SignIn() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    // On success there is nothing to do here: AuthProvider sees the new session
    // and the root layout's guard swaps this screen for the tabs.
    if (error) setError(error.message);
    setBusy(false);
  }

  return (
    <SafeAreaView style={styles.screen}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.form}
      >
        <Text variant="displaySmall">medtrack</Text>
        <Text variant="bodyLarge" style={styles.subtitle}>
          Sign in with the account you were given.
        </Text>
        <TextInput
          label="Email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          mode="outlined"
        />
        <TextInput
          label="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoComplete="current-password"
          mode="outlined"
          onSubmitEditing={submit}
        />
        <HelperText type="error" visible={error !== null}>
          {error ?? ' '}
        </HelperText>
        <Button
          mode="contained"
          onPress={submit}
          loading={busy}
          disabled={busy || !email || !password}
        >
          Sign in
        </Button>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  form: { flex: 1, justifyContent: 'center', padding: 24, gap: 12 },
  subtitle: { marginBottom: 12 },
});
