import os
import json
import time
import csv
from pathlib import Path
from datetime import datetime, timezone

import requests

try:
	from dotenv import load_dotenv
except ImportError:  # Permite ejecutar aunque no esté instalada, si las vars ya están en el entorno
	def load_dotenv(*_args, **_kwargs):  # type: ignore
		return False


def ensure_logs_dir() -> Path:
	logs_dir = Path("logs")
	logs_dir.mkdir(parents=True, exist_ok=True)
	return logs_dir


def iso_now() -> str:
	return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_base_url() -> str:
	base_url = os.getenv("RESULTADOS_BASE_URL", "https://api.resultados.gob.ar/api").rstrip("/")
	return base_url


def _extract_token_from_obj(obj: dict) -> str | None:
	# Busca token en claves comunes y estructuras anidadas
	for key in ("access_token", "token", "accessToken", "AccessToken"):
		val = obj.get(key)
		if isinstance(val, str) and val.strip():
			return val.strip()
	for nested_key in ("data", "result", "resultado"):
		nested = obj.get(nested_key)
		if isinstance(nested, dict):
			t = _extract_token_from_obj(nested)
			if t:
				return t
	return None


def create_token(base_url: str, username: str, password: str, timeout_s: float = 15.0) -> str:
	url = f"{base_url}/createtoken"
	headers = {
		"username": username,
		"password": password,
		"Accept": "application/json",
		"Content-Type": "application/json",
		"User-Agent": "elecciones-bot/1.0",
	}
	resp = requests.get(url, headers=headers, timeout=timeout_s)
	# Log seguro (sin cuerpo ni secretos)
	try:
		log_http_event("/createtoken", url, None, resp.status_code, resp.headers.get("Content-Type"), None, note="initial", content_length=len(resp.content) if resp.content is not None else None)
	except Exception:
		pass
	resp.raise_for_status()
	# Intentar parsear JSON
	data: dict | None = None
	if resp.content:
		try:
			parsed = resp.json()
			if isinstance(parsed, dict):
				data = parsed
		except ValueError:
			data = None
	# 1) Buscar en JSON (claves comunes y anidados)
	if isinstance(data, dict):
		token = _extract_token_from_obj(data)
		if token:
			return token
	# 2) Fallback: texto plano
	body_text = (resp.text or "").strip()
	if body_text:
		# Remover posibles envolturas simples
		if body_text.startswith("Bearer "):
			body_text = body_text[len("Bearer ") :].strip()
		if (body_text.startswith('"') and body_text.endswith('"')) or (
			body_text.startswith("'") and body_text.endswith("'")
		):
			body_text = body_text[1:-1].strip()
		if body_text:
			return body_text
	# 3) Si no se encuentra, escribir un log de depuración mínimo sin secretos
	try:
		logs_dir = ensure_logs_dir()
		debug_path = logs_dir / "createtoken_debug.log"
		with debug_path.open("a", encoding="utf-8") as f:
			f.write(f"[{iso_now()}] createtoken sin token: content_type={resp.headers.get('Content-Type','')}, status={resp.status_code}\n")
			if isinstance(data, dict):
				f.write(f"json_keys={list(data.keys())}\n")
			else:
				f.write("text_snippet=\n")
			f.write("\n")
	except Exception:
		pass
	raise RuntimeError("La respuesta de /createtoken no contiene un token reconocible")


def get_token_with_retries(base_url: str, username: str, password: str, max_retries: int = 4) -> str:
	wait_s = 1.0
	last_exc: Exception | None = None
	for attempt in range(1, max_retries + 1):
		try:
			return create_token(base_url, username, password)
		except requests.HTTPError as e:
			last_exc = e
			status = getattr(e.response, "status_code", None)
			try:
				log_http_event("/createtoken", f"{base_url}/createtoken", None, status, None, None, note=f"retry_{attempt}")
			except Exception:
				pass
			if status and status in (429, 500, 502, 503, 504):
				time.sleep(wait_s)
				wait_s = min(wait_s * 2.0, 16.0)
				continue
			else:
				raise
		except Exception as e:  # noqa: BLE001
			last_exc = e
			time.sleep(wait_s)
			wait_s = min(wait_s * 2.0, 16.0)
			continue
	if last_exc:
		raise last_exc
	raise RuntimeError("No se pudo obtener token tras reintentos")


