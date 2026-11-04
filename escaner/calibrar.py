"""Calibra el escáner con el backtest: qué activos avisan y desde qué puntuación.

Uso:  python -I escaner/calibrar.py backtest.json
Escribe escaner/calibracion.json, que leen el escáner (para filtrar y dar el histórico en cada aviso)
y la pestaña Señales de la Mesa.

Regla: para cada activo se prueba la puntuación mínima 55, 70 y 85. Se elige la más baja con la que
las señales habrían ganado de media al menos +0,05 R (spread incluido) con 20 señales o más.
Si ninguna lo cumple, el activo queda en pausa.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest import resumen  # noqa: E402

MIN_R, MIN_N = 0.05, 20

bt = json.load(open(sys.argv[1], encoding="utf-8"))
ops = bt["operaciones"]
salida = {"dias": bt["dias"], "generado": int(time.time()), "regla": f"R medio ≥ +{MIN_R} con {MIN_N}+ señales", "activos": {}}
for activo in sorted({o["activo"] for o in ops}):
    mias = [o for o in ops if o["activo"] == activo]
    datos = {"todas": resumen(mias), "activo": False, "min_puntos": None, "con_filtro": None}
    for umbral in (55, 70, 85):
        sub = [o for o in mias if o["puntos"] >= umbral]
        r = resumen(sub)
        datos[f"desde_{umbral}"] = r
        if not datos["activo"] and r["n"] >= MIN_N and r["R_medio"] >= MIN_R:
            datos.update(activo=True, min_puntos=umbral, con_filtro=r)
    salida["activos"][activo] = datos
ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibracion.json")
json.dump(salida, open(ruta, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
filtradas = [o for o in ops if salida["activos"][o["activo"]]["activo"] and o["puntos"] >= salida["activos"][o["activo"]]["min_puntos"]]
print("Sin filtro:", resumen(ops))
print("Con calibración:", resumen(filtradas))
for a, d in salida["activos"].items():
    print(f"{a:8} {'ACTIVO desde ' + str(d['min_puntos']) if d['activo'] else 'PAUSA':16} todas {d['todas']}  con filtro {d['con_filtro']}")
