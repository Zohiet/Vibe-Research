import { useEffect, useRef, useState } from "react";
import { AiStamp } from "@/components/ui/AiStamp";
import { useAiSession } from "@/hooks/useAiSession";
import { Swords, Play, Square, Save, CheckCircle2, Circle, AlertTriangle, Trash2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { debateStream, type DebateStage } from "@/lib/agents";
import { addNote } from "@/lib/notes";
import { ApiError } from "@/lib/api";

/**
 * 一个角色发言的收场方式。`undefined` = 正常说完。
 *
 * 三种「没说完」刻意分开，因为它们对读的人意味着完全不同的事：
 * - `failed`      后端判定这一轮生成失败（有原因，来自 `stage_done.failed`）
 * - `aborted`     **你自己点了停止** —— 绝不能显示成"生成失败"，那是制造假故障；
 *                 这套提示的价值全靠可信，出现过一次假失败，往后就没人看了
 * - `interrupted` 流在后端视野外断掉，或来自老存档（分不出前两者）
 */
type StageOutcome = "failed" | "aborted" | "interrupted";

interface StageBox {
  stage: DebateStage;
  label: string;
  content: string;
  done: boolean;
  outcome?: StageOutcome;
}

const OUTCOME_TEXT: Record<StageOutcome, string> = {
  failed: "生成失败",
  aborted: "已中止 · 你停止了这场辩论",
  interrupted: "已中断 · 未跑完",
};

/** 存档的形状。`start()` 里的本地快照与它同构 —— 存进去的就是这一份。 */
interface Saved {
  code: string; rounds: number; stages: StageBox[];
  progress: { title: string; ok: boolean }[];
  missing: string[]; status: string; error: string;
}

// 多方用品牌橙、空方用蓝灰、主持用中性——刻意不用红绿，
// 免得和 A 股「红涨绿跌」撞车被读成涨跌信号。
const STAGE_TONE: Record<DebateStage, string> = {
  bull: "border-primary/50 bg-primary/[0.06]",
  bull_rebut: "border-primary/30 bg-primary/[0.03]",
  bear: "border-sky-500/40 bg-sky-500/[0.06]",
  bear_rebut: "border-sky-500/25 bg-sky-500/[0.03]",
  referee: "border-border bg-background/40",
};

const DOSSIER_HINT = "多空双方拿到的是同一份接口实时拉取的数据，谁也不能靠编数字赢。";

export function Debate() {
  // 辩论存后端进程内存（VR-GOAL-010）。
  //
  // **与 Plan 的偏差**：Plan 写的 key 是 `debate:<code>`，但那样永远恢复不出来——
  // 进页面时 code 是空的，拿不到 key 就没得恢复，你得先把代码原样敲一遍才看得见上次的结果。
  // 改成单个 key `debate`，把 code 一起存进去：进页面就看到上次那场，代码框也自动填好。
  const session = useAiSession<Saved>(
    "debate", (v) => typeof v === "object" && v !== null && Array.isArray((v as { stages?: unknown }).stages));
  const [code, setCode] = useState("");
  const [rounds, setRounds] = useState(1);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState("");
  const [progress, setProgress] = useState<{ title: string; ok: boolean }[]>([]);
  const [missing, setMissing] = useState<string[]>([]);
  const [stages, setStages] = useState<StageBox[]>([]);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const reset = () => {
    setStatus(""); setProgress([]); setMissing([]); setStages([]); setError(""); setSaved(false);
  };

  // 清空这场辩论（决策 #10：改成"切页也留着"之后，要把重置能力明确补回来）
  const clearSession = () => { reset(); session.clear(); };

  useEffect(() => {
    if (!session.loaded || !session.data) return;
    const d = session.data;
    setCode(d.code); setRounds(d.rounds);
    // ⚠️ 存档里可能留着 done=false 的阶段（老存档，或流在后端视野外断掉）。
    // **恢复时一律收成终态** —— 界面上绝不能再出现一个永远脉冲的「生成中…」，
    // 那正是本 Goal 的病根：它把"已经死了"和"正在生成"渲染成同一个样子，
    // 用户连该不该继续等都判断不了（实测卡了半小时，其实早就结束了）。
    setStages((d.stages || []).map((s) =>
      s.done ? s : { ...s, done: true, outcome: s.outcome ?? "interrupted" }));
    setProgress(d.progress); setMissing(d.missing); setStatus(d.status);
    setError(d.error ?? "");
  }, [session.loaded, session.data]);

  async function start() {
    const c = code.trim();
    if (!/^\d{6}$/.test(c)) { setError("请输入 6 位 A 股代码"); return; }
    reset();
    setRunning(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    // 本地快照与 React 状态同步更新：finally 里要存档，而那时 React 状态变量还是旧闭包值。
    //
    // ⚠️ **所有写入必须走 patch()，作用域里不留第二个能用的 setter。**
    // 上一版是四份独立的本地变量配 `setSta` / `setStg` 双写函数，而裸的
    // `setStatus` / `setError` 也还在作用域里、类型一模一样（都是 `(v: string) => void`），
    // tsc 分不出来。结果 catch 分支调了裸 `setStatus("已中止")` —— 界面对了、快照没动，
    // 存进去的 status 还是中止前那句「底稿就绪，辩论开始」。
    // 那段代码上方**逐字写着这个警告**，人照样踩了 —— 所以这次用结构挡，不靠注释。
    let snap: Saved = {
      code: c, rounds, stages: [], progress: [], missing: [], status: "", error: "",
    };
    const patch = (p: Partial<Saved>) => {
      snap = { ...snap, ...p };
      if (p.stages) setStages(p.stages);
      if (p.progress) setProgress(p.progress);
      if (p.missing) setMissing(p.missing);
      if (p.status !== undefined) setStatus(p.status);
      if (p.error !== undefined) setError(p.error);
    };

    // 流是怎么收场的 —— 决定还没说完的角色标成什么。
    let ending: StageOutcome = "interrupted";

    try {
      await debateStream(c, rounds, {
        onStatus: (message) => patch({ status: message }),
        onDossierProgress: (title, ok, loaded, total) => patch({
          status: `正在拉取客观事实底稿… ${loaded}/${total}`,
          progress: [...snap.progress, { title, ok }],
        }),
        onDossierReady: (_sections, miss) => patch({ missing: miss, status: "底稿就绪，辩论开始" }),
        onStageStart: (stage, label) => patch({
          stages: [...snap.stages, { stage, label, content: "", done: false }],
        }),
        onDelta: (stage, text) => patch({
          stages: snap.stages.map((b) =>
            b.stage === stage && !b.done ? { ...b, content: b.content + text } : b),
        }),
        onStageDone: (stage, _label, content, failed) => patch({
          stages: snap.stages.map((b) =>
            b.stage === stage && !b.done
              ? { ...b, content, done: true, outcome: failed ? "failed" : undefined }
              : b),
        }),
        onError: (message, stage) => patch({ error: stage ? `${stage}：${message}` : message }),
      }, ctrl.signal);
      patch({ status: "辩论完成" });
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        ending = "aborted";
        patch({ status: "已中止" });
      } else {
        ending = "failed";
        patch({ error: e instanceof ApiError ? e.message : String(e) });
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
      // 把还没到终态的角色收口。不收的话它会以 done=false 存进去，
      // 恢复出来就是一个永远脉冲的「生成中…」—— 本 Goal 的病根。
      if (snap.stages.some((s) => !s.done)) {
        patch({ stages: snap.stages.map((s) => (s.done ? s : { ...s, done: true, outcome: ending })) });
      }
      // 结束时存一次（跑完 / 出错 / 中止三条路都走这里）。整份快照一起存——
      // 只恢复 stages 而 progress 空着，看起来像跑了一半。
      if (snap.stages.length > 0) session.save(snap);
    }
  }

  function stop() {
    abortRef.current?.abort();
    setRunning(false);
  }

  // 沉淀已落后端磁盘，addNote 变异步；失败要让用户看见（以前是同写 localStorage、不会失败）。
  async function save() {
    // 没说完的角色要在正文里写明——照 VR-GOAL-015「缺席要让读的人知道」：
    // 少一方而不说，读的人会以为这就是完整的一场辩论。
    const body = stages
      .map((s) => `## ${s.label}${s.outcome ? `（${OUTCOME_TEXT[s.outcome]}）` : ""}\n\n${s.content || "（无内容）"}`)
      .join("\n\n---\n\n");
    try {
      await addNote("多空辩论", `多空辩论 · ${code.trim()}`, body);
      setSaved(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "存入沉淀失败，请先启动 backend");
    }
  }

  // 「到终态」而不是「全都成功」。以前判的是后者，于是空方一断，
  // 多方那两千多字连「存入沉淀」都点不了——一个角色失败不该把整场的产物扣住。
  const finished = stages.length > 0 && stages.every((s) => s.done);

  return (
    <div>
      <PageHeader
        title="多空辩论"
        subtitle="同一份客观数据，多方与空方各自立论、互相质疑，最后由中立主持归纳分歧点与验证清单——不给买卖结论，判断留给你自己。"
      />

      <GlassCard>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">股票代码</label>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/[^\d]/g, "").slice(0, 6))}
              onKeyDown={(e) => { if (e.key === "Enter" && !running) start(); }}
              placeholder="6 位代码，如 600519"
              disabled={running}
              className="w-44 rounded-lg border border-border/60 bg-background/60 px-3 py-2 font-mono text-sm outline-none focus:border-primary/60"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">辩论深度</label>
            <select
              value={rounds}
              onChange={(e) => setRounds(Number(e.target.value))}
              disabled={running}
              className="rounded-lg border border-border/60 bg-background/60 px-3 py-2 text-sm outline-none focus:border-primary/60"
            >
              <option value={1}>一轮 · 各自陈述</option>
              <option value={2}>两轮 · 加交叉反驳</option>
            </select>
          </div>
          {running ? (
            <button onClick={stop}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border/60 px-4 py-2 text-sm hover:text-destructive">
              <Square className="h-4 w-4" /> 中止
            </button>
          ) : (
            <button onClick={start}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary/90 px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary">
              <Play className="h-4 w-4" /> 开始辩论
            </button>
          )}
          {/* 清空这场（决策 #10）：辩论现在会留到后端重启，得有个明确的重置入口 */}
          {stages.length > 0 && !running && (
            <button onClick={clearSession}
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:text-destructive">
              <Trash2 className="h-4 w-4" /> 清空这场
            </button>
          )}
          {finished && !running && (
            <button onClick={save} disabled={saved}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border/60 px-4 py-2 text-sm text-muted-foreground hover:text-foreground disabled:opacity-50">
              <Save className="h-4 w-4" /> {saved ? "已存入沉淀" : "存入沉淀"}
            </button>
          )}
        </div>

        {/* 开销提示：辩论比问答重得多，让用户在点下去之前就知道要花多久、调几次模型 */}
        {!running && !status && (
          <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground/70">
            ⏱ {rounds === 2
              ? "两轮约 3 分钟 · 5 次模型调用 · 约 6 万字进上下文"
              : "一轮约 100 秒 · 3 次模型调用 · 约 3.5 万字进上下文"}
            （每个角色都会带上完整底稿）。其中拉底稿约 35 秒、走公开数据接口，不消耗 token。
            省额度可用「订阅接入」的本机 CLI，或选中档模型——数据已备齐，模型只做组织和表达。
          </p>
        )}

        {status && <p className="mt-3 text-xs text-muted-foreground">{status}</p>}
        {!running && stages.length > 0 && <AiStamp ts={session.ts} className="mt-2" />}
        {error && (
          <p className="mt-3 flex items-start gap-1.5 text-xs text-destructive">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {error}
          </p>
        )}

        {progress.length > 0 && (
          <div className="mt-4 border-t border-border/40 pt-3">
            <p className="mb-2 text-[11px] text-muted-foreground">{DOSSIER_HINT}</p>
            <div className="flex flex-wrap gap-x-4 gap-y-1.5">
              {progress.map((p) => (
                <span key={p.title} className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                  {p.ok
                    ? <CheckCircle2 className="h-3 w-3 text-primary/70" />
                    : <Circle className="h-3 w-3 text-muted-foreground/40" />}
                  {p.title}
                </span>
              ))}
            </div>
            {missing.length > 0 && (
              <p className="mt-2 text-[11px] text-warning">
                未取到：{missing.join("、")}（双方立论时不得臆测这部分）
              </p>
            )}
          </div>
        )}
      </GlassCard>

      <div className="mt-4 space-y-4">
        {stages.map((s) => (
          <div key={s.stage} className={`rounded-xl border p-4 ${STAGE_TONE[s.stage]}`}>
            <div className="mb-2 flex items-center gap-2">
              <Swords className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-semibold">{s.label}</span>
              {/* 这里只判 !s.done，**不再叠加 `running`**。
                  不变量：`done=false` 只在流真的在跑时存在——两处归一化保证了它
                  （恢复存档时 + `finally` 收口时，各有一条 E2E 变红实验盯着）。
                  加过一次 `&& running`，变红实验证明那条分支永远进不去。 */}
              {!s.done && <span className="animate-pulse text-[11px] text-muted-foreground">生成中…</span>}
              {s.outcome && (
                <span className="inline-flex items-center gap-1 text-[11px] text-warning">
                  <AlertTriangle className="h-3 w-3" /> {OUTCOME_TEXT[s.outcome]}
                </span>
              )}
            </div>
            <div className="prose prose-sm dark:prose-invert max-w-none text-foreground prose-table:text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.content || "…"}</ReactMarkdown>
            </div>
          </div>
        ))}
      </div>

      {stages.length === 0 && !running && (
        <GlassCard className="mt-4">
          <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
            <Swords className="h-8 w-8 text-muted-foreground/40" />
            输入一个代码开始。后端会先拉一份客观事实底稿，再让多方 / 空方基于同一份数据互相质疑。
            <span className="text-xs">产出的是「分歧点 + 验证清单」，不是买卖建议。</span>
          </div>
        </GlassCard>
      )}

      <Disclaimer />
    </div>
  );
}
