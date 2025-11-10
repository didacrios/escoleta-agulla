#!/bin/bash
# Script wrapper per executar el parser amb el venv activat

# Anar al directori del projecte
cd "$(dirname "$0")"

# Activar el venv
source venv/bin/activate

# Executar el parser amb els arguments passats
python src/pdf_menu_parser.py "$@"

