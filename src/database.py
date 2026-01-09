"""
Module de gestion de la base de données SQLite.
Stocke l'historique des annonces, scores et statistiques.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    Boolean,
    create_engine,
    func,
    desc,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

logger = logging.getLogger(__name__)

Base = declarative_base()


class CarListing(Base):
    """Modèle pour une annonce de voiture."""

    __tablename__ = "car_listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    listing_id = Column(String(50), unique=True, nullable=False, index=True)
    url = Column(String(500), nullable=False)
    title = Column(String(300), nullable=False)
    price = Column(Integer, nullable=True)
    mileage = Column(Integer, nullable=True)
    year = Column(Integer, nullable=True)
    fuel = Column(String(50), nullable=True)
    gearbox = Column(String(50), nullable=True)
    brand = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    engine = Column(String(100), nullable=True)
    location = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)

    # Scoring et priorité
    score = Column(Integer, default=0)
    priority = Column(String(20), default="low")  # high, medium, low
    score_details = Column(Text, nullable=True)  # JSON des détails du score

    # Métadonnées
    discovered_at = Column(DateTime, default=datetime.utcnow, index=True)
    notified = Column(Boolean, default=False)
    notified_at = Column(DateTime, nullable=True)

    # Flags de filtrage
    excluded = Column(Boolean, default=False)
    exclusion_reason = Column(String(300), nullable=True)

    def __repr__(self) -> str:
        return f"<CarListing {self.listing_id}: {self.title} - {self.price}€>"


class BotStats(Base):
    """Statistiques journalières du bot."""

    __tablename__ = "bot_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False, index=True)
    listings_found = Column(Integer, default=0)
    listings_notified = Column(Integer, default=0)
    listings_excluded = Column(Integer, default=0)
    avg_score = Column(Float, default=0.0)
    high_priority_count = Column(Integer, default=0)
    medium_priority_count = Column(Integer, default=0)
    low_priority_count = Column(Integer, default=0)


class BotConfig(Base):
    """Configuration persistante du bot."""

    __tablename__ = "bot_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(String(500), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Database:
    """Gestionnaire de base de données."""

    def __init__(self, db_path: str = "data/cars.db"):
        """
        Initialise la connexion à la base de données.

        Args:
            db_path: Chemin vers le fichier SQLite
        """
        # Créer le dossier parent si nécessaire
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        logger.info(f"Base de données initialisée: {db_path}")

    def get_session(self) -> Session:
        """Retourne une nouvelle session de base de données."""
        return self.SessionLocal()

    def listing_exists(self, listing_id: str) -> bool:
        """Vérifie si une annonce existe déjà."""
        with self.get_session() as session:
            return (
                session.query(CarListing)
                .filter(CarListing.listing_id == listing_id)
                .first()
                is not None
            )

    def add_listing(self, listing_data: dict) -> Optional[CarListing]:
        """
        Ajoute une nouvelle annonce à la base de données.

        Args:
            listing_data: Dictionnaire avec les données de l'annonce

        Returns:
            L'objet CarListing créé ou None si déjà existant
        """
        with self.get_session() as session:
            # Vérifier si l'annonce existe déjà
            existing = (
                session.query(CarListing)
                .filter(CarListing.listing_id == listing_data.get("listing_id"))
                .first()
            )
            if existing:
                logger.debug(f"Annonce déjà existante: {listing_data.get('listing_id')}")
                return None

            listing = CarListing(**listing_data)
            session.add(listing)
            session.commit()
            session.refresh(listing)
            logger.info(f"Nouvelle annonce ajoutée: {listing.title} (score: {listing.score})")
            return listing

    def update_listing(self, listing_id: str, **kwargs) -> bool:
        """Met à jour une annonce existante."""
        with self.get_session() as session:
            listing = (
                session.query(CarListing)
                .filter(CarListing.listing_id == listing_id)
                .first()
            )
            if listing:
                for key, value in kwargs.items():
                    if hasattr(listing, key):
                        setattr(listing, key, value)
                session.commit()
                return True
            return False

    def mark_as_notified(self, listing_id: str) -> bool:
        """Marque une annonce comme notifiée."""
        return self.update_listing(
            listing_id, notified=True, notified_at=datetime.utcnow()
        )

    def get_unnotified_listings(self) -> list[CarListing]:
        """Récupère les annonces non encore notifiées, triées par score."""
        with self.get_session() as session:
            listings = (
                session.query(CarListing)
                .filter(CarListing.notified == False)
                .filter(CarListing.excluded == False)
                .order_by(desc(CarListing.score))
                .all()
            )
            # Détacher les objets de la session
            session.expunge_all()
            return listings

    def get_last_listings(self, limit: int = 5) -> list[CarListing]:
        """Récupère les dernières annonces découvertes."""
        with self.get_session() as session:
            listings = (
                session.query(CarListing)
                .filter(CarListing.excluded == False)
                .order_by(desc(CarListing.discovered_at))
                .limit(limit)
                .all()
            )
            session.expunge_all()
            return listings

    def get_stats_by_model(self) -> dict:
        """Retourne les statistiques par modèle."""
        with self.get_session() as session:
            results = (
                session.query(
                    CarListing.brand,
                    CarListing.model,
                    func.count(CarListing.id).label("count"),
                    func.avg(CarListing.score).label("avg_score"),
                    func.avg(CarListing.price).label("avg_price"),
                )
                .filter(CarListing.excluded == False)
                .group_by(CarListing.brand, CarListing.model)
                .all()
            )
            return [
                {
                    "brand": r.brand or "Inconnu",
                    "model": r.model or "Inconnu",
                    "count": r.count,
                    "avg_score": round(r.avg_score or 0, 1),
                    "avg_price": round(r.avg_price or 0, 0),
                }
                for r in results
            ]

    def get_daily_stats(self, days: int = 7) -> list[dict]:
        """Récupère les statistiques des derniers jours."""
        with self.get_session() as session:
            since = datetime.utcnow() - timedelta(days=days)
            results = (
                session.query(
                    func.date(CarListing.discovered_at).label("date"),
                    func.count(CarListing.id).label("count"),
                    func.avg(CarListing.score).label("avg_score"),
                )
                .filter(CarListing.discovered_at >= since)
                .filter(CarListing.excluded == False)
                .group_by(func.date(CarListing.discovered_at))
                .order_by(desc(func.date(CarListing.discovered_at)))
                .all()
            )
            return [
                {
                    "date": str(r.date),
                    "count": r.count,
                    "avg_score": round(r.avg_score or 0, 1),
                }
                for r in results
            ]

    def get_total_stats(self) -> dict:
        """Retourne les statistiques globales."""
        with self.get_session() as session:
            total = session.query(func.count(CarListing.id)).scalar() or 0
            notified = (
                session.query(func.count(CarListing.id))
                .filter(CarListing.notified == True)
                .scalar()
                or 0
            )
            excluded = (
                session.query(func.count(CarListing.id))
                .filter(CarListing.excluded == True)
                .scalar()
                or 0
            )
            avg_score = (
                session.query(func.avg(CarListing.score))
                .filter(CarListing.excluded == False)
                .scalar()
                or 0
            )
            high_priority = (
                session.query(func.count(CarListing.id))
                .filter(CarListing.priority == "high")
                .filter(CarListing.excluded == False)
                .scalar()
                or 0
            )

            # Stats des dernières 24h
            since_24h = datetime.utcnow() - timedelta(hours=24)
            today_count = (
                session.query(func.count(CarListing.id))
                .filter(CarListing.discovered_at >= since_24h)
                .scalar()
                or 0
            )

            return {
                "total": total,
                "notified": notified,
                "excluded": excluded,
                "avg_score": round(avg_score, 1),
                "high_priority": high_priority,
                "today_count": today_count,
            }

    def get_config(self, key: str, default: str = None) -> Optional[str]:
        """Récupère une valeur de configuration."""
        with self.get_session() as session:
            config = (
                session.query(BotConfig).filter(BotConfig.key == key).first()
            )
            return config.value if config else default

    def set_config(self, key: str, value: str) -> None:
        """Définit une valeur de configuration."""
        with self.get_session() as session:
            config = (
                session.query(BotConfig).filter(BotConfig.key == key).first()
            )
            if config:
                config.value = value
            else:
                config = BotConfig(key=key, value=value)
                session.add(config)
            session.commit()

    def cleanup_old_listings(self, days: int = 30) -> int:
        """Supprime les annonces plus anciennes que X jours."""
        with self.get_session() as session:
            cutoff = datetime.utcnow() - timedelta(days=days)
            deleted = (
                session.query(CarListing)
                .filter(CarListing.discovered_at < cutoff)
                .delete()
            )
            session.commit()
            if deleted > 0:
                logger.info(f"Nettoyage: {deleted} anciennes annonces supprimées")
            return deleted
