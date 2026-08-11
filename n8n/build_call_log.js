const raw = $input.first().json;
const body = raw.body || raw;
const args = body.args || {};

function normPhone(p) {
  const d = String(p || '').replace(/\D/g, '');
  if (!d) return '';
  if (d.length === 10) return '91' + d;
  return d;
}

function shorten(t, limit = 120) {
  const s = String(t || '').replace(/\s+/g, ' ').trim();
  if (s.length <= limit) return s;
  return s.slice(0, limit - 1).trim() + '…';
}

const SPANISH_MARKERS = ['sí', 'si ', 'hasta que', 'problema', 'solucione', 'tengo', ' que se ', ' el ', ' la '];
const ENTERTAINMENT_MARKERS = ['movie', 'film', 'devdas', 'song', 'video clip', 'trailer'];
const BUSINESS_KEYWORDS = [
  'app', 'website', 'web', 'software', 'development', 'marketing', 'digital', 'crm', 'whatsapp',
  'resilio', 'price', 'pricing', 'cost', 'quote', 'demo', 'service', 'mobile', 'android', 'ios',
  'design', 'appointment', 'book', 'lead', 'project',
];
const FAREWELL = /^(thanks|thank you|bye|goodbye|ok bye|theek hai|shukriya)/i;

function hasDevanagari(text) {
  return /[\u0900-\u097f]/.test(String(text || ''));
}

function isSttNoise(text) {
  const t = String(text || '').replace(/\s+/g, ' ').trim();
  if (!t) return true;
  const low = t.toLowerCase();
  if (SPANISH_MARKERS.filter((m) => low.includes(m)).length >= 2) return true;
  if (ENTERTAINMENT_MARKERS.some((m) => low.includes(m))) return true;
  if (/\b(movie|film)\b/.test(low) && !/(about|promo|marketing)/.test(low)) return true;
  const words = low.split(/\s+/);
  if (
    words.length <= 2 &&
    t.length < 16 &&
    !BUSINESS_KEYWORDS.some((k) => low.includes(k)) &&
    !/^[A-Za-z]{2,}(\s+[A-Za-z]{2,})?$/.test(t)
  ) {
    return true;
  }
  return false;
}

function callerQuality(text) {
  const t = String(text || '').replace(/\s+/g, ' ').trim();
  if (!t || FAREWELL.test(t) || isSttNoise(t)) return 0;
  const low = t.toLowerCase();
  let score = 0;
  if (BUSINESS_KEYWORDS.some((k) => low.includes(k))) score += 4;
  if (t.includes('?')) score += 2;
  if (/\b(my name|mera naam|naam hai|i am|this is)\b/i.test(low)) score += 3;
  const words = t.split(/\s+/);
  if (words.length >= 3 && words.length <= 24) score += 2;
  if (SPANISH_MARKERS.some((m) => low.includes(m))) score -= 3;
  return score;
}

function meaningfulCaller(text) {
  return callerQuality(text) >= 3;
}

function poorSummary(text) {
  const s = String(text || '').trim();
  if (!s || s.length > 420) return true;
  const low = s.toLowerCase();
  if (low.includes('caller said:') || low.includes('agent explained:')) return true;
  if (/caller:/i.test(s) || /agent:/i.test(s)) return true;
  if (low.includes('they said they wanted') && (low.includes('hasta que') || low.includes('movie') || hasDevanagari(s))) {
    return true;
  }
  if (low.includes('responded:') && hasDevanagari(s)) return true;
  if ((low.match(/they also asked/g) || []).length >= 2) return true;
  if (s.split('\n').filter(Boolean).length > 1) return true;
  return false;
}

function coalesceEntries(entries) {
  const out = [];
  for (const e of entries) {
    if (!e || !e.text) continue;
    const text = String(e.text).replace(/\s+/g, ' ').trim();
    if (!text) continue;
    if (out.length && out[out.length - 1].role === e.role) {
      const prev = out[out.length - 1].text;
      if (text.startsWith(prev)) out[out.length - 1].text = text;
      else if (prev.startsWith(text)) continue;
      else out[out.length - 1].text = `${prev} ${text}`.trim();
    } else out.push({ role: e.role, text });
  }
  return out;
}

function parseConversation(conversationFull) {
  const lines = String(conversationFull || '')
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);
  const entries = lines
    .map((l) => {
      if (l.startsWith('Caller:')) return { role: 'user', text: l.slice(7).trim() };
      if (l.startsWith('Agent:')) return { role: 'assistant', text: l.slice(6).trim() };
      return null;
    })
    .filter(Boolean);
  return entries;
}

function userLinesForSummary(entries) {
  const lines = [];
  const seen = new Set();
  for (const e of entries) {
    if (e.role !== 'user') continue;
    const text = String(e.text || '').replace(/\s+/g, ' ').trim();
    if (!text || isSttNoise(text)) continue;
    const key = text.toLowerCase().slice(0, 100);
    if (seen.has(key)) continue;
    seen.add(key);
    lines.push(text);
  }
  return lines;
}

