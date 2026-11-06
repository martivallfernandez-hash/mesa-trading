"""Resumen de cada mañana: qué hizo el oro ayer, qué suele pasar en un día como hoy y cuándo tener cuidado.

Nada se inventa: cada probabilidad es la frecuencia con la que pasó en los últimos ~10 años de velas
diarias de Yahoo (futuros de oro GC=F; oro en euros = GC=F ÷ EURUSD), con el número de casos (n).
Una «secuencia» solo se cuenta como repetitiva si se aleja al menos 5 puntos del 50 % (o de lo normal)
y se mantiene en el mismo sentido en los 2 últimos años. Las horas de más o menos movimiento salen de
las velas de 1 h de los últimos 120 días. La agenda viene del calendario de Forex Factory y los
titulares de Google Noticias.

Uso:  python -I resumen_dia.py           imprime el resumen de hoy (sin enviarlo)
"""
import datetime as dt
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import escaner      # noqa: E402
import laboratorio  # noqa: E402
import senales_h1   # noqa: E402

UTC = dt.timezone.utc
MADRID = escaner.MADRID
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MERCADOS = ("XAUUSD", "XAUEUR")
UA = {"User-Agent": "Mozilla/5.0"}


# ---------------- Datos ----------------
def yahoo_diario(sym):
    d = escaner.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=10y")["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    out = {}
    for t, o, h, l, c in zip(d["timestamp"], q["open"], q["high"], q["low"], q["close"]):
        if None in (o, h, l, c):
            continue
        out[dt.datetime.fromtimestamp(t + 12 * 3600, UTC).date()] = (o, h, l, c)   # +12 h: fecha de la sesión
    return out


def es(x, dec=2):
    """Número en formato español: 4.113,50"""
    return f"{x:,.{dec}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def diario(m, hoy):
    """Velas diarias completas (sin la de hoy, que aún no ha cerrado): lista de (fecha, o, h, l, c)."""
    oro = yahoo_diario("GC=F")
    if m == "XAUEUR":
        eur = yahoo_diario("EURUSD=X")
        filas = []
        for f, (o, h, l, c) in sorted(oro.items()):
            e = eur.get(f)
            if e:
                oo, cc = o / e[0], c / e[3]
                filas.append((f, oo, max(oo, cc, h / e[3]), min(oo, cc, l / e[3]), cc))
    else:
        filas = [(f, *x) for f, x in sorted(oro.items())]
    return [x for x in filas if x[0] < hoy]