def get_categorias(base_url: str, token: str, timeout_s: float = 20.0) -> dict:
	url = f"{base_url}/catalogo/getCategorias"
	headers = {
		"Authorization": f"Bearer {token}",
		"Token": token,
		"Accept": "application/json",
		"Content-Type": "application/json",
		"User-Agent": "elecciones-bot/1.0",
	}
	resp = requests.get(url, headers=headers, timeout=timeout_s)
	try:
		log_http_event("/catalogo/getCategorias", url, None, resp.status_code, resp.headers.get("Content-Type"), resp.text, note="initial", content_length=len(resp.content) if resp.content is not None else None)
	except Exception:
		pass
	resp.raise_for_status()
	return resp.json() if resp.content else {}


def get_catalogo(base_url: str, token: str, categoria_id: int, timeout_s: float = 20.0) -> dict:
	url = f"{base_url}/catalogo/getCatalogo"
	headers = {
		"Authorization": f"Bearer {token}",
		"Token": token,
		"Accept": "application/json",
		"Content-Type": "application/json",
		"User-Agent": "elecciones-bot/1.0",
	}
	params = {"categoriaId": str(categoria_id)}
	resp = requests.get(url, headers=headers, params=params, timeout=timeout_s)
	try:
		log_http_event("/catalogo/getCatalogo", url, params, resp.status_code, resp.headers.get("Content-Type"), resp.text, note="initial", content_length=len(resp.content) if resp.content is not None else None)
	except Exception:
		pass
	resp.raise_for_status()
	return resp.json() if resp.content else {}


def log_http_event(path: str, url: str, params: dict | None, status: int | None, content_type: str | None, body_snippet: str | None, note: str | None = None, content_length: int | None = None) -> None:
	try:
		logs_dir = ensure_logs_dir()
		log_path = logs_dir / "http.log"
		with log_path.open("a", encoding="utf-8") as f:
			note_text = f" note={note}" if note else ""
			params_text = json.dumps(params or {}, ensure_ascii=False)
			ct = content_type or ""
			snippet = (body_snippet or "")[:512].replace("\n", " ")
			f.write(f"[{iso_now()}] path={path}{note_text}\n")
			f.write(f"url={url}\nparams={params_text}\nstatus={status} content_type={ct} length={content_length}\n")
			if snippet:
				f.write(f"snippet={snippet}\n")
			f.write("\n")
	except Exception:
		pass


def authorized_get(base_url: str, token_provider, path: str, params: dict | None = None, timeout_s: float = 20.0) -> requests.Response:
	# token_provider(): devuelve token actual y permite renovarlo si 401
	url = f"{base_url}{path}"
	token = token_provider()
	headers = {
		"Authorization": f"Bearer {token}",
		"Token": token,
		"Accept": "application/json",
		"Content-Type": "application/json",
		"User-Agent": "elecciones-bot/1.0",
	}
	resp = requests.get(url, headers=headers, params=params, timeout=timeout_s)
	# Log intento inicial
	try:
		log_http_event(path, url, params, resp.status_code, resp.headers.get("Content-Type"), resp.text, note="initial", content_length=len(resp.content) if resp.content is not None else None)
	except Exception:
		pass
	if resp.status_code == 401:
		# Intentar refrescar y reintentar una vez
		token_provider(refresh=True)
		headers = {
			"Authorization": f"Bearer {token_provider()}",
			"Token": token_provider(),
			"Accept": "application/json",
			"Content-Type": "application/json",
			"User-Agent": "elecciones-bot/1.0",
		}
		resp = requests.get(url, headers=headers, params=params, timeout=timeout_s)
		try:
			log_http_event(path, url, params, resp.status_code, resp.headers.get("Content-Type"), resp.text, note="retry_after_401", content_length=len(resp.content) if resp.content is not None else None)
		except Exception:
			pass
	resp.raise_for_status()
	return resp