function inferTopic(topicArg, userBlob) {
  let t = String(topicArg || '').trim().replace(/\s+lead\s*$/i, '');
  if (t && !/^general enquir/i.test(t)) return t;
  const b = userBlob.toLowerCase();
  const checks = [
    [['digital marketing', 'marketing', 'seo'], 'Digital marketing'],
    [['appointment', 'book a', 'booking'], 'Appointment booking'],
    [['website', 'web design', 'web development'], 'Website / web development'],
    [['mobile app', 'android', 'ios app', 'application'], 'Mobile app development'],
    [['crm', 'whatsapp crm'], 'CRM / WhatsApp CRM'],
    [['demo'], 'Product demo'],
    [['price', 'pricing', 'cost', 'quote'], 'Pricing enquiry'],
    [['callback', 'call back'], 'Callback request'],
  ];
  for (const [keys, label] of checks) {
    if (keys.some((k) => b.includes(k))) return label;
  }
  return t || 'General enquiry';
}

function extractCallerName(entries) {
  const blob = userLinesForSummary(entries).join(' ');
  const patterns = [
    /(?:my name is|i am|i'm|this is)\s+([A-Za-z][A-Za-z\s.'-]{2,40})/i,
    /(?:mera naam|naam hai|mera name)\s+([A-Za-z][A-Za-z\s.'-]{2,40})/i,
  ];
  for (const pat of patterns) {
    const m = blob.match(pat);
    if (m && m[1] && !isSttNoise(m[1])) return m[1].trim().replace(/\b\w/g, (c) => c.toUpperCase());
  }
  return '';
}

function intentPhrases(text) {
  const low = String(text || '').toLowerCase();
  const found = [];
  const mapping = [
    [['mobile app', 'android app', 'ios app'], 'mobile app development'],
    [['website', 'web design', 'web development'], 'website development'],
    [['software'], 'software development'],
    [['digital marketing', 'marketing', 'seo'], 'digital marketing'],
    [['whatsapp crm', 'crm'], 'WhatsApp CRM'],
    [['resilio', 'resilience'], 'ResilioHub platform'],
    [['price', 'pricing', 'cost', 'quote'], 'pricing'],
    [['demo'], 'a product demo'],
    [['callback', 'call back'], 'a callback'],
  ];
  for (const [keys, label] of mapping) {
    if (keys.some((k) => low.includes(k)) && !found.includes(label)) found.push(label);
  }
  return found;
}

function collectCallerIntents(entries) {
  const intents = [];
  const seen = new Set();
  for (const text of userLinesForSummary(entries)) {
    if (!meaningfulCaller(text)) continue;
    for (const phrase of intentPhrases(text)) {
      const key = phrase.toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        intents.push(phrase);
      }
    }
  }
  return intents;
}

function summarizeAgent(entries) {
  const blocks = entries
    .filter((e) => e.role === 'assistant' && String(e.text || '').length > 15 && !FAREWELL.test(e.text))
    .map((e) => String(e.text));
  if (!blocks.length) return '';
  const combined = blocks.join(' ').toLowerCase();
  const services = [];
  if (/software|development|develop|सॉफ्ट/.test(combined)) services.push('software development');
  if (/web|website|वेब|design/.test(combined)) services.push('web design');
  if (/app|mobile|android|ios|ऐप/.test(combined)) services.push('mobile apps');
  if (/marketing|digital|मार्केट/.test(combined)) services.push('digital marketing');
  if (services.length) {
    return `The AI receptionist explained that the company offers ${services.join(', ')} and asked what the caller needed.`;
  }
  if (/price|pricing|cost|quote|₹|rupee|कीमत/.test(combined)) {
    return 'The AI receptionist shared pricing details with the caller.';
  }
  return 'The AI receptionist answered the caller\'s questions and offered to help further.';
}

