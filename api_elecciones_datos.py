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
	}
	resp = requests.get(url, headers=headers, timeout=timeout_s)
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
				snippet = (resp.text or "")[:256].replace("\n", " ")
				f.write(f"text_snippet={snippet}\n")
			f.write("\n")
	except Exception:
		pass
	raise RuntimeError("La respuesta de /createtoken no contiene un token reconocible")


def get_categorias(base_url: str, token: str, timeout_s: float = 20.0) -> dict:
	url = f"{base_url}/catalogo/getCategorias"
	headers = {"Authorization": f"Bearer {token}"}
	resp = requests.get(url, headers=headers, timeout=timeout_s)
	resp.raise_for_status()
	return resp.json() if resp.content else {}


def get_catalogo(base_url: str, token: str, categoria_id: int, timeout_s: float = 20.0) -> dict:
	url = f"{base_url}/catalogo/getCatalogo"
	headers = {"Authorization": f"Bearer {token}"}
	params = {"categoriaId": str(categoria_id)}
	resp = requests.get(url, headers=headers, params=params, timeout=timeout_s)
	resp.raise_for_status()
	return resp.json() if resp.content else {}


def authorized_get(base_url: str, token_provider, path: str, params: dict | None = None, timeout_s: float = 20.0) -> requests.Response:
	# token_provider(): devuelve token actual y permite renovarlo si 401
	url = f"{base_url}{path}"
	token = token_provider()
	headers = {"Authorization": f"Bearer {token}"}
	resp = requests.get(url, headers=headers, params=params, timeout=timeout_s)
	if resp.status_code == 401:
		# Intentar refrescar y reintentar una vez
		token_provider(refresh=True)
		headers = {"Authorization": f"Bearer {token_provider()}"}
		resp = requests.get(url, headers=headers, params=params, timeout=timeout_s)
	resp.raise_for_status()
	return resp


def get_resultados(base_url: str, token_provider, categoria_id: int, distrito_id: str | None) -> dict:
	params = {"categoriaId": str(categoria_id)}
	if distrito_id:
		params["distritoId"] = distrito_id
	resp = authorized_get(base_url, token_provider, "/resultados/getResultados", params=params, timeout_s=30.0)
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
	# Reemplazo atómico
	tmp_path.replace(csv_path)


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


def build_rows_nacional(res: dict, categoria_name: str, ts_iso: str, photos_base: str, photos_default: str, fotos_map: dict[str, str]) -> tuple[list[list[str]], float]:
	# Filtrar FP y LLA si existen; si faltan, completar con 0.00
	partidos = (res.get("valoresTotalizadosPositivos") or []) if isinstance(res, dict) else []
	def norm(name: str) -> str:
		return (name or "").strip().upper()

	def foto_for(item: dict) -> str:
		pid = str(item.get("idAgrupacion") or item.get("id") or "").strip()
		pname = str(item.get("nombreAgrupacion") or item.get("nombre") or "").strip()
		key = pid or pname
		cand = fotos_map.get(key) or fotos_map.get(pname) or fotos_map.get(pid)
		if cand:
			return str(Path(photos_base) / cand) if photos_base else cand
		return str(Path(photos_base) / photos_default) if photos_base and photos_default else photos_default

	# Buscar FP y LLA por nombre o id conocidos
	wanted_tags = ["FP", "LLA"]
	found: list[dict] = []
	for p in partidos:
		name = norm(str(p.get("nombreAgrupacion") or p.get("nombre") or ""))
		if any(tag == name or tag in name for tag in wanted_tags):
			found.append(p)

	# Backfill si faltan
	labels = {"FP": None, "LLA": None}
	for p in found:
		name = norm(str(p.get("nombreAgrupacion") or p.get("nombre") or ""))
		if "FP" in name:
			labels["FP"] = p
		if "LLA" in name:
			labels["LLA"] = p

	rows: list[list[str]] = []
	order = ["FP", "LLA"]
	mesas_pct = extract_mesas_pct(res)
	for idx, tag in enumerate(order, start=1):
		p = labels.get(tag)
		if p is None:
			rows.append(["NACIONAL", "AR", "", categoria_name, str(idx), "", tag, "0.00", truncate_2(mesas_pct), "", ts_iso])
			continue
		pct = float(p.get("votosPorcentaje") or p.get("porcentajeVotos") or 0.0)
		pid = str(p.get("idAgrupacion") or "")
		pname = str(p.get("nombreAgrupacion") or tag)
		rows.append([
			"NACIONAL",
			"AR",
			"",
			categoria_name,
			str(idx),
			pid,
			pname,
			truncate_2(pct),
			truncate_2(mesas_pct),
			foto_for(p),
			ts_iso,
		])
	return rows, mesas_pct


