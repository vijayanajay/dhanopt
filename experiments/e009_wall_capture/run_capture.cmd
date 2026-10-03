@echo off
REM e009 live chain capture — launched by Task Scheduler.
REM
REM The cd is load-bearing, not decoration: schtasks starts the action with
REM C:\Windows\System32 as its working directory, and `python -m
REM experiments.e009_wall_capture.watchdog` only resolves from the repo root.
REM This task runs the WATCHDOG, not capture_chains: the watchdog re-launches
REM the collector if the process dies, which is the whole point (a session
REM truncated by one crash fails kill 1 on coverage and is lost).
cd /d D:\Code\dhanopt
"D:\Code\dhanopt\.venv\Scripts\python.exe" -m experiments.e009_wall_capture.watchdog >> "D:\Code\dhanopt\experiments\e009_wall_capture\capture.log" 2>&1
