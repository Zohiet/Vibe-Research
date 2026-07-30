# VR-GOAL-XXX 验收报告 ｜ <标题>

- **Goal Spec**：[`../goals/VR-GOAL-XXX_<slug>.md`](../goals/VR-GOAL-XXX_<slug>.md)
- **实现 Plan**：[`../plans/VR-GOAL-XXX_<slug>.md`](../plans/VR-GOAL-XXX_<slug>.md)
- **验收日期**：YYYY-MM-DD
- **结论**：✅ 通过 / ❌ 不通过 / ⚠️ 有条件通过

---

# 一、业务验收（正文）

用业务语言写，对着 Goal Spec 的验收项逐条判定。**不要在这一节堆命令行输出。**

## 结论

一段话说清：做成了什么、用户现在能做到什么以前做不到的事。

## 逐条判定

| # | 验收项 | 结论 | 证据 |
|---|---|---|---|
| 1 | | ✅ 通过 | [`01_xxx.png`](../screenshots/VR-GOAL-XXX_<slug>/01_xxx.png) |
| 2 | | ✅ 通过 | |
| 3 | | ⚠️ 部分 | 说明差在哪、是否可接受 |

## 与 Plan 的偏差

实现过程中偏离 Plan 的地方 + 原因。没有就写「无」。
**发现了 Plan 没预料到的问题，写在这里**——这是下次写 Plan 时最值钱的输入。

## 遗留与后续

已知没做完 / 故意留到下个 Goal 的事。

---

# 二、工程追溯证据（附录）

## CI

```
$ ./ci.ps1
<粘贴关键输出>
```

- 前端 `tsc -b`：通过 / 失败
- 后端 `pytest -m "not live"`：`85 passed, 1 failed`（`test_run_cli_stream_timeout`
  为 Windows 基线失败，spawn `python3` 不存在，与本次改动无关）
- 后端 import 自检：`N` 条路由

## Playwright

```
$ npx playwright test e2e/VR-GOAL-XXX_<slug>.spec.ts
<粘贴输出>
```

截图归档目录：`docs/screenshots/VR-GOAL-XXX_<slug>/`

## 改动文件

```
$ git diff --stat <base>..<head>
```

## 关键提交

| sha | 说明 |
|---|---|
| | |

## diff 复查

- [ ] 改过的 API 的所有调用方都已跟进（grep 过）
- [ ] 没有误入库的临时文件 / 密钥 / 用户数据
- [ ] 合规红线未被触碰
