import AsyncStorage from '@react-native-async-storage/async-storage';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { Link, Stack, type Href } from 'expo-router';
import * as Speech from 'expo-speech';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Text, View } from '@/components/Themed';
import { fontSize } from '@/constants/accessibility';
import Colors from '@/constants/Colors';
import { useColorScheme } from '@/components/useColorScheme';
import { useVoiceRecording } from '@/hooks/useVoiceRecording';
import {
  fetchMeProfile,
  PENDING_VOICE_HANDOFF_KEY,
  sendCompanionMessage,
  sendCompanionVoiceMessage,
} from '@/lib/companionApi';

type Bubble = {
  role: 'user' | 'assistant';
  text: string;
  /** Backend flag: emergency contact notification was simulated (not a real SMS/call). */
  simulatedEmergencyNotify?: boolean;
};

const SCROLL_PAD = 120;

/** Full-line chat starters; three are reshuffled whenever this screen is opened. */
const ENGAGEMENT_KEYS = [
  'companion.engage.listMeds',
  'companion.engage.askDrug',
  'companion.engage.doctorSummary',
  'companion.engage.interactions',
  'companion.engage.mandarinVoice',
  'companion.engage.familyView',
] as const;

function pickRandomSubset<K>(keys: readonly K[], n: number): K[] {
  const copy = [...keys];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    const tmp = copy[i]!;
    copy[i] = copy[j]!;
    copy[j] = tmp;
  }
  return copy.slice(0, n);
}

const PEEK_ROLL = 0.38;

