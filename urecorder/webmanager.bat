@echo off
:: 显示系统信息（可选）
wmic os get Caption

uv run flask_app.py
pause