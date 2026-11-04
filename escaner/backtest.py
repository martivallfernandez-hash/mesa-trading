"""Backtest del escáner: simula sus señales sobre el histórico y mide cuánto habrían acertado.

Uso:
  python -I escaner/backtest.py [dias=60] [salida.json]

Para cada vela de 15 min cerrada (L-V de 8:00 a 22:00, hora de Madrid) ejecuta el mismo análisis que en
directo, con los datos que había en ese momento. Si sale una señal, sigue las velas siguientes:
  - gana si toca el objetivo antes que el stop; pierde si toca el stop (si toca los dos en la misma vela,
    cuenta como pérdida, por prudencia); si en 12 h no toca ninguno, se cierra al precio de ese momento.
  - el resultado se mide en R (1 R = lo que arriesgas) y se le resta el spread típico de cada activo.
No repite la misma señal (activo y dirección) en 3 horas, igual que los avisos.
"""
import bisect
import json
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import escaner  # noqa: E402

# Spread típico en una cuenta minorista (en precio)
SPREAD = {"AUDCAD": 0.0002, "NZDCAD": 0.00025, "EURUSD": 0.00008, "GBPUSD": 0.00012, "USDJPY": 0.012,
          "AUDUSD": 0.0001, "XAUUSD": 0.30, "BTCUSDT": 15.0, "ETHUSDT": 1.2}
MAX_VELAS = 48       # 12 h en velas de 15 min
VENTANA = 480        # velas de 15 min que ve el análisis (5 días, como en directo)


def tramo(p):
    return "85-100" if p >= 85 else "70-84" if p >= 70 else "55-69" if p >= 55 else "<55"


