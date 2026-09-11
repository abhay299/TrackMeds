// The medicines list. Each card shows the medicine and a one-line summary of
// its current schedule(s); the FAB opens the add form.
import { router } from 'expo-router';
import { ScrollView, StyleSheet, View } from 'react-native';
import { ActivityIndicator, Banner, Card, FAB, Text, useTheme } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { Medication } from '@/api/types';
import { useMedications } from '@/api/hooks';
import { scheduleSummary } from '@/features/scheduleSummary';

export default function Meds() {
  const theme = useTheme();
  const meds = useMedications();

  return (
    <SafeAreaView style={styles.screen} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        {meds.isError ? (
          <Banner visible icon="alert-circle" actions={[{ label: 'Retry', onPress: () => meds.refetch() }]}>
            Couldn’t load medications. {String((meds.error as Error).message)}
          </Banner>
        ) : null}

        {meds.isPending ? (
          <ActivityIndicator style={styles.spinner} />
        ) : meds.data && meds.data.length > 0 ? (
          meds.data.map((med) => <MedRow key={med.id} med={med} />)
        ) : (
          <View style={styles.empty}>
            <Text variant="bodyLarge">No medications yet.</Text>
            <Text variant="bodyMedium" style={styles.emptyHint}>
              Tap + to add the first one.
            </Text>
          </View>
        )}
      </ScrollView>
      <FAB icon="plus" label="Add" style={[styles.fab, { backgroundColor: theme.colors.primaryContainer }]} onPress={() => router.push('/medication/new')} />
    </SafeAreaView>
  );
}

function MedRow({ med }: { med: Medication }) {
  const summary = med.schedules.map(scheduleSummary).join(' · ') || 'No active schedule';
  return (
    <Card mode="outlined" style={styles.card} onPress={() => router.push(`/medication/${med.id}`)}>
      <Card.Title
        title={med.strength ? `${med.name} · ${med.strength}` : med.name}
        subtitle={summary}
        subtitleNumberOfLines={2}
      />
    </Card>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: 16, paddingBottom: 96 },
  card: { marginBottom: 12 },
  spinner: { marginTop: 48 },
  empty: { marginTop: 64, alignItems: 'center', gap: 6 },
  emptyHint: { textAlign: 'center', opacity: 0.7 },
  fab: { position: 'absolute', right: 16, bottom: 16 },
});
