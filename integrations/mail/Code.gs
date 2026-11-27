// Optional relay for store-originated restock emails. No store polling.
const HANDLER = 'relayStockMail';

function config_() {
  const p = PropertiesService.getScriptProperties();
  const token = p.getProperty('BOT_TOKEN') || '';
  const chat = p.getProperty('CHAT_ID') || '';
  const label = p.getProperty('MAIL_LABEL') || 'avail-stock';
  const senders = (p.getProperty('ALLOWED_SENDERS') || '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
  if (!/^\d+:[A-Za-z0-9_-]{20,}$/.test(token) || !/^\d+$/.test(chat)) throw new Error('Set BOT_TOKEN and private CHAT_ID in Script Properties.');
  if (!/^[A-Za-z0-9_-]{1,50}$/.test(label) || !senders.length || senders.some(s => !/^[a-z0-9._+-]+@[a-z0-9.-]+\.[a-z]{2,}$/i.test(s))) throw new Error('Set a dedicated Gmail label and exact verified sender addresses.');
  return {p,token,chat,label,senders};
}

function sender_(from) {
  const match = String(from).match(/<([^<>]+)>\s*$/);
  return (match ? match[1] : from).trim().toLowerCase();
}

function notification_(subject) {
  return 'avail | Mağaza bildirimi\n' + String(subject || '(Konusuz)').replace(/[\r\n\u0000-\u001f]/g,' ').slice(0,300) + '\nMağazanın kendi e-postasıdır. Canlı stok ayrıca doğrulanmadı. Alışveriş uygulamasını kontrol et.';
}

function send_(c, text) {
  let response;
  try {
    response = UrlFetchApp.fetch('https://api.telegram.org/bot' + c.token + '/sendMessage', {
      method:'post', contentType:'application/json',
      payload:JSON.stringify({chat_id:c.chat,text,link_preview_options:{is_disabled:true}}),
      muteHttpExceptions:true, followRedirects:false
    });
  } catch (_) { throw new Error('Telegram request failed'); }
  let result;
  try { result = JSON.parse(response.getContentText()); } catch (_) { throw new Error('Invalid Telegram response'); }
  if (response.getResponseCode() !== 200 || !result.ok) throw new Error('Telegram delivery failed');
}

function relayStockMail() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return;
  try {
    const c = config_();
    const now = Date.now();
    const cutoff = Number(c.p.getProperty('START_AT'));
    if (!Number.isFinite(cutoff) || cutoff <= 0) throw new Error('Run installRelay first.');
    const lowerBound = Math.max(cutoff, now - 48*60*60*1000);
    const threads = GmailApp.search('label:' + c.label + ' newer_than:2d',0,100);
    const seen = c.p.getProperties();
    Object.keys(seen).forEach(k => { if(k.startsWith('sent:') && Number(seen[k]) < now - 3*86400000) c.p.deleteProperty(k); });
    let count=0;
    for(const thread of threads) {
      for(const message of thread.getMessages()) {
        if (count >= 20) return;
        if (message.getDate().getTime() < lowerBound) continue;
        if (!c.senders.includes(sender_(message.getFrom()))) continue;
        const key='sent:'+message.getId();
        if (seen[key]) continue;
        // Only a user-selected stock-alert label and exact configured From address.
        // No email body, account credentials, or embedded links are transmitted.
        send_(c, notification_(message.getSubject()));
        c.p.setProperty(key,String(now));
        seen[key]=String(now);count++;
      }
    }
  } finally { lock.releaseLock(); }
}

function installRelay() {
  const c=config_();
  if(!GmailApp.getUserLabelByName(c.label)) throw new Error('Create the dedicated Gmail label first.');
  if(!c.p.getProperty('START_AT')) c.p.setProperty('START_AT',String(Date.now()));
  stopRelay();
  ScriptApp.newTrigger(HANDLER).timeBased().everyMinutes(1).create();
}

function stopRelay() {
  ScriptApp.getProjectTriggers().filter(t=>t.getHandlerFunction()===HANDLER).forEach(t=>ScriptApp.deleteTrigger(t));
}

function testRelay() {
  send_(config_(),'avail | E-posta aktarım testi\nBu bir stok bildirimi değildir.');
}
