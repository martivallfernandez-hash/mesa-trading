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


def analizar(m, cfg=None):
    """Devuelve la señal de la última vela de 1 h cerrada con la estrategia elegida, o None."""
    cfg = cfg or config()
    info = cfg["mercados"].get(m) or {}
    clave = info.get("elegida")
    if not clave:
        return None
    nombre, fn = laboratorio.ESTRATEGIAS[clave]
    v = velas_1h(m)
    ahora = dt.datetime.now(UTC).timestamp()
    cerradas = [x for x in v if x[0] + 3600 <= ahora + 60]   # la vela en curso no cuenta
    if len(cerradas) < 220:
        return None
    ind = laboratorio.preparar(cerradas)
    i = len(cerradas) - 1
    s = fn(cerradas, ind, i)
    if not s:
        return None
    direccion, stop, mult, vmax = s
    precio = v[-1][4]                       # precio actual (entrada al momento)
    compra = direccion == "compra"
    riesgo = (precio - stop) if compra else (stop - precio)
    if riesgo <= 0:
        return None
    objetivo = precio + (mult * riesgo if compra else -mult * riesgo)
    est = info["estrategias"][clave]
    return {"activo": m, "estrategia": clave, "nombre": nombre, "direccion": direccion, "entrada": precio, "stop": stop,
            "objetivo": objetivo, "rr": mult, "velas_max": vmax, "ts": cerradas[-1][0], "decimales": DEC.get(m, 5),
            "historico": est["prueba"], "historico_todo": est["todo"]}


def avisar(s):
    d = lambda x: f"{x:.{s['decimales']}f}"
    h = s["historico"]
    titulo = f"{s['activo']} · {s['direccion'].upper()} · {s['nombre']}"
    cuerpo = (f"Entrada ~{d(s['entrada'])} · Stop {d(s['stop'])} · Objetivo {d(s['objetivo'])} · R:B 1:{s['rr']}\n"
              f"Estrategia validada en 2 años de datos. En el periodo de prueba: {h['acierto']}% de acierto, {h['R_medio']:+.2f} R de media por operación ({h['n']} operaciones).\n"
              f"Si no toca stop ni objetivo, cerrar en {s['velas_max']} h. Compruébalo en tu gráfico. Educativo, cuenta demo.")
    req = urllib.request.Request(f"https://ntfy.sh/{escaner.tema_ntfy()}", data=cuerpo.encode("utf-8"), headers={
        "Title": titulo.encode("utf-8"), "Tags": "chart_with_upwards_trend" if s["direccion"] == "compra" else "chart_with_downwards_trend",
        "Priority": "high", "Click": escaner.MESA, "User-Agent": "Mozilla/5.0"})
    urllib.request.urlopen(req, timeout=20).close()


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
        if escaner.en_horario():
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
