# 来源与发布范围

- BetterGI 上游：https://github.com/babalae/better-genshin-impact
- 基准提交：`0af68c28f6b0e714d5304625ce644736d508022e`。本仓库保存当前修改后的源码快照，未携带开发机 Git 历史。
- BetterGI 许可证：`BetterGI/LICENSE`（GNU GPL v3）。上游 README 与源码版权标记保留在子目录内。
- 测试资源子模块：https://github.com/huiyadanli/BetterGI.UnitTest.Assets.git ，锁定 `a1965670874cb937060bcbf149a1b309e2ffd65d`。根目录 .gitmodules 调整了单仓库下的路径。
- GuideAI：用户提供的 GenshinGuideAI V3 产品包工作副本及后续协议、理解、复核、适配改动。未附原视频、账户、数据库和运行日志。
- DotRecast.Recast / DotRecast.Detour：遵循其 Zlib 许可，版本来自 BetterGI 的项目依赖。

## 未分发的额外蒙德几何资源

开发机存在 `BetterGI/BetterGenshinImpact/GameTask/AutoPathing/Assets/Navigation/mondstadt.obj`，原文件来自 HoYoMap 的游戏 HLOD 显示模型。本次源码及可执行包均不附该 OBJ，保留 source.txt 的来源记录。依赖该文件的自由目标地面寻路及两个 RealMondstadt 测试需要自行准备对应资源；它不是固定锚点传送与短走测试的依赖。

来源仓库：https://github.com/flatypus/hoyomap ，提交 `9ee2acd95981bf9cc201aef86632f05bb8449816`，原路径 `game_data/hlod_all/Area_Mengde_City_Constant_HLOD_Lod0.obj`。显示几何不等于游戏碰撞或可通行道路，真实通过性仍需实机验证。
