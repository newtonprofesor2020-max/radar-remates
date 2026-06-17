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
VERSION_SCRAPER = "PAGINACION_REINICIO_POR_PAGINA_V7_2026_06_17"

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


def esperar_lista_remates(page: Page, timeout: int = 20000) -> None:
    """Espera a que la vista de listado REMAJU esté disponible."""
    page.wait_for_selector("text=Remate N°", timeout=timeout)
    page.wait_for_timeout(800)


def obtener_numeros_remate_en_pagina(page: Page) -> list[str]:
    try:
        texto = page.locator("body").inner_text(timeout=8000)
    except Exception:
        return []

    return re.findall(r"Remate\s+N[°º]\s*(\d+)", texto, flags=re.I)



def obtener_elemento_accion_remate(page: Page, numero_remate: str, accion: str):
    """Devuelve el botón/enlace de una acción dentro del bloque del remate indicado.

    REMAJU renderiza varios botones "Detalle" y "Aviso" en la misma página.
    Usar nth(indice) puede cruzar avisos después de navegar/regresar. Por eso
    buscamos el botón dentro del contenedor que contiene exactamente el número
    de remate, por ejemplo Remate N° 24240.
    """
    script = r"""
    ({numero, accion}) => {
      const normalizar = (s) => (s || '').replace(/\s+/g, ' ').trim().toUpperCase();
      const objetivo = (`REMATE N° ${numero}`).toUpperCase();
      const objetivoAlt = (`REMATE Nº ${numero}`).toUpperCase();
      const accionNorm = normalizar(accion);
      const cuentaRemates = (txt) => (txt.match(/REMATE\s+N[°º]\s*\d+/g) || []).length;
      const textoEl = (el) => normalizar(
        el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || ''
      );

      const candidatos = Array.from(document.querySelectorAll('a,button,span,input[type=submit],input[type=button]'));

      for (const el of candidatos) {
        const t = textoEl(el);
        if (t !== accionNorm && !t.includes(accionNorm)) continue;

        let node = el;
        for (let depth = 0; node && depth < 12; depth++, node = node.parentElement) {
          const ntxt = normalizar(node.innerText || node.textContent || '');
          if (!ntxt.includes(objetivo) && !ntxt.includes(objetivoAlt)) continue;

          // Preferimos el contenedor más pequeño que contenga solo este remate.
          // Si contiene muchos remates probablemente es body o un contenedor global.
          if (cuentaRemates(ntxt) <= 1) {
            const clickable = el.closest('a,button,input[type=submit],input[type=button]') || el;
            clickable.scrollIntoView({block: 'center', inline: 'center'});
            return clickable;
          }
        }
      }

      // Fallback: buscar un bloque pequeño por texto y luego acción adentro.
      const bloques = Array.from(document.querySelectorAll('div,li,tr,section,article'))
        .filter(node => {
          const ntxt = normalizar(node.innerText || node.textContent || '');
          return (ntxt.includes(objetivo) || ntxt.includes(objetivoAlt)) && cuentaRemates(ntxt) <= 1;
        })
        .sort((a,b) => (a.innerText || '').length - (b.innerText || '').length);

      for (const bloque of bloques) {
        const internos = Array.from(bloque.querySelectorAll('a,button,span,input[type=submit],input[type=button]'));
        for (const el of internos) {
          const t = textoEl(el);
          if (t === accionNorm || t.includes(accionNorm)) {
            const clickable = el.closest('a,button,input[type=submit],input[type=button]') || el;
            clickable.scrollIntoView({block: 'center', inline: 'center'});
            return clickable;
          }
        }
      }

      return null;
    }
    """
    try:
        handle = page.evaluate_handle(script, {"numero": str(numero_remate), "accion": accion})
        return handle.as_element()
    except Exception:
        return None


