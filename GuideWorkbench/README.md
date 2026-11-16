# 动作目录引用的执行脚本

此目录保留现有工作台的 `natlan_live_runner.js`，供 GenshinGuideAI 动作目录做源码绑定检查。它依赖 BetterGI 脚本 API 及运行时另行生成的 plan / command / routes 文件；不是一个双击即可运行的完整工作台。

本次独立短流程入口是 `GenshinGuideAI/tools/run_live_smoke.py`。发布过程不安装或启动本目录脚本，也没有把它的源码存在视为完整攻略已经可以自动执行。