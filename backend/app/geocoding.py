import re
import unicodedata
from typing import Optional, Tuple

import requests


# Coordenadas aproximadas por distritos/provincias frecuentes.
# Cuando no se puede geocodificar una dirección exacta, estas coordenadas evitan
# enviar todos los inmuebles a Lima centro por defecto.
COORDENADAS_DISTRITOS = {
    # LIMA METROPOLITANA
    "LIMA": [-12.0464, -77.0428],
    "CERCADO DE LIMA": [-12.0464, -77.0428],
    "ANCON": [-11.7739, -77.1761],
    "ANCÓN": [-11.7739, -77.1761],
    "ATE": [-12.0464, -76.9000],
    "BARRANCO": [-12.1494, -77.0217],
    "BREÑA": [-12.0586, -77.0508],
    "BRENA": [-12.0586, -77.0508],
    "CARABAYLLO": [-11.8539, -77.0378],
    "CHACLACAYO": [-11.9828, -76.7686],
    "CHORRILLOS": [-12.1649, -77.0250],
    "CIENEGUILLA": [-12.1200, -76.8167],
    "COMAS": [-11.9328, -77.0408],
    "EL AGUSTINO": [-12.0483, -76.9994],
    "INDEPENDENCIA": [-11.9914, -77.0547],
    "JESUS MARIA": [-12.0763, -77.0444],
    "JESÚS MARÍA": [-12.0763, -77.0444],
    "LA MOLINA": [-12.0875, -76.9286],
    "LA VICTORIA": [-12.0653, -77.0308],
    "LINCE": [-12.0844, -77.0358],
    "LOS OLIVOS": [-11.9827, -77.0742],
    "LURIGANCHO": [-11.9364, -76.6972],
    "LURIGANCHO-CHOSICA": [-11.9364, -76.6972],
    "LURIGANCHO CHOSICA": [-11.9364, -76.6972],
    "LURIN": [-12.2736, -76.8706],
    "LURÍN": [-12.2736, -76.8706],
    "MAGDALENA DEL MAR": [-12.0917, -77.0672],
    "MIRAFLORES": [-12.1211, -77.0305],
    "PACHACAMAC": [-12.2294, -76.8583],
    "PUCUSANA": [-12.4817, -76.7975],
    "PUEBLO LIBRE": [-12.0769, -77.0677],
    "PUENTE PIEDRA": [-11.8667, -77.0747],
    "PUNTA HERMOSA": [-12.3375, -76.8250],
    "PUNTA NEGRA": [-12.3653, -76.7958],
    "RIMAC": [-12.0297, -77.0431],
    "RÍMAC": [-12.0297, -77.0431],
    "SAN BARTOLO": [-12.3906, -76.7808],
    "SAN BORJA": [-12.1080, -76.9995],
    "SAN ISIDRO": [-12.0972, -77.0365],
    "SAN JUAN DE LURIGANCHO": [-11.9828, -77.0080],
    "SAN JUAN DE MIRAFLORES": [-12.1575, -76.9708],
    "SAN LUIS": [-12.0756, -76.9975],
    "SAN MARTIN DE PORRES": [-12.0300, -77.0750],
    "SAN MARTÍN DE PORRES": [-12.0300, -77.0750],
    "SAN MIGUEL": [-12.0772, -77.0928],
    "SANTA ANITA": [-12.0433, -76.9714],
    "SANTA MARIA DEL MAR": [-12.4097, -76.7742],
    "SANTA MARÍA DEL MAR": [-12.4097, -76.7742],
    "SANTA ROSA": [-11.7983, -77.1717],
    "SANTIAGO DE SURCO": [-12.1450, -76.9918],
    "SURCO": [-12.1450, -76.9918],
    "SURQUILLO": [-12.1186, -77.0217],
    "VILLA EL SALVADOR": [-12.2133, -76.9367],
    "VILLA MARIA DEL TRIUNFO": [-12.1625, -76.9436],
    "VILLA MARÍA DEL TRIUNFO": [-12.1625, -76.9436],

    # CALLAO
    "CALLAO": [-12.0566, -77.1181],
    "BELLAVISTA": [-12.0611, -77.1297],
    "CARMEN DE LA LEGUA": [-12.0397, -77.0908],
    "CARMEN DE LA LEGUA REYNOSO": [-12.0397, -77.0908],
    "LA PERLA": [-12.0650, -77.1086],
    "LA PUNTA": [-12.0725, -77.1647],
    "VENTANILLA": [-11.8753, -77.1275],
    "MI PERU": [-11.8556, -77.1222],
    "MI PERÚ": [-11.8556, -77.1222],

    # ICA / provincias y distritos frecuentes en REMAJU
    "ICA": [-14.0678, -75.7286],
    "PARCONA": [-14.0475, -75.7056],
    "LA TINGUIÑA": [-14.0333, -75.7167],
    "TINGUIÑA": [-14.0333, -75.7167],
    "SUBTANJALLA": [-14.0186, -75.7581],
    "SAN JUAN BAUTISTA": [-14.0075, -75.7353],
    "LOS AQUIJES": [-14.0969, -75.6914],
    "PUEBLO NUEVO": [-14.1289, -75.7056],
    "SANTIAGO": [-14.1847, -75.7147],
    "TATE": [-14.1528, -75.7050],
    "OCUCAJE": [-14.3472, -75.6728],
    "PISCO": [-13.7103, -76.2056],
    "CHINCHA": [-13.4183, -76.1325],
    "CHINCHA ALTA": [-13.4183, -76.1325],
    "NAZCA": [-14.8278, -74.9389],
    "NASCA": [-14.8278, -74.9389],
    "PALPA": [-14.5336, -75.1850],
}

