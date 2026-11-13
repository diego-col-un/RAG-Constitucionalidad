import { useState, useRef, useEffect } from "react";
import { PREGUNTAS } from "./preguntas";
import "./App.css";

const API_URL = "http://localhost:5000/api/chat";

function barajar(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

const elegirSugeridas = () => barajar(PREGUNTAS).slice(0, 5);

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

// Formatea las respuestas del bot resaltando negritas y citas de artículos/páginas
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
  const [mensajes, setMensajes] = useState([
    {
      rol: "bot",
      texto:
        "Hola, soy tu asistente sobre la **Constitución Política de Colombia de 1991**. Elige una pregunta sugerida sobre derechos fundamentales o escribe la tuya.",
    },
  ]);
  const [input, setInput] = useState("");
  const [cargando, setCargando] = useState(false);
  const [sugeridas, setSugeridas] = useState(elegirSugeridas);
  const [copiadoIdx, setCopiadoIdx] = useState(null);
  const finRef = useRef(null);

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes, cargando]);

  async function enviar(texto) {
    const pregunta = (texto ?? input).trim();
    if (!pregunta || cargando) return;

    // Últimos mensajes previos (sin el saludo inicial) como memoria de la conversación
    const historial = mensajes.slice(1).slice(-6);

    setMensajes((m) => [...m, { rol: "user", texto: pregunta }]);
    setInput("");
    setCargando(true);

    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pregunta, historial }),
      });
      const data = await res.json();
      if (res.ok) {
        setMensajes((m) => [...m, { rol: "bot", texto: data.respuesta }]);
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
    setMensajes([
      {
        rol: "bot",
        texto:
          "Conversación reiniciada. Elige una pregunta sobre derechos fundamentales o escribe la tuya.",
      },
    ]);
  };

  const copiarTexto = (texto, idx) => {
    navigator.clipboard.writeText(texto);
    setCopiadoIdx(idx);
    setTimeout(() => setCopiadoIdx(null), 2000);
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
          <p className="subtitle">Asistente sobre derechos fundamentales · 1991</p>
        </div>

        <button className="new-chat-btn" onClick={limpiarChat} disabled={cargando}>
          <span>+</span> Nueva consulta
        </button>

        <div className="sidebar-section">
          <div className="sugerencias-header">
            <span>Preguntas sugeridas</span>
            <button
              className="barajar-btn"
              onClick={() => setSugeridas(elegirSugeridas())}
              disabled={cargando}
              title="Cargar otras preguntas"
            >
              ↻ Otras
            </button>
          </div>

          <div className="chips-list">
            {sugeridas.map((p) => (
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
            <span>RAG Híbrido Activo</span>
          </div>
          <p className="creator-credit">Creado por Santiago Cardona y Diego Aristizabal </p>
        </div>
      </aside>

      {/* Área Principal del Chat */}
      <main className="chat-main">
        {/* Cabecera visible solo en móviles */}
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
                        ? "Ciudadano"
                        : "Asistente Constitucional"}
                    </span>
                    {m.rol === "bot" && !m.esError && (
                      <button
                        className="copy-btn"
                        onClick={() => copiarTexto(m.texto, i)}
                      >
                        {copiadoIdx === i ? "✓ Copiado" : "Copiar"}
                      </button>
                    )}
                  </div>

                  {m.rol === "user" ? (
                    <p className="texto-usuario">{m.texto}</p>
                  ) : (
                    <FormatearRespuesta texto={m.texto} />
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
                  <span>Consultando la Constitución...</span>
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
              placeholder="Escribe tu pregunta sobre la Constitución o un artículo..."
              disabled={cargando}
            />
            <button
              className="enviar-btn"
              onClick={() => enviar()}
              disabled={cargando || !input.trim()}
            >
              Enviar ➔
            </button>
          </div>
          <p className="footer-note">
            Respuestas fundamentadas en el texto de la Constitución Política de Colombia de 1991.
          </p>
        </div>
      </main>
    </div>
  );
}