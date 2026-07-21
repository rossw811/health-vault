@echo off
cd /d "C:\Users\RossW\Projects\Health"
"C:\Users\RossW\.local\bin\claude.exe" -p "/youtube-queue" --dangerously-skip-permissions >> "C:\Users\RossW\Projects\Health\Logs\youtube-queue-task.log" 2>&1