export default function CompanionScreen() {
  const { t, i18n } = useTranslation();
  const navigation = useNavigation();
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];
  const insets = useSafeAreaInsets();
  const [messages, setMessages] = useState<Bubble[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [starterKeys, setStarterKeys] = useState<readonly string[]>(() =>
    pickRandomSubset(ENGAGEMENT_KEYS, 3)
  );
  const [peekKey, setPeekKey] = useState<(typeof ENGAGEMENT_KEYS)[number] | null>(null);
  const scrollRef = useRef<ScrollView>(null);
  const [profileLocale, setProfileLocale] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchMeProfile()
      .then((p) => {
        if (!cancelled && typeof p.locale === 'string') {
          setProfileLocale(p.locale);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setProfileLocale(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const speechLang =
    profileLocale === 'en'
      ? 'en-US'
      : profileLocale === 'zh-TW'
        ? 'zh-TW'
        : i18n.language.startsWith('zh')
          ? 'zh-TW'
          : 'en-US';

  const speak = useCallback(
    (text: string) => {
      Speech.stop();
      Speech.speak(text, {
        language: speechLang,
        rate: speechLang.startsWith('zh') ? 0.88 : 0.92,
        pitch: 1,
      });
    },
    [speechLang]
  );

  useEffect(
    () => () => {
      void Speech.stop();
    },
    []
  );

  useFocusEffect(
    useCallback(() => {
      setStarterKeys(pickRandomSubset(ENGAGEMENT_KEYS, 3));
      return undefined;
    }, [])
  );

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <Link href={'/doctor-summary' as Href} asChild>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t('companion.visitSummaryA11y')}
            style={({ pressed }) => ({ opacity: pressed ? 0.75 : 1, marginRight: 12, padding: 6 })}>
            <Text style={{ color: palette.tint, fontSize: 16, fontWeight: '700' }} maxFontSizeMultiplier={1.35}>
              {t('companion.visitSummaryLink')}
            </Text>
          </Pressable>
        </Link>
      ),
    });
  }, [navigation, palette.tint, t]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) {
      return;
    }
    setInput('');
    setError(null);
    setPeekKey(null);
    setMessages((prev) => [...prev, { role: 'user', text }]);
    setSending(true);
    try {
      const { reply, metadata } = await sendCompanionMessage(text);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: reply,
          simulatedEmergencyNotify: Boolean(metadata.simulated_emergency_notification),
        },
      ]);
      if (Math.random() < PEEK_ROLL) {
        const pool = ENGAGEMENT_KEYS;
        setPeekKey(pool[Math.floor(Math.random() * pool.length)]!);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : t('companion.errorUnknown');
      setError(msg);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: t('companion.errorAssistant') },
      ]);
    } finally {
      setSending(false);
    }
  }, [input, sending, t]);

  const processVoiceUri = useCallback(
    async (uri: string) => {
      const trimmed = uri.trim();
      if (!trimmed || sending) {
        return;
      }
      setError(null);
      setPeekKey(null);
      setSending(true);
      try {
        const { reply, transcript, metadata } = await sendCompanionVoiceMessage(trimmed);
        setMessages((prev) => [
          ...prev,
          { role: 'user', text: transcript },
          {
            role: 'assistant',
            text: reply,
            simulatedEmergencyNotify: Boolean(metadata.simulated_emergency_notification),
          },
        ]);
        speak(reply);
        if (Math.random() < PEEK_ROLL) {
          const pool = ENGAGEMENT_KEYS;
          setPeekKey(pool[Math.floor(Math.random() * pool.length)]!);
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : t('companion.errorUnknown');
        setError(msg);
        setMessages((prev) => [...prev, { role: 'assistant', text: t('companion.errorAssistant') }]);
      } finally {
        setSending(false);
      }
    },
    [sending, speak, t]
  );

  const { recording: voiceRecording, onPressIn: voicePressIn, onPressOut: voicePressOut } =
    useVoiceRecording({
      onRecordingUri: (uri) => {
        void processVoiceUri(uri);
      },
    });

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      void (async () => {
        const pending = await AsyncStorage.getItem(PENDING_VOICE_HANDOFF_KEY);
        if (!pending || cancelled) {
          return;
        }
        await AsyncStorage.removeItem(PENDING_VOICE_HANDOFF_KEY);
        await processVoiceUri(pending);
      })();
      return () => {
        cancelled = true;
      };
    }, [processVoiceUri])
  );

  const appendSuggestion = (q: string) => {
    setInput((prev) => (prev.trim() ? `${prev.trim()} ${q}` : q));
  };

  return (
    <>
      <Stack.Screen
        options={{
          title: t('companion.title'),
          headerBackTitle: t('tabs.today'),
        }}
      />
      <KeyboardAvoidingView
        style={[styles.flex, { backgroundColor: palette.background }]}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 8 : 0}>
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={[
            styles.scrollContent,
            {
              paddingTop: 12,
              paddingBottom: SCROLL_PAD + insets.bottom,
            },
          ]}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}>
          <Text style={[styles.subtitle, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.55}>
            {t('companion.subtitle')}
          </Text>

          <View style={styles.suggestionsRow} lightColor="transparent" darkColor="transparent">
            {starterKeys.map((key) => (
              <Pressable
                key={key}
                onPress={() => appendSuggestion(t(key))}
                style={({ pressed }) => [
                  styles.suggestionChip,
                  {
                    backgroundColor: palette.voicePanelBg,
                    borderColor: palette.dockBorder,
                    opacity: pressed ? 0.85 : 1,
                  },
                ]}>
                <Text style={styles.suggestionText} maxFontSizeMultiplier={1.45}>
                  {t(key)}
                </Text>
              </Pressable>
            ))}
          </View>

          {messages.map((m, i) => (
            <View
              key={`${m.role}-${i}`}
              style={[
                styles.bubbleWrap,
                m.role === 'user' ? styles.bubbleUser : styles.bubbleAssistant,
              ]}
              lightColor="transparent"
              darkColor="transparent">
              <View
                style={[
                  styles.bubble,
                  m.role === 'user'
                    ? { backgroundColor: palette.tint }
                    : { backgroundColor: palette.voicePanelBg, borderColor: palette.dockBorder },
                ]}>
                <Text
                  style={[
                    styles.bubbleText,
                    { color: m.role === 'user' ? palette.onPrimary : palette.text },
                  ]}
                  maxFontSizeMultiplier={1.6}>
                  {m.text}
                </Text>
                {m.role === 'assistant' ? (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={t('companion.readAloudA11y')}
                    onPress={() => speak(m.text)}
                    style={({ pressed }) => [styles.speakBtn, { opacity: pressed ? 0.75 : 1 }]}>
                    <FontAwesome name="volume-up" size={18} color={palette.tint} />
                    <Text style={[styles.speakLabel, { color: palette.tint }]} maxFontSizeMultiplier={1.4}>
                      {t('companion.readAloud')}
                    </Text>
                  </Pressable>
                ) : null}
                {m.role === 'assistant' && m.simulatedEmergencyNotify ? (
                  <Text
                    style={[styles.simBanner, { color: palette.textSecondary }]}
                    maxFontSizeMultiplier={1.45}>
                    {t('companion.simulatedEmergencyBanner')}
                  </Text>
                ) : null}
              </View>
            </View>
          ))}

          {peekKey ? (
            <View
              style={[styles.peekCard, { backgroundColor: palette.voicePanelBg, borderColor: palette.dockBorder }]}
              lightColor="transparent"
              darkColor="transparent">
              <Text style={[styles.peekHint, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.45}>
                {t('companion.peekHint')}
              </Text>
              <Pressable
                onPress={() => {
                  appendSuggestion(t(peekKey));
                  setPeekKey(null);
                }}
                style={({ pressed }) => [
                  styles.peekChip,
                  {
                    borderColor: palette.dockBorder,
                    backgroundColor: palette.background,
                    opacity: pressed ? 0.9 : 1,
                  },
                ]}>
                <Text style={[styles.peekChipText, { color: palette.text }]} maxFontSizeMultiplier={1.45}>
                  {t(peekKey)}
                </Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                onPress={() => setPeekKey(null)}
                style={({ pressed }) => [styles.peekDismiss, { opacity: pressed ? 0.7 : 1 }]}>
                <Text style={{ color: palette.tint, fontWeight: '600' }} maxFontSizeMultiplier={1.4}>
                  {t('companion.peekDismiss')}
                </Text>
              </Pressable>
            </View>
          ) : null}

          {error ? (
            <Text style={[styles.error, { color: palette.tint }]} maxFontSizeMultiplier={1.45}>
              {t('companion.errorPrefix')} {error}
            </Text>
          ) : null}

          <Text style={[styles.disclaimer, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.45}>
            {t('companion.disclaimer')}
          </Text>
        </ScrollView>

        <View
          style={[
            styles.composer,
            {
              paddingBottom: Math.max(insets.bottom, 12),
              backgroundColor: palette.dockBackground,
              borderTopColor: palette.dockBorder,
            },
          ]}>
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder={t('companion.placeholder')}
            placeholderTextColor={palette.textSecondary}
            multiline
            maxLength={2000}
            editable={!sending}
            style={[
              styles.input,
              {
                color: palette.text,
                borderColor: palette.dockBorder,
                backgroundColor: palette.background,
              },
            ]}
            accessibilityLabel={t('companion.placeholder')}
          />
          {Platform.OS !== 'web' ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={t('companion.voiceMicA11y')}
              accessibilityHint={t('voice.permissionBody')}
              disabled={sending}
              onPressIn={() => {
                void voicePressIn();
              }}
              onPressOut={() => {
                void voicePressOut();
              }}
              style={({ pressed }) => [
                styles.voiceSendBtn,
                {
                  backgroundColor: voiceRecording ? palette.tint : palette.voiceButtonBg,
                  borderColor: palette.voiceButtonBorder,
                  opacity: sending ? 0.45 : pressed ? 0.88 : 1,
                },
              ]}>
              <FontAwesome name="microphone" size={20} color={palette.onPrimary} />
            </Pressable>
          ) : null}
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t('companion.sendA11y')}
            disabled={sending || !input.trim()}
            onPress={() => void send()}
            style={({ pressed }) => [
              styles.sendBtn,
              {
                backgroundColor: palette.tint,
                opacity: sending || !input.trim() ? 0.45 : pressed ? 0.88 : 1,
              },
            ]}>
            {sending ? (
              <ActivityIndicator color={palette.onPrimary} />
            ) : (
              <FontAwesome name="send" size={20} color={palette.onPrimary} />
            )}
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 18,
  },
  subtitle: {
    fontSize: fontSize.caption,
    lineHeight: 26,
    marginBottom: 14,
  },
  suggestionsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 18,
  },
  suggestionChip: {
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    paddingVertical: 10,
    paddingHorizontal: 12,
    maxWidth: '100%',
  },
  suggestionText: {
    fontSize: 15,
    lineHeight: 22,
    fontWeight: '600',
  },
  peekCard: {
    borderRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
    padding: 14,
    marginBottom: 14,
    width: '100%',
  },
  peekHint: {
    fontSize: 14,
    lineHeight: 22,
    marginBottom: 10,
    fontWeight: '600',
  },
  peekChip: {
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    paddingVertical: 10,
    paddingHorizontal: 12,
    marginBottom: 8,
  },
  peekChipText: {
    fontSize: 15,
    lineHeight: 22,
    fontWeight: '600',
  },
  peekDismiss: {
    alignSelf: 'flex-start',
    paddingVertical: 4,
  },
  bubbleWrap: {
    marginBottom: 12,
    width: '100%',
  },
  bubbleUser: {
    alignItems: 'flex-end',
  },
  bubbleAssistant: {
    alignItems: 'flex-start',
  },
  bubble: {
    maxWidth: '92%',
    borderRadius: 18,
    paddingVertical: 14,
    paddingHorizontal: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'transparent',
  },
  bubbleText: {
    fontSize: fontSize.body,
    lineHeight: 28,
  },
  speakBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 12,
  },
  speakLabel: {
    fontSize: 15,
    fontWeight: '700',
  },
  simBanner: {
    fontSize: 12,
    lineHeight: 18,
    marginTop: 10,
    fontStyle: 'italic',
  },
  error: {
    fontSize: 14,
    marginTop: 8,
    marginBottom: 8,
  },
  disclaimer: {
    fontSize: 13,
    lineHeight: 22,
    marginTop: 20,
  },
  composer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 10,
    paddingHorizontal: 14,
    paddingTop: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  input: {
    flex: 1,
    minHeight: 48,
    maxHeight: 120,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: fontSize.body,
    lineHeight: 24,
  },
  sendBtn: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  voiceSendBtn: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
  },
});
