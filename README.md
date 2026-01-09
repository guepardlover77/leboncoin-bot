# Bot Leboncoin - Surveillance de Voitures

Bot Telegram qui surveille automatiquement les annonces de voitures sur Leboncoin selon des critères précis et envoie des notifications avec un système de scoring intelligent.

## Fonctionnalités

- Surveillance automatique toutes les 30 minutes (configurable)
- Filtrage intelligent par marque, modèle, prix, kilométrage, année
- Exclusions spécifiques par modèle (moteurs problématiques, transmissions, etc.)
- Système de scoring pour prioriser les meilleures annonces
- Notifications Telegram avec 3 niveaux de priorité
- Base de données SQLite pour l'historique
- Commandes Telegram pour contrôler le bot
- Logs avec rotation automatique
- Gestion propre des signaux d'arrêt (SIGINT/SIGTERM)

## Prérequis

- Python 3.8 ou supérieur
- Un compte Telegram
- Un bot Telegram (créé via @BotFather)

## Installation

### 1. Cloner le projet

```bash
git clone <url-du-repo>
cd leboncoin-bot
```

### 2. Créer un environnement virtuel

```bash
# Linux/macOS
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Configuration

#### Créer le bot Telegram

1. Ouvrez Telegram et cherchez `@BotFather`
2. Envoyez `/newbot` et suivez les instructions
3. Notez le **token** fourni (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

#### Obtenir votre Chat ID

1. Cherchez `@userinfobot` sur Telegram
2. Envoyez `/start`
3. Notez votre **ID** (nombre comme `123456789`)

#### Configurer les variables d'environnement

```bash
cp .env.example .env
```

Éditez `.env` avec vos valeurs :

```env
TELEGRAM_BOT_TOKEN=votre_token_ici
TELEGRAM_CHAT_ID=votre_chat_id_ici
LOG_LEVEL=INFO
```

### 5. Personnaliser les critères (optionnel)

Éditez `config/criteria.yaml` pour modifier :
- Prix maximum, kilométrage max, année minimum
- Modèles à surveiller et leurs priorités
- Intervalles de vérification
- Seuils de scoring

Éditez `config/exclusions.yaml` pour modifier :
- Moteurs à exclure par marque
- Mots-clés blacklist
- Mots-clés positifs (bonus scoring)

## Lancement

### Lancement direct

```bash
# Depuis la racine du projet
python -m src.main
```

### Avec le module

```bash
cd leboncoin-bot
python -m src.main
```

## Commandes Telegram

| Commande | Description |
|----------|-------------|
| `/start` | Démarrer la surveillance |
| `/stop` | Arrêter la surveillance |
| `/status` | Afficher le statut et les statistiques |
| `/last` | Voir les 5 dernières annonces |
| `/stats` | Statistiques par modèle |
| `/sethighscore X` | Modifier le seuil de haute priorité |
| `/criteria` | Afficher les critères actuels |
| `/help` | Aide |

## Système de Scoring

### Bonus (points positifs)

| Critère | Points |
|---------|--------|
| Mazda 2 essence/chaîne | +10 |
| Honda Jazz manuelle | +10 |
| Suzuki Swift 3 post-2010 | +10 |
| Seat Ibiza atmosphérique | +5 |
| Toyota Yaris | +5 |
| Entretien suivi mentionné | +3 |
| Distribution faite | +3 |
| Moteur chaîne | +3 |
| Prix < 2500€ | +2 |
| Km < 100 000 | +2 |

### Malus (points négatifs)

| Critère | Points |
|---------|--------|
| Diesel | -5 |
| Mot-clé suspect | -10 |

### Niveaux de priorité

- **HAUTE** (score > 15) : Notification avec son
- **MOYENNE** (score 10-15) : Notification standard
- **BASSE** (score < 10) : Notification silencieuse

## Exclusions Automatiques

### Par marque

| Marque | Exclusions |
|--------|------------|
| Peugeot/Citroën | 1.4 VTi, 1.6 VTi (chaîne distribution) |
| Renault | 1.2 TCe (fiabilité) |
| Honda | CVT, i-Shift, automatique (actionneurs) |
| Suzuki | 1.3 DDiS, années 2005-2009 |
| Seat | 1.2 TSI, 1.4 TSI, diesels TDI |
| Mazda | MZ-CD diesel (moteurs PSA) |

### Mots-clés blacklist

- panne, HS, pour pièces, accidenté
- boîte HS, embrayage à refaire
- CVT, robotisée
- vendu en l'état, sans garantie

## Déploiement Production (Linux)

### Service systemd

Créez le fichier `/etc/systemd/system/leboncoin-bot.service` :

```ini
[Unit]
Description=Bot Leboncoin Telegram
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/leboncoin-bot
Environment=PATH=/home/pi/leboncoin-bot/venv/bin
ExecStart=/home/pi/leboncoin-bot/venv/bin/python -m src.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Activer et démarrer :

```bash
sudo systemctl daemon-reload
sudo systemctl enable leboncoin-bot
sudo systemctl start leboncoin-bot
```

Voir les logs :

```bash
sudo journalctl -u leboncoin-bot -f
```

## Architecture du Code

```
leboncoin-bot/
├── config/
│   ├── criteria.yaml      # Critères de recherche
│   └── exclusions.yaml    # Listes d'exclusions
├── src/
│   ├── __init__.py
│   ├── main.py            # Point d'entrée, orchestration
│   ├── scraper.py         # Scraping Leboncoin
│   ├── filters.py         # Filtrage et scoring
│   ├── telegram_bot.py    # Bot et commandes Telegram
│   └── database.py        # Gestion SQLite
├── data/
│   └── cars.db            # Base de données (généré)
├── logs/
│   └── bot.log            # Logs avec rotation
├── requirements.txt
├── .env.example
└── README.md
```

## Troubleshooting

### Le bot ne répond pas aux commandes

1. Vérifiez que le token est correct dans `.env`
2. Vérifiez que vous avez envoyé un message au bot une première fois
3. Consultez les logs : `tail -f logs/bot.log`

### Erreur "TELEGRAM_BOT_TOKEN non défini"

1. Assurez-vous que `.env` existe (copié depuis `.env.example`)
2. Vérifiez que le token est bien renseigné sans espaces

### Pas de nouvelles annonces trouvées

1. Vérifiez les critères dans `criteria.yaml` (prix/km/année)
2. Élargissez les critères temporairement pour tester
3. Activez le niveau DEBUG dans les logs

### Erreur 403 sur Leboncoin

Le site peut bloquer les requêtes trop fréquentes :
1. Augmentez `request_delay_min` et `request_delay_max` dans `criteria.yaml`
2. Le bot utilise un backoff exponentiel automatique

### Base de données corrompue

```bash
rm data/cars.db
# La base sera recréée au prochain démarrage
```

## Notes Techniques Scraping

- **Respect du site** : Délai de 5-10s entre chaque requête
- **User-Agent** : Rotation de User-Agents réalistes
- **Rate limiting** : Backoff exponentiel en cas de 429
- **Parsing** : Utilise le JSON embarqué dans les pages (plus fiable que le HTML)
- **Robustesse** : Retry automatique sur erreurs réseau

## Licence

Ce projet est fourni tel quel pour un usage personnel. L'utilisation du scraping doit respecter les conditions d'utilisation de Leboncoin.

## Support

Pour signaler un bug ou suggérer une amélioration, ouvrez une issue sur le dépôt.
