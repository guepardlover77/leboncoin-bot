#!/bin/bash
#
# Script d'installation du Bot Leboncoin
# Compatible avec Raspberry Pi OS, Ubuntu, Debian
#
# Usage: chmod +x install.sh && ./install.sh
#

set -e

# Couleurs pour les messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Installation du Bot Leboncoin${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# Vérifier que Python 3.8+ est installé
echo -e "${YELLOW}Vérification de Python...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 n'est pas installé. Installation...${NC}"
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip python3-venv
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}Python $PYTHON_VERSION détecté${NC}"

# Vérifier la version minimale
MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 8 ]); then
    echo -e "${RED}Python 3.8 ou supérieur est requis. Version actuelle: $PYTHON_VERSION${NC}"
    exit 1
fi

# Créer l'environnement virtuel
echo
echo -e "${YELLOW}Création de l'environnement virtuel...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}Environnement virtuel créé${NC}"
else
    echo -e "${GREEN}Environnement virtuel existe déjà${NC}"
fi

# Activer l'environnement virtuel
source venv/bin/activate

# Installer les dépendances
echo
echo -e "${YELLOW}Installation des dépendances Python...${NC}"
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}Dépendances installées${NC}"

# Créer les dossiers nécessaires
echo
echo -e "${YELLOW}Création des dossiers...${NC}"
mkdir -p data logs
echo -e "${GREEN}Dossiers créés${NC}"

# Configurer le fichier .env
echo
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Configuration du fichier .env...${NC}"
    cp .env.example .env

    echo
    echo -e "${YELLOW}Veuillez entrer votre token Telegram (obtenu via @BotFather):${NC}"
    read -r TELEGRAM_TOKEN

    echo -e "${YELLOW}Veuillez entrer votre Chat ID Telegram (obtenu via @userinfobot):${NC}"
    read -r TELEGRAM_CHAT_ID

    # Remplacer les valeurs dans .env
    sed -i "s/your_bot_token_here/$TELEGRAM_TOKEN/" .env
    sed -i "s/your_chat_id_here/$TELEGRAM_CHAT_ID/" .env

    echo -e "${GREEN}Fichier .env configuré${NC}"
else
    echo -e "${GREEN}Fichier .env existe déjà${NC}"
fi

# Proposer l'installation du service systemd
echo
echo -e "${YELLOW}Voulez-vous installer le service systemd pour un démarrage automatique? (o/n)${NC}"
read -r INSTALL_SERVICE

if [ "$INSTALL_SERVICE" = "o" ] || [ "$INSTALL_SERVICE" = "O" ]; then
    echo -e "${YELLOW}Installation du service systemd...${NC}"

    # Obtenir le chemin absolu
    INSTALL_PATH=$(pwd)
    CURRENT_USER=$(whoami)

    # Créer une copie du service avec les bons chemins
    cp leboncoin-bot.service leboncoin-bot.service.tmp
    sed -i "s|/home/pi/leboncoin-bot|$INSTALL_PATH|g" leboncoin-bot.service.tmp
    sed -i "s|User=pi|User=$CURRENT_USER|g" leboncoin-bot.service.tmp
    sed -i "s|Group=pi|Group=$CURRENT_USER|g" leboncoin-bot.service.tmp

    # Installer le service
    sudo cp leboncoin-bot.service.tmp /etc/systemd/system/leboncoin-bot.service
    rm leboncoin-bot.service.tmp

    sudo systemctl daemon-reload
    sudo systemctl enable leboncoin-bot

    echo -e "${GREEN}Service systemd installé et activé${NC}"
    echo
    echo -e "${YELLOW}Pour démarrer le bot:${NC}"
    echo "  sudo systemctl start leboncoin-bot"
    echo
    echo -e "${YELLOW}Pour voir les logs:${NC}"
    echo "  sudo journalctl -u leboncoin-bot -f"
else
    echo
    echo -e "${YELLOW}Pour lancer le bot manuellement:${NC}"
    echo "  source venv/bin/activate"
    echo "  python -m src.main"
fi

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Installation terminée !${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "${YELLOW}Prochaines étapes:${NC}"
echo "1. Vérifiez la configuration dans config/criteria.yaml"
echo "2. Ajustez les exclusions dans config/exclusions.yaml"
echo "3. Lancez le bot et envoyez /start via Telegram"
echo
