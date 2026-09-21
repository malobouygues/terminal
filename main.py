"""Point d'entrée du terminal.

  1. lance IB Gateway (installation locale) et s'y connecte (auto-login optionnel) ;
  2. synchronise market_data.db (clôtures, FX, cash IB) ;
  3. recalcule la performance globale (analytics.db) ;
  4. ouvre le frontend PySide6 — la connexion IB reste ouverte pour les prix live ;
  5. à la fermeture de la fenêtre : déconnexion IB, arrêt d'IB Gateway et de Terminal.

Le terminal s'ouvre même si IB Gateway est indisponible (données en cache).
"""

import asyncio
import logging
import os
import plistlib
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_API", "pyside6")   # qasync doit lier PySide6, pas PyQt6 (aussi installé)
import qasync  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import market_data
from engine import performance
from engine.db import ensure_schemas
from frontend import MainWindow
from services import ServiceContainer
from ui.styles import get_stylesheet, load_bloomberg_font

IB_GATEWAY_APP = Path.home() / "Applications/IB Gateway 10.43/IB Gateway 10.43.app"
IB_HOST, IB_CLIENT_ID = "127.0.0.1", 7
IB_PORTS = (4001, 4002, 4000, 7496, 7497)   # ports API candidats : Gateway réel / papier, TWS réel / papier
IB_USERNAME = "apibot001"
IB_PASSWORD = "vuMjQFGceEawIH8"
IB_ACCOUNTS = {       # id de compte IB → compte ledger (IBK_LONG ou IBK_LEV)
    "U11542510": "IBK_LEV",
}
LOGIN_TIMEOUT = 300   # secondes — laisse le temps au 2FA

logger = logging.getLogger("main")


# ---------------------------------------------------------------------------
# IB Gateway
# ---------------------------------------------------------------------------

async def _api_port() -> int | None:
    """Premier port API qui accepte une connexion, sinon None."""
    for port in IB_PORTS:
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(IB_HOST, port), 1)
            writer.close()
            return port
        except OSError:
            continue
    return None


async def _auto_login() -> None:
    """Saisit identifiant + mot de passe dans la fenêtre de login (System Events).
    Nécessite l'autorisation Accessibilité pour le terminal qui lance main.py."""
    bundle_id = _bundle_id()
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
    tell application "System Events"
        repeat 90 times
            if exists (first process whose bundle identifier is "{bundle_id}") then
                tell (first process whose bundle identifier is "{bundle_id}")
                    if (exists window 1) and (exists text field 1 of window 1) then exit repeat
                end tell
            end if
            delay 1
        end repeat
        tell (first process whose bundle identifier is "{bundle_id}")
            set frontmost to true
            delay 1
            click text field 1 of window 1
            delay 0.5
            keystroke "a" using command down
            key code 51
            keystroke "{esc(IB_USERNAME)}"
            delay 0.3
            keystroke tab
            delay 0.3
            keystroke "a" using command down
            key code 51
            keystroke "{esc(IB_PASSWORD)}"
            delay 0.3
            keystroke return
        end tell
    end tell'''
    err = await _osascript(script)
    if err:
        logger.warning("Auto-login impossible (%s) — connectez-vous manuellement", err)


async def _osascript(script: str) -> str:
    """Exécute un AppleScript ; retourne le message d'erreur (vide si OK)."""
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    _, err = await proc.communicate()
    return err.decode().strip() if proc.returncode else ""


def _bundle_id() -> str:
    return plistlib.loads((IB_GATEWAY_APP / "Contents/Info.plist").read_bytes())["CFBundleIdentifier"]


async def show_terminal_only() -> None:
    """Masque IB Gateway et Terminal, met la fenêtre PySide6 au premier plan."""
    err = await _osascript(f'''
    tell application "System Events"
        set visible of (every process whose bundle identifier is "{_bundle_id()}") to false
        set visible of (every process whose name is "Terminal") to false
        set frontmost of (first process whose unix id is {os.getpid()}) to true
    end tell''')
    if err:
        logger.warning("Premier plan impossible (%s)", err)


async def launch_gateway() -> int | None:
    """Lance IB Gateway s'il n'écoute pas déjà, attend l'API (login, 2FA) et retourne son port."""
    port = await _api_port()
    if port:
        logger.info("IB Gateway déjà actif sur le port %s", port)
        return port
    if not IB_GATEWAY_APP.exists():
        logger.warning("IB Gateway introuvable : %s", IB_GATEWAY_APP)
        return None
    subprocess.Popen(["open", "-a", str(IB_GATEWAY_APP)])
    logger.info("IB Gateway lancé — en attente du login (%ss max)", LOGIN_TIMEOUT)
    if IB_USERNAME:
        await _auto_login()
    for i in range(LOGIN_TIMEOUT // 2):
        port = await _api_port()
        if port:
            logger.info("API IB Gateway disponible sur le port %s", port)
            await asyncio.sleep(3)          # laisse l'API finir son initialisation
            return port
        if i % 15 == 14:
            logger.info("En attente de l'API IB Gateway (login / 2FA)… ports testés : %s", IB_PORTS)
        await asyncio.sleep(2)
    logger.warning("IB Gateway toujours indisponible après %ss — ouverture sans données live", LOGIN_TIMEOUT)
    return None


def quit_gateway() -> None:
    subprocess.run(["pkill", "-f", str(IB_GATEWAY_APP / "Contents/MacOS")], stdout=subprocess.DEVNULL)


def quit_terminal() -> None:
    """Ferme Terminal.app (lancement par le raccourci) — processus détaché, après la sortie du shell."""
    if os.environ.get("TERM_PROGRAM") != "Apple_Terminal":
        return
    subprocess.Popen(["osascript", "-e", "delay 1", "-e", 'tell application "Terminal" to quit'],
                     start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------------------
# Démarrage
# ---------------------------------------------------------------------------

async def startup():
    ensure_schemas()
    port = await launch_gateway()
    ib = await market_data.connect(IB_HOST, port, IB_CLIENT_ID) if port else None
    if ib is not None:
        for label, coro in (("Clôtures et FX…", market_data.sync_history(ib)),
                            ("Cash IB…", market_data.sync_cash(ib, IB_ACCOUNTS)),
                            ("Prix live…", market_data.refresh_live(ib))):
            logger.info(label)
            try:
                await coro
            except Exception:
                logger.exception("Étape '%s' en échec — poursuite avec le cache", label)
    await asyncio.to_thread(performance.recompute)
    return ib


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    app.setStyleSheet(get_stylesheet(load_bloomberg_font()))

    async def open_terminal():
        try:
            ib = await startup()
        except Exception:
            logger.exception("Démarrage incomplet — ouverture du terminal sans IB")
            ib = None
        services = ServiceContainer.from_defaults(ib=ib)
        app.window = MainWindow(services=services)
        app.window.show()
        await show_terminal_only()
        app.aboutToQuit.connect(services.market.close)
        app.aboutToQuit.connect(quit_gateway)
        app.aboutToQuit.connect(quit_terminal)

    with loop:
        loop.create_task(open_terminal())
        loop.run_forever()


if __name__ == "__main__":
    run()
