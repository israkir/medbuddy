import { Stack, useRouter, type Href } from 'expo-router';
import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  TextInput,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { LargeButton } from '@/components/LargeButton';
import { Text } from '@/components/Themed';
import { fontSize, MIN_TOUCH } from '@/constants/accessibility';
import Colors from '@/constants/Colors';
import { useColorScheme } from '@/components/useColorScheme';
import { submitOnboarding } from '@/lib/companionApi';

export default function OnboardingScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];
  const insets = useSafeAreaInsets();
  const [name, setName] = useState('');
  const [ageText, setAgeText] = useState('');
  const [contact, setContact] = useState('');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(async () => {
    const trimmedName = name.trim();
    if (!trimmedName || busy) {
      return;
    }
    const ageDigits = ageText.replace(/\D/g, '');
    const ageNum = ageDigits.length > 0 ? Number.parseInt(ageDigits, 10) : NaN;
    const age_years = Number.isFinite(ageNum) && ageNum >= 0 && ageNum <= 120 ? ageNum : null;

    setBusy(true);
    setError(null);
    try {
      await submitOnboarding({
        preferred_name: trimmedName,
        age_years,
        emergency_contact: contact.trim(),
        health_notes: notes.trim(),
      });
      router.replace('/(tabs)' as Href);
    } catch (e) {
      const msg = e instanceof Error ? e.message : t('onboarding.errorUnknown');
      setError(msg);
    } finally {
      setBusy(false);
    }
  }, [ageText, busy, contact, name, notes, router, t]);

  return (
    <>
      <Stack.Screen
        options={{
          title: t('onboarding.title'),
          headerBackVisible: false,
        }}
      />
      <KeyboardAvoidingView
        style={[styles.flex, { backgroundColor: palette.background }]}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          contentContainerStyle={[
            styles.scroll,
            {
              paddingTop: 20,
              paddingBottom: 32 + insets.bottom,
            },
          ]}
          keyboardShouldPersistTaps="handled">
          <Text style={[styles.lead, { color: palette.text }]} maxFontSizeMultiplier={1.55}>
            {t('onboarding.lead')}
          </Text>
          <Text style={[styles.hint, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.45}>
            {t('onboarding.hintSkip')}
          </Text>

          <Text style={[styles.label, { color: palette.text }]} maxFontSizeMultiplier={1.45}>
            {t('onboarding.nameLabel')}
          </Text>
          <TextInput
            value={name}
            onChangeText={setName}
            placeholder={t('onboarding.namePlaceholder')}
            placeholderTextColor={palette.textSecondary}
            autoComplete="name"
            textContentType="name"
            maxLength={80}
            style={[
              styles.input,
              { color: palette.text, borderColor: palette.dockBorder, backgroundColor: palette.background },
            ]}
            accessibilityLabel={t('onboarding.nameLabel')}
          />

          <Text style={[styles.label, { color: palette.text }]} maxFontSizeMultiplier={1.45}>
            {t('onboarding.ageLabel')}
          </Text>
          <TextInput
            value={ageText}
            onChangeText={setAgeText}
            placeholder={t('onboarding.agePlaceholder')}
            placeholderTextColor={palette.textSecondary}
            keyboardType="number-pad"
            maxLength={3}
            style={[
              styles.input,
              { color: palette.text, borderColor: palette.dockBorder, backgroundColor: palette.background },
            ]}
            accessibilityLabel={t('onboarding.ageLabel')}
          />

          <Text style={[styles.label, { color: palette.text }]} maxFontSizeMultiplier={1.45}>
            {t('onboarding.contactLabel')}
          </Text>
          <TextInput
            value={contact}
            onChangeText={setContact}
            placeholder={t('onboarding.contactPlaceholder')}
            placeholderTextColor={palette.textSecondary}
            autoComplete="tel"
            maxLength={200}
            style={[
              styles.input,
              { color: palette.text, borderColor: palette.dockBorder, backgroundColor: palette.background },
            ]}
            accessibilityLabel={t('onboarding.contactLabel')}
          />

          <Text style={[styles.label, { color: palette.text }]} maxFontSizeMultiplier={1.45}>
            {t('onboarding.notesLabel')}
          </Text>
          <TextInput
            value={notes}
            onChangeText={setNotes}
            placeholder={t('onboarding.notesPlaceholder')}
            placeholderTextColor={palette.textSecondary}
            multiline
            maxLength={1000}
            style={[
              styles.inputMultiline,
              { color: palette.text, borderColor: palette.dockBorder, backgroundColor: palette.background },
            ]}
            accessibilityLabel={t('onboarding.notesLabel')}
          />

          {error ? (
            <Text style={[styles.error, { color: palette.tint }]} maxFontSizeMultiplier={1.4}>
              {t('onboarding.errorPrefix')} {error}
            </Text>
          ) : null}

          <LargeButton
            label={busy ? t('onboarding.saving') : t('onboarding.continue')}
            onPress={() => void submit()}
            disabled={busy || !name.trim()}
            style={styles.cta}
            accessibilityState={{ disabled: busy || !name.trim() }}
          />
          {busy ? <ActivityIndicator style={styles.spinner} color={palette.tint} /> : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  scroll: {
    paddingHorizontal: 20,
    maxWidth: 560,
    width: '100%',
    alignSelf: 'center',
  },
  lead: {
    fontSize: fontSize.title,
    fontWeight: '700',
    lineHeight: 36,
    marginBottom: 10,
  },
  hint: {
    fontSize: fontSize.caption,
    lineHeight: 26,
    marginBottom: 22,
  },
  label: {
    fontSize: fontSize.caption,
    fontWeight: '600',
    marginBottom: 8,
    marginTop: 14,
  },
  input: {
    minHeight: MIN_TOUCH,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 14,
    paddingHorizontal: 16,
    fontSize: fontSize.body,
  },
  inputMultiline: {
    minHeight: 100,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 14,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: fontSize.body,
    lineHeight: 28,
    textAlignVertical: 'top',
  },
  error: {
    marginTop: 16,
    fontSize: fontSize.caption - 2,
    lineHeight: 22,
  },
  cta: {
    marginTop: 28,
    width: '100%',
  },
  spinner: {
    marginTop: 16,
  },
});
