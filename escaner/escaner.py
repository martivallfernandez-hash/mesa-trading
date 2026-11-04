"""Escáner de oportunidades intradía para forex, oro y cripto (solo librería estándar).

Uso:
  python -I escaner.py analiza AUDCAD        Estudio del día de un activo: tendencia, zonas,
                                               mejor zona de compra y de venta, señal activa.
  python -I escaner.py escanea [--json]       Revisa toda la lista y muestra solo señales nuevas
                                               (no repite la misma señal en 3 horas).
  python -I escaner.py escanea --todas        Igual, pero sin filtrar repetidas.
  pythonw -I escaner.py escanea --avisar      Modo automático: si hay señales nuevas las manda al
                                               móvil por ntfy (tema en config.json) y lo apunta en escaner.log.

Datos: Yahoo Finance (forex y oro, velas de 15 min y 1 h, casi en tiempo real) y Binance (cripto).
Los niveles son orientativos: el precio exacto es el de tu broker. Herramienta educativa.
"""
import datetime as dt
import json
import os
import sys
import urllib.request

LISTA = ["AUDCAD", "NZDCAD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "BTCUSDT", "ETHUSDT"]
YAHOO = {"XAUUSD": "GC=F"}
ESTADO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "senales_enviadas.json")
UMBRAL = 70        # señal fuerte
UMBRAL_DEBIL = 55  # señal débil: se avisa, marcada como de poca relevancia
DEBIL = "poca relevancia"
UA = {"User-Agent": "Mozilla/5.0"}
try:
    from zoneinfo import ZoneInfo
    MADRID = ZoneInfo("Europe/Madrid")
except Exception:  # Windows sin base de zonas horarias: hora de invierno de España
    MADRID = dt.timezone(dt.timedelta(hours=1))


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return json.load(r)


def velas(activo, intervalo):
    """Devuelve [(datetime_utc, o, h, l, c)] de las últimas velas cerradas y la actual."""
    if activo.endswith("USDT"):
        iv = {"5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h"}[intervalo]
        k = get(f"https://data-api.binance.vision/api/v3/klines?symbol={activo}&interval={iv}&limit=300")
        return [(dt.datetime.fromtimestamp(x[0] / 1000, dt.timezone.utc), *map(float, x[1:5])) for x in k]
    sym = YAHOO.get(activo, activo + "=X")
    rng = {"5m": "5d", "15m": "5d", "30m": "1mo", "1h": "1mo"}[intervalo]
    yi = {"5m": "5m", "15m": "15m", "30m": "30m", "1h": "60m"}[intervalo]
    d = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={yi}&range={rng}")["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    out = []
    for t, o, h, l, c in zip(d["timestamp"], q["open"], q["high"], q["low"], q["close"]):
        if None not in (o, h, l, c):
            out.append((dt.datetime.fromtimestamp(t, dt.timezone.utc), o, h, l, c))
    return out


def ema(xs, n):
    k, out = 2 / (n + 1), []
    for x in xs:
        out.append(x if not out else x * k + out[-1] * (1 - k))
    return out


def atr(v, n=14):
    trs = [max(h - l, abs(h - v[i - 1][4]), abs(l - v[i - 1][4])) for i, (_, _, h, l, _) in enumerate(v) if i]
    a = sum(trs[:n]) / n
    for t in trs[n:]:
        a = (a * (n - 1) + t) / n
    return a


def rsi(cs, n=14):
    g = [max(cs[i] - cs[i - 1], 0) for i in range(1, len(cs))]
    p = [max(cs[i - 1] - cs[i], 0) for i in range(1, len(cs))]
    ag, al = sum(g[:n]) / n, sum(p[:n]) / n
    for a, b in zip(g[n:], p[n:]):
        ag, al = (ag * (n - 1) + a) / n, (al * (n - 1) + b) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def tendencia(v):
    cs = [x[4] for x in v]
    e20, e50 = ema(cs, 20), ema(cs, 50)
    p, pendiente = cs[-1], e50[-1] - e50[-6]
    if p > e20[-1] > e50[-1] and pendiente > 0:
        return "alcista", e20[-1], e50[-1]
    if p < e20[-1] < e50[-1] and pendiente < 0:
        return "bajista", e20[-1], e50[-1]
    return "lateral", e20[-1], e50[-1]


