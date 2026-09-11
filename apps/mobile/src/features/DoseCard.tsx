// One dose on the Today screen. Its look and available actions follow the
// status the API computed — we never re-derive it on the client.
import { memo } from 'react';
import { StyleSheet, View } from 'react-native';
import { Button, Card, Chip, Text, useTheme } from 'react-native-paper';

import type { DoseInstance, DoseStatus } from '@/api/types';
import { formatRelative, formatTime } from '@/lib/time';

const STATUS: Record<DoseStatus, { label: string; tone: 'due' | 'missed' | 'done' | 'upcoming' }> = {
  upcoming: { label: 'Upcoming', tone: 'upcoming' },
  due: { label: 'Due now', tone: 'due' },
  missed: { label: 'Missed', tone: 'missed' },
  taken: { label: 'Taken', tone: 'done' },
  skipped: { label: 'Skipped', tone: 'done' },
};

type Props = {
  dose: DoseInstance;
  busy: boolean;
  onTake: (dose: DoseInstance) => void;
  onSkip: (dose: DoseInstance) => void;
  onUndo: (dose: DoseInstance) => void;
};

function DoseCardBase({ dose, busy, onTake, onSkip, onUndo }: Props) {
  const theme = useTheme();
  const meta = STATUS[dose.status];
  const logged = dose.status === 'taken' || dose.status === 'skipped';
  const toneColor = {
    due: theme.colors.primary,
    missed: theme.colors.error,
    done: theme.colors.secondary,
    upcoming: theme.colors.outline,
  }[meta.tone];

  const dose_text = `${dose.dose_amount} ${dose.dose_unit}${dose.strength ? ` · ${dose.strength}` : ''}`;

  return (
    <Card mode="outlined" style={styles.card}>
      <Card.Content>
        <View style={styles.row}>
          <Text variant="titleMedium" style={styles.time}>
            {formatTime(dose.scheduled_at)}
          </Text>
          <Chip compact textStyle={{ color: toneColor }} style={[styles.chip, { borderColor: toneColor }]}>
            {meta.label}
          </Chip>
        </View>
        <Text variant="titleLarge">{dose.medication_name}</Text>
        <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant }}>
          {dose_text}
          {dose.instructions ? ` · ${dose.instructions}` : ''}
        </Text>
        {dose.status === 'due' || dose.status === 'missed' ? (
          <Text variant="bodySmall" style={{ color: toneColor, marginTop: 2 }}>
            {formatRelative(dose.scheduled_at)}
          </Text>
        ) : null}
      </Card.Content>
      <Card.Actions>
        {logged ? (
          <Button onPress={() => onUndo(dose)} disabled={busy}>
            Undo
          </Button>
        ) : (
          <>
            <Button onPress={() => onSkip(dose)} disabled={busy}>
              Skip
            </Button>
            <Button mode="contained" onPress={() => onTake(dose)} disabled={busy}>
              Take
            </Button>
          </>
        )}
      </Card.Actions>
    </Card>
  );
}

export const DoseCard = memo(DoseCardBase);

const styles = StyleSheet.create({
  card: { marginBottom: 12 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  time: { opacity: 0.9 },
  chip: { backgroundColor: 'transparent', borderWidth: 1 },
});
