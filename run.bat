@echo off
chcp 65001 >nul
title Wuwa Tappo Auto Claim - github.com/Triet2804Dev
cd /d "%~dp0"
python auto_claim.py
if errorlevel 1 pause

