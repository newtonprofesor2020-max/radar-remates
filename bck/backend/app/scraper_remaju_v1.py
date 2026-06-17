from app.supabase_client import supabase
from app.calculos import calcular_oportunidad
from app.geocoding import obtener_ubicacion

import re


def calcular_score(porcentaje_descuento, nivel_oportunidad):
    """
    Calcula un score de 0 a 100 para ordenar oportunidades.
    """
    porcentaje = float(porcentaje_descuento or 0)
    nivel = str(nivel_oportunidad or "").lower()

    score = 0

    if porcentaje >= 45:
        score = 95
    elif porcentaje >= 30:
        score = 85
    elif porcentaje >= 15:
        score = 70
    elif porcentaje > 0:
        score = 55
    else:
        score = 0

    if "excelente" in nivel:
        score += 5
    elif "alta" in nivel:
        score += 3
    elif "baja" in nivel:
        score -= 5

    if score > 100:
        score = 100

    if score < 0:
        score = 0

    return score


def calcular_riesgo(score):
    """
    Clasifica riesgo según el score.
    """
    if score >= 85:
        return "Bajo"

    if score >= 70:
        return "Medio"

    return "Alto"


def limpiar_numero(valor):
    """
    Convierte valores vacíos o None a 0.
    """
    try:
        if valor is None or valor == "":
            return 0

        return float(valor)
    except Exception:
        return 0



def normalizar_url(valor):
    texto = str(valor or "").strip()

    if not texto:
        return None

    if texto.startswith("http://") or texto.startswith("https://"):
        return texto

    if texto.startswith("www."):
        return f"https://{texto}"

    return None


def obtener_url_detalle(data):
    """Obtiene el enlace real del aviso si el extractor lo envió en algún campo."""
    campos_posibles = [
        "url_detalle",
        "url_original",
        "url",
        "fuente_url",
        "aviso_url",
        "url_aviso",
        "remate_url",
        "url_remaju",
        "link",
        "enlace",
    ]

    for campo in campos_posibles:
        url = normalizar_url(data.get(campo))

        if url:
            return url

    # Fallback: si el enlace quedó dentro de descripcion/texto_completo.
    for valor in data.values():
        if not isinstance(valor, str):
            continue

        coincidencia = re.search(r"https?://[^\s)\]\}\"']+", valor)

        if coincidencia:
            return coincidencia.group(0)

    return None

def guardar_inmueble(data):
    """
    Guarda o actualiza un inmueble en Supabase.

    Este método:
    - Calcula oportunidad.
    - Calcula ganancia estimada.
    - Calcula porcentaje de descuento.
    - Calcula score.
    - Calcula riesgo.
    - Obtiene ubicación exacta o aproximada.
    - Guarda lat, lng, ubicacion_tipo y direccion_completa.
    """

    precio_base = limpiar_numero(
        data.get("precio_base")
        or data.get("precio_remate")
        or data.get("precio")
    )

    valor_mercado = limpiar_numero(
        data.get("valor_mercado")
        or data.get("valor_comercial")
        or data.get("tasacion")
    )

    tasacion = limpiar_numero(data.get("tasacion"))

    calculo = calcular_oportunidad(
        valor_mercado=valor_mercado,
        precio_base=precio_base,
    )

    ubicacion = obtener_ubicacion(
        direccion=data.get("direccion"),
        distrito=data.get("distrito"),
    )

    score = calcular_score(
        calculo["porcentaje_descuento"],
        calculo["nivel_oportunidad"],
    )

    riesgo = calcular_riesgo(score)

    expediente = data.get("expediente")
    numero_remate = data.get("numero_remate") or data.get("remate") or expediente

    inmueble = {
        "expediente": expediente,
        "numero_remate": numero_remate,
        "juzgado": data.get("juzgado"),
        "distrito": data.get("distrito"),
        "direccion": data.get("direccion"),
        "tipo": data.get("tipo"),
        "area": data.get("area"),
        "tasacion": tasacion,
        "precio_base": precio_base,
        "valor_mercado": valor_mercado,
        "fecha_remate": data.get("fecha_remate"),
        "fecha_presentacion": data.get("fecha_presentacion") or data.get("fecha_remate"),
        "hora_presentacion": data.get("hora_presentacion") or data.get("hora_remate"),
        "convocatoria": data.get("convocatoria"),
        "fuente": data.get("fuente") or "REMAJU",
        "url_detalle": obtener_url_detalle(data),
        "descripcion": data.get("descripcion") or data.get("texto_completo"),
        "texto_completo": data.get("texto_completo"),
        "porcentaje_descuento": calculo["porcentaje_descuento"],
        "ganancia_estimada": calculo["ganancia_estimada"],
        "nivel_oportunidad": calculo["nivel_oportunidad"],
        "estrellas": calculo["estrellas"],
        "score": score,
        "riesgo": riesgo,
        "lat": ubicacion["lat"],
        "lng": ubicacion["lng"],
        "ubicacion_tipo": ubicacion["ubicacion_tipo"],
        "direccion_completa": ubicacion["direccion_completa"],
    }

    response = (
        supabase
        .table("inmuebles")
        .upsert(
            inmueble,
            on_conflict="expediente",
        )
        .execute()
    )

    return response.data


def guardar_varios_inmuebles(lista_inmuebles):
    """
    Guarda una lista de inmuebles extraídos por el scraper.
    """
    resultados = []

    for item in lista_inmuebles:
        try:
            resultado = guardar_inmueble(item)

            resultados.append({
                "ok": True,
                "expediente": item.get("expediente"),
                "resultado": resultado,
            })

            print(f"Guardado correctamente: {item.get('expediente')}")

        except Exception as error:
            resultados.append({
                "ok": False,
                "expediente": item.get("expediente"),
                "error": str(error),
            })

            print(f"Error guardando {item.get('expediente')}: {error}")

    return resultados


if __name__ == "__main__":
    inmueble_prueba = {
        "expediente": "TEST-REMAJU-001",
        "numero_remate": "TEST-REMAJU-001",
        "juzgado": "Juzgado de prueba",
        "distrito": "Surquillo",
        "direccion": "Av. Angamos Este 1805, Surquillo, Lima",
        "tipo": "Departamento",
        "area": 72,
        "tasacion": 300000,
        "precio_base": 200000,
        "valor_mercado": 330000,
        "fecha_remate": "24/06/2026",
        "fecha_presentacion": "24/06/2026",
        "hora_presentacion": "11:59 AM",
        "convocatoria": "PRIMERA CONVOCATORIA",
        "fuente": "REMAJU",
        "url_detalle": "",
        "descripcion": "Inmueble de prueba para validar scraper, ubicación y Supabase.",
        "texto_completo": "Inmueble de prueba para validar scraper, ubicación y Supabase.",
    }

    resultado = guardar_inmueble(inmueble_prueba)

    print("Resultado:")
    print(resultado)