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

export default function App() {
  const [mensajes, setMensajes] = useState([
    {
      rol: "bot",
      texto:
        "Hola, soy tu asistente sobre la Constitución Política de Colombia de 1991. Elige una pregunta sobre derechos fundamentales o escribe la tuya.",
    },
  ]);
  const [input, setInput] = useState("");
  const [cargando, setCargando] = useState(false);
  const [sugeridas, setSugeridas] = useState(elegirSugeridas);
  const finRef = useRef(null);

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes]);

  async function enviar(texto) {
    const pregunta = (texto ?? input).trim();
    if (!pregunta || cargando) return;

    setMensajes((m) => [...m, { rol: "user", texto: pregunta }]);
    setInput("");
    setCargando(true);

    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pregunta }),
      });
      const data = await res.json();
      const respuesta = res.ok ? data.respuesta : `Error: ${data.error}`;
      setMensajes((m) => [...m, { rol: "bot", texto: respuesta }]);
    } catch {
      setMensajes((m) => [
        ...m,
        { rol: "bot", texto: "No se pudo conectar con el servidor." },
      ]);
    } finally {
      setCargando(false);
    }
  }

  return (
    <div className="app">
      <header className="cabecera">
        <div className="franja" />
        <div className="cabecera-contenido">
          <Bandera />
          <div className="titulos">
            <h1>Constitución Política de Colombia</h1>
            <p>Asistente sobre derechos fundamentales · 1991</p>
          </div>
          <Balanza />
        </div>
      </header>

      <main className="chat">
        <div className="mensajes">
          {mensajes.map((m, i) => (
            <div key={i} className={`mensaje ${m.rol}`}>
              {m.texto}
            </div>
          ))}
          {cargando && <div className="mensaje bot">Consultando la Constitución...</div>}
          <div ref={finRef} />
        </div>

        <div className="sugerencias">
          <div className="sugerencias-barra">
            <span>Preguntas sobre derechos fundamentales</span>
            <button
              className="barajar"
              onClick={() => setSugeridas(elegirSugeridas())}
              disabled={cargando}
            >
              ↻ Otras preguntas
            </button>
          </div>
          <div className="chips">
            {sugeridas.map((p) => (
              <button
                key={p}
                className="chip"
                onClick={() => enviar(p)}
                disabled={cargando}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        <div className="entrada">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && enviar()}
            placeholder="Escribe tu pregunta..."
          />
          <button onClick={() => enviar()} disabled={cargando}>
            Enviar
          </button>
        </div>
      </main>
    </div>
  );
}