# Coordenadas aproximadas por departamento del Perú.
COORDENADAS_DEPARTAMENTOS = {
    "AMAZONAS": [-6.2317, -77.8690],
    "ANCASH": [-9.5278, -77.5278],
    "ÁNCASH": [-9.5278, -77.5278],
    "APURIMAC": [-13.6339, -72.8814],
    "APURÍMAC": [-13.6339, -72.8814],
    "AREQUIPA": [-16.3989, -71.5350],
    "AYACUCHO": [-13.1631, -74.2236],
    "CAJAMARCA": [-7.1617, -78.5128],
    "CALLAO": [-12.0566, -77.1181],
    "CUSCO": [-13.5319, -71.9675],
    "CUZCO": [-13.5319, -71.9675],
    "HUANCAVELICA": [-12.7864, -74.9756],
    "HUANUCO": [-9.9306, -76.2422],
    "HUÁNUCO": [-9.9306, -76.2422],
    "ICA": [-14.0678, -75.7286],
    "JUNIN": [-12.0667, -75.2167],
    "JUNÍN": [-12.0667, -75.2167],
    "LA LIBERTAD": [-8.1116, -79.0288],
    "LAMBAYEQUE": [-6.7714, -79.8409],
    "LIMA": [-12.0464, -77.0428],
    "LORETO": [-3.7491, -73.2538],
    "MADRE DE DIOS": [-12.5933, -69.1891],
    "MOQUEGUA": [-17.1939, -70.9350],
    "PASCO": [-10.6833, -76.2667],
    "PIURA": [-5.1945, -80.6328],
    "PUNO": [-15.8402, -70.0219],
    "SAN MARTIN": [-6.0342, -76.9717],
    "SAN MARTÍN": [-6.0342, -76.9717],
    "TACNA": [-18.0147, -70.2536],
    "TUMBES": [-3.5669, -80.4515],
    "UCAYALI": [-8.3791, -74.5539],
}

PERU_CENTRO = [-9.19, -75.0152]


def limpiar_texto(texto):
    return str(texto or "").strip()


