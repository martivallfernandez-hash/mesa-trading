---
name: trading-risk-review
description: Revisar cambios en dimensionamiento, exposición, cierres y persistencia de la simulación de Trading Lab.
---

Verifica el efecto del cambio sobre riesgo por operación (0,10 %), exposición máxima
(20 %), una sola posición y pausas diaria (0,50 %) y total (2 % desde máximo).
Son presupuestos y umbrales, no garantías de pérdida máxima. Conserva esa distinción.
Comprueba costes de ambos lados, huecos adversos, prioridad de stop sobre objetivo,
y que no se incremente la cantidad para buscar el objetivo neto superior a 10 USD.
Revisa que las señales se calculen sin datos futuros y las entradas se simulen en la
apertura siguiente. Preserva saldo, fecha de inicio y operaciones al cambiar de perfil.
Comprueba escritura condicional y conflictos concurrentes sin sobrescribir la cuenta.
Ejecuta `node --test tests/*.test.mjs`. Añade pruebas solo para riesgos nuevos.
No conectes fondos, amplíes exposición, elimines stops ni actives órdenes reales.
Documenta el cambio y las limitaciones. Esta skill mejora la revisión; no certifica rentabilidad.
