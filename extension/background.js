// Lexicon Web Clipper — Background Service Worker

const DEFAULT_API_BASE = 'http://localhost:8899';
const MAX_RECENT_CLIPS = 20;

async function getApiBase() {
  const { apiBase } = await chrome.storage.sync.get('apiBase');
  return apiBase || DEFAULT_API_BASE;
}

// Register context menus on install
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'clip-page',
    title: 'Clip Page to Lexicon',
    contexts: ['page'],
  });
  chrome.contextMenus.create({
    id: 'clip-selection',
    title: 'Clip Selection to Lexicon',
    contexts: ['selection'],
  });
});

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === 'clip-page') {
    await clipContent(tab.url, 'url', tab);
  } else if (info.menuItemId === 'clip-selection') {
    await clipContent(info.selectionText, 'text', tab);
  }
});

// Listen for messages from the popup
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === 'clipPage') {
    clipFromPopup(message.url, 'url').then(sendResponse);
    return true;
  }
  if (message.type === 'clipSelection') {
    clipFromPopup(message.text, 'text').then(sendResponse);
    return true;
  }
  if (message.type === 'getRecentClips') {
    getRecentClips().then(sendResponse);
    return true;
  }
});

async function clipFromPopup(content, source) {
  try {
    const API_BASE = await getApiBase();
    const body = source === 'url' ? { url: content } : { text: content };
    const response = await fetch(`${API_BASE}/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      throw new Error(`Server responded ${response.status}`);
    }

    await saveClip(content, source);
    await flashBadge('success');
    await maybeAutoCompile();
    return { ok: true };
  } catch (err) {
    await flashBadge('error');
    return { ok: false, error: err.message };
  }
}

async function clipContent(content, source, tab) {
  try {
    const API_BASE = await getApiBase();
    const body = source === 'url' ? { url: content } : { text: content };
    const response = await fetch(`${API_BASE}/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      throw new Error(`Server responded ${response.status}`);
    }

    await saveClip(content, source);
    await flashBadge('success');
    await maybeAutoCompile();
  } catch (err) {
    await flashBadge('error');
  }
}

async function saveClip(content, source) {
  const { recentClips = [] } = await chrome.storage.local.get('recentClips');
  const clip = {
    content: content.substring(0, 200),
    source,
    timestamp: Date.now(),
  };
  recentClips.unshift(clip);
  if (recentClips.length > MAX_RECENT_CLIPS) {
    recentClips.length = MAX_RECENT_CLIPS;
  }
  await chrome.storage.local.set({ recentClips });
  updateBadgeCount(recentClips.length);
}

async function getRecentClips() {
  const { recentClips = [] } = await chrome.storage.local.get('recentClips');
  return recentClips;
}

function updateBadgeCount(count) {
  chrome.action.setBadgeText({ text: count > 0 ? String(count) : '' });
  chrome.action.setBadgeBackgroundColor({ color: '#E8913A' });
}

async function flashBadge(status) {
  const color = status === 'success' ? '#3AE89B' : '#E85A3A';
  const text = status === 'success' ? '\u2713' : '\u2717';

  chrome.action.setBadgeText({ text });
  chrome.action.setBadgeBackgroundColor({ color });

  setTimeout(async () => {
    const { recentClips = [] } = await chrome.storage.local.get('recentClips');
    updateBadgeCount(recentClips.length);
  }, 1500);
}

async function maybeAutoCompile() {
  const { autoCompile = false } = await chrome.storage.local.get('autoCompile');
  if (autoCompile) {
    try {
      const API_BASE = await getApiBase();
      await fetch(`${API_BASE}/compile`, { method: 'POST' });
    } catch {
      // Compile is best-effort
    }
  }
}

// Initialize badge on startup
chrome.storage.local.get('recentClips').then(({ recentClips = [] }) => {
  updateBadgeCount(recentClips.length);
});
