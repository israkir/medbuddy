import type { MedicationExplanationId } from '@/hooks/useMedicationExplanations';

/** Prototype rows — replace with API / local storage later. */
export const MEDICATION_LIST: { id: MedicationExplanationId; remaining: number }[] = [
  { id: 'metformin', remaining: 28 },
  { id: 'bp', remaining: 14 },
  { id: 'statin', remaining: 30 },
];
