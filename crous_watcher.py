#!/usr/bin/env python3
"""
Surveille une page de résultats du site trouverunlogement.lescrous.fr
et envoie une notification Telegram quand une nouvelle annonce apparaît.

Variables d'environnement nécessaires :
- CROUS_URL             : l'URL de la page de résultats de recherche à surveiller
- TELEGRAM_BOT_TOKEN    : le token du bot Telegram (via @BotFather)
- TELEGRAM_CHAT_ID      : l'identifiant de chat Telegram qui recevra les alertes

Fichier d'état :
- state.json : mémorise les annonces déjà vues, pour ne notifier que les nouvelles.
"""

import json
import os
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

STATE_FILE = Path(__file__).parent / "state.json"
BASE_URL = "https://trouverunlogement.lescrous.fr"

# Une annonce est identifiée par son URL, du type /tools/47/accommodations/2071
LISTING_HREF_RE = re.compile(r"^/tools/\d+/accommodations/\d+")


def fetch_listings(url: str) -> dict[str, dict]:
    """Récupère la page de résultats et renvoie les annonces sous la forme
    {href: {"title": ..., "price": ..., "address": ..., "url": ...}}.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    listings: dict[str, dict] = {}

    for link in soup.find_all("a", href=LISTING_HREF_RE):
        href = link["href"]
        link_text = link.get_text(strip=True)

        # Une même annonce peut avoir plusieurs liens (image + titre) : on ne
        # garde/actualise le titre que quand on trouve un lien avec du texte.
        if href in listings:
            if link_text and listings[href]["title"] == "Logement CROUS":
                listings[href]["title"] = link_text
            continue

        # Le conteneur parent de l'annonce (pour en extraire le prix, l'adresse, etc.)
        container = link.find_parent("li") or link.parent
        text = container.get_text(" ", strip=True) if container else ""

        price_match = re.search(r"[\d,.]+\s*€", text)
        price = price_match.group(0) if price_match else "prix non trouvé"

        listings[href] = {
            "title": link_text or "Logement CROUS",
            "price": price,
            "url": BASE_URL + href,
        }

    return listings


def load_previous_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(
        url,
        data={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )
    if not resp.ok:
        print(f"Erreur d'envoi Telegram : {resp.status_code} {resp.text}", file=sys.stderr)


def main() -> None:
    crous_url = os.environ["CROUS_URL"]
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    previous_state = load_previous_state()
    current_listings = fetch_listings(crous_url)

    is_first_run = not previous_state
    new_hrefs = [h for h in current_listings if h not in previous_state]

    if is_first_run:
        print(f"Premier lancement : {len(current_listings)} annonce(s) enregistrée(s) comme référence.")
    elif new_hrefs:
        print(f"{len(new_hrefs)} nouvelle(s) annonce(s) trouvée(s).")
        for href in new_hrefs:
            listing = current_listings[href]
            message = (
                "🏠 Nouvelle annonce CROUS !\n\n"
                f"{listing['title']}\n"
                f"{listing['price']}\n"
                f"{listing['url']}"
            )
            send_telegram_message(bot_token, chat_id, message)
    else:
        print("Aucune nouvelle annonce.")

    save_state(current_listings)


if __name__ == "__main__":
    main()
