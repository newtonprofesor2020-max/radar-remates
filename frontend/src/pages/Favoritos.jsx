import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

const API_URL = "http://127.0.0.1:8000";

function normalizarNumero(valor) {
  const numero = Number(valor);
  return Number.isFinite(numero) ? numero : 0;
}

function formatoSoles(valor) {
  return new Intl.NumberFormat("es-PE", {
    style: "currency",
    currency: "PEN",
    maximumFractionDigits: 0,
  }).format(normalizarNumero(valor));
}

function limpiarTexto(texto) {
  return String(texto || "").trim().toLowerCase();
}

function Favoritos() {
  const [favoritos, setFavoritos] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");

  const cargarFavoritos = async () => {
    try {
      setCargando(true);
      setError("");

      const response = await fetch(`${API_URL}/favoritos`);

      if (!response.ok) {
        throw new Error(`Error HTTP: ${response.status}`);
      }

      const data = await response.json();
      setFavoritos(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Error cargando favoritos:", err);
      setError("No se pudieron cargar los favoritos.");
      setFavoritos([]);
    } finally {
      setCargando(false);
    }
  };

  const eliminarFavorito = async (inmuebleId) => {
    try {
      const response = await fetch(`${API_URL}/favoritos/${inmuebleId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("No se pudo eliminar el favorito.");
      }

      setFavoritos((lista) =>
        lista.filter((item) => String(item.id) !== String(inmuebleId))
      );
    } catch (err) {
      console.error("Error eliminando favorito:", err);
      setError("No se pudo eliminar el favorito.");
    }
  };

  useEffect(() => {
    cargarFavoritos();
  }, []);

  return (
    <main className="dashboard favoritos-page">
      <aside className="sidebar">
        <div className="logo">
          <span>RR</span>
          <div>
            <h2>Radar Remates</h2>
            <p>Oportunidades inmobiliarias</p>
          </div>
        </div>

        <nav>
          <Link to="/">Panel</Link>
          <Link to="/favoritos" className="activo">Favoritos</Link>
        </nav>
      </aside>

      <section className="contenido">
        <header className="topbar">
          <div>
            <h1>Favoritos</h1>
            <p>Inmuebles guardados para revisar, comparar y hacer seguimiento.</p>
          </div>

          <button onClick={cargarFavoritos} disabled={cargando}>
            {cargando ? "Cargando..." : "Actualizar favoritos"}
          </button>
        </header>

        {error && <div className="alerta-error">{error}</div>}

        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Oportunidades guardadas</h2>
              <p>
                Revisa tus inmuebles favoritos antes de tomar una decisión de inversión.
              </p>
            </div>
          </div>

          <div className="tabla-contenedor">
            <table>
              <thead>
                <tr>
                  <th>Distrito</th>
                  <th>Tipo</th>
                  <th>Precio remate</th>
                  <th>Valor mercado</th>
                  <th>Ganancia</th>
                  <th>Margen</th>
                  <th>Riesgo</th>
                  <th>Estado</th>
                  <th>Puntaje</th>
                  <th>Acción</th>
                </tr>
              </thead>

              <tbody>
                {cargando ? (
                  <tr>
                    <td colSpan="10" className="estado-tabla">
                      Cargando favoritos...
                    </td>
                  </tr>
                ) : favoritos.length === 0 ? (
                  <tr>
                    <td colSpan="10" className="estado-tabla">
                      Todavía no tienes inmuebles favoritos.
                    </td>
                  </tr>
                ) : (
                  favoritos.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>{item.distrito || "Sin distrito"}</strong>
                        <small>{item.direccion || "Dirección no registrada"}</small>
                      </td>

                      <td>{item.tipo || "Inmueble"}</td>
                      <td>{formatoSoles(item.precio_base)}</td>
                      <td>{formatoSoles(item.valor_mercado)}</td>

                      <td className={normalizarNumero(item.ganancia_estimada) >= 0 ? "ganancia" : "perdida"}>
                        {formatoSoles(item.ganancia_estimada)}
                      </td>

                      <td>{normalizarNumero(item.porcentaje_descuento)}%</td>

                      <td>
                        <span className={`badge ${limpiarTexto(item.riesgo)}`}>
                          {item.riesgo || "Alto"}
                        </span>
                      </td>

                      <td>
                        <span className={`badge estado-${limpiarTexto(item.estado)}`}>
                          {item.estado || "Activo"}
                        </span>
                      </td>

                      <td>
                        <span
                          className={`score ${
                            normalizarNumero(item.score) >= 85
                              ? "score-alto"
                              : normalizarNumero(item.score) >= 70
                              ? "score-medio"
                              : "score-bajo"
                          }`}
                        >
                          {normalizarNumero(item.score)}
                        </span>
                      </td>

                      <td>
                        <div className="acciones-favorito">
                          <Link className="ver-detalle" to={`/inmueble/${item.id}`}>
                            Ver detalle
                          </Link>

                          <button
                            type="button"
                            className="btn-favorito quitar"
                            onClick={() => eliminarFavorito(item.id)}
                          >
                            Quitar
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </main>
  );
}

export default Favoritos;
