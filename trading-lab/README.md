# Laboratorio del bot — investigación y simulación

El simulador conserva el perfil prudente actual bajo `worker/`: riesgo previsto de
0,10 %, exposición máxima de entrada del 20 %, una posición, pausa diaria al 0,50 %
y bloqueo total al caer 2 % desde el máximo. Son umbrales, no garantías. El objetivo
superior a 10 USD netos no incrementa la cantidad y puede exigir un recorrido grande;
los stops y las salidas por señal pueden cerrar con menos beneficio o con pérdidas.

El módulo `validation/` compara tres hipótesis fijas en BTC, ETH y SOL al contado:
cruce EMA, ruptura de canal y retroceso dentro de tendencia. Usa velas de 15 minutos,
no las de 5 minutos del bot desplegado. La fuente histórica es Coinbase, mientras que
el panel continúa con Kraken. No se adopta automáticamente una ganadora.

## Reproducir

Requiere Python 3.10+ y Node 20+, sin dependencias externas ni claves de exchange.

```sh
node --test tests/*.test.mjs
python3 -m unittest discover -s research -v
python3 -m unittest discover -s validation -p 'test_*.py' -v
python3 validation/download_history.py
python3 validation/evaluate.py
```

Las descargas van a `data/`, excluido de Git. Se comprueba orden, continuidad, OHLCV
y SHA256. Los metadatos de procedencia y resultados van a `reports/`.
Un histórico incompleto impide la evaluación; no se interpola silenciosamente.

## Protocolo

`validation/protocol.json` fija periodo, estrategias, costes, riesgo y criterios de
selección. El 60 % inicial sirve para desarrollo, el 20 % siguiente para validación
y el último 20 % se reserva sin evaluar. Solo una candidata elegida por desarrollo
puede pasar a validación y a costes adversos. Un candidato que no cumple número de
operaciones, beneficio neto, factor de beneficio y caída máxima no se aprueba.
El periodo final no se utiliza para elegir parámetros ni se mira por curiosidad.

## Antes de plantear capital real

Se necesita evidencia neta favorable fuera de los datos usados para diseñar,
suficientes operaciones, costes de la cuenta verificados, simulación prospectiva
estable y controles de desconexión, reconciliación y cierres probados en el bróker
concreto. Actualmente esos requisitos NO están cumplidos. Ningún test histórico
habilita fondos por sí solo. El paso a dinero real requiere autorización explícita
del usuario y límites de capital y pérdida acordados; no se pide ninguna clave aquí.

La mesa y el escáner existentes del repositorio se conservan. Este laboratorio no
modifica `escaner/`, sus credenciales, avisos, programación ni GitHub Pages. Las skills
bajo `.agents/skills/` guían revisión y validación; no certifican rentabilidad.

## Panel de varios bots y seguimiento v3

La cuenta cripto mantiene su historial. El catálogo presenta Forex y oro como
`pending_data`, sin saldo ni posibilidad de enviar órdenes. No se ha fingido una
conexión de XAU/USD usando futuros GC=F ni se han duplicado los 1.000 USD iniciales.
La fuente pública de Forex/oro probada devolvió `Edge: Too Many Requests`; queda
pendiente contratar o conectar una fuente adecuada y validar el motor de cada mercado.

Con el panel visible, el estado guardado se consulta cada cinco segundos y el ticker
público de Kraken cada quince. La casilla activa un ciclo de simulación cada cinco
minutos. Con el panel cerrado sigue vigente la tarea horaria. No se trata de un
motor de ejecución de órdenes ni de un servicio de scalping en tiempo real.

Las entradas y salidas incluyen hora simulada de la vela y hora de registro del ciclo.
Los eventos antiguos no tienen una hora de recepción inventada. Las posiciones se
valoran indicativamente con el bid y costes supuestos; ese valor no sustituye el
saldo contable del simulador. Los GET de estado, catálogo y ticker no operan ni
modifican la cuenta. Las escrituras de simulación siguen usando ETag.

## Skills y biblioteca aprobadas

Las cuatro skills propuestas quedan incorporadas como recursos de proyecto fijados
en `.agents/skills-lock.json`: depuración sistemática (Superpowers), pruebas por
propiedades, revisión diferencial y análisis dimensional (Trail of Bits). Se incluyen
las dos dependencias documentales de depuración: TDD y verificación de finalización.
Los wrappers locales remiten a fuentes completas, sus recursos y licencias bajo
`.agents/vendor/`. No se ejecutaron sus scripts de instalación ni se concedió acceso
a fondos. La instalación de recursos no equivale a haber ejecutado todas las auditorías.

Backtesting.py 0.6.6 se instaló en un entorno de investigación separado del Worker.
`research/tools/verify_backtesting.py` comprueba importación, ejecución en la apertura
siguiente y efecto de costes sobre precios sintéticos. No demuestra rentabilidad ni
se ha validado aún como segundo motor equivalente para toda la estrategia. El lockfile
conserva las versiones de sus dependencias. La skill «learn» no ha sido identificada;
no se ha instalado ninguna herramienta con ese nombre.

La revisión visual en navegador sigue pendiente porque el entorno no dispone de
`cua_repl.js`. Se comprobaron sintaxis del cliente, IDs únicos, funciones del servidor,
cuentas persistentes y datos reales del ticker. Las skills están instaladas como
recursos del repositorio, no como una conexión a fuentes de datos ni como una garantía
de rentabilidad. La biblioteca independiente se verifica además en un job separado de CI.
