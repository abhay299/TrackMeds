// TanStack Query hooks over the API. Keeping every endpoint and cache key here
// means screens never build URLs or juggle invalidation — they ask for data or
// fire a mutation, and the cache does the rest.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import type {
  DoseInstance,
  DoseLogInput,
  Medication,
  MedicationInput,
  Profile,
  ScheduleInput,
} from '@/api/types';

const keys = {
  profile: ['profile'] as const,
  medications: ['medications'] as const,
  doses: (from: string, to: string) => ['doses', from, to] as const,
};

export function useProfile() {
  return useQuery({ queryKey: keys.profile, queryFn: () => api<Profile>('/me') });
}

export function useMedications() {
  return useQuery({ queryKey: keys.medications, queryFn: () => api<Medication[]>('/medications') });
}

export function useDoses(from: string, to: string) {
  return useQuery({
    queryKey: keys.doses(from, to),
    queryFn: () => api<DoseInstance[]>(`/doses?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`),
  });
}

// Anything that changes schedules or logs can shift what's due, so mutations
// invalidate both lists and every doses window at once.
function useRefetchDomain() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: keys.medications });
    qc.invalidateQueries({ queryKey: ['doses'] });
  };
}

export function useCreateMedication() {
  const refetch = useRefetchDomain();
  return useMutation({
    mutationFn: (body: MedicationInput) =>
      api<Medication>('/medications', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: refetch,
  });
}

export function useArchiveMedication() {
  const refetch = useRefetchDomain();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/medications/${id}`, { method: 'DELETE' }),
    onSuccess: refetch,
  });
}

// Screens describe the dose; the source is always this app.
type LogArgs = Omit<DoseLogInput, 'source'>;

export function useLogDose() {
  const refetch = useRefetchDomain();
  return useMutation({
    mutationFn: (body: LogArgs) =>
      api('/doses/log', { method: 'POST', body: JSON.stringify({ ...body, source: 'app' }) }),
    onSuccess: refetch,
  });
}

export function useUndoLog() {
  const refetch = useRefetchDomain();
  return useMutation({
    mutationFn: (logId: string) => api<void>(`/doses/log/${logId}`, { method: 'DELETE' }),
    onSuccess: refetch,
  });
}
