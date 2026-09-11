// EXPO_PUBLIC_* variables are inlined into the JS bundle at build time — they are
// public by definition, which is fine: none of these is a secret. Failing fast
// here beats a cryptic network error later.
function required(name: string, value: string | undefined): string {
  if (!value) throw new Error(`Missing ${name} — copy .env.example to .env`);
  return value;
}

export const config = {
  supabaseUrl: required('EXPO_PUBLIC_SUPABASE_URL', process.env.EXPO_PUBLIC_SUPABASE_URL),
  supabasePublishableKey: required(
    'EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY',
    process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  ),
  apiUrl: required('EXPO_PUBLIC_API_URL', process.env.EXPO_PUBLIC_API_URL),
};
