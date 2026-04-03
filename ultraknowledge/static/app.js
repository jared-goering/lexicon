/* ultraknowledge — single-page app */

(function () {
  'use strict';

  const $ = (sel, ctx) => (ctx || document).querySelector(sel);
  const $$ = (sel, ctx) => [...(ctx || document).querySelectorAll(sel)];
  const app = () => $('#app');

  const ACCENTS = ['accent-1', 'accent-2', 'accent-3', 'accent-4'];
  const ACCENT_HEX = { 'accent-1': '#E8913A', 'accent-2': '#3A8FE8', 'accent-3': '#6B3AE8', 'accent-4': '#3AE89B' };

  // ─── State ───────────────────────────────────────────────────────────
  let state = {
    articles: [],
    stats: { article_count: 0, system_state: 'READY' },
    ingestions: [],
  };

  // ─── Routing ─────────────────────────────────────────────────────────
  function navigate(hash) {
    window.location.hash = hash;
  }

  function getRoute() {
    const h = window.location.hash.slice(1) || '/';
    if (h === '/' || h === '') return { view: 'home' };
    if (h.startsWith('/article/')) return { view: 'article', slug: decodeURIComponent(h.slice(9)) };
    if (h.startsWith('/ask/')) return { view: 'ask', question: decodeURIComponent(h.slice(5)) };
    if (h.startsWith('/research/')) return { view: 'research', query: decodeURIComponent(h.slice(10)) };
    return { view: 'home' };
  }

  async function router() {
    const route = getRoute();
    switch (route.view) {
      case 'home': await renderHome(); break;
      case 'article': await renderArticle(route.slug); break;
      case 'ask': await renderAsk(route.question); break;
      case 'research': await renderResearch(route.query); break;
      default: await renderHome();
    }
  }

  window.addEventListener('hashchange', router);

  // ─── API helpers ─────────────────────────────────────────────────────
  async function api(method, path, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    if (!res.ok) throw new Error(`API ${path}: ${res.status}`);
    return res.json();
  }

  async function loadStats() {
    try {
      const data = await api('GET', '/api/stats');
      state.stats = data;
    } catch { /* stats endpoint may not exist yet */ }
  }

  async function loadTopics() {
    try {
      const data = await api('GET', '/api/topics');
      state.articles = data.topics || [];
    } catch {
      // fallback to /articles
      const data = await api('GET', '/articles');
      state.articles = (data.articles || []).slice(0, 5);
    }
  }

  // ─── Markdown rendering ──────────────────────────────────────────────
  function renderMarkdown(md) {
    if (!md) return '';
    // Convert wikilinks [[Topic]] to clickable links
    const withLinks = md.replace(/\[\[([^\]]+)\]\]/g, (_, topic) => {
      const slug = topic.toLowerCase().replace(/\s+/g, '-');
      return `<a href="#/article/${encodeURIComponent(slug)}" class="wikilink">${topic}</a>`;
    });
    marked.setOptions({
      highlight: function (code, lang) {
        if (lang && hljs.getLanguage(lang)) {
          return hljs.highlight(code, { language: lang }).value;
        }
        return hljs.highlightAuto(code).value;
      },
    });
    return DOMPurify.sanitize(marked.parse(withLinks));
  }

  // ─── Shared Components ───────────────────────────────────────────────
  function logoHTML() {
    return `<div class="flex items-center gap-1.5">
      <div class="grid grid-cols-2 gap-0.5">
        <div class="w-2 h-2 rounded-full bg-accent-1"></div>
        <div class="w-2 h-2 rounded-full bg-accent-2"></div>
        <div class="w-2 h-2 rounded-full bg-accent-3"></div>
        <div class="w-2 h-2 rounded-full bg-accent-4"></div>
      </div>
    </div>`;
  }

  function headerHTML(showBack, showIngest) {
    return `<header class="fixed top-0 left-0 right-0 bg-bg/90 backdrop-blur-sm z-50 border-b border-border">
      <div class="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
        <div class="flex items-center gap-4">
          ${showBack ? `<button onclick="window.location.hash=''" class="font-mono text-xs text-text-secondary hover:text-text tracking-wide">← BACK</button>` : logoHTML()}
        </div>
        ${showIngest !== false ? `<button onclick="openIngestModal()" class="font-mono text-xs tracking-wider border border-border px-3 py-1.5 hover:bg-surface transition-colors">+ INGEST</button>` : ''}
      </div>
    </header>`;
  }

  function footerHTML() {
    return `<footer class="fixed bottom-0 left-0 right-0 bg-bg/90 backdrop-blur-sm border-t border-border z-50">
      <div class="max-w-5xl mx-auto px-6 h-10 flex items-center justify-between">
        <span class="font-mono text-[10px] text-text-secondary tracking-widest">COMPILED INDEX: ${state.stats.article_count.toLocaleString()} ARTICLES</span>
        <span class="font-mono text-[10px] text-text-secondary tracking-widest">SYSTEM STATE: ${state.stats.system_state}</span>
      </div>
    </footer>`;
  }

  function searchBarHTML(placeholder, id, scope) {
    const scopeAttr = scope ? `data-scope="${scope}"` : '';
    return `<div class="relative w-full max-w-2xl mx-auto">
      <input type="text" id="${id}" ${scopeAttr}
        class="w-full bg-surface border border-border rounded-lg px-5 py-4 text-base font-sans placeholder:text-text-secondary/60 focus:outline-none focus:border-accent-2/40 transition-colors"
        placeholder="${placeholder}">
      <span class="absolute right-4 top-1/2 -translate-y-1/2 font-mono text-[10px] text-text-secondary/50 tracking-widest pointer-events-none">ENTER TO ASK</span>
    </div>`;
  }

  function topicCardHTML(article, index) {
    const accent = ACCENTS[index % ACCENTS.length];
    const accentHex = ACCENT_HEX[accent];
    const isActive = index === 0;
    const title = article.title || article.slug;
    const slug = article.slug;
    return `<div class="bg-surface border border-border rounded-lg p-5 cursor-pointer hover:border-${accent}/40 transition-colors topic-card" onclick="window.location.hash='#/article/${encodeURIComponent(slug)}'">
      <div class="flex items-center justify-between mb-3">
        <span class="font-mono text-[10px] text-text-secondary tracking-widest">TOPIC // #${index + 1}</span>
        ${isActive ? `<span class="font-mono text-[10px] tracking-wider px-2 py-0.5 rounded" style="color:${accentHex}; background:${accentHex}15">ACTIVE</span>` : ''}
      </div>
      <h3 class="text-base font-medium mb-4">${title}</h3>
      <div class="h-1 rounded-full bg-border overflow-hidden">
        <div class="h-full rounded-full" style="width:${Math.min(100, 30 + Math.random() * 70)}%; background:${accentHex}"></div>
      </div>
    </div>`;
  }

  // ─── Home View ───────────────────────────────────────────────────────
  async function renderHome() {
    await Promise.all([loadStats(), loadTopics()]);

    const cards = state.articles.slice(0, 5).map((a, i) => topicCardHTML(a, i)).join('');
    const gridCols = state.articles.length === 0 ? '' : state.articles.length <= 3
      ? `grid-cols-1 sm:grid-cols-2 lg:grid-cols-${Math.min(3, state.articles.length)}`
      : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3';

    app().innerHTML = `
      ${headerHTML(false, true)}
      <main class="min-h-screen flex flex-col items-center justify-center px-6 pb-20 pt-20">
        <div class="text-center mb-10">
          <h1 class="font-mono text-2xl sm:text-3xl tracking-[0.3em] font-medium mb-2">ULTRAKNOWLEDGE</h1>
          <p class="font-mono text-xs text-text-secondary tracking-widest">LLM-COMPILED KNOWLEDGE BASE</p>
        </div>
        ${searchBarHTML('Ask your knowledge...', 'home-search')}
        ${state.articles.length > 0 ? `
          <div class="grid ${gridCols} gap-4 mt-12 w-full max-w-3xl">
            ${cards}
          </div>
        ` : `
          <div class="mt-12 text-center">
            <p class="font-mono text-xs text-text-secondary tracking-wider">NO ARTICLES YET — INGEST SOME KNOWLEDGE</p>
          </div>
        `}
      </main>
      ${footerHTML()}
    `;

    bindSearchInput('home-search');
  }

  // ─── Article View ────────────────────────────────────────────────────
  async function renderArticle(slug) {
    app().innerHTML = `
      ${headerHTML(true, true)}
      <main class="max-w-3xl mx-auto px-6 pt-20 pb-28">
        <div class="flex items-center gap-2 mb-2">
          <span class="font-mono text-[10px] text-text-secondary tracking-widest">LOADING...</span>
        </div>
      </main>
    `;

    try {
      const data = await api('GET', `/articles/${encodeURIComponent(slug)}`);
      let content = data.content || '';

      // Strip YAML frontmatter (---\n...\n---) before rendering
      const fmMatch = content.match(/^---\s*\n([\s\S]*?)\n---\s*\n?/);
      let fmMeta = {};
      if (fmMatch) {
        content = content.slice(fmMatch[0].length);
        // Parse simple key: value pairs from frontmatter
        fmMatch[1].split('\n').forEach(line => {
          const kv = line.match(/^(\w+):\s*(.+)/);
          if (kv) fmMeta[kv[1]] = kv[2].trim();
        });
      }

      // Extract metadata from markdown frontmatter-style headers
      const lines = content.split('\n');
      let title = fmMeta.title || slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      let sources = [];
      let relatedTopics = [];

      // Find title from first H1
      for (const line of lines) {
        if (line.startsWith('# ')) { title = line.slice(2).trim(); break; }
      }

      // Find wikilinks in content for related topics
      const wikiRe = /\[\[([^\]]+)\]\]/g;
      let m;
      while ((m = wikiRe.exec(content)) !== null) {
        if (!relatedTopics.includes(m[1])) relatedTopics.push(m[1]);
      }

      // Find the article index among loaded articles
      const idx = state.articles.findIndex(a => a.slug === slug);
      const accent = ACCENTS[(idx >= 0 ? idx : 0) % ACCENTS.length];
      const accentHex = ACCENT_HEX[accent];

      app().innerHTML = `
        ${headerHTML(true, true)}
        <main class="max-w-3xl mx-auto px-6 pt-20 pb-28">
          <div class="flex items-center gap-3 mb-1">
            <span class="font-mono text-[10px] text-text-secondary tracking-widest">TOPIC // #${idx >= 0 ? idx + 1 : '—'}</span>
            ${idx === 0 ? `<span class="font-mono text-[10px] tracking-wider px-2 py-0.5 rounded" style="color:${accentHex}; background:${accentHex}15">ACTIVE</span>` : ''}
          </div>

          <article class="prose-article mt-6">
            ${renderMarkdown(content)}
          </article>

          ${relatedTopics.length > 0 ? `
            <div class="border-t border-border mt-10 pt-6">
              <span class="font-mono text-[10px] text-text-secondary tracking-widest block mb-3">RELATED TOPICS</span>
              <div class="flex flex-wrap gap-2">
                ${relatedTopics.map(t => {
                  const s = t.toLowerCase().replace(/\s+/g, '-');
                  return `<a href="#/article/${encodeURIComponent(s)}" class="font-mono text-xs text-accent-2 hover:underline">[[${t}]]</a>`;
                }).join(' · ')}
              </div>
            </div>
          ` : ''}

          <div class="border-t border-border mt-8 pt-6">
            ${searchBarHTML(`Ask about ${title}...`, 'article-search', slug)}
          </div>
        </main>
        ${footerHTML()}
      `;

      bindSearchInput('article-search');
    } catch (err) {
      app().innerHTML = `
        ${headerHTML(true, true)}
        <main class="max-w-3xl mx-auto px-6 pt-20 pb-28 text-center">
          <p class="font-mono text-xs text-text-secondary tracking-wider mt-20">ARTICLE NOT FOUND: ${slug}</p>
          <p class="text-sm text-text-secondary mt-4">This topic hasn't been compiled yet.</p>
          <button onclick="window.location.hash='#/research/${encodeURIComponent(slug.replace(/-/g, ' '))}'" class="mt-6 font-mono text-xs tracking-wider border border-border px-4 py-2 hover:bg-surface transition-colors">RESEARCH THIS TOPIC →</button>
        </main>
        ${footerHTML()}
      `;
    }
  }

  // ─── Q&A View ────────────────────────────────────────────────────────
  async function renderAsk(question) {
    app().innerHTML = `
      ${headerHTML(true, false)}
      <main class="max-w-3xl mx-auto px-6 pt-20 pb-28">
        <div class="mb-8">
          <span class="font-mono text-[10px] text-text-secondary tracking-widest">QUESTION</span>
          <h2 class="text-xl font-medium mt-2">${escapeHTML(question)}</h2>
        </div>
        <div class="border-t border-border my-6"></div>
        <div class="flex items-center gap-2">
          <div class="loading-dots font-mono text-xs text-text-secondary tracking-widest">THINKING</div>
        </div>
      </main>
      ${footerHTML()}
    `;

    try {
      const data = await api('POST', '/ask', { question });
      const answer = data.answer || 'No answer available.';
      const citations = data.citations || [];
      const confidence = data.confidence || 0;
      const needsResearch = data.needs_research;
      const suggestedQueries = data.suggested_queries || [];

      const confLabel = confidence > 0.7 ? 'HIGH' : confidence > 0.4 ? 'MEDIUM' : 'LOW';
      const confColor = confidence > 0.7 ? 'text-accent-4' : confidence > 0.4 ? 'text-accent-1' : 'text-text-secondary';

      app().innerHTML = `
        ${headerHTML(true, false)}
        <main class="max-w-3xl mx-auto px-6 pt-20 pb-28">
          <div class="mb-8">
            <span class="font-mono text-[10px] text-text-secondary tracking-widest">QUESTION</span>
            <h2 class="text-xl font-medium mt-2">${escapeHTML(question)}</h2>
          </div>
          <div class="border-t border-border my-6"></div>

          <div class="prose-article">
            ${renderMarkdown(answer)}
          </div>

          ${citations.length > 0 ? `
            <div class="border-t border-border mt-8 pt-6">
              <span class="font-mono text-[10px] text-text-secondary tracking-widest block mb-3">SOURCES CITED</span>
              <div class="space-y-2">
                ${citations.map((c, i) => `
                  <div class="flex items-start gap-2 text-sm">
                    <span class="font-mono text-[10px] text-text-secondary">[${i + 1}]</span>
                    <span>${escapeHTML(c.title)}${c.score ? ` <span class="font-mono text-[10px] text-text-secondary">· relevance: ${c.score.toFixed(2)}</span>` : ''}</span>
                  </div>
                `).join('')}
              </div>
            </div>
          ` : ''}

          <div class="border-t border-border mt-6 pt-4 flex items-center gap-6">
            <span class="font-mono text-[10px] tracking-widest ${confColor}">CONFIDENCE: ${confLabel}</span>
            <span class="font-mono text-[10px] text-text-secondary tracking-widest">${citations.length} ARTICLES REFERENCED</span>
          </div>

          ${needsResearch || suggestedQueries.length > 0 ? `
            <button onclick="window.location.hash='#/research/${encodeURIComponent(question)}'"
              class="mt-6 font-mono text-xs tracking-wider border border-border px-4 py-2 hover:bg-surface transition-colors">
              RESEARCH THIS FURTHER →
            </button>
          ` : ''}

          <div class="border-t border-border mt-8 pt-6">
            ${searchBarHTML('Ask a follow-up...', 'followup-search')}
          </div>
        </main>
        ${footerHTML()}
      `;

      bindSearchInput('followup-search');
    } catch (err) {
      app().innerHTML = `
        ${headerHTML(true, false)}
        <main class="max-w-3xl mx-auto px-6 pt-20 pb-28">
          <div class="mb-8">
            <span class="font-mono text-[10px] text-text-secondary tracking-widest">QUESTION</span>
            <h2 class="text-xl font-medium mt-2">${escapeHTML(question)}</h2>
          </div>
          <div class="border-t border-border my-6"></div>
          <p class="text-sm text-text-secondary">Something went wrong while processing your question. Please try again.</p>
          <p class="font-mono text-xs text-text-secondary mt-2">${escapeHTML(err.message)}</p>
        </main>
        ${footerHTML()}
      `;
    }
  }

  // ─── Research View ───────────────────────────────────────────────────
  async function renderResearch(query) {
    app().innerHTML = `
      ${headerHTML(true, false)}
      <main class="max-w-3xl mx-auto px-6 pt-20 pb-28">
        <div class="mb-8">
          <span class="font-mono text-[10px] text-text-secondary tracking-widest">RESEARCH</span>
          <h2 class="text-xl font-medium mt-2">${escapeHTML(query)}</h2>
        </div>
        <div class="border-t border-border my-6"></div>
        <div class="flex items-center gap-2">
          <div class="loading-dots font-mono text-xs text-text-secondary tracking-widest">SEARCHING</div>
        </div>
      </main>
      ${footerHTML()}
    `;

    try {
      const data = await api('POST', '/research', { query, num_results: 10, compile: false });
      const results = data.results || [];

      app().innerHTML = `
        ${headerHTML(true, false)}
        <main class="max-w-3xl mx-auto px-6 pt-20 pb-28">
          <div class="mb-6">
            <span class="font-mono text-[10px] text-text-secondary tracking-widest">RESEARCH</span>
            <h2 class="text-xl font-medium mt-2">${escapeHTML(query)}</h2>
            <p class="font-mono text-xs text-text-secondary mt-2 tracking-wider">FOUND ${results.length} SOURCES VIA EXA</p>
          </div>
          <div class="border-t border-border my-6"></div>

          <div class="space-y-4" id="research-results">
            ${results.map((r, i) => {
              const checked = (r.score || 0) > 0.7 ? 'checked' : '';
              const domain = extractDomain(r.url);
              return `<label class="flex items-start gap-3 p-4 border border-border rounded-lg hover:bg-surface/50 cursor-pointer transition-colors">
                <input type="checkbox" ${checked} data-url="${escapeAttr(r.url)}" data-title="${escapeAttr(r.title)}" class="research-check mt-1 accent-accent-2">
                <div class="flex-1 min-w-0">
                  <div class="font-medium text-sm">${escapeHTML(r.title)}</div>
                  <div class="font-mono text-[10px] text-text-secondary mt-1 tracking-wider">
                    ${escapeHTML(domain)} · relevance: ${(r.score || 0).toFixed(2)}
                  </div>
                </div>
              </label>`;
            }).join('')}
          </div>

          ${results.length > 0 ? `
            <button id="ingest-selected-btn" onclick="ingestSelected()"
              class="mt-6 font-mono text-xs tracking-wider bg-text text-bg px-5 py-2.5 rounded hover:bg-text/90 transition-colors">
              INGEST SELECTED (<span id="selected-count">${results.filter(r => (r.score || 0) > 0.7).length}</span>)
            </button>
          ` : '<p class="text-sm text-text-secondary">No results found. Try a different query.</p>'}
        </main>
        ${footerHTML()}
      `;

      // Update count on checkbox change
      $$('.research-check').forEach(cb => {
        cb.addEventListener('change', updateSelectedCount);
      });
    } catch (err) {
      app().innerHTML = `
        ${headerHTML(true, false)}
        <main class="max-w-3xl mx-auto px-6 pt-20 pb-28">
          <div class="mb-8">
            <span class="font-mono text-[10px] text-text-secondary tracking-widest">RESEARCH</span>
            <h2 class="text-xl font-medium mt-2">${escapeHTML(query)}</h2>
          </div>
          <div class="border-t border-border my-6"></div>
          <p class="text-sm text-text-secondary">Research failed. This may require an Exa API key.</p>
          <p class="font-mono text-xs text-text-secondary mt-2">${escapeHTML(err.message)}</p>
        </main>
        ${footerHTML()}
      `;
    }
  }

  // ─── Ingest Modal ────────────────────────────────────────────────────
  window.openIngestModal = function () {
    // Remove existing modal if any
    const existing = $('#ingest-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'ingest-modal';
    modal.className = 'fixed inset-0 z-[100] flex items-center justify-center';
    modal.innerHTML = `
      <div class="absolute inset-0 bg-text/30 backdrop-blur-sm" onclick="closeIngestModal()"></div>
      <div class="relative bg-bg border border-border rounded-xl w-full max-w-lg mx-4 p-6 shadow-lg max-h-[80vh] overflow-y-auto">
        <div class="flex items-center justify-between mb-6">
          <span class="font-mono text-xs tracking-widest">INGEST NEW KNOWLEDGE</span>
          <button onclick="closeIngestModal()" class="text-text-secondary hover:text-text text-lg leading-none">&times;</button>
        </div>

        <div class="space-y-4">
          <input type="text" id="ingest-url" placeholder="Paste a URL..."
            class="w-full bg-surface border border-border rounded-lg px-4 py-3 text-sm font-sans placeholder:text-text-secondary/60 focus:outline-none focus:border-accent-2/40 transition-colors">

          <div class="flex items-center gap-2">
            <span class="font-mono text-[10px] text-text-secondary tracking-wider">OR</span>
          </div>

          <textarea id="ingest-text" rows="4" placeholder="Paste text content..."
            class="w-full bg-surface border border-border rounded-lg px-4 py-3 text-sm font-sans placeholder:text-text-secondary/60 focus:outline-none focus:border-accent-2/40 transition-colors resize-y"></textarea>

          <input type="text" id="ingest-title" placeholder="Title (optional)"
            class="w-full bg-surface border border-border rounded-lg px-4 py-3 text-sm font-sans placeholder:text-text-secondary/60 focus:outline-none focus:border-accent-2/40 transition-colors">

          <div class="flex gap-3">
            <button onclick="submitIngest()"
              class="font-mono text-xs tracking-wider bg-text text-bg px-5 py-2.5 rounded hover:bg-text/90 transition-colors">
              INGEST
            </button>
            <button onclick="window.location.hash='#/research/'; closeIngestModal()"
              class="font-mono text-xs tracking-wider border border-border px-4 py-2 hover:bg-surface transition-colors">
              RESEARCH TOPIC
            </button>
          </div>
        </div>

        <div class="border-t border-border mt-6 pt-4">
          <span class="font-mono text-[10px] text-text-secondary tracking-widest block mb-3">RECENT INGESTION</span>
          <div id="ingestion-feed" class="space-y-2">
            ${state.ingestions.length === 0
              ? '<p class="font-mono text-[10px] text-text-secondary/50">No recent ingestions</p>'
              : state.ingestions.map(ingestionItemHTML).join('')}
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  };

  window.closeIngestModal = function () {
    const modal = $('#ingest-modal');
    if (modal) modal.remove();
  };

  window.submitIngest = async function () {
    const url = $('#ingest-url')?.value?.trim();
    const text = $('#ingest-text')?.value?.trim();
    const title = $('#ingest-title')?.value?.trim();

    if (!url && !text) return;

    const body = {};
    if (url) body.url = url;
    else { body.text = text; body.title = title || undefined; }

    // Add to feed as processing
    const item = { source: url || title || 'Manual text', status: 'processing', time: 'now' };
    state.ingestions.unshift(item);
    updateIngestionFeed();

    try {
      const data = await api('POST', '/ingest', body);
      item.status = 'done';
      item.title = data.title;
      item.memories = data.memories_created;
      updateIngestionFeed();
      // Clear inputs
      if ($('#ingest-url')) $('#ingest-url').value = '';
      if ($('#ingest-text')) $('#ingest-text').value = '';
      if ($('#ingest-title')) $('#ingest-title').value = '';
    } catch (err) {
      item.status = 'error';
      item.error = err.message;
      updateIngestionFeed();
    }
  };

  function ingestionItemHTML(item) {
    const icon = item.status === 'done' ? '✓' : item.status === 'processing' ? '◌' : '✗';
    const cls = item.status === 'done' ? 'text-accent-4' : item.status === 'processing' ? 'text-accent-1' : 'text-red-500';
    const label = item.status === 'processing' ? 'compiling...' : (item.title || item.source);
    return `<div class="flex items-center gap-2 font-mono text-[11px]">
      <span class="${cls}">${icon}</span>
      <span class="text-text-secondary truncate">${escapeHTML(truncate(item.source, 40))}</span>
      <span class="text-text-secondary/50">→</span>
      <span class="truncate">${escapeHTML(label)}</span>
    </div>`;
  }

  function updateIngestionFeed() {
    const feed = $('#ingestion-feed');
    if (!feed) return;
    feed.innerHTML = state.ingestions.slice(0, 10).map(ingestionItemHTML).join('');
  }

  // ─── Research ingest ─────────────────────────────────────────────────
  window.ingestSelected = async function () {
    const checks = $$('.research-check:checked');
    if (checks.length === 0) return;

    const btn = $('#ingest-selected-btn');
    if (btn) { btn.textContent = 'INGESTING...'; btn.disabled = true; }

    let ingested = 0;
    for (const cb of checks) {
      const url = cb.dataset.url;
      try {
        await api('POST', '/ingest', { url });
        ingested++;
      } catch { /* skip failed */ }
    }

    // Show toast and redirect
    showToast(`Ingested ${ingested} sources`);
    setTimeout(() => navigate(''), 1500);
  };

  function updateSelectedCount() {
    const count = $$('.research-check:checked').length;
    const el = $('#selected-count');
    if (el) el.textContent = count;
  }

  // ─── Search binding ──────────────────────────────────────────────────
  function bindSearchInput(id) {
    const input = $(`#${id}`);
    if (!input) return;
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && input.value.trim()) {
        const q = input.value.trim();
        navigate(`/ask/${encodeURIComponent(q)}`);
      }
    });
  }

  // ─── Cmd+K focus ─────────────────────────────────────────────────────
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      // Focus whatever search bar is visible
      const input = $('input[type="text"]:not(#ingest-url):not(#ingest-text):not(#ingest-title)');
      if (input) input.focus();
    }
    // Escape closes modal only if it's open
    if (e.key === 'Escape' && $('#ingest-modal')) {
      e.stopPropagation();
      closeIngestModal();
    }
  });

  // ─── Toast ───────────────────────────────────────────────────────────
  function showToast(msg) {
    const toast = document.createElement('div');
    toast.className = 'fixed bottom-14 left-1/2 -translate-x-1/2 bg-text text-bg font-mono text-xs tracking-wider px-5 py-2.5 rounded-lg shadow-lg z-[200] transition-opacity';
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 2500);
  }

  // ─── Utilities ───────────────────────────────────────────────────────
  function escapeHTML(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function escapeAttr(str) {
    return escapeHTML(str || '');
  }

  function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.slice(0, len) + '...' : str;
  }

  function extractDomain(url) {
    try { return new URL(url).hostname; } catch { return url || ''; }
  }

  // ─── Init ────────────────────────────────────────────────────────────
  router();
})();
