"""Laboratorio de estrategias: prueba varias estrategias clásicas en velas de 1 hora y elige,
para cada mercado, la que gana también en datos que no ha visto.

Uso:  python -I escaner/laboratorio.py            (descarga ~2 años de velas de 1 h)
Escribe escaner/estrategias.json con la estrategia elegida por mercado y el ranking de mercados.

Reglas del juego (para no hacerse trampas):
- Entrada en la APERTURA de la vela siguiente a la señal (lo que podrías hacer de verdad).
- Si en una misma vela se tocan stop y objetivo, cuenta como stop.
- Se descuenta el spread típico de cada mercado.
- Los primeros 2/3 del histórico sirven para elegir; el último 1/3 solo para comprobar.
"""
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import escaner  # noqa: E402

MERCADOS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "AUDCAD", "NZDCAD", "XAUUSD", "XAUEUR", "BTCUSDT", "ETHUSDT"]
SPREAD = {"AUDCAD": 0.0002, "NZDCAD": 0.00025, "EURUSD": 0.00008, "GBPUSD": 0.00012, "USDJPY": 0.012,
          "AUDUSD": 0.0001, "XAUUSD": 0.30, "XAUEUR": 0.35, "BTCUSDT": 15.0, "ETHUSDT": 1.2}
UTC = dt.timezone.utc


# ---------------- Datos ----------------
def yahoo_1h(sym):
    d = escaner.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=60m&range=730d")["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    return [(t, o, h, l, c) for t, o, h, l, c in zip(d["timestamp"], q["open"], q["high"], q["low"], q["close"]) if None not in (o, h, l, c)]


