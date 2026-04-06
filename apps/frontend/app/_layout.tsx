import FontAwesome from '@expo/vector-icons/FontAwesome';
import { DarkTheme, DefaultTheme, ThemeProvider } from '@react-navigation/native';
import { useFonts } from 'expo-font';
import { Stack, useRouter, type Href } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import 'react-native-reanimated';

import '@/i18n';
import { applyStoredLanguage } from '@/i18n/languageStorage';
import { useColorScheme } from '@/components/useColorScheme';
import Colors from '@/constants/Colors';
import { fetchMeProfile } from '@/lib/companionApi';

export {
  // Catch any errors thrown by the Layout component.
  ErrorBoundary,
} from 'expo-router';

export const unstable_settings = {
  // Ensure that reloading on `/modal` keeps a back button present.
  initialRouteName: '(tabs)',
};

// Prevent the splash screen from auto-hiding before asset loading is complete.
SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [loaded, error] = useFonts({
    SpaceMono: require('../assets/fonts/SpaceMono-Regular.ttf'),
    ...FontAwesome.font,
  });
  const [i18nReady, setI18nReady] = useState(false);

  // Expo Router uses Error Boundaries to catch errors in the navigation tree.
  useEffect(() => {
    if (error) throw error;
  }, [error]);

  useEffect(() => {
    if (!loaded) {
      return;
    }
    let cancelled = false;
    (async () => {
      await applyStoredLanguage();
      if (cancelled) {
        return;
      }
      await SplashScreen.hideAsync();
      setI18nReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [loaded]);

  if (!loaded || !i18nReady) {
    return null;
  }

  return <RootLayoutNav />;
}

function RootLayoutNav() {
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];
  const router = useRouter();
  const [onboardingGate, setOnboardingGate] = useState<'pending' | 'done' | 'need'>('pending');
  const didRedirectToOnboarding = useRef(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await fetchMeProfile();
        if (cancelled) {
          return;
        }
        setOnboardingGate(me.onboarding_completed_at ? 'done' : 'need');
      } catch {
        if (cancelled) {
          return;
        }
        setOnboardingGate('done');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (onboardingGate !== 'need' || didRedirectToOnboarding.current) {
      return;
    }
    didRedirectToOnboarding.current = true;
    router.replace('/onboarding' as Href);
  }, [onboardingGate, router]);

  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <View style={styles.root}>
        <Stack>
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen
            name="onboarding"
            options={{ headerShown: true, gestureEnabled: false }}
          />
          <Stack.Screen name="companion" options={{ headerShown: true }} />
          <Stack.Screen name="modal" options={{ presentation: 'modal' }} />
        </Stack>
        {onboardingGate === 'pending' ? (
          <View
            style={[styles.gateOverlay, { backgroundColor: palette.background }]}
            accessibilityViewIsModal>
            <ActivityIndicator size="large" color={palette.tint} />
          </View>
        ) : null}
      </View>
    </ThemeProvider>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  gateOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
