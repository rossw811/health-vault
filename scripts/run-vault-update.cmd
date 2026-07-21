@echo off
cd /d "C:\Users\RossW\Projects\Health"
"C:\Users\RossW\.local\bin\claude.exe" -p "/vault-update" --dangerously-skip-permissions >> "C:\Users\RossW\Projects\Health\Logs\vault-update-task.log" 2>&1
