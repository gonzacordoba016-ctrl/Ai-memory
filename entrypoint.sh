#!/bin/bash
set -e
# Fix permissions on Railway-mounted volume (mounted as root after build)
mkdir -p /data/database /data/memory_db
chmod -R 755 /data 2>/dev/null || true
# Start server
exec python run.py serve --no-reload
