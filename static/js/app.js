// SEWAMITRA - shared utilities
const TRANSLATIONS = window.SEWAMITRA_TRANSLATIONS || { en: {} };
const SUPPORTED_LANGUAGES = window.SEWAMITRA_LANGUAGES || ['en'];
let currentLanguage = localStorage.getItem('sewamitra-language') || 'en';
const originalPageTitle = document.title;
const originalText = new WeakMap();
const originalAttributes = new WeakMap();

function t(key, vars = {}) {
  const source = String(key);
  let value = translateUiValue(source);
  Object.keys(vars).forEach(name => { value = value.replaceAll(`{${name}}`, vars[name]); });
  return value;
}

function translateUiValue(source) {
  const dictionary = TRANSLATIONS[currentLanguage] || {};
  const exactKey = Object.keys(dictionary).find(key => key.toLowerCase() === source.toLowerCase());
  let value = exactKey ? dictionary[exactKey] : source;
  if (value === source && TRANSLATIONS.en?.[source]) value = TRANSLATIONS.en[source];
  Object.keys(dictionary).sort((a, b) => b.length - a.length).forEach(key => {
    const escapedKey = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    value = value.replace(new RegExp(escapedKey, 'gi'), dictionary[key]);
  });
  return translateUiWords(value);
}

function translateUiWords(value) {
  const tokens = window.SEWAMITRA_TOKEN_TRANSLATIONS?.[currentLanguage] || {};
  if (!Object.keys(tokens).length) return value;
  return value.replace(/\b[A-Za-z][A-Za-z/&-]*\b/g, word => tokens[word.toLowerCase()] || word);
}

function translateTextNode(node) {
  if (!node.nodeValue.trim()) return;
  if (!originalText.has(node)) originalText.set(node, node.nodeValue);
  const translated = originalText.get(node);
  const dictionary = TRANSLATIONS[currentLanguage] || {};
  const trimmed = translated.trim();
  if (dictionary[trimmed]) {
    node.nodeValue = translated.replace(trimmed, dictionary[trimmed]);
    return;
  }
  node.nodeValue = translateUiValue(translated);
}

function translateElement(element) {
  if (!element || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(element.tagName)) return;
  if (element.matches?.('#langSelect')) {
    element.value = currentLanguage;
    return;
  }
  const attrs = ['placeholder', 'title', 'aria-label'];
  if (!originalAttributes.has(element)) originalAttributes.set(element, {});
  const saved = originalAttributes.get(element);
  attrs.forEach(attribute => {
    if (element.hasAttribute(attribute)) {
      if (saved[attribute] === undefined) saved[attribute] = element.getAttribute(attribute);
      element.setAttribute(attribute, t(saved[attribute]));
    }
  });
  if (element.dataset.i18n) element.textContent = t(element.dataset.i18n);
  element.childNodes.forEach(child => {
    if (child.nodeType === Node.TEXT_NODE) translateTextNode(child);
    else if (child.nodeType === Node.ELEMENT_NODE) translateElement(child);
  });
}

function applyLanguage(language) {
  currentLanguage = SUPPORTED_LANGUAGES.includes(language) ? language : 'en';
  localStorage.setItem('sewamitra-language', currentLanguage);
  document.documentElement.lang = currentLanguage;
  const select = document.getElementById('langSelect');
  if (select) select.value = currentLanguage;
  translateElement(document.body);
  const title = document.querySelector('title');
  if (title) title.textContent = t(originalPageTitle);
  document.dispatchEvent(new CustomEvent('languagechange', { detail: currentLanguage }));
}

function initLanguage() {
  applyLanguage(currentLanguage);
  if (window.sewamitraLanguageObserver) return;
  window.sewamitraLanguageObserver = new MutationObserver(records => {
    if (currentLanguage === 'en') return;
    records.forEach(record => record.addedNodes.forEach(node => {
      if (node.nodeType === Node.ELEMENT_NODE) translateElement(node);
      if (node.nodeType === Node.TEXT_NODE) translateTextNode(node);
    }));
  });
  window.sewamitraLanguageObserver.observe(document.body, { childList: true, subtree: true });
}
const API = (path, opts = {}) => {
  const defaults = {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin'
  };
  const merged = { ...defaults, ...opts, headers: { ...defaults.headers, ...(opts.headers || {}) } };
  return fetch('/api/' + path, merged).then(async r => {
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || 'Request failed');
    return data;
  });
};

