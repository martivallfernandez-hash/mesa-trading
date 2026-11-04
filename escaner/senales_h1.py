"""Señales en directo con las estrategias que ganaron en el laboratorio (velas de 1 hora).

Cada mercado usa SOLO la estrategia que ganó en entreno y en prueba (estrategias.json).
Se mira la última vela de 1 h cerrada; si da señal, se avisa una vez por vela.
"""
import datetime as dt
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import escaner      # noqa: E402
import laboratorio  # noqa: E402

UTC = dt.timezone.utc
# Cuenta demo del usuario: los lotes del aviso se calculan con esto
CUENTA = {"balance": 10000, "riesgo_pct": 1.0}
TAMANO_LOTE = {"XAUUSD": 100, "XAUEUR": 100}   # onzas por lote estándar en MetaTrader
MONEDA = {"XAUUSD": "USD", "XAUEUR": "EUR"}


def eurusd():
    try:
        d = escaner.get("https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X?interval=1h&range=1d")["chart"]["result"][0]
        return d["meta"]["regularMarketPrice"]
    except Exception:
        return 1.1


def lotes(s):
    """Lotes para arriesgar el % de la cuenta, en cuenta en USD y en cuenta en EUR (redondeado a la baja)."""
    m = s["activo"]
    if m not in TAMANO_LOTE:
        return None
    dist = abs(s["entrada"] - s["stop"])
    perdida_lote = dist * TAMANO_LOTE[m]          # en la moneda del precio (USD o EUR)
    tc = eurusd()
    perdida_usd = perdida_lote * (tc if MONEDA[m] == "EUR" else 1)
    perdida_eur = perdida_lote / (tc if MONEDA[m] == "USD" else 1)
    riesgo = CUENTA["balance"] * CUENTA["riesgo_pct"] / 100
    baja = lambda x: max(0.0, int(x * 100) / 100)
    return {"usd": baja(riesgo / perdida_usd), "eur": baja(riesgo / perdida_eur), "riesgo": riesgo}
DEC = {"EURUSD": 5, "GBPUSD": 5, "USDJPY": 3, "AUDUSD": 5, "AUDCAD": 5, "NZDCAD": 5, "XAUUSD": 2, "XAUEUR": 2, "BTCUSDT": 1, "ETHUSDT": 2}


def config():
    with open(os.path.join(escaner.CARPETA, "estrategias.json"), encoding="utf-8") as f:
        return json.load(f)


def velas_1h(m):
    """Últimos ~3 meses de velas de 1 h (suficiente para la media de 200)."""
    if m.endswith("USDT"):
        return laboratorio.binance_1h(m, dias=60)
    def yh(sym):
        d = escaner.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=60m&range=3mo")["chart"]["result"][0]
        q = d["indicators"]["quote"][0]
        return [(t, o, h, l, c) for t, o, h, l, c in zip(d["timestamp"], q["open"], q["high"], q["low"], q["close"]) if None not in (o, h, l, c)]
    if m == "XAUUSD":
        return yh("GC=F")
    if m == "XAUEUR":
        oro, eur = yh("GC=F"), {x[0]: x for x in yh("EURUSD=X")}
        out = []
        for t, o, h, l, c in oro:
            e = eur.get(t)
            if e:
                oo, cc = o / e[1], c / e[4]
                out.append((t, oo, max(oo, cc, h / e[4]), min(oo, cc, l / e[4]), cc))
        return out
    return yh(m + "=X")


def ruptura_robusta(v, ind, i, c):
    """Ruptura del canal de c['canal'] velas con filtro de la media de 200 (misma lógica que robustez.py)."""
    a, cierre, e200 = ind["atr"][i], ind["c"][i], ind["e200"][i]
    if a is None:
        return None
    n = c["canal"]
    alto, bajo = max(x[2] for x in v[i - n:i]), min(x[3] for x in v[i - n:i])
    if cierre > alto and (not c["filtro_200"] or cierre > e200):
        return ("compra", c["stop_atr"] * a, c["objetivo_R"], c["horas_max"])
    if cierre < bajo and (not c["filtro_200"] or cierre < e200):
        return ("venta", c["stop_atr"] * a, c["objetivo_R"], c["horas_max"])
    return None


