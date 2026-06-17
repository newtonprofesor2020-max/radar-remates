from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from postgrest.exceptions import APIError
from pydantic import BaseModel

from app.calculos import calcular_oportunidad
from app.geocoding import obtener_ubicacion
from app.supabase_client import supabase

app = FastAPI()

# Usuario temporal para el MVP.
# Supabase espera UUID en favoritos.usuario_id, por eso no usamos "demo".
USUARIO_DEMO = "00000000-0000-0000-0000-000000000001"


def obtener_usuario_demo(usuario_id: Optional[str] = None) -> str:
    """Normaliza el usuario temporal de favoritos.

    Permite que el frontend no envíe usuario_id y también evita errores
    si alguna llamada antigua todavía manda usuario_id=demo.
    """
    if usuario_id is None or str(usuario_id).strip() == "" or str(usuario_id).strip().lower() == "demo":
        return USUARIO_DEMO
    return str(usuario_id).strip()


class RevisionInmueble(BaseModel):
    estado: str = "Pendiente"
    observaciones: Optional[str] = ""
    apto_para_ofertar: bool = False


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Utilidades de cálculo
# -----------------------------
def numero(valor):
    try:
        if valor is None or valor == "":
            return 0
        return float(valor)
    except (TypeError, ValueError):
        return 0


def calcular_score_desde_margen(margen, convocatoria=""):
    score = round(margen * 2.1)
    convocatoria_texto = str(convocatoria or "").lower()

    if "segunda" in convocatoria_texto:
        score += 8

    if "tercera" in convocatoria_texto:
        score += 12

    if score < 0:
        score = 0

    if score > 95:
        score = 95

    return score


def procesar_inmueble_para_api(item: dict):
    item = dict(item or {})

    precio_base = numero(
        item.get("precio_base")
        or item.get("precio_remate")
        or item.get("precio")
    )

    valor_mercado = numero(
        item.get("valor_mercado")
        or item.get("valor_comercial")
        or item.get("tasacion")
    )

    # Fallback temporal: si no hay valor mercado, estima con precio base x 1.5.
    # Más adelante conviene reemplazarlo por comparables reales de mercado.
    if valor_mercado <= 0 and precio_base > 0:
        valor_mercado = round(precio_base * 1.5)

    calculo = calcular_oportunidad(
        valor_mercado=valor_mercado,
        precio_base=precio_base,
    )

    margen = round(numero(calculo["porcentaje_descuento"]))
    ganancia = round(numero(calculo["ganancia_estimada"]))

    score_actual = numero(item.get("score") or item.get("puntaje"))

    score = (
        int(score_actual)
        if score_actual > 0
        else calcular_score_desde_margen(margen, item.get("convocatoria"))
    )

    riesgo = item.get("riesgo")

    if not riesgo:
        if score >= 80:
            riesgo = "Bajo"
        elif score >= 60:
            riesgo = "Medio"
        else:
            riesgo = "Alto"

    item.update({
        "precio_base": precio_base,
        "valor_mercado": valor_mercado,
        "ganancia_estimada": ganancia,
        "porcentaje_descuento": margen,
        "score": score,
        "riesgo": riesgo,
        "estado": item.get("estado") or "Activo",
    })

    return item


# -----------------------------
# Salud / pruebas
# -----------------------------
@app.get("/")
def home():
    return {"mensaje": "Backend Radar Remates funcionando correctamente"}


@app.get("/test-db")
def test_db():
    response = (
        supabase
        .table("inmuebles")
        .select("*")
        .limit(5)
        .execute()
    )

    return response.data


# -----------------------------
# Revisión del inmueble
# -----------------------------
@app.get("/inmueble/{inmueble_id}/revision")
def obtener_revision(inmueble_id: int):
    response = (
        supabase
        .table("revisiones_inmueble")
        .select("*")
        .eq("inmueble_id", inmueble_id)
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )

    if not response.data:
        return {
            "inmueble_id": inmueble_id,
            "estado": "Pendiente",
            "observaciones": "",
            "apto_para_ofertar": False,
        }

    return response.data[0]


