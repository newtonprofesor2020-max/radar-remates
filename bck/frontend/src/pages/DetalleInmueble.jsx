import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";

const API_URL = "http://127.0.0.1:8000";

const COORDENADAS_DISTRITOS = {
  LIMA: [-12.0464, -77.0428],
  "CERCADO DE LIMA": [-12.0464, -77.0428],
  SURQUILLO: [-12.1186, -77.0217],
  MIRAFLORES: [-12.1211, -77.0305],
  "SAN ISIDRO": [-12.0972, -77.0365],
  "SANTIAGO DE SURCO": [-12.145, -76.9918],
  "SAN BORJA": [-12.108, -76.9995],
  "LA MOLINA": [-12.0875, -76.9286],
  BARRANCO: [-12.1494, -77.0217],
  CHORRILLOS: [-12.1649, -77.025],
  LINCE: [-12.0844, -77.0358],
  "JESUS MARIA": [-12.0763, -77.0444],
  "PUEBLO LIBRE": [-12.0769, -77.0674],
  "MAGDALENA DEL MAR": [-12.0917, -77.0672],
  "SAN MIGUEL": [-12.0778, -77.0922],
  "LOS OLIVOS": [-11.9631, -77.0736],
  "SAN MARTIN DE PORRES": [-12.0303, -77.0572],
  COMAS: [-11.9333, -77.05],
  CARABAYLLO: [-11.8539, -77.0378],
  INDEPENDENCIA: [-11.9961, -77.0522],
  RIMAC: [-12.0291, -77.0439],
  "EL AGUSTINO": [-12.0483, -76.9933],
  ATE: [-12.0464, -76.9],
  "SANTA ANITA": [-12.0433, -76.9714],
  "SAN LUIS": [-12.0733, -76.995],
  "LA VICTORIA": [-12.0653, -77.0308],
  BREÑA: [-12.0586, -77.0508],
  BRENA: [-12.0586, -77.0508],
  "SAN JUAN DE LURIGANCHO": [-12.0039, -77.0061],
  "SAN JUAN DE MIRAFLORES": [-12.1636, -76.9633],
  "VILLA MARIA DEL TRIUNFO": [-12.1581, -76.9436],
  "VILLA EL SALVADOR": [-12.2133, -76.9364],
  LURIN: [-12.2744, -76.8706],
  PACHACAMAC: [-12.2294, -76.8583],
  CALLAO: [-12.0566, -77.1181],
  BELLAVISTA: [-12.0625, -77.1292],
  "LA PERLA": [-12.0703, -77.165],
  "LA PUNTA": [-12.0725, -77.1636],
  "CARMEN DE LA LEGUA": [-12.0392, -77.0958],
  VENTANILLA: [-11.8753, -77.1189],
};

function numero(valor) {
  if (valor === null || valor === undefined || valor === "") {
    return 0;
  }

  if (typeof valor === "number") {
    return Number.isFinite(valor) ? valor : 0;
  }

  let texto = String(valor)
    .trim()
    .replace(/[^0-9.,-]/g, "");

  if (!texto) return 0;

  const ultimoPunto = texto.lastIndexOf(".");
  const ultimaComa = texto.lastIndexOf(",");

  if (ultimoPunto !== -1 && ultimaComa !== -1) {
    if (ultimaComa > ultimoPunto) {
      texto = texto.replace(/\./g, "").replace(",", ".");
    } else {
      texto = texto.replace(/,/g, "");
    }
  } else if (ultimoPunto !== -1) {
    const partes = texto.split(".");
    const ultimaParte = partes[partes.length - 1];

    if (partes.length > 1 && ultimaParte.length === 3) {
      texto = texto.replace(/\./g, "");
    }
  } else if (ultimaComa !== -1) {
    const partes = texto.split(",");
    const ultimaParte = partes[partes.length - 1];

    if (partes.length > 1 && ultimaParte.length === 3) {
      texto = texto.replace(/,/g, "");
    } else {
      texto = texto.replace(",", ".");
    }
  }

  const n = Number(texto);
  return Number.isFinite(n) ? n : 0;
}

function formatoNumero(valor, decimales = 0) {
  const n = numero(valor);
  const fijo = n.toFixed(decimales);
  const [entero, decimal] = fijo.split(".");
  const enteroConComas = entero.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return decimal !== undefined ? `${enteroConComas}.${decimal}` : enteroConComas;
}