def click_elemento_remate(page: Page, elemento) -> bool:
    """Click robusto sobre un elemento específico del remate."""
    if elemento is None:
        return False

    try:
        elemento.scroll_into_view_if_needed(timeout=5000)
        page.wait_for_timeout(250)
    except Exception:
        pass

    # Click físico por coordenadas. Es más confiable con PrimeFaces.
    try:
        box = elemento.bounding_box()
        if box:
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2
            page.mouse.move(x, y)
            page.wait_for_timeout(100)
            page.mouse.down()
            page.wait_for_timeout(80)
            page.mouse.up()
            return True
    except Exception:
        pass

    for modo in ("normal", "force", "js", "dispatch"):
        try:
            if modo == "normal":
                elemento.click(timeout=8000)
            elif modo == "force":
                elemento.click(timeout=8000, force=True)
            elif modo == "js":
                elemento.evaluate("el => el.click()")
            else:
                elemento.evaluate("""el => {
                    for (const tipo of ['mousedown','mouseup','click']) {
                        el.dispatchEvent(new MouseEvent(tipo, {bubbles:true, cancelable:true, view:window}));
                    }
                }""")
            return True
        except Exception:
            continue

    return False


def capturar_texto_detalle(page: Page, numero_remate: str) -> str:
    """Captura el detalle correcto del remate indicado.

    No usa nth(indice). Busca el botón Detalle dentro del bloque que contiene
    el número de remate. Así evitamos que el remate 24238 capture el detalle de
    24239, que era el problema observado.
    """
    numero_remate = str(numero_remate)

    try:
        elemento = obtener_elemento_accion_remate(page, numero_remate, "Detalle")
        if elemento is None:
            log(f"No encontré botón Detalle para REMAJU-{numero_remate}.")
            return ""

        url_antes = page.url
        clave_antes = obtener_clave_pagina(page)

        if not click_elemento_remate(page, elemento):
            log(f"No se pudo hacer click en Detalle de REMAJU-{numero_remate}.")
            return ""

        page.wait_for_timeout(1600)

        # Caso A: navega a la página de detalle.
        if "mostrarDetalleRemate.xhtml" in page.url or page.url != url_antes:
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass

            try:
                page.wait_for_function(
                    r"""numero => {
                        const txt = document.body.innerText || '';
                        return txt.includes('Remate N° ' + numero) || txt.includes('Remate Nº ' + numero);
                    }""",
                    arg=numero_remate,
                    timeout=12000,
                )
            except Exception:
                pass

            page.wait_for_timeout(700)
            texto = page.locator("body").inner_text(timeout=15000).strip()

            # Validar dentro de la función antes de regresar.
            m_det = re.search(r"Remate\s+N[°º]\s*(\d+)", texto, flags=re.I)
            if m_det and m_det.group(1) != numero_remate:
                log(f"  Advertencia: detalle cruzado para REMAJU-{numero_remate}; el detalle dice REMAJU-{m_det.group(1)}.")
                texto = ""

            # Volver al listado manteniendo estado de paginación.
            volvio = False
            for selector in [
                "button:has-text('Regresar')",
                "a:has-text('Regresar')",
                "input[value='Regresar']",
                ".ui-button:has-text('Regresar')",
            ]:
                try:
                    regresar = page.locator(selector)
                    if regresar.count() > 0:
                        regresar.first.scroll_into_view_if_needed(timeout=4000)
                        regresar.first.click(timeout=8000)
                        esperar_lista_remates(page, timeout=25000)
                        volvio = True
                        break
                except Exception:
                    pass

            if not volvio:
                try:
                    page.go_back(wait_until="domcontentloaded", timeout=20000)
                    esperar_lista_remates(page, timeout=25000)
                    volvio = True
                except Exception:
                    pass

            # Confirmar que volvimos a la misma lista, si es posible.
            try:
                if clave_antes:
                    page.wait_for_timeout(800)
            except Exception:
                pass

            return texto

        # Caso B: modal/dialog dentro de la misma página.
        dialogos = page.locator(".ui-dialog:visible, [role='dialog']:visible, .modal:visible")
        texto = ""
        if dialogos.count() > 0:
            texto = dialogos.last.inner_text(timeout=8000).strip()

        m_det = re.search(r"Remate\s+N[°º]\s*(\d+)", texto, flags=re.I)
        if m_det and m_det.group(1) != numero_remate:
            log(f"  Advertencia: detalle cruzado para REMAJU-{numero_remate}; el modal dice REMAJU-{m_det.group(1)}.")
            texto = ""

        for selector in [
            ".ui-dialog:visible button:has-text('Cerrar')",
            ".ui-dialog:visible a:has-text('Cerrar')",
            "[role='dialog']:visible button:has-text('Cerrar')",
            ".ui-dialog-titlebar-close:visible",
        ]:
            try:
                cerrar = page.locator(selector)
                if cerrar.count() > 0:
                    cerrar.first.click(timeout=2500)
                    page.wait_for_timeout(500)
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
        log(f"No se pudo capturar Detalle de REMAJU-{numero_remate}: {error}")
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



