// Lexicon Web Clipper — Popup Script

const DEFAULT_API_BASE = 'http://localhost:8899';

const $ = (sel) => document.querySelector(sel);
const statusDot = $('#statusDot');
const statusText = $('#statusText');
const statsSection = $('#stats');
const totalMemories = $('#totalMemories');
const articleCount = $('#articleCount');
const clipPageBtn = $('#clipPage');
const clipSelectionBtn = $('#clipSelection');
const autoCompileToggle = $('#autoCompile');
const recentSection = $('#recentSection');
const clipList = $('#clipList');
const toast = $('#toast');

let toastTimer = null;

// Initialize on popup open
document.addEventListener('DOMContentLoaded', async () => {
  await checkConnection();
  await loadAutoCompile();
  await loadRecentClips();
  await checkSelection();
});

async function getApiBase() {
  const { apiBase } = await chrome.storage.sync.get('apiBase');
  return apiBase || DEFAULT_API_BASE;
}

async function getAuthHeaders() {
  const { apiToken } = await chrome.storage.sync.get('apiToken');
  const headers = {};
  if (apiToken) {
    headers['Authorization'] = `Bearer ${apiToken}`;
  }
  return headers;
}

// Check server connection
async function checkConnection() {
  try {
    const API_BASE = await getApiBase();
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE}/api/stats`, { signal: AbortSignal.timeout(3000), headers });
    if (!res.ok) throw new Error();
    const data = await res.json();

    statusDot.className = 'status-dot connected';
    statusText.textContent = 'Connected';
    statsSection.style.display = 'flex';
    totalMemories.textContent = data.total_memories ?? '—';
    articleCount.textContent = data.article_count ?? '—';
  } catch {
    statusDot.className = 'status-dot disconnected';
    statusText.textContent = 'Disconnected';
    statsSection.style.display = 'none';
  }
}

// Check if text is selected on the active tab
async function checkSelection() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || tab.url?.startsWith('chrome://')) return;

    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => window.getSelection().toString(),
    });

    if (result?.result?.trim()) {
      clipSelectionBtn.disabled = false;
    }
  } catch {
    // Content script not available on this page
  }
}

// Clip page
clipPageBtn.addEventListener('click', async () => {
  clipPageBtn.disabled = true;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const response = await chrome.runtime.sendMessage({
      type: 'clipPage',
      url: tab.url,
    });

    if (response?.ok) {
      showToast('Page clipped successfully', 'success');
      await loadRecentClips();
    } else {
      showToast(response?.error || 'Failed to clip page', 'error');
    }
  } catch (err) {
    showToast('Failed to clip page', 'error');
  } finally {
    clipPageBtn.disabled = false;
  }
});

// Clip selection
clipSelectionBtn.addEventListener('click', async () => {
  clipSelectionBtn.disabled = true;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => window.getSelection().toString(),
    });

    const text = result?.result?.trim();
    if (!text) {
      showToast('No text selected', 'error');
      return;
    }

    const response = await chrome.runtime.sendMessage({
      type: 'clipSelection',
      text,
    });

    if (response?.ok) {
      showToast('Selection clipped successfully', 'success');
      await loadRecentClips();
    } else {
      showToast(response?.error || 'Failed to clip selection', 'error');
    }
  } catch (err) {
    showToast('Failed to clip selection', 'error');
  } finally {
    await checkSelection();
  }
});

// Auto-compile toggle
autoCompileToggle.addEventListener('change', () => {
  chrome.storage.local.set({ autoCompile: autoCompileToggle.checked });
});

async function loadAutoCompile() {
  const { autoCompile = false } = await chrome.storage.local.get('autoCompile');
  autoCompileToggle.checked = autoCompile;
}

// Recent clips
async function loadRecentClips() {
  const clips = await chrome.runtime.sendMessage({ type: 'getRecentClips' }) || [];
  const display = clips.slice(0, 5);

  if (display.length === 0) {
    recentSection.style.display = 'none';
    return;
  }

  recentSection.style.display = 'block';
  clipList.innerHTML = '';

  for (const clip of display) {
    const li = document.createElement('li');
    li.className = 'clip-item';
    li.innerHTML = `
      <span class="clip-icon ${clip.source}"></span>
      <span class="clip-content">${escapeHtml(clip.content)}</span>
      <span class="clip-time">${formatTime(clip.timestamp)}</span>
    `;
    clipList.appendChild(li);
  }
}

function formatTime(ts) {
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Toast notifications
function showToast(message, type) {
  if (toastTimer) clearTimeout(toastTimer);

  toast.textContent = message;
  toast.className = `toast ${type} show`;

  toastTimer = setTimeout(() => {
    toast.className = 'toast';
    toastTimer = null;
  }, 2500);
}
