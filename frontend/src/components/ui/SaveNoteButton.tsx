import { useState } from "react";
import { Check, BookmarkPlus, Loader2 } from "lucide-react";
import { addNote } from "@/lib/notes";
import { ApiError } from "@/lib/api";

// 把一段 AI 结果存入「研究记录」（沉淀）。存本机磁盘、不上传。
export function SaveNoteButton({ kind, title, content }: { kind: string; title: string; content: string }) {
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!content.trim()) return null;

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      await addNote(kind, title, content);
      setSaved(true);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "存入失败，请先启动 backend");
    } finally {
      setSaving(false);
    }
  };

  return (
    <button
      onClick={save}
      disabled={saved || saving}
      title={err ?? undefined}
      className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary disabled:opacity-60"
    >
      {saved ? (
        <><Check className="h-3.5 w-3.5" /> 已存入沉淀</>
      ) : saving ? (
        <><Loader2 className="h-3.5 w-3.5 animate-spin" /> 存入中…</>
      ) : err ? (
        <><BookmarkPlus className="h-3.5 w-3.5" /> 存入失败，重试</>
      ) : (
        <><BookmarkPlus className="h-3.5 w-3.5" /> 存入沉淀</>
      )}
    </button>
  );
}
