@echo off
cd /d "C:\Users\analistadados02\Desktop\ia_python"

echo === Step 1: git init ===
git init
if errorlevel 1 goto error1
echo.

echo === Step 2: git remote add origin ===
git remote add origin https://github.com/RaulRMO10/AGENTE_IA.git
if errorlevel 1 goto error2
echo.

echo === Step 3: git add . ===
git add .
if errorlevel 1 goto error3
echo.

echo === Step 4: git commit ===
git commit -m "Initial commit — BI Copilot agent%newline%Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
if errorlevel 1 goto error4
echo.

echo === Step 5: git branch -M main ===
git branch -M main
if errorlevel 1 goto error5
echo.

echo === Step 6: git push -u origin main ===
git push -u origin main
if errorlevel 1 goto error6
echo.

echo All operations completed successfully!
exit /b 0

:error1
echo Error at Step 1 (git init)
exit /b 1

:error2
echo Error at Step 2 (git remote add)
exit /b 1

:error3
echo Error at Step 3 (git add)
exit /b 1

:error4
echo Error at Step 4 (git commit)
exit /b 1

:error5
echo Error at Step 5 (git branch -M main)
exit /b 1

:error6
echo Error at Step 6 (git push)
exit /b 1
