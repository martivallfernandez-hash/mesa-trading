"""Mensajes de estado: cuándo NO operar y cuándo puede haber una oportunidad.

Todo sale de la estrategia validada (estrategias.json) y de los precios del momento; nada se inventa:
  - Resumen de la mañana (L-V, primera vuelta tras las 8:00): divisas sin ventaja → no operar;
    oro → precio exacto al que se activaría la compra o la venta.
  - «Atención»: el oro está a menos de 0,3 ATR del precio que activaría una señal (una vez cada 6 h).
  - «Operación cerrada → no operar en ese mercado hasta nuevo aviso» cuando una señal registrada se cierra.
  - Viernes desde las 21:00: fin de semana, no operar hasta el lunes.
El estado (qué se ha avisado ya) se guarda en la rama «datos» como estado.json.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import escaner      # noqa: E402
import laboratorio  # noqa: E402
import senales_h1   # noqa: E402
import resumen_dia  # noqa: E402

CERCA_ATR = 0.3


def enviar(titulo, cuerpo, prioridad=3, tags=("information_source",)):
    msg = {"topic": escaner.tema_ntfy(), "title": titulo, "message": cuerpo, "priority": prioridad,
           "click": escaner.MESA, "tags": list(tags)}
    urllib.request.urlopen(urllib.request.Request("https://ntfy.sh/", data=json.dumps(msg).encode("utf-8"),
                                                  headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}), timeout=20).close()


def niveles(m, cfg):
    """Precio actual y precios que activarían compra/venta en la próxima vela de 1 h (estrategia robusta)."""
    e = cfg["mercados"][m]["estrategias"].get("ruptura_robusta")
    if not e:
        return None
    c = e["config"]
    v = senales_h1.velas_1h(m)
    ahora = time.time()
    cerradas = [x for x in v if x[0] + 3600 <= ahora + 60]
    if len(cerradas) < 220:
        return None
    ind = laboratorio.preparar(cerradas)
    n = c["canal"]
    # La próxima vela se compara con el canal de las últimas n velas cerradas
    alto, bajo = max(x[2] for x in cerradas[-n:]), min(x[3] for x in cerradas[-n:])
    precio, e200, atr = v[-1][4], ind["e200"][-1], ind["atr"][-1]
    compra_ok = not c["filtro_200"] or precio > e200
    venta_ok = not c["filtro_200"] or precio < e200
    cal = senales_h1.calibracion_broker(m)
    off = cal["yahoo"] if cal else 0.0
    return {"precio": precio, "alto": alto, "bajo": bajo, "atr": atr, "e200": e200, "compra_ok": compra_ok,
            "venta_ok": venta_ok, "off": off, "calibrado": bool(cal), "dec": senales_h1.DEC.get(m, 2), "canal": n}


def texto_niveles(m, x):
    d = lambda v: f"{v + x['off']:.{x['dec']}f}"
    fuente = "ajustado a tu broker" if x["calibrado"] else "precio de referencia, puede diferir unos $ de tu broker"
    partes = [f"{m} ahora ~{d(x['precio'])} ({fuente})."]
    if x["compra_ok"]:
        partes.append(f"Posible COMPRA solo si una vela de 1 h CIERRA por encima de {d(x['alto'])} (máximo de las últimas {x['canal']} h).")
    if x["venta_ok"]:
        partes.append(f"Posible VENTA solo si una vela de 1 h CIERRA por debajo de {d(x['bajo'])} (mínimo de las últimas {x['canal']} h).")
    if not (x["compra_ok"] or x["venta_ok"]):
        partes.append("Ninguna dirección permitida ahora mismo.")
    return " ".join(partes)


def revisar(senales, estado, cfg=None):
    """Una pasada: decide qué mensajes de estado tocan y los envía. Modifica `estado`."""
    cfg = cfg or senales_h1.config()
    madrid = dt.datetime.now(dt.timezone.utc).astimezone(escaner.MADRID)
    hoy = madrid.strftime("%Y-%m-%d")
    activos = [m for m, d in cfg["mercados"].items() if d.get("elegida")]
    sin_ventaja = [m for m, d in cfg["mercados"].items() if not d.get("elegida")]
    abiertas = {s["activo"] for s in senales if s["estado"] == "abierta"}
    enviados = []

    # 0) Resumen del día: ayer, probabilidades de hoy, agenda y horas de cautela (una vez al día, L-V)
    if madrid.weekday() < 5 and madrid.hour >= 8 and estado.get("resumen_dia") != hoy and time.time() - estado.get("resumen_intento", 0) > 900:
        estado["resumen_intento"] = time.time()
        try:
            titulo, texto, agenda_ok = resumen_dia.generar()
            enviar(titulo, texto, 3, ("sunny",))
            estado["resumen_dia"] = hoy
            estado["resumen_texto"] = {"fecha": hoy, "titulo": titulo, "texto": texto}
            if not agenda_ok:
                estado["agenda_pendiente"] = hoy
            enviados.append("resumen_dia")
        except Exception as e:
            print("Error en el resumen del día:", e)
    if estado.get("agenda_pendiente") == hoy and madrid.hour < 15 and time.time() - estado.get("agenda_intento", 0) > 900:
        estado["agenda_intento"] = time.time()
        try:
            titulo, texto = resumen_dia.mensaje_agenda(madrid.date())
            enviar(titulo, texto, 3, ("newspaper",))
            estado.pop("agenda_pendiente", None)
            if estado.get("resumen_texto", {}).get("fecha") == hoy:
                estado["resumen_texto"]["texto"] += "\n\n" + texto
            enviados.append("agenda")
        except Exception as e:
            print("Agenda aún no disponible:", e)

    # 1) Qué operar y qué no (una vez al día, L-V)
    if madrid.weekday() < 5 and madrid.hour >= 8 and estado.get("resumen") != hoy:
        lineas = [f"🛑 Divisas: NO OPERAR ({', '.join(sin_ventaja)}). Ninguna estrategia ha demostrado ganar en ellas tras 2 años de pruebas."]
        for m in activos:
            if m in abiertas:
                lineas.append(f"📈 {m}: tienes una señal abierta; sigue su stop y objetivo.")
                continue
            x = niveles(m, cfg)
            lineas.append(f"⏳ {m}: esperar. " + (texto_niveles(m, x) if x else "Sin datos ahora."))
        lineas.append(f"Recuerda: máximo 150 € de pérdida por operación.")
        enviar("🎯 Hoy · qué operar y qué no", "\n".join(lineas), 3, ("sunny",))
        estado["resumen"] = hoy
        enviados.append("resumen")

    # 2) Atención: el oro se acerca al precio que activaría una señal
    for m in activos:
        if m in abiertas:
            continue
        x = niveles(m, cfg)
        if not x:
            continue
        for direccion, nivel, ok in (("compra", x["alto"], x["compra_ok"]), ("venta", x["bajo"], x["venta_ok"])):
            dist = (nivel - x["precio"]) if direccion == "compra" else (x["precio"] - nivel)
            clave = f"cerca-{m}-{direccion}"
            if ok and 0 < dist <= CERCA_ATR * x["atr"] and time.time() - estado.get(clave, 0) > 6 * 3600:
                d = lambda v: f"{v + x['off']:.{x['dec']}f}"
                enviar(f"👀 {m} · atención, posible {direccion.upper()} pronto",
                       f"Está a {dist:.{x['dec']}f} del precio que activaría la señal.\n"
                       f"{'COMPRA' if direccion == 'compra' else 'VENTA'} solo si una vela de 1 h CIERRA {'por encima' if direccion == 'compra' else 'por debajo'} de {d(nivel)}.\n"
                       "Todavía NO es una entrada: espera al aviso de señal.", 3, ("eyes",))
                estado[clave] = time.time()
                enviados.append(clave)

    # 3) Operaciones cerradas → no operar en ese mercado hasta nuevo aviso
    avisadas = set(estado.get("cierres", []))
    for s in senales:
        if s["estado"] != "abierta" and s["id"] not in avisadas and s.get("cierre_ts") and time.time() - s["cierre_ts"] < 48 * 3600:
            txt = {"objetivo": "✅ tocó el OBJETIVO", "stop": "❌ tocó el STOP", "tiempo": "⏱ pasó su tiempo máximo"}[s["estado"]]
            enviar(f"🛑 {s['activo']} · operación cerrada · no operar hasta nuevo aviso",
                   f"La señal de {s['direccion']} {txt} ({s['R']:+.2f} R).\n"
                   f"Si sigues dentro, ciérrala. No abras otra en {s['activo']} hasta el próximo aviso de señal.", 3, ("octagonal_sign",))
            avisadas.add(s["id"])
            enviados.append(f"cierre-{s['id']}")
    estado["cierres"] = sorted(avisadas)[-200:]

    # 4) Fin de semana
    semana = madrid.strftime("%G-%V")
    if madrid.weekday() == 4 and madrid.hour >= 21 and estado.get("finde") != semana:
        enviar("🛑 Fin de semana · no operar hasta el lunes",
               "El mercado cierra el viernes por la noche y puede abrir el lunes con un salto que se salte tu stop. "
               "No abras operaciones nuevas hasta el lunes a partir de las 8:00." +
               (f"\nTienes señales abiertas en {', '.join(sorted(abiertas))}: decide si las mantienes con su stop puesto." if abiertas else ""),
               3, ("octagonal_sign",))
        estado["finde"] = semana
        enviados.append("finde")
    return enviados


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = senales_h1.config()
    for m in [m for m, d in cfg["mercados"].items() if d.get("elegida")]:
        x = niveles(m, cfg)
        print(m, texto_niveles(m, x) if x else None)
