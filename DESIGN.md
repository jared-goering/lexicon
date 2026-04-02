# DESIGN.md — ultraknowledge UI Specification

> Reference mockup: [Variant.ai design](https://variant.com/shared/fbc458cf-b880-4e3a-8c6f-4b0aa2cf0424?t=1775168661200)

---

## Design Philosophy

**Radical simplicity.** The UI is a search bar. Everything else is secondary.

- No dashboard clutter, no stats widgets, no sidebar navigation on home
- The knowledge base speaks through the search bar — ask it anything
- Content-first: articles should read like a beautifully typeset blog
- Dark-on-light, monospace accents, generous whitespace

---

## Color Palette

| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#F5F3EF` | Page background (warm off-white) |
| `--surface` | `#FFFFFF` | Cards, search bar, article panels |
| `--text` | `#1A1A1A` | Primary text |
| `--text-secondary` | `#6B6B6B` | Labels, metadata, hints |
| `--accent-1` | `#E8913A` | Topic #1 progress bar, active states |
| `--accent-2` | `#3A8FE8` | Topic #2 progress bar, links |
| `--accent-3` | `#6B3AE8` | Topic #3 progress bar |
| `--border` | `#E5E2DC` | Card borders, dividers |
| `--mono` | `IBM Plex Mono` or `JetBrains Mono` | Labels, metadata, system text |
| `--sans` | `Inter` or system sans-serif | Body text, article prose |

---

## Typography

- **Brand name:** All caps, ultra-wide letter-spacing (`ULTRAKNOWLEDGE`), monospace
- **Labels/metadata:** Uppercase monospace, small (`TOPIC // #1`, `COMPILED INDEX: 14,204 ARTICLES`)
- **Body text:** Clean sans-serif, 16-18px, 1.6 line-height
- **Headings in articles:** Sans-serif, semibold, no uppercase

---

## Home Screen

The home screen has exactly three elements:

### 1. Brand + Search Bar (center)
- `ULTRAKNOWLEDGE` in spaced uppercase monospace, centered
- Below it: a large search/ask input bar
  - Placeholder: `Ask your knowledge...`
  - Right-aligned submit label: `ENTER TO ASK` (monospace, muted)
  - Subtle border, white background, generous padding
  - No icons, no decorations

### 2. Topic Cards (below search)
- Row of 3 cards showing top/recent topics
- Each card:
  - Label: `TOPIC // #1` (monospace, muted)
  - Status badge: `ACTIVE` (accent color, right-aligned) — only on the most recently updated topic
  - Topic name: clean sans-serif, medium weight (e.g., "Neural Architecture")
  - Colored progress bar at bottom (each topic gets a unique accent color)
  - Click → opens article view for that topic
- Cards have subtle borders, white background, no shadows
- Max 3-5 visible; scrollable or paginated if more

### 3. Footer Status Bar
- Left: `COMPILED INDEX: 14,204 ARTICLES` (monospace, small, muted)
- Right: `SYSTEM STATE: SUBSCRIBED` (monospace, small, muted)
- Anchored to bottom of viewport

### 4. Ingest Button (top-right corner)
- `+ INGEST` button, top-right
- Monospace, bordered, no fill
- Opens ingest modal/page

### 5. Logo (top-left)
- Small decorative element: 4 colored dots in a diamond/grid pattern (orange, blue, purple, and a fourth accent)
- Minimal, not a full wordmark — just a visual anchor

---

## Article View

When a user clicks a topic card or gets a search result:

```
┌─────────────────────────────────────────────────────────┐
│  ← Back                                    + INGEST     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  TOPIC // #1 · ACTIVE                                   │
│                                                         │
│  # Neural Architecture                                  │
│  Compiled from 23 sources · Last updated 2h ago         │
│                                                         │
│  [beautifully rendered markdown article content]        │
│  ...                                                    │
│  ...                                                    │
│                                                         │
│  ## Sources                                             │
│  [1] Attention Is All You Need — arxiv.org              │
│  [2] Karpathy blog post — karpathy.ai                  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  RELATED TOPICS                                         │
│  [[Systems Design]] · [[Epistemology]]                  │
├─────────────────────────────────────────────────────────┤
│  Ask about this topic...                    ENTER       │
└─────────────────────────────────────────────────────────┘
```

- Article fills the main content area, max-width ~720px centered
- Metadata line in monospace (source count, last compiled)
- Related topics as clickable wikilinks at the bottom
- Inline ask bar pinned to bottom — scoped to this topic

---

## Q&A Result View

After asking a question (from home or article view):

```
┌─────────────────────────────────────────────────────────┐
│  ← Back                                                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Q: What are the key differences between                │
│     attention mechanisms?                               │
│                                                         │
│  ─────────────────────────────────────────              │
│                                                         │
│  [synthesized answer with inline citations]             │
│  ...references [[Neural Architecture]][1]...            │
│  ...as described in [[Systems Design]][2]...            │
│                                                         │
│  SOURCES CITED                                          │
│  [1] Neural Architecture → Section 3                    │
│  [2] Systems Design → Overview                          │
│                                                         │
│  ─────────────────────────────────────────              │
│                                                         │
│  CONFIDENCE: HIGH · 2 articles referenced               │
│                                                         │
│  [Research this further →]                              │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  Ask a follow-up...                         ENTER       │
└─────────────────────────────────────────────────────────┘
```

- Question displayed at top
- Answer is the hero content — clean prose with inline citations
- Citations link to specific articles/sections in the KB
- Confidence indicator (based on source count + relevance scores)
- "Research this further" button → triggers Exa search + ingest
- Follow-up input at bottom

---

## Ingest Modal

Triggered by `+ INGEST` button:

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  INGEST NEW KNOWLEDGE                                   │
│                                                         │
│  ┌─────────────────────────────────────────────┐        │
│  │  Paste a URL or drop files here...          │        │
│  └─────────────────────────────────────────────┘        │
│                                                         │
│  Or: [Browse files]  [Paste text]  [Research topic]     │
│                                                         │
│  ─────────────────────────────────────────              │
│                                                         │
│  RECENT INGESTION                                       │
│  ✓ arxiv.org/abs/2401... → Neural Architecture  (2m)   │
│  ✓ karpathy.ai/blog...  → Neural Architecture  (5m)   │
│  ◌ processing: paper.pdf → compiling...                 │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

- Single input: URL paste or file drop (auto-detects)
- Secondary actions as text links below
- Live feed of recent ingestions with status + which article they compiled into
- Modal overlay — dismiss to return to home

---

## Research View

From "Research topic" in ingest modal or "Research this further" in Q&A:

```
┌─────────────────────────────────────────────────────────┐
│  ← Back                                                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  RESEARCH: transformer architecture advances            │
│                                                         │
│  Found 12 sources via Exa                               │
│                                                         │
│  ☑ "Attention Is All You Need Revisited"                │
│    arxiv.org · 2025 · relevance: 0.94                   │
│                                                         │
│  ☑ "The Evolution of Transformer Models"                │
│    blog.research.com · 2025 · relevance: 0.91           │
│                                                         │
│  ☐ "Intro to Neural Networks" (basic)                   │
│    medium.com · 2024 · relevance: 0.67                  │
│                                                         │
│  [Ingest Selected (8)]                                  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

- Results with checkboxes (high-relevance pre-selected)
- Source metadata: domain, date, relevance score
- Bulk ingest button with count
- After ingestion: redirects to home with toast "Compiled into X articles"

---

## Responsive Behavior

- **Desktop (>1024px):** Full layout as described
- **Tablet (768-1024px):** Topic cards stack to 2 columns, article max-width fills
- **Mobile (<768px):** Topic cards stack vertically, search bar full-width, ingest is full-screen sheet instead of modal

---

## Interaction Patterns

| Action | Behavior |
|--------|----------|
| Type in search bar + Enter | Triggers Q&A → shows answer view |
| Click topic card | Opens article view |
| `+ INGEST` | Opens ingest modal |
| Click `[[wikilink]]` | Navigates to that article |
| Click citation `[1]` | Scrolls to/opens source article |
| "Research this further" | Opens research view pre-filled with topic |
| `Cmd+K` / `Ctrl+K` | Focus search bar from anywhere |

---

## Implementation Notes

- **Framework:** React (Next.js) or plain HTML + HTMX for simplicity
- **Markdown rendering:** `react-markdown` or `marked` with syntax highlighting
- **Fonts:** Load Inter + JetBrains Mono from Google Fonts (or self-host)
- **No component library** — custom CSS for the minimal aesthetic. Tailwind optional.
- **API:** All views fetch from FastAPI backend (`/ask`, `/search`, `/articles`, `/ingest`, `/research`)
