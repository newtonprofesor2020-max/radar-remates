import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "./Dashboard.css";

const API_URL = "http://127.0.0.1:8000";

function limpiarTexto(texto) {
  return String(texto || "").trim().toLowerCase();
}

function normalizarNumero(valor) {
  if (valor === null || valor === undefined || valor === "") {
    return 0;
  }

  const texto = String(valor).replace(/,/g, "").trim();
  const numero = Number(texto);

  return Number.isFinite(numero) ? numero : 0;
}

function normalizarUrl(url) {
  const texto = String(url || "").trim();

  if (!texto) return "";
  if (texto.startsWith("http://") || texto.startsWith("https://")) return texto;
  if (texto.startsWith("www.")) return `https://${texto}`;

  return "";
}

function obtenerUrlAviso(item) {
  const candidatos = [
    item?.url_detalle,
    item?.url_original,
    item?.url,
    item?.fuente_url,
    item?.aviso_url,
    item?.url_aviso,
    item?.remate_url,
    item?.url_remaju,
    item?.enlace,
    item?.link,
  ];

  for (const candidato of candidatos) {
    const url = normalizarUrl(candidato);
    if (url) return url;
  }

  const valores = Object.values(item || {});
  for (const valor of valores) {
    if (typeof valor !== "string") continue;
    const coincidencia = valor.match(/https?:\/\/[^\s)]+/i);
    if (coincidencia) return coincidencia[0];
  }

  return "";
}

function normalizarInmueble(item) {
  const precioRemate = normalizarNumero(item.precio_base || item.precio_remate);

  const valorMercado = normalizarNumero(
    item.valor_mercado || item.valor_comercial || item.tasacion
  );

  const ganancia =
    item.ganancia_estimada !== null && item.ganancia_estimada !== undefined
      ? normalizarNumero(item.ganancia_estimada)
      : valorMercado - precioRemate;

  const margen =
    item.porcentaje_descuento !== null &&
    item.porcentaje_descuento !== undefined
      ? normalizarNumero(item.porcentaje_descuento)
      : valorMercado > 0
      ? Math.round(((valorMercado - precioRemate) / valorMercado) * 100)
      : 0;

  const score = normalizarNumero(item.score || item.puntaje || 0);

  return {
    id: item.id,
    expediente: item.expediente || "Sin expediente",
    direccion: item.direccion || "Dirección no registrada",
    distrito: item.distrito || "Sin distrito",
    tipo: item.tipo || "Inmueble",
    area: item.area ? `${item.area} m²` : "No indicado",
    tasacion: normalizarNumero(item.tasacion),
    precioRemate,
    valorMercado,
    ganancia,
    margen,
    riesgo:
      item.riesgo || (score >= 85 ? "Bajo" : score >= 70 ? "Medio" : "Alto"),
    score,
    estado: item.estado || "Activo",
    convocatoria:
      item.convocatoria || item.nivel_oportunidad || "Sin convocatoria",
    fechaRemate:
      item.fecha_remate || item.fecha_presentacion || item.fecha || "No indicada",
    horaRemate: item.hora_remate || item.hora_presentacion || "",
    juzgado: item.juzgado || "No registrado",
    fuente: item.fuente || "REMAJU",
    descripcion: item.descripcion || "",
    numeroRemate: item.numero_remate || item.remate || "",
    urlDetalle: obtenerUrlAviso(item),
    lat: normalizarNumero(item.lat) || -12.0464,
    lng: normalizarNumero(item.lng) || -77.0428,
    ubicacionTipo: item.ubicacion_tipo || "aproximada",
  };
}

function formatoNumero(valor, decimales = 0) {
  const n = normalizarNumero(valor);
  const fijo = n.toFixed(decimales);
  const [entero, decimal] = fijo.split(".");
  const enteroConComas = entero.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return decimal !== undefined ? `${enteroConComas}.${decimal}` : enteroConComas;
}

function formatoSoles(valor, decimales = 0) {
  const numero = normalizarNumero(valor);

  return `S/ ${new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  }).format(numero)}`;
}

