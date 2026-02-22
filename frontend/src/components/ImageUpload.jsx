import { useRef } from 'react';
import { ImagePlus } from 'lucide-react';

export default function ImageUpload({ onImageSelect, disabled, multiple = false }) {
  const fileRef = useRef(null);

  const processFiles = (fileList) => {
    const files = Array.from(fileList).filter(f => {
      if (!f.type.startsWith('image/')) return false;
      if (f.size > 20 * 1024 * 1024) {
        alert(`${f.name} es demasiado grande. Máximo 20MB.`);
        return false;
      }
      return true;
    });
    if (files.length === 0) return;

    const results = [];
    let processed = 0;
    files.forEach(file => {
      const reader = new FileReader();
      reader.onload = () => {
        results.push({ base64: reader.result.split(',')[1], mime: file.type });
        processed++;
        if (processed === files.length) {
          onImageSelect(results);
        }
      };
      reader.readAsDataURL(file);
    });
  };

  const handleFile = (e) => {
    if (!e.target.files?.length) return;
    processFiles(e.target.files);
    e.target.value = '';
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer?.files?.length) {
      processFiles(e.dataTransfer.files);
    }
  };

  return (
    <>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        multiple={multiple}
        onChange={handleFile}
        className="hidden"
      />
      <button
        type="button"
        onClick={() => fileRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        disabled={disabled}
        className="p-2.5 rounded-xl border border-gray-200 text-gray-500 hover:text-brand-600 
          hover:border-brand-300 hover:bg-brand-50 disabled:opacity-40 disabled:cursor-not-allowed 
          transition-colors shrink-0"
        title="Subir imagen"
      >
        <ImagePlus size={18} />
      </button>
    </>
  );
}