def get_resultados(base_url: str, token_provider, categoria_id: int, distrito_id: str | None) -> dict:
	params = {"categoriaId": str(categoria_id)}
	if distrito_id:
		params["distritoId"] = distrito_id
	resp = authorized_get(base_url, token_provider, "/resultados/getResultados", params=params, timeout_s=30.0)
	# Reintento si 200 con contenido vacío o sin JSON
	if not resp.content or not (resp.headers.get("Content-Type") or "").lower().startswith("application/json"):
		try:
			log_http_event("/resultados/getResultados", f"{base_url}/resultados/getResultados", params, resp.status_code, resp.headers.get("Content-Type"), resp.text, note="retry_empty_wait_1s")
		except Exception:
			pass
		time.sleep(1)
		resp = authorized_get(base_url, token_provider, "/resultados/getResultados", params=params, timeout_s=30.0)
		try:
			log_http_event("/resultados/getResultados", f"{base_url}/resultados/getResultados", params, resp.status_code, resp.headers.get("Content-Type"), resp.text, note="retry_empty_after_1s")
		except Exception:
			pass
	return resp.json() if resp.content else {}


def get_estado_recuento(base_url: str, token_provider, categoria_id: int, distrito_id: str | None) -> dict:
	params = {"categoriaId": str(categoria_id)}
	if distrito_id:
		params["distritoId"] = distrito_id
	resp = authorized_get(base_url, token_provider, "/estados/estadoRecuento", params=params, timeout_s=20.0)
	return resp.json() if resp.content else {}


def write_categorias_log(categorias_obj: dict, logs_dir: Path) -> Path:
	log_path = logs_dir / "categorias.log"
	# No registrar secretos. Solo timestamp y el JSON de categorías.
	with log_path.open("a", encoding="utf-8") as f:
		f.write(f"[{iso_now()}] categorias\n")
		f.write(json.dumps(categorias_obj, ensure_ascii=False, indent=2))
		f.write("\n\n")
	return log_path


def friendly_header() -> list[str]:
	return [
		"ambito",
		"ambito_id",
		"provincia",
		"categoria",
		"puesto",
		"agrupacion_id",
		"agrupacion",
		"votos_pct",
		"mesas_pct",
		"foto",
		"ts_iso",
	]


def truncate_2(x: float) -> str:
	# Truncar sin redondear a 2 decimales
	neg = x < 0
	val = abs(x)
	trunc = int(val * 100.0) / 100.0
	res = -trunc if neg else trunc
	return f"{res:.2f}"


def parse_categoria_nombre(nombre: str) -> str:
	# Abreviar a SENADORES / DIPUTADOS
	name = (nombre or "").upper()
	if "SENADOR" in name:
		return "SENADORES"
	if "DIPUTADO" in name:
		return "DIPUTADOS"
	return nombre


def atomic_write_csv(rows: list[list[str]], csv_path: Path) -> None:
	tmp_path = csv_path.with_suffix(".tmp")
	with tmp_path.open("w", newline="", encoding="utf-8") as f:
		writer = csv.writer(f)
		writer.writerow(friendly_header())
		writer.writerows(rows)
	# Reemplazo atómico con fallback para Windows si el archivo está bloqueado
	try:
		tmp_path.replace(csv_path)
	except Exception as e:  # noqa: BLE001
		try:
			fallback_path = csv_path.with_suffix(".fallback.csv")
			# Intentar reemplazar fallback
			if fallback_path.exists():
				fallback_path.unlink(missing_ok=True)
			tmp_path.replace(fallback_path)
			# Loggear advertencia
			try:
				logs_dir = ensure_logs_dir()
				with (logs_dir / "run.log").open("a", encoding="utf-8") as lf:
					lf.write(f"[{iso_now()}] warn csv_replace_failed: {e}; wrote fallback={fallback_path.name}\n\n")
			except Exception:
				pass
		except Exception:
			# Si todo falla, intentar escribir directo (no atómico)
			with csv_path.open("w", newline="", encoding="utf-8") as f2:
				writer2 = csv.writer(f2)
				writer2.writerow(friendly_header())
				writer2.writerows(rows)


