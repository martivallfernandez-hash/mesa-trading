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
import senales_h1  # noqa: E402

DURACION = 5 * 3600 + 20 * 60   # deja margen antes del límite de 6 h de GitHub
INTERVALO = 300                  # 5 minutos
DESFASE = 45                     # segundos tras el cierre de la vela, para que la fuente la tenga


def ahora():
    return dt.datetime.now(dt.timezone.utc)


SPREAD = {"AUDCAD": 0.0002, "NZDCAD": 0.00025, "EURUSD": 0.00008, "GBPUSD": 0.00012, "USDJPY": 0.012,
          "AUDUSD": 0.0001, "XAUUSD": 0.30, "XAUEUR": 0.35, "BTCUSDT": 15.0, "ETHUSDT": 1.2}
MAX_HORAS = 12
senales = None   # historial de avisos con su resultado (se guarda en la rama «datos» como senales.json)


def cargar_senales():
    """Recupera el historial de la rama «datos» (cada ejecución empieza en una máquina nueva)."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return []
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://api.github.com/repos/{repo}/contents/senales.json?ref=datos",
                headers={"Accept": "application/vnd.github.raw", "User-Agent": "escaner-mesa",
                         "Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN', '')}"}), timeout=20) as r:
            return json.load(r)
    except Exception as e:
        print("Sin historial previo de señales:", e)
        return []


def registrar(nuevas):
    """Guarda las señales nuevas de las estrategias de 1 h para seguir su resultado."""
    for x in nuevas or []:
        senales.append({"id": x["id"], "activo": x["activo"], "direccion": x["direccion"], "estrategia": x["nombre"],
                        "puntos": None, "fuerte": True, "entrada": x["entrada"], "stop": x["stop"], "objetivo": x["objetivo"],
                        "rr": x["rr"], "ts": x["ts"] + 3600, "velas_max": x["velas_max"], "decimales": x["decimales"],
                        "avisada": escaner.en_horario(), "estado": "abierta", "R": None, "cierre_ts": None})


def evaluar(datos):
    """Mira en las velas de 1 h si cada señal abierta tocó antes el objetivo o el stop."""
    abiertas = [s for s in senales if s["estado"] == "abierta"]
    cache = {}
    for s in abiertas:
        m = s["activo"]
        if m not in cache:
            try:
                cache[m] = senales_h1.velas_1h(m)
            except Exception as e:
                print("Sin velas para evaluar", m, e)
                cache[m] = []
        v = cache[m]
        if not v:
            continue
        compra, riesgo = s["direccion"] == "compra", abs(s["entrada"] - s["stop"]) or 1e-12
        ahora = time.time()
        cerradas = [x for x in v if x[0] >= s["ts"] and x[0] + 3600 <= ahora + 60]
        for t, o, h, l, c in cerradas:
            if (l <= s["stop"]) if compra else (h >= s["stop"]):
                s.update(estado="stop", cierre_ts=t + 3600, salida=s["stop"]); break
            if (h >= s["objetivo"]) if compra else (l <= s["objetivo"]):
                s.update(estado="objetivo", cierre_ts=t + 3600, salida=s["objetivo"]); break
        else:
            if len(cerradas) >= s.get("velas_max", 24):
                s.update(estado="tiempo", cierre_ts=cerradas[-1][0] + 3600, salida=cerradas[-1][4])
        if s["estado"] != "abierta":
            mov = (s["salida"] - s["entrada"]) if compra else (s["entrada"] - s["salida"])
            s["R"] = round((mov - SPREAD.get(m, 0)) / riesgo, 3)
        else:
            precio = v[-1][4]
            s["R_actual"] = round(((precio - s["entrada"]) if compra else (s["entrada"] - precio)) / riesgo, 2)
    limite = time.time() - 60 * 86400
    senales[:] = [s for s in senales if s["ts"] >= limite and s.get("estrategia")]  # solo señales de las estrategias nuevas


def publicar_datos(nuevas):
    """Exporta velas, análisis y el historial de señales a la rama «datos» (la lee la Mesa)."""
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return
    with tempfile.TemporaryDirectory() as d:
        datos = escaner.exporta(os.path.join(d, "datos.json"))
        registrar(nuevas)
        evaluar(datos)
        with open(os.path.join(d, "senales.json"), "w", encoding="utf-8") as f:
            json.dump(senales, f, ensure_ascii=False, separators=(",", ":"))
        git = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)
        git("init", "-q", "-b", "datos")
        git("add", "datos.json", "senales.json")
        git("-c", "user.name=escaner", "-c", "user.email=escaner@users.noreply.github.com", "commit", "-q", "-m", "Datos del escáner")
        git("push", "-q", "-f", f"https://x-access-token:{token}@github.com/{repo}.git", "datos")


def vigilar():
    global senales
    senales = cargar_senales()
    fin = time.time() + DURACION
    vueltas = 0
    while time.time() < fin and escaner.en_horario():
        inicio = ahora().strftime("%H:%M:%S UTC")
        nuevas = []
        try:
            nuevas = senales_h1.escanea({x["id"] for x in senales}, {x["activo"] for x in senales if x["estado"] == "abierta"})
        except Exception as e:
            print("Error al escanear:", e)
        try:
            publicar_datos(nuevas)
        except Exception as e:
            print("Error al publicar los datos:", e)
        vueltas += 1
        print(f"Vuelta {vueltas} hecha ({inicio}). {len(nuevas)} señales nuevas", flush=True)
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