def zonas(v15, tol):
    """Niveles por pivotes de M15 de los 2 últimos días + máximos/mínimos de hoy y ayer, agrupados."""
    hoy = v15[-1][0].date()
    ayer = max((x[0].date() for x in v15 if x[0].date() < hoy), default=hoy)
    niveles = []
    for nombre, dia in (("hoy", hoy), ("ayer", ayer)):
        dv = [x for x in v15 if x[0].date() == dia]
        if dv:
            niveles += [(max(x[2] for x in dv), f"máximo de {nombre}"), (min(x[3] for x in dv), f"mínimo de {nombre}")]
    recientes = [x for x in v15 if x[0].date() >= ayer]
    k = 3
    for i in range(k, len(recientes) - k):
        h, l = recientes[i][2], recientes[i][3]
        if h == max(x[2] for x in recientes[i - k:i + k + 1]):
            niveles.append((h, "giro previo"))
        if l == min(x[3] for x in recientes[i - k:i + k + 1]):
            niveles.append((l, "giro previo"))
    niveles.sort()
    grupos = []
    for precio, nota in niveles:
        if grupos and precio - grupos[-1]["hasta"] <= tol:
            g = grupos[-1]
            g["hasta"], g["toques"] = precio, g["toques"] + 1
            if nota != "giro previo" and nota not in g["notas"]:
                g["notas"].append(nota)
        else:
            grupos.append({"desde": precio, "hasta": precio, "toques": 1, "notas": [] if nota == "giro previo" else [nota]})
    return grupos


def dec(activo, precio):
    if activo.endswith("USDT"):
        return 2 if precio > 100 else 4
    if activo.endswith("JPY") or activo == "XAUUSD":
        return 3 if activo.endswith("JPY") else 2
    return 5


def sesion(ahora):
    h = ahora.astimezone(MADRID).hour + ahora.astimezone(MADRID).minute / 60
    if 14.5 <= h < 18:
        return "Londres + Nueva York (máxima liquidez)", 10
    if 9 <= h < 18:
        return "Londres", 5
    if 18 <= h < 22:
        return "Nueva York", 0
    return "Asia (poca liquidez en Europa)", -10


def plan(direccion, zona, precio, opuestas, atr15, objetivo_dia):
    """Plan de entrada en una zona: entrada en el borde, stop detrás con margen, objetivo en la zona opuesta."""
    margen = 0.3 * atr15
    if direccion == "compra":
        entrada = zona["hasta"]
        stop = min(zona["desde"] - margen, entrada - atr15)  # nunca a menos de 1 ATR: el ruido te sacaría
        cands = [z["desde"] for z in opuestas if z["desde"] > entrada + (entrada - stop) * 1.2]
        objetivo = min(cands) if cands else objetivo_dia
    else:
        entrada = zona["desde"]
        stop = max(zona["hasta"] + margen, entrada + atr15)
        cands = [z["hasta"] for z in opuestas if z["hasta"] < entrada - (stop - entrada) * 1.2]
        objetivo = max(cands) if cands else objetivo_dia
    riesgo = abs(entrada - stop)
    rr = abs(objetivo - entrada) / riesgo if riesgo else 0
    return {"direccion": direccion, "entrada": entrada, "stop": stop, "objetivo": objetivo, "rr": round(rr, 2),
            "distancia_atr": round(abs(precio - entrada) / atr15, 1)}