def analizar(m, cfg=None):
    """Devuelve la señal de la última vela de 1 h cerrada con la estrategia elegida, o None."""
    cfg = cfg or config()
    info = cfg["mercados"].get(m) or {}
    clave = info.get("elegida")
    if not clave:
        return None
    est_info = info["estrategias"][clave]
    if clave == "ruptura_robusta":
        nombre, fn = est_info["nombre"], None
    else:
        nombre, fn = laboratorio.ESTRATEGIAS[clave]
    v = velas_1h(m)
    ahora = dt.datetime.now(UTC).timestamp()
    cerradas = [x for x in v if x[0] + 3600 <= ahora + 60]   # la vela en curso no cuenta
    if len(cerradas) < 220:
        return None
    ind = laboratorio.preparar(cerradas)
    i = len(cerradas) - 1
    precio = v[-1][4]                       # precio actual (entrada al momento)
    if fn is None:
        r = ruptura_robusta(cerradas, ind, i, est_info["config"])
        if not r:
            return None
        direccion, dist, mult, vmax = r
        stop = precio - dist if direccion == "compra" else precio + dist
    else:
        r = fn(cerradas, ind, i)
        if not r:
            return None
        direccion, stop, mult, vmax = r
    compra = direccion == "compra"
    riesgo = (precio - stop) if compra else (stop - precio)
    if riesgo <= 0:
        return None
    objetivo = precio + (mult * riesgo if compra else -mult * riesgo)
    est = est_info
    return {"activo": m, "estrategia": clave, "nombre": nombre, "direccion": direccion, "entrada": precio, "stop": stop,
            "objetivo": objetivo, "rr": mult, "velas_max": vmax, "ts": cerradas[-1][0], "decimales": DEC.get(m, 5),
            "historico": est["prueba"], "historico_todo": est["todo"]}


def avisar(s):
    d = lambda x: f"{x:.{s['decimales']}f}"
    h = s["historico"]
    titulo = f"{s['activo']} · {s['direccion'].upper()} · {s['nombre']}"
    lt = lotes(s)
    linea_lotes = (f"Lotes para arriesgar {CUENTA['riesgo_pct']:g}% de {CUENTA['balance']:,}".replace(",", ".") +
                   f": {lt['usd']:.2f} si tu cuenta es en USD · {lt['eur']:.2f} si es en EUR.\n") if lt else ""
    dist_stop, dist_obj = abs(s["entrada"] - s["stop"]), abs(s["objetivo"] - s["entrada"])
    arriba, abajo = ("por encima", "por debajo") if s["direccion"] == "compra" else ("por debajo", "por encima")
    fuente = "precios de tu MetaTrader" if s.get("fuente") == "mt5" else "datos de referencia, pueden diferir de tu broker"
    cuerpo = (f"Entra al precio de tu MetaTrader y pon:\n"
              f"• Stop {d(dist_stop)} {abajo} de tu entrada\n• Objetivo {d(dist_obj)} {arriba} de tu entrada (R:B 1:{s['rr']})\n"
              f"Niveles orientativos ({fuente}): entrada ~{d(s['entrada'])}, stop {d(s['stop'])}, objetivo {d(s['objetivo'])}.\n" + linea_lotes +
              f"Estrategia validada en 2 años de datos. En el periodo de prueba: {h['acierto']}% de acierto, {h['R_medio']:+.2f} R de media por operación ({h['n']} operaciones).\n"
              f"Si no toca stop ni objetivo, cerrar en {s['velas_max']} h. Compruébalo en tu gráfico. Educativo, cuenta demo.")
    # Publicación en JSON: así el título conserva acentos y símbolos (en una cabecera HTTP se estropean)
    mensaje = {"topic": escaner.tema_ntfy(), "title": titulo, "message": cuerpo, "priority": 4, "click": escaner.MESA,
               "tags": ["chart_with_upwards_trend" if s["direccion"] == "compra" else "chart_with_downwards_trend"]}
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(mensaje).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    urllib.request.urlopen(req, timeout=20).close()


def ya_avisado(m, direccion, horas=6):
    """¿Ya se avisó de este mercado y dirección en las últimas horas (p. ej. desde el puente de MetaTrader del PC)?"""
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{escaner.tema_ntfy()}/json?poll=1&since={horas}h",
                                                           headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
            titulos = [json.loads(x).get("title", "") for x in r.read().decode("utf-8").splitlines() if x.strip()]
        return any(t.startswith(f"{m} · {direccion.upper()} ·") for t in titulos)
    except Exception:
        return False


def escanea(ya_avisadas_ids, mercados_abiertos=()):
    """Revisa todos los mercados con estrategia; avisa de las señales nuevas. Devuelve la lista de nuevas."""
    cfg = config()
    nuevas = []
    for m, info in cfg["mercados"].items():
        if not info.get("elegida") or m in mercados_abiertos:
            continue   # como en el backtest: una operación a la vez por mercado
        try:
            s = analizar(m, cfg)
        except Exception as e:
            escaner.log(f"H1 error {m}: {e}")
            continue
        if not s:
            continue
        sid = f"{m}-{s['ts']}-{s['direccion']}"
        if sid in ya_avisadas_ids:
            continue
        s["id"] = sid
        if escaner.en_horario() and ya_avisado(m, s["direccion"]):
            escaner.log(f"H1 {m} {s['direccion']}: ya avisado desde tu MetaTrader; solo se registra")
        elif escaner.en_horario():
            try:
                avisar(s)
                escaner.log(f"AVISO H1 {m} {s['direccion']} {s['nombre']} entrada {s['entrada']}")
            except Exception as e:
                escaner.log(f"ERROR al avisar H1 {m}: {e}")
        nuevas.append(s)
    return nuevas


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = config()
    for m in cfg["mercados"]:
        try:
            print(m, analizar(m, cfg))
        except Exception as e:
            print(m, "error", e)