def extract_mesas_pct(payload: dict) -> float:
	# Intenta distintas rutas comunes
	# estadoRecuento.mesasTotalizadasPorcentaje o similar
	try:
		estado = payload.get("estadoRecuento") or {}
		val = estado.get("mesasTotalizadasPorcentaje")
		if isinstance(val, (int, float)):
			return float(val)
	except Exception:
		pass
	return 0.0


def _foto_for(item: dict, photos_base: str, photos_default: str, fotos_map: dict[str, str]) -> str:
	pid = str(item.get("idAgrupacion") or item.get("id") or "").strip()
	pname = str(item.get("nombreAgrupacion") or item.get("nombre") or "").strip()
	key = pid or pname
	cand = fotos_map.get(key) or fotos_map.get(pname) or fotos_map.get(pid)
	if cand:
		return str(Path(photos_base) / cand) if photos_base else cand
	return str(Path(photos_base) / photos_default) if photos_base and photos_default else photos_default


def get_mesas_pct_with_fallback(base_url: str, token_provider, categoria_id: int, distrito_id: str | None, res_payload: dict) -> float:
	val = extract_mesas_pct(res_payload)
	# Si está vacío o 0, intentar fallback al endpoint de estados
	if val <= 0.0:
		try:
			est = get_estado_recuento(base_url, token_provider, categoria_id, distrito_id)
			if isinstance(est, dict):
				estado = est.get("estadoRecuento") or est
				fval = estado.get("mesasTotalizadasPorcentaje") if isinstance(estado, dict) else None
				if isinstance(fval, (int, float)):
					return float(fval)
		except Exception:
			pass
	return float(val or 0.0)


def build_rows_full(res: dict, ambito: str, ambito_id: str, provincia: str, categoria_name: str, ts_iso: str, photos_base: str, photos_default: str, fotos_map: dict[str, str], base_url: str, token_provider, categoria_id: int, distrito_id: str | None) -> tuple[list[list[str]], float]:
	items = (res.get("valoresTotalizadosPositivos") or []) if isinstance(res, dict) else []
	mesas_pct = get_mesas_pct_with_fallback(base_url, token_provider, categoria_id, distrito_id, res)

	def pct_of(x: dict) -> float:
		return float(x.get("votosPorcentaje") or x.get("porcentajeVotos") or 0.0)

	sorted_items = sorted(items, key=pct_of, reverse=True)
	rows: list[list[str]] = []
	for it in sorted_items:
		pct = pct_of(it)
		pid = str(it.get("idAgrupacion") or "")
		pname = str(it.get("nombreAgrupacion") or it.get("nombre") or "")
		rows.append([
			ambito,
			ambito_id,
			provincia,
			categoria_name,
			"0",  # puesto se asigna luego
			pid,
			pname,
			truncate_2(pct),
			truncate_2(mesas_pct),
			_foto_for(it, photos_base, photos_default, fotos_map),
			ts_iso,
		])
	return rows, mesas_pct


def index_rows_by_key(rows: list[list[str]]) -> dict[str, list[list[str]]]:
	index: dict[str, list[list[str]]] = {}
	for r in rows:
		# clave: ambito|ambito_id|categoria
		key = f"{r[0]}|{r[1]}|{r[3]}"
		index.setdefault(key, []).append(r)
	return index


