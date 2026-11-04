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


# ---------- Autocalibración: diferencia entre tu broker y las fuentes de la nube ----------
KRAKEN = {"XAUUSD": "PAXGUSD", "XAUEUR": "PAXGEUR"}
CALIB_LOCAL = os.path.join(os.path.expanduser("~"), ".claude", "trading", "calibracion_precio.json")


def kraken_mid(par):
    d = escaner.get(f"https://api.kraken.com/0/public/Ticker?pair={par}")["result"]
    t = next(iter(d.values()))
    return (float(t["a"][0]) + float(t["b"][0])) / 2


def calibrar():
    """Mide broker - Yahoo (avisos de la nube) y broker - Kraken (gráfico de la Mesa) y guarda un historial."""
    try:
        with open(CALIB_LOCAL, encoding="utf-8") as f:
            hist = json.load(f)
    except (OSError, ValueError):
        hist = {"mercados": {}, "publicado": 0}
    ahora = int(time.time())
    for m in MERCADOS:
        tick = mt5.symbol_info_tick(m)
        if not tick or not tick.bid:
            continue
        h0 = hist["mercados"].setdefault(m, {"medidas": []})
        quieto = h0.get("ultimo_tick") == tick.time_msc   # mismo tick que hace 5 min: mercado parado (pausa o cierre)
        h0["ultimo_tick"] = tick.time_msc
        if quieto or "ultimo_tick_visto" not in h0:
            h0["ultimo_tick_visto"] = True
            continue                                       # solo se mide con el precio moviéndose
        broker = (tick.bid + tick.ask) / 2
        try:
            yahoo = H.velas_1h(m)[-1][4]
            kraken = kraken_mid(KRAKEN[m])
        except Exception as e:
            log(f"calibración {m}: sin fuente ({e})"); continue
        h = hist["mercados"].setdefault(m, {"medidas": []})
        h["medidas"] = (h["medidas"] + [[ahora, round(broker - yahoo, 3), round(broker - kraken, 3)]])[-60:]
        ult = [x for x in h["medidas"] if ahora - x[0] < 6 * 3600] or h["medidas"][-1:]
        med = lambda i: sorted(x[i] for x in ult)[len(ult) // 2]
        dispersion = lambda i: round(max(x[i] for x in ult) - min(x[i] for x in ult), 2)
        h.update({"actualizado": ahora, "broker": round(broker, 3), "yahoo": round(med(1), 3), "kraken": round(med(2), 3),
                  "rango_yahoo": dispersion(1), "rango_kraken": dispersion(2), "n": len(ult)})
    with open(CALIB_LOCAL, "w", encoding="utf-8") as f:
        json.dump(hist, f)
    # Publicar en la rama «calibracion» cada 30 min (la leen la nube y la Mesa)
    if ahora - hist.get("publicado", 0) >= 1800 and hist["mercados"]:
        publicar_calibracion({"generado": ahora, "mercados": {m: {k: v for k, v in h.items() if k not in ("medidas", "ultimo_tick", "ultimo_tick_visto")}
                                                             for m, h in hist["mercados"].items() if h.get("n")}})
        hist["publicado"] = ahora
        with open(CALIB_LOCAL, "w", encoding="utf-8") as f:
            json.dump(hist, f)


def publicar_calibracion(datos):
    import subprocess, tempfile
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "calibracion.json"), "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)
        git = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        git("init", "-q", "-b", "calibracion")
        git("add", "calibracion.json")
        git("-c", "user.name=puente-mt5", "-c", "user.email=puente@users.noreply.github.com", "commit", "-q", "-m", "Calibración de precios")
        git("push", "-q", "-f", "https://github.com/martivallfernandez-hash/mesa-trading.git", "calibracion")
    log("calibración publicada: " + ", ".join(f"{m} {v['yahoo']:+.2f}/{v['kraken']:+.2f}" for m, v in datos["mercados"].items()))


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
        try:
            calibrar()
        except Exception as e:
            log(f"error de calibración: {e}")
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
