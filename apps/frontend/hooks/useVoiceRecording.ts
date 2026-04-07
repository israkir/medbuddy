import { Audio } from 'expo-av';
import * as Haptics from 'expo-haptics';
import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Platform } from 'react-native';

export type VoiceRecordingOptions = {
  /** Called after a recording is successfully stopped (before the result alert). */
  onRecordingComplete?: () => void;
  /**
   * When set, receives the local file URI after stop; skips the default "saved" alert
   * so the caller can upload or hand off the clip (e.g. Medication helper).
   */
  onRecordingUri?: (uri: string) => void;
};

export function useVoiceRecording(options?: VoiceRecordingOptions) {
  const onRecordingComplete = options?.onRecordingComplete;
  const onRecordingUri = options?.onRecordingUri;
  const { t } = useTranslation();
  const [recording, setRecording] = useState(false);
  const recordingRef = useRef<Audio.Recording | null>(null);

  const ensurePermission = useCallback(async () => {
    if (Platform.OS === 'web') {
      Alert.alert(t('appName'), t('voice.webUnavailable'));
      return false;
    }
    const { status } = await Audio.requestPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert(t('voice.permissionTitle'), t('voice.permissionBody'));
      return false;
    }
    await Audio.setAudioModeAsync({
      allowsRecordingIOS: true,
      playsInSilentModeIOS: true,
    });
    return true;
  }, [t]);

  const onPressIn = useCallback(async () => {
    const ok = await ensurePermission();
    if (!ok) {
      return;
    }
    try {
      if (Platform.OS === 'ios') {
        void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      }
      const rec = new Audio.Recording();
      await rec.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      await rec.startAsync();
      recordingRef.current = rec;
      setRecording(true);
    } catch {
      Alert.alert(t('appName'), t('voice.recordError'));
    }
  }, [ensurePermission, t]);

  const onPressOut = useCallback(async () => {
    const rec = recordingRef.current;
    if (!rec) {
      setRecording(false);
      return;
    }
    recordingRef.current = null;
    try {
      await rec.stopAndUnloadAsync();
      const uri = rec.getURI() ?? '';
      setRecording(false);
      if (Platform.OS === 'ios') {
        void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }
      onRecordingComplete?.();
      if (onRecordingUri && uri) {
        onRecordingUri(uri);
      } else {
        Alert.alert(t('voice.resultTitle'), t('voice.resultBody'));
      }
    } catch {
      setRecording(false);
    }
  }, [onRecordingComplete, onRecordingUri, t]);

  return { recording, onPressIn, onPressOut };
}