def analizar(activo):
    v15, v1h = velas(activo, "15m"), velas(activo, "1h")
    ahora = v15[-1][0]
    cerradas = v15[:-1]
    precio = v15[-1][4]
    a15, a1h = atr(cerradas), atr(v1h[:-1])
    t1h, e20h, e50h = tendencia(v1h)
    t15, e20, _ = tendencia(cerradas)
    hoy = [x for x in v15 if x[0].date() == ahora.date()]
    zs = zonas(cerradas, 0.35 * a15)
    for z in zs:
        z["fuerza"] = min(3, z["toques"]) + (1 if any("ayer" in n or "hoy" in n for n in z["notas"]) else 0)
    soportes = [z for z in zs if z["hasta"] < precio - 0.1 * a15]
    resist = [z for z in zs if z["desde"] > precio + 0.1 * a15]
    sop = max(soportes, key=lambda z: (z["hasta"], z["fuerza"])) if soportes else None
    res = min(resist, key=lambda z: (z["desde"], -z["fuerza"])) if resist else None
    maxd, mind = (max(x[2] for x in hoy), min(x[3] for x in hoy)) if hoy else (precio, precio)
    planes = []
    if sop:
        planes.append(plan("compra", sop, precio, resist, a15, maxd if maxd > precio else precio + 2 * a15))
    if res:
        planes.append(plan("venta", res, precio, soportes, a15, mind if mind < precio else precio - 2 * a15))
    for p in planes:
        p["a_favor"] = (p["direccion"] == "compra" and t1h == "alcista") or (p["direccion"] == "venta" and t1h == "bajista")

    # Señal activa: última vela de 15 min cerrada rechazando una zona a favor de la tendencia de 1 h
    _, o, h, l, c = cerradas[-1]
    cuerpo = abs(c - o) or 1e-12
    r = rsi([x[4] for x in cerradas])
    nombre_ses, bonus_ses = sesion(ahora)
    senal = None
    def buscar(tol, mecha_min, rr_min, base, permite_contra):
        """Busca un rechazo de zona en la última vela de 15 min. Modo estricto o flexible."""
        cand = []
        zb = max([z for z in zs if z["desde"] <= l + tol * a15 and z["hasta"] >= l - tol * a15], key=lambda z: z["fuerza"], default=None)
        za = max([z for z in zs if z["desde"] <= h + tol * a15 and z["hasta"] >= h - tol * a15], key=lambda z: z["fuerza"], default=None)
        if zb and c > o and (min(o, c) - l) >= mecha_min * cuerpo and (permite_contra or t1h != "bajista"):
            cand.append(("compra", zb, (min(o, c) - l) / cuerpo))
        if za and c < o and (h - max(o, c)) >= mecha_min * cuerpo and (permite_contra or t1h != "alcista"):
            cand.append(("venta", za, (h - max(o, c)) / cuerpo))
        if not cand and t1h == "alcista" and abs(l - e20) <= (tol + 0.05) * a15 and c > o and c > e20:
            cand.append(("compra", {"desde": l, "hasta": e20, "fuerza": 1, "toques": 1, "notas": ["media de 20 en M15"]}, (min(o, c) - l) / cuerpo))
        if not cand and t1h == "bajista" and abs(h - e20) <= (tol + 0.05) * a15 and c < o and c < e20:
            cand.append(("venta", {"desde": e20, "hasta": h, "fuerza": 1, "toques": 1, "notas": ["media de 20 en M15"]}, (h - max(o, c)) / cuerpo))
        for direccion, zona, mecha in cand:
            if direccion == "compra":
                entrada, stop = c, min(min(l, zona["desde"]) - 0.3 * a15, c - a15)
                obj = min([z["desde"] for z in resist if z["desde"] > entrada], default=entrada + 2 * (entrada - stop))
            else:
                entrada, stop = c, max(max(h, zona["hasta"]) + 0.3 * a15, c + a15)
                obj = max([z["hasta"] for z in soportes if z["hasta"] < entrada], default=entrada - 2 * (stop - entrada))
            rr = abs(obj - entrada) / abs(entrada - stop)
            if rr < rr_min:
                continue
            a_favor = (direccion == "compra" and t1h == "alcista") or (direccion == "venta" and t1h == "bajista")
            contra = (direccion == "compra" and t1h == "bajista") or (direccion == "venta" and t1h == "alcista")
            puntos = base
            puntos += 15 if a_favor else -10 if contra else 0
            puntos += 10 if t15 == t1h and t1h != "lateral" else 0
            puntos += 10 if zona["fuerza"] >= 3 else 5 if zona["fuerza"] == 2 else 0
            puntos += 10 if rr >= 2 else 0
            puntos += 5 if mecha >= 2 else 0
            puntos += 5 if (direccion == "compra" and r < 40) or (direccion == "venta" and r > 60) else 0
            puntos += bonus_ses
            return {"direccion": direccion, "entrada": entrada, "stop": stop, "objetivo": obj, "rr": round(rr, 2),
                    "puntos": max(0, min(100, puntos)), "motivo": f"vela de 15 min rechazando {', '.join(zona['notas']) or 'zona con ' + str(zona.get('toques', 1)) + ' toques'}"
                    + ("" if base == 50 else " (patrón flexible: mecha o toque más débil)"),
                    "vela": cerradas[-1][0].astimezone(MADRID).strftime("%H:%M"), "ts": int(cerradas[-1][0].timestamp())}
        return None

    # Primero el patrón estricto; si no hay, uno flexible con menos puntos (solo puede dar señales débiles)
    senal = buscar(0.25, 1.0, 1.5, 50, False) or buscar(0.45, 0.5, 1.3, 40, True)
    if senal and senal["motivo"].endswith("más débil)"):
        senal["puntos"] = min(senal["puntos"], UMBRAL - 1)

    corta = lambda v, n: [[int(x[0].timestamp()), x[1], x[2], x[3], x[4]] for x in v[-n:]]
    return {"activo": activo, "hora": ahora.astimezone(MADRID).strftime("%d/%m %H:%M"), "precio": precio,
            "decimales": dec(activo, precio), "velas15": corta(v15, 192), "velas1h": corta(v1h, 120),
            "dia": {"apertura": hoy[0][1] if hoy else precio, "maximo": maxd, "minimo": mind},
            "tendencia_1h": t1h, "tendencia_15m": t15, "rsi_15m": round(r, 1), "atr_15m": a15, "atr_1h": a1h,
            "ema20_1h": e20h, "ema50_1h": e50h, "zonas": zs, "soporte": sop, "resistencia": res,
            "planes": planes, "senal": senal, "sesion": nombre_ses}


