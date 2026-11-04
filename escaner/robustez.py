"""Prueba de solidez de la ruptura de canal en el oro.

Uso:  python -I escaner/robustez.py
Prueba muchas variantes (canal, stop, objetivo, filtro de tendencia, tiempo máximo y mover el stop a
la entrada al ir +1 R a favor). Una ventaja real no depende de un número exacto: los vecinos de una
buena configuración también deben ganar. Por eso se elige la configuración cuyo VECINDARIO gana más
en el entreno (meseta), no la mejor suelta, y después se comprueba en la prueba (datos no vistos).
Escribe escaner/robustez.json.
"""
import itertools
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import laboratorio as L  # noqa: E402

REJILLA = {
    "canal": [10, 15, 20, 30, 40],
    "stop_atr": [1.5, 2.0, 2.5, 3.0],
    "objetivo_R": [1.0, 1.5, 2.0, 3.0],
    "filtro_200": [True, False],
    "horas_max": [48, 72, 120],
    "a_entrada": [False, True],     # mover el stop a la entrada al llegar a +1 R
}


def simular(v, ind, cfg, spread):
    n, sa, mult, filtro, vmax, be = cfg["canal"], cfg["stop_atr"], cfg["objetivo_R"], cfg["filtro_200"], cfg["horas_max"], cfg["a_entrada"]
    ops, libre = [], 0
    for i in range(max(210, n + 1), len(v) - 1):
        if i < libre:
            continue
        a, c, e200 = ind["atr"][i], ind["c"][i], ind["e200"][i]
        if a is None:
            continue
        alto, bajo = max(x[2] for x in v[i - n:i]), min(x[3] for x in v[i - n:i])
        if c > alto and (not filtro or c > e200):
            compra = True
        elif c < bajo and (not filtro or c < e200):
            compra = False
        else:
            continue
        entrada = v[i + 1][1]
        stop = entrada - sa * a if compra else entrada + sa * a
        riesgo = abs(entrada - stop)
        objetivo = entrada + (mult * riesgo if compra else -mult * riesgo)
        salida, fin = None, None
        for j in range(i + 1, min(len(v), i + 1 + vmax)):
            _, o, h, l, cc = v[j]
            if (l <= stop) if compra else (h >= stop):
                salida, fin = stop, j; break
            if (h >= objetivo) if compra else (l <= objetivo):
                salida, fin = objetivo, j; break
            if be and ((h >= entrada + riesgo) if compra else (l <= entrada - riesgo)):
                stop = entrada   # a partir de la vela siguiente
        if salida is None:
            fin = min(len(v) - 1, i + vmax); salida = v[fin][4]
        r = (((salida - entrada) if compra else (entrada - salida)) - spread) / riesgo
        ops.append({"ts": v[i][0], "R": round(r, 3)})
        libre = fin + 1
    return ops


def vecinos(cfg):
    """Configuraciones que cambian un solo parámetro un paso arriba o abajo."""
    out = []
    for k, vals in REJILLA.items():
        idx = vals.index(cfg[k])
        for d in (-1, 1):
            if 0 <= idx + d < len(vals):
                out.append(tuple(sorted({**cfg, k: vals[idx + d]}.items())))
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    salida = {"generado": int(time.time()), "mercados": {}}
    for m in ("XAUUSD", "XAUEUR"):
        t0 = time.time()
        v = L.cargar(m)
        ind = L.preparar(v)
        corte = v[int(len(v) * 2 / 3)][0]
        res = {}
        for combo in itertools.product(*REJILLA.values()):
            cfg = dict(zip(REJILLA, combo))
            ops = simular(v, ind, cfg, L.SPREAD[m])
            ent, pru = [o for o in ops if o["ts"] < corte], [o for o in ops if o["ts"] >= corte]
            res[tuple(sorted(cfg.items()))] = (L.resumen(ent), L.resumen(pru), L.resumen(ops))
        validas = {k: x for k, x in res.items() if x[0]["n"] >= 60}
        # Meseta: media del R del entreno de la configuración y sus vecinos
        def meseta(k):
            vs = [res[n][0]["R_medio"] for n in vecinos(dict(k)) if n in res and res[n][0]["n"] >= 40]
            return (res[k][0]["R_medio"] + sum(vs)) / (1 + len(vs))
        orden = sorted(validas, key=lambda k: -meseta(k))
        mejor = orden[0]
        ent, pru, todo = res[mejor]
        positivas_ent = sum(1 for x in validas.values() if x[0]["R_medio"] > 0) / len(validas)
        positivas_pru = sum(1 for x in validas.values() if x[1]["R_medio"] > 0) / len(validas)
        vec = [res[n] for n in vecinos(dict(mejor)) if n in res]
        vec_pru_pos = sum(1 for x in vec if x[1]["R_medio"] > 0) / max(1, len(vec))
        original = tuple(sorted({"canal": 20, "stop_atr": 2.0, "objetivo_R": 1.5, "filtro_200": True, "horas_max": 72, "a_entrada": False}.items()))
        salida["mercados"][m] = {
            "elegida": dict(mejor), "entreno": ent, "prueba": pru, "todo": todo, "meseta_entreno": round(meseta(mejor), 3),
            "vecinos_ganan_en_prueba": round(vec_pru_pos * 100), "variantes": len(validas),
            "variantes_ganan_entreno": round(positivas_ent * 100), "variantes_ganan_prueba": round(positivas_pru * 100),
            "original": {"entreno": res[original][0], "prueba": res[original][1]},
            "top5": [{"cfg": dict(k), "meseta": round(meseta(k), 3), "entreno": res[k][0], "prueba": res[k][1]} for k in orden[:5]],
        }
        print(f"\n{m}: {len(validas)} variantes en {time.time() - t0:.0f} s")
        print(f"  Variantes que ganan: {round(positivas_ent*100)} % en entreno, {round(positivas_pru*100)} % en prueba")
        print(f"  Original (20/2.0/1.5R): entreno {res[original][0]['R_medio']:+.3f} · prueba {res[original][1]['R_medio']:+.3f}")
        print(f"  ELEGIDA por meseta: {dict(mejor)}")
        print(f"    entreno {ent}\n    prueba  {pru}\n    vecinos que ganan en prueba: {round(vec_pru_pos*100)} %")
        for t in salida["mercados"][m]["top5"][1:]:
            print(f"    otra: {t['cfg']} → prueba R {t['prueba']['R_medio']:+.3f} (n={t['prueba']['n']})")
    json.dump(salida, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "robustez.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
