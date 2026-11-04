"""Vigilante para GitHub Actions: escanea cada 5 minutos durante unas horas y luego pide el relevo.

GitHub descarta muchas ejecuciones programadas, así que en vez de arrancar cada 5 minutos,
cada ejecución se queda vigilando (L-V de 8:00 a 22:00, hora de Madrid) y, al terminar,
lanza la siguiente con workflow_dispatch.

Uso (desde el workflow):
  python -I escaner/vigilar.py           vigila hasta el límite de tiempo o hasta fuera de horario
  python -I escaner/vigilar.py relevo    lanza la siguiente ejecución si aún estamos en horario
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import escaner  # noqa: E402

DURACION = 5 * 3600 + 20 * 60   # deja margen antes del límite de 6 h de GitHub
INTERVALO = 300                  # 5 minutos
DESFASE = 45                     # segundos tras el cierre de la vela, para que la fuente la tenga


def ahora():
    return dt.datetime.now(dt.timezone.utc)


def publicar_datos():
    """Exporta velas y análisis y los sube a la rama «datos» (la lee el gráfico de la Mesa)."""
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return
    with tempfile.TemporaryDirectory() as d:
        escaner.exporta(os.path.join(d, "datos.json"))
        git = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)
        git("init", "-q", "-b", "datos")
        git("add", "datos.json")
        git("-c", "user.name=escaner", "-c", "user.email=escaner@users.noreply.github.com", "commit", "-q", "-m", "Datos del escáner")
        git("push", "-q", "-f", f"https://x-access-token:{token}@github.com/{repo}.git", "datos")


def vigilar():
    fin = time.time() + DURACION
    vueltas = 0
    while time.time() < fin and escaner.en_horario():
        inicio = ahora().strftime("%H:%M:%S UTC")
        try:
            escaner.escanea(enviar=True)
        except Exception as e:
            print("Error al escanear:", e)
        try:
            publicar_datos()
        except Exception as e:
            print("Error al publicar los datos:", e)
        vueltas += 1
        print(f"Vuelta {vueltas} hecha ({inicio}). {open(os.path.join(escaner.CARPETA, 'escaner.log'), encoding='utf-8').read().splitlines()[-1]}", flush=True)
        espera = INTERVALO - (time.time() % INTERVALO) + DESFASE
        if time.time() + espera >= fin:
            break
        time.sleep(espera)
    print(f"Fin de la vigilancia tras {vueltas} vueltas. En horario: {escaner.en_horario()}")


def relevo():
    """Lanza la siguiente ejecución del workflow si seguimos en horario de mercado."""
    if not escaner.en_horario():
        print("Fuera de horario: no hace falta relevo. Mañana arrancará la programación de GitHub.")
        return
    token, repo = os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"]
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/workflows/escaner.yml/dispatches",
        data=json.dumps({"ref": "main"}).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "escaner-mesa"})
    with urllib.request.urlopen(req, timeout=20) as r:
        print("Relevo lanzado:", r.status)


if __name__ == "__main__":
    relevo() if sys.argv[1:] == ["relevo"] else vigilar()
