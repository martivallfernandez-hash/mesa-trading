"""Puente con tu MetaTrader 5: señales del oro con los precios y velas de TU broker.

Uso (en el PC, con MetaTrader 5 abierto y con sesión iniciada):
  pythonw -E -P escaner/mt5_puente.py          una pasada (la lanza el Programador de tareas cada 5 min)
  python  -E -P escaner/mt5_puente.py prueba   muestra el análisis sin avisar

Usa la misma estrategia robusta que la nube (estrategias.json), pero con las velas de 1 h, el precio
(bid/ask) y el tamaño de contrato de tu broker, y calcula los lotes con tu balance y tu moneda reales.
Si la nube ya ha avisado de lo mismo (mismo mercado y dirección en las últimas 6 h), no repite.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.request

CARPETA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CARPETA)
if sys.stdout is None:   # pythonw no tiene consola
    sys.stdout = sys.stderr = open(os.devnull, "w")
else:
    sys.stdout.reconfigure(encoding="utf-8")

import MetaTrader5 as mt5  # noqa: E402
import laboratorio as L    # noqa: E402
import senales_h1 as H     # noqa: E402
import escaner             # noqa: E402

TERMINAL = "C:/Program Files/MetaTrader 5/terminal64.exe"
MERCADOS = ["XAUUSD", "XAUEUR"]
RIESGO_PCT = 1.0
LOG = os.path.join(os.path.expanduser("~"), ".claude", "trading", "mt5_puente.log")


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def tema():
    if os.environ.get("NTFY_TEMA"):
        return os.environ["NTFY_TEMA"]
    with open(os.path.join(os.path.expanduser("~"), ".claude", "trading", "config.json"), encoding="utf-8") as f:
        return json.load(f)["ntfy_tema"]


def ya_avisado(m, direccion, horas=6):
    """¿Se ha avisado ya de este mercado y dirección (desde el PC o la nube) en las últimas horas?"""
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{tema()}/json?poll=1&since={horas}h",
                                                           headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
            titulos = [json.loads(x).get("title", "") for x in r.read().decode("utf-8").splitlines() if x.strip()]
        return any(t.startswith(f"{m} · {direccion.upper()} ·") for t in titulos)
    except Exception:
        return False


def velas_broker(m):
    """Velas de 1 h cerradas del broker, con la hora pasada a UTC."""
    tick = mt5.symbol_info_tick(m)
    desfase = round((tick.time - time.time()) / 3600) * 3600 if tick and tick.time else 0   # hora del servidor - UTC
    r = mt5.copy_rates_from_pos(m, mt5.TIMEFRAME_H1, 0, 600)
    if r is None or len(r) < 230:
        return None, None
    v = [(int(x["time"]) - desfase, float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"])) for x in r]
    ahora = time.time()
    return [x for x in v if x[0] + 3600 <= ahora + 60], tick


def analizar(m, cfg):
    info = cfg["mercados"].get(m) or {}
    if info.get("elegida") != "ruptura_robusta":
        return None
    est = info["estrategias"]["ruptura_robusta"]
    if not mt5.symbol_select(m, True):
        return None
    cerradas, tick = velas_broker(m)
    if not cerradas or not tick or not tick.bid:
        return None
    ind = L.preparar(cerradas)
    r = H.ruptura_robusta(cerradas, ind, len(cerradas) - 1, est["config"])
    if not r:
        return None
    direccion, dist, mult, vmax = r
    compra = direccion == "compra"
    entrada = tick.ask if compra else tick.bid
    stop = entrada - dist if compra else entrada + dist
    objetivo = entrada + (mult * dist if compra else -mult * dist)
    s = mt5.symbol_info(m)
    cuenta = mt5.account_info()
    tipo = mt5.ORDER_TYPE_BUY if compra else mt5.ORDER_TYPE_SELL
    perdida_lote = abs(mt5.order_calc_profit(tipo, m, 1.0, entrada, stop) or 0)   # en la moneda de la cuenta
    riesgo = cuenta.balance * RIESGO_PCT / 100
    lotes = 0.0
    if perdida_lote > 0:
        paso = s.volume_step or 0.01
        lotes = max(0.0, int(riesgo / perdida_lote / paso) * paso)
        lotes = min(lotes, s.volume_max)
    return {"activo": m, "nombre": est["nombre"], "direccion": direccion, "entrada": entrada, "stop": stop, "objetivo": objetivo,
            "rr": mult, "velas_max": vmax, "ts": cerradas[-1][0], "decimales": s.digits, "historico": est["prueba"],
            "lotes": round(lotes, 2), "riesgo": round(riesgo, 2), "moneda": cuenta.currency, "spread": round(tick.ask - tick.bid, s.digits)}


def avisar(x):
    d = lambda v: f"{v:.{x['decimales']}f}"
    h = x["historico"]
    titulo = f"{x['activo']} · {x['direccion'].upper()} · {x['nombre']}"
    cuerpo = (f"Precios de TU MetaTrader (MetaQuotes-Demo):\n"
              f"Entrada {d(x['entrada'])} · Stop {d(x['stop'])} · Objetivo {d(x['objetivo'])} · R:B 1:{x['rr']:g}\n"
              f"Lotes: {x['lotes']:.2f} (arriesgas {RIESGO_PCT:g}% = {x['riesgo']:,.2f} {x['moneda']}). Spread ahora: {d(x['spread'])}.\n".replace(",", "X").replace(".", ",").replace("X", ".")
              + f"En el periodo de prueba: {h['acierto']}% de acierto, {h['R_medio']:+.2f} R de media ({h['n']} operaciones).\n"
              f"Si no toca stop ni objetivo, cerrar en {x['velas_max']} h. Educativo, cuenta demo.")
    msg = {"topic": tema(), "title": titulo, "message": cuerpo, "priority": 4, "click": escaner.MESA,
           "tags": ["chart_with_upwards_trend" if x["direccion"] == "compra" else "chart_with_downwards_trend", "computer"]}
    urllib.request.urlopen(urllib.request.Request("https://ntfy.sh/", data=json.dumps(msg).encode("utf-8"),
                                                  headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}), timeout=20).close()


def pasada(prueba=False):
    if not mt5.initialize(path=TERMINAL, timeout=20000):
        log(f"MetaTrader no responde: {mt5.last_error()}")
        print("MetaTrader no responde:", mt5.last_error())
        return
    try:
        cuenta = mt5.account_info()
        if not cuenta:
            log("MetaTrader abierto pero sin sesión iniciada"); print("Sin sesión iniciada"); return
        cfg = H.config()
        for m in MERCADOS:
            x = analizar(m, cfg)
            if prueba:
                cerradas, tick = velas_broker(m)
                print(f"{m}: precio {tick.bid if tick else '?'} · última vela 1 h cerrada {dt.datetime.fromtimestamp(cerradas[-1][0]).strftime('%d/%m %H:%M') if cerradas else '?'} · señal: {x}")
                continue
            if not x or not escaner.en_horario():
                continue
            if ya_avisado(m, x["direccion"]):
                log(f"{m} {x['direccion']}: ya avisado en las últimas 6 h")
                continue
            avisar(x)
            log(f"AVISO {m} {x['direccion']} entrada {x['entrada']} stop {x['stop']} lotes {x['lotes']}")
        if not prueba:
            log(f"pasada hecha · cuenta {cuenta.login} · balance {cuenta.balance} {cuenta.currency}")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    pasada(prueba=sys.argv[1:] == ["prueba"])