def normalizar_texto(texto):
    texto = limpiar_texto(texto).upper()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(
        caracter for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def extraer_entre(texto_normalizado: str, patron: str) -> Optional[str]:
    match = re.search(patron, texto_normalizado, flags=re.IGNORECASE)
    if not match:
        return None

    valor = match.group(1).strip()
    valor = re.split(
        r"\b(PROVINCIA|DEPARTAMENTO|CUYA|INSCRITO|CON|SE|UBICADO|MZ|LOTE|PARTIDA|AREA|ÁREA)\b",
        valor,
        maxsplit=1,
    )[0].strip(" ,.;:-")
    return valor or None


def detectar_ubicacion_desde_texto(*textos) -> Tuple[Optional[str], Optional[list], str]:
    """Detecta distrito/provincia/departamento desde textos legales de REMAJU."""
    texto = normalizar_texto(" ".join(limpiar_texto(t) for t in textos if t))

    if not texto:
        return None, None, "sin_ubicacion"

    # 1. Buscar frases típicas: DISTRITO DE ICA, DISTRITO DE SUBTANJALLA, etc.
    candidatos = []
    for patron in [
        r"DISTRITO\s+DE\s+([A-ZÑ ]{3,60})",
        r"DISTRITO\s*,\s*PROVINCIA\s+Y\s+DEPARTAMENTO\s+DE\s+([A-ZÑ ]{3,60})",
        r"DISTRITO\s+PROVINCIA\s+Y\s+DEPARTAMENTO\s+DE\s+([A-ZÑ ]{3,60})",
        r"UBICADO\s+EN\s+EL\s+DISTRITO\s+DE\s+([A-ZÑ ]{3,60})",
    ]:
        valor = extraer_entre(texto, patron)
        if valor:
            candidatos.append(valor)

    for candidato in candidatos:
        clave = normalizar_texto(candidato)
        if clave in COORDENADAS_DISTRITOS:
            return candidato.title(), COORDENADAS_DISTRITOS[clave], "aproximada"

    # 2. Si no detecta distrito, buscar departamento/provincia.
    for patron in [
        r"DEPARTAMENTO\s+DE\s+([A-ZÑ ]{3,60})",
        r"PROVINCIA\s+DE\s+([A-ZÑ ]{3,60})",
        r"PROVINCIA\s+Y\s+DEPARTAMENTO\s+DE\s+([A-ZÑ ]{3,60})",
    ]:
        valor = extraer_entre(texto, patron)
        if not valor:
            continue

        clave = normalizar_texto(valor)
        if clave in COORDENADAS_DISTRITOS:
            return valor.title(), COORDENADAS_DISTRITOS[clave], "aproximada"

        if clave in COORDENADAS_DEPARTAMENTOS:
            return valor.title(), COORDENADAS_DEPARTAMENTOS[clave], "aproximada"

    # 3. Como fallback, buscar menciones directas de departamentos.
    for departamento, coordenadas in COORDENADAS_DEPARTAMENTOS.items():
        dep_normalizado = normalizar_texto(departamento)
        if re.search(rf"\b{re.escape(dep_normalizado)}\b", texto):
            return departamento.title(), coordenadas, "aproximada"

    return None, None, "sin_ubicacion"


def consultar_nominatim(consulta: str):
    response = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": consulta,
            "format": "json",
            "limit": 1,
            "countrycodes": "pe",
        },
        headers={"User-Agent": "RadarRemates/1.0"},
        timeout=10,
    )
    response.raise_for_status()
    resultados = response.json()
    return resultados[0] if resultados else None


def obtener_ubicacion(direccion=None, distrito=None, descripcion=None, texto_completo=None):
    """Devuelve lat/lng para un inmueble.

    Regla clave: ya no fuerza siempre ", Lima, Perú". Si el texto del aviso indica
    ICA, Arequipa, Piura, etc., usa ese lugar como contexto o fallback.
    """
    direccion = limpiar_texto(direccion)
    distrito_original = limpiar_texto(distrito)
    descripcion = limpiar_texto(descripcion)
    texto_completo = limpiar_texto(texto_completo)

    distrito_normalizado = normalizar_texto(distrito_original)

    lugar_detectado, coords_detectadas, tipo_detectado = detectar_ubicacion_desde_texto(
        direccion,
        distrito_original,
        descripcion,
        texto_completo,
    )

    # Si el campo distrito coincide con un distrito/provincia conocida, úsalo como contexto.
    if not lugar_detectado and distrito_normalizado in COORDENADAS_DISTRITOS:
        lugar_detectado = distrito_original
        coords_detectadas = COORDENADAS_DISTRITOS[distrito_normalizado]
        tipo_detectado = "aproximada"

    if not lugar_detectado and distrito_normalizado in COORDENADAS_DEPARTAMENTOS:
        lugar_detectado = distrito_original
        coords_detectadas = COORDENADAS_DEPARTAMENTOS[distrito_normalizado]
        tipo_detectado = "aproximada"

    # 1. Intentar geocodificación exacta si hay dirección.
    if direccion:
        consultas = []

        if lugar_detectado:
            consultas.append(f"{direccion}, {lugar_detectado}, Perú")
        elif distrito_original:
            consultas.append(f"{direccion}, {distrito_original}, Perú")

        # Nunca forzar Lima si el texto menciona otra región.
        if not lugar_detectado:
            consultas.append(f"{direccion}, Perú")

        for consulta in consultas:
            try:
                resultado = consultar_nominatim(consulta)

                if resultado:
                    return {
                        "lat": float(resultado["lat"]),
                        "lng": float(resultado["lon"]),
                        "ubicacion_tipo": "exacta",
                        "direccion_completa": consulta,
                    }

            except Exception as error:
                print(f"Error geocodificando dirección '{consulta}':", error)

    # 2. Fallback aproximado por distrito/departamento detectado.
    if coords_detectadas:
        lat, lng = coords_detectadas
        return {
            "lat": lat,
            "lng": lng,
            "ubicacion_tipo": tipo_detectado,
            "direccion_completa": f"Referencia aproximada: {lugar_detectado}, Perú",
        }

    # 3. Último fallback: centro de Perú, no Lima centro.
    return {
        "lat": PERU_CENTRO[0],
        "lng": PERU_CENTRO[1],
        "ubicacion_tipo": "sin_ubicacion",
        "direccion_completa": "Ubicación no geocodificada - Perú",
    }
