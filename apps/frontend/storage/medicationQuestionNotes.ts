import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY_TEXT = '@medbuddy/medication_question_text_v1';
const KEY_VOICE_AT = '@medbuddy/medication_question_voice_at_v1';

export async function loadQuestionText(): Promise<string> {
  try {
    const v = await AsyncStorage.getItem(KEY_TEXT);
    return v ?? '';
  } catch {
    return '';
  }
}

export async function saveQuestionText(text: string): Promise<void> {
  await AsyncStorage.setItem(KEY_TEXT, text);
}

export async function loadVoiceSavedAt(): Promise<string | null> {
  try {
    return await AsyncStorage.getItem(KEY_VOICE_AT);
  } catch {
    return null;
  }
}

export async function saveVoiceSavedAt(iso: string): Promise<void> {
  await AsyncStorage.setItem(KEY_VOICE_AT, iso);
}
