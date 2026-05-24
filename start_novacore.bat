@echo off

echo =====================================
echo        STARTING NOVACORE AI
echo =====================================

echo Starting Ollama Server...
start cmd /k "ollama serve"

timeout /t 5

echo Starting NovaCore AI...
start cmd /k "python -m streamlit run app.py"

timeout /t 8

start http://localhost:8501

exit