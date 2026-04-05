import * as Speech from 'expo-speech';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

export type MedicationExplanationId = 'metformin' | 'bp' | 'statin';

export function useMedicationExplanations() {
  const { t, i18n } = useTranslation();
  const [playing, setPlaying] = useState<MedicationExplanationId | null>(null);

  const speak = useCallback(
    (text: string, onDone: () => void) => {
      Speech.stop();
      Speech.speak(text, {
        language: i18n.language.startsWith('zh') ? 'zh-TW' : 'en-US',
        rate: i18n.language.startsWith('zh') ? 0.88 : 0.92,
        pitch: 1,
        onDone,
        onStopped: onDone,
        onError: onDone,
      });
    },
    [i18n.language]
  );

  const explain = useCallback(
    (id: MedicationExplanationId) => {
      const key =
        id === 'metformin'
          ? 'medications.sampleExplanation'
          : id === 'bp'
            ? 'medications.sampleBpExplanation'
            : 'medications.sampleStatinExplanation';
      setPlaying(id);
      speak(t(key), () => setPlaying(null));
    },
    [speak, t]
  );

  useEffect(
    () => () => {
      void Speech.stop();
    },
    []
  );

  /** True while any explanation is playing — disable other Listen buttons. */
  const listenBusy = playing !== null;

  return { playing, explain, listenBusy };
}
