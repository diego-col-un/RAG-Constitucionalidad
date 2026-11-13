import { useState, useRef, useEffect } from "react";
import { PREGUNTAS } from "./preguntas";
import "./App.css";

const API_URL = "http://localhost:5000/api/chat";

const CASOS_EJEMPLO = [
  "Mi EPS lleva 45 días sin autorizar una cirugía urgente de corazón ordenada por mi médico tratante y me dicen que no hay agenda.",
  "Radiqué un derecho de petición ante la Alcaldía hace 25 días hábiles pidiendo información pública sobre un contrato y no me han respondido.",
  "Un colegio privado expulsó a una estudiante embarazada alegando el manual de convivencia.",
  "Una central de riesgo mantiene un reporte negativo mío por una deuda que ya pagué hace 3 años y no atienden mi solicitud de rectificación.",
];

function barajar(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

const elegirSugeridas = () => barajar(PREGUNTAS).slice(0, 4);

function Bandera() {
  return (
    <svg className="bandera" viewBox="0 0 30 20" aria-label="Bandera de Colombia">
      <rect width="30" height="10" fill="#FCD116" />
      <rect y="10" width="30" height="5" fill="#003893" />
      <rect y="15" width="30" height="5" fill="#CE1126" />
    </svg>
  );
}

function Balanza() {
  return (
    <svg
      className="balanza"
      viewBox="0 0 64 64"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M32 8v44M18 54h28M12 16h40" />
      <path d="M12 16L4 36M12 16l8 20M4 36a8 8 0 0 0 16 0z" />
      <path d="M52 16l-8 20M52 16l8 20M44 36a8 8 0 0 0 16 0z" />
    </svg>
  );
}

// Grafo SVG interactivo de Interpretación Sistemática entre artículos
function GrafoConstitucional({ grafo, onConsultarArticulo, cargando }) {
  const [nodoActivo, setNodoActivo] = useState(null);

  if (!grafo || !grafo.relacionados || grafo.relacionados.length === 0) {
    return null;
  }

  const cx = 210;
  const cy = 125;
  const radio = 86;
  const total = grafo.relacionados.length;

  return (
    <div className="grafo-panel">
      <div className="grafo-header">
        <span>🕸️ Red de Conexidad Constitucional (Interpretación Sistemática)</span>
        <small>Haz clic en un nodo para inspeccionar o consultar</small>
      </div>

      <div className="grafo-body">
        <svg viewBox="0 0 420 250" className="grafo-svg">
          {/* Líneas de conexión y etiquetas de afinidad */}
          {grafo.relacionados.map((rel, i) => {
            const angulo = (2 * Math.PI * i) / total - Math.PI / 2;
            const nx = cx + radio * Math.cos(angulo);
            const ny = cy + radio * Math.sin(angulo);
            const mx = (cx + nx) / 2;
            const my = (cy + ny) / 2;

            return (
              <g key={`edge-${rel.articulo}`}>
                <line
                  x1={cx}
                  y1={cy}
                  x2={nx}
                  y2={ny}
                  stroke={nodoActivo?.articulo === rel.articulo ? "#d4af37" : "#cbd5e1"}
                  strokeWidth={nodoActivo?.articulo === rel.articulo ? "2.5" : "1.6"}
                  strokeDasharray="4 3"
                />
                <rect
                  x={mx - 17}
                  y={my - 9}
                  width="34"
                  height="18"
                  rx="6"
                  fill="#ffffff"
                  stroke="#e2e8f0"
                />
                <text
                  x={mx}
                  y={my + 4}
                  textAnchor="middle"
                  fontSize="9.5"
                  fontWeight="600"
                  fill="#475569"
                >
                  {rel.afinidad}%
                </text>
              </g>
            );
          })}

          {/* Nodo Central (Artículo Eje) */}
          <g
            className="grafo-node central"
            onClick={() => setNodoActivo(grafo.central)}
            style={{ cursor: "pointer" }}
          >
            <circle cx={cx} cy={cy} r="28" fill="#0b192c" stroke="#d4af37" strokeWidth="3" />
            <text x={cx} y={cy - 2} textAnchor="middle" fill="#d4af37" fontSize="9" fontWeight="700">
              EJE
            </text>
            <text x={cx} y={cy + 11} textAnchor="middle" fill="#ffffff" fontSize="11" fontWeight="700">
              Art. {grafo.central.articulo}
            </text>
          </g>

          {/* Nodos Periféricos (Artículos Conexos) */}
          {grafo.relacionados.map((rel, i) => {
            const angulo = (2 * Math.PI * i) / total - Math.PI / 2;
            const nx = cx + radio * Math.cos(angulo);
            const ny = cy + radio * Math.sin(angulo);
            const seleccionado = nodoActivo?.articulo === rel.articulo;

            return (
              <g
                key={`node-${rel.articulo}`}
                onClick={() => setNodoActivo(rel)}
                style={{ cursor: "pointer" }}
              >
                <circle
                  cx={nx}
                  cy={ny}
                  r="23"
                  fill={seleccionado ? "#003893" : "#ffffff"}
                  stroke={seleccionado ? "#d4af37" : "#003893"}
                  strokeWidth="2.2"
                />
                <text
                  x={nx}
                  y={ny + 4}
                  textAnchor="middle"
                  fill={seleccionado ? "#ffffff" : "#0b192c"}
                  fontSize="10.5"
                  fontWeight="700"
                >
                  Art. {rel.articulo}
                </text>
              </g>
            );
          })}
        </svg>

        {/* Tarjeta de detalle del nodo seleccionado */}
        <div className="grafo-info">
          {nodoActivo ? (
            <>
              <div className="grafo-info-top">
                <strong>Artículo {nodoActivo.articulo} (Pág. {nodoActivo.pagina})</strong>
                {nodoActivo.afinidad && (
                  <span className="afinidad-pill">Conexidad: {nodoActivo.afinidad}%</span>
                )}
              </div>
              <p className="grafo-extracto">"{nodoActivo.resumen}"</p>
              <button
                className="grafo-ask-btn"
                disabled={cargando}
                onClick={() =>
                  onConsultarArticulo(
                    `¿Qué establece el artículo ${nodoActivo.articulo} y cómo se relaciona con el artículo ${grafo.central.articulo}?`
                  )
                }
              >
                Explorar relación con Art. {grafo.central.articulo} ➔
              </button>
            </>
          ) : (
            <div className="grafo-placeholder">
              <p>
                <strong>Artículo Eje: Art. {grafo.central.articulo}</strong>
              </p>
              <p>
                Selecciona cualquiera de los {total} nodos conectados en el mapa para leer su extracto y analizar su vínculo constitucional.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function FormatearRespuesta({ texto }) {
  const parrafos = texto.split("\n").filter((p) => p.trim() !== "");

  const procesarLinea = (linea) => {
    const partes = linea.split(/(\*\*.*?\*\*|\[Art\..*?\]|Artículo\s+\d+)/gi);
    return partes.map((parte, idx) => {
      if (parte.startsWith("**") && parte.endsWith("**")) {
        return <strong key={idx}>{parte.slice(2, -2)}</strong>;
      }
      if (parte.startsWith("[Art.") || /^Artículo\s+\d+/i.test(parte)) {
        return (
          <span key={idx} className="cite-badge">
            {parte}
          </span>
        );
      }
      return parte;
    });
  };

  return (
    <div className="bot-formatted-text">
      {parrafos.map((p, index) => {
        const esLista = /^[-•*]\s/.test(p.trim());
        if (esLista) {
          return (
            <div key={index} className="bullet-item">
              <span className="bullet-dot">•</span>
              <span>{procesarLinea(p.trim().replace(/^[-•*]\s/, ""))}</span>
            </div>
          );
        }
        return <p key={index}>{procesarLinea(p)}</p>;
      })}
    </div>
  );
}

export default function App() {
  const [modo, setModo] = useState("consulta");
  const [mensajes, setMensajes] = useState([
    {
      rol: "bot",
      texto:
        "Hola, soy tu asistente jurídico sobre la **Constitución Política de Colombia de 1991**. Cada respuesta incluye **auditoría matemática anti-alucinación** contra el PDF oficial y un **mapa interactivo de conexidad** entre artículos.",
      fuentes: [],
      auditoria: [],
      grafo: null,
    },
  ]);
  const [input, setInput] = useState("");
  const [cargando, setCargando] = useState(false);
  const [sugeridas, setSugeridas] = useState(elegirSugeridas);
  const [copiadoIdx, setCopiadoIdx] = useState(null);
  const [panelAbierto, setPanelAbierto] = useState({}); // { [idx]: "fuentes" | "grafo" | null }
  const finRef = useRef(null);

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes, cargando]);

  async function enviar(texto) {
    const pregunta = (texto ?? input).trim();
    if (!pregunta || cargando) return;

    const historial = mensajes.slice(1).slice(-6);

    setMensajes((m) => [...m, { rol: "user", texto: pregunta, modo }]);
    setInput("");
    setCargando(true);

    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pregunta, historial, modo }),
      });
      const data = await res.json();
      if (res.ok) {
        const nuevoIdx = mensajes.length + 1;
        setMensajes((m) => [
          ...m,
          {
            rol: "bot",
            texto: data.respuesta,
            fuentes: data.fuentes || [],
            auditoria: data.auditoria || [],
            rigor_global: data.rigor_global ?? 100,
            grafo: data.grafo || null,
            modo: data.modo || modo,
          },
        ]);
        // Abrir el grafo automáticamente en consultas para impacto visual inmediato
        if (data.grafo) {
          setPanelAbierto((prev) => ({ ...prev, [nuevoIdx]: "grafo" }));
        }
      } else {
        setMensajes((m) => [
          ...m,
          { rol: "bot", texto: `Error: ${data.error}`, esError: true },
        ]);
      }
    } catch {
      setMensajes((m) => [
        ...m,
        {
          rol: "bot",
          texto: "No se pudo conectar con el servidor.",
          esError: true,
        },
      ]);
    } finally {
      setCargando(false);
    }
  }

  const limpiarChat = () => {
    setPanelAbierto({});
    setMensajes([
      {
        rol: "bot",
        texto:
          modo === "caso"
            ? "Modo **Evaluador de Caso + Borrador** activo. Describe los hechos del ciudadano y analizaré los derechos vulnerados, el mecanismo idóneo y redactaré el escrito constitucional."
            : "Conversación reiniciada. Elige una pregunta sugerida o escribe tu consulta constitucional.",
        fuentes: [],
        auditoria: [],
        grafo: null,
      },
    ]);
  };

  const cambiarModo = (nuevoModo) => {
    setModo(nuevoModo);
    setMensajes((prev) => [
      ...prev,
      {
        rol: "bot",
        texto:
          nuevoModo === "caso"
            ? "⚖️ **Modo Evaluador de Casos activado:** Cuéntame un caso real de vulneración de derechos. Diagnosticaré los artículos aplicables, verificaré las citas matemáticamente y generaré un borrador descargable en Word."
            : "📖 **Modo Consulta Constitucional activado:** Pregunta sobre cualquier artículo, derecho o institución de la Carta de 1991.",
        fuentes: [],
        auditoria: [],
        grafo: null,
      },
    ]);
  };

  const copiarTexto = (texto, idx) => {
    navigator.clipboard.writeText(texto);
    setCopiadoIdx(idx);
    setTimeout(() => setCopiadoIdx(null), 2000);
  };

  const descargarWord = (texto, idx) => {
    const contenidoHtml = `
      <html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
      <head><meta charset='utf-8'><title>Borrador Constitucional</title></head>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; margin: 40px;">
        <h2 style="color: #0b192c; border-bottom: 2px solid #003893; padding-bottom: 8px;">
          Análisis y Borrador Constitucional — Constitución Política de Colombia (1991)
        </h2>
        <div style="white-space: pre-wrap;">${texto.replace(/\*\*/g, "")}</div>
      </body>
      </html>`;
    const blob = new Blob(["\ufeff", contenidoHtml], {
      type: "application/msword",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `Borrador_Constitucional_${idx}.doc`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const togglePanel = (idx, tipo) => {
    setPanelAbierto((prev) => ({
      ...prev,
      [idx]: prev[idx] === tipo ? null : tipo,
    }));
  };

  return (
    <div className="app-layout">
      {/* Barra Lateral Institucional */}
      <aside className="sidebar">
        <div className="franja-tricolor">
          <span className="amarillo" />
          <span className="azul" />
          <span className="rojo" />
        </div>

        <div className="brand-header">
          <div className="brand-top">
            <Bandera />
            <Balanza />
          </div>
          <h1>Constitución Política de Colombia</h1>
          <p className="subtitle">Consultorio Jurídico IA · 1991</p>
        </div>

        <div className="mode-switcher">
          <button
            className={`mode-btn ${modo === "consulta" ? "active" : ""}`}
            onClick={() => cambiarModo("consulta")}
            disabled={cargando}
          >
            📖 Consulta
          </button>
          <button
            className={`mode-btn ${modo === "caso" ? "active" : ""}`}
            onClick={() => cambiarModo("caso")}
            disabled={cargando}
          >
            ⚖️ Evaluar Caso
          </button>
        </div>

        <button className="new-chat-btn" onClick={limpiarChat} disabled={cargando}>
          <span>+</span> Nueva sesión
        </button>

        <div className="sidebar-section">
          <div className="sugerencias-header">
            <span>
              {modo === "caso" ? "Casos prácticos de prueba" : "Preguntas sugeridas"}
            </span>
            {modo === "consulta" && (
              <button
                className="barajar-btn"
                onClick={() => setSugeridas(elegirSugeridas())}
                disabled={cargando}
              >
                ↻ Otras
              </button>
            )}
          </div>

          <div className="chips-list">
            {(modo === "caso" ? CASOS_EJEMPLO : sugeridas).map((p) => (
              <button
                key={p}
                className="chip-btn"
                onClick={() => enviar(p)}
                disabled={cargando}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        <div className="sidebar-footer">
          <div className="status-row">
            <span className="status-dot" />
            <span>Verificador Anti-Alucinación Activo</span>
          </div>
          <p className="creator-credit">Proyecto Convenio SUMA · Santy</p>
        </div>
      </aside>

      {/* Área Principal del Chat */}
      <main className="chat-main">
        <header className="mobile-header">
          <div className="mobile-brand">
            <Bandera />
            <span>Constitución 1991</span>
          </div>
          <button onClick={limpiarChat} className="mobile-clear-btn">
            Limpiar
          </button>
        </header>

        <div className="mensajes-scroll">
          <div className="mensajes-container">
            {mensajes.map((m, i) => (
              <div key={i} className={`mensaje-row ${m.rol}`}>
                <div className="avatar">
                  {m.rol === "user" ? "Tú" : <Balanza />}
                </div>
                <div className={`burbuja ${m.esError ? "error" : ""}`}>
                  <div className="burbuja-meta">
                    <span className="autor">
                      {m.rol === "user"
                        ? m.modo === "caso"
                          ? "Relato del Caso"
                          : "Consulta Ciudadana"
                        : m.modo === "caso"
                        ? "Dictamen y Borrador Constitucional"
                        : "Asistente Constitucional"}
                    </span>
                    {m.rol === "bot" && !m.esError && (
                      <div className="meta-actions">
                        {m.modo === "caso" && (
                          <button
                            className="word-btn"
                            onClick={() => descargarWord(m.texto, i)}
                          >
                            ⬇ Word (.doc)
                          </button>
                        )}
                        <button
                          className="copy-btn"
                          onClick={() => copiarTexto(m.texto, i)}
                        >
                          {copiadoIdx === i ? "✓ Copiado" : "Copiar"}
                        </button>
                      </div>
                    )}
                  </div>

                  {m.rol === "user" ? (
                    <p className="texto-usuario">{m.texto}</p>
                  ) : (
                    <>
                      <FormatearRespuesta texto={m.texto} />

                      {/* Semáforo Matemático de Rigor Normativo */}
                      {m.auditoria && m.auditoria.length > 0 && (
                        <div className="semaforo-bar">
                          <span className="semaforo-title">
                            🛡️ Rigor Normativo ({m.rigor_global}%):
                          </span>
                          <div className="semaforo-pills">
                            {m.auditoria.map((c) => (
                              <span
                                key={c.articulo}
                                className={`rigor-pill ${c.estado}`}
                                title={`${c.etiqueta} — Fidelidad semántica: ${c.score}%`}
                              >
                                {c.estado === "verificado"
                                  ? "🟢"
                                  : c.estado === "extensivo"
                                  ? "🟡"
                                  : "🔴"}{" "}
                                Art. {c.articulo} ({c.score}%)
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Botones de Herramientas Jurídicas (Grafo + Texto Literal) */}
                      {(m.grafo || (m.fuentes && m.fuentes.length > 0)) && (
                        <div className="tools-tabs">
                          {m.grafo && (
                            <button
                              className={`tool-tab-btn ${
                                panelAbierto[i] === "grafo" ? "active" : ""
                              }`}
                              onClick={() => togglePanel(i, "grafo")}
                            >
                              🕸️ Mapa de Conexidad (Art. {m.grafo.central.articulo})
                            </button>
                          )}
                          {m.fuentes && m.fuentes.length > 0 && (
                            <button
                              className={`tool-tab-btn ${
                                panelAbierto[i] === "fuentes" ? "active" : ""
                              }`}
                              onClick={() => togglePanel(i, "fuentes")}
                            >
                              🔍 Texto Literal PDF ({m.fuentes.length})
                            </button>
                          )}
                        </div>
                      )}

                      {/* Panel 1: Grafo Interactivo */}
                      {panelAbierto[i] === "grafo" && m.grafo && (
                        <GrafoConstitucional
                          grafo={m.grafo}
                          onConsultarArticulo={(q) => enviar(q)}
                          cargando={cargando}
                        />
                      )}

                      {/* Panel 2: Texto Literal Oficial */}
                      {panelAbierto[i] === "fuentes" && m.fuentes && (
                        <div className="audit-list">
                          {m.fuentes.map((f, fIdx) => (
                            <div key={fIdx} className="audit-card">
                              <div className="audit-card-header">
                                <strong>
                                  {f.articulo
                                    ? `Artículo ${f.articulo}`
                                    : "Texto Constitucional"}
                                </strong>
                                <span>Página {f.pagina} del PDF</span>
                              </div>
                              <p className="audit-extract">"{f.extracto}"</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}

            {cargando && (
              <div className="mensaje-row bot">
                <div className="avatar">
                  <Balanza />
                </div>
                <div className="burbuja typing">
                  <div className="dots">
                    <span />
                    <span />
                    <span />
                  </div>
                  <span>
                    {modo === "caso"
                      ? "Analizando caso, auditando citas y trazando red constitucional..."
                      : "Calculando similitud normativa y verificando citas en el PDF..."}
                  </span>
                </div>
              </div>
            )}
            <div ref={finRef} />
          </div>
        </div>

        {/* Barra de entrada */}
        <div className="entrada-wrapper">
          <div className="entrada-box">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && enviar()}
              placeholder={
                modo === "caso"
                  ? "Describe los hechos del caso (quién vulnera el derecho, qué pasó y cuándo)..."
                  : "Escribe tu pregunta sobre la Constitución o un artículo..."
              }
              disabled={cargando}
            />
            <button
              className="enviar-btn"
              onClick={() => enviar()}
              disabled={cargando || !input.trim()}
            >
              {modo === "caso" ? "Evaluar Caso ➔" : "Enviar ➔"}
            </button>
          </div>
          <p className="footer-note">
            Verificación matemática determinística contra los 380 artículos de la Constitución Política de Colombia (1991).
          </p>
        </div>
      </main>
    </div>
  );
}