def texto(a):
    d = lambda x: f"{x:.{dec(a['activo'], a['precio'])}f}"
    dia = a["dia"]
    cambio = (a["precio"] / dia["apertura"] - 1) * 100
    L = [f"# {a['activo']} · {a['hora']} (Madrid) · sesión: {a['sesion']}",
         f"Precio {d(a['precio'])} · hoy {cambio:+.2f}% · máx {d(dia['maximo'])} · mín {d(dia['minimo'])}",
         f"Tendencia 1 h: {a['tendencia_1h']} (EMA20 {d(a['ema20_1h'])} / EMA50 {d(a['ema50_1h'])}) · 15 min: {a['tendencia_15m']} · RSI 15 min {a['rsi_15m']}",
         f"Volatilidad: ATR 15 min {d(a['atr_15m'])} · ATR 1 h {d(a['atr_1h'])}",
         "Zonas (de arriba abajo):"]
    for z in sorted(a["zonas"], key=lambda z: -z["hasta"])[:10]:
        marca = " ← precio" if z["desde"] <= a["precio"] <= z["hasta"] else ""
        L.append(f"  {d(z['desde'])}–{d(z['hasta'])}  fuerza {z['fuerza']}  {', '.join(z['notas'])}{marca}")
    for p in a["planes"]:
        L.append(f"Plan de {p['direccion']}{' (a favor de la tendencia)' if p['a_favor'] else ' (contra la tendencia de 1 h)'}: "
                 f"entrada {d(p['entrada'])} · stop {d(p['stop'])} · objetivo {d(p['objetivo'])} · R:B 1:{p['rr']} · a {p['distancia_atr']} ATR del precio")
    s = a["senal"]
    if s:
        nivel = "" if s["puntos"] >= UMBRAL else f", {DEBIL}" if s["puntos"] >= UMBRAL_DEBIL else ", demasiado débil para avisar"
        L.append(f"SEÑAL ACTIVA ({s['puntos']}/100{nivel}): {s['direccion']} en {d(s['entrada'])}, stop {d(s['stop'])}, objetivo {d(s['objetivo'])}, "
                 f"R:B 1:{s['rr']} — {s['motivo']} (vela de las {s['vela']})")
    else:
        L.append("Sin señal activa ahora mismo: esperar a que el precio llegue a una zona y la rechace.")
    return "\n".join(L)


CARPETA = os.path.dirname(os.path.abspath(__file__))
MESA = "https://martivallfernandez-hash.github.io/mesa-trading/"


