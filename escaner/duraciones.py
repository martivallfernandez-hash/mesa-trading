"""Cuánto tardan en cerrarse las operaciones de la estrategia del oro (datos del backtest, sin inventar).

Uso:  python -I escaner/duraciones.py
Simula la configuración robusta de cada mercado sobre todo el histórico de velas de 1 h y mide, para cada
operación, las horas desde la entrada hasta que tocó el stop, el objetivo o el tiempo máximo.
Guarda el resumen en estrategias.json (estrategias.ruptura_robusta.duracion).
Nota: con velas de 1 h la duración se mide en horas enteras (una operación cerrada dentro de la primera
hora cuenta como 1 h); no hay más precisión que esa.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import laboratorio as L  # noqa: E402


def simular(v, ind, c, spread):
    ops, libre, n = [], 0, c["canal"]
    for i in range(max(210, n + 1), len(v) - 1):
        if i < libre:
            continue
        a, cierre, e200 = ind["atr"][i], ind["c"][i], ind["e200"][i]
        if a is None:
            continue
        alto, bajo = max(x[2] for x in v[i - n:i]), min(x[3] for x in v[i - n:i])
        if cierre > alto and (not c["filtro_200"] or cierre > e200):
            compra = True
        elif cierre < bajo and (not c["filtro_200"] or cierre < e200):
            compra = False
        else:
            continue
        entrada = v[i + 1][1]
        stop = entrada - c["stop_atr"] * a if compra else entrada + c["stop_atr"] * a
        riesgo = abs(entrada - stop)
        obj = entrada + (c["objetivo_R"] * riesgo if compra else -c["objetivo_R"] * riesgo)
        fin, motivo = None, "tiempo"
        for j in range(i + 1, min(len(v), i + 1 + c["horas_max"])):
            _, o, h, l, cc = v[j]
            if (l <= stop) if compra else (h >= stop):
                fin, motivo = j, "stop"; break
            if (h >= obj) if compra else (l <= obj):
                fin, motivo = j, "objetivo"; break
        if fin is None:
            fin = min(len(v) - 1, i + c["horas_max"])
        ops.append({"horas": fin - i, "motivo": motivo})
        libre = fin + 1
    return ops


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else None


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estrategias.json")
    est = json.load(open(ruta, encoding="utf-8"))
    for m in ("XAUUSD", "XAUEUR"):
        e = est["mercados"][m]["estrategias"].get("ruptura_robusta")
        if not e:
            continue
        v = L.cargar(m)
        ops = simular(v, L.preparar(v), e["config"], L.SPREAD[m])
        hs = [o["horas"] for o in ops]
        gan = [o["horas"] for o in ops if o["motivo"] == "objetivo"]
        per = [o["horas"] for o in ops if o["motivo"] == "stop"]
        dur = {"n": len(ops), "mediana": pct(hs, 50), "p25": pct(hs, 25), "p75": pct(hs, 75), "p90": pct(hs, 90),
               "objetivo_mediana": pct(gan, 50), "stop_mediana": pct(per, 50),
               "por_tiempo_pct": round(sum(o["motivo"] == "tiempo" for o in ops) / len(ops) * 100),
               "max_horas": e["config"]["horas_max"]}
        e["duracion"] = dur
        print(m, dur)
    json.dump(est, open(ruta, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
