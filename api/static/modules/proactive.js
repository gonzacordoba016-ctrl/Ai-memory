// ── PROACTIVE ─────────────────────────────────────────────────────────────
function connectProactiveWS() {
  wsProactive = new WebSocket(_wsTokenParam(WS_PROACTIVE));
  wsProactive.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'ping') return;
    showProactiveNotification(data);
    if (data.type === 'job_complete') loadJobs();
  };
  wsProactive.onclose = () => setTimeout(connectProactiveWS, 5000);
  wsProactive.onerror = () => addLog('WS proactivo error', 'warn');
}

function showProactiveNotification(data) {
  const title   = data.title || 'Notificación';
  const message = data.message || '';
  const colors  = {
    device_connected: 'border-primary text-primary',
    device_inactive:  'border-[#ffaa00] text-[#ffaa00]',
    recurring_error:  'border-error text-error',
    job_complete:     'border-secondary text-secondary',
    daily_summary:    'border-[#8eff71] text-[#8eff71]',
  };
  const cls = colors[data.type] || 'border-[#494847] text-[#adaaaa]';

  const notif = document.createElement('div');
  notif.className = `fixed bottom-6 right-6 z-[300] max-w-sm bg-black border-l-4 ${cls} p-4 font-mono text-[10px]`;
  notif.innerHTML = `
    <div class="flex items-start gap-3">
      <div class="flex-1">
        <div class="font-bold uppercase tracking-widest mb-1">${escHtml(title)}</div>
        <div class="text-[#adaaaa] leading-relaxed">${escHtml(message.slice(0,120))}${message.length > 120 ? '...' : ''}</div>
      </div>
      <button onclick="this.closest('div.fixed').remove()" class="text-[#494847] hover:text-error flex-shrink-0 ml-2">✕</button>
    </div>`;
  document.body.appendChild(notif);
  setTimeout(() => notif.remove?.(), 8000);
  addMessage('agent', `${title}\n${message}`, ['proactive']);
  addLog(`[PROACTIVE] ${title}`, 'info');
}