def obtener_clave_pagina(page: Page) -> str:
    numeros = obtener_numeros_remate_en_pagina(page)
    return "|".join(numeros)



def obtener_html_paginador(page: Page) -> str:
    """Devuelve HTML resumido de posibles paginadores para depuración."""
    try:
        selectores = [
            ".ui-paginator",
            "[class*=\'paginator\']",
            "[class*=\'pagination\']",
            "[class*=\'pager\']",
            "nav",
            "ul",
        ]
        partes = []
        for selector in selectores:
            loc = page.locator(selector)
            total = loc.count()
            for i in range(min(total, 5)):
                try:
                    item = loc.nth(i)
                    texto = re.sub(r"\s+", " ", item.inner_text(timeout=500) or "").strip()
                    html = re.sub(r"\s+", " ", item.evaluate("el => el.outerHTML || ''"))[:800]
                    if "Total:" in texto or "Rows Per Page" in texto or "registros" in texto or "12345" in texto or "FP" in texto or "NE" in texto or "paginator" in html.lower():
                        partes.append(f"SELECTOR={selector} IDX={i} TEXT={texto[:300]} HTML={html[:800]}")
                except Exception:
                    pass
        return " || ".join(partes) if partes else "SIN_PAGINADOR"
    except Exception as error:
        return f"ERROR_PAGINADOR: {error}"


def diagnosticar_clickables_paginacion(page: Page) -> str:
    """Lista controles clicables visibles en la mitad inferior, para depurar REMAJU."""
    try:
        datos = page.evaluate(
            """() => {
                const h = window.innerHeight || 900;
                const els = Array.from(document.querySelectorAll('a,button,span,li,div[role=button],button[role=button]'));
                return els.map((el, idx) => {
                    const r = el.getBoundingClientRect();
                    const txt = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                    const cls = el.getAttribute('class') || '';
                    const aria = el.getAttribute('aria-label') || '';
                    const role = el.getAttribute('role') || '';
                    const disabled = el.getAttribute('disabled') || el.getAttribute('aria-disabled') || '';
                    return {idx, txt, cls, aria, role, disabled, x:r.x, y:r.y, w:r.width, h:r.height, visible: !!(r.width && r.height)};
                }).filter(x => x.visible && x.y > h * 0.35 && (x.txt || x.aria || x.cls));
            }"""
        )
        filtrados = []
        for d in datos:
            texto = str(d.get('txt') or '')
            clase = str(d.get('cls') or '')
            aria = str(d.get('aria') or '')
            combinado = f"{texto} {clase} {aria}".lower()
            if any(k in combinado for k in ['total', 'row', 'page', 'pagina', 'pagin', 'next', 'siguiente', 'first', 'last']) or texto in ['F','P','N','E','1','2','3','4','5','6','7','8','9','10','12']:
                filtrados.append(d)
        return json.dumps(filtrados[:80], ensure_ascii=False)
    except Exception as error:
        return f"ERROR_CLICKABLES: {error}"