@app.post("/inmueble/{inmueble_id}/revision")
def guardar_revision(inmueble_id: int, revision: RevisionInmueble):
    inmueble = (
        supabase
        .table("inmuebles")
        .select("id")
        .eq("id", inmueble_id)
        .limit(1)
        .execute()
    )

    if not inmueble.data:
        raise HTTPException(status_code=404, detail="Inmueble no encontrado")

    revision_actual = (
        supabase
        .table("revisiones_inmueble")
        .select("*")
        .eq("inmueble_id", inmueble_id)
        .limit(1)
        .execute()
    )

    datos_revision = {
        "inmueble_id": inmueble_id,
        "estado": revision.estado,
        "observaciones": revision.observaciones,
        "apto_para_ofertar": revision.apto_para_ofertar,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if revision_actual.data:
        revision_id = revision_actual.data[0]["id"]

        response = (
            supabase
            .table("revisiones_inmueble")
            .update(datos_revision)
            .eq("id", revision_id)
            .execute()
        )

        return {
            "mensaje": "Revisión actualizada correctamente",
            "revision": response.data[0] if response.data else None,
        }

    response = (
        supabase
        .table("revisiones_inmueble")
        .insert(datos_revision)
        .execute()
    )

    return {
        "mensaje": "Revisión creada correctamente",
        "revision": response.data[0] if response.data else None,
    }


# -----------------------------
# Inmuebles
# -----------------------------
def guardar_inmueble(data: dict):
    precio_base = data.get("precio_base") or data.get("precio_remate") or 0
    valor_mercado = (
        data.get("valor_mercado")
        or data.get("valor_comercial")
        or data.get("tasacion")
        or 0
    )

    calculo = calcular_oportunidad(
        valor_mercado=valor_mercado,
        precio_base=precio_base,
    )

    ubicacion = obtener_ubicacion(
        direccion=data.get("direccion"),
        distrito=data.get("distrito"),
    )

    inmueble = {
        "expediente": data.get("expediente"),
        "numero_remate": data.get("numero_remate") or data.get("remate"),
        "distrito": data.get("distrito"),
        "direccion": data.get("direccion"),
        "tipo": data.get("tipo"),
        "area": data.get("area"),
        "convocatoria": data.get("convocatoria"),
        "fecha_presentacion": data.get("fecha_presentacion") or data.get("fecha_remate"),
        "hora_presentacion": data.get("hora_presentacion") or data.get("hora_remate"),
        "juzgado": data.get("juzgado"),
        "tasacion": data.get("tasacion"),
        "precio_base": precio_base,
        "valor_mercado": valor_mercado,
        "ganancia_estimada": calculo["ganancia_estimada"],
        "porcentaje_descuento": calculo["porcentaje_descuento"],
        "nivel_oportunidad": calculo["nivel_oportunidad"],
        "estrellas": calculo["estrellas"],
        "score": data.get("score") or 0,
        "riesgo": data.get("riesgo"),
        "estado": data.get("estado") or "Activo",
        "fuente": data.get("fuente") or "REMAJU",
        "url_detalle": data.get("url_detalle") or data.get("url_original"),
        "descripcion": data.get("descripcion") or data.get("texto_completo"),
        "lat": ubicacion["lat"],
        "lng": ubicacion["lng"],
        "ubicacion_tipo": ubicacion["ubicacion_tipo"],
        "direccion_completa": ubicacion["direccion_completa"],
    }

    response = (
        supabase
        .table("inmuebles")
        .insert(inmueble)
        .execute()
    )

    return response.data


@app.post("/inmuebles")
def crear_inmueble(data: dict):
    return guardar_inmueble(data)


@app.get("/ranking")
def ranking():
    response = (
        supabase
        .table("inmuebles")
        .select("*")
        .order("score", desc=True)
        .limit(500)
        .execute()
    )

    return [procesar_inmueble_para_api(item) for item in response.data]


@app.get("/inmueble/{inmueble_id}")
def obtener_inmueble(inmueble_id: int):
    response = (
        supabase
        .table("inmuebles")
        .select("*")
        .eq("id", inmueble_id)
        .single()
        .execute()
    )

    if not response.data:
        raise HTTPException(status_code=404, detail="Inmueble no encontrado")

    return procesar_inmueble_para_api(response.data)


# Mantengo este endpoint viejo para no romper tu frontend si alguna pantalla antigua lo llama.
# La revisión profesional debe usar /inmueble/{id}/revision.
@app.put("/inmueble/{inmueble_id}")
def actualizar_revision(inmueble_id: int, data: dict):
    try:
        response = (
            supabase
            .table("inmuebles")
            .update({
                "estado_revision": data.get("estado_revision"),
                "observaciones": data.get("observaciones"),
                "apto_para_ofertar": data.get("apto_para_ofertar"),
            })
            .eq("id", inmueble_id)
            .execute()
        )

        return {
            "mensaje": "Revisión actualizada correctamente",
            "data": response.data[0] if response.data else None,
        }

    except APIError as error:
        return {"error": str(error)}


# -----------------------------
# Favoritos
# -----------------------------
@app.get("/favoritos/ids")
def obtener_ids_favoritos(usuario_id: Optional[str] = None):
    usuario = obtener_usuario_demo(usuario_id)

    response = (
        supabase
        .table("favoritos")
        .select("inmueble_id")
        .eq("usuario_id", usuario)
        .execute()
    )

    return [item["inmueble_id"] for item in response.data]




@app.get("/favoritos")
def listar_favoritos(usuario_id: str = USUARIO_DEMO):
    favoritos_response = (
        supabase
        .table("favoritos")
        .select("*")
        .eq("usuario_id", usuario_id)
        .order("created_at", desc=True)
        .execute()
    )

    favoritos_data = favoritos_response.data or []

    if not favoritos_data:
        return []

    inmueble_ids = [
        item["inmueble_id"]
        for item in favoritos_data
        if item.get("inmueble_id") is not None
    ]

    if not inmueble_ids:
        return []

    inmuebles_response = (
        supabase
        .table("inmuebles")
        .select("*")
        .in_("id", inmueble_ids)
        .execute()
    )

    inmuebles_data = inmuebles_response.data or []

    inmuebles_por_id = {
        item["id"]: item
        for item in inmuebles_data
    }

    resultado = []

    for favorito in favoritos_data:
        inmueble_id = favorito.get("inmueble_id")
        inmueble = inmuebles_por_id.get(inmueble_id)

        if not inmueble:
            continue

        inmueble_procesado = procesar_inmueble_para_api(inmueble)
        inmueble_procesado["favorito_id"] = favorito.get("id")
        inmueble_procesado["favorito_created_at"] = favorito.get("created_at")
        resultado.append(inmueble_procesado)

    return resultado





@app.post("/favoritos/{inmueble_id}")
def agregar_favorito(inmueble_id: int, usuario_id: Optional[str] = None):
    usuario = obtener_usuario_demo(usuario_id)

    inmueble = (
        supabase
        .table("inmuebles")
        .select("id")
        .eq("id", inmueble_id)
        .limit(1)
        .execute()
    )

    if not inmueble.data:
        raise HTTPException(status_code=404, detail="Inmueble no encontrado")

    favorito_existente = (
        supabase
        .table("favoritos")
        .select("*")
        .eq("inmueble_id", inmueble_id)
        .eq("usuario_id", usuario)
        .limit(1)
        .execute()
    )

    if favorito_existente.data:
        return {
            "mensaje": "El inmueble ya estaba en favoritos",
            "favorito": favorito_existente.data[0],
        }

    response = (
        supabase
        .table("favoritos")
        .insert({
            "inmueble_id": inmueble_id,
            "usuario_id": usuario,
        })
        .execute()
    )

    return {
        "mensaje": "Favorito agregado correctamente",
        "favorito": response.data[0] if response.data else None,
    }


@app.delete("/favoritos/{inmueble_id}")
def eliminar_favorito(inmueble_id: int, usuario_id: Optional[str] = None):
    usuario = obtener_usuario_demo(usuario_id)

    response = (
        supabase
        .table("favoritos")
        .delete()
        .eq("inmueble_id", inmueble_id)
        .eq("usuario_id", usuario)
        .execute()
    )

    return {
        "mensaje": "Favorito eliminado correctamente",
        "eliminado": response.data,
    }
