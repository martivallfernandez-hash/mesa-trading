"""Busca la mejor combinación de reglas con el backtest, sin hacerse trampas.

Uso:  python -I escaner/optimizar.py backtest.json

Divide el histórico en dos: los 2/3 más antiguos para ELEGIR las reglas y el último 1/3 para
COMPROBARLAS (datos que el optimizador no ha visto). Solo se da por buena una combinación que gane
en las dos partes. Escribe escaner/estrategia.json con las reglas elegidas.
"""
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest import resumen  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
bt = json.load(open(sys.argv[1], encoding="utf-8"))
ops = [o for o in bt["operaciones"] if "R_var" in o]
ops.sort(key=lambda o: o["ts"])
corte = ops[int(len(ops) * 2 / 3)]["ts"]
entreno = [o for o in ops if o["ts"] < corte]
prueba = [o for o in ops if o["ts"] >= corte]

OPC = {
    "tendencia": ["cualquiera", "no_contra", "a_favor"],
    "tipo": ["todas", "estrictas"],
    "min_puntos": [0, 55, 70],
    "horas": ["8-22", "9-18", "14-18"],
    "salida": ["zona", "1R", "1.5R", "2R"],
    "alineado_15m": [False, True],
}


def pasa(o, r):
    if r["tendencia"] == "a_favor" and not o["a_favor"]:
        return False
    if r["tendencia"] == "no_contra" and o["contra"]:
        return False
    if r["tipo"] == "estrictas" and o["flexible"]:
        return False
    if o["puntos"] < r["min_puntos"]:
        return False
    h0, h1 = map(int, r["horas"].split("-"))
    if not h0 <= o["hora"] < h1:
        return False
    if r["alineado_15m"] and not o["t15_igual"]:
        return False
    return True


def evaluar(lista, r, activos=None):
    sel = [dict(o, R=o["R_var"][r["salida"]]) for o in lista if pasa(o, r) and (activos is None or o["activo"] in activos)]
    return resumen(sel), sel


resultados = []
for combo in itertools.product(*OPC.values()):
    r = dict(zip(OPC.keys(), combo))
    e, _ = evaluar(entreno, r)
    if e["n"] < 60:
        continue
    resultados.append((e["R_medio"], r, e))
resultados.sort(key=lambda x: -x[0])

print(f"Señales: {len(ops)} (entreno {len(entreno)}, prueba {len(prueba)})")
print("Sin filtros, salida en zona → entreno", evaluar(entreno, {"tendencia": "cualquiera", "tipo": "todas", "min_puntos": 0, "horas": "8-22", "salida": "zona", "alineado_15m": False})[0],
      "· prueba", evaluar(prueba, {"tendencia": "cualquiera", "tipo": "todas", "min_puntos": 0, "horas": "8-22", "salida": "zona", "alineado_15m": False})[0])
print("\nMEJORES 10 EN ENTRENO y cómo les va en PRUEBA:")
elegida = None
for rm, r, e in resultados[:10]:
    p, _ = evaluar(prueba, r)
    ok = p["n"] >= 20 and p["R_medio"] > 0
    print(("✔ " if ok else "✘ "), r, "| entreno", e, "| prueba", p)
    if ok and elegida is None:
        elegida = (r, e, p)

if not elegida:
    print("\nNinguna combinación gana también en la prueba: la estrategia no tiene ventaja clara.")
    sys.exit(0)

r, e, p = elegida
# Activos: se eligen SOLO con el entreno (los que no pierden con la regla elegida); la prueba los valida
por_activo = {}
for a in sorted({o["activo"] for o in ops}):
    te, _ = evaluar(entreno, r, {a})
    pe, _ = evaluar(prueba, r, {a})
    to, _ = evaluar(ops, r, {a})
    por_activo[a] = {"entreno": te, "prueba": pe, "todo": to, "activo": te["n"] >= 6 and te["R_medio"] > 0}
activos = {a for a, v in por_activo.items() if v["activo"]}
final_e, _ = evaluar(entreno, r, activos)
final_p, _ = evaluar(prueba, r, activos)
print("\nELEGIDA:", r)
print("Activos que se quedan:", sorted(activos))
print("Entreno:", final_e)
print("Prueba (no vista):", final_p)
json.dump({"reglas": r, "activos": por_activo, "entreno": final_e, "prueba": final_p, "dias": bt["dias"]},
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "estrategia.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
