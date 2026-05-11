-- Migration: atomic emergency-contact set-primary function
--
-- Replaces two sequential UPDATEs (demote-others, promote-latest) with a
-- single statement executed inside a Postgres function.  This prevents a
-- concurrent insert from observing a window where multiple rows share
-- is_primary = true.

CREATE OR REPLACE FUNCTION medbuddy_set_emergency_primary(
    p_patient_id UUID,
    p_contact_id UUID
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    -- Set is_primary in a single pass: true for the target row, false for all others.
    UPDATE emergency_contacts
    SET    is_primary = (id = p_contact_id)
    WHERE  patient_id = p_patient_id;
END;
$$;
