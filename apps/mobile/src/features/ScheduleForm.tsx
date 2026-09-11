// The schedule half of the add-medication form. The kind picker decides which
// fields matter — this component shows only those, and returns a ScheduleInput
// the API accepts. Kept apart from the medication fields so it can be reused
// when we add "edit schedule" later.
import { useState } from 'react';
import { Platform, StyleSheet, View } from 'react-native';
import DateTimePicker from '@react-native-community/datetimepicker';
import { Button, Chip, HelperText, SegmentedButtons, Text, TextInput, useTheme } from 'react-native-paper';

import type { ScheduleInput, ScheduleKind } from '@/api/types';
import { deviceTz } from '@/lib/time';

const DAYS = [
  { v: 0, label: 'M' }, { v: 1, label: 'T' }, { v: 2, label: 'W' }, { v: 3, label: 'T' },
  { v: 4, label: 'F' }, { v: 5, label: 'S' }, { v: 6, label: 'S' },
];

export type ScheduleFormValue = ScheduleInput;

const HH = (n: number) => String(n).padStart(2, '0');

export function defaultSchedule(): ScheduleFormValue {
  return {
    kind: 'daily',
    tz: deviceTz(),
    times_of_day: ['08:00:00'],
    days_of_week: [],
    interval: 1,
    dose_amount: 1,
    dose_unit: 'tablet',
  };
}

type Props = { value: ScheduleFormValue; onChange: (v: ScheduleFormValue) => void };

export function ScheduleForm({ value, onChange }: Props) {
  const theme = useTheme();
  const set = (patch: Partial<ScheduleFormValue>) => onChange({ ...value, ...patch });
  const [picker, setPicker] = useState<number | 'new' | null>(null);

  const showTimes = value.kind === 'daily' || value.kind === 'weekly' || value.kind === 'every_n_days';
  const fmtTime = (t: string) => {
    const [h, m] = t.split(':').map(Number);
    const d = new Date();
    d.setHours(h, m, 0, 0);
    return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(d);
  };

  const onPicked = (index: number | 'new', date?: Date) => {
    setPicker(null);
    if (!date) return;
    const t = `${HH(date.getHours())}:${HH(date.getMinutes())}:00`;
    const times = new Set(value.times_of_day);
    if (index !== 'new') value.times_of_day.forEach((x, i) => i === index && times.delete(x));
    times.add(t);
    set({ times_of_day: [...times].sort() });
  };

  return (
    <View style={styles.section}>
      <Text variant="labelLarge" style={styles.label}>Schedule</Text>
      <SegmentedButtons
        value={value.kind}
        onValueChange={(k) => set({ kind: k as ScheduleKind })}
        density="small"
        buttons={[
          { value: 'daily', label: 'Daily' },
          { value: 'weekly', label: 'Weekly' },
          { value: 'every_n_days', label: 'N days' },
          { value: 'every_n_hours', label: 'Hourly' },
        ]}
      />

      {value.kind === 'weekly' ? (
        <View style={styles.days}>
          {DAYS.map((d) => {
            const on = value.days_of_week.includes(d.v);
            return (
              <Chip
                key={d.v}
                selected={on}
                showSelectedCheck={false}
                style={styles.day}
                onPress={() =>
                  set({ days_of_week: on ? value.days_of_week.filter((x) => x !== d.v) : [...value.days_of_week, d.v].sort() })
                }
              >
                {d.label}
              </Chip>
            );
          })}
        </View>
      ) : null}

      {value.kind === 'every_n_days' ? (
        <IntervalField label="Every N days" value={value.interval} onChange={(interval) => set({ interval })} />
      ) : null}

      {value.kind === 'every_n_hours' ? (
        <IntervalField label="Every N hours" value={value.interval} onChange={(interval) => set({ interval })} />
      ) : null}

      {showTimes ? (
        <View style={styles.times}>
          {value.times_of_day.map((t, i) => (
            <Chip key={t} icon="clock-outline" onPress={() => setPicker(i)} onClose={value.times_of_day.length > 1 ? () => set({ times_of_day: value.times_of_day.filter((x) => x !== t) }) : undefined} style={styles.timeChip}>
              {fmtTime(t)}
            </Chip>
          ))}
          <Button icon="plus" mode="text" onPress={() => setPicker('new')} compact>
            Add time
          </Button>
        </View>
      ) : null}

      <View style={styles.doseRow}>
        <TextInput
          label="Dose"
          mode="outlined"
          keyboardType="decimal-pad"
          value={String(value.dose_amount)}
          onChangeText={(x) => set({ dose_amount: Number(x.replace(/[^0-9.]/g, '')) || 0 })}
          style={styles.doseAmount}
          dense
        />
        <TextInput
          label="Unit"
          mode="outlined"
          value={value.dose_unit}
          onChangeText={(dose_unit) => set({ dose_unit })}
          style={styles.doseUnit}
          dense
        />
      </View>
      <TextInput
        label="Instructions (optional)"
        mode="outlined"
        value={value.instructions ?? ''}
        onChangeText={(instructions) => set({ instructions: instructions || undefined })}
        placeholder="after food"
        dense
        style={styles.instructions}
      />

      {picker !== null ? (
        <DateTimePicker
          mode="time"
          value={new Date()}
          is24Hour={false}
          display={Platform.OS === 'ios' ? 'spinner' : 'clock'}
          onChange={(e, date) => onPicked(picker, e.type === 'set' ? date : undefined)}
        />
      ) : null}
    </View>
  );
}

function IntervalField({ label, value, onChange }: { label: string; value: number; onChange: (n: number) => void }) {
  return (
    <View style={styles.interval}>
      <TextInput
        label={label}
        mode="outlined"
        keyboardType="number-pad"
        value={String(value)}
        onChangeText={(x) => onChange(Math.max(1, Number(x.replace(/[^0-9]/g, '')) || 1))}
        dense
        style={{ width: 160 }}
      />
      <HelperText type="info">{value < 1 ? 'At least 1' : ' '}</HelperText>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: 12, marginTop: 8 },
  label: { opacity: 0.7 },
  days: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  day: { minWidth: 40, alignItems: 'center' },
  interval: { marginTop: 4 },
  times: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 6 },
  timeChip: {},
  doseRow: { flexDirection: 'row', gap: 12 },
  doseAmount: { flex: 1 },
  doseUnit: { flex: 2 },
  instructions: {},
});
