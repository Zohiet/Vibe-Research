# 沉淀记录落盘：`~/.vibe-research/myaccumulation/`

**日期**：2026-07-11
**状态**：已定稿，待实现

## 背景

「研究记录（沉淀）」目前只存在浏览器 `localStorage["vr-notes"]`（见 [frontend/src/lib/notes.ts](../../../frontend/src/lib/notes.ts)）。
问题：换浏览器 / 无痕 / 清缓存即丢，且无法在磁盘上备份或回看。

目标：把沉淀记录改为**后端持久化到本机磁盘文件**，与「我的研报」「持仓」同一红线——只落本地、不上传、不进仓。

## 决策（已与用户确认）

1. **后端文件为唯一真相源**。前端改走 `/api` 读写；后端未运行时优雅提示（与持仓/研报页一致）。
2. **首次自动迁移** `localStorage["vr-notes"]` 进文件；localStorage 原数据保留作备份，不删。
3. **一条沉淀 = 一个 markdown 文件**，文件名体现日期；目录即归档，人可读、可手改。

## 存储形态

```
~/.vibe-research/myaccumulation/
  2026-07-04_090132_每日复盘-2026-07-04.md
  2026-07-05_211540_AI算力-今日要点.md
```

- 目录：`VR_DATA_DIR/myaccumulation`，`VR_ACCUMULATION_DIR` 可单独覆盖；`VR_DATA_DIR` 默认 `~/.vibe-research`（与 myreports 同源）。
- 文件名：`{YYYY-MM-DD}_{HHMMSS}_{净化标题}.md`（时间取自该条 `ts`，本地时区）。
  - 标题净化：去掉 `<>:"/\|?*`、控制字符与路径分隔符，折叠空白，截断 ~60 字；空则兜底 `未命名`。
  - 撞名（同秒同标题）：追加 `_{id[:6]}`。
- 文件内容 = 极简 frontmatter + markdown 正文（**不引 PyYAML**，守零依赖红线）：

  ```
  ---
  id: 9f3a2c4e...
  kind: 复盘
  title: 每日复盘 2026-07-04
  ts: 1720054892000
  ---

  <原 markdown 正文>
  ```

- **frontmatter 手解析规则**：文件须以 `---\n` 开头，取到**下一个** `\n---\n` 为止为元数据区，其后全部为正文。
  - 每行 `key: value`，按第一个 `: ` 切分，value 取到行尾原文（title 里含 `:` 安全）。
  - 正文里出现 `---` 不受影响（只认第一段 frontmatter 的闭合分隔符）。
  - 解析失败（缺 frontmatter / 缺必填字段）的文件：跳过，不进列表，不报错（best-effort，与 myreports 读索引失败的容错一致）。
- **目录即索引**，不维护 `index.json`；列表时扫描 `*.md` 读 frontmatter，按 `ts` 倒序。

## 后端 `backend/myaccumulation.py`

照 [backend/myreports.py](../../../backend/myreports.py) 的规矩：原子写（temp + `os.replace`）、写/删用 `threading.Lock` 串行化。

- `ACCUMULATION_DIR`：`VR_ACCUMULATION_DIR` 或 `VR_DATA_DIR/myaccumulation`。
- `list_notes() -> list[dict]`：扫描目录，解析每个 `.md`，返回 `{id,kind,title,content,ts}`，按 `ts` 倒序。
- `add_note(kind, title, content, ts=None, id=None) -> dict`：生成 id（缺省 uuid4 hex）、ts（缺省 now ms），拼 frontmatter + 正文，算文件名，原子写盘；返回该条 dict。
- `delete_note(id) -> bool`：扫描找到 frontmatter `id` 匹配的文件，删之；命中返回 True。
- `clear_notes() -> int`：删目录内全部 `.md`，返回删除条数。
- `import_notes(notes: list[dict]) -> int`：批量导入，保留每条原 `id`+`ts`；已存在同 id 的跳过（幂等）；返回实际新增条数。
- 无 legacy 目录迁移（此前无后端存储）；localStorage→后端的迁移在前端触发（见下）。

## 后端路由 `backend/app.py`

