// Root of the app. Providers on the outside, then the auth gate: Expo Router's
// Stack.Protected removes screens whose guard is false, so a signed-out user can
// only ever reach sign-in, and signing in/out moves them automatically.
import {
  DarkTheme as NavigationDarkTheme,
  DefaultTheme as NavigationDefaultTheme,
  ThemeProvider,
} from 'expo-router/react-navigation';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { Platform, StyleSheet, useColorScheme, View } from 'react-native';
import { type MD3Theme, MD3DarkTheme, MD3LightTheme, PaperProvider } from 'react-native-paper';

import { AuthProvider, useAuth } from '@/auth/AuthProvider';

const queryClient = new QueryClient();

// Paper themes its components; the navigator paints screen backgrounds, headers
// and tab bars. Deriving the navigator's palette from Paper's keeps the two in
// agreement in both light and dark mode. (Paper's adaptNavigationTheme helper
// predates Expo Router's own theme type, so the mapping is done by hand.)
function navigationTheme(paper: MD3Theme) {
  const base = paper.dark ? NavigationDarkTheme : NavigationDefaultTheme;
  return {
    ...base,
    colors: {
      ...base.colors,
      primary: paper.colors.primary,
      background: paper.colors.background,
      card: paper.colors.elevation.level2,
      text: paper.colors.onSurface,
      border: paper.colors.outline,
      notification: paper.colors.error,
    },
  };
}

function RootNavigator() {
  const { session, loading } = useAuth();
  if (loading) return null; // session is being restored from storage; a blink at most

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={session !== null}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="medication/new" options={{ headerShown: true, title: 'Add medication', presentation: 'modal' }} />
        <Stack.Screen name="medication/[id]" options={{ headerShown: true, title: 'Medication' }} />
      </Stack.Protected>
      <Stack.Protected guard={session === null}>
        <Stack.Screen name="sign-in" />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  const paper = useColorScheme() === 'dark' ? MD3DarkTheme : MD3LightTheme;
  return (
    <PaperProvider theme={paper}>
      <ThemeProvider value={navigationTheme(paper)}>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <StatusBar style="auto" />
            <View style={styles.frame}>
              <RootNavigator />
            </View>
          </AuthProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </PaperProvider>
  );
}

const styles = StyleSheet.create({
  // In a desktop browser (a dev convenience, not the product) keep a phone-like width.
  frame: Platform.select({
    web: { flex: 1, width: '100%', maxWidth: 480, alignSelf: 'center' },
    default: { flex: 1 },
  }),
});