function formatoPorcentaje(valor, decimales = 0) {
  return `${formatoNumero(valor, decimales)}%`;
}

function tieneUrlAviso(item) {
  const url = String(item?.urlDetalle || "").trim();
  return url.startsWith("http://") || url.startsWith("https://");
}


function esFuenteRemaJu(item) {
  return (
    limpiarTexto(item?.fuente) === "remaju" ||
    String(item?.expediente || "").toUpperCase().startsWith("REMAJU-")
  );
}

function puedeVerDetalleRemaJu(item) {
  return Boolean(item?.id && esFuenteRemaJu(item)) || tieneUrlAviso(item);
}

function obtenerUrlDetalleRemaJu(item) {
  if (item?.id && esFuenteRemaJu(item)) {
    return `${API_URL}/inmueble/${item.id}/aviso-remaju`;
  }

  return item?.urlDetalle || "";
}

function escaparHTML(valor) {
  return String(valor ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function calcularGastosEstimados(precioRemate) {
  // Estimación referencial para trámites, impuestos, notaría y saneamiento inicial.
  return Math.round(normalizarNumero(precioRemate) * 0.07);
}

function calcularInversionTotal(item) {
  return normalizarNumero(item?.precioRemate) + calcularGastosEstimados(item?.precioRemate);
}

function calcularRentabilidad(item) {
  const inversionTotal = calcularInversionTotal(item);

  if (inversionTotal <= 0) {
    return 0;
  }

  return Math.round((normalizarNumero(item?.ganancia) / inversionTotal) * 100);
}

function obtenerCategoria(item) {
  if (!item) return "Sin datos";

  if (item.score >= 85 && item.margen >= 30) {
    return "Excelente oportunidad";
  }

  if (item.score >= 70 || item.margen >= 25) {
    return "Buena oportunidad";
  }

  return "Oportunidad con riesgo";
}

function obtenerRecomendacion(item) {
  if (!item) {
    return "No hay suficientes datos para emitir una recomendación.";
  }

  const riesgo = limpiarTexto(item.riesgo);
  const esDerechosAcciones = limpiarTexto(item.tipo).includes("derechos") ||
    limpiarTexto(item.descripcion).includes("derechos y acciones");

  if (esDerechosAcciones) {
    return "No ofertar todavía: revisar si se trata de derechos y acciones, porcentaje de participación y posibilidad real de independización o posesión.";
  }

  if (riesgo === "alto") {
    return "Analizar con cautela: validar SUNARP, ocupación, cargas, estado procesal y gastos antes de separar capital para la oferta.";
  }

  if (item.margen >= 30 && item.score >= 80) {
    return "Candidato prioritario: avanzar con revisión registral, verificación de ocupación y comparación de precios reales antes de ofertar.";
  }

  return "Oportunidad interesante, pero conviene compararla con otros inmuebles del distrito y validar documentos antes de tomar decisión.";
}

function generarHTMLInforme(item) {
  const gastos = calcularGastosEstimados(item.precioRemate);
  const inversionTotal = calcularInversionTotal(item);
  const rentabilidad = calcularRentabilidad(item);
  const avisoHtml = puedeVerDetalleRemaJu(item)
    ? `<a class="btn" href="${escaparHTML(obtenerUrlDetalleRemaJu(item))}" target="_blank" rel="noopener noreferrer">Ver detalle REMAJU ↗</a>`
    : `<span class="muted">Detalle REMAJU no disponible para este inmueble. Vuelve a ejecutar el scraper actualizado.</span>`;

  return `
    <!doctype html>
    <html lang="es">
      <head>
        <meta charset="utf-8" />
        <title>Informe - ${escaparHTML(item.distrito)}</title>
        <style>
          body { font-family: Arial, sans-serif; color: #0f172a; padding: 32px; }
          h1 { color: #071b3a; margin-bottom: 4px; }
          p { color: #475569; }
          table { width: 100%; border-collapse: collapse; margin-top: 18px; }
          th, td { border: 1px solid #e2e8f0; padding: 10px; text-align: left; }
          th { background: #f1f5f9; }
          .box { border: 1px solid #dbeafe; background: #eff6ff; padding: 14px; border-radius: 12px; margin-top: 18px; }
          .actions { margin: 18px 0; display: flex; gap: 10px; flex-wrap: wrap; }
          .btn { display: inline-block; background: #0b5cff; color: white; padding: 11px 14px; border-radius: 10px; font-weight: bold; text-decoration: none; }
          .btn-light { background: #eaf1ff; color: #0b3ea8; }
          .muted { color: #64748b; font-size: 13px; }
        </style>
      </head>
      <body>
        <h1>Informe de oportunidad inmobiliaria</h1>
        <p>Generado desde Radar Remates</p>

        <div class="actions">
          ${avisoHtml}
          <a class="btn btn-light" href="javascript:window.print()">Imprimir / Guardar PDF</a>
        </div>

        <table>
          <tbody>
            <tr><th>Distrito</th><td>${escaparHTML(item.distrito)}</td></tr>
            <tr><th>Dirección</th><td>${escaparHTML(item.direccion)}</td></tr>
            <tr><th>Tipo</th><td>${escaparHTML(item.tipo)}</td></tr>
            <tr><th>Precio de remate</th><td>${formatoSoles(item.precioRemate)}</td></tr>
            <tr><th>Valor de mercado estimado</th><td>${formatoSoles(item.valorMercado)}</td></tr>
            <tr><th>Ahorro estimado</th><td>${formatoSoles(item.ganancia)}</td></tr>
            <tr><th>Gastos referenciales</th><td>${formatoSoles(gastos)}</td></tr>
            <tr><th>Inversión total referencial</th><td>${formatoSoles(inversionTotal)}</td></tr>
            <tr><th>Margen</th><td>${formatoPorcentaje(item.margen)}</td></tr>
            <tr><th>Rentabilidad referencial</th><td>${formatoPorcentaje(rentabilidad)}</td></tr>
            <tr><th>Riesgo</th><td>${escaparHTML(item.riesgo)}</td></tr>
            <tr><th>Puntaje</th><td>${item.score}/100</td></tr>
            <tr><th>Estado</th><td>${escaparHTML(item.estado)}</td></tr>
            <tr><th>Convocatoria</th><td>${escaparHTML(item.convocatoria)}</td></tr>
            <tr><th>Fecha de remate</th><td>${escaparHTML(`${item.fechaRemate} ${item.horaRemate}`.trim())}</td></tr>
            <tr><th>Juzgado / fuente</th><td>${escaparHTML(`${item.juzgado} / ${item.fuente}`)}</td></tr>
          </tbody>
        </table>

        <div class="box">
          <strong>Recomendación:</strong> ${escaparHTML(obtenerRecomendacion(item))}
        </div>
      </body>
    </html>
  `;
}

function AjustarVistaMapa({ puntos }) {
  const map = useMap();

  useEffect(() => {
    const puntosValidos = puntos
      .map((item) => ({
        item,
        posicion: [item.latMapa, item.lngMapa],
      }))
      .filter(({ posicion }) =>
        Number.isFinite(posicion[0]) && Number.isFinite(posicion[1])
      );

    const timer = setTimeout(() => {
      map.invalidateSize();
    }, 120);

    if (puntosValidos.length === 0) {
      map.setView([-12.0464, -77.0428], 11);
      return () => clearTimeout(timer);
    }

    if (puntosValidos.length === 1) {
      const { item, posicion } = puntosValidos[0];
      const zoom = item.ubicacionTipo === "exacta" ? 17 : 15;

      map.setView(posicion, zoom, {
        animate: true,
      });

      return () => clearTimeout(timer);
    }

    map.fitBounds(
      puntosValidos.map(({ posicion }) => posicion),
      {
        padding: [45, 45],
        maxZoom: 15,
      }
    );

    return () => clearTimeout(timer);
  }, [map, puntos]);

  return null;
}

function Dashboard() {
  const [remates, setRemates] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [favoritosIds, setFavoritosIds] = useState([]);

  const [busqueda, setBusqueda] = useState("");
  const [riesgo, setRiesgo] = useState("Todos");
  const [distrito, setDistrito] = useState("Todos");
  const [estado, setEstado] = useState("Todos");
  const [precioMin, setPrecioMin] = useState("");
  const [precioMax, setPrecioMax] = useState("");

  const [paginaActual, setPaginaActual] = useState(1);
  const itemsPorPagina = 6;

  const cargarRanking = async () => {
    try {
      setCargando(true);
      setError("");

      const response = await fetch(`${API_URL}/ranking`);

      if (!response.ok) {
        throw new Error(`Error HTTP: ${response.status}`);
      }

      const data = await response.json();
      const lista = Array.isArray(data) ? data : [];
      const datos = lista.map(normalizarInmueble);

      setRemates(datos);
    } catch (error) {
      console.error("Error cargando ranking:", error);
      setError("No se pudo cargar la información del backend.");
      setRemates([]);
    } finally {
      setCargando(false);
    }
  };

  const cargarFavoritosIds = async () => {
    try {
      const response = await fetch(`${API_URL}/favoritos/ids`);

      if (!response.ok) {
        throw new Error(`Error HTTP: ${response.status}`);
      }

      const data = await response.json();
      setFavoritosIds(Array.isArray(data) ? data.map(String) : []);
    } catch (error) {
      console.error("Error cargando favoritos:", error);
      setFavoritosIds([]);
    }
  };

  const alternarFavorito = async (inmuebleId) => {
    const idTexto = String(inmuebleId);
    const yaEsFavorito = favoritosIds.includes(idTexto);

    try {
      const response = await fetch(`${API_URL}/favoritos/${inmuebleId}`, {
        method: yaEsFavorito ? "DELETE" : "POST",
      });

      if (!response.ok) {
        throw new Error("No se pudo actualizar el favorito.");
      }

      setFavoritosIds((lista) =>
        yaEsFavorito
          ? lista.filter((item) => item !== idTexto)
          : [...lista, idTexto]
      );
    } catch (error) {
      console.error("Error actualizando favorito:", error);
      setError("No se pudo actualizar el favorito.");
    }
  };

  useEffect(() => {
    cargarRanking();
    cargarFavoritosIds();
  }, []);

  const distritos = useMemo(() => {
    const lista = remates
      .map((item) => item.distrito)
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b));

    return ["Todos", ...new Set(lista)];
  }, [remates]);

  const estadosRemate = useMemo(() => {
    const estadosBase = ["Activo", "Finalizado", "Adjudicado", "Retirado", "Observado"];

    const estadosDesdeDatos = remates
      .map((item) => item.estado)
      .filter(Boolean);

    return ["Todos", ...new Set([...estadosBase, ...estadosDesdeDatos])];
  }, [remates]);

  const rematesFiltrados = useMemo(() => {
    return remates.filter((item) => {
      const textoBusqueda = limpiarTexto(busqueda);

      const coincideBusqueda =
        textoBusqueda === "" ||
        limpiarTexto(item.distrito).includes(textoBusqueda) ||
        limpiarTexto(item.tipo).includes(textoBusqueda) ||
        limpiarTexto(item.direccion).includes(textoBusqueda) ||
        limpiarTexto(item.expediente).includes(textoBusqueda);

      const coincideRiesgo =
        riesgo === "Todos" ||
        limpiarTexto(item.riesgo) === limpiarTexto(riesgo);

      const coincideDistrito =
        distrito === "Todos" ||
        limpiarTexto(item.distrito) === limpiarTexto(distrito);

      const coincideEstado =
        estado === "Todos" ||
        limpiarTexto(item.estado) === limpiarTexto(estado);

      const cumplePrecioMin =
        precioMin === "" || item.precioRemate >= Number(precioMin);

      const cumplePrecioMax =
        precioMax === "" || item.precioRemate <= Number(precioMax);

      return (
        coincideBusqueda &&
        coincideRiesgo &&
        coincideDistrito &&
        coincideEstado &&
        cumplePrecioMin &&
        cumplePrecioMax
      );
    });
  }, [remates, busqueda, riesgo, distrito, estado, precioMin, precioMax]);

  useEffect(() => {
    setPaginaActual(1);
  }, [busqueda, riesgo, distrito, estado, precioMin, precioMax]);

  const totalPaginas = Math.max(
    1,
    Math.ceil(rematesFiltrados.length / itemsPorPagina)
  );

  const indiceInicial = (paginaActual - 1) * itemsPorPagina;
  const indiceFinal = indiceInicial + itemsPorPagina;

  const rematesPaginados = rematesFiltrados.slice(indiceInicial, indiceFinal);

  const rematesMapa = useMemo(() => {
    const contadorCoordenadas = {};

    return rematesPaginados.map((item) => {
      const clave = `${item.lat},${item.lng}`;
      const cantidad = contadorCoordenadas[clave] || 0;
      contadorCoordenadas[clave] = cantidad + 1;

      const angulo = cantidad * 45 * (Math.PI / 180);
      const distancia = cantidad === 0 ? 0 : 0.0025;

      const latAjustada = item.lat + Math.sin(angulo) * distancia;
      const lngAjustada = item.lng + Math.cos(angulo) * distancia;

      return {
        ...item,
        latMapa: latAjustada,
        lngMapa: lngAjustada,
        posicionRepetida: cantidad > 0,
      };
    });
  }, [rematesPaginados]);

  const centroInicialMapa = rematesMapa.length > 0
    ? [rematesMapa[0].latMapa, rematesMapa[0].lngMapa]
    : [-12.0464, -77.0428];

  const totalRemates = remates.length;

  const mejoresOportunidades = remates.filter(
    (item) => item.margen >= 30 || item.score >= 80
  ).length;

  const riesgoBajo = remates.filter(
    (item) => limpiarTexto(item.riesgo) === "bajo"
  ).length;

  const gananciaPromedio =
    remates.length > 0
      ? remates.reduce((total, item) => total + item.ganancia, 0) /
        remates.length
      : 0;

  const mejorInmueble = useMemo(() => {
    if (rematesFiltrados.length === 0) return null;

    return [...rematesFiltrados].sort((a, b) => b.score - a.score)[0];
  }, [rematesFiltrados]);

  const resumenInforme = useMemo(() => {
    if (!mejorInmueble) return null;

    const gastos = calcularGastosEstimados(mejorInmueble.precioRemate);
    const inversionTotal = calcularInversionTotal(mejorInmueble);
    const rentabilidad = calcularRentabilidad(mejorInmueble);

    return {
      gastos,
      inversionTotal,
      rentabilidad,
      categoria: obtenerCategoria(mejorInmueble),
      recomendacion: obtenerRecomendacion(mejorInmueble),
    };
  }, [mejorInmueble]);

  const imprimirInforme = () => {
    if (!mejorInmueble) return;

    const ventana = window.open("", "_blank", "width=900,height=700");

    if (!ventana) {
      setError("El navegador bloqueó la ventana para generar el informe.");
      return;
    }

    ventana.document.open();
    ventana.document.write(generarHTMLInforme(mejorInmueble));
    ventana.document.close();
    ventana.focus();
    ventana.print();
  };

  return (
    <main className="dashboard">
      <aside className="sidebar">
        <div className="logo">
          <span>RR</span>
          <div>
            <h2>Radar Remates</h2>
            <p>Oportunidades inmobiliarias</p>
          </div>
        </div>

        <nav>
          <Link to="/" className="activo">
            Dashboard
          </Link>

          <a href="#remates">
            Remates
          </a>

          <a href="#oportunidades">
            Oportunidades
          </a>

          <a href="#mapa">
            Mapa
          </a>

          <Link to="/favoritos">
            Favoritos
          </Link>

          <a href="#informes">
            Informes
          </a>
        </nav>
      </aside>

      <section className="contenido">
        <header className="topbar">
          <div>
            <h1>Dashboard de Remates</h1>
            <p>Vista resumida para encontrar oportunidades y abrir informes completos cuando haga falta.</p>
          </div>

          <button onClick={cargarRanking} disabled={cargando}>
            {cargando ? "Cargando..." : "Actualizar datos"}
          </button>
        </header>

        {error && <div className="alerta-error">{error}</div>}

        <section className="cards">
          <div className="card">
            <p>Total remates</p>
            <h3>{totalRemates}</h3>
            <span>Datos cargados</span>
          </div>

          <div className="card">
            <p>Mejores oportunidades</p>
            <h3>{mejoresOportunidades}</h3>
            <span>Margen mayor al 30%</span>
          </div>

          <div className="card">
            <p>Ganancia promedio</p>
            <h3>{formatoSoles(gananciaPromedio)}</h3>
            <span>Estimación referencial</span>
          </div>

          <div className="card">
            <p>Riesgo bajo</p>
            <h3>{riesgoBajo}</h3>
            <span>Mejores candidatos</span>
          </div>
        </section>

        <section className="panel" id="remates">
          <div className="panel-header">
            <div>
              <h2>Las mejores oportunidades</h2>
              <p>
                Ranking basado en precio de remate, valor comercial, ganancia
                estimada y margen.
              </p>
            </div>

            <div className="filtros">
              <input
                type="text"
                placeholder="Buscar distrito, dirección o tipo..."
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
              />

              <select value={riesgo} onChange={(e) => setRiesgo(e.target.value)}>
                <option>Todos</option>
                <option>Bajo</option>
                <option>Medio</option>
                <option>Alto</option>
              </select>

              <select value={estado} onChange={(e) => setEstado(e.target.value)}>
                {estadosRemate.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>

              <select
                value={distrito}
                onChange={(e) => setDistrito(e.target.value)}
              >
                {distritos.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>

              <input
                type="number"
                placeholder="Precio mín."
                value={precioMin}
                onChange={(e) => setPrecioMin(e.target.value)}
              />

              <input
                type="number"
                placeholder="Precio máx."
                value={precioMax}
                onChange={(e) => setPrecioMax(e.target.value)}
              />
            </div>
          </div>

          <div className="tabla-contenedor">
            <table>
              <thead>
                <tr>
                  <th>Inmueble</th>
                  <th>Precio remate</th>
                  <th>Valor mercado</th>
                  <th>Ahorro</th>
                  <th>Margen</th>
                  <th>Riesgo / Puntaje</th>
                  <th>Acciones</th>
                </tr>
              </thead>

              <tbody>
                {cargando ? (
                  <tr>
                    <td colSpan="7" className="estado-tabla">
                      Cargando inmuebles...
                    </td>
                  </tr>
                ) : rematesFiltrados.length === 0 ? (
                  <tr>
                    <td colSpan="7" className="estado-tabla">
                      No hay inmuebles que coincidan con los filtros actuales.
                    </td>
                  </tr>
                ) : (
                  rematesPaginados.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>{item.distrito}</strong>
                        <small>{item.direccion}</small>
                        <small>{item.tipo} · {item.area}</small>
                      </td>

                      <td>{formatoSoles(item.precioRemate)}</td>
                      <td>{formatoSoles(item.valorMercado)}</td>

                      <td className={item.ganancia >= 0 ? "ganancia" : "perdida"}>
                        {formatoSoles(item.ganancia)}
                      </td>

                      <td>{formatoPorcentaje(item.margen)}</td>

                      <td>
                        <span className={`badge ${limpiarTexto(item.riesgo)}`}>
                          {item.riesgo}
                        </span>
                        <span
                          className={`score score-compacto ${
                            item.score >= 85
                              ? "score-alto"
                              : item.score >= 70
                              ? "score-medio"
                              : "score-bajo"
                          }`}
                        >
                          {item.score}/100
                        </span>
                        <small>{item.estado}</small>
                      </td>

                      <td>
                        <div className="acciones-tabla">
                          <Link className="ver-detalle" to={`/inmueble/${item.id}`}>
                            Detalle
                          </Link>

                          {puedeVerDetalleRemaJu(item) && (
                            <a
                              className="link-aviso"
                              href={obtenerUrlDetalleRemaJu(item)}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              Ver detalle REMAJU ↗
                            </a>
                          )}

                          <button
                            type="button"
                            className={`btn-favorito ${
                              favoritosIds.includes(String(item.id)) ? "activo" : ""
                            }`}
                            onClick={() => alternarFavorito(item.id)}
                            title={
                              favoritosIds.includes(String(item.id))
                                ? "Quitar de favoritos"
                                : "Guardar en favoritos"
                            }
                          >
                            {favoritosIds.includes(String(item.id)) ? "★" : "☆"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {rematesFiltrados.length > 0 && (
            <div className="paginacion">
              <div className="paginacion-info">
                Mostrando {indiceInicial + 1} -{" "}
                {Math.min(indiceFinal, rematesFiltrados.length)} de{" "}
                {rematesFiltrados.length} inmuebles
              </div>

              <div className="paginacion-botones">
                <button
                  onClick={() =>
                    setPaginaActual((pagina) => Math.max(1, pagina - 1))
                  }
                  disabled={paginaActual === 1}
                >
                  ← Anterior
                </button>

                <span>
                  Página {paginaActual} de {totalPaginas}
                </span>

                <button
                  onClick={() =>
                    setPaginaActual((pagina) =>
                      Math.min(totalPaginas, pagina + 1)
                    )
                  }
                  disabled={paginaActual === totalPaginas}
                >
                  Siguiente →
                </button>
              </div>
            </div>
          )}
        </section>

        {mejorInmueble && resumenInforme && (
          <section className="panel analisis-panel" id="oportunidades">
            <div className="analisis-header">
              <div>
                <h2>Análisis de oportunidad</h2>
                <p>
                  Resumen ejecutivo del inmueble con mejor puntaje según los filtros
                  aplicados.
                </p>
              </div>

              <div className="acciones-informe">
                <span className="analisis-etiqueta">Mejor oportunidad</span>
                <button type="button" className="btn-secundario" onClick={imprimirInforme}>
                  Imprimir / PDF
                </button>
                {puedeVerDetalleRemaJu(mejorInmueble) && (
                  <a
                    className="btn-terciario"
                    href={obtenerUrlDetalleRemaJu(mejorInmueble)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Ver detalle REMAJU ↗
                  </a>
                )}
                <Link className="btn-terciario" to={`/inmueble/${mejorInmueble.id}`}>
                  Ver detalle
                </Link>
              </div>
            </div>

            <div className="analisis-grid analisis-grid-resumen">
              <div>
                <span>Distrito</span>
                <strong>{mejorInmueble.distrito}</strong>
              </div>

              <div>
                <span>Precio de remate</span>
                <strong>{formatoSoles(mejorInmueble.precioRemate)}</strong>
              </div>

              <div>
                <span>Valor mercado</span>
                <strong>{formatoSoles(mejorInmueble.valorMercado)}</strong>
              </div>

              <div>
                <span>Ahorro estimado</span>
                <strong>{formatoSoles(mejorInmueble.ganancia)}</strong>
              </div>

              <div>
                <span>Margen</span>
                <strong>{formatoPorcentaje(mejorInmueble.margen)}</strong>
              </div>

              <div>
                <span>Puntaje</span>
                <strong>{mejorInmueble.score}/100</strong>
              </div>
            </div>

            <div className="recomendacion-box">
              <span>Recomendación operativa</span>
              <p>{resumenInforme.recomendacion}</p>
            </div>
          </section>
        )}

        <section className="grid-inferior">
          <div className="panel mapa" id="mapa">
            <h2>Mapa de oportunidades</h2>
            <p>
              Mostrando las ubicaciones de los {rematesPaginados.length} inmuebles
              visibles en esta página.
            </p>

            <div className="mapa-real">
              <MapContainer
                key={`mapa-pagina-${paginaActual}`}
                center={centroInicialMapa}
                zoom={15}
                minZoom={10}
                maxZoom={18}
                scrollWheelZoom={true}
                doubleClickZoom={true}
                dragging={true}
                zoomControl={true}
                className="mapa-leaflet"
                style={{
                  height: "430px",
                  width: "100%",
                  borderRadius: "18px",
                }}
              >
                <AjustarVistaMapa puntos={rematesMapa} />

                <TileLayer
                  attribution="&copy; OpenStreetMap contributors"
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />

                {rematesMapa.map((item) => (
                  <CircleMarker
                    key={item.id}
                    center={[item.latMapa, item.lngMapa]}
                    radius={10}
                  >
                    <Popup>
                      <strong>{item.distrito}</strong>
                      <br />
                      {item.direccion}
                      <br />
                      {item.tipo}
                      <br />
                      Ganancia: {formatoSoles(item.ganancia)}
                      <br />
                      Puntaje: {item.score}
                      <br />
                      Estado: {item.estado}
                      {puedeVerDetalleRemaJu(item) && (
                        <>
                          <br />
                          <a href={obtenerUrlDetalleRemaJu(item)} target="_blank" rel="noopener noreferrer">
                            Ver detalle REMAJU ↗
                          </a>
                        </>
                      )}
                      <br />
                      Ubicación:{" "}
                      {item.ubicacionTipo === "exacta"
                        ? "Exacta"
                        : "Aproximada"}
                      {item.posicionRepetida && (
                        <>
                          <br />
                          Punto separado visualmente porque comparte coordenadas.
                        </>
                      )}
                    </Popup>
                  </CircleMarker>
                ))}
              </MapContainer>
            </div>
          </div>

          <div className="panel criterios-panel informe-panel" id="informes">
            <div className="informe-header">
              <div>
                <h2>Informe de decisión</h2>
                <p>Checklist financiero, legal y operativo para decidir si conviene ofertar.</p>
              </div>

              {mejorInmueble && (
                <button type="button" className="btn-secundario" onClick={imprimirInforme}>
                  Imprimir / PDF
                </button>
              )}
            </div>

            {mejorInmueble && resumenInforme ? (
              <>
                <div className="decision-grid decision-grid-compacto">
                  <div className="decision-card decision-principal">
                    <span>Decisión sugerida</span>
                    <strong>
                      {mejorInmueble.score >= 80 && mejorInmueble.margen >= 30
                        ? "Priorizar revisión"
                        : mejorInmueble.score >= 65
                        ? "Comparar antes de ofertar"
                        : "No priorizar por ahora"}
                    </strong>
                    <p>{resumenInforme.recomendacion}</p>
                  </div>

                  <div className="decision-card">
                    <span>Antes de ofertar</span>
                    <ul>
                      <li>Validar SUNARP, cargas y gravámenes.</li>
                      <li>Confirmar ocupación real del inmueble.</li>
                      <li>Revisar fecha, modalidad y requisitos.</li>
                      <li>Comparar el precio con inmuebles reales del distrito.</li>
                    </ul>
                  </div>
                </div>

                <div className="informe-acciones-finales">
                  {puedeVerDetalleRemaJu(mejorInmueble) && (
                    <a
                      className="btn-terciario"
                      href={obtenerUrlDetalleRemaJu(mejorInmueble)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Ver detalle REMAJU ↗
                    </a>
                  )}

                  <button type="button" className="btn-secundario" onClick={imprimirInforme}>
                    Abrir informe completo
                  </button>
                </div>
              </>
            ) : (
              <div className="estado-tabla">
                No hay datos suficientes para generar el informe con los filtros actuales.
              </div>
            )}
          </div>
        </section>
      </section>
    </main>
  );
}

export default Dashboard;