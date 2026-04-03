// UltraKnowledge Web Clipper — Content Script
// Returns selected text when asked by the popup

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === 'getSelection') {
    sendResponse({ text: window.getSelection().toString() });
  }
  return true;
});
