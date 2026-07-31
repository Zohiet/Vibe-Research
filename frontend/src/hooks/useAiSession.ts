import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

// AI 会话内存（VR-GOAL-010）：把各页的 AI 产出存到后端进程内存，
// **切页 / 刷新都还在，后端一停就没**。绝不落盘。
//
// 为什么不是 localStorage：AI 输出最容易撑爆它的 5 MB 配额，而 localStorage
// 写满会**直接抛异常**导致整页白屏（CLAUDE.md 记着的坑）；而且要模拟"后端一停就没"
// 还得再加一套 boot_id 校验——多一套机制就多一处会失灵的地方。
//
// 为什么不是提到 Layout 的 context：那样切页能活，**刷新活不过**，不满足需求。

export interface AiSession<T> {
  /** 首次拉取是否已回来。false 时按空态渲染（不加骨架屏——本地请求毫秒级，加了反而闪）*/
  loaded: boolean;
  data: T | null;
  /** 生成时间（后端盖的，前端不自己写）。给 <AiStamp> 判断陈不陈旧 */
  ts: number | null;
  save: (data: T) => void;
  clear: () => void;
}

export function useAiSession<T>(key: string | null): AiSession<T> {
  const [loaded, setLoaded] = useState(false);
  const [data, setData] = useState<T | null>(null);
  const [ts, setTs] = useState<number | null>(null);
  // key 换了以后，旧 key 的迟到响应不许写进新 key 的状态（切股票时会发生）
  const keyRef = useRef(key);
  keyRef.current = key;

  useEffect(() => {
    if (!key) { setLoaded(true); return; }
    let alive = true;
    setLoaded(false);
    api.aiSessionGet<T>(key)
      .then((r) => { if (alive && keyRef.current === key) { setData(r.data); setTs(r.ts); } })
      // 后端没起 / 端点出错都当作"没有存档"——副功能不能干掉主页面（tools.py 的「失败不抛」同源）
      .catch(() => { if (alive) { setData(null); setTs(null); } })
      .finally(() => { if (alive) setLoaded(true); });
    return () => { alive = false; };
  }, [key]);

  const save = useCallback((next: T) => {
    setData(next);
    if (!key) return;
    api.aiSessionPut(key, next)
      .then((r) => { if (keyRef.current === key) setTs(r.ts); })
      .catch(() => { /* 存不上就存不上，界面上已经有内容了，不打扰用户 */ });
  }, [key]);

  const clear = useCallback(() => {
    setData(null);
    setTs(null);
    if (key) api.aiSessionDelete(key).catch(() => { /* 同上 */ });
  }, [key]);

  return { loaded, data, ts, save, clear };
}
