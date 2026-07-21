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

function poorSummary(text) {
  const s = String(text || '').trim();
  if (!s || s.length > 420) return true;
  const low = s.toLowerCase();
  if (low.includes('caller said:') || low.includes('agent explained:') || low.includes('agent covered:')) return true;
  if (low.includes('key ask:') || low.includes('caller wanted:') || low.includes('agent shared:')) return true;
  if (/caller:/i.test(s) || /agent:/i.test(s)) return true;
  if ((low.match(/they also asked/g) || []).length >= 2) return true;
  if (/they (also )?asked about \w+\./i.test(low)) return true;
  if (s.includes('|') && s.split('|').length >= 4) return true;
  if (s.startsWith('[') && low.includes('turns]')) return true;
  if (s.split('\n').filter(Boolean).length > 1) return true;
  return false;
}

const FAREWELL = /^(thanks|thank you|bye|goodbye|ok bye|theek hai|shukriya)/i;

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

function meaningfulCaller(text) {
  const t = String(text || '').replace(/\s+/g, ' ').trim();
  if (!t || FAREWELL.test(t)) return false;
  const words = t.split(/\s+/);
  if (words.length >= 3) return true;
  if (t.length >= 20) return true;
  if (t.includes('?')) return true;
  if (words.length === 1 && words[0].length < 10) return false;
  if (t.length < 14) return false;
  return true;
}

function inferTopic(topicArg, userBlob) {
  const t = String(topicArg || '').trim();
  if (t && !/^general enquir/i.test(t)) return t;
  const b = userBlob.toLowerCase();
  const checks = [
    [['digital marketing', 'marketing', 'seo', 'social media'], 'Digital marketing'],
    [['appointment', 'book a', 'booking', 'schedule'], 'Appointment booking'],
    [['website', 'web design', 'web development'], 'Website / web development'],
    [['mobile app', 'android', 'ios app'], 'Mobile app'],
    [['crm', 'whatsapp crm'], 'CRM / WhatsApp CRM'],
    [['hosting', 'domain'], 'Hosting'],
    [['demo'], 'Product demo'],
    [['price', 'pricing', 'cost', 'quote'], 'Pricing enquiry'],
    [['callback', 'call back'], 'Callback request'],
  ];
  for (const [keys, label] of checks) {
    if (keys.some((k) => b.includes(k))) return label;
  }
  return t || 'General enquiry';
}

function cleanupStt(text) {
  let t = String(text || '').replace(/\s+/g, ' ').trim();
  t = t.replace(/\bappoint\s+ment\b/gi, 'appointment');
  t = t.replace(/\bdigi\s+tal\b/gi, 'digital');
  t = t.replace(/\bmark\s+eting\b/gi, 'marketing');
  return t;
}

function naturalRequest(text) {
  let t = cleanupStt(text);
  t = t.replace(
    /^(hi|hello|hey|yes|yeah|ok|okay|namaste|i want to|i want|i need to|i need|please|can you|could you|tell me|mujhe|main|want to|want)\s+/i,
    '',
  ).trim();
  if (!t) t = cleanupStt(text);
  if (t.length > 1) t = t.charAt(0).toLowerCase() + t.slice(1);
  return shorten(t, 160);
}

function embedAnswer(text) {
  let t = shorten(text, 130).replace(/\.$/, '').trim();
  if (!t) return 'responded briefly';
  const low = t.charAt(0).toLowerCase() + t.slice(1);
  if (/^(we |our |yes|no |the |i |haan|ji |sure)/i.test(low)) return `explained that ${low}`;
  return `responded: ${low}`;
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
  return coalesceEntries(entries);
}

function narrateCall(topic, conversationFull, nextStep, outcome, args) {
  const coalesced = parseConversation(conversationFull);
  const userBlob = coalesced
    .filter((e) => e.role === 'user')
    .map((e) => e.text)
    .join(' ');
  const topicLabel = inferTopic(topic, userBlob);
  const topicPhrase = topicLabel !== 'General enquiry' ? topicLabel.toLowerCase() : 'their enquiry';

  const userBlocks = coalesced.filter((e) => e.role === 'user' && meaningfulCaller(e.text)).map((e) => e.text);
  const agentBlocks = coalesced.filter(
    (e) => e.role === 'assistant' && e.text.length > 18 && !FAREWELL.test(e.text),
  ).map((e) => e.text);

  const sentences = [`The caller contacted the company regarding ${topicPhrase}.`];

  if (userBlocks.length) {
    const main = naturalRequest(userBlocks[0]);
    if (userBlocks.length > 1) {
      const extra = naturalRequest(userBlocks.slice(1, 3).join(' '));
      if (extra && !main.includes(extra)) {
        sentences.push(`They said they wanted ${main}, and also mentioned ${extra}.`);
      } else sentences.push(`They said they wanted ${main}.`);
    } else if (main.endsWith('?')) sentences.push(`They asked ${main}`);
    else sentences.push(`They said they wanted ${main}.`);
  } else {
    sentences.push('The conversation was very short and few details were captured.');
  }

  if (agentBlocks.length) {
    let best = agentBlocks[agentBlocks.length - 1];
    for (const line of agentBlocks) if (line.length > best.length) best = line;
    sentences.push(`The receptionist ${embedAnswer(best)}.`);
  }

  if (args.appointment_booked === true || args.appointment_booked === 'yes') {
    sentences.push('An appointment was booked during the call.');
  } else if (args.lead_captured === true || args.lead_captured === 'yes') {
    sentences.push("The agent captured the caller's details for a follow-up call.");
  } else if (nextStep && nextStep !== 'None') {
    sentences.push(`Next step for the team: ${String(nextStep).toLowerCase()}.`);
  }

  const oc = String(outcome || '').toLowerCase();
  if (oc && !oc.includes('hangup')) {
    if (oc.includes('thanks') || oc.includes('goodbye')) sentences.push('The caller ended the conversation politely.');
    else if (oc.includes('silence')) sentences.push('The call ended after a period of silence.');
    else if (oc.includes('hung up')) sentences.push('The caller hung up before finishing the discussion.');
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

const waText = [
  `📞 *${business} — Call*`,
  `${date}${timeIst ? ' · ' + timeIst : ''} · ${duration}`,
  `Caller: ${from || 'unknown'}`,
  `Topic: ${topic}`,
  `Next: ${nextStep}`,
  '',
  summary,
].join('\n').trim();

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
      topic,
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