def simular(activo, dias):
    orig = escaner.velas
    rng15 = "60d" if dias >= 30 else f"{dias}d"
    if activo.endswith("USDT"):
        v15, v1h = [], []
        fin = int(time.time() * 1000)
        for iv, dest, paso in (("15m", v15, 900), ("1h", v1h, 3600)):
            desde = fin - (dias + 7) * 86400 * 1000
            while desde < fin:
                k = escaner.get(f"https://data-api.binance.vision/api/v3/klines?symbol={activo}&interval={iv}&startTime={desde}&limit=1000")
                if not k:
                    break
                dest += [(escaner.dt.datetime.fromtimestamp(x[0] / 1000, escaner.dt.timezone.utc), *map(float, x[1:5])) for x in k]
                desde = k[-1][0] + paso * 1000
    else:
        sym = escaner.YAHOO.get(activo, activo + "=X")
        def yahoo(iv, rango):
            d = escaner.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={iv}&range={rango}")["chart"]["result"][0]
            q = d["indicators"]["quote"][0]
            return [(escaner.dt.datetime.fromtimestamp(t, escaner.dt.timezone.utc), o, h, l, c)
                    for t, o, h, l, c in zip(d["timestamp"], q["open"], q["high"], q["low"], q["close"]) if None not in (o, h, l, c)]
        v15, v1h = yahoo("15m", rng15), yahoo("60m", "6mo")
    t1h = [x[0] for x in v1h]
    operaciones, ultima = [], {}
    inicio = max(VENTANA // 2, len(v15) - dias * 96)
    for i in range(inicio, len(v15) - 1):
        t = v15[i][0]
        if not escaner.en_horario(t):
            continue
        # Solo lo que se sabía al cerrar la vela i: la vela «en curso» es una copia de su cierre,
        # y de 1 h solo las velas ya cerradas más una en curso con el precio de ese momento.
        cierre = v15[i][4]
        t_fin = t + escaner.dt.timedelta(minutes=15)
        c15 = v15[max(0, i - VENTANA):i + 1] + [(t_fin, cierre, cierre, cierre, cierre)]
        j = bisect.bisect_right(t1h, t_fin - escaner.dt.timedelta(hours=1))
        hora = t_fin.replace(minute=0, second=0, microsecond=0)
        c1h = v1h[max(0, j - 150):j] + [(hora, cierre, cierre, cierre, cierre)]
        if len(c1h) < 60 or len(c15) < 100:
            continue
        escaner.velas = lambda a, iv, a15=c15, a1h=c1h: a15 if iv == "15m" else a1h
        try:
            an = escaner.analizar(activo)
            s = an["senal"]
        except Exception:
            s = None
        finally:
            escaner.velas = orig
        if not s:
            continue
        clave = s["direccion"]
        if t.timestamp() - ultima.get(clave, 0) < 3 * 3600:
            continue
        ultima[clave] = t.timestamp()
        compra = s["direccion"] == "compra"
        entrada, stop, obj = s["entrada"], s["stop"], s["objetivo"]
        riesgo = abs(entrada - stop)
        futuras = v15[i + 1:i + 1 + MAX_VELAS]
        if not futuras:
            continue
        # Varias salidas posibles para la misma entrada: objetivo en la zona, o a 1, 1,5 y 2 veces el riesgo
        signo = 1 if compra else -1
        salidas = {"zona": obj, "1R": entrada + signo * riesgo, "1.5R": entrada + signo * 1.5 * riesgo, "2R": entrada + signo * 2 * riesgo}
        rs_var = {}
        for nombre, objv in salidas.items():
            res_v, sal_v = None, None
            for _, o, h, l, c in futuras:
                if (l <= stop) if compra else (h >= stop):
                    res_v, sal_v = "stop", stop; break
                if (h >= objv) if compra else (l <= objv):
                    res_v, sal_v = "objetivo", objv; break
            if res_v is None:
                sal_v = futuras[-1][4]
            rs_var[nombre] = round(((sal_v - entrada) if compra else (entrada - sal_v)) / riesgo - SPREAD.get(activo, 0) / riesgo, 3)
        resultado, salida = None, None
        for _, o, h, l, c in futuras:
            toca_stop = l <= stop if compra else h >= stop
            toca_obj = h >= obj if compra else l <= obj
            if toca_stop:
                resultado, salida = "stop", stop
                break
            if toca_obj:
                resultado, salida = "objetivo", obj
                break
        if resultado is None:
            if not futuras:
                continue
            resultado, salida = "tiempo", futuras[-1][4]
        r = ((salida - entrada) if compra else (entrada - salida)) / riesgo - SPREAD.get(activo, 0) / riesgo
        operaciones.append({"activo": activo, "ts": int(t.timestamp()), "direccion": s["direccion"], "puntos": s["puntos"],
                            "tramo": tramo(s["puntos"]), "flexible": "flexible" in s["motivo"],
                            "a_favor": (s["direccion"] == "compra" and an["tendencia_1h"] == "alcista") or (s["direccion"] == "venta" and an["tendencia_1h"] == "bajista"),
                            "contra": (s["direccion"] == "compra" and an["tendencia_1h"] == "bajista") or (s["direccion"] == "venta" and an["tendencia_1h"] == "alcista"),
                            "t15_igual": an["tendencia_15m"] == an["tendencia_1h"] and an["tendencia_1h"] != "lateral",
                            "hora": t.astimezone(escaner.MADRID).hour, "rr": s["rr"], "resultado": resultado, "R": round(r, 3), "R_var": rs_var})
    return operaciones


def resumen(ops):
    if not ops:
        return {"n": 0}
    gan = [o for o in ops if o["R"] > 0]
    rs = [o["R"] for o in ops]
    curva, pico, dd = 0, 0, 0
    for x in rs:
        curva += x; pico = max(pico, curva); dd = max(dd, pico - curva)
    pg, pp = sum(x for x in rs if x > 0), -sum(x for x in rs if x < 0)
    return {"n": len(ops), "acierto": round(len(gan) / len(ops) * 100, 1), "R_medio": round(sum(rs) / len(rs), 3),
            "R_total": round(sum(rs), 2), "factor": round(pg / pp, 2) if pp else None, "max_caida_R": round(dd, 2)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    dias = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    salida = sys.argv[2] if len(sys.argv) > 2 else os.path.join(escaner.CARPETA, "backtest.json")
    todas = []
    for activo in escaner.LISTA:
        t0 = time.time()
        try:
            ops = simular(activo, dias)
        except Exception as e:
            print(f"{activo}: error {e}", flush=True)
            continue
        todas += ops
        print(f"{activo}: {len(ops)} señales en {time.time() - t0:.0f} s · {resumen(ops)}", flush=True)
    por = defaultdict(list)
    for o in todas:
        por[(o["activo"], o["tramo"])].append(o)
        por[("TODOS", o["tramo"])].append(o)
        por[(o["activo"], "todas")].append(o)
        por[("TODOS", "todas")].append(o)
        por[("TODOS", "flexible" if o["flexible"] else "estricta")].append(o)
    tabla = {f"{a}|{t}": resumen(v) for (a, t), v in sorted(por.items())}
    with open(salida, "w", encoding="utf-8") as f:
        json.dump({"dias": dias, "generado": int(time.time()), "resumen": tabla, "operaciones": todas}, f, ensure_ascii=False)
    print("\nRESUMEN")
    for k, v in tabla.items():
        if k.startswith("TODOS") or k.endswith("|todas"):
            print(k, v)
