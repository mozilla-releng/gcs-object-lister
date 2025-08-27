#!/bin/bash

# Simple development script that rebuilds on file changes
# Requires fswatch (brew install fswatch on macOS)

echo "Starting development watch mode..."
echo "Watching for changes in app/ and static/ directories..."

# Initial build
docker compose build && docker compose up -d

# Watch for changes and rebuild
fswatch -o app/ static/ requirements.txt Dockerfile | while read f
do
    echo "Files changed, rebuilding..."
    docker compose build && docker compose up -d
    echo "Rebuild complete!"
done