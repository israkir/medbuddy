import React, { createContext, useContext } from 'react';

import { useMedicationExplanations } from '@/hooks/useMedicationExplanations';

type Value = ReturnType<typeof useMedicationExplanations>;

const MedicationExplanationContext = createContext<Value | null>(null);

export function MedicationExplanationProvider({ children }: { children: React.ReactNode }) {
  const value = useMedicationExplanations();
  return (
    <MedicationExplanationContext.Provider value={value}>{children}</MedicationExplanationContext.Provider>
  );
}

export function useSharedMedicationExplanations(): Value {
  const v = useContext(MedicationExplanationContext);
  if (!v) {
    throw new Error('useSharedMedicationExplanations must be used within MedicationExplanationProvider');
  }
  return v;
}
