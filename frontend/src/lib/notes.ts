// 研究记录（沉淀）—— 把 AI 复盘 / 今日要点 / 问 AI 的结果存本机磁盘，形成个人投研记录。
// 真相源是后端文件（~/.vibe-research/myaccumulation/，一条一个 markdown 文件），只落本地、不上传、不进仓库。
// 对应投研框架第 7 层「沉淀」。

import { api, type AccumulationList, type Note } from "@/lib/api";
import { storageGet, storageSet } from "@/lib/storage";

export type { Note };

const OLD_KEY = "vr-notes";            // ≤ 本次改造前的浏览器本地存储
const MIGRATED = "vr-notes-migrated";  // 迁移完成标记（置位后不再重复迁移）

export function listNotes(): Promise<AccumulationList> {
  return api.myAccumulation();
}

// 把一条沉淀投进 wiki 的待摄入队列（VR-GOAL-009）。本机文件复制，不经网络。
export function pushToWiki(id: string): Promise<{ path: string }> {
  return api.pushNoteToWiki(id);
}

export function addNote(kind: string, title: string, content: string): Promise<Note> {
  return api.addAccumulation(kind, title, content);
}

export function deleteNote(id: string): Promise<void> {
  return api.deleteAccumulation(id).then(() => undefined);
}

export function clearNotes(): Promise<void> {
  return api.clearAccumulation().then(() => undefined);
}

// 首次把浏览器 localStorage 里的旧沉淀整批迁到后端文件；幂等、只跑一次。
// localStorage 原数据保留作备份、不删；后端不可用则静默不置标记，下次再试。
export async function migrateLocalNotes(): Promise<void> {
  try {
    if (storageGet(MIGRATED)) return;
    const raw = storageGet(OLD_KEY);
    if (!raw) {
      storageSet(MIGRATED, "1"); // 无旧数据，直接标记完成，省得每次都读
      return;
    }
    const old = JSON.parse(raw);
    if (!Array.isArray(old) || old.length === 0) {
      storageSet(MIGRATED, "1");
      return;
    }
    await api.importAccumulation(old as Note[]);
    storageSet(MIGRATED, "1");
  } catch {
    /* 后端未启动 / localStorage 不可用：不置标记，下次进页面再迁 */
  }
}