def obtener_locator_siguiente(page: Page):
    """
    Devuelve un control candidato para avanzar página.

    REMAJU no siempre usa clases PrimeFaces visibles. En el texto plano aparece
    como: F P 1 2 3 4 5 N E / Rows Per Page. Por eso también probamos el
    control exacto 'N' y varios frameworks de paginación.
    """
    selectores = [
        ".ui-paginator-next:not(.ui-state-disabled)",
        ".ui-paginator .ui-paginator-next:not(.ui-state-disabled)",
        ".p-paginator-next:not(.p-disabled)",
        ".p-paginator-next:not(.disabled)",
        "[class*=\'paginator-next\']:not(.disabled)",
        "[class*=\'pagination-next\']:not(.disabled)",
        "a[aria-label*=\'Next\']:not(.disabled)",
        "button[aria-label*=\'Next\']:not(.disabled)",
        "a[aria-label*=\'Siguiente\']:not(.disabled)",
        "button[aria-label*=\'Siguiente\']:not(.disabled)",
        "button:has-text('Siguiente')",
        "a:has-text('Siguiente')",
        "span:has-text('Siguiente')",
        "button:has-text('Next')",
        "a:has-text('Next')",
        "span:has-text('Next')",
    ]

    for selector in selectores:
        try:
            loc = page.locator(selector)
            total = loc.count()
            if total == 0:
                continue
            for i in range(total):
                candidato = loc.nth(i)
                if es_control_paginacion_valido(candidato):
                    return candidato
        except Exception:
            pass

    # Fallback principal para REMAJU: botón textual exacto N.
    for texto in ["N", ">", "›", "»"]:
        candidato = obtener_locator_texto_paginacion(page, texto)
        if candidato is not None:
            return candidato

    return None


def es_control_paginacion_valido(locator) -> bool:
    try:
        if locator.count() == 0:
            return False
    except Exception:
        pass

    try:
        if not locator.is_visible(timeout=500):
            return False
    except Exception:
        pass

    try:
        datos = locator.evaluate(
            """el => {
                const r = el.getBoundingClientRect();
                return {
                    cls: (el.getAttribute('class') || '').toLowerCase(),
                    ariaDisabled: (el.getAttribute('aria-disabled') || '').toLowerCase(),
                    disabled: el.hasAttribute('disabled'),
                    txt: (el.innerText || el.textContent || '').replace(/\s+/g,' ').trim(),
                    x: r.x, y: r.y, w: r.width, h: r.height,
                    winH: window.innerHeight || 900
                };
            }"""
        )
        if datos.get("disabled") or datos.get("ariaDisabled") == "true" or "disabled" in datos.get("cls", ""):
            return False
        # Evitar clicks en menús superiores. El paginador está debajo de las tarjetas.
        if datos.get("y", 0) < datos.get("winH", 900) * 0.35:
            return False
        return True
    except Exception:
        return True


def obtener_locator_texto_paginacion(page: Page, texto_exact: str):
    """Busca controles visibles con texto exacto en la zona inferior."""
    consultas = [
        lambda: page.get_by_text(texto_exact, exact=True),
        lambda: page.locator(f"button:text-is('{texto_exact}')"),
        lambda: page.locator(f"a:text-is('{texto_exact}')"),
        lambda: page.locator(f"span:text-is('{texto_exact}')"),
        lambda: page.locator(f"li:text-is('{texto_exact}')"),
        lambda: page.locator(f"div[role=button]:text-is('{texto_exact}')"),
    ]

    candidatos = []
    for crear in consultas:
        try:
            loc = crear()
            total = loc.count()
            for i in range(total):
                cand = loc.nth(i)
                try:
                    if not cand.is_visible(timeout=300):
                        continue
                    datos = cand.evaluate(
                        """el => {
                            const r = el.getBoundingClientRect();
                            return {
                                x:r.x, y:r.y, w:r.width, h:r.height,
                                txt:(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim(),
                                cls:(el.getAttribute('class')||'').toLowerCase(),
                                ariaDisabled:(el.getAttribute('aria-disabled')||'').toLowerCase(),
                                disabled:el.hasAttribute('disabled'),
                                winH: window.innerHeight || 900
                            };
                        }"""
                    )
                    if datos.get("txt") != texto_exact:
                        continue
                    if datos.get("disabled") or datos.get("ariaDisabled") == "true" or "disabled" in datos.get("cls", ""):
                        continue
                    if datos.get("y", 0) < datos.get("winH", 900) * 0.35:
                        continue
                    # Preferimos controles pequeños, típicos de paginador.
                    if datos.get("w", 999) > 160 or datos.get("h", 999) > 90:
                        continue
                    candidatos.append((datos.get("y", 0), datos.get("x", 0), cand))
                except Exception:
                    pass
        except Exception:
            pass

    if not candidatos:
        return None

    # Usar el último en vertical, normalmente el paginador debajo del listado.
    candidatos.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidatos[0][2]


