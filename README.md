# elecciones

## Guia rapida de ejecucion (Windows)

### 1) Requisitos
- Python 3.10 o superior
- Internet habilitado al dominio `api.resultados.gob.ar`

### 2) Instalar dependencias
En PowerShell, dentro de la carpeta del proyecto:

```powershell
pip install -r .\requirements.txt
```

Si falla, probá:

```powershell
py -m pip install -r .\requirements.txt
```

### 3) Variables de entorno
Debes definir al menos usuario y password (o un token temporal):

```powershell
$env:RESULTADOS_USERNAME = "tu_usuario"
$env:RESULTADOS_PASSWORD = "tu_password"
# Opcional si ya tenes token (omite USERNAME/PASSWORD)
# $env:RESULTADOS_TOKEN = "eyJhbGciOi..."

# Opcionales
$env:RESULTADOS_BASE_URL = "https://api.resultados.gob.ar/api"
$env:RESULTADOS_INTERVAL_SECONDS = "30"  # intervalo de actualizacion
$env:RESULTADOS_PBA_NAME = "Provincia de Buenos Aires"  # por si cambia el texto

# Fotos (opcional)
$env:FOTOS_BASE_PATH = "D:\\graficas\\elecciones\\assets"
$env:FOTOS_DEFAULT_FILE = "default.jpg"
# Mapa JSON de fotos: {"001":"fp.jpg", "LLA":"lla.jpg"}
$env:FOTOS_JSON_PATH = "D:\\graficas\\elecciones\\fotos.json"
```

Notas de seguridad:
- No subas tus credenciales a git. Usá variables de entorno o un `.env` local (no incluido).
- Los tokens expiran; el script reintenta solicitar uno si recibe 401.

### 4) Ejecutar

```powershell
python .\api_elecciones_datos.py
```

Que hace:
- Crea/usa un token para la API.
- Descarga categorias y las guarda en `logs/categorias.log`.
- Cada ~30s genera `elecciones_datos.csv` en la raiz del proyecto.
- Escribe logs de ciclo en `logs/run.log`.

### 5) CSV generado
Cabecera:

```
ambito,ambito_id,provincia,categoria,puesto,agrupacion_id,agrupacion,votos_pct,mesas_pct,foto,ts_iso
```

Ejemplo de filas:

```
NACIONAL,AR,,DIPUTADOS,1,001,FP,36.12,78.45,assets/fp.jpg,2025-10-22T21:05:00Z
PBA,PBA,Buenos Aires,SENADORES,1,001,FP,35.90,75.10,assets/fp.jpg,2025-10-22T21:05:00Z
PROVINCIA,03,Catamarca,DIPUTADOS,1,001,FP,34.22,80.03,assets/fp.jpg,2025-10-22T21:05:00Z
```

Definiciones rapidas:
- ambito: NACIONAL | PBA | PROVINCIA
- ambito_id: AR | PBA | distritoId
- categoria: SENADORES | DIPUTADOS
- puesto: orden por `votos_pct` (desc)
- `mesas_pct` nunca retrocede entre ciclos (consistencia)

### 6) Integracion con vMix
1. En vMix, Data Sources > Add > CSV > selecciona `elecciones_datos.csv`.
2. Habilita Auto-Refresh.
3. Mapea columnas a tus Títulos/GT (ej.: `agrupacion`, `votos_pct`, `mesas_pct`).

### 7) Solucion de problemas
- "Could not find a version that satisfies ... requeriments.txt": es `requirements.txt` y debe usarse con `-r`.
- "La respuesta de /createtoken no contiene ...": verifica usuario/pass o setea `RESULTADOS_TOKEN`.
- `elecciones_datos.csv` no aparece: revisa `logs/run.log` por errores, conecta a internet y valida credenciales.
- PBA no aparece: valida `RESULTADOS_PBA_NAME` coincida con el nombre exacto del catalogo.

### 8) Desarrollo
- Codigo principal: `api_elecciones_datos.py`.
- Logs en `logs/`.
- Dependencias en `requirements.txt`.

# elecciones