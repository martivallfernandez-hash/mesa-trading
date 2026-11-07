---
name: trading-risk-review
description: Revisar cambios en dimensionamiento, exposición, cierres y persistencia de la simulación de Trading Lab.
---

El perfil activo solicitado usa 10.000 USD ficticios, un presupuesto diario de
150 USD compartido y ninguna cuota fija por entrada. Comprueba pérdidas realizadas,
reserva de stops abiertos y tamaño según el riesgo restante. Las ganancias no reponen
pérdidas consumidas. Mantén exposición de entrada del 20 %, una sola posición y
protección global del 2 % desde máximo. El día se calcula en Europe/Madrid.
Los perfiles anteriores de 1.000 USD permanecen solo como historia y regresión.
Son presupuestos y umbrales, no garantías de pérdida máxima. Conserva esa distinción.
Comprueba costes de ambos lados, huecos adversos, prioridad de stop sobre objetivo,
y que no se incremente la cantidad para buscar el objetivo neto superior a 10 USD.
Revisa que las señales se calculen sin datos futuros y las entradas se simulen en la
apertura siguiente. No reinicies una sesión para ocultar pérdidas. Si el usuario pide una sesión nueva,
archiva íntegramente la anterior, conserva fecha y operaciones y haz la activación
idempotente; repetirla no debe volver a reponer el capital inicial.
Comprueba escritura condicional y conflictos concurrentes sin sobrescribir la cuenta.
Ejecuta `node --test tests/*.test.mjs`. Añade pruebas solo para riesgos nuevos.
No conectes fondos, amplíes exposición, elimines stops ni actives órdenes reales.
Documenta el cambio y las limitaciones. Esta skill mejora la revisión; no certifica rentabilidad.