def obtener_locator_pagina_numero(page: Page, numero_pagina: int):
    """Fallback: busca el número de página siguiente exacto en la zona inferior."""
    return obtener_locator_texto_paginacion(page, str(numero_pagina))


def click_paginador(control, page: Page | None = None) -> bool:
    """Click robusto para controles PrimeFaces/REMAJU.

    REMAJU usa PrimeFaces/AJAX. En algunos casos control.click() se ejecuta
    sin disparar el AJAX. Por eso usamos, en este orden:
    1) scroll al fondo,
    2) click físico con mouse al centro del elemento,
    3) click Playwright normal/force,
    4) dispatch de eventos mouse.
    """
    try:
        if page is not None:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(400)
    except Exception:
        pass

    try:
        control.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass

    # 1) Click físico al centro. Suele ser el más confiable con PrimeFaces.
    if page is not None:
        try:
            box = control.bounding_box(timeout=3000)
            if box:
                x = box["x"] + box["width"] / 2
                y = box["y"] + box["height"] / 2
                page.mouse.move(x, y)
                page.wait_for_timeout(100)
                page.mouse.down()
                page.wait_for_timeout(80)
                page.mouse.up()
                return True
        except Exception:
            pass

    # 2) Clicks Playwright / JS.
    for intento in ("normal", "force", "js", "dispatch"):
        try:
            if intento == "normal":
                control.click(timeout=8000)
            elif intento == "force":
                control.click(timeout=8000, force=True)
            elif intento == "js":
                control.evaluate("el => el.click()")
            else:
                control.evaluate("""el => {
                    for (const tipo of ['mousedown','mouseup','click']) {
                        el.dispatchEvent(new MouseEvent(tipo, {bubbles:true, cancelable:true, view:window}));
                    }
                }""")
            return True
        except Exception:
            continue

    return False


def esperar_cambio_de_pagina(page: Page, clave_antes: str) -> bool:
    """Espera a que cambien los números de remate visibles."""
    try:
        page.wait_for_function(
            """claveAnterior => {
                const texto = document.body.innerText || '';
                const nums = [...texto.matchAll(/Remate\s+N[°º]\s*(\d+)/gi)].map(m => m[1]).join('|');
                return nums && nums !== claveAnterior;
            }""",
            arg=clave_antes,
            timeout=25000,
        )
        return True
    except Exception:
        page.wait_for_timeout(3000)
        return obtener_clave_pagina(page) != clave_antes


def seleccionar_filas_por_pagina(page: Page, filas: int = 12) -> None:
    """Intenta cambiar Rows Per Page a 12 para reducir paginación. Si falla, continúa."""
    try:
        actual = page.locator("body").inner_text(timeout=3000)
        if f"Rows Per Page 4 8 {filas}" not in actual and "Rows Per Page" not in actual:
            return

        # Solo click en el texto exacto si está en la zona inferior.
        loc = obtener_locator_texto_paginacion(page, str(filas))
        if loc is None:
            return

        clave_antes = obtener_clave_pagina(page)
        if click_paginador(loc, page):
            # Puede no cambiar números si sigue en página 1; esperamos redibujado.
            page.wait_for_load_state("domcontentloaded", timeout=5000)
            page.wait_for_timeout(2000)
            esperar_lista_remates(page, timeout=15000)
            log(f"Se intentó cambiar Rows Per Page a {filas}.")
    except Exception:
        pass


