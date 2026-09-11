// The app talks to Supabase for exactly one thing: authentication. Data goes
// through our own API. The publishable key can only sign users in — every table
// has RLS enabled with no policies, so it cannot read anything directly.
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient } from '@supabase/supabase-js';
import { AppState } from 'react-native';

import { config } from '@/lib/config';

export const supabase = createClient(config.supabaseUrl, config.supabasePublishableKey, {
  auth: {
    storage: AsyncStorage, // session survives app restarts
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false, // no browser URL to inspect on native
  },
});

// Access tokens live one hour. Refresh them only while the app is in the
// foreground; a backgrounded app would otherwise wake up for nothing.
AppState.addEventListener('change', (state) => {
  if (state === 'active') supabase.auth.startAutoRefresh();
  else supabase.auth.stopAutoRefresh();
});
