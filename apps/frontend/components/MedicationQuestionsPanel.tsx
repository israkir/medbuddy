import FontAwesome from '@expo/vector-icons/FontAwesome';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { fontSize, MIN_TOUCH } from '@/constants/accessibility';
import Colors from '@/constants/Colors';
import { useVoiceRecording } from '@/hooks/useVoiceRecording';
import {
  loadQuestionText,
  loadVoiceSavedAt,
  saveQuestionText,
  saveVoiceSavedAt,
} from '@/storage/medicationQuestionNotes';
import { useColorScheme } from '@/components/useColorScheme';

const MIC_SIZE = 76;
const MIC_ICON = 32;

function formatVoiceTime(iso: string, lng: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(lng.startsWith('zh') ? 'zh-TW' : 'en-US', {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  } catch {
    return iso;
  }
}

export function MedicationQuestionsPanel() {
  const { t, i18n } = useTranslation();
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];
  const [noteText, setNoteText] = useState('');
  const [voiceSavedAt, setVoiceSavedAt] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  const onVoiceFinished = useCallback(async () => {
    const iso = new Date().toISOString();
    await saveVoiceSavedAt(iso);
    setVoiceSavedAt(iso);
  }, []);

  const { recording, onPressIn, onPressOut } = useVoiceRecording({
    onRecordingComplete: onVoiceFinished,
  });

  useEffect(() => {
    void (async () => {
      const [text, voiceAt] = await Promise.all([loadQuestionText(), loadVoiceSavedAt()]);
      setNoteText(text);
      setVoiceSavedAt(voiceAt);
      setHydrated(true);
    })();
  }, []);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    const id = setTimeout(() => {
      void saveQuestionText(noteText);
    }, 700);
    return () => clearTimeout(id);
  }, [noteText, hydrated]);

  const voiceHint = recording ? t('medications.questionsReleasing') : t('medications.questionsHoldMic');
  const voiceWhen =
    voiceSavedAt != null
      ? t('medications.questionsVoiceSaved', {
          when: formatVoiceTime(voiceSavedAt, i18n.language),
        })
      : null;

  return (
    <View
      style={[
        styles.shell,
        {
          backgroundColor: palette.dosePendingSurface,
          borderColor: palette.dosePendingAccent,
        },
        Platform.select({
          ios: {
            shadowColor: '#c2410c',
            shadowOffset: { width: 0, height: 2 },
            shadowOpacity: 0.1,
            shadowRadius: 10,
          },
          android: { elevation: 2 },
          default: {},
        }),
      ]}
      accessibilityLabel={t('medications.questionsSectionLabel')}>
      <Text
        style={[styles.eyebrow, { color: palette.dosePendingBadgeText }]}
        maxFontSizeMultiplier={1.45}>
        {t('medications.questionsSectionLabel')}
      </Text>
      <Text style={[styles.title, { color: palette.text }]} maxFontSizeMultiplier={1.55}>
        {t('medications.questionsTitle')}
      </Text>
      <Text style={[styles.subtitle, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.5}>
        {t('medications.questionsSubtitle')}
      </Text>

      <View style={styles.purposeRow}>
        <View
          style={[
            styles.purposeCard,
            {
              backgroundColor: palette.medicationFieldSurface,
              borderColor: palette.tint,
            },
          ]}>
          <FontAwesome name="question-circle" size={22} color={palette.tint} />
          <Text style={[styles.purposeTitle, { color: palette.text }]} maxFontSizeMultiplier={1.45}>
            {t('medications.questionsPurposeAskTitle')}
          </Text>
          <Text style={[styles.purposeBody, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.45}>
            {t('medications.questionsPurposeAskBody')}
          </Text>
        </View>
        <View
          style={[
            styles.purposeCard,
            {
              backgroundColor: palette.medicationFieldSurface,
              borderColor: palette.dosePendingAccent,
            },
          ]}>
          <FontAwesome name="heart" size={22} color={palette.dosePendingAccent} />
          <Text style={[styles.purposeTitle, { color: palette.text }]} maxFontSizeMultiplier={1.45}>
            {t('medications.questionsPurposeNoteTitle')}
          </Text>
          <Text style={[styles.purposeBody, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.45}>
            {t('medications.questionsPurposeNoteBody')}
          </Text>
        </View>
      </View>

      <Text style={[styles.samePlace, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.45}>
        {t('medications.questionsSamePlace')}
      </Text>

      <View style={[styles.voiceBadge, { backgroundColor: palette.dosePendingBadgeBg }]}>
        <Text style={[styles.voiceBadgeText, { color: palette.dosePendingBadgeText }]} maxFontSizeMultiplier={1.4}>
          {t('medications.questionsVoiceBadge')}
        </Text>
      </View>

      <View
        style={[
          styles.voicePlate,
          {
            backgroundColor: palette.medicationFieldSurface,
            borderColor: palette.medicationFieldBorder,
          },
        ]}>
        <Text style={[styles.voiceCaption, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.45}>
          {voiceHint}
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t('a11y.questionsMic')}
          accessibilityHint={t('voice.permissionBody')}
          onPressIn={onPressIn}
          onPressOut={onPressOut}
          style={({ pressed }) => [
            styles.micOuter,
            {
              backgroundColor: recording ? palette.tint : palette.voiceButtonBg,
              borderColor: palette.voiceButtonBorder,
              opacity: pressed ? 0.92 : 1,
            },
          ]}>
          <FontAwesome name="microphone" size={MIC_ICON} color={palette.onPrimary} />
        </Pressable>
        {voiceWhen ? (
          <Text style={[styles.voiceSaved, { color: palette.tint }]} maxFontSizeMultiplier={1.45}>
            {voiceWhen}
          </Text>
        ) : null}
      </View>

      <View style={styles.dividerRow}>
        <View style={[styles.dividerLine, { backgroundColor: palette.separator }]} />
        <Text style={[styles.dividerText, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.45}>
          {t('medications.questionsOrType')}
        </Text>
        <View style={[styles.dividerLine, { backgroundColor: palette.separator }]} />
      </View>

      <Text style={[styles.inputLabel, { color: palette.text }]} maxFontSizeMultiplier={1.5}>
        {t('medications.questionsTextFieldLabel')}
      </Text>
      <TextInput
        value={noteText}
        onChangeText={setNoteText}
        placeholder={t('medications.questionsPlaceholder')}
        placeholderTextColor={palette.textSecondary}
        multiline
        textAlignVertical="top"
        editable={hydrated}
        style={[
          styles.textArea,
          {
            color: palette.text,
            backgroundColor: palette.medicationFieldSurface,
            borderColor: palette.border,
          },
        ]}
        maxFontSizeMultiplier={1.55}
      />

      <Text style={[styles.typeHint, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.45}>
        {t('medications.questionsTypeHint')}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  shell: {
    borderRadius: 18,
    borderLeftWidth: 5,
    padding: 18,
    marginBottom: 8,
    width: '100%',
    maxWidth: 520,
    alignSelf: 'center',
    borderTopWidth: 1,
    borderRightWidth: 1,
    borderBottomWidth: 1,
  },
  eyebrow: {
    fontSize: fontSize.caption - 2,
    fontWeight: '800',
    letterSpacing: 0.3,
    marginBottom: 6,
  },
  title: {
    fontSize: fontSize.title - 2,
    fontWeight: '800',
    lineHeight: 34,
    marginBottom: 10,
  },
  subtitle: {
    fontSize: fontSize.caption,
    lineHeight: 24,
    marginBottom: 16,
  },
  purposeRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 12,
  },
  purposeCard: {
    flex: 1,
    minWidth: 0,
    borderRadius: 14,
    borderWidth: 2,
    paddingVertical: 12,
    paddingHorizontal: 10,
    alignItems: 'center',
  },
  purposeTitle: {
    fontSize: fontSize.caption + 1,
    fontWeight: '800',
    marginTop: 8,
    marginBottom: 6,
    textAlign: 'center',
  },
  purposeBody: {
    fontSize: fontSize.caption - 3,
    lineHeight: 20,
    textAlign: 'center',
    fontWeight: '600',
  },
  samePlace: {
    fontSize: fontSize.caption - 2,
    lineHeight: 22,
    fontWeight: '700',
    textAlign: 'center',
    marginBottom: 14,
    paddingHorizontal: 4,
  },
  voiceBadge: {
    alignSelf: 'flex-start',
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 10,
    marginBottom: 12,
  },
  voiceBadgeText: {
    fontSize: 15,
    fontWeight: '800',
  },
  voicePlate: {
    borderRadius: 16,
    borderWidth: 1,
    paddingVertical: 16,
    paddingHorizontal: 14,
    alignItems: 'center',
  },
  voiceCaption: {
    fontSize: fontSize.caption - 1,
    fontWeight: '700',
    textAlign: 'center',
    marginBottom: 10,
    lineHeight: 22,
  },
  micOuter: {
    width: MIC_SIZE,
    height: MIC_SIZE,
    borderRadius: MIC_SIZE / 2,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    marginBottom: 8,
    minHeight: MIN_TOUCH,
    minWidth: MIN_TOUCH,
  },
  voiceSaved: {
    fontSize: fontSize.caption - 2,
    fontWeight: '700',
    textAlign: 'center',
    lineHeight: 20,
  },
  dividerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 16,
    gap: 10,
  },
  dividerLine: {
    flex: 1,
    height: StyleSheet.hairlineWidth * 2,
  },
  dividerText: {
    fontSize: fontSize.caption - 1,
    fontWeight: '700',
    flexShrink: 0,
  },
  inputLabel: {
    fontSize: fontSize.caption,
    fontWeight: '800',
    marginBottom: 8,
  },
  textArea: {
    minHeight: 150,
    borderWidth: 2,
    borderRadius: 14,
    padding: 16,
    fontSize: fontSize.body,
    lineHeight: 30,
    fontWeight: '600',
  },
  typeHint: {
    fontSize: fontSize.caption - 2,
    lineHeight: 20,
    marginTop: 10,
    fontWeight: '600',
  },
});
