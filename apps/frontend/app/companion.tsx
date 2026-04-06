import FontAwesome from '@expo/vector-icons/FontAwesome';
import { Stack } from 'expo-router';
import * as Speech from 'expo-speech';
import { useCallback, useEffect, useRef, useState } from 'react';
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
import { sendCompanionMessage } from '@/lib/companionApi';

type Bubble = { role: 'user' | 'assistant'; text: string };

const SCROLL_PAD = 120;

export default function CompanionScreen() {
  const { t, i18n } = useTranslation();
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];
  const insets = useSafeAreaInsets();
  const [messages, setMessages] = useState<Bubble[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<ScrollView>(null);
  const speechLang = i18n.language.startsWith('zh') ? 'zh-TW' : 'en-US';

  const speak = useCallback(
    (text: string) => {
      Speech.stop();
      Speech.speak(text, {
        language: speechLang,
        rate: i18n.language.startsWith('zh') ? 0.88 : 0.92,
        pitch: 1,
      });
    },
    [i18n.language, speechLang]
  );

  useEffect(
    () => () => {
      void Speech.stop();
    },
    []
  );

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) {
      return;
    }
    setInput('');
    setError(null);
    setMessages((prev) => [...prev, { role: 'user', text }]);
    setSending(true);
    try {
      const reply = await sendCompanionMessage(text);
      setMessages((prev) => [...prev, { role: 'assistant', text: reply }]);
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
            {[t('companion.suggested1'), t('companion.suggested2'), t('companion.suggested3')].map(
              (label) => (
                <Pressable
                  key={label}
                  onPress={() => appendSuggestion(label)}
                  style={({ pressed }) => [
                    styles.suggestionChip,
                    {
                      backgroundColor: palette.voicePanelBg,
                      borderColor: palette.dockBorder,
                      opacity: pressed ? 0.85 : 1,
                    },
                  ]}>
                  <Text style={styles.suggestionText} maxFontSizeMultiplier={1.45}>
                    {label}
                  </Text>
                </Pressable>
              )
            )}
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
              </View>
            </View>
          ))}

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
});
