@echo off
cd /d "C:\Users\RossW\Projects\Health"
"C:\Users\RossW\.local\bin\claude.exe" -p "/oura-sync" --dangerously-skip-permissions >> "C:\Users\RossW\Projects\Health\Logs\oura-sync-task.log" 2>&1
