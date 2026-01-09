"""
Module de gestion du bot Telegram.
Gère les commandes, les notifications et l'interaction utilisateur.
"""

import asyncio
import logging
from typing import Optional, Callable, Awaitable

from telegram import Update, Bot
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.error import TelegramError

from .database import Database, CarListing
from .filters import CarFilter, ScoreResult

logger = logging.getLogger(__name__)


class TelegramBot:
    """Bot Telegram pour les notifications de voitures."""

    def __init__(
        self,
        token: str,
        chat_id: str,
        database: Database,
        car_filter: CarFilter,
    ):
        """
        Initialise le bot Telegram.

        Args:
            token: Token du bot Telegram
            chat_id: ID du chat pour les notifications
            database: Instance de la base de données
            car_filter: Instance du filtre de voitures
        """
        self.token = token
        self.chat_id = chat_id
        self.database = database
        self.car_filter = car_filter
        self.application: Optional[Application] = None
        self.bot: Optional[Bot] = None
        self._is_monitoring = False
        self._on_start_callback: Optional[Callable[[], Awaitable[None]]] = None
        self._on_stop_callback: Optional[Callable[[], Awaitable[None]]] = None

        logger.info(f"Bot Telegram initialisé pour le chat {chat_id}")

    def set_callbacks(
        self,
        on_start: Optional[Callable[[], Awaitable[None]]] = None,
        on_stop: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> None:
        """Configure les callbacks pour start/stop de la surveillance."""
        self._on_start_callback = on_start
        self._on_stop_callback = on_stop

    async def initialize(self) -> None:
        """Initialise l'application Telegram."""
        self.application = (
            Application.builder()
            .token(self.token)
            .build()
        )
        self.bot = self.application.bot

        # Enregistrer les commandes
        self.application.add_handler(CommandHandler("start", self._cmd_start))
        self.application.add_handler(CommandHandler("stop", self._cmd_stop))
        self.application.add_handler(CommandHandler("status", self._cmd_status))
        self.application.add_handler(CommandHandler("last", self._cmd_last))
        self.application.add_handler(CommandHandler("stats", self._cmd_stats))
        self.application.add_handler(CommandHandler("sethighscore", self._cmd_set_high_score))
        self.application.add_handler(CommandHandler("criteria", self._cmd_criteria))
        self.application.add_handler(CommandHandler("help", self._cmd_help))

        # Handler pour messages inconnus
        self.application.add_handler(
            MessageHandler(filters.COMMAND, self._cmd_unknown)
        )

        await self.application.initialize()
        logger.info("Application Telegram initialisée")

    async def start(self) -> None:
        """Démarre le bot en mode polling."""
        if not self.application:
            await self.initialize()

        await self.application.start()
        await self.application.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot Telegram démarré en mode polling")

    async def stop(self) -> None:
        """Arrête le bot proprement."""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info("Bot Telegram arrêté")

    def is_monitoring(self) -> bool:
        """Retourne l'état de la surveillance."""
        return self._is_monitoring

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Commande /start - Démarre la surveillance."""
        if self._is_monitoring:
            await update.message.reply_text(
                "La surveillance est déjà active."
            )
            return

        self._is_monitoring = True
        self.database.set_config("monitoring", "true")

        if self._on_start_callback:
            await self._on_start_callback()

        await update.message.reply_text(
            "Surveillance démarrée.\n\n"
            "Je vais surveiller les nouvelles annonces et vous notifier "
            "selon les critères configurés.\n\n"
            "Commandes disponibles: /help"
        )
        logger.info("Surveillance démarrée par commande Telegram")

    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Commande /stop - Arrête la surveillance."""
        if not self._is_monitoring:
            await update.message.reply_text(
                "La surveillance n'est pas active."
            )
            return

        self._is_monitoring = False
        self.database.set_config("monitoring", "false")

        if self._on_stop_callback:
            await self._on_stop_callback()

        await update.message.reply_text(
            "Surveillance arrêtée.\n\n"
            "Utilisez /start pour reprendre."
        )
        logger.info("Surveillance arrêtée par commande Telegram")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Commande /status - Affiche le statut et les statistiques."""
        stats = self.database.get_total_stats()

        status_emoji = "" if self._is_monitoring else ""
        status_text = "Active" if self._is_monitoring else "Arrêtée"

        message = (
            f"**Statut du bot**\n\n"
            f"{status_emoji} Surveillance: {status_text}\n\n"
            f"**Statistiques globales:**\n"
            f"- Total annonces: {stats['total']}\n"
            f"- Notifiées: {stats['notified']}\n"
            f"- Exclues: {stats['excluded']}\n"
            f"- Score moyen: {stats['avg_score']}\n"
            f"- Haute priorité: {stats['high_priority']}\n\n"
            f"**Dernières 24h:**\n"
            f"- Nouvelles annonces: {stats['today_count']}"
        )

        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_last(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Commande /last - Affiche les 5 dernières annonces."""
        listings = self.database.get_last_listings(5)

        if not listings:
            await update.message.reply_text("Aucune annonce trouvée.")
            return

        message = "**5 dernières annonces:**\n\n"
        for listing in listings:
            priority_emoji = self._get_priority_emoji(listing.priority)
            message += (
                f"{priority_emoji} **{listing.title}**\n"
                f"   Score: {listing.score} | "
                f"{listing.price}€ | "
                f"{listing.mileage or '?'} km | "
                f"{listing.year or '?'}\n"
                f"   [Voir l'annonce]({listing.url})\n\n"
            )

        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

    async def _cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Commande /stats - Statistiques par modèle."""
        model_stats = self.database.get_stats_by_model()
        daily_stats = self.database.get_daily_stats(7)

        if not model_stats:
            await update.message.reply_text("Pas encore de statistiques disponibles.")
            return

        message = "**Statistiques par modèle:**\n\n"
        for stat in sorted(model_stats, key=lambda x: x["count"], reverse=True):
            message += (
                f"**{stat['brand']} {stat['model']}**\n"
                f"   {stat['count']} annonces | "
                f"Score moy: {stat['avg_score']} | "
                f"Prix moy: {stat['avg_price']:.0f}€\n"
            )

        if daily_stats:
            message += "\n**7 derniers jours:**\n"
            for day in daily_stats[:7]:
                message += f"   {day['date']}: {day['count']} annonces (score moy: {day['avg_score']})\n"

        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_set_high_score(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Commande /sethighscore X - Modifie le seuil de haute priorité."""
        try:
            if not context.args:
                await update.message.reply_text(
                    f"Seuil actuel: {self.car_filter.high_threshold}\n\n"
                    f"Usage: /sethighscore <valeur>"
                )
                return

            new_threshold = int(context.args[0])
            if new_threshold < 0 or new_threshold > 100:
                raise ValueError("Valeur hors limites")

            self.car_filter.set_high_threshold(new_threshold)
            self.database.set_config("high_threshold", str(new_threshold))

            await update.message.reply_text(
                f"Seuil de haute priorité mis à jour: {new_threshold}\n\n"
                f"Les annonces avec un score > {new_threshold} "
                f"déclencheront une notification urgente."
            )

        except (ValueError, IndexError):
            await update.message.reply_text(
                "Valeur invalide. Usage: /sethighscore <nombre entre 0 et 100>"
            )

    async def _cmd_criteria(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Commande /criteria - Affiche les critères de recherche."""
        summary = self.car_filter.get_criteria_summary()
        await update.message.reply_text(summary, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Commande /help - Affiche l'aide."""
        help_text = (
            "**Commandes disponibles:**\n\n"
            "/start - Démarrer la surveillance\n"
            "/stop - Arrêter la surveillance\n"
            "/status - Statut et statistiques globales\n"
            "/last - 5 dernières annonces avec scores\n"
            "/stats - Statistiques par modèle\n"
            "/sethighscore X - Modifier seuil haute priorité\n"
            "/criteria - Afficher critères de recherche\n"
            "/help - Cette aide\n\n"
            "**Niveaux de priorité:**\n"
            " HAUTE - Score > seuil haute priorité\n"
            " MOYENNE - Score intermédiaire\n"
            " BASSE - Score bas (silencieux)"
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler pour les commandes inconnues."""
        await update.message.reply_text(
            "Commande inconnue. Utilisez /help pour la liste des commandes."
        )

    def _get_priority_emoji(self, priority: str) -> str:
        """Retourne l'emoji correspondant à la priorité."""
        return {
            "high": "",
            "medium": "",
            "low": "",
        }.get(priority, "")

    async def send_notification(
        self,
        listing: CarListing,
        score_result: ScoreResult,
    ) -> bool:
        """
        Envoie une notification pour une nouvelle annonce.

        Args:
            listing: L'annonce à notifier
            score_result: Résultat du scoring

        Returns:
            True si la notification a été envoyée
        """
        if not self.bot:
            logger.error("Bot non initialisé")
            return False

        try:
            priority_emoji = self._get_priority_emoji(score_result.priority)

            # Construire le message
            message_parts = [
                f"{priority_emoji} **{score_result.priority.upper()} PRIORITÉ**\n",
                f"Score: **{score_result.total_score}**\n\n",
                f"**{listing.title}**\n\n",
            ]

            # Caractéristiques
            chars = []
            if listing.price:
                chars.append(f"Prix: {listing.price}€")
            if listing.mileage:
                chars.append(f"Km: {listing.mileage:,}".replace(",", " "))
            if listing.year:
                chars.append(f"Année: {listing.year}")
            if listing.fuel:
                chars.append(f"Carburant: {listing.fuel}")
            if listing.gearbox:
                chars.append(f"Boîte: {listing.gearbox}")
            if listing.engine:
                chars.append(f"Moteur: {listing.engine}")
            if listing.location:
                chars.append(f"Lieu: {listing.location}")

            if chars:
                message_parts.append("\n".join(chars) + "\n\n")

            # Points forts (bonuses)
            if score_result.bonuses:
                message_parts.append("**Points forts:**\n")
                for bonus in score_result.bonuses:
                    message_parts.append(f"  {bonus}\n")
                message_parts.append("\n")

            # Warnings
            if score_result.warnings:
                message_parts.append("**Attention:**\n")
                for warning in score_result.warnings:
                    message_parts.append(f"  {warning}\n")
                message_parts.append("\n")

            # Pénalités significatives
            if score_result.penalties:
                message_parts.append("**Points négatifs:**\n")
                for penalty in score_result.penalties:
                    message_parts.append(f"  {penalty}\n")
                message_parts.append("\n")

            # Lien
            message_parts.append(f"[Voir l'annonce]({listing.url})")

            message = "".join(message_parts)

            # Paramètres de notification selon priorité
            disable_notification = score_result.priority == "low"

            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=False,
                disable_notification=disable_notification,
            )

            logger.info(
                f"Notification envoyée: {listing.title} "
                f"(score: {score_result.total_score}, priorité: {score_result.priority})"
            )
            return True

        except TelegramError as e:
            logger.error(f"Erreur envoi notification Telegram: {e}")
            return False

    async def send_message(self, text: str, silent: bool = False) -> bool:
        """
        Envoie un message simple.

        Args:
            text: Texte du message
            silent: Si True, notification silencieuse

        Returns:
            True si envoyé avec succès
        """
        if not self.bot:
            logger.error("Bot non initialisé")
            return False

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                disable_notification=silent,
            )
            return True
        except TelegramError as e:
            logger.error(f"Erreur envoi message Telegram: {e}")
            return False

    async def send_startup_message(self) -> None:
        """Envoie un message au démarrage du bot."""
        await self.send_message(
            " **Bot Leboncoin démarré**\n\n"
            "Surveillance prête. Utilisez /start pour commencer.",
            silent=True
        )

    async def send_shutdown_message(self) -> None:
        """Envoie un message à l'arrêt du bot."""
        await self.send_message(
            " **Bot Leboncoin arrêté**\n\n"
            "La surveillance est interrompue.",
            silent=True
        )
