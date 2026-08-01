import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import { Sparkles, X, Settings, Send, Loader2, Wrench, AlertCircle, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { hasLlm, chatStream, type ChatMsg } from "@/lib/llm";
import { ApiError } from "@/lib/api";
import { SaveNoteButton } from "@/components/ui/SaveNoteButton";
import { AiStamp } from "@/components/ui/AiStamp";
import { useAiSession } from "@/hooks/useAiSession";

interface Props {
  // 本分栏/本页要喂给用户 AI 的上下文，作为对话的系统上下文。
  context: string;
  // 会话在后端内存里的标识（VR-GOAL-010）。**必填**——设成必填是为了让 tsc 把
  // 每个调用点都报出来，漏一个都编译不过；本仓库最大的伤害源就是 git 不报的语义冲突。
  //
  // 命名按"对话是关于谁的"：portfolio / watchlist / stock:600519 / sector:ai-chain。
  // **不能拿 context 去哈希**——context 里含实时行情，价格一跳 key 就变、对话就"丢"了。
  sessionKey: string;
  // 可选的额外上下文（VR-GOAL-013）。勾选框渲染在**面板内**——
  // 控制项必须和它的效果在同一个视野里；放在页面上的话，勾选会在对话进行中
  // 静默改变下一轮要发的内容、而面板里看不到任何变化。
  //
  // 本组件**不知道额外上下文是什么**（wiki 研究页也好、别的也好），只知道
  // "有个可选的东西，勾了就去取、拼进 context"。个股页传 wiki，将来别的页面传别的。
  extraContext?: { label: string; fetch: () => Promise<string> };
  suggestions?: string[];
  label?: string;
}

const TOOL_LABEL: Record<string, string> = {
  query_quote: "查行情",
  query_valuation: "查估值",
  query_reports: "查研报",
  query_news: "查新闻",
};

// 数据溯源：把工具调用的关键参数压成一小段（查了哪只/哪些代码）。
const argStr = (a: Record<string, unknown>): string => {
  if (Array.isArray(a.codes)) return (a.codes as unknown[]).join(",");
  if (typeof a.code === "string") return a.code;
  return "";
};

interface ToolUse { name: string; arg: string }
// aborted：这轮流是被中止的（切页/换问题），内容只有半截。
// 之所以要保留而不是丢弃：**已生成的这些 token 早就付过费了**（API 按生成计费，
// 订阅接入是已经 spawn 过的一次 CLI），中止只省下剩余部分，扔掉已收到的是纯亏。
// 而 AI 习惯把结论放前面，半截答案常常仍然有用。
type Msg = ChatMsg & { tools?: ToolUse[]; aborted?: boolean };

/**
 * 中止时怎么处理最后一条 assistant 气泡（VR-GOAL-010 决策 #9）。
 * 抽成纯函数是为了让这段逻辑能被单独推理和评审——它有三个分支且都不显眼。
 */
export function finalizeOnAbort(msgs: Msg[]): Msg[] {
  const last = msgs[msgs.length - 1];
  if (!last || last.role !== "assistant") return msgs;
  // 一个字都没收到 → 不留空气泡（维持原有行为，空泡看起来像出错）
  if (!last.content) return msgs.slice(0, -1);
  return [...msgs.slice(0, -1), { ...last, aborted: true }];
}

// 「问 AI」入口 —— 把当前分栏内容作为上下文，调用户自己配置的模型；
// AI 可自行调 A股数据工具作答。结论由用户模型给出，本产品不校准、不负责。
export function AskAiButton({ context, sessionKey, extraContext, suggestions = [], label = "问 AI" }: Props) {
  const [open, setOpen] = useState(false);
  const [configured, setConfigured] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [useExtra, setUseExtra] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  // 在跑的流式请求：关面板/换问题时中止，省用户的订阅/API 额度，也防迟到 chunk 写进新气泡
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (open) setConfigured(hasLlm());
  }, [open]);

  useEffect(() => () => abortRef.current?.abort(), []); // 组件卸载兜底

  // 会话内存（VR-GOAL-010）：mount 就拉，不等打开面板——否则打开时会先闪一下空白。
  // ⚠️ 内部加 `chat:` 前缀，**不要直接用 sessionKey**。
  // 页面上除了这个对话，还可能有自己的 useAiSession（每日复盘页就有：
  // 它用 "daily-review" 存复盘正文，而这里曾用同一个 key 存 Msg[]）——
  // 同一个 key 两种形状，谁后写谁赢，复盘页拿到数组喂给 ReactMarkdown 直接崩。
  // 前缀让「对话」和「页面自己的东西」在命名空间上永不相交，
  // 而不是靠每个页面自觉去起不重名的 key。
  const session = useAiSession<Msg[]>(`chat:${sessionKey}`, Array.isArray);
  useEffect(() => {
    if (!session.loaded) return;
    // 必须写 `?? []` 而不是「有才设」：换股票时 key 变、新 key 没有存档，
    // 不清空的话上一只股票的对话会留在这只股票的面板里。
    setMsgs(session.data ?? []);
  }, [session.loaded, session.data]);

  // 把当前最新的 msgs 存进后端。**只在流结束/中止时调一次**——逐 delta 存就是每秒几十个请求。
  // 用函数式 setState 读最新值（流刚跑完时 msgs 变量还是旧的），副作用挪出 updater 再执行。
  const flush = () => setMsgs((m) => { queueMicrotask(() => session.save(m)); return m; });

  const close = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
    setOpen(false);
  };

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [msgs, loading]);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || loading) return;
    setInput("");
    setErr(null);
    const history: ChatMsg[] = [...msgs.map(({ role, content }) => ({ role, content })), { role: "user", content: q }];
    // 先放用户气泡 + 一个空的 assistant 气泡，流式往里填。
    setMsgs((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "", tools: [] }]);
    setLoading(true);
    // 更新「最后一条 assistant 气泡」（不可变）。
    const patchLast = (fn: (msg: ChatMsg & { tools?: ToolUse[] }) => ChatMsg & { tools?: ToolUse[] }) =>
      setMsgs((m) => m.map((msg, i) => (i === m.length - 1 && msg.role === "assistant" ? fn(msg) : msg)));
    // 勾了才取，而且是**发消息时**才取——勾上就拉的话，你勾了又取消就白花一次
    let ctx = context;
    if (useExtra && extraContext) {
      try {
        ctx = `${context}

${await extraContext.fetch()}`;
      } catch {
        // 附加上下文拿不到不该阻断主功能——照常发，只是这轮没带上
        setErr(`${extraContext.label}拉取失败，本轮未带上`);
      }
    }
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    // 只有仍是「当前这次请求」才允许写 UI——旧请求的迟到 chunk 直接丢弃
    const alive = () => abortRef.current === ac && !ac.signal.aborted;
    try {
      await chatStream(history, ctx, {
        onTool: (tool, args) => { if (alive()) patchLast((msg) => ({ ...msg, tools: [...(msg.tools || []), { name: tool, arg: argStr(args) }] })); },
        onDelta: (t) => { if (alive()) patchLast((msg) => ({ ...msg, content: msg.content + t })); },
      }, ac.signal);
    } catch (e) {
      // 出错/中止：一个字都没收到就去掉空气泡，收到了半截就留着并标「已中断」
      // （那些 token 已经付过费了，丢掉是纯亏）。主动中止不算错误，不提示。
      setMsgs(finalizeOnAbort);
      if (!ac.signal.aborted) setErr(e instanceof ApiError ? e.message : "对话失败");
    } finally {
      if (abortRef.current === ac) {
        abortRef.current = null;
        setLoading(false);
      }
      flush(); // 存档：正常跑完、出错、被中止，三条路都要落
    }
  };

  const clearChat = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
    setErr(null);
    setMsgs([]);
    session.clear();
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-3 py-1.5 text-sm font-medium text-primary shadow-glow transition-colors hover:bg-primary/25"
      >
        <Sparkles className="h-4 w-4" />
        {label}
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/50" onClick={close} />
          <aside className="glass relative m-3 flex w-full max-w-md flex-col rounded-2xl">
            <div className="flex items-center justify-between border-b border-border/60 p-4">
              <span className="flex items-center gap-2 font-semibold text-glow">
                <Sparkles className="h-4 w-4 text-primary" /> 问 AI · 本页上下文
              </span>
              <div className="flex items-center gap-3">
                {/* 清空对话（VR-GOAL-010 决策 #10）：改成"切页也留着"之后，
                    原来靠「切走再切回」重置对话的办法就没了，得把这个能力明确补回来。 */}
                {msgs.length > 0 && (
                  <button onClick={clearChat} title="清空这段对话，重新开始"
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-destructive">
                    <Trash2 className="h-3.5 w-3.5" /> 清空对话
                  </button>
                )}
                <button onClick={close} className="text-muted-foreground hover:text-foreground">
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {!configured ? (
              // 未接入 AI：引导去设置
              <div className="flex-1 space-y-4 overflow-auto p-4 text-sm">
                <div className="rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs text-muted-foreground">
                  分析结论由你自己配置的 AI 给出，本产品只负责把本页数据打包成上下文、并让 AI 能调数据工具，
                  <b className="text-foreground">不校准、不背书、不对结果负责</b>。
                </div>
                <div>
                  <p className="mb-1.5 text-xs font-medium text-muted-foreground">将随提问发给 AI 的本页上下文：</p>
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
{context}
                  </pre>
                </div>
                <Link to="/settings" className="flex items-center justify-center gap-2 rounded-lg bg-primary/15 px-3 py-2 text-sm font-medium text-primary hover:bg-primary/25">
                  <Settings className="h-4 w-4" /> 先接入你的 AI（订阅 / API）
                </Link>
              </div>
            ) : (
              // 已接入：真对话
              <>
                <div ref={scrollRef} className="flex-1 space-y-3 overflow-auto p-4 text-sm">
                  {/* 恢复出来的对话标上生成时间——三小时前那句「当前 PE 32 倍」现在可能已经不对了 */}
                  {msgs.length > 0 && !loading && <AiStamp ts={session.ts} />}
                  {msgs.length === 0 && (
                    <div className="rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs text-muted-foreground">
                      AI 可基于本页上下文、并自行调取 A股行情/估值/研报数据作答。结论由你的模型给出，
                      <b className="text-foreground">不构成投资建议</b>。
                    </div>
                  )}
                  {msgs.map((m, i) => (
                    <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                      <div className={cn(
                        "max-w-[85%] rounded-2xl px-3 py-2 leading-relaxed",
                        m.role === "user" ? "bg-primary/20 text-foreground" : "bg-muted/40 text-foreground",
                      )}>
                        {m.tools && m.tools.length > 0 && (
                          <div className="mb-1.5 flex flex-wrap items-center gap-1">
                            <span className="text-[10px] text-muted-foreground/70">数据来源</span>
                            {m.tools.map((t, j) => (
                              <span key={j} className="inline-flex items-center gap-0.5 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-primary">
                                <Wrench className="h-2.5 w-2.5" /> {TOOL_LABEL[t.name] || t.name}{t.arg ? ` ${t.arg}` : ""}
                              </span>
                            ))}
                          </div>
                        )}
                        <p className="whitespace-pre-wrap">{m.content}</p>
                        {m.aborted && (
                          <span className="mt-1 inline-block text-[10px] text-warning">
                            · 已中断（切换页面时停了，内容只有半截）
                          </span>
                        )}
                        {m.role === "assistant" && m.content && !(loading && i === msgs.length - 1) && (
                          <div className="mt-1.5"><SaveNoteButton kind="问AI" title={`问 AI · ${msgs[i - 1]?.content?.slice(0, 24) || "对话"}`} content={m.content} /></div>
                        )}
                      </div>
                    </div>
                  ))}
                  {loading && (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> AI 正在思考 / 调取数据…
                    </div>
                  )}
                  {err && (
                    <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive">
                      <AlertCircle className="h-3.5 w-3.5 shrink-0" /> {err}
                    </div>
                  )}
                  {msgs.length === 0 && suggestions.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {suggestions.map((s) => (
                        <button key={s} onClick={() => send(s)} className="rounded-full border border-border bg-muted/40 px-2.5 py-1 text-xs hover:border-primary/40 hover:text-primary">
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <div className="border-t border-border/60 p-3">
                  {extraContext && (
                    <label className="mb-2 flex cursor-pointer items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground">
                      <input type="checkbox" checked={useExtra} onChange={(e) => setUseExtra(e.target.checked)}
                        className="h-3 w-3 accent-primary" />
                      {extraContext.label}
                    </label>
                  )}
                  <div className="flex items-end gap-2">
                    <textarea
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
                      rows={1}
                      placeholder="就本页内容提问…"
                      className="flex-1 resize-none rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50"
                    />
                    <button onClick={() => send(input)} disabled={loading || !input.trim()}
                      className="rounded-lg bg-primary/15 p-2 text-primary hover:bg-primary/25 disabled:opacity-40">
                      <Send className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </>
            )}
          </aside>
        </div>
      )}
    </>
  );
}
