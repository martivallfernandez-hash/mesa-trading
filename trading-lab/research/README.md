# Bot de trading — prototipo de investigación

## Qué está hecho

- Descarga pública de BTC/USD, ETH/USD y SOL/USD desde Kraken, en velas de 5 minutos.
- Exclusión de velas abiertas, validación de precios y comprobación de continuidad antes del análisis.
- EMA 9/21, RSI 14 y ATR 14 de Wilder, MACD 12/26/9 y volumen medio de las 20 velas anteriores.
- Señales experimentales: compra tras cruce alcista con RSI entre 50 y 70 y volumen superior a la media; cierre tras cruce bajista.
- Simulación histórica de cartera con hasta dos posiciones, riesgo previsto de 0,25 % por entrada, stop a 1,5 ATR y objetivo a dos veces esa distancia.
- Costes hipotéticos por lado: comisión del 0,40 % y deslizamiento/spread agregado del 0,10 %. Deben sustituirse por costes de la cuenta e instrumento elegidos.
- Límite diario de pérdidas del 1 % sobre valor de liquidación: pausa entradas y solicita cerrar en la apertura siguiente; los huecos pueden superar el límite.
- Archivo SQLite sin duplicados y recolector periódico opcional.
- CSV de operaciones, curva de capital y resumen JSON con procedencia y fecha.
- Parada mediante archivo STOP. No hay función de ejecución de órdenes.

## Empezar

Python 3.10 o posterior. No requiere bibliotecas externas ni claves.

Desde la carpeta del proyecto:

```sh
python3 -m unittest -v
python3 monitor.py
```

El segundo comando ejecuta **un ciclo**, descarga datos reales, calcula indicadores,
prueba la estrategia sobre el último tramo y archiva las velas.

Resultados en `runs/`. El archivo `runs/LATEST` indica la carpeta de la última
investigación completada. Comprueba `generated_at_utc` en `summary.json` para no
confundir un informe anterior con datos actuales. Si falla un ciclo, pueden quedar
archivos parciales en su carpeta, pero LATEST no apunta a ella hasta completar
el informe. La base SQLite se actualiza después; si el archivo de velas falla,
el proceso devuelve error aunque el informe de investigación se haya completado.

Para solicitar consulta cada cinco minutos mientras el proceso permanezca activo:

```sh
python3 monitor.py --continuous
```

Parada: Ctrl+C o crear el archivo `runs/STOP`. Retira STOP para permitir una
nueva ejecución. Si hay una solicitud de red en curso, termina o agota su timeout
antes de detenerse. No hemos dejado un proceso continuo ejecutándose en el chat.

## Resultado inicial observado

El 7 de noviembre de 2026 se descargaron 720 velas cerradas por activo, unas
60 horas. La primera evaluación del tramo entre el 5 y el 7 de noviembre produjo
12 operaciones y aproximadamente **-28,02 USD (-2,80 %)** sobre 1.000 USD ficticios,
con los costes supuestos. Ninguna operación tuvo resultado neto positivo.
No se han modificado parámetros para ocultar ese resultado.

Es una comprobación funcional, no una validación estadística ni una prueba fuera
de muestra suficiente. El capital del informe está en USD: no representa una
conversión de los 1.000 EUR previstos por el usuario.

## Detalles de simulación

Las señales se calculan al cierre y se ejecutan en la apertura siguiente. Las
primeras 100 velas se usan para calentamiento; las EMA se inicializan con el
primer cierre. RSI usa 14 cambios y ATR 14 rangos. Si una vela toca stop y objetivo,
se aplica el stop de forma conservadora. Un hueco por debajo del stop se ejecuta
a la apertura con deslizamiento. Las posiciones se liquidan al terminar la muestra.
La prioridad entre señales simultáneas sigue el orden alfabético de los activos.
No hay apalancamiento ni ventas en corto: una señal bajista cierra una compra.
El riesgo por operación es un presupuesto previsto, no una pérdida máxima garantizada.

Los backtests actuales usan las últimas 720 velas; la base `history.sqlite3`
acumula observaciones para futuros estudios más largos. Kraken puede limitar
el histórico y puede omitir intervalos sin operaciones: el análisis actual falla
si encuentra huecos en lugar de rellenarlos silenciosamente.

## Nube

`deploy/trading-research.service` contiene una plantilla para un servidor Linux
persistente. Requiere instalar el proyecto en `/opt/trading-bot`, crear el usuario
sin privilegios `trading` y registrar el servicio en systemd. El directorio de estado
sería `/var/lib/trading-research`. Su archivo STOP debe crearse allí. No se ha
contratado un servidor ni instalado el servicio: este entorno de desarrollo no
es una garantía de disponibilidad 24/7. La plantilla debe verificarse en el
servidor de destino antes de habilitarla. No genera costes de infraestructura
por sí misma.

## Decisiones recuperadas y pendientes

Usuario principiante, Python, nube, presupuesto futuro de 1.000 EUR, mercados
finales crypto/acciones/ETF/Forex. Primero pruebas con crypto. Binance rechazó
el acceso por ubicación (HTTP 451), así que se utiliza Kraken tras autorización
para resolver el bloqueo. El cambio de fuente cambia la moneda cotizada de
USDT a USD. No se han creado cuentas ni compartido credenciales.

Falta una muestra histórica extensa, separación temporal fuera de muestra,
evaluación con costes verificables, paper trading persistente, panel de control,
monitorización de disponibilidad y despliegue permanente. No existe evidencia
para recomendar operar esta estrategia con dinero real. No se han conectado
fondos, añadido IA a las decisiones ni declarado que la estrategia sea rentable.