def ir_siguiente_pagina(page: Page, pagina_actual: int) -> bool:
    """Avanza una página en REMAJU usando el paginador PrimeFaces.

    Esta versión no usa el filtro por número. Usa el paginador real, pero con
    click físico por coordenadas y selectores específicos del paginador inferior.
    """
    try:
        clave_antes = obtener_clave_pagina(page)
        if not clave_antes:
            log("No pude leer clave de la página actual antes de paginar.")
            return False

        log(f"Intentando pasar de página {pagina_actual} a {pagina_actual + 1}...")

        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(700)
        except Exception:
            pass

        controles = []

        # 1) Selector exacto del botón N de PrimeFaces. Tomamos el último visible,
        # porque puede existir un paginador arriba y otro abajo.
        for selector in [
            "a.ui-paginator-next:not(.ui-state-disabled)",
            ".ui-paginator-next:not(.ui-state-disabled)",
            "[aria-label='Next Page']:not(.ui-state-disabled)",
        ]:
            try:
                loc = page.locator(selector)
                for i in range(loc.count() - 1, -1, -1):
                    cand = loc.nth(i)
                    if es_control_paginacion_valido(cand):
                        controles.append(cand)
                        break
            except Exception:
                pass

        # 2) Número de página siguiente.
        for selector in [
            f"a.ui-paginator-page:text-is('{pagina_actual + 1}')",
            f".ui-paginator-page:text-is('{pagina_actual + 1}')",
        ]:
            try:
                loc = page.locator(selector)
                for i in range(loc.count() - 1, -1, -1):
                    cand = loc.nth(i)
                    if es_control_paginacion_valido(cand):
                        controles.append(cand)
                        break
            except Exception:
                pass

        # 3) Fallbacks anteriores.
        for control in [
            obtener_locator_siguiente(page),
            obtener_locator_pagina_numero(page, pagina_actual + 1),
            obtener_locator_texto_paginacion(page, "N"),
        ]:
            if control is not None:
                controles.append(control)

        # Quitar duplicados aproximados por bounding box.
        vistos = set()
        controles_limpios = []
        for control in controles:
            if control is None:
                continue
            try:
                box = control.bounding_box(timeout=1000)
                firma = tuple(round(box.get(k, 0)) for k in ("x", "y", "width", "height")) if box else id(control)
            except Exception:
                firma = id(control)
            if firma in vistos:
                continue
            vistos.add(firma)
            controles_limpios.append(control)

        for control in controles_limpios:
            try:
                datos_control = control.evaluate("el => ({txt:(el.innerText||el.textContent||'').trim(), cls:el.className || '', html:(el.outerHTML||'').slice(0,250)})")
                log(f"Probando control paginación: {datos_control}")
            except Exception:
                pass

            if not click_paginador(control, page):
                continue

            if esperar_cambio_de_pagina(page, clave_antes):
                esperar_lista_remates(page, timeout=25000)
                clave_despues = obtener_clave_pagina(page)
                log(f"Página cambiada correctamente: {clave_antes} -> {clave_despues}")
                return True

            log("El click se ejecutó, pero no cambió la lista de remates.")

        log("No encontré botón siguiente funcional ni número de página siguiente.")
        log(f"HTML paginador: {obtener_html_paginador(page)}")
        log(f"Clickables paginación: {diagnosticar_clickables_paginacion(page)}")
        return False
    except Exception as error:
        log(f"No se pudo avanzar a la siguiente página: {error}")
        log(f"HTML paginador: {obtener_html_paginador(page)}")
        log(f"Clickables paginación: {diagnosticar_clickables_paginacion(page)}")
        return False


def recargar_listado_remaju(page: Page) -> bool:
    """Vuelve al listado público desde cero.

    Esto evita que PrimeFaces deje el DOM en estado corrupto después de abrir
    varias páginas de detalle. Es más lento, pero mucho más estable para
    cargar todos los avisos.
    """
    try:
        page.goto(URL_REMAJU_PUBLICA, wait_until="networkidle", timeout=60000)
        esperar_lista_remates(page, timeout=30000)
        return True
    except Exception as error:
        log(f"No pude recargar el listado REMAJU: {error}")
        return False


