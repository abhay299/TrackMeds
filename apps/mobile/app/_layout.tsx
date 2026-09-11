// Root of the app. Providers on the outside, then the auth gate: Expo Router's
// Stack.Protected removes screens whose guard is false, so a signed-out user can
// only ever reach sign-in, and signing in/out moves them automatically.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useColorScheme } from 'react-native';
import { MD3DarkTheme, MD3LightTheme, PaperProvider } from 'react-native-paper';

import { AuthProvider, useAuth } from '@/auth/AuthProvider';

const queryClient = new QueryClient();

function RootNavigator() {
  const { session, loading } = useAuth();
  if (loading) return null; // session is being restored from storage; a blink at most

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={session !== null}>
        <Stack.Screen name="(tabs)" />
      </Stack.Protected>
      <Stack.Protected guard={session === null}>
        <Stack.Screen name="sign-in" />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  const theme = useColorScheme() === 'dark' ? MD3DarkTheme : MD3LightTheme;
  return (
    <PaperProvider theme={theme}>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <StatusBar style="auto" />
          <RootNavigator />
        </AuthProvider>
      </QueryClientProvider>
    </PaperProvider>
  );
}