function narrateCall(topic, conversationFull, nextStep, outcome, args) {
  const entries = parseConversation(conversationFull);
  const userBlob = userLinesForSummary(entries).join(' ');
  const topicLabel = inferTopic(topic, userBlob);
  const topicPhrase = topicLabel !== 'General enquiry' ? topicLabel.toLowerCase() : 'a general enquiry';
  const name = extractCallerName(entries);
  const intents = collectCallerIntents(entries);

  const sentences = [];
  sentences.push(name ? `${name} called regarding ${topicPhrase}.` : `A caller contacted the company regarding ${topicPhrase}.`);

  const topicNorm = topicLabel.toLowerCase();
  const deduped = intents.filter((i) => !topicNorm.includes(i.toLowerCase()) && !i.toLowerCase().includes(topicNorm));
  const use = deduped.length ? deduped : intents.slice(0, 1);
  if (use.length === 1 && !topicNorm.includes(use[0].toLowerCase())) {
    sentences.push(`They enquired about ${use[0]}.`);
  } else if (use.length > 1) {
    sentences.push(`They enquired about ${use[0]} and also asked about ${use[1]}.`);
  } else if (topicLabel !== 'General enquiry') {
    sentences.push(`The main topic of the call was ${topicPhrase}.`);
  } else {
    sentences.push('Few clear details were captured from the caller\'s speech.');
  }

  const agentLine = summarizeAgent(entries);
  if (agentLine) sentences.push(agentLine);

  if (args.appointment_booked === true || args.appointment_booked === 'yes') {
    sentences.push('An appointment was booked during the call.');
  } else if (args.lead_captured === true || args.lead_captured === 'yes') {
    sentences.push('The caller\'s details were captured as a sales lead for follow-up.');
  } else if (nextStep && nextStep !== 'None') {
    sentences.push(`Recommended next step: ${String(nextStep).toLowerCase()}.`);
  }

  const oc = String(outcome || '').toLowerCase();
  if (oc && !oc.includes('hangup')) {
    if (oc.includes('thanks') || oc.includes('goodbye')) sentences.push('The caller ended the conversation politely.');
    else if (oc.includes('silence')) sentences.push('The call ended after a period of silence.');
    else if (oc.includes('completed') || oc.includes('request completed')) {
      sentences.push('The call ended after the caller\'s request was handled.');
    } else if (oc.includes('hung up')) sentences.push('The caller hung up before finishing the discussion.');
    else sentences.push(`The call ended (${oc}).`);
  }

  return sentences.join(' ').slice(0, 480).trim();
}

const from = normPhone(body.from || args.caller_phone || args.caller);
const callId = String(body.call_id || args.call_id || `CALL-${Date.now()}`);
let summary = String(args.summary || '').trim();
const topic = String(args.topic || args.caller_intent || 'General enquiry').trim();
let nextStep = String(args.next_step || '').trim();
const conversationFull = String(args.conversation_full || args.transcript || '').trim();
const durationSec = Number(args.duration_sec || 0);
const duration = args.duration || (durationSec ? `${durationSec} sec` : '');
const date = args.date || new Date().toISOString().slice(0, 10);
const timeIst = args.time_ist || args.time || '';
const business = body.business_name || 'ResilienceSoft';
const notify = normPhone(args.notify_whatsapp || body.notify_whatsapp || '');
const outcome = args.outcome || args.reason || 'Ended';
const turns =
  Number(args.transcript_turns || args.turns || 0) ||
  (conversationFull ? conversationFull.split('\n').filter(Boolean).length : 0);

if (!nextStep) {
  if (args.appointment_booked === 'yes') nextStep = 'Appointment booked';
  else if (args.lead_captured === 'yes') nextStep = 'Lead — call back';
  else if (args.follow_up === 'callback') nextStep = 'Callback needed';
  else if (args.follow_up === 'team_notified') nextStep = 'Team notified';
  else nextStep = 'None';
}

const narrative = narrateCall(topic, conversationFull, nextStep, outcome, args);
summary = narrative || summary;
if (poorSummary(summary)) summary = narrative;

const ocLow = String(outcome || '').toLowerCase();
const isCallback =
  ocLow.includes('callback') ||
  String(nextStep || '').toLowerCase().includes('call customer back');

const waLines = isCallback
  ? [
      `⚠️ *${business} — CALL BACK NOW*`,
      `Customer: ${from || 'unknown'}`,
      `${date}${timeIst ? ' · ' + timeIst : ''} · ${duration}`,
      `Topic: ${inferTopic(topic, conversationFull.toLowerCase())}`,
      '',
      summary,
      '',
      `Please call the customer back on ${from || 'the number above'} (not via Plivo).`,
    ]
  : [
      `📞 *${business} — Call*`,
      `${date}${timeIst ? ' · ' + timeIst : ''} · ${duration}`,
      `Caller: ${from || 'unknown'}`,
      `Topic: ${inferTopic(topic, conversationFull.toLowerCase())}`,
      `Next: ${nextStep}`,
      '',
      summary,
    ];
const waText = waLines.join('\n').trim();

const waBody = notify
  ? {
      messageObject: {
        messaging_product: 'whatsapp',
        to: notify,
        type: 'text',
        text: { body: waText },
      },
      enableLog: true,
    }
  : null;

return [
  {
    json: {
      call_id: callId,
      date,
      time: timeIst,
      caller: from,
      duration,
      topic: inferTopic(topic, conversationFull.toLowerCase()),
      summary,
      next_step: nextStep,
      turns,
      transcript: conversationFull,
      notify_whatsapp: notify,
      waBody,
      hasWhatsApp: !!waBody,
    },
  },
];