def enforce_mesas_monotonic(key: str, rows: list[list[str]], mesas_pct_current: float, prev_mesas_pct_by_key: dict[str, float]) -> list[list[str]]:
	prev = prev_mesas_pct_by_key.get(key)
	if prev is not None and mesas_pct_current < prev:
		# reemplazar mesas_pct en filas por prev
		for r in rows:
			r[8] = truncate_2(prev)
	else:
		prev_mesas_pct_by_key[key] = mesas_pct_current
	return rows


def _rank_and_stabilize_rows(ambito_key: str, rows: list[list[str]], prev_rows_by_key: dict[str, list[list[str]]]) -> list[list[str]]:
	# rows: mismas columnas; index relevantes: 4=puesto, 5=agrupacion_id, 6=agrupacion, 7=votos_pct, 8=mesas_pct, 9=foto
	prev_rows = prev_rows_by_key.get(ambito_key, [])
	def unique_key_of(r: list[str]) -> str:
		agr_id = (r[5] or "").strip()
		return agr_id or (r[6] or "").strip()

	prev_by_key: dict[str, list[str]] = {unique_key_of(r): r for r in prev_rows}
	curr_by_key: dict[str, list[str]] = {unique_key_of(r): r for r in rows}

	# Agregar filas 0.00 para fuerzas previas faltantes
	missing_keys = [k for k in prev_by_key.keys() if k not in curr_by_key]
	if rows:
		mesas_pct_current = rows[0][8]
		for k in missing_keys:
			pr = prev_by_key[k]
			stub = [
				rows[0][0],  # ambito
				rows[0][1],  # ambito_id
				rows[0][2],  # provincia
				rows[0][3],  # categoria
				"0",
				pr[5],  # agrupacion_id
				pr[6],  # agrupacion
				"0.00",
				mesas_pct_current,
				pr[9] if len(pr) > 9 else rows[0][9],
				rows[0][10],
			]
			rows.append(stub)

	# Deduplicar por agrupacion_id o nombre
	seen: set[str] = set()
	deduped: list[list[str]] = []
	for r in rows:
		uk = unique_key_of(r)
		if uk in seen:
			continue
		seen.add(uk)
		deduped.append(r)

	# Ordenar por votos_pct desc
	def votos_float(r: list[str]) -> float:
		try:
			return float(r[7])
		except Exception:
			return 0.0
	ordered = sorted(deduped, key=votos_float, reverse=True)

	# Asignar puesto 1..N
	for i, r in enumerate(ordered, start=1):
		r[4] = str(i)

	return ordered


def _validate_rows_per_ambito(ambito_key: str, rows: list[list[str]]) -> list[str]:
	warnings: list[str] = []
	# Suma de % <= 100
	total = 0.0
	for r in rows:
		try:
			total += float(r[7])
		except Exception:
			pass
	if total > 100.01:
		warnings.append(f"ambito {ambito_key}: suma_pct={total:.2f} > 100")
	# Duplicados por agrupacion_id
	seen_ids: set[str] = set()
	for r in rows:
		agr_id = (r[5] or "").strip()
		if agr_id:
			if agr_id in seen_ids:
				warnings.append(f"ambito {ambito_key}: duplicado agrupacion_id={agr_id}")
				break
			seen_ids.add(agr_id)
	return warnings


