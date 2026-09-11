// Phase 0: this screen only proves the phone can reach the API with a real
// token and that the API can reach the database. Phase 1 replaces it with the
// actual Today view.
import { useQuery } from '@tanstack/react-query';
import { ScrollView, StyleSheet } from 'react-native';
import { Card, Text } from 'react-native-paper';

import { api } from '@/lib/api';

type Me = { id: string; email: string | null };
type DbHealth = { status: string; database: string };

function Status({ title, query }: { title: string; query: { isPending: boolean; error: Error | null; data: unknown } }) {
  const body = query.isPending
    ? 'checking…'
    : query.error
      ? `failed: ${query.error.message}`
      : JSON.stringify(query.data);
  return (
    <Card style={styles.card}>
      <Card.Title title={title} />
      <Card.Content>
        <Text variant="bodyMedium">{body}</Text>
      </Card.Content>
    </Card>
  );
}

export default function Today() {
  const me = useQuery({ queryKey: ['me'], queryFn: () => api<Me>('/me') });
  const db = useQuery({ queryKey: ['health', 'db'], queryFn: () => api<DbHealth>('/health/db') });

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text variant="titleMedium">Connection check (Phase 0)</Text>
      <Status title="API knows who I am — GET /me" query={me} />
      <Status title="API can reach the database — GET /health/db" query={db} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, gap: 12 },
  card: { marginTop: 4 },
});
