#!/bin/bash
# backend/docker-entrypoint.sh
# =============================================================
# Docker entrypoint cho ZaloAssistant Backend
#
# Workflow:
# 1. Kiểm tra nếu knowledge indexes chưa tồn tại → auto rebuild
# 2. Chạy main application
#
# Rebuild manual (trong container):
#   python -m app.mcp.knowledge.rebuild
# =============================================================

set -e

INDEXED_DIR="/app/app/mcp/knowledge/indexed"
EXTRACTED_DIR="/app/app/mcp/knowledge/extracted"

# -----------------------------------------------------------
# Auto-rebuild knowledge indexes nếu chưa có
# -----------------------------------------------------------
if [ ! -f "$EXTRACTED_DIR/entities.json" ] || [ ! -d "$INDEXED_DIR" ] || [ -z "$(ls -A $INDEXED_DIR 2>/dev/null)" ]; then
    echo "=================================================="
    echo " Knowledge indexes not found. Running rebuild..."
    echo "=================================================="

    if [ -n "$GOOGLE_API_KEY" ]; then
        echo "Starting knowledge rebuild in background..."
        python -m app.mcp.knowledge.rebuild --no-langextract >> /var/log/knowledge_rebuild.log 2>&1 &
    else
        echo "WARNING: GOOGLE_API_KEY not set. Skipping knowledge rebuild."
        echo "         System will start in legacy mode."
    fi

    echo "=================================================="
    echo ""
fi

# -----------------------------------------------------------
# Chạy application
# -----------------------------------------------------------
exec "$@"
