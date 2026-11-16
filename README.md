# GenshinGuideAI + BetterGI

原神攻略理解与受控执行的开发快照，版本 `v0.1.0-preview.1`。这是个人实验分支，基于 [BetterGI](https://github.com/babalae/better-genshin-impact)，不属于上游正式发行版。

**当前可验证的是离线计划、输入保护逻辑和程序启动；真实游戏里的传送、走路、停稳尚未验收。** 不应将本项目理解为已经完成的全地图自动寻路或自动主线程序。

## 下载与启动

在 [Releases](https://github.com/gg3347113376-coder/GenshinGuideAI-BetterGI/releases) 下载 `GenshinGuideAI-BetterGI-win-x64-preview.1.zip`，完整解压到可写目录，打开 `BetterGI/BetterGI.exe`。包内包含 .NET 8 Windows x64 运行时；Windows 10 22H2 / Windows 11，首次启动可能按程序清单申请管理员权限。

发布包不含游戏客户端、个人账号配置、运行日志、攻略原视频、Ollama 大模型或额外提取的蒙德 OBJ 地形。BetterGI 自身依赖的地图识别、OCR 和模型资源通过其原有 NuGet 依赖构建。启动 BetterGI 不等于启动攻略自动执行。

## 组成与能力

- `GenshinGuideAI/`：统一 JSON / SQLite 协议、证据索引、动作目录、OCR/转写校验、目标绑定、独立语义复核、计划生成及测试。
- `BetterGI/`：保留上游源码和许可证，包含本项目已有的浏览器接入、地图选点、输入释放与失焦保护，以及本地客户端的独立短流程测试入口。
- `GuideWorkbench/`：动作目录引用的现有执行脚本，供源码绑定检查使用。
- `scripts/build.ps1`：构建 Windows x64 自包含测试版并安装固定测试脚本，不启动游戏、不发送键鼠。
- `docs/VALIDATION.md`：本次发布检查与历史验证边界。
- `UPSTREAM.md`：上游版本、资源来源及未随包提供的资源。

动作目录在 `GenshinGuideAI/schema/action_catalog.json`。计划保留证据引用与未知项，`execution_allowed=false`；尚未自动把完整攻略计划交给游戏执行。

## 离线运行

需要 Python 3.11+。在仓库根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\GenshinGuideAI\requirements-phase1.txt
$env:PYTHONPATH = (Resolve-Path .\GenshinGuideAI\src).Path
.\.venv\Scripts\python.exe -m ggai validate .\GenshinGuideAI\samples\sample_project.json
```

完整测试还需要 PyAV / NumPy；文字核验与语音复听依赖见 `requirements-grounding.txt` 和 `GenshinGuideAI/docs/GROUNDING.md`。大模型使用本地 Ollama，模型文件需要自行准备。当前入口的默认模型是 `qwen3.5:4b-q4_K_M`，HTTP 地址是 `http://127.0.0.1:11435`；可显式传 `--model` / `--host`。

分析自己的攻略片段：

```powershell
.\.venv\Scripts\python.exe .\GenshinGuideAI\tools\plan_guide.py --video D:\Guides\clip.mp4 --transcript D:\Guides\transcript.json --output D:\GuideRuns\new-run --start 0 --end 20 --frames '1,6,12,19'
```

转写 JSON 形如 `{"segments":[{"start":0,"end":2,"text":"原文"}]}`。输出目录必须不存在。入口会核验本地证据并调用模型，不操作游戏。原有 `run_phase1.ps1` 是开发机样例启动脚本，依赖当地的数据布局；换电脑应使用上面的参数化入口。

## 固定的实机测试入口

仅针对**本地原神客户端**。需要用户已登录、停在大地图、手动选中已解锁的「传送锚点」，右侧有「传送」按钮，并保持游戏前台。此入口不支持云原神，不代表浏览器接入代码已完成验收。

```powershell
python .\GenshinGuideAI\tools\run_live_smoke.py --bettergi D:\Apps\GenshinGuideAI-BetterGI\BetterGI --run --output D:\GuideRuns\new-live-check
```

上面的路径要改为实际解压目录。只有加 `--run` 才会尝试执行；不加时只准备固定脚本。流程为核验选中锚点 → 传送并等待落地 → 前进 600 毫秒 → 松开输入并检查位移与停稳。只有当本次新生成的 receipt 同时证明传送、移动、停稳且没有持有按键时才算通过。没有游戏或游戏不在前台时直接返回 blocked。

**尚缺的实机验证**：这个短流程、各阶段暂停 / 失焦 / 停止 / 重启、不同电脑的输入与分辨率适配。已有浏览器与自由目的地相关代码仍属实验代码；本包不包含它们的完整数据和可靠性保证。

## 从源码构建

需要 .NET 8 SDK（开发时使用 8.0.427）和 Windows x64。仓库根目录执行：

```powershell
.\scripts\build.ps1 -OutputDirectory D:\Builds\GenshinGuideAI-BetterGI -Python python
```

如要运行上游依赖图片的测试，请先 `git submodule update --init --recursive`。定向输入保护测试不依赖这些图片。蒙德 OBJ 相关两个测试需要另行提供原始几何文件；见 `UPSTREAM.md`。

## 许可证与历史材料

BetterGI 源码依照其 [GPL-3.0 许可证](BetterGI/LICENSE) 提供。各第三方组件保留原许可；本仓库没有将第三方代码重新授权为自有代码。GuideAI 来自用户提供的产品包及本项目后续开发，当前为公开的开发快照，没有新增覆盖全仓库的许可证。

`GenshinGuideAI/docs/reports/` 和子项目 README 包含原产品包的历史材料；部分截图与外部运行产物不随本次发布。当前状态以本页和 `docs/VALIDATION.md` 为准，历史沙盘演示和模拟执行结果不能作为真实游戏通过的证明。
