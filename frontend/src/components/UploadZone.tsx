import { useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { UploadCloud, X, FileImage } from 'lucide-react';

export default function UploadZone({ onFile, onAnalyze, busy }: {
  onFile: (f: File) => void; onAnalyze: () => void; busy: boolean;
}) {
  const [drag, setDrag] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const ref = useRef<HTMLInputElement>(null);

  const pick = (f: File | undefined) => {
    if (!f) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(f.type)) { alert('Only JPG, PNG, WEBP allowed.'); return; }
    if (f.size > 10 * 1024 * 1024) { alert('Max 10 MB.'); return; }
    setFile(f); setPreview(URL.createObjectURL(f)); onFile(f);
  };
  return (
    <div className={`glass scanline p-6 text-center transition ${drag ? 'border-cyan-300 shadow-glow' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files?.[0]); }}>
      {!preview ? (
        <>
          <motion.div animate={{ y: [0, -6, 0] }} transition={{ repeat: Infinity, duration: 2.5 }}>
            <UploadCloud className="mx-auto mb-3 text-violet-300" size={44} />
          </motion.div>
          <p className="font-semibold">Drop an image here</p>
          <p className="text-sm text-slate-400">or</p>
          <button onClick={() => ref.current?.click()} className="btn-primary mt-3">Browse Files</button>
          <p className="mt-3 text-xs text-slate-500">Supports JPG, PNG, WEBP (Max 10MB)</p>
        </>
      ) : (
        <div>
          <img src={preview} alt="preview" className="mx-auto max-h-64 rounded-xl border border-white/10" />
          <p className="mt-2 flex items-center justify-center gap-2 text-sm text-slate-300">
            <FileImage size={16} /> {file?.name} · {((file?.size || 0) / 1024).toFixed(0)} KB
          </p>
          <div className="mt-3 flex justify-center gap-2">
            <button onClick={() => { setFile(null); setPreview(null); }} className="rounded-xl border border-white/10 px-4 py-2 text-sm flex items-center gap-1"><X size={14} /> Remove</button>
            <button onClick={onAnalyze} disabled={busy} className="btn-primary text-sm disabled:opacity-50">{busy ? 'Analyzing…' : 'Analyze'}</button>
          </div>
        </div>
      )}
      <input ref={ref} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
    </div>
  );
}
