@echo off
cd /d D:\Obsidian\ai-knowledge-base
if not exist logs mkdir logs
python pipeline\pipeline.py --sources github,rss --limit 20 --verbose >> logs\collect.log 2>&1
