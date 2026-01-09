"""
Point d'entrée principal du bot Leboncoin.
Orchestre le scraping, le filtrage et les notifications Telegram.
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

from .database import Database
from .filters import CarFilter
from .scraper import LeboncoinScraper
from .telegram_bot import TelegramBot

# Charger les variables d'environnement
load_dotenv()


def setup_logging(log_dir: str = "logs", log_level: str = "INFO") -> logging.Logger:
    """
    Configure le système de logging avec rotation.

    Args:
        log_dir: Dossier pour les fichiers de log
        log_level: Niveau de log (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Logger configuré
    """
    # Créer le dossier de logs
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # Configurer le logger racine
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Format des logs
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Handler fichier avec rotation (5 fichiers de 5 MB max)
    file_handler = RotatingFileHandler(
        f"{log_dir}/bot.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    # Handler console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.addHandler(console_handler)

    # Réduire le bruit des librairies tierces
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    return logger


class LeboncoinBot:
    """Classe principale orchestrant le bot."""

    def __init__(
        self,
        config_dir: str = "config",
        data_dir: str = "data",
        log_dir: str = "logs",
    ):
        """
        Initialise le bot.

        Args:
            config_dir: Dossier de configuration
            data_dir: Dossier des données
            log_dir: Dossier des logs
        """
        self.config_dir = config_dir
        self.data_dir = data_dir
        self.log_dir = log_dir

        # Setup logging
        self.logger = setup_logging(log_dir)
        self.logger.info("Initialisation du bot Leboncoin...")

        # Charger la configuration
        self.config = self._load_config()

        # Vérifier les variables d'environnement requises
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not self.telegram_token:
            raise ValueError("TELEGRAM_BOT_TOKEN non défini dans les variables d'environnement")
        if not self.telegram_chat_id:
            raise ValueError("TELEGRAM_CHAT_ID non défini dans les variables d'environnement")

        # Initialiser les composants
        self.database = Database(f"{data_dir}/cars.db")
        self.car_filter = CarFilter(config_dir)
        self.scraper: Optional[LeboncoinScraper] = None
        self.telegram_bot: Optional[TelegramBot] = None

        # État
        self._running = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

        self.logger.info("Bot initialisé avec succès")

    def _load_config(self) -> dict:
        """Charge la configuration générale."""
        config_path = Path(self.config_dir) / "criteria.yaml"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            self.logger.warning(f"Fichier de configuration non trouvé: {config_path}")
            return {}

    async def _init_components(self) -> None:
        """Initialise les composants asynchrones."""
        # Scraper
        general_config = self.config.get("general", {})
        self.scraper = LeboncoinScraper(
            delay_min=general_config.get("request_delay_min", 5),
            delay_max=general_config.get("request_delay_max", 10),
        )

        # Bot Telegram
        self.telegram_bot = TelegramBot(
            token=self.telegram_token,
            chat_id=self.telegram_chat_id,
            database=self.database,
            car_filter=self.car_filter,
        )

        # Callbacks pour start/stop
        self.telegram_bot.set_callbacks(
            on_start=self._on_monitoring_start,
            on_stop=self._on_monitoring_stop,
        )

        await self.telegram_bot.initialize()

        # Charger le seuil depuis la DB si défini
        saved_threshold = self.database.get_config("high_threshold")
        if saved_threshold:
            self.car_filter.set_high_threshold(int(saved_threshold))

        # Restaurer l'état de monitoring
        monitoring_state = self.database.get_config("monitoring")
        if monitoring_state == "true":
            self.telegram_bot._is_monitoring = True

    async def _on_monitoring_start(self) -> None:
        """Callback quand la surveillance démarre."""
        if self._monitoring_task is None or self._monitoring_task.done():
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
            self.logger.info("Tâche de surveillance créée")

    async def _on_monitoring_stop(self) -> None:
        """Callback quand la surveillance s'arrête."""
        self.logger.info("Surveillance mise en pause")
        # La boucle continue mais ne fait rien si is_monitoring est False

    def _search_all_models(self) -> list:
        """Recherche toutes les voitures pour tous les modèles configurés."""
        all_listings = []
        models = self.car_filter.get_model_configs()
        general = self.config.get("general", {})

        for model_config in models:
            try:
                brand = model_config.get("brand", "")
                model = model_config.get("model", "")

                if not brand:
                    continue

                self.logger.info(f"Recherche: {model_config.get('name', brand)}")

                listings = self.scraper.search_cars(
                    brand=brand,
                    model=model,
                    max_price=general.get("max_price", 3000),
                    max_km=general.get("max_km", 150000),
                    min_year=model_config.get("year_min", general.get("min_year", 2008)),
                    fuel=general.get("fuel", "essence"),
                    gearbox=general.get("gearbox", "manuelle"),
                )

                all_listings.extend(listings)

            except Exception as e:
                self.logger.error(f"Erreur recherche {model_config.get('name', '?')}: {e}")

        return all_listings

    async def _process_listings(self, listings: list) -> int:
        """
        Traite les annonces trouvées: filtrage, scoring, stockage et notification.

        Args:
            listings: Liste des annonces brutes

        Returns:
            Nombre de nouvelles annonces notifiées
        """
        new_count = 0

        for listing in listings:
            try:
                # Vérifier si déjà en base
                if self.database.listing_exists(listing.listing_id):
                    continue

                # Évaluer l'annonce
                score_result = self.car_filter.evaluate(
                    listing_id=listing.listing_id,
                    title=listing.title,
                    description=listing.description or "",
                    price=listing.price,
                    mileage=listing.mileage,
                    year=listing.year,
                    fuel=listing.fuel,
                    gearbox=listing.gearbox,
                    brand=listing.brand,
                    model=listing.model,
                    engine=listing.engine,
                )

                # Préparer les données pour la DB
                db_data = listing.to_dict()
                db_data["score"] = score_result.total_score
                db_data["priority"] = score_result.priority
                db_data["score_details"] = score_result.to_json()
                db_data["excluded"] = score_result.excluded
                db_data["exclusion_reason"] = score_result.exclusion_reason

                # Sauvegarder en base
                db_listing = self.database.add_listing(db_data)

                if not db_listing:
                    continue

                # Si exclue, pas de notification
                if score_result.excluded:
                    self.logger.debug(
                        f"Annonce exclue: {listing.title} - {score_result.exclusion_reason}"
                    )
                    continue

                # Envoyer la notification
                if await self.telegram_bot.send_notification(db_listing, score_result):
                    self.database.mark_as_notified(listing.listing_id)
                    new_count += 1

            except Exception as e:
                self.logger.error(f"Erreur traitement annonce {listing.listing_id}: {e}")

        return new_count

    async def _monitoring_loop(self) -> None:
        """Boucle principale de surveillance."""
        general = self.config.get("general", {})
        check_interval = general.get("check_interval_minutes", 30) * 60  # En secondes

        self.logger.info(f"Boucle de surveillance démarrée (intervalle: {check_interval}s)")

        while self._running:
            try:
                # Vérifier si la surveillance est active
                if not self.telegram_bot.is_monitoring():
                    await asyncio.sleep(10)  # Attendre 10s avant de revérifier
                    continue

                self.logger.info("Début du cycle de recherche...")
                start_time = datetime.now()

                # Rechercher les annonces
                listings = await asyncio.to_thread(self._search_all_models)
                self.logger.info(f"Total annonces trouvées: {len(listings)}")

                # Traiter les annonces
                new_count = await self._process_listings(listings)

                # Nettoyage périodique (annonces > 30 jours)
                self.database.cleanup_old_listings(30)

                elapsed = (datetime.now() - start_time).total_seconds()
                self.logger.info(
                    f"Cycle terminé en {elapsed:.1f}s - "
                    f"{new_count} nouvelles annonces notifiées"
                )

                # Attendre jusqu'au prochain cycle
                wait_time = max(0, check_interval - elapsed)
                self.logger.debug(f"Prochain cycle dans {wait_time:.0f}s")

                # Utiliser wait_for pour pouvoir être interrompu
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=wait_time
                    )
                    # Si on arrive ici, shutdown demandé
                    break
                except asyncio.TimeoutError:
                    # Timeout normal, continuer la boucle
                    pass

            except asyncio.CancelledError:
                self.logger.info("Boucle de surveillance annulée")
                break
            except Exception as e:
                self.logger.error(f"Erreur dans la boucle de surveillance: {e}")
                await asyncio.sleep(60)  # Attendre 1 min avant de réessayer

        self.logger.info("Boucle de surveillance terminée")

    async def run(self) -> None:
        """Lance le bot."""
        self._running = True

        try:
            # Initialiser les composants
            await self._init_components()

            # Démarrer le bot Telegram
            await self.telegram_bot.start()

            # Message de démarrage
            await self.telegram_bot.send_startup_message()

            # Démarrer la surveillance si elle était active
            if self.telegram_bot.is_monitoring():
                self._monitoring_task = asyncio.create_task(self._monitoring_loop())

            # Attendre le signal d'arrêt
            await self._shutdown_event.wait()

        except Exception as e:
            self.logger.error(f"Erreur fatale: {e}")
            raise
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        """Nettoie les ressources avant l'arrêt."""
        self.logger.info("Nettoyage en cours...")

        # Arrêter la boucle de surveillance
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        # Fermer le scraper
        if self.scraper:
            self.scraper.close()

        # Envoyer message d'arrêt et fermer le bot Telegram
        if self.telegram_bot:
            try:
                await self.telegram_bot.send_shutdown_message()
            except Exception:
                pass
            await self.telegram_bot.stop()

        self.logger.info("Nettoyage terminé")

    def shutdown(self) -> None:
        """Demande l'arrêt propre du bot."""
        self.logger.info("Arrêt demandé...")
        self._running = False
        self._shutdown_event.set()


def main() -> None:
    """Point d'entrée principal."""
    # Déterminer le dossier de base (racine du projet)
    base_dir = Path(__file__).parent.parent

    # Créer l'instance du bot
    bot = LeboncoinBot(
        config_dir=str(base_dir / "config"),
        data_dir=str(base_dir / "data"),
        log_dir=str(base_dir / "logs"),
    )

    # Gérer les signaux d'arrêt
    def signal_handler(signum, frame):
        print(f"\nSignal {signum} reçu, arrêt en cours...")
        bot.shutdown()

    # Enregistrer les handlers de signaux
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Windows: SIGBREAK
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal_handler)

    # Lancer le bot
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\nInterruption clavier, arrêt...")
    except Exception as e:
        logging.error(f"Erreur fatale non gérée: {e}")
        sys.exit(1)

    print("Bot arrêté proprement.")


if __name__ == "__main__":
    main()