def binance_1h(sym, dias=730):
    out, fin = [], int(time.time() * 1000)
    desde = fin - dias * 86400 * 1000
    while desde < fin:
        k = escaner.get(f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval=1h&startTime={desde}&limit=1000")
        if not k:
            break
        out += [(x[0] // 1000, *map(float, x[1:5])) for x in k]
        desde = k[-1][0] + 3600 * 1000
    return out


def cargar(m):
    if m.endswith("USDT"):
        return binance_1h(m)
    if m == "XAUUSD":
        return yahoo_1h("GC=F")
    if m == "XAUEUR":  # oro en euros = oro en dólares / EURUSD, vela a vela
        oro, eur = yahoo_1h("GC=F"), {x[0]: x for x in yahoo_1h("EURUSD=X")}
        out = []
        for t, o, h, l, c in oro:
            e = eur.get(t)
            if e:
                oo, cc = o / e[1], c / e[4]
                out.append((t, oo, max(oo, cc, h / e[4]), min(oo, cc, l / e[4]), cc))
        return out
    return yahoo_1h(m + "=X")


# ---------------- Indicadores ----------------
def ema(xs, n):
    k, out = 2 / (n + 1), []
    for x in xs:
        out.append(x if not out else x * k + out[-1] * (1 - k))
    return out


def atr_serie(v, n=14):
    out, a = [None], None
    for i in range(1, len(v)):
        tr = max(v[i][2] - v[i][3], abs(v[i][2] - v[i - 1][4]), abs(v[i][3] - v[i - 1][4]))
        a = tr if a is None else (a * (n - 1) + tr) / n
        out.append(a)
    return out


def rsi_serie(cs, n):
    out, ag, al = [None] * len(cs), 0.0, 0.0
    for i in range(1, len(cs)):
        d = cs[i] - cs[i - 1]
        g, p = max(d, 0), max(-d, 0)
        if i <= n:
            ag += g / n; al += p / n
            if i < n:
                continue
        else:
            ag, al = (ag * (n - 1) + g) / n, (al * (n - 1) + p) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def sma(xs, n, i):
    return sum(xs[i - n + 1:i + 1]) / n


def desv(xs, n, i):
    m = sma(xs, n, i)
    return (sum((x - m) ** 2 for x in xs[i - n + 1:i + 1]) / n) ** 0.5


def preparar(v):
    cs = [x[4] for x in v]
    return {"c": cs, "e20": ema(cs, 20), "e50": ema(cs, 50), "e200": ema(cs, 200), "atr": atr_serie(v),
            "rsi14": rsi_serie(cs, 14), "rsi2": rsi_serie(cs, 2)}


# ---------------- Estrategias ----------------
# Cada una mira la vela i ya cerrada y devuelve (dirección, stop, objetivo, velas_max) o None.
def tendencia_retroceso(v, ind, i):
    c, e20, e50, e200, a, r = ind["c"][i], ind["e20"][i], ind["e50"][i], ind["e200"][i], ind["atr"][i], ind["rsi14"]
    if None in (a, r[i], r[i - 1]):
        return None
    if e50 > e200 and c > e200 and min(x[3] for x in v[i - 3:i + 1]) <= e20 and r[i - 1] < 45 <= r[i]:
        stop = min(x[3] for x in v[i - 10:i + 1]) - 0.2 * a
        return ("compra", stop, 2.0, 48)
    if e50 < e200 and c < e200 and max(x[2] for x in v[i - 3:i + 1]) >= e20 and r[i - 1] > 55 >= r[i]:
        stop = max(x[2] for x in v[i - 10:i + 1]) + 0.2 * a
        return ("venta", stop, 2.0, 48)
    return None


def ruptura_canal(v, ind, i):
    a, c, e200 = ind["atr"][i], ind["c"][i], ind["e200"][i]
    if a is None:
        return None
    alto, bajo = max(x[2] for x in v[i - 20:i]), min(x[3] for x in v[i - 20:i])
    if c > alto and c > e200:
        return ("compra", c - 2 * a, 1.5, 72)
    if c < bajo and c < e200:
        return ("venta", c + 2 * a, 1.5, 72)
    return None


def ruptura_londres(v, ind, i):
    t = dt.datetime.fromtimestamp(v[i][0], UTC)
    if t.weekday() >= 5 or t.hour not in (7, 8, 9):
        return None
    dia = [x for x in v[max(0, i - 12):i + 1] if dt.datetime.fromtimestamp(x[0], UTC).date() == t.date()]
    asia = [x for x in dia if dt.datetime.fromtimestamp(x[0], UTC).hour < 7]
    if len(asia) < 5:
        return None
    alto, bajo = max(x[2] for x in asia), min(x[3] for x in asia)
    rango, c, prev = alto - bajo, ind["c"][i], ind["c"][i - 1]
    if rango <= 0 or (ind["atr"][i] and rango > 3 * ind["atr"][i] * 3):
        return None
    if c > alto and prev <= alto:
        return ("compra", (alto + bajo) / 2, 1.5, 10)
    if c < bajo and prev >= bajo:
        return ("venta", (alto + bajo) / 2, 1.5, 10)
    return None


def reversion_rsi2(v, ind, i):
    a, c, e200, r = ind["atr"][i], ind["c"][i], ind["e200"][i], ind["rsi2"][i]
    if None in (a, r):
        return None
    if c > e200 and r < 8:
        return ("compra", c - 2 * a, 1.0, 12)
    if c < e200 and r > 92:
        return ("venta", c + 2 * a, 1.0, 12)
    return None


def bollinger_lateral(v, ind, i):
    a, c = ind["atr"][i], ind["c"][i]
    if a is None:
        return None
    cs = ind["c"]
    pendiente = abs(ind["e50"][i] - ind["e50"][i - 20]) / a
    if pendiente > 1.0:   # solo en mercado lateral
        return None
    m, s = sma(cs, 20, i), desv(cs, 20, i)
    if c < m - 2 * s and cs[i - 1] >= m - 2 * s:
        return ("compra", c - 1.5 * a, 1.0, 24)
    if c > m + 2 * s and cs[i - 1] <= m + 2 * s:
        return ("venta", c + 1.5 * a, 1.0, 24)
    return None


ESTRATEGIAS = {
    "tendencia_retroceso": ("Tendencia + retroceso", tendencia_retroceso),
    "ruptura_canal": ("Ruptura de canal de 20 h", ruptura_canal),
    "ruptura_londres": ("Ruptura de Londres", ruptura_londres),
    "reversion_rsi2": ("Reversión con RSI(2)", reversion_rsi2),
    "bollinger_lateral": ("Rebote en Bollinger (lateral)", bollinger_lateral),
}


# ---------------- Simulación ----------------
def simular(v, ind, fn, spread):
    ops, ocupado_hasta = [], -1
    for i in range(210, len(v) - 1):
        if i <= ocupado_hasta:
            continue   # una operación a la vez por mercado
        s = fn(v, ind, i)
        if not s:
            continue
        direccion, stop, mult, vmax = s
        entrada = v[i + 1][1]             # apertura de la vela siguiente
        compra = direccion == "compra"
        riesgo = (entrada - stop) if compra else (stop - entrada)
        if riesgo <= 0 or riesgo < spread * 2:
            continue
        objetivo = entrada + (mult * riesgo if compra else -mult * riesgo)
        salida, j_fin = None, None
        for j in range(i + 1, min(len(v), i + 1 + vmax)):
            _, o, h, l, c = v[j]
            if (l <= stop) if compra else (h >= stop):
                salida, j_fin = stop, j; break
            if (h >= objetivo) if compra else (l <= objetivo):
                salida, j_fin = objetivo, j; break
        if salida is None:
            j_fin = min(len(v) - 1, i + vmax)
            salida = v[j_fin][4]
        r = (((salida - entrada) if compra else (entrada - salida)) - spread) / riesgo
        ops.append({"ts": v[i][0], "direccion": direccion, "R": round(r, 3)})
        ocupado_hasta = j_fin
    return ops


def resumen(ops):
    if not ops:
        return {"n": 0, "acierto": 0, "R_medio": 0, "R_total": 0, "factor": None, "max_caida_R": 0, "por_mes": 0}
    rs = [o["R"] for o in ops]
    curva = pico = dd = 0
    for x in rs:
        curva += x; pico = max(pico, curva); dd = max(dd, pico - curva)
    pg, pp = sum(x for x in rs if x > 0), -sum(x for x in rs if x < 0)
    meses = max(1, (ops[-1]["ts"] - ops[0]["ts"]) / (30 * 86400))
    return {"n": len(ops), "acierto": round(sum(x > 0 for x in rs) / len(rs) * 100, 1), "R_medio": round(sum(rs) / len(rs), 3),
            "R_total": round(sum(rs), 1), "factor": round(pg / pp, 2) if pp else None, "max_caida_R": round(dd, 1),
            "por_mes": round(len(ops) / meses, 1)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    resultado = {"generado": int(time.time()), "mercados": {}}
    for m in MERCADOS:
        try:
            v = cargar(m)
        except Exception as e:
            print(m, "error de datos:", e, flush=True)
            continue
        if len(v) < 1000:
            print(m, "pocos datos:", len(v)); continue
        ind = preparar(v)
        corte = v[int(len(v) * 2 / 3)][0]
        filas = {}
        for clave, (nombre, fn) in ESTRATEGIAS.items():
            ops = simular(v, ind, fn, SPREAD[m])
            ent, pru = [o for o in ops if o["ts"] < corte], [o for o in ops if o["ts"] >= corte]
            filas[clave] = {"nombre": nombre, "entreno": resumen(ent), "prueba": resumen(pru), "todo": resumen(ops)}
        # Elegida: la mejor en entreno que también gana en la prueba con muestra suficiente
        candidatas = [(k, f) for k, f in filas.items() if f["entreno"]["n"] >= 30 and f["entreno"]["R_medio"] > 0.05
                      and f["prueba"]["n"] >= 15 and f["prueba"]["R_medio"] > 0]
        candidatas.sort(key=lambda kf: -kf[1]["entreno"]["R_medio"])
        elegida = candidatas[0][0] if candidatas else None
        dias = (v[-1][0] - v[0][0]) / 86400
        resultado["mercados"][m] = {"dias": round(dias), "estrategias": filas, "elegida": elegida}
        print(f"\n{m} ({round(dias)} días de velas de 1 h)", flush=True)
        for k, f in filas.items():
            marca = "★" if k == elegida else " "
            print(f" {marca} {f['nombre']:32} entreno n={f['entreno']['n']:4} R={f['entreno']['R_medio']:+.3f} | prueba n={f['prueba']['n']:4} R={f['prueba']['R_medio']:+.3f} acierto={f['prueba']['acierto']}% factor={f['prueba']['factor']}")
    ranking = sorted(((m, d) for m, d in resultado["mercados"].items() if d["elegida"]),
                     key=lambda md: -md[1]["estrategias"][md[1]["elegida"]]["prueba"]["R_medio"])
    resultado["ranking"] = [m for m, _ in ranking]
    print("\nRANKING (por R medio en la prueba, datos no vistos):")
    for pos, (m, d) in enumerate(ranking, 1):
        f = d["estrategias"][d["elegida"]]
        print(f" {pos}. {m:8} {f['nombre']:32} prueba: {f['prueba']}")
    sin = [m for m, d in resultado["mercados"].items() if not d["elegida"]]
    print("Sin estrategia ganadora:", sin)
    json.dump(resultado, open(os.path.join(escaner.CARPETA, "estrategias.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
