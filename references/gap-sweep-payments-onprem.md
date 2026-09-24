# Gap sweep layer — middleware de pagos on-prem sobre un ERP de terceros

Aplica cuando `_profile.yml gap_sweep_layers:` incluye `payments-onprem`. Corre **después** del barrido base de `gap-sweep.md`, nunca en su lugar. Se solapa a propósito con `gap-sweep-web-baas.md` en la mitad del receptor de webhook: esa capa cubre el receptor, esta cubre lo que hay detrás.

El caso que describe: un servicio propio que cobra por un proveedor externo y escribe el resultado en la base de datos de un ERP que **no controlas**, en una máquina física dentro del local del cliente.

## Escribir en la base de un ERP ajeno

- **¿Con qué usuario de SQL Server, y con qué permisos enumerados uno por uno?** "El usuario de la aplicación" no es una respuesta. `sa` y `db_owner` son un hallazgo automático.
- **¿Hay un trigger sobre una tabla del ERP? ¿Qué pasa cuando falla?** Un trigger que lanza excepción **aborta la transacción que lo disparó**. El fallo no se ve en el middleware: se ve en la caja, donde el cajero ya no puede facturar. El barrido base pregunta por ramas de error; aquí la rama de error es una operación de un tercero que tú rompiste. Debe declararse explícitamente si el trigger puede propagar error o no.
- **¿Sobrevive a una actualización del ERP?** El fabricante actualiza esquema y objetos. Un trigger, una vista o una columna añadida pueden desaparecer en la siguiente versión sin aviso. Nombrar qué se rompe y cómo se detecta.
- **¿Sobrevive a un restore?** Restaurar un respaldo del ERP devuelve la base al estado en que estaba, sin los objetos añadidos después.
- **¿Qué recalcula el ERP por su cuenta?** Correlativos, saldos, documentos de cuentas por cobrar. Una escritura externa que los deja inconsistentes no da error: da un descuadre que aparece semanas después en un reporte.

## Dinero: el monto no es un número, es tres

- **Moneda de la factura contra moneda del cobro.** Si difieren, ¿quién fija la tasa, en qué momento, y qué pasa si se mueve entre que se emite el QR y que se paga?
- **Redondeo y decimales.** Dos sistemas con distinta precisión producen diferencias de centavos que, acumuladas, son un descuadre de cartera.
- **Comisión del proveedor.** Lo que el comercio recibe puede no ser lo que el cliente pagó. Decir cuál de los dos se escribe en el ERP.
- **Pago parcial y sobrepago.** ¿El proveedor puede reportar pagado un monto distinto al pedido? Si sí, ¿qué rama lo atiende? Escribir un cobro por un monto que no es el de la factura es peor que no escribir nada.
- **Reembolsos y contracargos.** Aunque queden fuera de alcance, el operador se los encontrará. Sin decisión escrita, improvisará sobre la base de datos.

## Custodia del secreto en una máquina física

- **¿Dónde vive en reposo?** Almacén de secretos del sistema operativo, nunca configuración versionada. Nombrar el mecanismo.
- **¿Quién tiene acceso físico y administrativo a esa máquina?** En un local comercial la respuesta suele ser "más gente de la que crees".
- **¿Aparece en algún volcado?** Logs, trazas de excepción, respuestas de error, consola.
- **¿Cómo se rota?** Un secreto que no se puede rotar sin parar el servicio no se rota nunca. Decir qué pasa con las órdenes en vuelo durante la rotación.

## Inmutabilidad por permisos

- **Contra quién es inmutable.** Quitar `UPDATE` y `DELETE` al usuario de la aplicación protege contra la aplicación y contra quien robe sus credenciales. **No protege contra un administrador de la base**, que es dueño del esquema. Decirlo en la prosa: una bitácora anunciada como inmutable que un DBA puede editar es una promesa falsa ante una auditoría.
- **Retención contra inmutabilidad.** Si nada puede borrarse, la tabla crece para siempre; si algo puede borrarse, hay un camino de borrado que alguien puede usar. Resolver la tensión explícitamente, no dejar las dos afirmaciones sueltas en secciones distintas.

## El túnel saliente como superficie

- **Quitar el puerto de entrada no quita la autenticación.** Cualquiera que descubra la URL del túnel puede enviarle peticiones. La verificación de firma sigue siendo lo único que separa un evento real de uno inventado.
- **¿Qué más publica el túnel?** Si expone la raíz del servicio en vez de solo el path del webhook, saca a internet el panel administrativo y la pantalla de caja. Enumerar exactamente qué paths quedan publicados.
- **La credencial del túnel es otro secreto**, con las mismas preguntas de custodia y rotación.
- **¿Qué pasa cuando el túnel cae?** Los eventos que el proveedor intente entregar durante la caída se pierden o se reintentan según su política — que es un número del barrido base, y si no se conoce, el respaldo por consulta activa es obligatorio, no opcional.

## Interrupción entre dos sistemas

El middleware confirma al proveedor y escribe en el ERP. Son dos pasos y no hay transacción que los abarque.

- **¿Qué pasa si el proceso muere entre los dos?** Cortes de luz en un local comercial no son un caso teórico. El evento quedó confirmado ante el proveedor, que no lo reintentará, y el ERP no tiene el cobro.
- **¿Cómo se recupera al reiniciar?** Debe existir un estado persistido que permita terminar lo empezado, y debe ser idempotente: al reintentar no puede escribir dos veces.

## El operador humano en la caja

- **¿Qué ve cuando el pago no llega?** Un cajero mirando una pantalla que no cambia toma una decisión por su cuenta.
- **¿Puede cancelar o re-emitir?** Si puede re-emitir, ¿puede haber dos órdenes vivas para la misma factura? Dos QR válidos para un mismo documento es un cobro doble esperando ocurrir.
- **¿Puede liberar la mercancía sin confirmación?** Si el sistema no lo impide, la regla de negocio no existe: es una sugerencia.

## Verificando esta capa

Los permisos de base de datos, la inmutabilidad de la bitácora y lo que el túnel publica **no se comprueban leyendo código**. Se comprueban intentando la operación prohibida contra el sistema real y observando que falla. El doc debe decir cuáles de estas comprobaciones son `[MANUAL]` y contra qué entorno se ejecutan.