function soles(valor, decimales = 0) {
  return `S/ ${formatoNumero(valor, decimales)}`;
}

function porcentaje(valor, decimales = 1) {
  return `${formatoNumero(valor, decimales)} %`;
}

function obtenerUrlAviso(item) {
  const posibles = [
    item?.url_detalle,
    item?.url_original,
    item?.url,
    item?.url_aviso,
    item?.aviso_url,
    item?.fuente_url,
    item?.link,
    item?.enlace,
  ];

  const url = posibles.find((valor) => typeof valor === "string" && valor.trim() !== "");
  return url ? url.trim() : "";
}

function texto(valor, fallback = "No registrado") {
  return valor && String(valor).trim() !== "" ? valor : fallback;
}

function limpiar(valor) {
  return String(valor || "").toLowerCase().trim();
}

function normalizarClave(valor) {
  return String(valor || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .trim();
}

function coordenadasPorDistrito(distrito) {
  const clave = normalizarClave(distrito);
  const coordenadas = COORDENADAS_DISTRITOS[clave];

  if (coordenadas) {
    return {
      lat: coordenadas[0],
      lng: coordenadas[1],
    };
  }

  return {
    lat: -12.0464,
    lng: -77.0428,
  };
}

function calcularMargen(precioBase, valorMercado) {
  if (valorMercado <= 0 || precioBase <= 0) return 0;
  return Math.round(((valorMercado - precioBase) / valorMercado) * 100);
}

function calcularScore(margen, convocatoria) {
  let score = Math.round(margen * 2.1);
  const conv = limpiar(convocatoria);

  if (conv.includes("segunda")) score += 8;
  if (conv.includes("tercera")) score += 12;

  if (score < 0) score = 0;
  if (score > 95) score = 95;

  return score;
}

function colorRiesgo(riesgo) {
  const r = limpiar(riesgo);

  if (r.includes("bajo")) return "riesgo-bajo";
  if (r.includes("medio")) return "riesgo-medio";
  return "riesgo-alto";
}

function normalizarInmueble(item) {
  const precioBase = numero(item.precio_base || item.precio_remate || item.precio);

  let valorMercado = numero(
    item.valor_mercado || item.valor_comercial || item.tasacion
  );

  if (valorMercado <= 0 && precioBase > 0) {
    valorMercado = Math.round(precioBase * 1.5);
  }

  const ganancia =
    item.ganancia_estimada !== null && item.ganancia_estimada !== undefined
      ? numero(item.ganancia_estimada)
      : valorMercado - precioBase;

  const margen =
    item.porcentaje_descuento !== null &&
    item.porcentaje_descuento !== undefined
      ? numero(item.porcentaje_descuento)
      : calcularMargen(precioBase, valorMercado);

  const scoreBD = numero(
    item.score || item.puntaje || item.score_oportunidad || item.score_total
  );

  const score =
    scoreBD > 0 ? scoreBD : calcularScore(margen, item.convocatoria || "");

  const riesgo =
    item.riesgo || (score >= 80 ? "Bajo" : score >= 60 ? "Medio" : "Alto");

  const distrito = texto(item.distrito, "Sin distrito");

  const coordenadasDistrito = coordenadasPorDistrito(distrito);
  const latBD = numero(item.lat);
  const lngBD = numero(item.lng);
  const tieneCoordenadasBD = latBD !== 0 && lngBD !== 0;

  const ubicacionTipo = item.ubicacion_tipo || "aproximada";

  return {
    id: item.id,
    expediente: texto(item.expediente, "Sin expediente"),
    numeroRemate: texto(item.numero_remate || item.remate, "No registrado"),
    distrito,
    direccion: texto(item.direccion || item.descripcion, "Dirección no registrada"),
    direccionCompleta: texto(
      item.direccion_completa || item.direccion || item.descripcion,
      "Ubicación no registrada"
    ),
    tipo: texto(item.tipo, "Inmueble"),
    area: item.area ? `${item.area} m²` : "No indicada",
    convocatoria: texto(item.convocatoria || item.nivel_oportunidad, "No registrada"),
    juzgado: texto(item.juzgado, "No registrado"),
    fuente: texto(item.fuente || item.origen, "No registrada"),
    fechaPresentacion: texto(item.fecha_presentacion || item.fecha_remate, "No registrada"),
    horaPresentacion: texto(item.hora_presentacion || item.hora_remate, "No registrada"),
    precioBase,
    valorMercado,
    ganancia,
    margen,
    score,
    riesgo,
    lat: tieneCoordenadasBD ? latBD : coordenadasDistrito.lat,
    lng: tieneCoordenadasBD ? lngBD : coordenadasDistrito.lng,
    ubicacionTipo,
    urlDetalle: obtenerUrlAviso(item),
    estadoRevision: texto(item.estado_revision, "Pendiente"),
    observaciones: item.observaciones || "",
    aptoParaOfertar: Boolean(item.apto_para_ofertar),
    raw: item,
  };
}

function DetalleInmueble() {
  const { id } = useParams();

  const [inmueble, setInmueble] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");

  const [estadoRevision, setEstadoRevision] = useState("Pendiente");
  const [observaciones, setObservaciones] = useState("");
  const [aptoParaOfertar, setAptoParaOfertar] = useState(false);
  const [guardandoRevision, setGuardandoRevision] = useState(false);
  const [mensajeRevision, setMensajeRevision] = useState("");


  const [ofertaSimulada, setOfertaSimulada] = useState("");
  const [gastosLegales, setGastosLegales] = useState(0);
  const [alcabala, setAlcabala] = useState(0);
  const [sunarp, setSunarp] = useState(0);
  const [notaria, setNotaria] = useState(0);
  const [reparaciones, setReparaciones] = useState(0);
  useEffect(() => {
    async function cargarDetalle() {
      try {
        setCargando(true);
        setError("");

        const response = await fetch(`${API_URL}/inmueble/${id}`);

        if (!response.ok) {
          const rankingResponse = await fetch(`${API_URL}/ranking`);

          if (!rankingResponse.ok) {
            throw new Error("No se pudo cargar el inmueble.");
          }

          const ranking = await rankingResponse.json();

          const encontrado = Array.isArray(ranking)
            ? ranking.find((item) => String(item.id) === String(id))
            : null;

          if (!encontrado) {
            throw new Error("No se encontró el inmueble solicitado.");
          }

          setInmueble(normalizarInmueble(encontrado));
          return;
        }

        const data = await response.json();
        setInmueble(normalizarInmueble(data));
      } catch (err) {
        console.error("Error cargando detalle:", err);
        setError(err.message || "No se pudo cargar el detalle.");
      } finally {
        setCargando(false);
      }
    }

    cargarDetalle();
  }, [id]);

 useEffect(() => {
  async function cargarRevision() {
    try {
      const response = await fetch(`${API_URL}/inmueble/${id}/revision`);

      if (!response.ok) {
        return;
      }

      const revision = await response.json();

      setEstadoRevision(revision.estado || "Pendiente");
      setObservaciones(revision.observaciones || "");
      setAptoParaOfertar(Boolean(revision.apto_para_ofertar));
    } catch (error) {
      console.error("Error cargando revisión:", error);
    }
  }

  cargarRevision();
}, [id]);

  const categoria = useMemo(() => {
    if (!inmueble) return "Sin análisis";
    if (inmueble.score >= 85) return "Excelente oportunidad";
    if (inmueble.score >= 70) return "Buena oportunidad";
    if (inmueble.score >= 45) return "Oportunidad con revisión";
    return "Oportunidad con riesgo";
  }, [inmueble]);

  const ubicacionEsExacta = limpiar(inmueble?.ubicacionTipo) === "exacta";

  const rentabilidad = useMemo(() => {
  if (!inmueble) {
    return {
      precioOferta: 0,
      gastosTotales: 0,
      inversionTotal: 0,
      gananciaNeta: 0,
      roi: 0,
      decision: "Sin datos"
    };
  }

  const precioOferta =
    numero(ofertaSimulada) > 0 ? numero(ofertaSimulada) : inmueble.precioBase;

  const gastosTotales =
    numero(gastosLegales) +
    numero(alcabala) +
    numero(sunarp) +
    numero(notaria) +
    numero(reparaciones);

  const inversionTotal = precioOferta + gastosTotales;
  const gananciaNeta = inmueble.valorMercado - inversionTotal;

  const roi =
    inversionTotal > 0
      ? (gananciaNeta / inversionTotal) * 100
      : 0;

    let decision = "Revisar con cuidado";

    if (roi >= 30 && gananciaNeta > 0) {
      decision = "Muy interesante para analizar";
    } else if (roi >= 15 && gananciaNeta > 0) {
      decision = "Potencial moderado";
    } else if (gananciaNeta <= 0) {
      decision = "No recomendable con estos gastos";
    }

    return {
      precioOferta,
      gastosTotales,
      inversionTotal,
      gananciaNeta,
      roi,
      decision
    };
  }, [
    inmueble,
    ofertaSimulada,
    gastosLegales,
    alcabala,
    sunarp,
    notaria,
    reparaciones
  ]);

  const guardarRevision = async () => {
  try {
    setGuardandoRevision(true);
    setMensajeRevision("");

    const response = await fetch(`${API_URL}/inmueble/${id}/revision`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        estado: estadoRevision,
        observaciones,
        apto_para_ofertar: aptoParaOfertar,
      }),
    });

    if (!response.ok) {
      throw new Error("No se pudo guardar la revisión.");
    }

    const resultado = await response.json();

    if (resultado.revision) {
      setEstadoRevision(resultado.revision.estado || "Pendiente");
      setObservaciones(resultado.revision.observaciones || "");
      setAptoParaOfertar(Boolean(resultado.revision.apto_para_ofertar));
    }

    setMensajeRevision("Revisión guardada correctamente.");
  } catch (err) {
    console.error("Error guardando revisión:", err);
    setMensajeRevision("Error al guardar la revisión.");
  } finally {
    setGuardandoRevision(false);
  }
};

  if (cargando) {
    return (
      <main className="detalle-page">
        <div className="detalle-loading">Cargando detalle del inmueble...</div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="detalle-page">
        <div className="detalle-error">
          <h2>No se pudo cargar el detalle</h2>
          <p>{error}</p>
          <Link to="/" className="detalle-btn">
            Volver al panel
          </Link>
        </div>
      </main>
    );
  }

  if (!inmueble) return null;

  return (
    <main className="detalle-page">
      <section className="detalle-hero">
        <div>
          <Link to="/" className="detalle-back">
            ← Volver al panel
          </Link>

          <div className="detalle-tags">
            <span>{inmueble.tipo}</span>
            <span className={colorRiesgo(inmueble.riesgo)}>
              Riesgo {inmueble.riesgo}
            </span>
            <span>Puntaje {inmueble.score}/100</span>
            <span className={ubicacionEsExacta ? "ubicacion-exacta" : "ubicacion-aproximada"}>
              {ubicacionEsExacta ? "Ubicación exacta" : "Ubicación aproximada"}
            </span>
          </div>

          <p className="detalle-label">Distrito</p>
          <h1>{inmueble.distrito}</h1>

          <p className="detalle-direccion">{inmueble.direccion}</p>

          <p className="detalle-expediente">
            Expediente <strong>{inmueble.expediente}</strong> ·{" "}
            <strong>{inmueble.convocatoria}</strong>
          </p>
        </div>

        <div className="detalle-score-card">
          <span>Puntaje de oportunidad</span>
          <strong>{inmueble.score}/100</strong>
          <p>{categoria}</p>
        </div>
      </section>

      <section className="detalle-metricas">
        <div>
          <span>Precio base</span>
          <strong>{soles(inmueble.precioBase)}</strong>
        </div>

        <div>
          <span>Valor de mercado</span>
          <strong>{soles(inmueble.valorMercado)}</strong>
        </div>

        <div>
          <span>Ganancia estimada</span>
          <strong className={inmueble.ganancia >= 0 ? "positivo" : "negativo"}>
            {soles(inmueble.ganancia)}
          </strong>
        </div>

        <div>
          <span>Margen estimado</span>
          <strong>{inmueble.margen}%</strong>
        </div>
      </section>



      <section className="detalle-panel calculadora-rentabilidad">
  <div className="calculadora-header">
    <div>
      <h2>Calculadora de rentabilidad</h2>
      <p>
        Simula la inversión total antes de ofertar. Los valores son referenciales
        y deben validarse con documentos reales.
      </p>
    </div>

    <div className="calculadora-decision">
      <span>Resultado rápido</span>
      <strong>{rentabilidad.decision}</strong>
    </div>
  </div>

  <div className="calculadora-grid">
    <label>
      Precio de remate u oferta simulada
      <input
        type="number"
        min="0"
        value={ofertaSimulada}
        onChange={(e) => setOfertaSimulada(e.target.value)}
        placeholder={String(inmueble.precioBase)}
      />
      <small>Vacío = usa el precio base del remate.</small>
    </label>

    <label>
      Gastos legales
      <input
        type="number"
        min="0"
        value={gastosLegales}
        onChange={(e) => setGastosLegales(e.target.value)}
      />
    </label>

    <label>
      Alcabala
      <input
        type="number"
        min="0"
        value={alcabala}
        onChange={(e) => setAlcabala(e.target.value)}
      />
    </label>

    <label>
      SUNARP
      <input
        type="number"
        min="0"
        value={sunarp}
        onChange={(e) => setSunarp(e.target.value)}
      />
    </label>

    <label>
      Notaría
      <input
        type="number"
        min="0"
        value={notaria}
        onChange={(e) => setNotaria(e.target.value)}
      />
    </label>

    <label>
      Reparaciones
      <input
        type="number"
        min="0"
        value={reparaciones}
        onChange={(e) => setReparaciones(e.target.value)}
      />
    </label>
  </div>

  <div className="calculadora-resultados">
      <div>
        <span>Precio usado</span>
        <strong>{soles(rentabilidad.precioOferta)}</strong>
      </div>

      <div>
        <span>Gastos totales</span>
        <strong>{soles(rentabilidad.gastosTotales)}</strong>
      </div>

      <div>
        <span>Inversión total</span>
        <strong>{soles(rentabilidad.inversionTotal)}</strong>
      </div>

      <div>
        <span>Valor de mercado</span>
        <strong>{soles(inmueble.valorMercado)}</strong>
      </div>

      <div>
        <span>Ganancia neta</span>
        <strong className={rentabilidad.gananciaNeta >= 0 ? "positivo" : "negativo"}>
          {soles(rentabilidad.gananciaNeta)}
        </strong>
      </div>

      <div>
        <span>ROI estimado</span>
        <strong className={rentabilidad.roi >= 30 ? "positivo" : "negativo"}>
          {porcentaje(rentabilidad.roi, 1)}
        </strong>
      </div>
    </div>
  </section>










      <section className="detalle-grid">
        <div className="detalle-panel">
          <h2>Información del remate</h2>
          <p>Resumen principal del proceso y del inmueble.</p>

          <div className="detalle-info-grid">
            <div>
              <span>Expediente</span>
              <strong>{inmueble.expediente}</strong>
            </div>

            <div>
              <span>Número de remate</span>
              <strong>{inmueble.numeroRemate}</strong>
            </div>

            <div>
              <span>Convocatoria</span>
              <strong>{inmueble.convocatoria}</strong>
            </div>

            <div>
              <span>Fecha de presentación</span>
              <strong>{inmueble.fechaPresentacion}</strong>
            </div>

            <div>
              <span>Hora de presentación</span>
              <strong>{inmueble.horaPresentacion}</strong>
            </div>

            <div>
              <span>Juzgado</span>
              <strong>{inmueble.juzgado}</strong>
            </div>

            <div>
              <span>Distrito</span>
              <strong>{inmueble.distrito}</strong>
            </div>

            <div>
              <span>Dirección</span>
              <strong>{inmueble.direccion}</strong>
            </div>

            <div>
              <span>Tipo</span>
              <strong>{inmueble.tipo}</strong>
            </div>

            <div>
              <span>Área</span>
              <strong>{inmueble.area}</strong>
            </div>

            <div>
              <span>Fuente</span>
              <strong>{inmueble.fuente}</strong>
            </div>

            <div>
              <span>Tipo de ubicación</span>
              <strong>
                {ubicacionEsExacta
                  ? "Exacta según dirección registrada"
                  : "Aproximada por distrito"}
              </strong>
            </div>
          </div>
        </div>

        <aside className="detalle-panel detalle-recomendacion">
          <h2>Recomendación rápida</h2>

          <div className="detalle-recomendacion-box">
            <strong>{categoria}</strong>
            <p>
              Revisa partida registral, cargas, ocupación del inmueble y valor
              comercial actualizado antes de ofertar.
            </p>
          </div>

          {inmueble.urlDetalle ? (
            <a
              href={inmueble.urlDetalle}
              target="_blank"
              rel="noopener noreferrer"
              className="detalle-btn full aviso-remaju"
            >
              Ver aviso REMAJU ↗
            </a>
          ) : (
            <button className="detalle-btn full disabled" disabled>
              Aviso original no registrado
            </button>
          )}

          <div className="revision-box">
            <h3>Revisión del inmueble</h3>

            <label>
              Estado de revisión
              <select
                value={estadoRevision}
                onChange={(e) => setEstadoRevision(e.target.value)}
              >
                <option value="Pendiente">Pendiente</option>
                <option value="Revisado">Revisado</option>
                <option value="Con observaciones">Con observaciones</option>
                <option value="Descartado">Descartado</option>
                <option value="Apto para ofertar">Apto para ofertar</option>
              </select>
            </label>

            <label>
              Observaciones
              <textarea
                value={observaciones}
                onChange={(e) => setObservaciones(e.target.value)}
                placeholder="Ejemplo: Revisar SUNARP, verificar ocupación, validar cargas..."
                rows="5"
              />
            </label>

            <label className="check-revision">
              <input
                type="checkbox"
                checked={aptoParaOfertar}
                onChange={(e) => setAptoParaOfertar(e.target.checked)}
              />
              Apto para ofertar
            </label>

            <button
              className="detalle-btn full"
              onClick={guardarRevision}
              disabled={guardandoRevision}
            >
              {guardandoRevision ? "Guardando..." : "Guardar revisión"}
            </button>

            {mensajeRevision && (
              <p className="mensaje-revision">{mensajeRevision}</p>
            )}
          </div>
        </aside>
      </section>

      <section className="detalle-panel detalle-panel-mapa">
        <div className="detalle-mapa-header">
          <div>
            <h2>Ubicación del inmueble</h2>
            <p>
              {ubicacionEsExacta
                ? "Ubicación exacta obtenida desde la dirección registrada del remate."
                : "Ubicación aproximada basada en el distrito registrado del inmueble."}
            </p>
          </div>

          <span
            className={`ubicacion-badge ${
              ubicacionEsExacta ? "exacta" : "aproximada"
            }`}
          >
            {ubicacionEsExacta ? "Exacta" : "Aproximada"}
          </span>
        </div>

        <div className="detalle-mapa-layout">
          <div className="detalle-mapa">
            <MapContainer
              key={`${inmueble.id}-${inmueble.lat}-${inmueble.lng}`}
              center={[inmueble.lat, inmueble.lng]}
              zoom={ubicacionEsExacta ? 18 : 15}
              scrollWheelZoom={true}
              doubleClickZoom={true}
              dragging={true}
              zoomControl={true}
              minZoom={10}
              maxZoom={19}
              wheelPxPerZoomLevel={80}
              style={{
                height: "390px",
                width: "100%",
                borderRadius: "18px",
              }}
            >
              <TileLayer
                attribution="&copy; OpenStreetMap contributors"
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />

              <CircleMarker center={[inmueble.lat, inmueble.lng]} radius={11}>
                <Popup>
                  <strong>{inmueble.distrito}</strong>
                  <br />
                  {inmueble.direccionCompleta}
                  <br />
                  {ubicacionEsExacta
                    ? "Ubicación exacta"
                    : "Ubicación aproximada"}
                </Popup>
              </CircleMarker>
            </MapContainer>
          </div>

          <div className="detalle-ubicacion-info">
            <div>
              <span>Dirección usada</span>
              <strong>{inmueble.direccionCompleta}</strong>
            </div>

            <div>
              <span>Distrito</span>
              <strong>{inmueble.distrito}</strong>
            </div>

            <div>
              <span>Latitud</span>
              <strong>{inmueble.lat}</strong>
            </div>

            <div>
              <span>Longitud</span>
              <strong>{inmueble.lng}</strong>
            </div>

            <div>
              <span>Precisión</span>
              <strong>
                {ubicacionEsExacta
                  ? "Punto exacto geocodificado"
                  : "Referencia aproximada del distrito"}
              </strong>
            </div>
          </div>
        </div>
      </section>

      <section className="detalle-panel">
        <h2>Descripción</h2>
        <p>Detalle general del inmueble rematado.</p>

        <div className="detalle-descripcion">{inmueble.direccion}</div>
      </section>

      <section className="detalle-panel">
        <h2>Criterios antes de ofertar</h2>

        <ul className="detalle-lista">
          <li>Verificar la partida registral en SUNARP.</li>
          <li>Revisar si existen cargas, gravámenes o litigios.</li>
          <li>Confirmar si el inmueble está ocupado.</li>
          <li>Comparar el precio base con valores reales de mercado.</li>
          <li>Validar fechas, requisitos y modalidad del remate.</li>
        </ul>
      </section>
    </main>
  );
}

export default DetalleInmueble;