"""
Module de scraping pour Leboncoin.
Respecte les bonnes pratiques: délais entre requêtes, User-Agent réaliste,
gestion des erreurs avec backoff exponentiel.
"""

import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# User-Agents réalistes (navigateurs courants)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
]

# Mapping des marques pour les URLs Leboncoin
BRAND_MAPPING = {
    "mazda": "mazda",
    "honda": "honda",
    "suzuki": "suzuki",
    "seat": "seat",
    "peugeot": "peugeot",
    "citroen": "citroen",
    "citroën": "citroen",
    "renault": "renault",
    "toyota": "toyota",
}

# Mapping des modèles pour les URLs
MODEL_MAPPING = {
    "mazda_2": "2",
    "honda_jazz": "jazz",
    "suzuki_swift": "swift",
    "seat_ibiza": "ibiza",
    "peugeot_206": "206",
    "peugeot_207": "207",
    "peugeot_208": "208",
    "citroen_c3": "c3",
    "renault_clio": "clio",
    "toyota_yaris": "yaris",
}


@dataclass
class CarListing:
    """Représentation d'une annonce de voiture."""

    listing_id: str
    url: str
    title: str
    price: Optional[int] = None
    mileage: Optional[int] = None
    year: Optional[int] = None
    fuel: Optional[str] = None
    gearbox: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    engine: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    raw_data: dict = field(default_factory=dict)

    def matches_search(self, search_brand: str, search_model: Optional[str]) -> bool:
        """
        Vérifie si l'annonce correspond à la recherche.
        Utilise le titre et la marque/modèle stockés.
        """
        title_lower = self.title.lower() if self.title else ""
        brand_lower = (self.brand or "").lower()
        model_lower = (self.model or "").lower()
        search_brand_lower = search_brand.lower()
        search_model_lower = (search_model or "").lower()

        # Normaliser les marques (citroën -> citroen)
        brand_aliases = {
            "citroen": ["citroën", "citroen"],
            "citroën": ["citroën", "citroen"],
        }
        search_brands = brand_aliases.get(search_brand_lower, [search_brand_lower])

        # Vérifier la marque
        brand_match = any(
            sb in brand_lower or sb in title_lower
            for sb in search_brands
        )

        if not brand_match:
            return False

        # Si pas de modèle spécifié, la marque suffit
        if not search_model:
            return True

        # Vérifier le modèle avec des règles strictes
        # Pour éviter "Mazda 2" match "Peugeot 2008"

        # D'abord vérifier si le modèle stocké correspond exactement
        if model_lower and search_model_lower in model_lower:
            return True

        # Pour les modèles numériques courts (1, 2, 3...), être plus strict
        if search_model_lower.isdigit() and len(search_model_lower) <= 2:
            # Patterns stricts pour éviter "2" dans "2008", "206", etc.
            strict_patterns = [
                f"{search_brand_lower} {search_model_lower}",  # "mazda 2"
                f"{search_brand_lower}{search_model_lower} ",  # "mazda2 "
                f"{search_brand_lower}{search_model_lower},",  # "mazda2,"
                f" {search_model_lower} ",                     # " 2 " (avec espaces)
            ]
            # Aussi accepter en fin de titre
            if title_lower.endswith(f" {search_model_lower}"):
                return True
            if title_lower.endswith(f"{search_brand_lower}{search_model_lower}"):
                return True
            return any(p in title_lower for p in strict_patterns)

        # Pour les modèles alphanumériques (c3, jazz, swift, ibiza...)
        model_patterns = [
            search_model_lower,
            f" {search_model_lower} ",
            f" {search_model_lower},",
            f" {search_model_lower}.",
        ]

        return any(p in title_lower or p in model_lower for p in model_patterns)

    def to_dict(self) -> dict:
        """Convertit l'objet en dictionnaire pour la base de données."""
        return {
            "listing_id": self.listing_id,
            "url": self.url,
            "title": self.title,
            "price": self.price,
            "mileage": self.mileage,
            "year": self.year,
            "fuel": self.fuel,
            "gearbox": self.gearbox,
            "brand": self.brand,
            "model": self.model,
            "engine": self.engine,
            "location": self.location,
            "description": self.description,
            "image_url": self.image_url,
        }


