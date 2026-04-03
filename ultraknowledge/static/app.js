/* ultraknowledge — single-page app */

(function () {
  'use strict';

  const $ = (sel, ctx) => (ctx || document).querySelector(sel);
  const $$ = (sel, ctx) => [...(ctx || document).querySelectorAll(sel)];
  const app = () => $('#app');

  const ACCENTS = ['accent-1', 'accent-2', 'accent-3', 'accent-4'];
  const ACCENT_HEX = { 'accent-1': '#D97B2B', 'accent-2': '#2E7DC9', 'accent-3': '#6B3AE8', 'accent-4': '#2AA872' };
  const GRAPH_BG = '#F0EDE7';
  const GRAPH_BORDER = '#DDD8CE';

  // Category icons (inline SVG for each accent)
  const CATEGORY_ICONS = [
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3"><path d="M10 2L2 7l8 5 8-5-8-5zM2 13l8 5 8-5M2 10l8 5 8-5"/></svg>',
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3"><circle cx="10" cy="10" r="7"/><path d="M10 3v14M3 10h14M5 5l10 10M15 5L5 15"/></svg>',
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3"><path d="M3 3h5v5H3zM12 3h5v5h-5zM3 12h5v5H3zM12 12h5v5h-5z"/></svg>',
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3"><path d="M10 2v16M6 6l4-4 4 4M2 10h16M6 14l4 4 4-4"/></svg>',
  ];

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
    return `<div class="uk-logo">
      <div class="uk-logo-grid">
        <div class="uk-logo-dot" style="background:var(--accent-1)"></div>
        <div class="uk-logo-dot" style="background:var(--accent-2)"></div>
        <div class="uk-logo-dot" style="background:var(--accent-3)"></div>
        <div class="uk-logo-dot" style="background:var(--accent-4)"></div>
      </div>
      <span class="uk-logo-text">UK</span>
    </div>`;
  }

  function headerHTML(showBack, showIngest) {
    return `<header class="uk-header">
      <div class="uk-header-inner">
        <div class="flex items-center gap-4">
          ${showBack ? `<button onclick="window.location.hash=''" class="font-mono text-[10px] text-text-secondary hover:text-text tracking-[0.2em] transition-colors flex items-center gap-2"><span class="text-sm">&#8592;</span> BACK</button>` : logoHTML()}
        </div>
        ${showIngest !== false ? `<button onclick="openIngestModal()" class="uk-ingest-btn">+ INGEST</button>` : ''}
      </div>
    </header>`;
  }

  function footerHTML() {
    const stateColor = state.stats.system_state === 'READY' ? 'var(--accent-4)' : 'var(--accent-1)';
    return `<footer class="uk-footer">
      <div class="uk-footer-inner">
        <div class="uk-footer-stat">
          <span class="font-display italic text-[11px]" style="color:var(--text-secondary)">${state.stats.article_count.toLocaleString()}</span>
          <span>ARTICLES COMPILED</span>
        </div>
        <div class="uk-footer-stat">
          <span class="uk-footer-dot" style="background:${stateColor}"></span>
          <span>${state.stats.system_state}</span>
        </div>
      </div>
    </footer>`;
  }

  function searchBarHTML(placeholder, id, scope) {
    const scopeAttr = scope ? `data-scope="${scope}"` : '';
    return `<div class="uk-search-wrap">
      <input type="text" id="${id}" ${scopeAttr}
        class="uk-search-input"
        placeholder="${placeholder}">
      <div class="uk-search-hint">
        <span class="uk-search-kbd">&#8984;K</span>
        <span class="uk-search-kbd">ENTER</span>
      </div>
    </div>`;
  }

  function topicCardHTML(article, index) {
    const accent = ACCENTS[index % ACCENTS.length];
    const accentHex = ACCENT_HEX[accent];
    const isActive = index === 0;
    const title = article.title || article.slug;
    const slug = article.slug;
    const icon = CATEGORY_ICONS[index % CATEGORY_ICONS.length];
    const fillWidth = Math.min(100, 30 + Math.random() * 70);

    return `<div class="topic-card topic-card-${accent} animate-fade-in-up stagger-${index + 1}" onclick="window.location.hash='#/article/${encodeURIComponent(slug)}'">
      <span class="topic-card-number">${String(index + 1).padStart(2, '0')}</span>
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2.5">
          <div style="width:18px;height:18px;color:${accentHex};opacity:0.6">${icon}</div>
          <span class="topic-card-label">TOPIC ${String(index + 1).padStart(2, '0')}</span>
        </div>
        ${isActive ? `<span class="topic-card-tag" style="color:${accentHex}; background:${accentHex}12"><span style="width:5px;height:5px;border-radius:50%;background:${accentHex};display:inline-block"></span> LATEST</span>` : ''}
      </div>
      <h3 class="topic-card-title">${title}</h3>
      <div class="topic-card-bar">
        <div class="topic-card-bar-fill" style="width:${fillWidth}%; background:${accentHex}"></div>
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
        <div class="uk-hero text-center mb-12 animate-fade-in-up">
          <h1 class="uk-hero-title">Ultra<em class="font-display italic" style="font-style:italic">Knowledge</em></h1>
          <p class="uk-hero-subtitle">LLM-COMPILED KNOWLEDGE BASE</p>
        </div>
        <div class="w-full max-w-4xl flex flex-col sm:flex-row items-stretch sm:items-center gap-3 animate-fade-in-up" style="animation-delay:0.1s">
          <div class="flex-1">
            ${searchBarHTML('Ask your knowledge base anything\u2026', 'home-search')}
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
            <span class="font-mono text-[10px] tracking-[0.24em]">GRAPH</span>
          </button>
        </div>
        ${state.articles.length > 0 ? `
          <div class="w-full max-w-4xl mt-16">
            <div class="flex items-center justify-between mb-6 px-1">
              <div class="flex items-center gap-3">
                <div class="uk-divider" style="width:2rem"></div>
                <span class="font-mono text-[9px] text-text-muted tracking-[0.28em]">KNOWLEDGE INDEX</span>
                <div class="uk-divider" style="width:2rem"></div>
              </div>
              <span class="font-mono text-[9px] text-text-muted tracking-[0.2em]">${state.articles.length} TOPICS</span>
            </div>
            <div class="grid ${gridCols} gap-5">
              ${cards}
            </div>
          </div>
        ` : `
          <div class="uk-empty-state mt-16 animate-fade-in-up" style="animation-delay:0.2s">
            <div class="uk-empty-state-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" style="color:var(--text-muted)">
                <path d="M12 6v6l4 2M12 2a10 10 0 100 20 10 10 0 000-20z"/>
              </svg>
            </div>
            <p class="font-display italic text-xl text-text-secondary mb-2">No articles yet</p>
            <p class="font-mono text-[10px] text-text-muted tracking-[0.2em]">INGEST SOME KNOWLEDGE TO GET STARTED</p>
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
      <main class="max-w-3xl mx-auto px-6 pt-24 pb-28">
        <div class="flex items-center gap-2 mb-2 animate-fade-in">
          <div class="loading-dots font-mono text-[10px] text-text-muted tracking-widest">LOADING</div>
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
        <main class="max-w-3xl mx-auto px-6 pt-24 pb-28">
          <div class="animate-fade-in-up">
            <div class="flex items-center gap-3 mb-4">
              <span class="topic-card-label">TOPIC ${String(idx >= 0 ? idx + 1 : 0).padStart(2, '0')}</span>
              ${idx === 0 ? `<span class="topic-card-tag" style="color:${accentHex}; background:${accentHex}12"><span style="width:5px;height:5px;border-radius:50%;background:${accentHex};display:inline-block"></span> LATEST</span>` : ''}
            </div>

            <div class="article-toolbar">
              <div>
                <h1 class="font-display text-3xl sm:text-4xl leading-tight" style="letter-spacing:-0.01em">${escapeHTML(title)}</h1>
                <p class="font-mono text-[9px] text-text-muted tracking-[0.22em] mt-3">COMPILED ARTICLE &middot; STATIC VIEW</p>
              </div>
              <div class="article-export-shell" id="article-export-shell">
                <button type="button" id="article-export-btn" class="article-export-btn">
                  <span class="font-mono text-[10px] tracking-[0.2em]">EXPORT</span>
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
          </div>

          <div class="uk-divider my-8"></div>

          <article class="prose-article animate-fade-in-up" style="animation-delay:0.12s">
            ${renderMarkdown(content)}
          </article>

          ${relatedTopics.length > 0 ? `
            <div class="mt-12 pt-8 animate-fade-in-up" style="animation-delay:0.2s; border-top: 1px solid var(--border-subtle)">
              <span class="font-mono text-[9px] text-text-muted tracking-[0.22em] block mb-4">RELATED TOPICS</span>
              <div class="flex flex-wrap gap-2">
                ${relatedTopics.map(t => {
                  const s = t.toLowerCase().replace(/\s+/g, '-');
                  return `<a href="#/article/${encodeURIComponent(s)}" class="inline-flex items-center gap-1.5 font-mono text-[11px] text-accent-2 hover:text-text px-3 py-1.5 rounded-lg border border-border-subtle hover:border-accent-2/30 transition-all" style="background:rgba(46,125,201,0.03)">
                    <span style="opacity:0.4">&#91;&#91;</span>${t}<span style="opacity:0.4">&#93;&#93;</span>
                  </a>`;
                }).join('')}
              </div>
            </div>
          ` : ''}

          <div class="mt-10 pt-8 animate-fade-in-up" style="animation-delay:0.25s; border-top: 1px solid var(--border-subtle)">
            ${searchBarHTML(`Ask about ${title}\u2026`, 'article-search', slug)}
          </div>
        </main>
        ${footerHTML()}
      `;

      bindArticleExportMenu(slug);
      bindSearchInput('article-search');
    } catch (err) {
      app().innerHTML = `
        ${headerHTML(true, true)}
        <main class="max-w-3xl mx-auto px-6 pt-24 pb-28">
          <div class="uk-empty-state mt-16 animate-fade-in-up">
            <div class="uk-empty-state-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" style="color:var(--text-muted)">
                <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
              </svg>
            </div>
            <p class="font-display italic text-xl text-text-secondary mb-2">Article not found</p>
            <p class="font-mono text-[10px] text-text-muted tracking-[0.15em] mb-6">${escapeHTML(slug)}</p>
            <button onclick="window.location.hash='#/research/${encodeURIComponent(slug.replace(/-/g, ' '))}'" class="uk-ingest-btn">RESEARCH THIS TOPIC &rarr;</button>
          </div>
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
      <main class="max-w-3xl mx-auto px-6 pt-24 pb-28">
        <div class="mb-8 animate-fade-in-up">
          <span class="font-mono text-[9px] text-text-muted tracking-[0.22em]">QUESTION</span>
          <h2 class="font-display text-2xl mt-3" style="line-height:1.3">${escapeHTML(question)}</h2>
        </div>
        <div class="uk-divider my-6"></div>
        <div class="flex items-center gap-3 animate-fade-in" style="animation-delay:0.15s">
          <div style="width:8px;height:8px;border-radius:50%;background:var(--accent-1);animation:pulseGlow 1.5s ease-in-out infinite"></div>
          <div class="loading-dots font-mono text-[10px] text-text-secondary tracking-[0.2em]">REASONING</div>
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
      const confClass = confidence > 0.7 ? 'confidence-high' : confidence > 0.4 ? 'confidence-medium' : 'confidence-low';

      app().innerHTML = `
        ${headerHTML(true, false)}
        <main class="max-w-3xl mx-auto px-6 pt-24 pb-28">
          <div class="mb-8 animate-fade-in-up">
            <span class="font-mono text-[9px] text-text-muted tracking-[0.22em]">QUESTION</span>
            <h2 class="font-display text-2xl mt-3" style="line-height:1.3">${escapeHTML(question)}</h2>
          </div>
          <div class="uk-divider my-6"></div>

          <div class="prose-article animate-fade-in-up" style="animation-delay:0.08s">
            ${renderMarkdown(answer)}
          </div>

          ${citations.length > 0 ? `
            <div class="mt-10 pt-6 animate-fade-in-up" style="animation-delay:0.15s; border-top: 1px solid var(--border-subtle)">
              <span class="font-mono text-[9px] text-text-muted tracking-[0.22em] block mb-4">SOURCES CITED</span>
              <div class="space-y-2.5">
                ${citations.map((c, i) => `
                  <div class="flex items-start gap-3 text-sm">
                    <span class="font-display italic text-text-muted text-lg leading-none mt-0.5">${i + 1}</span>
                    <span class="text-text-secondary">${escapeHTML(c.title)}${c.score ? ` <span class="font-mono text-[9px] text-text-muted">&middot; ${c.score.toFixed(2)}</span>` : ''}</span>
                  </div>
                `).join('')}
              </div>
            </div>
          ` : ''}

          <div class="flex items-center gap-6 mt-8 pt-5" style="border-top: 1px solid var(--border-subtle)">
            <span class="font-mono text-[9px] tracking-[0.2em] ${confClass}">CONFIDENCE: ${confLabel}</span>
            <span class="font-mono text-[9px] text-text-muted tracking-[0.2em]">${citations.length} ARTICLES</span>
          </div>

          ${needsResearch || suggestedQueries.length > 0 ? `
            <button onclick="window.location.hash='#/research/${encodeURIComponent(question)}'"
              class="mt-6 uk-ingest-btn">
              RESEARCH FURTHER &rarr;
            </button>
          ` : ''}

          <div class="mt-10 pt-8" style="border-top: 1px solid var(--border-subtle)">
            ${searchBarHTML('Ask a follow-up\u2026', 'followup-search')}
          </div>
        </main>
        ${footerHTML()}
      `;

      bindSearchInput('followup-search');
    } catch (err) {
      app().innerHTML = `
        ${headerHTML(true, false)}
        <main class="max-w-3xl mx-auto px-6 pt-24 pb-28">
          <div class="mb-8 animate-fade-in-up">
            <span class="font-mono text-[9px] text-text-muted tracking-[0.22em]">QUESTION</span>
            <h2 class="font-display text-2xl mt-3" style="line-height:1.3">${escapeHTML(question)}</h2>
          </div>
          <div class="uk-divider my-6"></div>
          <p class="text-sm text-text-secondary">Something went wrong while processing your question.</p>
          <p class="font-mono text-[10px] text-text-muted mt-2">${escapeHTML(err.message)}</p>
        </main>
        ${footerHTML()}
      `;
    }
  }

  // ─── Research View ───────────────────────────────────────────────────
  async function renderResearch(query) {
    app().innerHTML = `
      ${headerHTML(true, false)}
      <main class="max-w-3xl mx-auto px-6 pt-24 pb-28">
        <div class="mb-8 animate-fade-in-up">
          <span class="font-mono text-[9px] text-text-muted tracking-[0.22em]">RESEARCH</span>
          <h2 class="font-display text-2xl mt-3" style="line-height:1.3">${escapeHTML(query)}</h2>
        </div>
        <div class="uk-divider my-6"></div>
        <div class="flex items-center gap-3 animate-fade-in" style="animation-delay:0.15s">
          <div style="width:8px;height:8px;border-radius:50%;background:var(--accent-2);animation:pulseGlow 1.5s ease-in-out infinite"></div>
          <div class="loading-dots font-mono text-[10px] text-text-secondary tracking-[0.2em]">SEARCHING</div>
        </div>
      </main>
      ${footerHTML()}
    `;

    try {
      const data = await api('POST', '/research', { query, num_results: 10, compile: false });
      const results = data.results || [];

      app().innerHTML = `
        ${headerHTML(true, false)}
        <main class="max-w-3xl mx-auto px-6 pt-24 pb-28">
          <div class="mb-6 animate-fade-in-up">
            <span class="font-mono text-[9px] text-text-muted tracking-[0.22em]">RESEARCH</span>
            <h2 class="font-display text-2xl mt-3" style="line-height:1.3">${escapeHTML(query)}</h2>
            <p class="font-mono text-[9px] text-text-muted mt-3 tracking-[0.2em]">FOUND ${results.length} SOURCES VIA EXA</p>
          </div>
          <div class="uk-divider my-6"></div>

          <div class="space-y-3" id="research-results">
            ${results.map((r, i) => {
              const checked = (r.score || 0) > 0.7 ? 'checked' : '';
              const domain = extractDomain(r.url);
              return `<label class="flex items-start gap-3 p-4 border border-border-subtle rounded-xl hover:bg-surface/50 cursor-pointer transition-all animate-fade-in-up stagger-${Math.min(i + 1, 5)}" style="background:var(--surface-raised)">
                <input type="checkbox" ${checked} data-url="${escapeAttr(r.url)}" data-title="${escapeAttr(r.title)}" class="research-check mt-1 accent-accent-2">
                <div class="flex-1 min-w-0">
                  <div class="font-medium text-sm">${escapeHTML(r.title)}</div>
                  <div class="font-mono text-[9px] text-text-muted mt-1.5 tracking-[0.1em]">
                    ${escapeHTML(domain)} &middot; relevance: ${(r.score || 0).toFixed(2)}
                  </div>
                </div>
              </label>`;
            }).join('')}
          </div>

          ${results.length > 0 ? `
            <button id="ingest-selected-btn" onclick="ingestSelected()"
              class="mt-8 font-mono text-[10px] tracking-[0.2em] bg-text text-bg px-6 py-3 rounded-lg hover:opacity-90 transition-opacity">
              INGEST SELECTED (<span id="selected-count">${results.filter(r => (r.score || 0) > 0.7).length}</span>)
            </button>
          ` : `
            <div class="uk-empty-state mt-8">
              <p class="font-display italic text-lg text-text-secondary">No results found</p>
              <p class="font-mono text-[10px] text-text-muted tracking-[0.15em] mt-1">TRY A DIFFERENT QUERY</p>
            </div>
          `}
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
        <main class="max-w-3xl mx-auto px-6 pt-24 pb-28">
          <div class="mb-8 animate-fade-in-up">
            <span class="font-mono text-[9px] text-text-muted tracking-[0.22em]">RESEARCH</span>
            <h2 class="font-display text-2xl mt-3" style="line-height:1.3">${escapeHTML(query)}</h2>
          </div>
          <div class="uk-divider my-6"></div>
          <p class="text-sm text-text-secondary">Research failed. This may require an Exa API key.</p>
          <p class="font-mono text-[10px] text-text-muted mt-2">${escapeHTML(err.message)}</p>
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
            <button onclick="window.location.hash=''" class="font-mono text-[10px] text-text-secondary hover:text-text tracking-[0.2em] transition-colors flex items-center gap-2"><span class="text-sm">&#8592;</span> BACK</button>
            <div>
              <h1 class="font-display text-lg sm:text-xl" style="letter-spacing:-0.01em">Knowledge Graph</h1>
              <p class="font-mono text-[9px] text-text-muted tracking-[0.2em] mt-0.5">MAPPING ARTICLE RELATIONSHIPS</p>
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
              <label for="graph-charge" class="graph-control-label">DENSITY</label>
              <input id="graph-charge" class="graph-slider" type="range" min="0" max="100" value="50">
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

          ctx.fillStyle = 'rgba(240, 237, 231, 0.92)';
          ctx.fillRect(boxX - padX, boxY - padY, textWidth + padX * 2, fontSize + padY * 2);
          ctx.fillStyle = '#1A1714';
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

      const applyDensity = (val) => {
        // val: 0 (very sparse) → 100 (very dense)
        // charge: -300 (strong repulsion) → -10 (minimal repulsion)
        const charge = -300 + val * 2.9;
        // link distance: scaled inversely — dense = shorter links
        const baseLinkDist = Number(linkDistanceInput.value);
        const linkScale = 1.5 - val / 100;  // 1.5x at 0, 0.5x at 100
        fg.d3Force('charge').strength(charge);
        fg.d3Force('link').distance(baseLinkDist * linkScale);
      };
      applyDensity(Number(chargeInput.value));
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
        applyDensity(Number(chargeInput.value));
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
      <div class="absolute inset-0 bg-text/30 backdrop-blur-sm animate-fade-in" onclick="closeIngestModal()"></div>
      <div class="relative bg-bg border border-border rounded-2xl w-full max-w-lg mx-4 p-7 max-h-[80vh] overflow-y-auto animate-scale-in" style="box-shadow: 0 24px 64px rgba(26,23,20,0.12)">
        <div class="flex items-center justify-between mb-7">
          <div>
            <span class="font-mono text-[9px] tracking-[0.22em] text-text-muted block mb-1">NEW ENTRY</span>
            <span class="font-display text-lg">Ingest Knowledge</span>
          </div>
          <button onclick="closeIngestModal()" class="text-text-muted hover:text-text text-xl leading-none transition-colors w-8 h-8 flex items-center justify-center rounded-lg hover:bg-bg-warm">&times;</button>
        </div>

        <div class="space-y-4">
          <input type="text" id="ingest-url" placeholder="Paste a URL\u2026"
            class="uk-search-input" style="font-size:0.9375rem;padding:0.85rem 1.15rem">

          <div class="flex items-center gap-3">
            <div class="uk-divider flex-1"></div>
            <span class="font-mono text-[9px] text-text-muted tracking-[0.2em]">OR</span>
            <div class="uk-divider flex-1"></div>
          </div>

          <textarea id="ingest-text" rows="4" placeholder="Paste text content\u2026"
            class="uk-search-input resize-y" style="font-size:0.9375rem;padding:0.85rem 1.15rem;border-radius:12px"></textarea>

          <input type="text" id="ingest-title" placeholder="Title (optional)"
            class="uk-search-input" style="font-size:0.9375rem;padding:0.85rem 1.15rem">

          <div class="flex gap-3 pt-1">
            <button onclick="submitIngest()"
              class="font-mono text-[10px] tracking-[0.2em] bg-text text-bg px-6 py-3 rounded-lg hover:opacity-90 transition-opacity">
              INGEST
            </button>
            <button onclick="window.location.hash='#/research/'; closeIngestModal()"
              class="uk-ingest-btn">
              RESEARCH TOPIC
            </button>
          </div>
        </div>

        <div class="mt-7 pt-5" style="border-top: 1px solid var(--border-subtle)">
          <span class="font-mono text-[9px] text-text-muted tracking-[0.22em] block mb-3">RECENT INGESTION</span>
          <div id="ingestion-feed" class="space-y-2">
            ${state.ingestions.length === 0
              ? '<p class="font-mono text-[10px] text-text-muted" style="opacity:0.5">No recent ingestions</p>'
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
    const icon = item.status === 'done' ? '&#10003;' : item.status === 'processing' ? '&#9676;' : '&#10007;';
    const cls = item.status === 'done' ? 'text-accent-4' : item.status === 'processing' ? 'text-accent-1' : 'text-red-500';
    const label = item.status === 'processing' ? 'compiling\u2026' : (item.title || item.source);
    return `<div class="flex items-center gap-2 font-mono text-[10px]">
      <span class="${cls}">${icon}</span>
      <span class="text-text-muted truncate">${escapeHTML(truncate(item.source, 40))}</span>
      <span class="text-text-muted" style="opacity:0.4">&rarr;</span>
      <span class="truncate text-text-secondary">${escapeHTML(label)}</span>
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
    toast.className = 'uk-toast';
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
