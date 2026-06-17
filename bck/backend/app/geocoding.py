import requests
import unicodedata


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
}


def limpiar_texto(texto):
    return str(texto or "").strip()


def normalizar_texto(texto):
    texto = limpiar_texto(texto).upper()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(
        caracter for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )
    return texto


def obtener_ubicacion(direccion=None, distrito=None):
    direccion = limpiar_texto(direccion)
    distrito_original = limpiar_texto(distrito)
    distrito_normalizado = normalizar_texto(distrito_original)

    # 1. Intentar ubicación exacta usando dirección + distrito
    if direccion and distrito_original:
        consulta = f"{direccion}, {distrito_original}, Lima, Perú"

        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": consulta,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "pe",
                },
                headers={
                    "User-Agent": "RadarRemates/1.0"
                },
                timeout=10,
            )

            response.raise_for_status()
            resultados = response.json()

            if resultados:
                return {
                    "lat": float(resultados[0]["lat"]),
                    "lng": float(resultados[0]["lon"]),
                    "ubicacion_tipo": "exacta",
                    "direccion_completa": consulta,
                }

        except Exception as error:
            print("Error geocodificando dirección:", error)

    # 2. Si no encuentra dirección exacta, usar coordenada aproximada del distrito
    if distrito_normalizado in COORDENADAS_DISTRITOS:
        lat, lng = COORDENADAS_DISTRITOS[distrito_normalizado]

        return {
            "lat": lat,
            "lng": lng,
            "ubicacion_tipo": "aproximada",
            "direccion_completa": distrito_original or distrito_normalizado,
        }

    # 3. Si no reconoce nada, usar Lima centro por defecto
    return {
        "lat": -12.0464,
        "lng": -77.0428,
        "ubicacion_tipo": "aproximada",
        "direccion_completa": "Lima, Perú",
    }