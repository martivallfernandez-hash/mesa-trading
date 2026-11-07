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