在 myreports 段落后照抄风格新增（响应统一包 `{"data": ...}`）：

- `GET    /api/myaccumulation`            → `{data: list}`
- `POST   /api/myaccumulation` `{kind,title,content}` → `{data: note}`
- `DELETE /api/myaccumulation/{id}`       → `{data: {ok: bool}}`
- `DELETE /api/myaccumulation`            → `{data: {removed: int}}`
- `POST   /api/myaccumulation/import` `{notes:[{id,kind,title,content,ts}]}` → `{data: {imported: int}}`

Pydantic 模型：`AccumulationIn{kind,title,content}`、`AccumulationImportIn{notes: list[AccumulationItem]}`，`AccumulationItem{id,kind,title,content,ts}`。
`kind/title` 允许为空由后端兜底；`content` 空则 400。

## 前端

### `frontend/src/lib/api.ts`
新增：
- `myAccumulation(): Promise<Note[]>` → GET
- `addAccumulation(kind,title,content): Promise<Note>` → POST
- `deleteAccumulation(id): Promise<{ok:boolean}>` → DELETE `/myaccumulation/{id}`
- `clearAccumulation(): Promise<{removed:number}>` → DELETE `/myaccumulation`
- `importAccumulation(notes): Promise<{imported:number}>` → POST `/myaccumulation/import`

`Note` 类型移到 api.ts（或 notes.ts 导出、api.ts 复用），字段 `{id,kind,title,content,ts}`。

### `frontend/src/lib/notes.ts`（由同步 localStorage 改为 async 客户端）
- `listNotes(): Promise<Note[]>` → `api.myAccumulation()`
- `addNote(kind,title,content): Promise<Note>` → `api.addAccumulation(...)`
- `deleteNote(id): Promise<void>` → `api.deleteAccumulation(id)`
- `clearNotes(): Promise<void>` → `api.clearAccumulation()`
- `migrateLocalNotes(): Promise<void>`：
  - 读旧 `localStorage["vr-notes"]`；若为空或标记 `localStorage["vr-notes-migrated"]` 已置 → 直接返回。
  - 调 `api.importAccumulation(oldNotes)`；成功后置 `vr-notes-migrated="1"`。**不删** `vr-notes`（留作备份）。
  - 后端不可用（ApiError）时静默失败、不置标记（下次再试）。
- 旧的常量 `KEY="vr-notes"` 仅迁移读取时用；`MAX/persist` 等 localStorage 写逻辑移除。

### `frontend/src/pages/Notes.tsx`
- `useState<Note[]>([])` + `loading` + `error`。
- `useEffect`：先 `await migrateLocalNotes()`，再 `await listNotes()`；捕获 ApiError 设 `error`。
- 三态渲染：loading（骨架/占位）、error（"连接不到后端，请先启动 backend…"，沿用 api.ts 的 ApiError 文案）、空、列表。
- 删除 / 清空改 async，成功后刷新列表。

### `frontend/src/components/ui/SaveNoteButton.tsx`
- `onClick` 改 async：`await addNote(...)`；成功置 `saved`，失败给一次性错误提示（`title` 属性或短暂文案），可 `saving` 态防重复点击。

## 影响与取舍

- 后端未运行时**存不进也看不到**沉淀——「后端为准」的必然代价，用优雅提示兜底，与持仓/研报页一致。
- 页面副标题「数据只存本地、不上传」仍成立（落本机磁盘文件）。
- 迁移只跑一次且幂等，localStorage 旧数据保留，最坏情况可手工重来。

## 测试

`backend/tests/test_myaccumulation.py`（照 test_reports_and_security.py 风格，用 `VR_ACCUMULATION_DIR` 指向临时目录）：
- 新增→列表可见→内容/元数据 roundtrip→删除→列表消失。
- 文件名含日期、标题净化（非法字符被去除）。
- frontmatter 手解析：正文含 `---` 不破坏解析。
- `import_notes` 幂等：同 id 重复导入不新增。
- `clear` 清空返回条数。
- content 为空 → 400。

前端：`npm run build`（tsc）确保 async 改造类型通过；手动跑一遍存入→回看→删除→清空。
