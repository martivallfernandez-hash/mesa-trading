# Primera conexión a tu MetaTrader 5 demo

Esta fase comprueba precios, velas e instrumentos del terminal Windows. No envía
órdenes y no convierte la cuenta simulada del panel en una cuenta del bróker.
El paquete oficial de Python necesita un terminal MT5 compatible instalado y con
sesión iniciada. El móvil sirve para ver la misma cuenta, pero no sustituye al
componente Windows.

## Pasos en Windows

1. Descarga este repositorio desde GitHub con **Code → Download ZIP** y descomprímelo.
2. Abre tu MetaTrader 5 en Windows y entra en la **misma cuenta demo** que usas en el móvil.
3. Abre esta carpeta del proyecto y ejecuta **Preparar_MT5_Demo**. Pedirá confirmación
   para crear un entorno Python local e instalar el paquete oficial con versión fijada.
   Requiere Python de 64 bits para Windows; si no está instalado, utiliza su instalador oficial.
4. Ejecuta **Leer_MT5_Demo**. Se conectará al terminal que ya está abierto. No pide
   la contraseña del bróker y rechaza cuentas reales o de concurso antes de consultar precios.
5. En tu panel privado, entra en **Conexión MT5**, selecciona la lectura demo generada
   e impórtala. Las cotizaciones disponibles aparecerán en las tarjetas de Forex y oro.

La primera importación es manual: demuestra qué datos recibimos, no una sincronización
continua. Replit está preparando el canal autenticado para automatizar después las
lecturas. No copies tokens del panel ni contraseñas del bróker a mensajes, capturas o GitHub.

## Instrumentos y datos

Los nombres de símbolos dependen del bróker: puede usar sufijos como XAUUSD.a.
La variable local `MT5_SYMBOL_MAP` permite indicar el nombre exacto, conservando la
etiqueta del panel. Un símbolo ausente se informa como no disponible; no se sustituye
por futuros ni por un activo parecido. El lector entrega tamaño de contrato, lote
mínimo y paso de volumen del propio bróker. Esto todavía no calcula ni ejecuta órdenes.
Las velas son de cinco minutos y se excluyen las abiertas. `tickVolume` es un recuento
de ticks, no volumen negociado centralizado. Los tiempos se conservan en UTC.
Un tick antiguo se marca como no reciente, incluso si el mercado está cerrado:
no se desplazan sus fechas para hacerlo parecer actual.

No se incluye login ni contraseña en la lectura. La referencia de cuenta está
seudonimizada y la moneda sí se conserva para interpretar cifras correctamente.

## Ejecución demo pendiente

Antes de habilitarla hay que comprobar los instrumentos reales, lotes mínimos,
capital y moneda de referencia, límites conjuntos, confirmaciones del bróker,
reintentos sin duplicados, stops y conciliación del historial. No debe copiarse a
ciegas una entrada antigua de la simulación ni ejecutarse cripto al contado como si
fuese el mismo contrato CFD ofrecido por el bróker. No hay funciones de órdenes en
este lector. La conexión real con tu terminal no se puede verificar desde el entorno
Linux donde se desarrolla el proyecto; las pruebas actuales utilizan un terminal simulado.

La funcionalidad de envío opcional de lecturas solo acepta un receptor HTTPS y un
token específico de ese receptor, configurados localmente. No es un token de MT5 ni
un permiso de trading; la URL del futuro canal de Replit deberá confirmarse cuando exista.

Documentación oficial: [Python Integration de MetaTrader 5](https://www.mql5.com/en/docs/python_metatrader5).
