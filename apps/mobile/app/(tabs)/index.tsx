// Today: every dose scheduled for the current local day, grouped nothing fancy,
// just time-ordered as the API returns them. Take/Skip/Undo write straight
// through to the log and the cache refreshes.
import { useMemo, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { ActivityIndicator, Banner, Text } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { DoseInstance } from '@/api/types';
import { useDoses, useLogDose, useUndoLog } from '@/api/hooks';
import { DoseCard } from '@/features/DoseCard';
import { formatDay, localDayWindow } from '@/lib/time';

export default function Today() {
  // Compute the window once per mount; a pull-to-refresh re-runs the query.
  const today = useMemo(() => new Date(), []);
  const { from, to } = useMemo(() => localDayWindow(today), [today]);
  const doses = useDoses(from, to);
  const log = useLogDose();
  const undo = useUndoLog();
  const [pendingAt, setPendingAt] = useState<string | null>(null);

  const busyFor = (dose: DoseInstance) => pendingAt === dose.scheduled_at;

  async function act(dose: DoseInstance, run: () => Promise<unknown>) {
    setPendingAt(dose.scheduled_at);
    try {
      await run();
    } finally {
      setPendingAt(null);
    }
  }

  const take = (d: DoseInstance) =>
    act(d, () => log.mutateAsync({ schedule_id: d.schedule_id, scheduled_at: d.scheduled_at, status: 'taken' }));
  const skip = (d: DoseInstance) =>
    act(d, () => log.mutateAsync({ schedule_id: d.schedule_id, scheduled_at: d.scheduled_at, status: 'skipped' }));
  const undoDose = (d: DoseInstance) => (d.log ? act(d, () => undo.mutateAsync(d.log!.id)) : undefined);

  return (
    <SafeAreaView style={styles.screen} edges={['bottom']}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={doses.isFetching} onRefresh={() => doses.refetch()} />}
      >
        <Text variant="titleMedium" style={styles.heading}>
          {formatDay(today)}
        </Text>

        {doses.isError ? (
          <Banner visible icon="alert-circle" actions={[{ label: 'Retry', onPress: () => doses.refetch() }]}>
            Couldn’t load today’s doses. {String((doses.error as Error).message)}
          </Banner>
        ) : null}

        {doses.isPending ? (
          <ActivityIndicator style={styles.spinner} />
        ) : doses.data && doses.data.length > 0 ? (
          doses.data.map((dose) => (
            <DoseCard
              key={`${dose.schedule_id}:${dose.scheduled_at}`}
              dose={dose}
              busy={busyFor(dose)}
              onTake={take}
              onSkip={skip}
              onUndo={undoDose}
            />
          ))
        ) : (
          <View style={styles.empty}>
            <Text variant="bodyLarge">Nothing scheduled today.</Text>
            <Text variant="bodyMedium" style={styles.emptyHint}>
              Add a medication from the Meds tab and its doses will show up here.
            </Text>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: 16, paddingBottom: 32 },
  heading: { marginBottom: 12, opacity: 0.7 },
  spinner: { marginTop: 48 },
  empty: { marginTop: 64, alignItems: 'center', gap: 6 },
  emptyHint: { textAlign: 'center', opacity: 0.7, maxWidth: 280 },
});
