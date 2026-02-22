import { useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Check, ZoomIn, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const CARD_COLORS = [
  { bg: 'bg-slate-50', border: 'border-slate-200', accent: 'text-slate-700', badge: 'bg-slate-700' },
  { bg: 'bg-zinc-50', border: 'border-zinc-200', accent: 'text-zinc-700', badge: 'bg-zinc-700' },
  { bg: 'bg-stone-50', border: 'border-stone-200', accent: 'text-stone-700', badge: 'bg-stone-700' },
];

export default function AlternativeCarousel({ alternatives, artifacts, onSelect, originalImages = [] }) {
  const scrollRef = useRef(null);
  const [expanded, setExpanded] = useState(null);
  const [zoomedImage, setZoomedImage] = useState(null);

  const scroll = (direction) => {
    if (!scrollRef.current) return;
    const cardWidth = scrollRef.current.firstChild?.offsetWidth || 320;
    scrollRef.current.scrollBy({
      left: direction === 'left' ? -cardWidth - 16 : cardWidth + 16,
      behavior: 'smooth',
    });
  };

  // Match artifacts to alternatives by order (A=0, B=1, C=2)
  const getArtifactForIndex = (idx) => {
    if (!artifacts || artifacts.length === 0) return null;
    // Artifacts arrive in order A, B, C
    return artifacts[idx] || null;
  };

  return (
    <div className="relative">
      {/* Navigation arrows - desktop only */}
      {alternatives.length > 2 && (
        <>
          <button
            onClick={() => scroll('left')}
            className="hidden md:flex absolute -left-3 top-1/2 -translate-y-1/2 z-10 bg-white shadow-lg rounded-full p-1.5 hover:bg-gray-50 transition-colors border border-gray-200"
          >
            <ChevronLeft size={16} />
          </button>
          <button
            onClick={() => scroll('right')}
            className="hidden md:flex absolute -right-3 top-1/2 -translate-y-1/2 z-10 bg-white shadow-lg rounded-full p-1.5 hover:bg-gray-50 transition-colors border border-gray-200"
          >
            <ChevronRight size={16} />
          </button>
        </>
      )}

      {/* Lightbox */}
      {zoomedImage && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4" onClick={() => setZoomedImage(null)}>
          <button className="absolute top-4 right-4 text-white bg-black/50 rounded-full p-2 hover:bg-black/70" onClick={() => setZoomedImage(null)}>
            <X size={20} />
          </button>
          <img src={zoomedImage} alt="Zoom" className="max-w-full max-h-[90vh] object-contain rounded-lg shadow-2xl" onClick={e => e.stopPropagation()} />
        </div>
      )}

      {/* Carousel container */}
      <div
        ref={scrollRef}
        className="carousel-scroll flex gap-4 overflow-x-auto pb-3 px-1"
      >
        {/* Original image card */}
        {originalImages.length > 0 && (
          <div className="flex-shrink-0 w-[280px] sm:w-[300px] md:w-[320px] rounded-xl border-2 overflow-hidden border-amber-300 bg-amber-50">
            <div className="relative aspect-[4/3] bg-gray-100 overflow-hidden cursor-pointer" onClick={() => setZoomedImage(originalImages[0])}>
              <img src={originalImages[0]} alt="Original" className="w-full h-full object-cover" />
              <span className="absolute top-2 left-2 bg-amber-600 text-white text-xs font-bold px-2.5 py-1 rounded-full shadow">ORIGINAL</span>
              <span className="absolute bottom-2 right-2 bg-black/40 text-white rounded-full p-1"><ZoomIn size={14} /></span>
            </div>
            <div className="p-3">
              <h3 className="font-bold text-sm text-amber-800 mb-1">Foto Original</h3>
              <p className="text-xs text-gray-500">Estado actual del espacio. Compara con las alternativas de dise\u00f1o.</p>
              {originalImages.length > 1 && (
                <div className="flex gap-1 mt-2">
                  {originalImages.slice(1).map((img, i) => (
                    <img key={i} src={img} alt={`Original ${i+2}`} className="h-10 w-10 rounded object-cover border cursor-pointer hover:ring-2 ring-amber-400" onClick={() => setZoomedImage(img)} />
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {alternatives.map((alt, idx) => {
          const colors = CARD_COLORS[idx] || CARD_COLORS[0];
          const artifact = getArtifactForIndex(idx);
          const isExpanded = expanded === idx;

          return (
            <div
              key={alt.letter}
              className={`flex-shrink-0 w-[280px] sm:w-[300px] md:w-[320px] rounded-xl border-2 overflow-hidden transition-all
                ${colors.bg} ${colors.border} hover:shadow-lg`}
            >
              {/* Image area */}
              <div className="relative aspect-[4/3] bg-gray-100 overflow-hidden cursor-pointer" onClick={() => artifact && setZoomedImage(artifact.url)}>
                {artifact ? (
                  <img
                    src={artifact.url}
                    alt={`Alternativa ${alt.letter}`}
                    className="w-full h-full object-cover"
                    onError={(e) => { e.target.style.display = 'none'; e.target.nextSibling && (e.target.nextSibling.style.display = 'flex'); }}
                  />
                ) : null}
                <div className={`w-full h-full items-center justify-center text-gray-300 ${artifact ? 'hidden' : 'flex'}`}>
                  <div className="text-center">
                    <div className="text-3xl mb-1">🎨</div>
                    <p className="text-xs">Generando imagen...</p>
                  </div>
                </div>
                {artifact && <span className="absolute bottom-2 right-2 bg-black/40 text-white rounded-full p-1"><ZoomIn size={14} /></span>}
                {/* Letter badge */}
                <span
                  className={`absolute top-2 left-2 ${colors.badge} text-white text-xs font-bold px-2.5 py-1 rounded-full shadow`}
                >
                  {alt.letter}
                </span>
              </div>

              {/* Content */}
              <div className="p-3">
                <h3 className={`font-bold text-sm ${colors.accent} mb-1 leading-tight`}>
                  {alt.title}
                </h3>
                {alt.concept && (
                  <p className="text-xs text-gray-500 mb-3 line-clamp-3">
                    {alt.concept}
                  </p>
                )}

                {/* Expandable detail */}
                {isExpanded && alt.body && (
                  <div className="prose prose-xs max-w-none mb-3 text-[11px] leading-relaxed border-t border-gray-200 pt-2 max-h-60 overflow-y-auto">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {alt.body}
                    </ReactMarkdown>
                  </div>
                )}

                <div className="flex gap-2">
                  <button
                    onClick={() => onSelect(alt.letter)}
                    className={`flex-1 flex items-center justify-center gap-1.5 ${colors.badge} text-white text-xs font-medium py-2 rounded-lg hover:opacity-90 transition-opacity`}
                  >
                    <Check size={14} />
                    Elegir {alt.letter}
                  </button>
                  <button
                    onClick={() => setExpanded(isExpanded ? null : idx)}
                    className="text-xs text-gray-400 hover:text-gray-600 px-2 py-2 rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors"
                  >
                    {isExpanded ? 'Menos' : 'Más'}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Dot indicators for mobile */}
      <div className="flex justify-center gap-1.5 mt-2 md:hidden">
        {alternatives.map((_, idx) => (
          <div
            key={idx}
            className={`w-1.5 h-1.5 rounded-full ${
              idx === 0 ? 'bg-gray-500' : 'bg-gray-300'
            }`}
          />
        ))}
      </div>
    </div>
  );
}
