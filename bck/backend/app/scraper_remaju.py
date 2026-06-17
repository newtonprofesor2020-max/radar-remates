"""
Scraper REMAJU para Radar Remates.

Qué hace:
- Entra a la página pública de REMAJU.
- Lee los remates visibles de la página.
- Hace click en el botón Aviso de cada remate para capturar la URL real del aviso, cuando REMAJU la expone.
- Hace click en Detalle para capturar texto adicional, cuando REMAJU lo muestra en modal.
- Guarda/actualiza los inmuebles en Supabase.

Uso recomendado desde backend:
    python -m app.scraper_remaju --limite 20 --no-guardar --visible
    python -m app.scraper_remaju --limite 50

Instalación:
    python -m pip install playwright beautifulsoup4
    python -m playwright install chromium
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from typing import Any, Optional
from urllib.parse import urljoin

from app.supabase_client import supabase
from app.calculos import calcular_oportunidad
from app.geocoding import obtener_ubicacion

try:
    from playwright.sync_api import (
        sync_playwright,
        TimeoutError as PlaywrightTimeoutError,
        Page,
        BrowserContext,
    )
except Exception:  # pragma: no cover
    sync_playwright = None
    PlaywrightTimeoutError = Exception
    Page = Any
    BrowserContext = Any


URL_REMAJU_PUBLICA = "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml"
URL_BASE_REMAJU = "https://remaju.pj.gob.pe"

URLS_BLOQUEADAS = (
    "remaju_manual_postor",
    "manual_postor",
    "manual",
    "instructivo",
    "tutorial",
    "/doc/remaju_manual",
)


@dataclass
class RemateExtraido:
    expediente: str
    numero_remate: str
    juzgado: str
    distrito: str
    direccion: str
    tipo: str
    area: Optional[float]
    tasacion: float
    precio_base: float
    valor_mercado: float
    fecha_remate: str
    fecha_presentacion: str
    hora_presentacion: str
    convocatoria: str
    fuente: str
    url_detalle: str
    descripcion: str
    texto_completo: str
    moneda: str
    fase: str
    estado: str


def log(mensaje: str) -> None:
    print(mensaje, flush=True)


def calcular_score(porcentaje_descuento, nivel_oportunidad):
    porcentaje = float(porcentaje_descuento or 0)
    nivel = str(nivel_oportunidad or "").lower()

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

    return max(0, min(100, score))


def calcular_riesgo(score):
    if score >= 85:
        return "Bajo"
    if score >= 70:
        return "Medio"
    return "Alto"


def limpiar_numero(valor) -> float:
    """Convierte S/. 154,354.57, $ 14,212.19 o 14.212,19 a float."""
    if valor is None:
        return 0

    texto = str(valor).strip()
    if not texto:
        return 0

    texto = (
        texto.replace("S/.", "")
        .replace("S/", "")
        .replace("$", "")
        .replace("US$", "")
        .replace("USD", "")
        .replace("PEN", "")
        .replace(" ", "")
        .strip()
    )

    # Caso 154,354.57 -> coma miles, punto decimal.
    if "," in texto and "." in texto:
        if texto.rfind(".") > texto.rfind(","):
            texto = texto.replace(",", "")
        else:
            texto = texto.replace(".", "").replace(",", ".")
    # Caso 154.354 o 154.354,57.
    elif "." in texto:
        partes = texto.split(".")
        if len(partes[-1]) == 3 and len(partes) > 1:
            texto = "".join(partes)
    # Caso 154,57 o 154,354.
    elif "," in texto:
        partes = texto.split(",")
        if len(partes[-1]) == 3 and len(partes) > 1:
            texto = "".join(partes)
        else:
            texto = texto.replace(",", ".")

    try:
        return float(texto)
    except Exception:
        return 0


def detectar_moneda(texto: str) -> str:
    t = str(texto or "")
    if "$" in t or "US$" in t.upper() or "USD" in t.upper():
        return "USD"
    return "PEN"


def normalizar_url(url: Any) -> str:
    texto = str(url or "").strip()
    if not texto:
        return ""
    texto = urljoin(URL_BASE_REMAJU, texto)
    return texto


def es_url_valida_aviso(url: Any) -> bool:
    texto = normalizar_url(url).lower()
    if not texto:
        return False
    if not texto.startswith("http://") and not texto.startswith("https://"):
        return False
    if any(bloqueado in texto for bloqueado in URLS_BLOQUEADAS):
        return False
    return True


def elegir_url_aviso(*urls: Any) -> str:
    for url in urls:
        url_norm = normalizar_url(url)
        if es_url_valida_aviso(url_norm):
            return url_norm
    return ""


def extraer_area(texto: str) -> Optional[float]:
    patrones = [
        r"AREA\s+TECHADA\s*[:\-]?\s*([0-9]+(?:[.,][0-9]+)?)",
        r"AREA\s+OCUPADA\s*[:\-]?\s*([0-9]+(?:[.,][0-9]+)?)",
        r"([0-9]+(?:[.,][0-9]+)?)\s*M2",
        r"([0-9]+(?:[.,][0-9]+)?)\s*M²",
    ]
    for patron in patrones:
        m = re.search(patron, texto or "", flags=re.I)
        if m:
            return limpiar_numero(m.group(1))
    return None


def limpiar_lineas(texto: str) -> list[str]:
    return [linea.strip() for linea in str(texto or "").splitlines() if linea.strip()]


def parsear_bloque_remate(bloque: str, url_aviso: str = "", detalle_texto: str = "") -> Optional[RemateExtraido]:
    texto = str(bloque or "").strip()
    if not texto.startswith("Remate N°"):
        return None

    lineas = limpiar_lineas(texto)
    if not lineas:
        return None

    encabezado = lineas[0]
    m = re.search(r"Remate\s+N[°º]\s*([0-9]+)\s*-\s*(.+)", encabezado, flags=re.I)
    if not m:
        return None

    numero = m.group(1).strip()
    convocatoria = m.group(2).strip().upper()
    expediente = f"REMAJU-{numero}"

    tipo = lineas[1] if len(lineas) > 1 else "Inmueble"
    distrito = lineas[2] if len(lineas) > 2 else "Sin distrito"

    fecha = ""
    hora = ""
    estado = ""
    fase = ""
    precio_texto = ""

    fecha_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", texto)
    if fecha_match:
        fecha = fecha_match.group(1)

    hora_match = re.search(r"\b(\d{1,2}:\d{2}\s*(?:AM|PM))\b", texto, flags=re.I)
    if hora_match:
        hora = hora_match.group(1).upper().replace("  ", " ")

    precio_match = re.search(r"Precio\s*Base\s*\n?\s*((?:S/\.|S/|US\$|USD|\$)\s*[0-9][0-9.,]*)", texto, flags=re.I)
    if precio_match:
        precio_texto = precio_match.group(1)

    precio_base = limpiar_numero(precio_texto)
    moneda = detectar_moneda(precio_texto)

    # REMAJU no siempre publica tasación/valor de mercado en la tarjeta.
    # Para no dejar score en cero, usamos una estimación conservadora referencial.
    valor_mercado = round(precio_base * 1.5, 2) if precio_base > 0 else 0
    tasacion = valor_mercado

    if "En proceso" in texto:
        estado = "Activo"
    elif "Finalizado" in texto:
        estado = "Finalizado"
    else:
        estado = "Activo"

    for posible_fase in (
        "Publicación e Inscripcion",
        "Publicación e Inscripción",
        "Validación de Inscripción",
        "Presentación de Ofertas",
        "Pago Saldo",
        "Validación del Saldo",
        "Finalizado",
    ):
        if posible_fase.lower() in texto.lower():
            fase = posible_fase
            break

    descripcion = ""
    patron_desc = re.search(
        r"(?:Publicación e Inscripcion|Publicación e Inscripción)\s*(.*?)\s*Precio\s*Base",
        texto,
        flags=re.I | re.S,
    )
    if patron_desc:
        descripcion = " ".join(patron_desc.group(1).split())

    if not descripcion:
        # Fallback: usar líneas entre hora/fase y Precio Base.
        try:
            idx_precio = next(i for i, l in enumerate(lineas) if "Precio Base" in l)
            candidatos = lineas[3:idx_precio]
            candidatos = [
                c for c in candidatos
                if not re.match(r"\d{2}/\d{2}/\d{4}$", c)
                and not re.match(r"\d{1,2}:\d{2}\s*(AM|PM)$", c, flags=re.I)
                and c.lower() not in {"presentación de ofertas", "en proceso", "publicación e inscripcion", "publicación e inscripción"}
            ]
            descripcion = " ".join(candidatos[-3:]).strip()
        except Exception:
            descripcion = ""

    texto_completo = texto
    if detalle_texto:
        texto_completo = f"{texto}\n\nDETALLE REMAJU:\n{detalle_texto}"

    area = extraer_area(f"{descripcion} {detalle_texto}")

    return RemateExtraido(
        expediente=expediente,
        numero_remate=numero,
        juzgado="No registrado",
        distrito=distrito,
        direccion=descripcion or distrito,
        tipo=tipo,
        area=area,
        tasacion=tasacion,
        precio_base=precio_base,
        valor_mercado=valor_mercado,
        fecha_remate=fecha,
        fecha_presentacion=fecha,
        hora_presentacion=hora,
        convocatoria=convocatoria,
        fuente="REMAJU",
        url_detalle=elegir_url_aviso(url_aviso) or URL_REMAJU_PUBLICA,
        descripcion=descripcion or detalle_texto or texto,
        texto_completo=texto_completo,
        moneda=moneda,
        fase=fase,
        estado=estado,
    )


def separar_bloques_remate(texto_pagina: str) -> list[str]:
    partes = re.split(r"(?=Remate\s+N[°º]\s*\d+\s*-)", texto_pagina or "")
    bloques = []
    for parte in partes:
        parte = parte.strip()
        if parte.startswith("Remate N°") or parte.startswith("Remate Nº"):
            # Cortar basura posterior del paginador si existe.
            parte = re.split(r"\n\s*Total:\s*\d+\s*registros", parte, maxsplit=1)[0].strip()
            bloques.append(parte)
    return bloques


def obtener_botones(page: Page, texto: str):
    # REMAJU puede renderizar botones como <button>, <a> o <span> con role dinámico.
    return page.locator(
        f"button:has-text('{texto}'), a:has-text('{texto}'), span:has-text('{texto}')"
    ).filter(has_text=re.compile(rf"^\s*{re.escape(texto)}\s*$", re.I))


def capturar_texto_detalle(page: Page, indice: int) -> str:
    try:
        botones = obtener_botones(page, "Detalle")
        if botones.count() <= indice:
            return ""

        botones.nth(indice).scroll_into_view_if_needed(timeout=3000)
        botones.nth(indice).click(timeout=5000)
        page.wait_for_timeout(1200)

        dialogos = page.locator(".ui-dialog:visible, [role='dialog']:visible, .modal:visible")
        texto = ""
        if dialogos.count() > 0:
            texto = dialogos.last.inner_text(timeout=3000)

        # Cerrar modal si apareció.
        for selector in [
            ".ui-dialog:visible button:has-text('Cerrar')",
            ".ui-dialog:visible a:has-text('Cerrar')",
            "[role='dialog']:visible button:has-text('Cerrar')",
            ".ui-dialog-titlebar-close:visible",
        ]:
            try:
                cerrar = page.locator(selector)
                if cerrar.count() > 0:
                    cerrar.first.click(timeout=1500)
                    page.wait_for_timeout(400)
                    break
            except Exception:
                pass

        if not texto:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass

        return texto.strip()
    except Exception as error:
        log(f"No se pudo capturar Detalle #{indice + 1}: {error}")
        return ""


def capturar_url_aviso(page: Page, context: BrowserContext, indice: int) -> str:
    """
    Captura la URL del botón Aviso del remate indicado.
    No acepta manuales, instructivos ni tutoriales.
    """
    try:
        botones = obtener_botones(page, "Aviso")
        if botones.count() <= indice:
            return ""

        boton = botones.nth(indice)
        boton.scroll_into_view_if_needed(timeout=3000)

        # 1) Revisar si el elemento ya contiene href u onclick con URL.
        try:
            datos = boton.evaluate(
                """el => ({
                    href: el.href || el.getAttribute('href') || '',
                    dataHref: el.getAttribute('data-href') || '',
                    onclick: el.getAttribute('onclick') || '',
                    outerHTML: el.outerHTML || ''
                })"""
            )
            for valor in datos.values():
                if not isinstance(valor, str):
                    continue
                for match in re.findall(r"https?://[^'\"\s<>]+", valor):
                    if es_url_valida_aviso(match):
                        return normalizar_url(match)
                for match in re.findall(r"(?:/remaju|/doc|/faces|/pages)/[^'\"\s<>]+", valor):
                    url = normalizar_url(match)
                    if es_url_valida_aviso(url):
                        return url
        except Exception:
            pass

        # 2) Intentar popup.
        try:
            with context.expect_page(timeout=5000) as popup_info:
                boton.click(timeout=5000)
            popup = popup_info.value
            popup.wait_for_load_state("domcontentloaded", timeout=8000)
            popup.wait_for_timeout(800)
            url = popup.url
            try:
                popup.close()
            except Exception:
                pass
            if es_url_valida_aviso(url):
                return normalizar_url(url)
        except PlaywrightTimeoutError:
            pass
        except Exception as error:
            log(f"Aviso #{indice + 1}: no abrió popup limpio: {error}")

        # 3) Intentar navegación en la misma pestaña.
        try:
            url_antes = page.url
            boton = obtener_botones(page, "Aviso").nth(indice)
            boton.click(timeout=5000)
            page.wait_for_timeout(1500)
            url_despues = page.url
            if url_despues != url_antes and es_url_valida_aviso(url_despues):
                try:
                    page.go_back(wait_until="networkidle", timeout=8000)
                except Exception:
                    page.goto(URL_REMAJU_PUBLICA, wait_until="networkidle", timeout=20000)
                return normalizar_url(url_despues)
            if url_despues != url_antes:
                try:
                    page.go_back(wait_until="networkidle", timeout=8000)
                except Exception:
                    page.goto(URL_REMAJU_PUBLICA, wait_until="networkidle", timeout=20000)
        except Exception:
            pass

        return ""
    except Exception as error:
        log(f"No se pudo capturar Aviso #{indice + 1}: {error}")
        return ""


def extraer_remates_remaju(limite: int = 20, visible: bool = False) -> list[dict[str, Any]]:
    if sync_playwright is None:
        raise RuntimeError(
            "Playwright no está instalado. Ejecuta: python -m pip install playwright && python -m playwright install chromium"
        )

    resultados: list[dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not visible)
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1400, "height": 950},
        )
        page = context.new_page()

        log(f"Abriendo REMAJU: {URL_REMAJU_PUBLICA}")
        page.goto(URL_REMAJU_PUBLICA, wait_until="networkidle", timeout=60000)
        page.wait_for_selector("text=Remate N°", timeout=30000)
        page.wait_for_timeout(1500)

        texto_pagina = page.locator("body").inner_text(timeout=10000)
        bloques = separar_bloques_remate(texto_pagina)
        total = min(len(bloques), limite)

        log(f"Remates visibles detectados: {len(bloques)}. Procesando: {total}")

        for indice in range(total):
            bloque = bloques[indice]
            numero = re.search(r"Remate\s+N[°º]\s*(\d+)", bloque, flags=re.I)
            numero_txt = numero.group(1) if numero else str(indice + 1)
            log(f"[{indice + 1}/{total}] Remate {numero_txt}")

            detalle_texto = capturar_texto_detalle(page, indice)
            url_aviso = capturar_url_aviso(page, context, indice)

            # Si después de click cambió o recargó algo, asegurar que seguimos en la lista.
            try:
                if "remateExterno.xhtml" not in page.url:
                    page.goto(URL_REMAJU_PUBLICA, wait_until="networkidle", timeout=30000)
                    page.wait_for_selector("text=Remate N°", timeout=15000)
            except Exception:
                pass

            remate = parsear_bloque_remate(
                bloque=bloque,
                url_aviso=url_aviso,
                detalle_texto=detalle_texto,
            )

            if remate:
                resultados.append(asdict(remate))
                log(f"  OK {remate.expediente} | {remate.distrito} | URL: {remate.url_detalle}")
            else:
                log(f"  No se pudo parsear remate {numero_txt}")

        context.close()
        browser.close()

    return resultados


def guardar_inmueble(data):
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

    if valor_mercado <= 0 and precio_base > 0:
        valor_mercado = round(precio_base * 1.5, 2)

    tasacion = limpiar_numero(data.get("tasacion")) or valor_mercado

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

    url_detalle = elegir_url_aviso(
        data.get("url_detalle"),
        data.get("url_original"),
        data.get("url"),
        data.get("url_aviso"),
        data.get("aviso_url"),
        data.get("fuente_url"),
        data.get("remate_url"),
        data.get("url_remaju"),
        data.get("link"),
        data.get("enlace"),
    ) or URL_REMAJU_PUBLICA

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
        "url_detalle": url_detalle,
        "descripcion": data.get("descripcion") or data.get("texto_completo"),
        "texto_completo": data.get("texto_completo"),
        "porcentaje_descuento": calculo["porcentaje_descuento"],
        "ganancia_estimada": calculo["ganancia_estimada"],
        "nivel_oportunidad": calculo["nivel_oportunidad"],
        "estrellas": calculo["estrellas"],
        "score": score,
        "riesgo": riesgo,
        "estado": data.get("estado") or "Activo",
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
    resultados = []

    for item in lista_inmuebles:
        try:
            resultado = guardar_inmueble(item)
            resultados.append({
                "ok": True,
                "expediente": item.get("expediente"),
                "resultado": resultado,
            })
            log(f"Guardado correctamente: {item.get('expediente')}")
        except Exception as error:
            resultados.append({
                "ok": False,
                "expediente": item.get("expediente"),
                "error": str(error),
            })
            log(f"Error guardando {item.get('expediente')}: {error}")

    return resultados


def limpiar_registros_malos() -> dict[str, Any]:
    """Elimina registros SEMILLA y registros con URL de manual/instructivo."""
    response = supabase.table("inmuebles").select("id, expediente, fuente, url_detalle").execute()
    items = response.data or []

    ids = []
    for item in items:
        expediente = str(item.get("expediente") or "")
        url = str(item.get("url_detalle") or "").lower()
        fuente = str(item.get("fuente") or "").upper()

        es_malo = (
            expediente.startswith("SEMILLA-")
            or any(bloqueado in url for bloqueado in URLS_BLOQUEADAS)
            or "remaju_manual_postor.pdf" in url
            or (fuente == "REMAJU" and "manual" in url)
        )

        if es_malo and item.get("id") is not None:
            ids.append(item["id"])

    if not ids:
        return {"eliminados": 0, "ids": []}

    try:
        supabase.table("favoritos").delete().in_("inmueble_id", ids).execute()
    except Exception:
        pass

    try:
        supabase.table("revisiones_inmueble").delete().in_("inmueble_id", ids).execute()
    except Exception:
        pass

    supabase.table("inmuebles").delete().in_("id", ids).execute()
    return {"eliminados": len(ids), "ids": ids}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Scraper REMAJU para Radar Remates")
    parser.add_argument("--limite", type=int, default=20, help="Cantidad máxima de remates visibles a procesar")
    parser.add_argument("--no-guardar", action="store_true", help="Solo extrae y muestra; no guarda en Supabase")
    parser.add_argument("--visible", action="store_true", help="Abre Chromium visible para depuración")
    parser.add_argument("--json", action="store_true", help="Imprime JSON completo de lo extraído")
    parser.add_argument("--limpiar-malos", action="store_true", help="Elimina registros SEMILLA y URLs de manual/instructivo")

    args = parser.parse_args(argv)

    if args.limpiar_malos:
        resultado = limpiar_registros_malos()
        log(f"Limpieza BD: {resultado}")

    remates = extraer_remates_remaju(limite=args.limite, visible=args.visible)

    if args.json or args.no_guardar:
        print(json.dumps(remates, ensure_ascii=False, indent=2))

    if not args.no_guardar:
        resultados = guardar_varios_inmuebles(remates)
        log(json.dumps(resultados, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
