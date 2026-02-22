import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, ImagePlus, Loader2, Sparkles, ShoppingCart, Download } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { createSession, sendMessageSSE } from '../lib/adk-client';
import { hasAlternatives, parseAlternatives } from '../lib/parse-response';
import AlternativeCarousel from './AlternativeCarousel';
import ImageUpload from './ImageUpload';
import { exportShoppingListPDF } from '../lib/pdf-export';

export default function ChatPanel({ project, section }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionReady, setSessionReady] = useState(false);
  const [artifacts, setArtifacts] = useState([]);
  const [pendingImages, setPendingImages] = useState([]);
  const [originalImages, setOriginalImages] = useState([]);
  const messagesEndRef = useRef(null);
  const controllerRef = useRef(null);

  const userId = project.id;
  const sessionId = section.sessionId || `${project.id}__${section.id}`;

  // Initialize session
  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        await createSession(userId, sessionId, {
          project_style: project.style,
          section_type: section.type,
          section_name: section.name,
        });
        if (!cancelled) setSessionReady(true);
      } catch (err) {
        console.error('Session init error:', err);
        if (!cancelled) setSessionReady(true); // proceed anyway, session may exist
      }
    }
    init();
    return () => {
      cancelled = true;
      controllerRef.current?.abort();
    };
  }, [userId, sessionId, project.style, section.type, section.name]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const storageKey = sessionId ? `facelift_chat_${userId}_${sessionId}` : null;

  const serializeMessages = useCallback((items) =>
    items.map(({ image, ...rest }) => rest),
  []);

  // Persist messages + artifacts to localStorage per section (without base64 images)
  useEffect(() => {
    if (!storageKey || messages.length === 0) return;
    try {
      const payload = {
        messages: serializeMessages(messages),
        artifacts,
      };
      localStorage.setItem(storageKey, JSON.stringify(payload));
    } catch (err) {
      console.warn('Failed to persist chat history', err);
      localStorage.removeItem(storageKey);
    }
  }, [messages, artifacts, storageKey, serializeMessages]);

  // Load persisted messages + artifacts on mount
  useEffect(() => {
    if (!storageKey) return;
    const stored = localStorage.getItem(storageKey);
    if (!stored) return;
    try {
      const { messages: m, artifacts: a } = JSON.parse(stored);
      if (Array.isArray(m) && m.length > 0) setMessages(m);
      if (Array.isArray(a)) setArtifacts(a);
    } catch (e) {
      console.warn('Failed to load persisted chat', e);
      localStorage.removeItem(storageKey);
    }
  }, [storageKey]);

  const addArtifact = useCallback(
    (name) => {
      // Generated images are saved as /static/{filename} by the backend
      const url = `/static/${name}`;
      setArtifacts((prev) => {
        if (prev.some((a) => a.name === name)) return prev;
        return [...prev, { name, url }];
      });
    },
    []
  );

  const sendMsg = useCallback(
    async (text, images = [], defaultMime = 'image/jpeg') => {
      if (!text && images.length === 0) return;
      if (loading) return;

      // Store ALL originals for carousel display (all uploaded this turn)
      if (images.length > 0) {
        const dataUrls = images.map(img => `data:${img.mime || defaultMime};base64,${img.base64}`);
        // Replace originalImages with current batch (not append across turns)
        setOriginalImages(dataUrls);
      }

      // Add user message
      const userMsg = {
        id: Date.now(),
        role: 'user',
        text: text || (images.length > 0 ? `📸 ${images.length} imagen(es) subida(s)` : ''),
        image: images.length > 0
          ? `data:${images[0].mime || defaultMime};base64,${images[0].base64}`
          : null,
        imageCount: images.length,
      };
      setMessages((prev) => [...prev, userMsg]);
      setInput('');
      setPendingImages([]);
      setLoading(true);

      // Build image parts for the request
      const firstImage = images.length > 0 ? images[0] : null;
      const imageBase64 = firstImage?.base64 || null;
      const imageMime = firstImage?.mime || defaultMime;

      // Prepend context for first message in session
      let fullText = text || '';
      if (messages.length === 0 && images.length > 0) {
        fullText = `Estilo del proyecto: ${project.style}. Tipo de espacio: ${section.type}. Sección: ${section.name}. ${fullText}`.trim();
      }

      // Add assistant placeholder
      const assistantId = Date.now() + 1;
      setMessages((prev) => [
        ...prev,
        { id: assistantId, role: 'assistant', text: '', loading: true },
      ]);

      const newArtifactNames = [];

      controllerRef.current = sendMessageSSE(
        userId,
        sessionId,
        fullText,
        imageBase64,
        imageMime,
        {
          onToken: (_chunk, fullText) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, text: fullText, loading: true }
                  : m
              )
            );
          },
          onArtifact: (name) => {
            newArtifactNames.push(name);
            // Immediately add as /static/ URL
            addArtifact(name);
          },
          onDone: async (finalText) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, text: finalText, loading: false }
                  : m
              )
            );
            setLoading(false);

            // Artifacts already added via addArtifact in onArtifact callback
          },
          onError: (err) => {
            console.error('SSE error:', err);
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      text: `Error: ${err.message}. Verifica que el backend ADK esté corriendo en el puerto 8000.`,
                      loading: false,
                      error: true,
                    }
                  : m
              )
            );
            setLoading(false);
          },
        }
      );
    },
    [loading, messages.length, userId, sessionId, project.style, section.type, section.name, addArtifact]
  );

  const handleSubmit = (e) => {
    e.preventDefault();
    if (pendingImages.length > 0) {
      const text = input.trim() || 'Analiza esta imagen y propón 3 alternativas de diseño.';
      sendMsg(text, pendingImages);
    } else {
      sendMsg(input, []);
    }
  };

  const handleImageSelect = (files) => {
    // files = [{base64, mime}, ...]
    setPendingImages(prev => [...prev, ...files]);
  };

  const removePendingImage = (idx) => {
    setPendingImages(prev => prev.filter((_, i) => i !== idx));
  };

  const handleSelectAlternative = (letter) => {
    sendMsg(`Me gusta la alternativa ${letter}. Genera el plan refinado con esa opción.`, []);
  };

  const handleVerifyConsistency = (letter) => {
    sendMsg(`Verifica la consistencia de la alternativa ${letter}`, []);
  };

  const handleRequestShoppingList = () => {
    sendMsg('Genera la lista de compra completa con todos los materiales y herramientas del plan.', []);
  };

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between shrink-0">
        <div>
          <h2 className="font-semibold text-gray-800 flex items-center gap-2">
            <span>{getSectionIcon(section.type)}</span>
            {section.name}
          </h2>
          <p className="text-xs text-gray-400">
            {project.name} · Estilo: {project.style}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleRequestShoppingList}
            disabled={loading || messages.length === 0}
            className="flex items-center gap-1.5 text-xs bg-emerald-50 text-emerald-700 px-3 py-1.5 rounded-full hover:bg-emerald-100 disabled:opacity-40 transition-colors"
          >
            <ShoppingCart size={14} />
            Lista de compra
          </button>
          <button
            onClick={() => {
              const lastAssistant = [...messages].reverse().find(m => m.role === 'assistant' && m.text);
              if (lastAssistant) exportShoppingListPDF(lastAssistant.text, project.name, section.name);
            }}
            disabled={loading || messages.length === 0}
            className="flex items-center gap-1.5 text-xs bg-blue-50 text-blue-700 px-3 py-1.5 rounded-full hover:bg-blue-100 disabled:opacity-40 transition-colors"
          >
            <Download size={14} />
            PDF
          </button>
        </div>
      </header>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-center text-gray-400">
            <ImagePlus size={48} strokeWidth={1.5} className="mb-3 text-gray-300" />
            <p className="text-sm font-medium mb-1">Sube una foto para empezar</p>
            <p className="text-xs">
              El copiloto analizará la imagen y generará 3 alternativas de diseño
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            artifacts={artifacts}
            originalImages={originalImages}
            onSelectAlternative={handleSelectAlternative}
            onVerifyAlternative={handleVerifyConsistency}
          />
        ))}

        <div ref={messagesEndRef} />
      </div>

      {/* Pending images preview */}
      {pendingImages.length > 0 && (
        <div className="px-4 pb-2">
          <div className="flex flex-wrap gap-2">
            {pendingImages.map((img, idx) => (
              <div key={idx} className="inline-flex items-center gap-1.5 bg-blue-50 rounded-lg px-2 py-1 text-xs text-blue-700">
                <img
                  src={`data:${img.mime};base64,${img.base64}`}
                  alt={`preview ${idx + 1}`}
                  className="h-8 w-8 rounded object-cover"
                />
                <span>Foto {idx + 1}</span>
                <button
                  onClick={() => removePendingImage(idx)}
                  className="text-blue-400 hover:text-blue-600 ml-0.5"
                >
                  ✕
                </button>
              </div>
            ))}
            <span className="text-xs text-gray-400 self-center">Escribe tu mensaje y envía</span>
          </div>
        </div>
      )}

      {/* Input area */}
      <div className="bg-white border-t border-gray-200 px-4 py-3 shrink-0">
        <form onSubmit={handleSubmit} className="flex items-end gap-2">
          <ImageUpload onImageSelect={handleImageSelect} disabled={loading} multiple />
          <div className="flex-1 relative">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              placeholder={
                messages.length === 0
                  ? 'Sube una imagen o escribe un mensaje...'
                  : 'Elige alternativa, pide cambios, o solicita la lista de compra...'
              }
              disabled={loading}
              rows={1}
              className="w-full resize-none rounded-xl border border-gray-200 px-4 py-2.5 pr-10 text-sm
                focus:border-brand-400 focus:ring-2 focus:ring-brand-100 outline-none
                disabled:bg-gray-50 disabled:text-gray-400 transition-colors"
            />
          </div>
          <button
            type="submit"
            disabled={loading || (!input.trim() && pendingImages.length === 0)}
            className="bg-brand-600 text-white p-2.5 rounded-xl hover:bg-brand-700
              disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors shrink-0"
          >
            {loading ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <Send size={18} />
            )}
          </button>
        </form>
      </div>
    </div>
  );
}

