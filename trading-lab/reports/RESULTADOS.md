# Validación inicial del laboratorio

Estado: **NINGUNA CANDIDATA APROBADA. Operativa real deshabilitada.**

Se descargaron 176 días de BTC/USD, ETH/USD y SOL/USD, 16.896 velas de 15 minutos por activo. El protocolo original solicitaba el 1 de mayo al 1 de noviembre de 2026. Faltaban 25 velas consecutivas del 8 de mayo en los tres activos, también ausentes en la comprobación de cinco minutos. Se recortó el comienzo al 9 de mayo por calidad, sin evaluar rentabilidades para elegir el periodo. Se conservan el protocolo inicial, la enmienda, las huellas SHA256 y el diagnóstico.

El 60 % inicial se utilizó para evaluar las tres hipótesis ya fijadas. Ninguna pasó los criterios, de modo que no se eligió candidata, no se abrió el tramo de validación ni se evaluó el último 20 % reservado. Los límites de protección interrumpen cada simulación si se alcanza la caída fijada: estos resultados no equivalen a mantener la estrategia operando todo el periodo sin protección.

| Candidata | Operaciones | Ganadoras | Resultado neto de 1.000 USD | Caída máxima | Recorrido medio hasta objetivo |
| --- | ---: | ---: | ---: | ---: | ---: |
| ema_cross | 28 | 2 | -20.16 USD | 2.02 % | 14.36 % |
| channel_breakout | 25 | 2 | -20.15 USD | 2.01 % | 14.52 % |
| trend_pullback | 24 | 0 | -20.62 USD | 2.06 % | 14.07 % |

La referencia de no operar obtiene 0 %. Los costes supuestos son 0,40 % de comisión y 0,10 % de deslizamiento/spread por lado. No son tarifas verificadas de una cuenta contratada. Las entradas arriesgan aproximadamente 1 USD sobre 1.000, con como máximo un 20 % invertido. El objetivo de más de 10 USD netos requiere en promedio un movimiento del activo cercano al 14 %, aunque cada entrada varía. Los stops y cruces pueden cerrar antes con pérdida.

Estos resultados no prueban que todas las estrategias de estos mercados fallen; rechazan estas tres configuraciones en este experimento. No se ha buscado una combinación ganadora después de mirar los resultados. El siguiente experimento deberá registrarse por separado y justificar cualquier cambio en objetivos, costes, frecuencia o condiciones de entrada.

La frecuencia de investigación es de 15 minutos y la fuente Coinbase; el bot desplegado usa Kraken y cinco minutos. No se ha cambiado automáticamente su estrategia, su saldo ni su programación. El histórico reservado no es autorización para fondos.

## Reproducción

Desde `trading-lab/`, ejecutar `python3 validation/download_history.py` y después `python3 validation/evaluate.py`. Los CSV se mantienen fuera de Git; `data-manifest.json` conserva procedencia, cobertura y huellas. Los resultados completos están en `validation.json`.