let currentUser = null;
let notificationState = { items: [], unread_count: 0 };

async function checkAuth() {
  try {
    const res = await API('auth/me');
    currentUser = res.user;
    document.dispatchEvent(new CustomEvent('authchange', { detail: currentUser }));
    return res;
  } catch {
    currentUser = null;
    document.dispatchEvent(new CustomEvent('authchange', { detail: null }));
    return { user: null };
  }
}

function normalizeRoleForAccess(role) {
  return role === 'service-team' ? 'worker' : role;
}

function requireAuth(roles) {
  if (!currentUser) {
    window.location.href = '/';
    return false;
  }
  const allowedRoles = (roles || []).map(normalizeRoleForAccess);
  const userRole = normalizeRoleForAccess(currentUser.role);
  if (roles && !allowedRoles.includes(userRole)) {
    window.location.href = getDashboardUrl(currentUser.role);
    return false;
  }
  return true;
}

function getDashboardUrl(role) {
  const map = {
    customer: 'customer', worker: 'worker', 'service-team': 'service-team', business: 'business', admin: 'admin'
  };
  return '/' + (map[role] || '') + '.html';
}

function toast(msg, type = '') {
  let el = document.getElementById('toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className = 'toast show ' + type;
  setTimeout(() => el.classList.remove('show'), 3000);
}

function fmtMoney(n) {
  return '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function fmtDate(s) {
  if (!s) return '';
  const value = String(s).trim();
  let d;
  if (value.includes(' ')) {
    d = new Date(value.replace(' ', 'T'));
  } else {
    d = new Date(value);
  }
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function starsHTML(score) {
  let html = '<span class="stars">';
  for (let i = 1; i <= 5; i++) {
    html += `<span class="star${i <= score ? '' : ' empty'}">★</span>`;
  }
  html += '</span>';
  return html;
}

function statusBadge(status) {
  return `<span class="badge badge-${status}">${status}</span>`;
}

function setTheme(theme) {
  const isDark = theme === 'dark';
  document.body.classList.toggle('dark-theme', isDark);
  localStorage.setItem('sewamitra-theme', theme);
  const button = document.getElementById('themeToggle');
  if (button) {
    button.textContent = isDark ? '☀️' : '🌙';
    button.setAttribute('aria-label', isDark ? 'Switch to light mode' : 'Switch to dark mode');
  }
}

function toggleTheme() {
  const nextTheme = document.body.classList.contains('dark-theme') ? 'light' : 'dark';
  setTheme(nextTheme);
}

function initTheme() {
  const savedTheme = localStorage.getItem('sewamitra-theme');
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  setTheme(savedTheme || (prefersDark ? 'dark' : 'light'));
}

function renderNavbar(active) {
  const links = [];
  if (currentUser) {
    links.push(`<a href="${getDashboardUrl(currentUser.role)}" class="${active === 'dashboard' ? 'active' : ''}">Dashboard</a>`);
    if (currentUser.role === 'customer') {
      links.push(`<a href="/jobs.html" class="${active === 'jobs' ? 'active' : ''}">Jobs</a>`);
      links.push(`<a href="/map.html" class="${active === 'map' ? 'active' : ''}">Find Workers</a>`);
      links.push(`<a href="/cooperative.html" class="${active === 'cooperative' ? 'active' : ''}">Cooperative Gigs</a>`);
      links.push(`<a href="/marketplace.html" class="${active === 'market' ? 'active' : ''}">Marketplace</a>`);
    }
    if (currentUser.role === 'worker' || currentUser.role === 'service-team') {
      links.push(`<a href="/jobs.html" class="${active === 'jobs' ? 'active' : ''}">Find Jobs</a>`);
      links.push(`<a href="/cooperative.html" class="${active === 'cooperative' ? 'active' : ''}">Cooperative Gigs</a>`);
      links.push(`<a href="/groups.html" class="${active === 'groups' ? 'active' : ''}">Groups</a>`);
      links.push(`<a href="/committee.html" class="${active === 'committee' ? 'active' : ''}">Committee</a>`);
    }
    if (currentUser.role === 'business') {
      links.push(`<a href="/marketplace.html" class="${active === 'market' ? 'active' : ''}">Products</a>`);
      links.push(`<a href="/orders.html" class="${active === 'orders' ? 'active' : ''}">Orders</a>`);
    }
    links.push(`<a href="/messages.html" class="${active === 'messages' ? 'active' : ''}">Messages</a>`);
    links.push(`<a href="/profile.html" class="${active === 'profile' ? 'active' : ''}">Profile</a>`);
    links.push(`<a href="/help.html" class="${active === 'help' ? 'active' : ''}">Help & Support</a>`);
    if (currentUser.role === 'admin') {
      links.push(`<a href="/admin.html" class="${active === 'admin' ? 'active' : ''}">Admin Panel</a>`);
    }
    links.push(`
      <button id="notificationButton" class="notification-bell" aria-label="Notifications" onclick="toggleNotificationsPanel()">
        &#128276;
        <span id="notificationBadge" class="notification-badge hidden">0</span>
      </button>
    `);
    links.push(`<button onclick="doLogout()">Logout</button>`);
  } else {
    links.push(`<a href="/login.html">Login</a>`);
    links.push(`<a href="/register.html">Register</a>`);
    links.push(`<a href="/help.html">Help & Support</a>`);
  }
  links.push(`<button id="themeToggle" class="theme-toggle" onclick="toggleTheme()" aria-label="Switch theme">🌙</button>`);
  return `
    <nav class="navbar">
      <div class="navbar-brand">SEWAMITRA<span>.</span></div>
      <button class="navbar-menu-toggle" type="button" onclick="toggleMobileNav()" aria-label="Open navigation" aria-controls="navbarLinks" aria-expanded="false">☰</button>
      <div class="navbar-links" id="navbarLinks">${links.join('')}</div>
      <button class="navbar-overlay" type="button" onclick="toggleMobileNav(false)" aria-label="Close navigation"></button>
    </nav>
  `;
}

function toggleMobileNav(force) {
  const navbar = document.querySelector('.navbar');
  const toggle = document.querySelector('.navbar-menu-toggle');
  if (!navbar || !toggle) return;
  const open = force === undefined ? !navbar.classList.contains('mobile-nav-open') : force;
  navbar.classList.toggle('mobile-nav-open', open);
  toggle.setAttribute('aria-expanded', String(open));
  toggle.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
}

function renderSOSFab() {
  return `
    <button class="chat-fab" id="sosFab" onclick="triggerSOS()" title="Emergency SOS" style="bottom: 84px; right: 18px; background: linear-gradient(135deg, #ef4444, #f97316);">🆘</button>
  `;
}

function triggerSOS() {
  toast('SOS alert triggered. Please contact emergency services or your local support team.', 'error');
  return false;
}

function renderChatFab() {
  return `
    <button class="chat-fab" id="chatFab" onclick="toggleChatbot()" title="Chat support">💬</button>
  `;
}

function getChatbotReply(input) {
  const text = (input || '').toLowerCase();
  if (!text) return 'Hi! I can help with jobs, profiles, workers, and marketplace questions.';
  if (text.includes('job') || text.includes('work')) return 'You can browse active jobs from the Jobs page and apply from there.';
  if (text.includes('profile')) return 'Open your profile from the top navigation to edit your details and update your portfolio.';
  if (text.includes('worker') || text.includes('find')) return 'Use the Find Workers map to search nearby workers by category and location.';
  if (text.includes('market') || text.includes('product')) return 'Visit the Marketplace to view products and place orders from businesses.';
  if (text.includes('hello') || text.includes('hi')) return 'Hello! How can I help you today?';
  return 'I can help with jobs, workers, profile, and marketplace. Ask me anything about the app!';
}

function toggleChatbot() {
  let panel = document.getElementById('chatbotPanel');
  if (!panel) {
    document.body.insertAdjacentHTML('beforeend', `
      <div id="chatbotPanel" class="chatbot-panel">
        <div class="chatbot-header">
          <div>
            <strong>SEWAMITRA Assistant</strong>
            <div class="chatbot-status">Online</div>
          </div>
          <button class="chatbot-close" onclick="toggleChatbot()" aria-label="Close chat">×</button>
        </div>
        <div class="chatbot-messages">
          <div class="chatbot-bubble bot">Hi! I can help with jobs, profiles, workers, and marketplace questions.</div>
        </div>
        <div class="chatbot-input-row">
          <input id="chatbotInput" type="text" placeholder="Ask about the app..." />
          <button onclick="sendChatbotMessage()">Send</button>
        </div>
      </div>
    `);
    panel = document.getElementById('chatbotPanel');
    const input = document.getElementById('chatbotInput');
    if (input) input.focus();
    return;
  }

  panel.classList.toggle('hidden');
  if (!panel.classList.contains('hidden')) {
    const input = document.getElementById('chatbotInput');
    if (input) input.focus();
  }
}

function sendChatbotMessage() {
  const input = document.getElementById('chatbotInput');
  const panel = document.getElementById('chatbotPanel');
  if (!input || !panel) return;

  const value = input.value.trim();
  if (!value) return;

  const messages = panel.querySelector('.chatbot-messages');
  messages.insertAdjacentHTML('beforeend', `<div class="chatbot-bubble user">${value}</div>`);
  input.value = '';

  const reply = getChatbotReply(value);
  setTimeout(() => {
    messages.insertAdjacentHTML('beforeend', `<div class="chatbot-bubble bot">${reply}</div>`);
    messages.scrollTop = messages.scrollHeight;
  }, 250);

  messages.scrollTop = messages.scrollHeight;
}

function renderLangBar() {
  return `
    <div class="lang-bar">
      <strong>Language:</strong>
      <select id="langSelect" onchange="translatePage()">
        <option value="en">English</option>
        <option value="hi">हिन्दी</option>
        <option value="ta">தமிழ்</option>
        <option value="te">తెలుగు</option>
        <option value="bn">বাংলা</option>
        <option value="mr">मराठी</option>
        <option value="kn">ಕನ್ನಡ</option>
      </select>
      <input type="text" id="langInput" placeholder="Type to translate..." oninput="translatePage()">
      <span id="langOutput"></span>
    </div>
  `;
}

function translatePage() {
  const output = document.getElementById('langOutput');
  const lang = document.getElementById('langSelect')?.value || 'en';
  const text = document.getElementById('langInput')?.value || '';
  applyLanguage(lang);
  if (output) output.textContent = text ? (TRANSLATIONS[lang]?.[text] || text) : '';
}

async function doLogout() {
  try { await API('auth/logout', { method: 'POST' }); } catch {}
  currentUser = null;
  window.location.href = '/';
}

function updateNotificationBadge() {
  const badge = document.getElementById('notificationBadge');
  if (!badge) return;
  const unread = Number(notificationState.unread_count || notificationState.unreadCount || 0);
  badge.textContent = unread > 99 ? '99+' : String(unread);
  badge.classList.toggle('hidden', unread <= 0);
}

function renderNotificationsPanel() {
  const existing = document.getElementById('notificationsPanel');
  if (existing) existing.remove();
  if (!currentUser) return;

  const sampleNotifications = [
    { id: 'demo-1', title: 'New job match', message: 'A customer in your area posted a plumbing job matching your skills.', type: 'info', read_flag: 0 },
    { id: 'demo-2', title: 'Payment released', message: 'Your completed job payment has been credited to your wallet.', type: 'success', read_flag: 0 },
    { id: 'demo-3', title: 'Safety reminder', message: 'Please confirm the safety checklist before starting the next assignment.', type: 'warning', read_flag: 1 }
  ];
  const itemsList = (notificationState.items && notificationState.items.length) ? notificationState.items : sampleNotifications;

  const items = itemsList.map(item => `
    <button class="notification-item ${item.read_flag ? 'read' : 'unread'}" data-id="${item.id}" onclick="event.stopPropagation(); openNotification(${item.id})">
      <div class="notification-item-title">${item.title || 'Update'}</div>
      <div class="notification-item-message">${item.message || ''}</div>
      <div class="notification-item-meta">${item.type || 'info'}</div>
    </button>
  `).join('');

  document.body.insertAdjacentHTML('beforeend', `
    <div id="notificationsPanel" class="notifications-panel hidden">
      <div class="notifications-header">
        <strong>Notifications</strong>
        <button type="button" class="notifications-close" onclick="toggleNotificationsPanel()">×</button>
      </div>
      <div class="notifications-list">${items || '<div class="notification-empty">No notifications yet.</div>'}</div>
    </div>
  `);
}

async function loadNotifications() {
  if (!currentUser) {
    notificationState = { items: [], unread_count: 0 };
    updateNotificationBadge();
    return [];
  }
  try {
    const res = await API('notifications');
    const items = Array.isArray(res?.items) && res.items.length ? res.items : [
      { id: 'demo-1', title: 'New job match', message: 'A customer in your area posted a plumbing job matching your skills.', type: 'info', read_flag: 0 },
      { id: 'demo-2', title: 'Payment released', message: 'Your completed job payment has been credited to your wallet.', type: 'success', read_flag: 0 },
      { id: 'demo-3', title: 'Safety reminder', message: 'Please confirm the safety checklist before starting the next assignment.', type: 'warning', read_flag: 1 }
    ];
    notificationState = { items, unread_count: items.filter(item => !item.read_flag).length };
    updateNotificationBadge();
    renderNotificationsPanel();
    return items;
  } catch (err) {
    console.warn('Unable to load notifications', err);
    const fallback = [
      { id: 'demo-1', title: 'New job match', message: 'A customer in your area posted a plumbing job matching your skills.', type: 'info', read_flag: 0 },
      { id: 'demo-2', title: 'Payment released', message: 'Your completed job payment has been credited to your wallet.', type: 'success', read_flag: 0 },
      { id: 'demo-3', title: 'Safety reminder', message: 'Please confirm the safety checklist before starting the next assignment.', type: 'warning', read_flag: 1 }
    ];
    notificationState = { items: fallback, unread_count: fallback.filter(item => !item.read_flag).length };
    updateNotificationBadge();
    renderNotificationsPanel();
    return fallback;
  }
}

async function openNotification(notificationId) {
  const item = (notificationState.items || []).find(n => Number(n.id) === Number(notificationId));
  if (item && !item.read_flag) {
    try {
      await API(`notifications/${notificationId}/read`, { method: 'POST' });
      item.read_flag = 1;
      notificationState.unread_count = Math.max(0, Number(notificationState.unread_count || 0) - 1);
      updateNotificationBadge();
      renderNotificationsPanel();
    } catch (err) {
      console.warn('Unable to mark notification read', err);
    }
  }
  if (item?.link) {
    window.location.href = item.link;
  }
}

function toggleNotificationsPanel() {
  const panel = document.getElementById('notificationsPanel');
  if (!panel) {
    renderNotificationsPanel();
  }
  const next = document.getElementById('notificationsPanel');
  if (!next) return;
  next.classList.toggle('hidden');
  if (!next.classList.contains('hidden')) {
    const unread = (notificationState.items || []).filter(item => !item.read_flag);
    if (unread.length) {
      unread.forEach(item => {
        if (item && !item.read_flag) {
          API(`notifications/${item.id}/read`, { method: 'POST' }).catch(() => {});
          item.read_flag = 1;
        }
      });
      notificationState.unread_count = 0;
      updateNotificationBadge();
      renderNotificationsPanel();
    }
  }
}

document.addEventListener('authchange', async (event) => {
  currentUser = event.detail || null;
  if (currentUser) {
    await loadNotifications();
  } else {
    notificationState = { items: [], unread_count: 0 };
    updateNotificationBadge();
    const panel = document.getElementById('notificationsPanel');
    if (panel) panel.remove();
  }
});

function injectLayout(activePage) {
  document.body.insertAdjacentHTML('afterbegin', renderNavbar(activePage) + renderLangBar());
  document.body.insertAdjacentHTML('beforeend', renderChatFab());
}

async function initPage(activePage, requiredRoles) {
  await checkAuth();
  if (requiredRoles && !requireAuth(requiredRoles)) return false;
  injectLayout(activePage);
  if (currentUser) {
    await loadNotifications();
  }
  initTheme();
  initLanguage();
  return true;
}

initTheme();
document.addEventListener('DOMContentLoaded', initLanguage);
