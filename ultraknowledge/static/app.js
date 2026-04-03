/* ultraknowledge — single-page app */

(function () {
  'use strict';

  const $ = (sel, ctx) => (ctx || document).querySelector(sel);
  const $$ = (sel, ctx) => [...(ctx || document).querySelectorAll(sel)];
  const app = () => $('#app');

  const ACCENTS = ['accent-1', 'accent-2', 'accent-3', 'accent-4'];
  const ACCENT_HEX = { 'accent-1': '#E8913A', 'accent-2': '#3A8FE8', 'accent-3': '#6B3AE8', 'accent-4': '#3AE89B' };
  const GRAPH_BG = '#F5F3EF';
  const GRAPH_BORDER = '#E5E2DC';

  // ─── State ───────────────────────────────────────────────────────────
  let state = {
    articles: [],
    stats: { article_count: 0, system_state: 'READY' },
    ingestions: [],
  };
  let graphViewCleanup = null;
  let activeRouteToken = 0;

  // ─── Routing ─────────────────────────────────────────────────────────
  function navigate(hash) {
    window.location.hash = hash;
  }

  function getRoute() {
    const h = window.location.hash.slice(1) || '/';
    if (h === '/' || h === '') return { view: 'home' };
    if (h === '/graph') return { view: 'graph' };
    if (h.startsWith('/article/')) return { view: 'article', slug: decodeURIComponent(h.slice(9)) };
    if (h.startsWith('/ask/')) return { view: 'ask', question: decodeURIComponent(h.slice(5)) };
    if (h.startsWith('/research/')) return { view: 'research', query: decodeURIComponent(h.slice(10)) };
    return { view: 'home' };
  }

  async function router() {
    const routeToken = ++activeRouteToken;
    if (graphViewCleanup) {
      graphViewCleanup();
      graphViewCleanup = null;
    }
    const route = getRoute();
    switch (route.view) {
      case 'home': await renderHome(); break;
      case 'graph': await renderGraph(routeToken); break;
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

  async function loadGraph() {
    return api('GET', '/api/graph');
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
        <div class="w-full max-w-4xl flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <div class="flex-1">
            ${searchBarHTML('Ask your knowledge...', 'home-search')}
          </div>
          <button onclick="window.location.hash='#/graph'" class="graph-launch-btn group">
            <span class="graph-launch-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M6 7.5 12 12m0 0 6-6m-6 6 5.5 5M12 12 6.5 18"></path>
                <circle cx="6" cy="7.5" r="2.25" fill="currentColor" stroke="none"></circle>
                <circle cx="18" cy="6" r="2.25" fill="currentColor" stroke="none"></circle>
                <circle cx="17.5" cy="17" r="2.25" fill="currentColor" stroke="none"></circle>
                <circle cx="6.5" cy="18" r="2.25" fill="currentColor" stroke="none"></circle>
              </svg>
            </span>
            <span class="font-mono text-xs tracking-[0.24em]">GRAPH</span>
          </button>
        </div>
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

          <div class="article-toolbar">
            <div>
              <h1 class="text-3xl font-medium leading-tight">${escapeHTML(title)}</h1>
              <p class="font-mono text-[10px] text-text-secondary tracking-widest mt-2">STATIC ARTICLE VIEW</p>
            </div>
            <div class="article-export-shell" id="article-export-shell">
              <button type="button" id="article-export-btn" class="article-export-btn">
                <span class="font-mono text-xs tracking-[0.24em]">EXPORT</span>
              </button>
              <div id="article-export-menu" class="article-export-menu hidden">
                <button type="button" class="article-export-option" data-export-kind="report">REPORT (MD)</button>
                <button type="button" class="article-export-option" data-export-kind="briefing">BRIEFING (MD)</button>
                <button type="button" class="article-export-option" data-export-kind="slides">SLIDES (MARP)</button>
                <button type="button" class="article-export-option" data-export-kind="snapshot">HTML SNAPSHOT</button>
                <button type="button" class="article-export-option" data-export-kind="pdf">PDF</button>
              </div>
            </div>
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

      bindArticleExportMenu(slug);
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

  function bindArticleExportMenu(slug) {
    const shell = $('#article-export-shell');
    const button = $('#article-export-btn');
    const menu = $('#article-export-menu');
    if (!shell || !button || !menu) return;

    const closeMenu = () => menu.classList.add('hidden');
    const toggleMenu = (event) => {
      event.stopPropagation();
      menu.classList.toggle('hidden');
    };
    const onDocumentClick = (event) => {
      if (!shell.contains(event.target)) closeMenu();
    };

    button.addEventListener('click', toggleMenu);
    document.addEventListener('click', onDocumentClick);

    $$('.article-export-option', menu).forEach(option => {
      option.addEventListener('click', async () => {
        closeMenu();
        option.disabled = true;
        try {
          const filename = option.dataset.exportKind === 'snapshot'
            ? await exportArticleSnapshot(slug)
            : await exportArticleAsset(slug, option.dataset.exportKind);
          showToast(`Exported as ${filename}`);
        } catch (err) {
          showToast(`Export failed: ${err.message}`);
        } finally {
          option.disabled = false;
        }
      });
    });
  }

  async function exportArticleAsset(slug, format) {
    const result = await api('POST', '/export', { topic: slug, format });
    if (!result.filename) throw new Error('Missing export filename');
    await downloadFile(`/api/exports/${encodeURIComponent(result.filename)}`, result.filename);
    return result.filename;
  }

  async function exportArticleSnapshot(slug) {
    return downloadFile('/api/snapshot', null, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slug }),
    });
  }

  async function downloadFile(url, fallbackFilename, options) {
    const response = await fetch(url, options || {});
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const blob = await response.blob();
    const filename = extractFilename(response.headers.get('content-disposition')) || fallbackFilename || 'download';
    const objectUrl = window.URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(objectUrl);
    return filename;
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

  // ─── Graph View ──────────────────────────────────────────────────────
  async function renderGraph(routeToken) {
    app().innerHTML = `
      <main class="graph-shell">
        <header class="graph-topbar">
          <div class="flex items-center gap-4">
            <button onclick="window.location.hash=''" class="font-mono text-xs text-text-secondary hover:text-text tracking-[0.24em] transition-colors">← BACK</button>
            <div>
              <h1 class="font-mono text-sm sm:text-base tracking-[0.28em]">KNOWLEDGE GRAPH</h1>
              <p class="font-mono text-[10px] text-text-secondary tracking-[0.24em] mt-1">MAPPING ARTICLE RELATIONSHIPS</p>
            </div>
          </div>
          <div class="graph-stats">
            <span class="graph-stat">LOADING NODES</span>
            <span class="graph-stat">LOADING EDGES</span>
          </div>
        </header>
        <section class="graph-stage">
          <div id="graph-canvas" class="graph-canvas"></div>
          <div id="graph-tooltip" class="graph-tooltip hidden"></div>
          <div class="graph-controls">
            <div>
              <label for="graph-charge" class="graph-control-label">DENSITY / CHARGE</label>
              <input id="graph-charge" class="graph-slider" type="range" min="30" max="260" value="120">
            </div>
            <div>
              <label for="graph-link-distance" class="graph-control-label">LINK DISTANCE</label>
              <input id="graph-link-distance" class="graph-slider" type="range" min="40" max="220" value="110">
            </div>
          </div>
        </section>
      </main>
    `;

    if (!window.ForceGraph) {
      $('#graph-canvas').innerHTML = '<div class="graph-empty-state">ForceGraph failed to load.</div>';
      return;
    }

    let cleanedUp = false;
    const cleanupFns = [];
    graphViewCleanup = function () {
      if (cleanedUp) return;
      cleanedUp = true;
      cleanupFns.forEach(fn => fn());
    };

    try {
      const data = await loadGraph();
      if (cleanedUp || routeToken !== activeRouteToken || getRoute().view !== 'graph') return;

      const container = $('#graph-canvas');
      const tooltip = $('#graph-tooltip');
      const chargeInput = $('#graph-charge');
      const linkDistanceInput = $('#graph-link-distance');
      if (!container || !tooltip || !chargeInput || !linkDistanceInput) return;

      const nodes = (data.nodes || []).map(node => ({
        ...node,
        __radius: clamp(4, scaleSourceCount(node.source_count, data.nodes || []), 20),
        __linkCount: 0,
      }));
      const nodeById = Object.fromEntries(nodes.map(node => [node.id, node]));
      const edges = (data.edges || []).filter(edge => nodeById[edge.source] && nodeById[edge.target]);
      const clusters = data.clusters || [];
      const clusterColors = Object.fromEntries(clusters.map(cluster => [cluster.id, cluster.color]));

      edges.forEach(edge => {
        nodeById[edge.source].__linkCount += 1;
        nodeById[edge.target].__linkCount += 1;
      });

      const stats = $$('.graph-stat');
      if (stats[0]) stats[0].textContent = `${nodes.length} NODES`;
      if (stats[1]) stats[1].textContent = `${edges.length} EDGES`;

      if (nodes.length === 0) {
        container.innerHTML = '<div class="graph-empty-state">No articles compiled yet.</div>';
        return;
      }

      let hoveredNode = null;
      let pointer = { x: 0, y: 0 };

      const fg = window.ForceGraph()(container)
        .backgroundColor(GRAPH_BG)
        .graphData({ nodes, links: edges })
        .nodeId('id')
        .linkSource('source')
        .linkTarget('target')
        .linkColor(() => GRAPH_BORDER)
        .linkWidth(0.8)
        .linkDirectionalParticles(0)
        .nodeCanvasObjectMode(() => 'replace')
        .nodeCanvasObject((node, ctx, globalScale) => {
          const radius = node.__radius || 6;
          const color = clusterColors[node.cluster] || ACCENT_HEX['accent-2'];

          ctx.beginPath();
          ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
          ctx.fillStyle = color;
          ctx.shadowColor = `${color}33`;
          ctx.shadowBlur = hoveredNode && hoveredNode.id === node.id ? 18 : 10;
          ctx.fill();
          ctx.shadowBlur = 0;

          const shouldLabel = globalScale >= 1.55 || (hoveredNode && hoveredNode.id === node.id);
          if (!shouldLabel) return;

          const fontSize = Math.max(10 / globalScale, 3.5);
          const label = node.title;
          ctx.font = `500 ${fontSize}px JetBrains Mono`;
          const textWidth = ctx.measureText(label).width;
          const padX = 6 / globalScale;
          const padY = 4 / globalScale;
          const boxX = node.x + radius + 6 / globalScale;
          const boxY = node.y - fontSize;

          ctx.fillStyle = 'rgba(245, 243, 239, 0.92)';
          ctx.fillRect(boxX - padX, boxY - padY, textWidth + padX * 2, fontSize + padY * 2);
          ctx.fillStyle = '#1A1A1A';
          ctx.fillText(label, boxX, node.y + fontSize * 0.15);
        })
        .nodePointerAreaPaint((node, color, ctx) => {
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(node.x, node.y, (node.__radius || 6) + 4, 0, 2 * Math.PI, false);
          ctx.fill();
        })
        .onNodeClick(node => navigate(`/article/${encodeURIComponent(node.id)}`))
        .onNodeHover(node => {
          hoveredNode = node || null;
          updateTooltip(node, tooltip, pointer);
          container.style.cursor = node ? 'pointer' : 'grab';
        });

      fg.d3Force('charge').strength(-Number(chargeInput.value));
      fg.d3Force('link').distance(Number(linkDistanceInput.value));
      fg.cooldownTicks(120);
      fg.onEngineStop(() => fg.zoomToFit(500, 60));

      const onPointerMove = (event) => {
        const rect = container.getBoundingClientRect();
        pointer = { x: event.clientX - rect.left, y: event.clientY - rect.top };
        if (hoveredNode) updateTooltip(hoveredNode, tooltip, pointer);
      };
      const onPointerLeave = () => {
        hoveredNode = null;
        updateTooltip(null, tooltip, pointer);
        container.style.cursor = 'grab';
      };
      container.addEventListener('pointermove', onPointerMove);
      container.addEventListener('pointerleave', onPointerLeave);

      const onResize = () => {
        fg.width(container.clientWidth);
        fg.height(container.clientHeight);
      };
      window.addEventListener('resize', onResize);
      onResize();

      const onChargeInput = () => {
        fg.d3Force('charge').strength(-Number(chargeInput.value));
        fg.d3ReheatSimulation();
      };
      const onLinkDistanceInput = () => {
        fg.d3Force('link').distance(Number(linkDistanceInput.value));
        fg.d3ReheatSimulation();
      };
      chargeInput.addEventListener('input', onChargeInput);
      linkDistanceInput.addEventListener('input', onLinkDistanceInput);

      cleanupFns.push(() => window.removeEventListener('resize', onResize));
      cleanupFns.push(() => container.removeEventListener('pointermove', onPointerMove));
      cleanupFns.push(() => container.removeEventListener('pointerleave', onPointerLeave));
      cleanupFns.push(() => chargeInput.removeEventListener('input', onChargeInput));
      cleanupFns.push(() => linkDistanceInput.removeEventListener('input', onLinkDistanceInput));
      cleanupFns.push(() => {
        tooltip.classList.add('hidden');
      });
      cleanupFns.push(() => {
        if (typeof fg.pauseAnimation === 'function') fg.pauseAnimation();
        if (typeof fg._destructor === 'function') fg._destructor();
      });
    } catch (err) {
      if (cleanedUp || routeToken !== activeRouteToken || getRoute().view !== 'graph') return;
      const container = $('#graph-canvas');
      if (container) {
        container.innerHTML = `<div class="graph-empty-state">Unable to load graph.<br><span class="font-mono text-[11px] text-text-secondary">${escapeHTML(err.message)}</span></div>`;
      }
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

  function extractFilename(contentDisposition) {
    if (!contentDisposition) return '';
    const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8Match) return decodeURIComponent(utf8Match[1]);
    const plainMatch = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
    return plainMatch ? plainMatch[1] : '';
  }

  function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.slice(0, len) + '...' : str;
  }

  function extractDomain(url) {
    try { return new URL(url).hostname; } catch { return url || ''; }
  }

  function scaleSourceCount(value, nodes) {
    const counts = nodes.map(node => node.source_count || 0);
    const min = Math.min.apply(null, counts);
    const max = Math.max.apply(null, counts);
    if (min === max) return 10;
    const ratio = ((value || 0) - min) / (max - min);
    return 4 + ratio * 16;
  }

  function clamp(min, value, max) {
    return Math.max(min, Math.min(value, max));
  }

  function updateTooltip(node, tooltip, pointer) {
    if (!tooltip) return;
    if (!node) {
      tooltip.classList.add('hidden');
      return;
    }

    tooltip.innerHTML = DOMPurify.sanitize(`
      <div class="graph-tooltip-title">${escapeHTML(node.title)}</div>
      <div class="graph-tooltip-meta">${node.source_count || 0} sources</div>
      <div class="graph-tooltip-meta">${node.__linkCount || 0} links</div>
    `);
    tooltip.style.transform = `translate(${pointer.x + 18}px, ${pointer.y + 18}px)`;
    tooltip.classList.remove('hidden');
  }

  // ─── Init ────────────────────────────────────────────────────────────
  router();
})();
