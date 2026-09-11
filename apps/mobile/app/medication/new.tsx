// Add a medication: the name/form fields plus one ScheduleForm. On save the
// whole thing goes to POST /medications, which creates the medicine and its
// first schedule together.
import { router } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet } from 'react-native';
import { Button, HelperText, SegmentedButtons, Text, TextInput } from 'react-native-paper';

import type { MedicationForm } from '@/api/types';
import { useCreateMedication } from '@/api/hooks';
import { ScheduleForm, defaultSchedule, type ScheduleFormValue } from '@/features/ScheduleForm';

const FORMS: { value: MedicationForm; label: string }[] = [
  { value: 'tablet', label: 'Tablet' },
  { value: 'capsule', label: 'Capsule' },
  { value: 'liquid', label: 'Liquid' },
  { value: 'other', label: 'Other' },
];

export default function NewMedication() {
  const create = useCreateMedication();
  const [name, setName] = useState('');
  const [strength, setStrength] = useState('');
  const [form, setForm] = useState<MedicationForm>('tablet');
  const [schedule, setSchedule] = useState<ScheduleFormValue>(defaultSchedule);
  const [error, setError] = useState<string | null>(null);

  const scheduleReady =
    (schedule.kind !== 'weekly' || schedule.days_of_week.length > 0) &&
    (!['daily', 'weekly', 'every_n_days'].includes(schedule.kind) || schedule.times_of_day.length > 0) &&
    Number(schedule.dose_amount) > 0 &&
    schedule.dose_unit.trim().length > 0;

  async function save() {
    setError(null);
    try {
      await create.mutateAsync({
        name: name.trim(),
        strength: strength.trim() || undefined,
        form,
        schedule,
      });
      router.back();
    } catch (e) {
      setError(String((e as Error).message));
    }
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <TextInput label="Name" mode="outlined" value={name} onChangeText={setName} autoFocus />
        <TextInput label="Strength (optional)" mode="outlined" value={strength} onChangeText={setStrength} placeholder="500 mg" />

        <Text variant="labelLarge" style={styles.label}>Form</Text>
        <SegmentedButtons value={form} onValueChange={(v) => setForm(v as MedicationForm)} density="small" buttons={FORMS} />

        <ScheduleForm value={schedule} onChange={setSchedule} />

        <HelperText type="error" visible={error !== null}>
          {error ?? ' '}
        </HelperText>
        <Button mode="contained" onPress={save} loading={create.isPending} disabled={create.isPending || name.trim().length === 0 || !scheduleReady} style={styles.save}>
          Save
        </Button>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: 16, gap: 12, paddingBottom: 48 },
  label: { opacity: 0.7, marginTop: 4 },
  save: { marginTop: 4 },
});
