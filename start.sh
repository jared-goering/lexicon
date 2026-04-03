#!/usr/bin/env bash
# Lexicon server startup script
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Activate venv
source .venv/bin/activate

# Load API keys
export OPENAI_API_KEY="${OPENAI_API_KEY:-$(cat ~/.lexicon/secrets/openai-api-key.txt 2>/dev/null || echo '')}"
export EXA_API_KEY="${EXA_API_KEY:-$(grep EXA_API_KEY ~/.lexicon/.env 2>/dev/null | cut -d= -f2 || echo '')}"

# Lexicon config
export LEXICON_LLM_MODEL="${LEXICON_LLM_MODEL:-openai/gpt-4o-mini}"
export LEXICON_HOST="${LEXICON_HOST:-127.0.0.1}"
export LEXICON_PORT="${LEXICON_PORT:-8899}"

echo "Starting Lexicon server..."
echo "  Model:  $LEXICON_LLM_MODEL"
echo "  Listen: $LEXICON_HOST:$LEXICON_PORT"
echo "  Exa:    $([ -n "$EXA_API_KEY" ] && echo 'configured' || echo 'MISSING')"
echo "  OpenAI: $([ -n "$OPENAI_API_KEY" ] && echo 'configured' || echo 'MISSING')"

# Embedded SQLite is single-writer; keep one worker to avoid DB lock races.
exec uvicorn lexicon.server:app \
  --host "$LEXICON_HOST" \
  --port "$LEXICON_PORT" \
  --workers 1
