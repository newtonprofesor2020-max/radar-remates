def calcular_oportunidad(valor_mercado, precio_base):
    if not valor_mercado or valor_mercado <= 0:
        return {
            "porcentaje_descuento": 0,
            "ganancia_estimada": 0,
            "nivel_oportunidad": "Sin datos",
            "estrellas": "Sin clasificación"
        }

    porcentaje_descuento = ((valor_mercado - precio_base) / valor_mercado) * 100
    ganancia_estimada = valor_mercado - precio_base

    if porcentaje_descuento >= 45:
        nivel = "Oportunidad excelente"
        estrellas = "⭐⭐⭐⭐⭐"
    elif porcentaje_descuento >= 30:
        nivel = "Oportunidad alta"
        estrellas = "⭐⭐⭐⭐"
    elif porcentaje_descuento >= 15:
        nivel = "Oportunidad media"
        estrellas = "⭐⭐⭐"
    else:
        nivel = "Oportunidad baja"
        estrellas = "⭐"

    return {
        "porcentaje_descuento": round(porcentaje_descuento, 2),
        "ganancia_estimada": round(ganancia_estimada, 2),
        "nivel_oportunidad": nivel,
        "estrellas": estrellas
    }