def main() -> int:
	# Carga .env si existe
	load_dotenv()

	logs_dir = ensure_logs_dir()
	base_url = get_base_url()

	# Token: usar RESULTADOS_TOKEN si existe; si no, crearlo con username/password y reintentos
	token = os.getenv("RESULTADOS_TOKEN")
	if not token:
		username = os.getenv("RESULTADOS_USERNAME")
		password = os.getenv("RESULTADOS_PASSWORD")
		if not username or not password:
			msg = (
				"Faltan credenciales en entorno: defina RESULTADOS_USERNAME y RESULTADOS_PASSWORD, "
				"o bien establezca RESULTADOS_TOKEN."
			)
			print(msg)
			return 2
		try:
			token = get_token_with_retries(base_url, username, password)
		except requests.HTTPError as e:
			print(f"Error HTTP al crear token: {e}")
			return 3
		except Exception as e:  # noqa: BLE001
			print(f"Error al crear token: {e}")
			return 4

	# Obtener categorías (para log inmediato y para resolver ids de SEN/DIP)
	try:
		categorias = get_categorias(base_url, token)
	except requests.HTTPError as e:
		print(f"Error HTTP al obtener categorias: {e}")
		return 5
	except Exception as e:  # noqa: BLE001
		print(f"Error al obtener categorias: {e}")
		return 6

	try:
		log_file = write_categorias_log(categorias, logs_dir)
		print(f"Categorias guardadas en: {log_file}")
	except Exception as e:  # noqa: BLE001
		print(f"Error al escribir log de categorias: {e}")
		# Continuar aunque falle el log

	# A partir de aquí: bucle de generación de CSV
	interval_s = int(os.getenv("RESULTADOS_INTERVAL_SECONDS", "30"))
	photos_base = os.getenv("FOTOS_BASE_PATH", "")
	photos_default = os.getenv("FOTOS_DEFAULT_FILE", "default.png")
	fotos_map_path = os.getenv("FOTOS_JSON_PATH", "")
	fotos_map: dict[str, str] = {}
	if fotos_map_path:
		try:
			with Path(fotos_map_path).open("r", encoding="utf-8") as f:
				fotos_map = json.load(f)
		except Exception:
			fotos_map = {}

	# Resolver ids de categorias de interes (SENADORES, DIPUTADOS)
	cat_items = categorias if isinstance(categorias, list) else categorias.get("categorias") or categorias
	sen_id: int | None = None
	dip_id: int | None = None
	if isinstance(cat_items, list):
		for c in cat_items:
			name = str(c.get("nombre", "")).upper()
			cid = c.get("categoriaId")
			if cid is None:
				continue
			if "SENADOR" in name:
				sen_id = int(cid)
			if "DIPUTADO" in name:
				dip_id = int(cid)

	if sen_id is None and dip_id is None:
		print("No se encontraron categorias de SENADORES/DIPUTADOS; finalizar.")
		return 0

	# Preparar proveedor de token con refresh on-demand
	username = os.getenv("RESULTADOS_USERNAME")
	password = os.getenv("RESULTADOS_PASSWORD")
	_token_cache = token

	def token_provider(refresh: bool = False) -> str:
		nonlocal _token_cache
		if refresh:
			if username and password:
				try:
					_token_cache = get_token_with_retries(base_url, username, password)
				except Exception:
					pass
			return _token_cache
		return _token_cache

	# Resolver catálogo para PBA y distritos por cada categoría disponible (según manual: lista de "ambitos")
	def resolve_pba_and_districts(cat_id: int) -> tuple[str | None, list[dict]]:
		catalogo = get_catalogo(base_url, token_provider(), cat_id)
		# El manual indica estructura con clave "ambitos" y dentro "codigoAmbitos" con "distritoId"
		items = catalogo if isinstance(catalogo, list) else catalogo.get("ambitos") or catalogo
		pba_id: str | None = None
		dists: list[dict] = []
		# Configurable: detectar PBA por id preferentemente, o por nombre
		pba_id_env = os.getenv("RESULTADOS_PBA_ID", "02").strip()
		pba_name_env = os.getenv("RESULTADOS_PBA_NAME", "Provincia de Buenos Aires").strip().lower()
		if isinstance(items, list):
			seen: set[str] = set()
			for a in items:
				# Tomar solo provincias (nivelId == 10)
				try:
					nivel_id = int(a.get("nivelId")) if a.get("nivelId") is not None else None
				except Exception:
					nivel_id = None
				if nivel_id != 10:
					continue
				nombre = str(a.get("nombre", ""))
				codigo = a.get("codigoAmbitos") or {}
				did = str(codigo.get("distritoId", "")) if isinstance(codigo, dict) else ""
				if not did or did in seen:
					continue
				seen.add(did)
				if did == pba_id_env or nombre.strip().lower() == pba_name_env:
					pba_id = did
				dists.append({"distritoId": did, "nombre": nombre})
		return pba_id, dists

	# Estado previo por ambito para consistencia y fallback
	prev_rows_by_key: dict[str, list[list[str]]] = {}
	prev_mesas_pct_by_key: dict[str, float] = {}

	csv_path = Path("elecciones_datos.csv")
	run_log = logs_dir / "run.log"

	while True:
		cycle_ts = iso_now()
		rows: list[list[str]] = []
		errors: list[str] = []
		ambitos_ok = 0

		for cid, cname in ((sen_id, "SENADORES"), (dip_id, "DIPUTADOS")):
			if cid is None:
				continue
			try:
				pba_id, distritos = resolve_pba_and_districts(cid)
			except Exception as e:  # noqa: BLE001
				errors.append(f"catalogo cid={cid}: {e}")
				continue

		# NACIONAL: todas las fuerzas, ranking completo
			try:
				res_nac = get_resultados(base_url, token_provider, cid, None)
				ambito_key = f"NACIONAL|AR|{cname}"
				amb_rows, mesas_pct_val = build_rows_full(
					res_nac,
					"NACIONAL",
					"AR",
					"",
					cname,
					cycle_ts,
					photos_base,
					photos_default,
					fotos_map,
					base_url,
					token_provider,
					cid,
					None,
				)
				if not amb_rows:
					errors.append(f"empty resultados nacional cid={cid}")
					fallback = prev_rows_by_key.get(ambito_key, [])
					rows.extend(fallback)
				else:
					amb_rows = _rank_and_stabilize_rows(ambito_key, amb_rows, prev_rows_by_key)
					amb_rows = enforce_mesas_monotonic(ambito_key, amb_rows, mesas_pct_val, prev_mesas_pct_by_key)
					rows.extend(amb_rows)
					ambitos_ok += 1
					# Escritura incremental: combinar filas procesadas del ciclo con fallback del ciclo previo
					try:
						partial_by_key = index_rows_by_key(rows)
						combined_by_key = dict(prev_rows_by_key)
						combined_by_key.update(partial_by_key)
						combined_rows: list[list[str]] = []
						for _k, _v in combined_by_key.items():
							combined_rows.extend(_v)
						if combined_rows:
							atomic_write_csv(combined_rows, csv_path)
					except Exception as e:  # noqa: BLE001
						errors.append(f"csv_incr_nacional: {e}")
			except Exception as e:  # noqa: BLE001
				errors.append(f"nacional cid={cid}: {e}")
				rows.extend(prev_rows_by_key.get(f"NACIONAL|AR|{cname}", []))

			# PBA: todas las fuerzas, ranking completo
			if pba_id:
				try:
					res_pba = get_resultados(base_url, token_provider, cid, pba_id)
					ambito_key = f"PBA|PBA|{cname}"
					pba_name = os.getenv("RESULTADOS_PBA_NAME", "Provincia de Buenos Aires")
					amb_rows, mesas_pct_val = build_rows_full(
						res_pba,
						"PBA",
						"PBA",
						pba_name,
						cname,
						cycle_ts,
						photos_base,
						photos_default,
						fotos_map,
						base_url,
						token_provider,
						cid,
						pba_id,
					)
					if not amb_rows:
						errors.append(f"empty resultados pba cid={cid}")
						fallback = prev_rows_by_key.get(ambito_key, [])
						rows.extend(fallback)
					else:
						amb_rows = _rank_and_stabilize_rows(ambito_key, amb_rows, prev_rows_by_key)
						amb_rows = enforce_mesas_monotonic(ambito_key, amb_rows, mesas_pct_val, prev_mesas_pct_by_key)
						rows.extend(amb_rows)
						ambitos_ok += 1
						# Escritura incremental
						try:
							partial_by_key = index_rows_by_key(rows)
							combined_by_key = dict(prev_rows_by_key)
							combined_by_key.update(partial_by_key)
							combined_rows: list[list[str]] = []
							for _k, _v in combined_by_key.items():
								combined_rows.extend(_v)
							if combined_rows:
								atomic_write_csv(combined_rows, csv_path)
						except Exception as e:  # noqa: BLE001
							errors.append(f"csv_incr_pba: {e}")
				except Exception as e:  # noqa: BLE001
					errors.append(f"pba cid={cid}: {e}")
					rows.extend(prev_rows_by_key.get(f"PBA|PBA|{cname}", []))

			# Provincias: todas las fuerzas, ranking completo (incluye Buenos Aires aunque ya se muestre PBA)
			for d in distritos or []:
				did = d.get("distritoId")
				dname = d.get("nombre")
				if not did:
					continue
				try:
					res_dist = get_resultados(base_url, token_provider, cid, did)
					ambito_key = f"PROVINCIA|{did}|{cname}"
					amb_rows, mesas_pct_val = build_rows_full(
						res_dist,
						"PROVINCIA",
						did,
						dname,
						cname,
						cycle_ts,
						photos_base,
						photos_default,
						fotos_map,
						base_url,
						token_provider,
						cid,
						did,
					)
					if not amb_rows:
						errors.append(f"empty resultados prov did={did} cid={cid}")
						fallback = prev_rows_by_key.get(ambito_key, [])
						rows.extend(fallback)
					else:
						amb_rows = _rank_and_stabilize_rows(ambito_key, amb_rows, prev_rows_by_key)
						amb_rows = enforce_mesas_monotonic(ambito_key, amb_rows, mesas_pct_val, prev_mesas_pct_by_key)
						rows.extend(amb_rows)
						ambitos_ok += 1
						# Escritura incremental por provincia
						try:
							partial_by_key = index_rows_by_key(rows)
							combined_by_key = dict(prev_rows_by_key)
							combined_by_key.update(partial_by_key)
							combined_rows: list[list[str]] = []
							for _k, _v in combined_by_key.items():
								combined_rows.extend(_v)
							if combined_rows:
								atomic_write_csv(combined_rows, csv_path)
						except Exception as e:  # noqa: BLE001
							errors.append(f"csv_incr_prov_{did}: {e}")
				except Exception as e:  # noqa: BLE001
					errors.append(f"prov did={did} cid={cid}: {e}")
					rows.extend(prev_rows_by_key.get(f"PROVINCIA|{did}|{cname}", []))

		# Guardar estado previo para fallback del proximo ciclo SOLO si hay filas nuevas
		# Evita perder el estado si el ciclo no devolvió resultados
		if rows:
			prev_rows_by_key = index_rows_by_key(rows)

		# Validaciones por ámbito
		by_key = index_rows_by_key(rows)
		for k, v in by_key.items():
			warnings = _validate_rows_per_ambito(k, v)
			for w in warnings:
				errors.append(f"warn {w}")

		# Escribir CSV de forma atómica solo si hay filas
		if rows:
			try:
				atomic_write_csv(rows, csv_path)
			except Exception as e:  # noqa: BLE001
				errors.append(f"csv: {e}")
		else:
			errors.append("skip write: no rows this cycle")

		# Log de ciclo
		try:
			with run_log.open("a", encoding="utf-8") as f:
				f.write(f"[{cycle_ts}] ambitos_ok={ambitos_ok} errores={len(errors)}\n")
				for err in errors:
					f.write(f"- {err}\n")
				f.write("\n")
		except Exception:
			pass

		time.sleep(max(1, interval_s))

	# no se alcanza
	# return 0


if __name__ == "__main__":
	exit(main())