def navegar_a_pagina_desde_inicio(page: Page, pagina_objetivo: int) -> bool:
    """Carga la página 1 y avanza hasta pagina_objetivo.

    La V6 funcionaba varias páginas y luego perdía el paginador. La causa es
    el estado AJAX de REMAJU/PrimeFaces después de abrir muchos detalles.
    Esta versión reinicia el listado para cada página objetivo, avanza desde
    la página 1 y recién ahí extrae los 4 avisos de esa página.
    """
    if pagina_objetivo <= 1:
        return recargar_listado_remaju(page)

    if not recargar_listado_remaju(page):
        return False

    pagina_actual = 1
    while pagina_actual < pagina_objetivo:
        if not ir_siguiente_pagina(page, pagina_actual):
            log(f"No pude llegar a la página {pagina_objetivo}; me quedé en {pagina_actual}.")
            return False
        pagina_actual += 1

    return True


def obtener_total_publicado_desde_pagina(page: Page) -> int:
    """Intenta leer 'Total: N registros' desde la página de REMAJU."""
    try:
        texto = page.locator("body").inner_text(timeout=8000)
    except Exception:
        return 0

    patrones = [
        r"Total\s*:?\s*(\d+)\s*registros",
        r"(\d+)\s*registros",
        r"Total\s*:?\s*(\d+)",
    ]

    for patron in patrones:
        m = re.search(patron, texto, flags=re.I)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return 0

    return 0