const MessageBubble = React.memo(function MessageBubble({
  message,
  artifacts,
  originalImages,
  onSelectAlternative,
  onVerifyAlternative,
}) {
  const isUser = message.role === 'user';
  const showAlternatives = !isUser && hasAlternatives(message.text);
  const alternatives = showAlternatives ? parseAlternatives(message.text) : [];

  return (
    <div
      className={`animate-fade-in-up flex ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      <div
        className={`max-w-[85%] lg:max-w-[75%] rounded-2xl px-4 py-3 ${
          isUser
            ? 'bg-brand-600 text-white'
            : message.error
              ? 'bg-red-50 text-red-800 border border-red-200'
              : 'bg-white shadow-sm border border-gray-100'
        }`}
      >
        {/* User image */}
        {isUser && message.image && (
          <img
            src={message.image}
            alt="uploaded"
            className="rounded-lg mb-2 max-h-48 object-cover"
          />
        )}

        {/* Loading indicator */}
        {message.loading && !message.text && (
          <div className="flex gap-1 py-1">
            <div className="loading-dot w-2 h-2 rounded-full bg-gray-400" />
            <div className="loading-dot w-2 h-2 rounded-full bg-gray-400" />
            <div className="loading-dot w-2 h-2 rounded-full bg-gray-400" />
          </div>
        )}

        {/* Text content */}
        {message.text && !showAlternatives && (
          <div className={`prose prose-sm max-w-none ${isUser ? 'prose-invert' : ''}`}>
            {isUser ? (
              <p className="text-sm m-0">{message.text}</p>
            ) : (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.text}
              </ReactMarkdown>
            )}
          </div>
        )}

        {/* Alternatives carousel */}
        {showAlternatives && alternatives.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles size={16} className="text-amber-500" />
              <span className="font-semibold text-sm">3 Alternativas de Diseño</span>
            </div>
            <AlternativeCarousel
              alternatives={alternatives}
              artifacts={artifacts}
              originalImages={originalImages}
              onSelect={onSelectAlternative}
              onVerify={onVerifyAlternative}
            />
            {/* Show full text below the carousel */}
            <details className="mt-3">
              <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">
                Ver detalle completo (texto técnico)
              </summary>
              <div className="prose prose-sm max-w-none mt-2 text-xs">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.text}
                </ReactMarkdown>
              </div>
            </details>
          </div>
        )}

        {/* Alternatives fallback: show full text if no carousel */}
        {showAlternatives && alternatives.length === 0 && (
          <div className="prose prose-sm max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.text}
            </ReactMarkdown>
          </div>
        )}

        {/* Loading indicator at end of partial text */}
        {message.loading && message.text && (
          <div className="flex gap-1 mt-2">
            <div className="loading-dot w-1.5 h-1.5 rounded-full bg-gray-300" />
            <div className="loading-dot w-1.5 h-1.5 rounded-full bg-gray-300" />
            <div className="loading-dot w-1.5 h-1.5 rounded-full bg-gray-300" />
          </div>
        )}
      </div>
    </div>
  );
});

function getSectionIcon(type) {
  const icons = {
    exterior: '🏠',
    interior: '🛋️',
    baño: '🚿',
    cocina: '🍳',
    dormitorio: '🛏️',
    jardín: '🌿',
    garaje: '🚗',
    otro: '📐',
  };
  return icons[type] || '📐';
}