class LeboncoinScraper:
    """Scraper pour les annonces automobiles sur Leboncoin."""

    BASE_URL = "https://www.leboncoin.fr"
    SEARCH_URL = f"{BASE_URL}/recherche"
    API_URL = "https://api.leboncoin.fr/finder/search"

    def __init__(
        self,
        delay_min: float = 5.0,
        delay_max: float = 10.0,
        max_retries: int = 3,
        timeout: float = 30.0,
    ):
        """
        Initialise le scraper.

        Args:
            delay_min: Délai minimum entre requêtes (secondes)
            delay_max: Délai maximum entre requêtes (secondes)
            max_retries: Nombre maximum de tentatives en cas d'échec
            timeout: Timeout pour les requêtes HTTP (secondes)
        """
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.max_retries = max_retries
        self.timeout = timeout
        self._last_request_time = 0
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        """Retourne ou crée un client HTTP avec headers réalistes."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers=self._get_headers(),
            )
        return self._client

    def _get_headers(self) -> dict:
        """Génère des headers HTTP réalistes."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    def _get_api_headers(self) -> dict:
        """Génère des headers pour l'API Leboncoin."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://www.leboncoin.fr",
            "Referer": "https://www.leboncoin.fr/",
            "api_key": "ba0c2dad52b3ec",  # Clé API publique de Leboncoin
        }

    def _respect_rate_limit(self) -> None:
        """Attend le délai nécessaire pour respecter le rate limiting."""
        elapsed = time.time() - self._last_request_time
        delay = random.uniform(self.delay_min, self.delay_max)
        if elapsed < delay:
            sleep_time = delay - elapsed
            logger.debug(f"Rate limiting: attente de {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _make_request(
        self, url: str, method: str = "GET", **kwargs
    ) -> Optional[httpx.Response]:
        """
        Effectue une requête HTTP avec retry et backoff exponentiel.

        Args:
            url: URL à requêter
            method: Méthode HTTP (GET, POST)
            **kwargs: Arguments supplémentaires pour httpx

        Returns:
            Réponse HTTP ou None en cas d'échec
        """
        self._respect_rate_limit()
        client = self._get_client()

        for attempt in range(self.max_retries):
            try:
                if method.upper() == "POST":
                    response = client.post(url, **kwargs)
                else:
                    response = client.get(url, **kwargs)

                if response.status_code == 200:
                    return response
                elif response.status_code == 403:
                    logger.warning(f"Accès refusé (403) - Possible blocage anti-bot")
                    # Renouveler le client avec de nouveaux headers
                    self._client = None
                elif response.status_code == 429:
                    logger.warning(f"Rate limit atteint (429)")
                else:
                    logger.warning(
                        f"Requête échouée: {response.status_code} pour {url}"
                    )

            except httpx.TimeoutException:
                logger.warning(f"Timeout sur {url} (tentative {attempt + 1})")
            except httpx.RequestError as e:
                logger.error(f"Erreur réseau: {e}")

            # Backoff exponentiel
            if attempt < self.max_retries - 1:
                backoff = (2**attempt) * random.uniform(1, 2)
                logger.info(f"Retry dans {backoff:.1f}s...")
                time.sleep(backoff)

        return None

    def _build_search_params(
        self,
        brand: str,
        model: Optional[str] = None,
        max_price: int = 3000,
        max_km: int = 150000,
        min_year: int = 2008,
        fuel: str = "essence",
        gearbox: str = "manuelle",
    ) -> dict:
        """
        Construit les paramètres de recherche pour l'API Leboncoin.
        """
        # Mapping carburant
        fuel_mapping = {
            "essence": "1",
            "diesel": "2",
            "hybride": "3",
            "electrique": "4",
            "gpl": "5",
        }

        # Mapping boîte de vitesse
        gearbox_mapping = {
            "manuelle": "1",
            "automatique": "2",
        }

        params = {
            "category": "2",  # Voitures
            "fuel": fuel_mapping.get(fuel.lower(), "1"),
            "gearbox": gearbox_mapping.get(gearbox.lower(), "1"),
            "owner_type": "all",
            "sort": "time",  # Tri par date (plus récent)
            "order": "desc",
        }

        # Prix maximum
        if max_price:
            params["price"] = f"0-{max_price}"

        # Kilométrage maximum
        if max_km:
            params["mileage"] = f"0-{max_km}"

        # Année minimum
        if min_year:
            params["regdate"] = f"{min_year}-{2025}"

        # Marque
        brand_normalized = BRAND_MAPPING.get(brand.lower(), brand.lower())
        params["brand"] = brand_normalized

        # Modèle (optionnel)
        if model:
            params["model"] = model.lower()

        return params

    def _build_search_url(self, params: dict) -> str:
        """Construit l'URL de recherche complète."""
        base_params = {
            "category": "2",
            "sort": "time",
            "order": "desc",
        }
        base_params.update(params)
        return f"{self.SEARCH_URL}?{urlencode(base_params)}"

    def search_cars(
        self,
        brand: str,
        model: Optional[str] = None,
        max_price: int = 3000,
        max_km: int = 150000,
        min_year: int = 2008,
        fuel: str = "essence",
        gearbox: str = "manuelle",
        max_results: int = 50,
    ) -> list[CarListing]:
        """
        Recherche des voitures sur Leboncoin.

        Args:
            brand: Marque de la voiture
            model: Modèle (optionnel)
            max_price: Prix maximum
            max_km: Kilométrage maximum
            min_year: Année minimum
            fuel: Type de carburant
            gearbox: Type de boîte de vitesse
            max_results: Nombre maximum de résultats

        Returns:
            Liste d'annonces trouvées
        """
        logger.info(f"Recherche: {brand} {model or ''} (max {max_price}€)")

        # Construire l'URL de recherche
        params = self._build_search_params(
            brand=brand,
            model=model,
            max_price=max_price,
            max_km=max_km,
            min_year=min_year,
            fuel=fuel,
            gearbox=gearbox,
        )
        search_url = self._build_search_url(params)

        # Récupérer la page de recherche
        response = self._make_request(search_url)
        if not response:
            logger.error(f"Échec de la recherche pour {brand} {model}")
            return []

        # Parser les résultats
        listings = self._parse_search_results(response.text, brand, model)

        # Filtrer pour ne garder que les annonces correspondant vraiment à la recherche
        filtered_listings = [
            listing for listing in listings
            if listing.matches_search(brand, model)
        ]

        logger.info(
            f"Trouvé {len(listings)} annonces, {len(filtered_listings)} correspondent à {brand} {model or ''}"
        )

        return filtered_listings[:max_results]

    def _parse_search_results(
        self, html: str, brand: str, model: Optional[str]
    ) -> list[CarListing]:
        """
        Parse les résultats de recherche HTML de Leboncoin.
        Leboncoin stocke les données dans un script JSON embarqué.
        """
        soup = BeautifulSoup(html, "lxml")
        listings = []

        # Chercher le JSON embarqué dans la page
        # Leboncoin stocke les données dans un script __NEXT_DATA__
        script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if script_tag and script_tag.string:
            try:
                data = json.loads(script_tag.string)
                ads = (
                    data.get("props", {})
                    .get("pageProps", {})
                    .get("searchData", {})
                    .get("ads", [])
                )

                for ad in ads:
                    listing = self._parse_ad_json(ad, brand, model)
                    if listing:
                        listings.append(listing)

            except json.JSONDecodeError as e:
                logger.error(f"Erreur parsing JSON: {e}")

        # Fallback: parser le HTML directement si pas de JSON
        if not listings:
            listings = self._parse_html_fallback(soup, brand, model)

        return listings

    def _parse_ad_json(
        self, ad: dict, brand: str, model: Optional[str]
    ) -> Optional[CarListing]:
        """Parse une annonce depuis les données JSON."""
        try:
            listing_id = str(ad.get("list_id", ""))
            if not listing_id:
                return None

            # Extraire les attributs
            attributes = {
                attr.get("key"): attr.get("value")
                for attr in ad.get("attributes", [])
                if attr.get("key") and attr.get("value")
            }

            # Extraire le kilométrage (peut être dans différents formats)
            mileage = None
            mileage_str = attributes.get("mileage", "")
            if mileage_str:
                mileage_match = re.search(r"(\d+)", mileage_str.replace(" ", ""))
                if mileage_match:
                    mileage = int(mileage_match.group(1))

            # Extraire l'année
            year = None
            regdate = attributes.get("regdate", "")
            if regdate:
                year_match = re.search(r"(\d{4})", regdate)
                if year_match:
                    year = int(year_match.group(1))

            # URL de l'image
            images = ad.get("images", {})
            image_url = None
            if images.get("urls"):
                image_url = images["urls"][0] if images["urls"] else None
            elif images.get("small_url"):
                image_url = images["small_url"]

            # Extraire la vraie marque/modèle depuis les attributs JSON
            actual_brand = attributes.get("brand", brand)
            actual_model = attributes.get("model", model)

            return CarListing(
                listing_id=listing_id,
                url=f"{self.BASE_URL}/ad/voitures/{listing_id}.htm",
                title=ad.get("subject", "Sans titre"),
                price=ad.get("price", [None])[0] if isinstance(ad.get("price"), list) else ad.get("price"),
                mileage=mileage,
                year=year,
                fuel=attributes.get("fuel", ""),
                gearbox=attributes.get("gearbox", ""),
                brand=actual_brand,
                model=actual_model,
                engine=attributes.get("vehicle_engine", ""),
                location=ad.get("location", {}).get("city", ""),
                description=ad.get("body", ""),
                image_url=image_url,
                raw_data=ad,
            )

        except Exception as e:
            logger.error(f"Erreur parsing annonce JSON: {e}")
            return None

    def _parse_html_fallback(
        self, soup: BeautifulSoup, brand: str, model: Optional[str]
    ) -> list[CarListing]:
        """
        Parse HTML en fallback si le JSON n'est pas disponible.
        Méthode moins fiable mais fonctionne en dernier recours.
        """
        listings = []

        # Chercher les cartes d'annonces
        ad_cards = soup.find_all("a", {"data-test-id": "ad"})
        if not ad_cards:
            ad_cards = soup.find_all("a", class_=re.compile(r".*styles_adCard.*"))

        for card in ad_cards:
            try:
                href = card.get("href", "")
                if not href or "/ad/" not in href:
                    continue

                # Extraire l'ID de l'annonce
                id_match = re.search(r"/(\d+)\.htm", href)
                if not id_match:
                    continue
                listing_id = id_match.group(1)

                # Titre
                title_elem = card.find(["h2", "p"], class_=re.compile(r".*title.*", re.I))
                title = title_elem.get_text(strip=True) if title_elem else "Sans titre"

                # Prix
                price = None
                price_elem = card.find(["span", "p"], class_=re.compile(r".*price.*", re.I))
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r"(\d[\d\s]*)", price_text.replace(" ", ""))
                    if price_match:
                        price = int(price_match.group(1).replace(" ", ""))

                listings.append(
                    CarListing(
                        listing_id=listing_id,
                        url=f"{self.BASE_URL}{href}" if href.startswith("/") else href,
                        title=title,
                        price=price,
                        brand=brand,
                        model=model,
                    )
                )

            except Exception as e:
                logger.debug(f"Erreur parsing carte HTML: {e}")
                continue

        return listings

    def get_listing_details(self, listing: CarListing) -> CarListing:
        """
        Récupère les détails complets d'une annonce.
        Utile pour obtenir la description complète et les attributs manquants.
        """
        response = self._make_request(listing.url)
        if not response:
            return listing

        soup = BeautifulSoup(response.text, "lxml")

        # Chercher le JSON embarqué
        script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if script_tag and script_tag.string:
            try:
                data = json.loads(script_tag.string)
                ad_data = data.get("props", {}).get("pageProps", {}).get("ad", {})

                if ad_data:
                    # Mettre à jour les champs manquants
                    attributes = {
                        attr.get("key"): attr.get("value")
                        for attr in ad_data.get("attributes", [])
                        if attr.get("key")
                    }

                    if not listing.description:
                        listing.description = ad_data.get("body", "")

                    if not listing.mileage and attributes.get("mileage"):
                        mileage_match = re.search(
                            r"(\d+)", attributes["mileage"].replace(" ", "")
                        )
                        if mileage_match:
                            listing.mileage = int(mileage_match.group(1))

                    if not listing.year and attributes.get("regdate"):
                        year_match = re.search(r"(\d{4})", attributes["regdate"])
                        if year_match:
                            listing.year = int(year_match.group(1))

                    if not listing.fuel:
                        listing.fuel = attributes.get("fuel", "")

                    if not listing.gearbox:
                        listing.gearbox = attributes.get("gearbox", "")

                    if not listing.engine:
                        listing.engine = attributes.get("vehicle_engine", "")

            except json.JSONDecodeError as e:
                logger.debug(f"Erreur parsing JSON détail: {e}")

        return listing

    def close(self) -> None:
        """Ferme le client HTTP."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
