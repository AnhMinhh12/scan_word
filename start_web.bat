@echo off
chcp 65001 > nul
title CONVEYOR VISION - WEB HMI SERVER
echo ================================================================
echo   HỆ THỐNG KIỂM TRA OCR CAMERA BASLER GIGE - GIAO DIỆN WEB
echo   Camera IP: 192.168.3.3
echo   Server Web: http://localhost:8000
echo ================================================================
echo.
python web_server.py
pause
