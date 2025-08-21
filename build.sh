#!/usr/bin/env bash
# exit on error
set -o errexit
pip install --upgrade pip
pip install -r requirements.txt

# Executa o script para criar o banco de dados se ele não existir
if [ ! -f instance/chamados.db ]; then
  echo "Criando o banco de dados..."
  python database.py
else
  echo "Banco de dados já existe."
fi
