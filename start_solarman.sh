#!/bin/bash

# Diretório onde o script será executado
cd /home/usuario/scrape-solarman/

# Nome do ambiente virtual
VENV_DIR="venv"

# Verifica se o ambiente virtual existe, se não, cria-o
if [ ! -d "$VENV_DIR" ]; then
    echo "Ambiente virtual não encontrado. Criando ambiente virtual..."
    python3.11 -m venv "$VENV_DIR"
    echo "Ambiente virtual criado com sucesso."
fi

# Ativa o ambiente virtual
source "$VENV_DIR/bin/activate"

# Verifica e instala as dependências necessárias
REQUIRED_PACKAGES=(
    "requests==2.32.2"
    "retry==0.9.2"
    "pyyaml==6.0"
    "influxdb-client==1.36.1"
    "hyundai_kia_connect_api==3.10.5"
    "cachetools==5.3.0"
)

for PACKAGE in "${REQUIRED_PACKAGES[@]}"; do
    pip show ${PACKAGE%%==*} &> /dev/null
    if [ $? -ne 0 ]; then
        echo "Pacote $PACKAGE não encontrado. Instalando..."
        pip install "$PACKAGE"
    else
        echo "Pacote $PACKAGE já está instalado."
    fi
done

# Executa o comando em segundo plano
python3 solarman_api.py &

# Notificação de conclusão da execução
echo "Script iniciado em segundo plano. O log não está sendo salvo."
