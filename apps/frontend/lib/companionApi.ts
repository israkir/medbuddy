import i18next from '@/i18n';
import {
  apiBaseUrl,
  appUserId,
  mobileBearerToken,
  useMockData,
} from '@/constants/integration';

function mockReply(userText: string): string {
  const t = i18next.t.bind(i18next);
  const low = userText.toLowerCase();
  const isZh = i18next.language.startsWith('zh');
  const together =
    /together|interaction|mix|併用|一起|同時|交互/i.test(userText) ||
    (/一起/.test(userText) && /藥/.test(userText));
  if (together) {
    return t('companion.mockInteraction');
  }
  if (
    /metformin|二甲|雙胍|血糖|aspirin|阿斯匹靈|血壓|statin|膽固醇|cholesterol|bp\b/i.test(
      low + userText
    )
  ) {
    return t('companion.mockDrugDetail');
  }
  if (isZh && (/什麼|做什麼|為什麼|用法|怎麼/.test(userText) || /解釋|說明/.test(userText))) {
    return t('companion.mockDrugDetail');
  }
  if (!isZh && (/what|why|how|explain|purpose/.test(low) || /dose|timing/.test(low))) {
    return t('companion.mockDrugDetail');
  }
  return t('companion.mockGeneric');
}

/**
 * One assistant turn for medication comprehension (backend assistant or offline mock).
 */
export async function sendCompanionMessage(text: string): Promise<string> {
  const trimmed = text.trim();
  if (!trimmed) {
    return '';
  }
  if (useMockData) {
    await Promise.resolve();
    return mockReply(trimmed);
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-App-User-Id': appUserId,
  };
  if (mobileBearerToken) {
    headers.Authorization = `Bearer ${mobileBearerToken}`;
  }

  const r = await fetch(`${apiBaseUrl}/v1/app/messages`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ text: trimmed }),
  });

  if (!r.ok) {
    const body = await r.text();
    throw new Error(body || `${r.status} ${r.statusText}`);
  }

  const data = (await r.json()) as { reply: string };
  return data.reply ?? '';
}
