// Lexicon Web Clipper — Options Page

const DEFAULT_API_BASE = 'http://localhost:8899';

const apiBaseInput = document.getElementById('apiBase');
const apiTokenInput = document.getElementById('apiToken');
const saveBtn = document.getElementById('save');
const savedIndicator = document.getElementById('saved');

// Load saved values on open
chrome.storage.sync.get(['apiBase', 'apiToken'], ({ apiBase, apiToken }) => {
  apiBaseInput.value = apiBase || DEFAULT_API_BASE;
  apiTokenInput.value = apiToken || '';
});

saveBtn.addEventListener('click', () => {
  const base = apiBaseInput.value.trim().replace(/\/+$/, '') || DEFAULT_API_BASE;
  apiBaseInput.value = base;
  const token = apiTokenInput.value.trim();

  chrome.storage.sync.set({ apiBase: base, apiToken: token }, () => {
    savedIndicator.classList.add('show');
    setTimeout(() => savedIndicator.classList.remove('show'), 1500);
  });
});
