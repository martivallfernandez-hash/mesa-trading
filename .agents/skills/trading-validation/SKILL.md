---
name: trading-validation
description: Evaluar estrategias de Trading Lab con costes, separación temporal y resultados completos.
---

Antes de evaluar, registra fuente, fechas, calidad de datos, costes y parámetros.
Separa desarrollo y validación cronológicamente. No denomines fuera de muestra a
un tramo ya usado para diseñar o elegir parámetros. La simulación prospectiva debe
conservar su fecha de comienzo y no incluir operaciones anteriores a ella.
Mide resultados netos, número de operaciones, máxima caída, exposición, distribución
de pérdidas y sensibilidad a comisiones, spreads y huecos. Compara con no operar y
con una referencia pasiva. Informa también los escenarios desfavorables y periodos sin señales.
No elijas parámetros por el mejor resultado de una muestra corta ni ocultes variantes fallidas.
Un objetivo superior a 10 USD puede exigir un recorrido grande y disminuir su frecuencia
de alcance; mostrar objetivos no equivale a predecir beneficios. Más operaciones aumentan costes.
Ejecuta pruebas de Python y JavaScript antes de cambiar código. No despliegues cambios
ni cambies parámetros desde la tarea horaria de actualización. No habilites dinero real.