def build_rows_top4(res: dict, ambito: str, ambito_id: str, provincia: str, categoria_name: str, ts_iso: str, photos_base: str, photos_default: str, fotos_map: dict[str, str]) -> tuple[list[list[str]], float]:
	items = (res.get("valoresTotalizadosPositivos") or []) if isinstance(res, dict) else []
	mesas_pct = extract_mesas_pct(res)

	def foto_for(item: dict) -> str:
		pid = str(item.get("idAgrupacion") or item.get("id") or "").strip()
		pname = str(item.get("nombreAgrupacion") or item.get("nombre") or "").strip()
		key = pid or pname
		cand = fotos_map.get(key) or fotos_map.get(pname) or fotos_map.get(pid)
		if cand:
			return str(Path(photos_base) / cand) if photos_base else cand
		return str(Path(photos_base) / photos_default) if photos_base and photos_default else photos_default

	def pct_of(x: dict) -> float:
		return float(x.get("votosPorcentaje") or x.get("porcentajeVotos") or 0.0)

	# Ordenar desc y tomar top 4
	sorted_items = sorted(items, key=pct_of, reverse=True)[:4]
	rows: list[list[str]] = []
	for i, it in enumerate(sorted_items, start=1):
		pct = pct_of(it)
		pid = str(it.get("idAgrupacion") or "")
		pname = str(it.get("nombreAgrupacion") or it.get("nombre") or "")
		rows.append([
			ambito,
			ambito_id,
			provincia,
			categoria_name,
			str(i),
			pid,
			pname,
			truncate_2(pct),
			truncate_2(mesas_pct),
			foto_for(it),
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


def main() -> int:
	# Carga .env si existe
	load_dotenv()

	logs_dir = ensure_logs_dir()
	base_url = get_base_url()

	# Token: usar RESULTADOS_TOKEN si existe; si no, crearlo con username/password
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
			token = create_token(base_url, username, password)
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
	photos_default = os.getenv("FOTOS_DEFAULT_FILE", "")
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
				_token_cache = create_token(base_url, username, password)
			return _token_cache
		return _token_cache

	# Resolver catálogo para PBA y distritos por cada categoría disponible
	def resolve_pba_and_districts(cat_id: int) -> tuple[str | None, list[dict]]:
		catalogo = get_catalogo(base_url, token_provider(), cat_id)
		items = catalogo if isinstance(catalogo, list) else catalogo.get("distritos") or catalogo
		pba_id: str | None = None
		dists: list[dict] = []
		if isinstance(items, list):
			for d in items:
				nombre = str(d.get("nombre", ""))
				did = str(d.get("distritoId", ""))
				if not did:
					continue
				if nombre.strip().lower() == os.getenv("RESULTADOS_PBA_NAME", "Provincia de Buenos Aires").strip().lower():
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

			# NACIONAL: FP/LLA si existen, backfill si faltan
			try:
				res_nac = get_resultados(base_url, token_provider, cid, None)
				ambito_key = f"NACIONAL|AR|{cname}"
				amb_rows, mesas_pct_val = build_rows_nacional(res_nac, cname, cycle_ts, photos_base, photos_default, fotos_map)
				amb_rows = enforce_mesas_monotonic(ambito_key, amb_rows, mesas_pct_val, prev_mesas_pct_by_key)
				rows.extend(amb_rows)
				ambitos_ok += 1
			except Exception as e:  # noqa: BLE001
				errors.append(f"nacional cid={cid}: {e}")
				rows.extend(prev_rows_by_key.get(f"NACIONAL|AR|{cname}", []))

			# PBA top-4
			if pba_id:
				try:
					res_pba = get_resultados(base_url, token_provider, cid, pba_id)
					ambito_key = f"PBA|PBA|{cname}"
					amb_rows, mesas_pct_val = build_rows_top4(res_pba, "PBA", "PBA", "Buenos Aires", cname, cycle_ts, photos_base, photos_default, fotos_map)
					amb_rows = enforce_mesas_monotonic(ambito_key, amb_rows, mesas_pct_val, prev_mesas_pct_by_key)
					rows.extend(amb_rows)
					ambitos_ok += 1
				except Exception as e:  # noqa: BLE001
					errors.append(f"pba cid={cid}: {e}")
					rows.extend(prev_rows_by_key.get(f"PBA|PBA|{cname}", []))

			# Provincias top-4
			for d in distritos or []:
				did = d.get("distritoId")
				dname = d.get("nombre")
				if not did or did == pba_id:
					continue
				try:
					res_dist = get_resultados(base_url, token_provider, cid, did)
					ambito_key = f"PROVINCIA|{did}|{cname}"
					amb_rows, mesas_pct_val = build_rows_top4(res_dist, "PROVINCIA", did, dname, cname, cycle_ts, photos_base, photos_default, fotos_map)
					amb_rows = enforce_mesas_monotonic(ambito_key, amb_rows, mesas_pct_val, prev_mesas_pct_by_key)
					rows.extend(amb_rows)
					ambitos_ok += 1
				except Exception as e:  # noqa: BLE001
					errors.append(f"prov did={did} cid={cid}: {e}")
					rows.extend(prev_rows_by_key.get(f"PROVINCIA|{did}|{cname}", []))

		# Guardar estado previo para fallback del proximo ciclo
		# Claves por ambito estan ya definidas dentro de los helpers (usamos mismas claves)
		prev_rows_by_key = index_rows_by_key(rows)

		# Escribir CSV de forma atómica
		try:
			atomic_write_csv(rows, csv_path)
		except Exception as e:  # noqa: BLE001
			errors.append(f"csv: {e}")

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


