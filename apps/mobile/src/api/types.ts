// Hand-friendly aliases over the generated OpenAPI schema, so screens import
// `Medication` rather than `components['schemas']['MedicationOut']`. Regenerate
// schema.d.ts with `pnpm gen:api` whenever the backend contract changes.
import type { components } from '@/api/schema';

type S = components['schemas'];

export type Medication = S['MedicationOut'];
export type Schedule = S['ScheduleOut'];
export type DoseInstance = S['DoseInstanceOut'];
export type DoseLog = S['DoseLogOut'];
export type Profile = S['ProfileOut'];
export type ScheduleInput = S['ScheduleIn'];
export type MedicationInput = S['MedicationIn'];
export type DoseLogInput = S['DoseLogIn'];

export type ScheduleKind = S['ScheduleKind'];
export type DoseStatus = S['DoseStatus'];
export type MedicationForm = NonNullable<S['MedicationIn']['form']>;
