// A single medication: its details, current schedules, and archive. Editing a
// schedule (replace) comes in Phase 3; for now this is view + archive.
import { router, useLocalSearchParams, useNavigation } from 'expo-router';
import { useLayoutEffect } from 'react';
import { Alert, ScrollView, StyleSheet, View } from 'react-native';
import { ActivityIndicator, Button, Card, Divider, List, Text } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useArchiveMedication, useMedications } from '@/api/hooks';
import { scheduleSummary } from '@/features/scheduleSummary';

export default function MedicationDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const navigation = useNavigation();
  const meds = useMedications();
  const archive = useArchiveMedication();
  const med = meds.data?.find((m) => m.id === id);

  useLayoutEffect(() => {
    if (med) navigation.setOptions({ title: med.name });
  }, [med, navigation]);

  if (meds.isPending) return <ActivityIndicator style={styles.spinner} />;
  if (!med) {
    return (
      <View style={styles.center}>
        <Text>Medication not found.</Text>
      </View>
    );
  }

  function confirmArchive() {
    Alert.alert('Archive medication?', `${med!.name} will stop reminding you. Its history is kept.`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Archive',
        style: 'destructive',
        onPress: async () => {
          await archive.mutateAsync(med!.id);
          router.back();
        },
      },
    ]);
  }

  return (
    <SafeAreaView style={styles.screen} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text variant="headlineSmall">{med.name}</Text>
        {med.strength ? <Text variant="bodyLarge" style={styles.sub}>{med.strength} · {med.form}</Text> : <Text variant="bodyLarge" style={styles.sub}>{med.form}</Text>}
        {med.notes ? <Text variant="bodyMedium" style={styles.notes}>{med.notes}</Text> : null}

        <Card mode="outlined" style={styles.card}>
          <Card.Title title="Schedules" />
          <Card.Content>
            {med.schedules.length === 0 ? (
              <Text variant="bodyMedium">No active schedule.</Text>
            ) : (
              med.schedules.map((s, i) => (
                <View key={s.id}>
                  {i > 0 ? <Divider style={styles.divider} /> : null}
                  <List.Item title={scheduleSummary(s)} titleNumberOfLines={2} left={(p) => <List.Icon {...p} icon="calendar-clock" />} />
                </View>
              ))
            )}
          </Card.Content>
        </Card>

        <Button mode="outlined" textColor="#b3261e" onPress={confirmArchive} loading={archive.isPending} style={styles.archive}>
          Archive medication
        </Button>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: 16, gap: 8 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  spinner: { marginTop: 48 },
  sub: { opacity: 0.7 },
  notes: { marginTop: 8 },
  card: { marginTop: 16 },
  divider: { marginVertical: 4 },
  archive: { marginTop: 24, borderColor: '#b3261e' },
});
