import { StyleSheet, View } from 'react-native';
import { Button, List } from 'react-native-paper';

import { useAuth } from '@/auth/AuthProvider';
import { config } from '@/lib/config';
import { supabase } from '@/lib/supabase';

export default function Settings() {
  const { session } = useAuth();
  return (
    <View style={styles.screen}>
      <List.Item title="Signed in as" description={session?.user.email ?? '—'} />
      <List.Item title="API" description={config.apiUrl} />
      <Button mode="outlined" onPress={() => supabase.auth.signOut()} style={styles.button}>
        Sign out
      </Button>
    </View>
  );
}

const styles = StyleSheet.create({ screen: { flex: 1, padding: 16 }, button: { marginTop: 24 } });
