// Lexicon Web Clipper — Options Page

const DEFAULT_API_BASE = 'http://localhost:8899';

const apiBaseInput = document.getElementById('apiBase');
const saveBtn = document.getElementById('save');
const savedIndicator = document.getElementById('saved');

// Load saved value on open
chrome.storage.sync.get('apiBase', ({ apiBase }) => {
  apiBaseInput.value = apiBase || DEFAULT_API_BASE;
});

saveBtn.addEventListener('click', () => {
  const value = apiBaseInput.value.trim().replace(/\/+$/, '') || DEFAULT_API_BASE;
  apiBaseInput.value = value;

  chrome.storage.sync.set({ apiBase: value }, () => {
    savedIndicator.classList.add('show');
    setTimeout(() => savedIndicator.classList.remove('show'), 1500);
  });
});
