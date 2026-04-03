#!/usr/bin/env bash
# UltraKnowledge server startup script
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Activate venv
source .venv/bin/activate

# Load API keys
export OPENAI_API_KEY="${OPENAI_API_KEY:-$(cat ~/.openclaw/secrets/openai-api-key.txt 2>/dev/null || echo '')}"
export EXA_API_KEY="${EXA_API_KEY:-$(grep EXA_API_KEY ~/.openclaw/.env 2>/dev/null | cut -d= -f2 || echo '')}"

# UltraKnowledge config
export UK_LLM_MODEL="${UK_LLM_MODEL:-openai/gpt-4o-mini}"
export UK_HOST="${UK_HOST:-127.0.0.1}"
export UK_PORT="${UK_PORT:-8899}"

echo "Starting UltraKnowledge server..."
echo "  Model:  $UK_LLM_MODEL"
echo "  Listen: $UK_HOST:$UK_PORT"
echo "  Exa:    $([ -n "$EXA_API_KEY" ] && echo 'configured' || echo 'MISSING')"
echo "  OpenAI: $([ -n "$OPENAI_API_KEY" ] && echo 'configured' || echo 'MISSING')"

exec uvicorn ultraknowledge.server:app \
  --host "$UK_HOST" \
  --port "$UK_PORT" \
  --workers 2
