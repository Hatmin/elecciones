# Manual API Legislativas 2025

Este documento describe los métodos de autenticación, uso del token y endpoints disponibles en la API de resultados electorales.

## Autenticación y Token
La información e imágenes de escrutinio se obtienen mediante consulta a servicios web (GET). Para ello, deben especificarse varios datos en la cabecera de la llamada (HEADERS):
- Content-Type: application/json
- Authorization: Bearer
- Token: <token>, donde "token" es el token obtenido por el usuario
- URL de la petición:
https://api.resultados.gob.ar/api<opciones> En todos los casos, "opciones" son los parámetros a añadir dependiendo del motivo de la consulta de datos.
Ejemplos de llamada
Javascript
type: "GET",
url: "https://api.resultados.gob.ar/api/estados/estadoRecuento?
distritoId=02&categoriaId=05",
dataType: 'json',
beforeSend: function(request) {
request.setRequestHeader("Authorization", 'Bearer LCJzY29wZSI6Im (.......)
LnNpZ25pbi ' );
}
Curl
curl -i --header "Content-Type: application/json" \
-H "Authorization: Bearer eyJraWQiOiJ(......)6XP5qpMb2g"
"https://api.resultados.gob.ar/api/estados/estadoRecuento?
distritoId=02&categoriaId=05"
Herramienta como Postman o Insomnia, configurar según corresponda, con las siguientes indicaciones:
- En el tipo de autorización, seleccionar Bearer
- Introducir token de validación
- Configurar la petición como GET

## Endpoints de Catálogo
Obtener el catálogo por categoría electoral de agrupaciones políticas.
Parámetros:
Nombre Descripción
distritoId Id del distrito
seccionProvincialId Id de sección provincial
seccionId Id de Sección, Departamento o Comuna
municipioId Id del Municipio o Localidad
circuitoId Id del Circuito
establecimientoId Id del Establecimiento de votación
mesaId Id de la Mesa
categoriaId *required / integer Id de la categoría electoral para la cual se están solicitando datos.
Respuestas:
Código Descripción
400 Invalid ID value
200 successful operationGET
[ { "idAgrupacion": "string", "idAgrupacionTelegrama": "string", "nombreAgrupacion": "string", }
] /catalogo/getCategorias
Obtener las categorías disponibles para recuperar el catálogo.
Parámetros:
Sin parámetros.
Respuestas:
Código Descripción
200 successful operationGET
[ { "orden": 0, "categoriaId": 0, "nombre": "string" }
] /catalogo/getCatalogo
Obtener el catálogo completo de ámbitos para cada una de las categorías electorales.
Parámetros:
Nombre Descripción
categoriaId *required / integer Id de la categoría electoral que queremos obtener
Respuestas:
Código Descripción
200 successful operationGET
[ { "version": 2, "categoriaId": 2, "ambitos": [{ "nivelId": 1, "nombre": "ARGENTINA", "codigoAmbitos": { "indice": 0, "distritoId": "", "seccionProvincialId": "", "seccionId": "", "municipioId": "", "circuitoId": "", "establecimientoId": "", "mesaId": "" } },…
], "niveles": [{ "nivelId": 1, "nombre": "Pais" }, …. ]
}
]Llamadas a la API - Catálogos

## Endpoints de Resultados
/resultados/getResultados
Devuelve los resultados para el Id de la categoría electoral solicitada. Información disponibles a partir de nivel País, hasta la mesa. Para solicitar un ámbito en concreto será necesario enviar también los Id de los padres del ámbito. Por ejemplo para solicitar una sección, sera necesario enviar el Id de distrito. El Id de la mesa, será el código único de la mesa (distrito + sección + número mesa). Para solicitar los valores totalizados a nivel País, no indicar ningún parámetro salvo la categoría.
Parámetros:
Nombre Descripción
distritoId Id del distrito
seccionProvincialId Id de sección provincial
seccionId Id de Sección, Departamento o Comuna
municipioId Id del Municipio o Localidad
circuitoId Id del Circuito
establecimientoId Id del Establecimiento de votación
mesaId Id de la Mesa
categoriaId *required / integer Id de la categoría electoral para la cual se están solicitando datos
Respuestas:
Código Descripción
400 Invalid ID value
200 successful operationGET
{ "fechaTotalizacion": "Jul 31, 2025, 11:22:10 PM", "estadoRecuento": { "mesasEsperadas": 0, "mesasTotalizadas": 0, "mesasTotalizadasPorcentaje": 0, "cantidadElectores": 0, "electoresTotales":0, "cantidadVotantes": 0, "participacionPorcentaje": 0 }, "valoresTotalizadosPositivos": [ { "idAgrupacion": "string", "idAgrupacionTelegrama": "string", "nombreAgrupacion": "string", "votos": 0, "votosPorcentaje": 0 } ], "valoresTotalizadosOtros": { "votosNulos": 0, "votosNulosPorcentaje": 0, "votosEnBlanco": 0, "votosEnBlancoPorcentaje": 0, "votosRecurridos": 0, "votosComando": 0, "votosImpugnados": 0, "votosRecurridosPorcentaje": 0, "votosComandoPorcentaje": 0, "votosImpugnadosPorcentaje": 0 } /resultados/getBancas
Devuelve la proyección de bancas para el Id de la categoría electoral solicitada. Información disponible en el nivel País, y a nivel Distrito. Para solicitar los valores totalizados a nivel País, no indicar ningún parámetro salvo la categoría.
Parámetros:
Nombre Descripción
distritoId Id del distrito
categoriaId *required / integer Id de la categoría electoral para la cual se están solicitando datos
Respuestas:
Código Descripción
400 Invalid ID value
200 successful operationGET
{ "fechaTotalizacion": "Jul 31, 2025, 11:22:10 PM", "repartoBancas": [ { "idAgrupacion": "string", "idAgrupacionTelegrama": "string", "nombreAgrupacion": "string", "nroBancas": 0 } ]
} /estados/estadoRecuento
Obtener el avance del recuento provisional de resultados.
Parámetros:
Nombre Descripción
distritoId Id del distrito
seccionProvincialId Id de sección provincial
seccionId Id de Sección, Departamento o Comuna
municipioId Id del Municipio
circuitoId Id del Circuito
establecimientoId Id del Establecimiento
mesaId Id de la Mesa
categoriaId *required / integer Id de la categoría electoral para recuperar los datos
Respuestas:
Código Descripción
400 Invalid parameters
200 successful operationGET
[ { "mesasEsperadas": 0, "mesasTotalizadas": 0, "mesasTotalizadasPorcentaje": 0, "cantidadElectores": 0, "electoresTotales":0, "cantidadVotantes": 0, "participacionPorcentaje": 0 }
] Llamadas a la API - Resultados
Nota: Existe una limitación de 6.000 peticiones cada 5 minutos por usuario.
Los porcentajes de las agrupaciones políticas se calculan sobre votos afirmativos y se informan truncados a dos decimales. /resultados/getFile
Obtener el PDF de la mesa enviando el ID de la misma.
Parámetros:
Nombre Descripción
mesaId *required / string Id de la Mesa
Respuestas:
Código Descripción
400 Invalid ID value
200 successful operation
Formato de la respuesta: PDF, imagen en BASE64.GET
{ "nombreArchivo": "0202600060X", "imagen": "JVBERi0xLjcKJYGBgYEKCjQg…" "fechaEscaneo": "Jul 31, 2025, 11:22:10 PM", "fechaTotalizacion": "Aug 1, 2025, 4:13:34 PM"
} /resultados/getTelegramasTotalizados
Método para obtener un array con el listado de telegramas escrutados. Información disponible a partir del nivel de sección.
Parámetros:
Nombre Descripción
distritoId *required / string Id del distrito
seccionProvincialId Id de sección provincial
seccionId *required / string Id de Sección, Departamento o Comuna
municipioId Id del Municipio
circuitoId Id del Circuito
establecimientoId Id del Establecimiento
mesaId Id de la Mesa
Respuestas:
Código Descripción
400 Invalid parameters
200 successful operationGET
[ [ "string" ]
]

