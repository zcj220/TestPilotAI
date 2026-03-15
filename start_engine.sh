#!/bin/zsh
export PATH="/Users/zcj/.local/bin:$PATH"
cd /Users/zcj/Desktop/Projects/TestPilotAi
poetry run python main.py >> /tmp/engine.log 2>&1
