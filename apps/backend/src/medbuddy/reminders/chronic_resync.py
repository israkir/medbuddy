"""Daily chronic-medication reminder resync.

Indefinite / lifelong meds (``medications.is_indefinite = true``) keep their reminders
firing forever via the same rolling-window architecture finite meds use. The window
is refilled by **two** mechanisms:

1. This module's :func:`resync_all_indefinite_patients` runs once daily from the arq
   worker cron (primary path) — see ``medbuddy.reminders.worker.resync_chronic_meds_cron``.
2. A delivery-time safety net in :func:`medbuddy.reminders.deliver.deliver_dose_reminder`
   tops up the window for one med when its remaining future events fall below a
   small threshold.

Both call :func:`medbuddy.reminders.lifecycle.sync_and_enqueue_reminders`, the same
hook used when a user mutates a medication, so all materialization + enqueue logic
stays in one place.
"""

from __future__ import annotations

import logging

from medbuddy.reminders.lifecycle import sync_and_enqueue_reminders
from medbuddy.services import AppServices

log = logging.getLogger(__name__)


async def resync_all_indefinite_patients(svc: AppServices) -> int:
    """Refresh dose_events for every patient with at least one chronic medication.

    Returns the number of patients resynced. Errors for one patient are logged and
    do not abort the batch (medical reminders for other users keep flowing).
    """
    try:
        user_keys = await svc.users.list_patients_with_indefinite_medications()
    except Exception:
        log.exception("chronic_resync: failed to list patients with indefinite medications")
        return 0
    if not user_keys:
        log.info("chronic_resync: no patients with indefinite medications")
        return 0

    resynced = 0
    failed = 0
    for user_key in user_keys:
        try:
            await sync_and_enqueue_reminders(svc, user_key)
            resynced += 1
        except Exception:
            failed += 1
            log.exception(
                "chronic_resync: sync_and_enqueue_reminders failed for user_key=%s", user_key
            )
    log.info(
        "chronic_resync: completed patients=%d resynced=%d failed=%d",
        len(user_keys),
        resynced,
        failed,
    )
    return resynced
