"""
Module de filtrage et scoring des annonces.
Implémente les critères d'exclusion et le système de scoring pour prioriser les annonces.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ScoreResult:
    """Résultat du scoring d'une annonce."""

    total_score: int = 0
    priority: str = "low"  # high, medium, low
    bonuses: list = field(default_factory=list)
    penalties: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    excluded: bool = False
    exclusion_reason: Optional[str] = None

    def to_json(self) -> str:
        """Convertit les détails en JSON pour stockage."""
        return json.dumps(
            {
                "total_score": self.total_score,
                "priority": self.priority,
                "bonuses": self.bonuses,
                "penalties": self.penalties,
                "warnings": self.warnings,
            },
            ensure_ascii=False,
        )


class CarFilter:
    """Filtre et score les annonces selon les critères définis."""

    def __init__(self, config_dir: str = "config"):
        """
        Initialise le filtre avec les fichiers de configuration.

        Args:
            config_dir: Dossier contenant les fichiers YAML
        """
        self.config_dir = Path(config_dir)
        self.criteria = self._load_yaml("criteria.yaml")
        self.exclusions = self._load_yaml("exclusions.yaml")

        # Seuils de priorité (modifiables)
        self.high_threshold = (
            self.criteria.get("priority_thresholds", {}).get("high", 15)
        )
        self.medium_threshold = (
            self.criteria.get("priority_thresholds", {}).get("medium", 10)
        )

        logger.info("Filtre initialisé avec les critères de configuration")

    def _load_yaml(self, filename: str) -> dict:
        """Charge un fichier YAML."""
        filepath = self.config_dir / filename
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"Fichier de configuration non trouvé: {filepath}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Erreur parsing YAML {filepath}: {e}")
            return {}

    def set_high_threshold(self, value: int) -> None:
        """Modifie le seuil de haute priorité."""
        self.high_threshold = value
        logger.info(f"Seuil haute priorité mis à jour: {value}")

    def _normalize_text(self, text: Optional[str]) -> str:
        """Normalise le texte pour comparaison (minuscules, sans accents)."""
        if not text:
            return ""
        text = text.lower()
        # Simplifier les accents courants
        replacements = {
            "é": "e",
            "è": "e",
            "ê": "e",
            "ë": "e",
            "à": "a",
            "â": "a",
            "ù": "u",
            "û": "u",
            "ô": "o",
            "î": "i",
            "ï": "i",
            "ç": "c",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    def _check_blacklist(self, text: str) -> tuple[bool, Optional[str]]:
        """
        Vérifie si le texte contient des mots-clés blacklistés.

        Returns:
            (is_blacklisted, keyword_found)
        """
        text_normalized = self._normalize_text(text)
        blacklist = self.exclusions.get("blacklist_keywords", {})

        for category, keywords in blacklist.items():
            for keyword in keywords:
                keyword_normalized = self._normalize_text(keyword)
                if keyword_normalized in text_normalized:
                    logger.debug(f"Mot-clé blacklist détecté: '{keyword}' ({category})")
                    return True, keyword

        return False, None

    def _check_brand_exclusions(
        self, brand: str, title: str, description: str, engine: str
    ) -> tuple[bool, Optional[str], list[str]]:
        """
        Vérifie les exclusions spécifiques à la marque.

        Returns:
            (is_excluded, exclusion_reason, warnings)
        """
        brand_lower = brand.lower() if brand else ""
        text = f"{title} {description} {engine}".lower()
        exclusions = self.exclusions.get("brand_exclusions", {})
        warnings = []

        if brand_lower not in exclusions:
            return False, None, warnings

        brand_rules = exclusions[brand_lower]

        # Vérifier les moteurs exclus
        excluded_engines = brand_rules.get("engines", [])
        for engine_pattern in excluded_engines:
            if engine_pattern.lower() in text:
                reason = f"Moteur exclu: {engine_pattern} - {brand_rules.get('reason', '')}"
                return True, reason, warnings

        # Vérifier les transmissions exclues (Honda Jazz notamment)
        excluded_trans = brand_rules.get("transmissions", [])
        for trans in excluded_trans:
            if trans.lower() in text:
                reason = f"Transmission exclue: {trans} - {brand_rules.get('reason', '')}"
                return True, reason, warnings

        # Vérifier si boîte manuelle requise (Honda Jazz)
        if brand_rules.get("require_manual"):
            if "manuelle" not in text and "manuel" not in text:
                warnings.append("Vérifier absence CVT/automatique")

        # Vérifier les exclusions par année (Suzuki Swift)
        year_excl = brand_rules.get("year_exclusions")
        if year_excl:
            # On vérifie cela au niveau du scoring, pas de l'exclusion directe
            pass

        # Seat Ibiza: vérifier moteurs acceptés
        if brand_lower == "seat":
            accepted = brand_rules.get("accepted_engines", [])
            engine_detected = False
            for acc_engine in accepted:
                if acc_engine.lower() in text:
                    engine_detected = True
                    break

            # Si moteur TSI/TDI détecté sans être dans les acceptés
            tsi_tdi_pattern = r"\b1\.[24]\s*(tsi|tdi)\b"
            if re.search(tsi_tdi_pattern, text, re.IGNORECASE) and not engine_detected:
                reason = "Seat Ibiza avec moteur TSI/TDI exclu"
                return True, reason, warnings

        return False, None, warnings

    def _calculate_bonus_points(
        self, brand: str, model: str, title: str, description: str, price: int, mileage: int
    ) -> tuple[int, list[str]]:
        """
        Calcule les points bonus selon les critères.

        Returns:
            (bonus_points, list_of_bonuses)
        """
        points = 0
        bonuses = []
        text = f"{title} {description}".lower()
        brand_lower = (brand or "").lower()
        model_lower = (model or "").lower()

        scoring = self.criteria.get("scoring", {})

        # Bonus modèles prioritaires
        # Mazda 2 essence chaîne
        if brand_lower == "mazda" and "2" in model_lower:
            if "essence" in text or "chaîne" in text or "chaine" in text:
                points += scoring.get("high_priority_models", {}).get("mazda_2_essence", 10)
                bonuses.append("+10 Mazda 2 essence/chaîne")

        # Honda Jazz manuelle
        if brand_lower == "honda" and "jazz" in model_lower:
            if "manuelle" in text or "manuel" in text:
                points += scoring.get("high_priority_models", {}).get("honda_jazz_manuelle", 10)
                bonuses.append("+10 Honda Jazz manuelle")

        # Suzuki Swift 3 post-2010
        if brand_lower == "suzuki" and "swift" in model_lower:
            points += scoring.get("high_priority_models", {}).get("swift_3_post_2010", 10)
            bonuses.append("+10 Suzuki Swift 3")

        # Seat Ibiza atmosphérique
        if brand_lower == "seat" and "ibiza" in model_lower:
            if "1.4 16v" in text or "1.2 12v" in text or "atmosphérique" in text or "atmo" in text:
                points += scoring.get("high_priority_models", {}).get("seat_ibiza_atmo", 5)
                bonuses.append("+5 Seat Ibiza atmosphérique")

        # Toyota Yaris
        if brand_lower == "toyota" and "yaris" in model_lower:
            points += scoring.get("high_priority_models", {}).get("toyota_yaris", 5)
            bonuses.append("+5 Toyota Yaris")

        # Bonus mots-clés positifs
        positive_keywords = self.exclusions.get("positive_keywords", {})

        # Historique entretien
        for kw in positive_keywords.get("maintenance", []):
            if self._normalize_text(kw) in self._normalize_text(text):
                if "distribution" in kw.lower():
                    points += scoring.get("distribution_done", 3)
                    bonuses.append(f"+3 Distribution mentionnée")
                elif "chaîne" in kw.lower() or "chaine" in kw.lower():
                    points += scoring.get("chain_engine", 3)
                    bonuses.append(f"+3 Moteur chaîne")
                else:
                    points += scoring.get("history_mentioned", 3)
                    bonuses.append(f"+3 Entretien suivi")
                break  # Un seul bonus entretien

        # Bonus prix < 2500€
        if price and price < 2500:
            points += scoring.get("price_under_2500", 2)
            bonuses.append(f"+2 Prix < 2500€")

        # Bonus km < 100 000
        if mileage and mileage < 100000:
            points += scoring.get("km_under_100000", 2)
            bonuses.append(f"+2 Km < 100 000")

        return points, bonuses

    def _calculate_penalty_points(
        self, brand: str, title: str, description: str, fuel: str
    ) -> tuple[int, list[str]]:
        """
        Calcule les points de pénalité.

        Returns:
            (penalty_points, list_of_penalties) - penalty_points est négatif
        """
        points = 0
        penalties = []
        text = f"{title} {description} {fuel}".lower()
        scoring = self.criteria.get("scoring", {})

        # Pénalité diesel (sauf si explicitement accepté)
        if "diesel" in text or fuel and "diesel" in fuel.lower():
            brand_lower = (brand or "").lower()
            # Les diesels sont quasi-toujours problématiques sur ces modèles
            points += scoring.get("diesel_penalty", -5)
            penalties.append(f"-5 Diesel")

        # Pénalité mots-clés blacklist (si pas exclu mais mentionné en contexte)
        blacklist = self.exclusions.get("blacklist_keywords", {})
        suspicious = blacklist.get("suspicious", [])
        for kw in suspicious:
            if self._normalize_text(kw) in self._normalize_text(text):
                points += scoring.get("blacklist_keyword_penalty", -10)
                penalties.append(f"-10 Mot suspect: {kw}")
                break

        return points, penalties

    def evaluate(
        self,
        listing_id: str,
        title: str,
        description: str = "",
        price: Optional[int] = None,
        mileage: Optional[int] = None,
        year: Optional[int] = None,
        fuel: Optional[str] = None,
        gearbox: Optional[str] = None,
        brand: Optional[str] = None,
        model: Optional[str] = None,
        engine: Optional[str] = None,
    ) -> ScoreResult:
        """
        Évalue une annonce et retourne son score et sa priorité.

        Args:
            listing_id: ID unique de l'annonce
            title: Titre de l'annonce
            description: Description complète
            price: Prix en euros
            mileage: Kilométrage
            year: Année
            fuel: Type de carburant
            gearbox: Type de boîte
            brand: Marque
            model: Modèle
            engine: Motorisation

        Returns:
            ScoreResult avec le score total, priorité et détails
        """
        result = ScoreResult()
        full_text = f"{title} {description}"

        # 1. Vérifier blacklist globale
        is_blacklisted, blacklist_keyword = self._check_blacklist(full_text)
        if is_blacklisted:
            result.excluded = True
            result.exclusion_reason = f"Mot-clé blacklist: {blacklist_keyword}"
            logger.info(f"Annonce {listing_id} exclue: {result.exclusion_reason}")
            return result

        # 2. Vérifier exclusions par marque
        is_excluded, exclusion_reason, brand_warnings = self._check_brand_exclusions(
            brand or "", title, description, engine or ""
        )
        if is_excluded:
            result.excluded = True
            result.exclusion_reason = exclusion_reason
            logger.info(f"Annonce {listing_id} exclue: {result.exclusion_reason}")
            return result
        result.warnings.extend(brand_warnings)

        # 3. Vérifier critères généraux
        general = self.criteria.get("general", {})

        # Prix maximum
        max_price = general.get("max_price", 3000)
        if price and price > max_price:
            result.excluded = True
            result.exclusion_reason = f"Prix {price}€ > max {max_price}€"
            return result

        # Kilométrage maximum
        max_km = general.get("max_km", 150000)
        if mileage and mileage > max_km:
            result.excluded = True
            result.exclusion_reason = f"Km {mileage} > max {max_km}"
            return result

        # Année minimum
        min_year = general.get("min_year", 2008)
        if year and year < min_year:
            result.excluded = True
            result.exclusion_reason = f"Année {year} < min {min_year}"
            return result

        # Boîte de vitesse (essence uniquement - vérifier si manuelle)
        required_gearbox = general.get("gearbox", "manuelle")
        if gearbox:
            gearbox_lower = gearbox.lower()
            if required_gearbox == "manuelle" and "automatique" in gearbox_lower:
                result.excluded = True
                result.exclusion_reason = "Boîte automatique exclue"
                return result

        # Carburant
        required_fuel = general.get("fuel", "essence")
        if fuel:
            fuel_lower = fuel.lower()
            if required_fuel == "essence" and "diesel" in fuel_lower:
                # Ne pas exclure immédiatement, mais pénaliser
                pass

        # 4. Calculer les bonus
        bonus_points, bonuses = self._calculate_bonus_points(
            brand or "", model or "", title, description, price or 0, mileage or 0
        )
        result.bonuses = bonuses

        # 5. Calculer les pénalités
        penalty_points, penalties = self._calculate_penalty_points(
            brand or "", title, description, fuel or ""
        )
        result.penalties = penalties

        # 6. Score total
        result.total_score = bonus_points + penalty_points  # penalty_points est négatif

        # 7. Déterminer la priorité
        if result.total_score > self.high_threshold:
            result.priority = "high"
        elif result.total_score >= self.medium_threshold:
            result.priority = "medium"
        else:
            result.priority = "low"

        logger.debug(
            f"Annonce {listing_id}: score={result.total_score}, priorité={result.priority}"
        )

        return result

    def get_criteria_summary(self) -> str:
        """Retourne un résumé des critères de recherche."""
        general = self.criteria.get("general", {})
        models = self.criteria.get("models", [])

        summary = [
            "**Critères de recherche actuels:**",
            "",
            "**Général:**",
            f"- Prix max: {general.get('max_price', 3000)}€",
            f"- Km max: {general.get('max_km', 150000)} km",
            f"- Année min: {general.get('min_year', 2008)}",
            f"- Boîte: {general.get('gearbox', 'manuelle')}",
            f"- Carburant: {general.get('fuel', 'essence')}",
            "",
            "**Modèles ciblés:**",
        ]

        for m in models:
            summary.append(f"- {m.get('name', 'Inconnu')} (priorité: {m.get('priority_score', 0)})")

        summary.extend([
            "",
            f"**Seuils de priorité:**",
            f"- Haute: score > {self.high_threshold}",
            f"- Moyenne: score {self.medium_threshold}-{self.high_threshold}",
            f"- Basse: score < {self.medium_threshold}",
        ])

        return "\n".join(summary)

    def get_model_configs(self) -> list[dict]:
        """Retourne la configuration des modèles pour les recherches."""
        return self.criteria.get("models", [])
