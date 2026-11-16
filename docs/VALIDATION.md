# 发布验证记录

日期：2026-11-16。对象：本仓库发布副本，不是原开发目录。

## 本次完成

- Python：`python -B -m unittest discover -s tests -v`，205 项，200 通过、5 跳过。
- BetterGI 定向测试：NativeTeleportWalkSmokeTests、BrowserGameSafetyTests、PressedInputStateTests、NewRetryTests，共 31 项全部通过。
- 动作目录：7 个声明有源码绑定的动作均找到对应文件和符号；wait / unknown 没有实现绑定。源码存在不等于适配器已连通或实机验证。
- 从发布副本执行 `scripts/build.ps1`，Windows x64 自包含构建成功，固定测试脚本准备成功。构建沿用原代码，仍有上游/既有编译警告；本次没有进行全仓库问题修复。
- 检查运行包的 .NET 运行时、BetterGI.dll SHA-256 与能力记录一致；检查未包含个人 User/config.json、运行日志、账号数据库、额外蒙德 OBJ。
- 对拟上传文本扫描常见令牌、私钥与带凭据 URL；无实际命中。此前一处 Password 命中是 XAML Binding，已经核对。此项不是完整安全审计。

## 实机状态

本次没有启动或操作游戏。用户此前明确告知已卸载本地原神。

2026-11-09 曾确认自包含应用能打开；当时实机预检返回 `blocked / game_missing / execution_attempted=false`。这条历史启动记录不等于 2026-11-16 新构建已经完成 UI 或游戏验收。

锚点传送、短距离移动、停稳，以及游戏内各阶段暂停、失焦、停止、重启，均未完成实机验收。完整攻略计划仍不允许直接执行；独立的固定短流程入口与其分开。

## 范围限制

没有运行全部上游 BetterGI 测试，没有重新进行模型质量评测，没有进行跨电脑兼容性验证。额外蒙德几何文件未分发，相关两个 RealMondstadt 测试不在本轮测试范围。