def log(msg):
    try:
        with open(os.path.join(CARPETA, "escaner.log"), "a", encoding="utf-8") as f:
            f.write(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def calibracion():
    """Lee calibracion.json (sale del backtest). Si no existe, no filtra nada."""
    try:
        with open(os.path.join(CARPETA, "calibracion.json"), encoding="utf-8") as f:
            return json.load(f)["activos"]
    except (OSError, ValueError, KeyError):
        return {}


def estrategia():
    """Reglas elegidas por el optimizador (estrategia.json). Si no existe, no filtra nada."""
    try:
        with open(os.path.join(CARPETA, "estrategia.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def aplicar_estrategia(a):
    """Devuelve la señal ajustada a las reglas ganadoras, o None si no las cumple."""
    e, s = estrategia(), a["senal"]
    if not e or not s:
        return s
    r = e["reglas"]
    act = e["activos"].get(a["activo"])
    if act is not None and not act.get("activo"):
        return None
    compra = s["direccion"] == "compra"
    t1h = a["tendencia_1h"]
    a_favor = (compra and t1h == "alcista") or (not compra and t1h == "bajista")
    contra = (compra and t1h == "bajista") or (not compra and t1h == "alcista")
    if r["tendencia"] == "a_favor" and not a_favor:
        return None
    if r["tendencia"] == "no_contra" and contra:
        return None
    if r["tipo"] == "estrictas" and "flexible" in s["motivo"]:
        return None
    if s["puntos"] < r["min_puntos"]:
        return None
    h0, h1 = map(int, r["horas"].split("-"))
    if not h0 <= dt.datetime.fromtimestamp(s["ts"], dt.timezone.utc).astimezone(MADRID).hour < h1:
        return None
    if r["alineado_15m"] and not (a["tendencia_15m"] == t1h and t1h != "lateral"):
        return None
    if r["salida"] != "zona":
        m = float(r["salida"].rstrip("R"))
        riesgo = abs(s["entrada"] - s["stop"])
        s = dict(s, objetivo=s["entrada"] + (m if compra else -m) * riesgo, rr=m)
    return s


def historico(activo, puntos):
    """Texto con lo que habría hecho este tipo de señal en el backtest."""
    e = estrategia()
    if e:
        p = e["activos"].get(activo, {}).get("todo") or {}
        if p.get("n", 0) >= 8:
            return f"Histórico de esta estrategia en {activo}: {p['n']} señales, {p['acierto']}% de acierto, {p['R_medio']:+.2f} R de media (backtest {e.get('dias', 60)} días)."
        return ""
    c = calibracion().get(activo)
    if not c:
        return ""
    for umbral in (85, 70, 55):
        r = c.get(f"desde_{umbral}")
        if puntos >= umbral and r and r.get("n", 0) >= 10:
            return f"Histórico ({r['n']} señales de {umbral}+ pts): {r['acierto']}% de acierto, {r['R_medio']:+.2f} R de media."
    return ""


def tema_ntfy():
    """El tema sale de la variable NTFY_TEMA (GitHub) o de config.json (PC)."""
    if os.environ.get("NTFY_TEMA"):
        return os.environ["NTFY_TEMA"].strip()
    with open(os.path.join(CARPETA, "config.json"), encoding="utf-8") as f:
        return json.load(f)["ntfy_tema"]


def ya_avisadas():
    """Títulos enviados al canal en las últimas 3 horas (desde el PC o desde GitHub)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://ntfy.sh/{tema_ntfy()}/json?poll=1&since=3h", headers=UA), timeout=20) as r:
            return {json.loads(l).get("title", "") for l in r.read().decode("utf-8").splitlines() if l.strip()}
    except Exception:
        return None


def avisar(a):
    """Manda la señal al móvil con ntfy (https://ntfy.sh)."""
    tema = tema_ntfy()
    s, d = a["senal"], (lambda x: f"{x:.{dec(a['activo'], a['precio'])}f}")
    debil = s["puntos"] < UMBRAL
    titulo = f"{a['activo']} · {s['direccion'].upper()} · {s['puntos']}/100" + (f" · {DEBIL}" if debil else "")
    cuerpo = (("Señal débil: poca relevancia. Úsala para observar o practicar, no como entrada principal.\n" if debil else "") +
              f"Entrada {d(s['entrada'])} · Stop {d(s['stop'])} · Objetivo {d(s['objetivo'])} · R:B 1:{s['rr']}\n"
              f"{s['motivo'].capitalize()} (vela de las {s['vela']}). Tendencia 1 h: {a['tendencia_1h']}.\n" +
              (historico(a["activo"], s["puntos"]) + "\n" if historico(a["activo"], s["puntos"]) else "") +
              "Compruébalo en tu gráfico antes de entrar. Educativo, cuenta demo.")
    req = urllib.request.Request(f"https://ntfy.sh/{tema}", data=cuerpo.encode("utf-8"), headers={
        "Title": titulo.encode("utf-8"), "Tags": "chart_with_upwards_trend" if s["direccion"] == "compra" else "chart_with_downwards_trend",
        "Priority": "high" if s["puntos"] >= 85 else "low" if debil else "default", "Click": MESA, "User-Agent": "Mozilla/5.0"})
    urllib.request.urlopen(req, timeout=20).close()


def en_horario(ahora=None):
    """Lunes a viernes de 8:00 a 22:00, hora de Madrid."""
    m = (ahora or dt.datetime.now(dt.timezone.utc)).astimezone(MADRID)
    return m.weekday() < 5 and 8 <= m.hour < 22


def escanea(todas=False, como_json=False, enviar=False):
    if enviar and not en_horario():
        return []
    try:
        with open(ESTADO, encoding="utf-8") as f:
            enviadas = json.load(f)
    except (OSError, ValueError):
        enviadas = {}
    ahora = dt.datetime.now(dt.timezone.utc).timestamp()
    nuevas, errores = [], []
    enviados_canal = ya_avisadas() if enviar else None
    for activo in LISTA:
        try:
            a = analizar(activo)
        except Exception as e:  # una fuente caída no debe parar el resto
            errores.append(f"{activo}: {e}")
            continue
        s = a["senal"]
        if not s or s["puntos"] < UMBRAL_DEBIL:
            continue
        if estrategia():
            s = aplicar_estrategia(a)
            if not s:
                continue  # no cumple las reglas que ganaron en el backtest
            a["senal"] = s
        else:
            cal = calibracion().get(activo)
            if cal is not None and (not cal.get("activo") or s["puntos"] < (cal.get("min_puntos") or 0)):
                continue  # el backtest dice que este activo o esta puntuación no compensan
        fuerte = s["puntos"] >= UMBRAL
        # Una señal débil no se repite si ya se avisó cualquier cosa de ese activo y dirección;
        # una fuerte solo se bloquea si ya se avisó otra fuerte (puede «mejorar» una débil).
        clave = f"{activo}-{s['direccion']}-{'fuerte' if fuerte else 'debil'}"
        bloquea = [clave] if fuerte else [clave, f"{activo}-{s['direccion']}-fuerte"]
        if not todas and any(ahora - enviadas.get(k, 0) < 3 * 3600 for k in bloquea):
            continue
        prefijo = f"{activo} · {s['direccion'].upper()} ·"
        if not todas and enviados_canal and any(t.startswith(prefijo) and (not fuerte or DEBIL not in t) for t in enviados_canal):
            continue
        enviadas[clave] = ahora
        nuevas.append(a)
    try:
        with open(ESTADO, "w", encoding="utf-8") as f:
            json.dump(enviadas, f)
    except OSError:
        pass
    if enviar:
        for a in nuevas:
            try:
                avisar(a)
                log(f"AVISO {a['activo']} {a['senal']['direccion']} {a['senal']['puntos']}/100 entrada {a['senal']['entrada']}")
            except Exception as e:
                log(f"ERROR al avisar {a['activo']}: {e}")
        log(f"escaneo hecho: {len(nuevas)} señales nuevas" + (f", errores: {'; '.join(errores)}" if errores else ""))
        return nuevas
    if como_json:
        sin_velas = [{k: v for k, v in a.items() if not k.startswith("velas")} for a in nuevas]
        print(json.dumps({"senales": sin_velas, "errores": errores}, default=str, ensure_ascii=False))
        return
    if not nuevas:
        print("SIN SEÑALES NUEVAS")
    for a in nuevas:
        print(texto(a), end="\n\n")
    for e in errores:
        print("Error de datos:", e)


def exporta(ruta):
    """Guarda velas y análisis de toda la lista en un JSON para el gráfico de la Mesa."""
    salida = {"generado": int(dt.datetime.now(dt.timezone.utc).timestamp()), "activos": {}, "errores": []}
    for activo in LISTA:
        try:
            a = analizar(activo)
            for iv, clave, n in (("5m", "velas5", 192), ("30m", "velas30", 160)):
                try:
                    a[clave] = [[int(x[0].timestamp()), x[1], x[2], x[3], x[4]] for x in velas(activo, iv)[-n:]]
                except Exception as e:
                    salida["errores"].append(f"{activo} {iv}: {e}")
            salida["activos"][activo] = a
        except Exception as e:
            salida["errores"].append(f"{activo}: {e}")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(salida, f, default=str, ensure_ascii=False, separators=(",", ":"))
    log(f"exportado {ruta}: {len(salida['activos'])} activos")
    return salida


if __name__ == "__main__":
    args = sys.argv[1:]
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8")
    if args[:1] == ["analiza"] and len(args) > 1:
        print(texto(analizar(args[1].upper().replace("/", ""))))
    elif args[:1] == ["exporta"] and len(args) > 1:
        exporta(args[1])
    elif args[:1] == ["escanea"]:
        if sys.stdout is None:  # pythonw no tiene consola
            sys.stdout = sys.stderr = open(os.devnull, "w")
        escanea(todas="--todas" in args, como_json="--json" in args, enviar="--avisar" in args)
    else:
        print(__doc__)