def extraer_remates_remaju(
    limite: int = 0,
    max_paginas: int = 0,
    visible: bool = False,
) -> list[dict[str, Any]]:
    """Extrae remates de REMAJU reiniciando el listado por cada página.

    - limite=0 significa sin límite de registros.
    - max_paginas=0 intenta calcular todas las páginas desde el total publicado.

    Esta estrategia es intencionalmente más lenta que paginar en una sola
    sesión, pero evita el error donde el paginador desaparece o vuelve a página
    1 después de varios clicks en Detalle.
    """
    if sync_playwright is None:
        raise RuntimeError(
            "Playwright no está instalado. Ejecuta: python -m pip install playwright && python -m playwright install chromium"
        )

    resultados: list[dict[str, Any]] = []
    expedientes_vistos: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not visible)
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1400, "height": 950},
        )
        page = context.new_page()

        log(f"Scraper version: {VERSION_SCRAPER}")
        log(f"Abriendo REMAJU: {URL_REMAJU_PUBLICA}")

        if not recargar_listado_remaju(page):
            context.close()
            browser.close()
            return []

        total_publicado = obtener_total_publicado_desde_pagina(page)
        paginas_estimadas = (total_publicado + 3) // 4 if total_publicado else 0

        if max_paginas > 0:
            paginas_a_recorrer = max_paginas
        elif limite > 0:
            paginas_a_recorrer = (limite + 3) // 4
            if paginas_estimadas:
                paginas_a_recorrer = min(paginas_a_recorrer, paginas_estimadas)
        elif paginas_estimadas:
            paginas_a_recorrer = paginas_estimadas
        else:
            # Fallback defensivo si REMAJU no muestra el total.
            paginas_a_recorrer = 80

        log(
            f"Total publicado detectado: {total_publicado or 'no detectado'} | "
            f"páginas a recorrer: {paginas_a_recorrer}"
        )

        pagina = 1
        paginas_sin_nuevos = 0

        while pagina <= paginas_a_recorrer:
            if limite and len(resultados) >= limite:
                log(f"Límite alcanzado: {limite} remates.")
                break

            if not navegar_a_pagina_desde_inicio(page, pagina):
                log(f"No se pudo abrir la página {pagina}. Se detiene la carga.")
                break

            texto_pagina = page.locator("body").inner_text(timeout=12000)
            bloques = separar_bloques_remate(texto_pagina)

            if not bloques:
                log(f"Página {pagina}: no se detectaron remates.")
                break

            log(f"Página {pagina}: remates visibles detectados: {len(bloques)}")
            nuevos_en_pagina = 0

            for indice, bloque in enumerate(bloques):
                if limite and len(resultados) >= limite:
                    break

                numero = re.search(r"Remate\s+N[°º]\s*(\d+)", bloque, flags=re.I)
                numero_txt = numero.group(1) if numero else str(indice + 1)
                expediente_tmp = f"REMAJU-{numero_txt}"

                if expediente_tmp in expedientes_vistos:
                    log(f"  Saltando duplicado en ejecución: {expediente_tmp}")
                    continue

                log(f"[{len(resultados) + 1}] Página {pagina} | Remate {numero_txt}")

                # Como reiniciamos el listado por página, podemos abrir el detalle
                # sin miedo a perder el estado para la siguiente página.
                detalle_texto = capturar_texto_detalle(page, numero_txt)

                if detalle_texto:
                    m_det = re.search(r"Remate\s+N[°º]\s*(\d+)", detalle_texto, flags=re.I)
                    if m_det and m_det.group(1) != numero_txt:
                        log(
                            f"  Advertencia: detalle cruzado para REMAJU-{numero_txt}; "
                            f"el detalle dice REMAJU-{m_det.group(1)}. Se omitirá detalle_texto."
                        )
                        detalle_texto = ""

                # No usamos el botón Aviso porque REMAJU no ofrece URL única
                # estable por aviso; usamos el detalle capturado localmente.
                url_aviso = ""

                try:
                    if "remateExterno.xhtml" not in page.url:
                        page.go_back(wait_until="domcontentloaded", timeout=15000)
                    esperar_lista_remates(page, timeout=20000)
                except Exception:
                    # Si no vuelve limpio, recargamos la página objetivo para
                    # seguir con el resto de tarjetas de esa misma página.
                    navegar_a_pagina_desde_inicio(page, pagina)

                remate = parsear_bloque_remate(
                    bloque=bloque,
                    url_aviso=url_aviso,
                    detalle_texto=detalle_texto,
                )

                if remate:
                    expedientes_vistos.add(remate.expediente)
                    resultados.append(asdict(remate))
                    nuevos_en_pagina += 1
                    log(f"  OK {remate.expediente} | {remate.distrito} | URL: {remate.url_detalle}")
                else:
                    log(f"  No se pudo parsear remate {numero_txt}")

            if nuevos_en_pagina == 0:
                paginas_sin_nuevos += 1
            else:
                paginas_sin_nuevos = 0

            if paginas_sin_nuevos >= 3:
                log("Tres páginas seguidas sin remates nuevos. Se detiene la carga.")
                break

            pagina += 1

        context.close()
        browser.close()

    log(f"Total extraído: {len(resultados)} remates.")
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
    parser.add_argument("--limite", type=int, default=0, help="Cantidad máxima de remates a procesar. 0 = todos")
    parser.add_argument("--paginas", type=int, default=0, help="Cantidad máxima de páginas a recorrer. 0 = todas")
    parser.add_argument("--no-guardar", action="store_true", help="Solo extrae y muestra; no guarda en Supabase")
    parser.add_argument("--visible", action="store_true", help="Abre Chromium visible para depuración")
    parser.add_argument("--json", action="store_true", help="Imprime JSON completo de lo extraído")
    parser.add_argument("--limpiar-malos", action="store_true", help="Elimina registros SEMILLA y URLs de manual/instructivo")

    args = parser.parse_args(argv)

    if args.limpiar_malos:
        resultado = limpiar_registros_malos()
        log(f"Limpieza BD: {resultado}")

    remates = extraer_remates_remaju(limite=args.limite, visible=args.visible, max_paginas=args.paginas)

    if args.json or args.no_guardar:
        print(json.dumps(remates, ensure_ascii=False, indent=2))

    if not args.no_guardar:
        resultados = guardar_varios_inmuebles(remates)
        log(json.dumps(resultados, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