def leer(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return r.read()


def agenda_hoy(hoy):
    """Noticias de impacto alto/medio de USD y EUR hoy (hora de Madrid)."""
    ev = json.loads(leer("https://nfs.faireconomy.media/ff_calendar_thisweek.json"))
    out = []
    for e in ev:
        if e.get("country") not in ("USD", "EUR") or e.get("impact") not in ("High", "Medium"):
            continue
        try:
            t = dt.datetime.fromisoformat(e["date"]).astimezone(MADRID)
        except (KeyError, ValueError):
            continue
        if t.date() == hoy:
            out.append({"hora": t, "pais": e["country"], "impacto": e["impact"], "titulo": e["title"],
                        "previsto": e.get("forecast") or "", "anterior": e.get("previous") or ""})
    return sorted(out, key=lambda x: x["hora"])


def titulares(n=3):
    raiz = ET.fromstring(leer("https://news.google.com/rss/search?q=precio+del+oro+when:1d&hl=es&gl=ES&ceid=ES:es"))
    return [i.findtext("title") for i in raiz.iter("item")][:n]


# ---------------- Estadística ----------------
def frec(casos):
    """(probabilidad 0-100, n) de una lista de booleanos."""
    return (round(100 * sum(casos) / len(casos)), len(casos)) if casos else (None, 0)


def estadisticas(d, hoy):
    """Frecuencias históricas para el día de hoy dado lo que pasó ayer. d = velas diarias completas."""
    c = [x[4] for x in d]
    sube = [None] + [c[i] > c[i - 1] for i in range(1, len(d))]
    sma = [None] * len(d)
    for i in range(49, len(d)):
        sma[i] = sum(c[i - 49:i + 1]) / 50
    rango = [x[2] - x[3] for x in d]
    med20 = [None] * len(d)
    for i in range(20, len(d)):
        med20[i] = sorted(rango[i - 20:i])[10]
    hace2 = hoy - dt.timedelta(days=730)

    ult = len(d) - 1
    ayer_sube, encima = sube[ult], c[ult] > sma[ult]
    racha, k = 1, ult
    while k - 1 >= 1 and sube[k - 1] == ayer_sube:
        racha, k = racha + 1, k - 1
    ayer_movido = rango[ult] > 1.3 * med20[ult]

    def contar(cond, res, desde=None):
        """Frecuencia de res(i) en los días i cuyo día anterior cumple cond(i-1)."""
        return frec([res(i) for i in range(51, len(d)) if cond(i - 1) and (desde is None or d[i][0] >= desde)])

    def racha_en(j):
        r, k = 1, j
        while k - 1 >= 1 and sube[k - 1] == sube[j]:
            r, k = r + 1, k - 1
        return r

    base_sube = contar(lambda j: True, lambda i: sube[i])
    est = {
        "base_sube": base_sube,
        "cierre": contar(lambda j: sube[j] == ayer_sube and (c[j] > sma[j]) == encima, lambda i: sube[i]),
        "cierre_2a": contar(lambda j: sube[j] == ayer_sube and (c[j] > sma[j]) == encima, lambda i: sube[i], hace2),
        "rompe_max": contar(lambda j: sube[j] == ayer_sube, lambda i: d[i][2] > d[i - 1][2]),
        "rompe_min": contar(lambda j: sube[j] == ayer_sube, lambda i: d[i][3] < d[i - 1][3]),
        "ambos": contar(lambda j: sube[j] == ayer_sube, lambda i: d[i][2] > d[i - 1][2] and d[i][3] < d[i - 1][3]),
        "ninguno": contar(lambda j: sube[j] == ayer_sube, lambda i: d[i][2] <= d[i - 1][2] and d[i][3] >= d[i - 1][3]),
        "ayer_sube": ayer_sube, "encima_sma50": encima, "racha": racha, "ayer_movido": ayer_movido,
        "rango_tipico": med20[ult], "rango_ayer": rango[ult], "sma50": sma[ult],
    }
    # Candidatas a «secuencia que se repite»: (texto, prob, n, prob en 2 años, referencia)
    sec = []
    def cand(texto, cond, res, ref):
        p, n = contar(cond, res)
        p2, n2 = contar(cond, res, hace2)
        if p is not None and p2 is not None and n >= 80 and n2 >= 25:
            sec.append({"texto": texto, "p": p, "n": n, "p2": p2, "n2": n2, "ref": ref})
    dir_txt = "subir" if ayer_sube else "bajar"
    cand(f"Tras un día que {'sube' if ayer_sube else 'baja'}, al día siguiente vuelve a {dir_txt}",
         lambda j: sube[j] == ayer_sube, lambda i: sube[i] == ayer_sube, 50)
    if racha >= 2:
        cand(f"Tras {racha}+ días seguidos {'subiendo' if ayer_sube else 'bajando'}, sigue la racha",
             lambda j: sube[j] == ayer_sube and racha_en(j) >= racha, lambda i: sube[i] == ayer_sube, 50)
    dia = hoy.weekday()
    cand(f"Los {DIAS[dia]} el oro cierra al alza",
         lambda j: d[j + 1][0].weekday() == dia if j + 1 < len(d) else False, lambda i: sube[i], base_sube[0])
    if ayer_movido:
        cand("Tras un día muy movido (rango > 1,3× lo normal), hoy también se mueve más de lo normal",
             lambda j: med20[j] and rango[j] > 1.3 * med20[j], lambda i: rango[i] > med20[i], 50)
    else:
        cand("Tras un día tranquilo, hoy se mueve más de lo normal",
             lambda j: med20[j] and rango[j] <= 1.3 * med20[j], lambda i: rango[i] > med20[i], 50)
    cand(f"Con el precio {'por encima' if encima else 'por debajo'} de su media de 50 días, cierra al alza",
         lambda j: sma[j] and (c[j] > sma[j]) == encima, lambda i: sube[i], base_sube[0])
    for s in sec:   # repetitiva = se aleja 5+ puntos de lo normal y en los 2 últimos años va en el mismo sentido
        s["fiable"] = abs(s["p"] - s["ref"]) >= 5 and (s["p2"] - s["ref"]) * (s["p"] - s["ref"]) > 0 and abs(s["p2"] - s["ref"]) >= 3
    est["secuencias"] = sec
    return est


def perfil_horas(m="XAUUSD", dias=120):
    """Rango medio de las velas de 1 h por hora de Madrid (L-V), relativo a la media del día."""
    v = laboratorio.cargar(m)
    desde = v[-1][0] - dias * 86400
    por_hora = {}
    for t, o, h, l, c in v:
        if t < desde:
            continue
        mt = dt.datetime.fromtimestamp(t, MADRID)
        if mt.weekday() < 5:
            por_hora.setdefault(mt.hour, []).append(h - l)
    media = {hh: sum(x) / len(x) for hh, x in por_hora.items() if len(x) >= 30}
    total = sum(media.values()) / len(media)
    return {hh: media[hh] / total for hh in sorted(media)}


# ---------------- Texto ----------------
def etiqueta(p):
    if p is None:
        return ""
    if 45 <= p <= 55:
        return "≈ moneda al aire"
    if p >= 65 or p <= 35:
        return "bastante claro"
    return "ligera ventaja"


def franjas(perfil, desde=8, hasta=22):
    horas = [h for h in range(desde, hasta) if h in perfil]
    activas = sorted(horas, key=lambda h: -perfil[h])[:3]
    tranquilas = sorted(horas, key=lambda h: perfil[h])[:3]
    fmt = lambda hs: ", ".join(f"{h}:00–{h + 1}:00 (×{es(perfil[h], 1)})" for h in sorted(hs))
    return fmt(activas), fmt(tranquilas)


def generar(ahora=None, enviar_a=None):
    """Devuelve (título, texto) del resumen de hoy."""
    ahora = ahora or dt.datetime.now(UTC)
    madrid = ahora.astimezone(MADRID)
    hoy = madrid.date()
    L = []
    probs = {}
    for m in MERCADOS:
        try:
            d = diario(m, hoy)
            est = estadisticas(d, hoy)
        except Exception as e:
            L.append(f"{m}: sin datos ({str(e)[:60]})")
            continue
        cal = senales_h1.calibracion_broker(m)
        off = cal["yahoo"] if cal else 0.0
        sim = "$" if m == "XAUUSD" else "€"
        f = lambda x: es(x + off)
        fecha, o, h, l, c = d[-1]
        prev = d[-2][4]
        var = (c / prev - 1) * 100
        L.append(f"━━ {m} ━━")
        cuando = "Ayer" if fecha == hoy - dt.timedelta(days=1) else "Último día"
        L.append(f"📊 {cuando} ({DIAS[fecha.weekday()]} {fecha.day}/{fecha.month}): cerró {f(c)} ({'+' if var >= 0 else ''}{es(var)} %). "
                 f"Máx {f(h)} · mín {f(l)}. Se movió {h - l:.0f} {sim} ({es((h - l) / est['rango_tipico'], 1)}× lo normal).")
        tend = "por encima" if est["encima_sma50"] else "por debajo"
        L.append(f"Tendencia: precio {tend} de su media de 50 días ({f(est['sma50'])}); "
                 f"racha de {est['racha']} día{'s' if est['racha'] > 1 else ''} {'subiendo' if est['ayer_sube'] else 'bajando'}.")
        p, n = est["cierre"]
        p2, n2 = est["cierre_2a"]
        pm, nm = est["rompe_max"]
        pn, _ = est["rompe_min"]
        pa, _ = est["ambos"]
        pq, _ = est["ninguno"]
        L.append(f"🔮 Hoy (días parecidos en 10 años, n={nm}):")
        L.append(f"• Supera el máximo de ayer ({f(h)}): {pm}/100")
        L.append(f"• Pierde el mínimo de ayer ({f(l)}): {pn}/100")
        L.append(f"• Hace las dos cosas: {pa}/100 · ninguna (se queda dentro): {pq}/100")
        L.append(f"• Cierra más alto que ayer: {p}/100 (n={n}; últimos 2 años {p2}/100) → {etiqueta(p)}")
        L.append(f"• Movimiento típico del día: ~{est['rango_tipico']:.0f} {sim} entre máximo y mínimo")
        opciones = [(pm, f"supere el máximo de ayer ({pm}/100)"), (pn, f"pierda el mínimo de ayer ({pn}/100)"),
                    (pq, f"se quede dentro del rango de ayer ({pq}/100)")]
        mejor = max(opciones)
        dir_txt = ("al alza" if p > 50 else "a la baja") + f" ({max(p, 100 - p)}/100)"
        L.append(f"👉 Lo más probable: que {mejor[1]}. "
                 + ("Hacia dónde cierra: moneda al aire, no hay ventaja." if 45 <= p <= 55 else f"Cierre {dir_txt}, {etiqueta(p)}."))
        fiables = [s for s in est["secuencias"] if s["fiable"]]
        if fiables:
            L.append("🔁 Secuencias que se repiten:")
            for s in fiables:
                L.append(f"• {s['texto']}: {s['p']}/100 (n={s['n']}; 2 años: {s['p2']}/100)")
        else:
            L.append("🔁 Secuencias: ninguna fiable hoy (todas cerca de lo normal; no hay patrón que aprovechar).")
        probs[m] = {"max": pm, "min": pn, "cierre": p}
        if not cal:
            L.append(f"(Precios de futuros de referencia: pueden diferir unos {sim} de tu broker.)")
        L.append("")

    # Agenda y titulares
    try:
        lineas, cautela = bloque_agenda(hoy)
        L += lineas
        agenda_ok = True
    except Exception:
        cautela, agenda_ok = {}, False
        L.append("📰 Agenda: el calendario no responde ahora; te la envío en cuanto esté disponible.")
    try:
        tit = [f"• {t}" for t in titulares()]
    except Exception:
        tit = []
    pos_tit = len(L)
    L.append("")

    # Cuándo ser cauteloso o más activo
    try:
        activas, tranquilas = franjas(perfil_horas())
        L.append("⏰ Tu día por horas (movimiento del oro en los últimos 120 días, ×1 = normal):")
        L.append(f"🟢 Más activo: {activas}. Es cuando el oro más se mueve: atento a los avisos.")
        L.append(f"⚪ Tranquilo: {tranquilas}. El precio suele moverse poco: no fuerces entradas.")
    except Exception as e:
        L.append(f"⏰ Perfil por horas no disponible ({str(e)[:50]}).")
    if cautela:
        L.append(texto_cautela(cautela))
    if madrid.weekday() == 4:
        L.append("🔴 Viernes: desde las 21:00 no abras nada nuevo (cierre de fin de semana).")
    L.append("«Más activo» no es arriesgar más: máximo 150 € por operación.")
    titulo = f"☀️ {DIAS[madrid.weekday()].capitalize()} {hoy.day}/{hoy.month} · resumen del día"
    # Titulares solo si caben (ntfy corta a 4096 bytes)
    junto = lambda t: "\n".join(L[:pos_tit] + (["🗞 Titulares del oro:"] + t if t else []) + L[pos_tit:]).strip()
    while tit and len(junto(tit).encode("utf-8")) > 3900:
        tit.pop()
    return titulo, junto(tit)[:3900], agenda_ok


def bloque_agenda(hoy):
    """Líneas de la agenda de hoy y ventanas de cautela (±30 min de cada noticia roja). Lanza error si no hay calendario."""
    ag = agenda_hoy(hoy)
    cautela = {}
    if not ag:
        return ["📰 Agenda: sin noticias importantes de USD o EUR hoy."], cautela
    lineas = ["📰 Agenda de hoy (hora de Madrid):"]
    for e in ag:
        icono = "🔴" if e["impacto"] == "High" else "🟠"
        extra = f" (previsto {e['previsto']}, anterior {e['anterior']})" if e["previsto"] or e["anterior"] else ""
        lineas.append(f"{icono} {e['hora']:%H:%M} {e['pais']} · {e['titulo']}{extra}")
        if e["impacto"] == "High":
            ini, fin = e["hora"] - dt.timedelta(minutes=30), e["hora"] + dt.timedelta(minutes=30)
            cautela.setdefault(f"{ini:%H:%M}–{fin:%H:%M}", []).append(e["titulo"])
    return lineas, cautela


def texto_cautela(cautela):
    ventanas = "; ".join(f"{k} ({', '.join(v)})" for k, v in cautela.items())
    return f"🔴 Cauteloso: {ventanas}. No abras justo antes de una noticia roja: el precio puede saltar tu stop."


def mensaje_agenda(hoy):
    """Mensaje aparte con la agenda cuando no estaba disponible a primera hora."""
    lineas, cautela = bloque_agenda(hoy)
    if cautela:
        lineas.append(texto_cautela(cautela))
    return "📰 Agenda de hoy · noticias que mueven el oro", "\n".join(lineas)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    t, txt, _ = generar()
    print(t)
    print(txt)
    print(f"\n[{len(txt.encode('utf-8'))} bytes]")
