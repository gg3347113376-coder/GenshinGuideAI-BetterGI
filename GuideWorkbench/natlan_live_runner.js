// Native BetterGI executor. Guide content is data; no per-action approval or eval.
(async function () {
    const allowed = new Set(["VK_W", "VK_A", "VK_S", "VK_D", "VK_F", "VK_T", "VK_E", "VK_Q", "VK_SPACE", "VK_LBUTTON", "VK_1", "VK_2", "VK_3", "VK_4", "VK_ESCAPE"]);
    const norm = text => String(text || "").replace(/\s+/g, "");
    const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
    const validPoint = p => p && Number.isFinite(p.x) && Number.isFinite(p.y) && Math.abs(p.x) < 1e6 && Math.abs(p.y) < 1e6;
    const validName = name => typeof name === "string" && /^[a-zA-Z0-9_-]{1,64}$/.test(name);
    const stamp = () => new Date().toISOString();
    const save = (name, data) => {
        if (!file.writeTextSync(name, JSON.stringify(data, null, 2))) throw new Error("无法保存执行记录，已停止");
    };
    function point() {
        const p = genshin.getPositionFromMap();
        const result = p && {x: Number(p.x), y: Number(p.y)};
        if (!validPoint(result)) throw new Error("未识别到有效坐标");
        return result;
    }
    function ready() {
        // The native guard waits for foreground/resume and observes the stop hotkey.
        waitForGameInput();
    }
    function observe(id) {
        ready();
        const info = {time: stamp()};
        try { info.position = point(); } catch (error) { info.position_error = String(error); }
        const frame = captureGameRegion();
        try {
            if (!file.writeImageSync("evidence/" + id + ".png", frame.srcMat)) throw new Error("无法保存截图");
            const hits = frame.findMulti(RecognitionObject.ocrThis);
            info.text = [];
            for (let i = 0; i < hits.count; i++) if (!/UID/i.test(hits[i].text)) info.text.push(hits[i].text);
        } finally { frame.dispose(); }
        return info;
    }
    async function textGate(texts, seconds, action = "") {
        let stable = 0, previous = "";
        const start = Date.now();
        while (Date.now() - start < seconds * 1000) {
            ready();
            const frame = captureGameRegion();
            try {
                const hits = frame.findMulti(RecognitionObject.ocrThis);
                const matches = [];
                for (let i = 0; i < hits.count; i++)
                    if (texts.some(text => norm(hits[i].text).includes(norm(text)))) matches.push(hits[i]);
                if (matches.length === 1 && isGameInputReady()) {
                    const label = norm(matches[0].text);
                    stable = label === previous ? stable + 1 : 1;
                    previous = label;
                    if (stable >= 2) {
                        if (action === "dialogue") matches[0].click();
                        else if (action === "interact") keyPress("VK_F");
                        return matches[0].text;
                    }
                } else { stable = 0; previous = ""; }
            } finally { frame.dispose(); }
            await sleep(200);
        }
        return null;
    }
    function validate(cmd) {
        if (!cmd || !validName(cmd.id)) throw new Error("步骤编号无效");
        if (!["probe", "map_probe", "main", "tp", "path", "keys", "interact", "dialogue", "collect", "fight", "wait", "auto_dialogue"].includes(cmd.kind)) throw new Error("未知动作:" + cmd.kind);
        if (["tp", "path"].includes(cmd.kind) && !validPoint(cmd.target)) throw new Error("目标坐标无效");
        if (cmd.start && !validPoint(cmd.start)) throw new Error("起点坐标无效");
        if (cmd.kind === "path" && !validName(cmd.route)) throw new Error("路线文件名无效");
        if (cmd.radius !== undefined && (!Number.isFinite(cmd.radius) || cmd.radius < 0.5 || cmd.radius > 35)) throw new Error("到达半径无效");
        if (["interact", "dialogue", "collect"].includes(cmd.kind) && !norm(cmd.target_text)) throw new Error("缺少交互目标");
        if (cmd.after_texts !== undefined && (!Array.isArray(cmd.after_texts) || !cmd.after_texts.length || cmd.after_texts.some(t => typeof t !== "string" || !norm(t)))) throw new Error("完成条件无效");
        if (cmd.kind === "collect" && !cmd.after_texts) throw new Error("拾取必须配置奖励证据");
        if (cmd.wait_seconds !== undefined && (!Number.isFinite(cmd.wait_seconds) || cmd.wait_seconds < 0.2 || cmd.wait_seconds > 120)) throw new Error("识别等待时间无效");
        if (cmd.kind === "fight" && (cmd.strategy !== undefined && !validName(cmd.strategy))) throw new Error("战斗策略无效");
        if (cmd.timeout !== undefined && (!Number.isFinite(cmd.timeout) || cmd.timeout < 1 || cmd.timeout > 120)) throw new Error("战斗超时无效");
        if (cmd.on_missing && (cmd.kind !== "collect" || cmd.on_missing !== "record_and_continue")) throw new Error("仅收集目标缺失可记录后继续");
        if (cmd.kind === "keys") {
            if (!Array.isArray(cmd.keys) || !cmd.keys.length || cmd.keys.length > 20) throw new Error("按键序列无效");
            for (const k of cmd.keys) if (!allowed.has(k.key) || !Number.isInteger(k.ms) || k.ms < 0 || k.ms > 5000) throw new Error("按键或持续时间不允许");
        }
    }
    async function execute(cmd, result) {
        ready();
        if (cmd.kind === "probe") return;
        if (cmd.kind === "map_probe") {
            const p = genshin.getPositionFromBigMap();
            result.map_position = {x: Number(p.x), y: Number(p.y)};
        } else if (cmd.kind === "main") {
            await genshin.returnMainUi(); await sleep(400); result.position = point();
        } else if (cmd.kind === "tp") {
            await genshin.returnMainUi(); await sleep(300);
            await genshin.tp(cmd.target.x, cmd.target.y); await sleep(500);
            result.position = point();
            if (dist(result.position, cmd.target) > (cmd.radius || 35)) throw new Error("传送后位置不符");
        } else if (cmd.kind === "path") {
            await genshin.returnMainUi(); await sleep(300);
            if (cmd.start && dist(point(), cmd.start) > 20) throw new Error("角色不在该段起点附近");
            for (let attempt = 0; attempt < 2; attempt++) {
                ready();
                await pathingScript.runFileWithTimeout("routes/" + cmd.route + ".json", 120); await sleep(300);
                result.position = point(); result.path_attempts = attempt + 1;
                if (dist(result.position, cmd.target) <= (cmd.radius || 8)) break;
                // Retry only an arrival mismatch, never cancellation or an action exception.
                if (attempt || dist(result.position, cmd.target) > 20) throw new Error("路线执行后未到达目标");
                log.info("到达误差较大，自动重新接近一次");
            }
        } else if (cmd.kind === "keys") {
            for (const k of cmd.keys) {
                ready();
                if (!k.ms) keyPress(k.key);
                else {
                    let remaining = k.ms;
                    while (remaining > 0) {
                        ready(); keyDown(k.key);
                        try {
                            while (remaining > 0 && isGameInputReady()) {
                                const slice = Math.min(remaining, 100);
                                await sleep(slice); remaining -= slice;
                            }
                        } finally { keyUp(k.key); }
                    }
                }
                await sleep(250);
            }
        } else if (["interact", "dialogue", "collect"].includes(cmd.kind)) {
            const action = cmd.kind === "dialogue" ? "dialogue" : "interact";
            result.target_evidence = await textGate([cmd.target_text], cmd.wait_seconds || 8, action);
            if (!result.target_evidence) {
                if (cmd.kind === "collect" && cmd.on_missing === "record_and_continue") {
                    result.status = "unconfirmed"; result.reason = "未找到唯一的宝箱交互，不判定已领取"; return;
                }
                throw new Error("交互文字缺失或不唯一:" + cmd.target_text);
            }
            await sleep(200);
        } else if (cmd.kind === "fight") {
            const cts = dispatcher.getLinkedCancellationTokenSource();
            cts.cancelAfter(((cmd.timeout || 110) + 5) * 1000);
            try {
                const p = new AutoFightParam(cmd.strategy || "GuideWorkbench-Arle");
                p.Timeout = cmd.timeout || 110; p.FightFinishDetectEnabled = true; p.PickDropsAfterFightEnabled = false;
                await dispatcher.runAutoFightTask(p, cts.token);
            } finally { cts.dispose(); }
        } else if (cmd.kind === "auto_dialogue") {
            dispatcher.addTimer(new RealtimeTimer("AutoSkip"));
            try { await sleep((cmd.wait_seconds || 15) * 1000); }
            finally { dispatcher.clearAllTriggers(); }
        } else if (cmd.kind === "wait") await sleep((cmd.wait_seconds || 1) * 1000);
        if (cmd.after_texts) {
            result.completion_evidence = await textGate(cmd.after_texts, cmd.wait_seconds || 15);
            if (!result.completion_evidence) {
                if (cmd.kind === "collect" && cmd.on_missing === "record_and_continue") {
                    result.status = "unconfirmed"; result.reason = "交互已尝试，但未识别到新的奖励证据"; return;
                }
                throw new Error("未取得完成证据:" + cmd.after_texts.join("/"));
            }
        }
    }
    async function runStep(cmd, id) {
        validate(cmd);
        const result = {id: cmd.id, kind: cmd.kind, title: cmd.title || cmd.id, status: "running", started: stamp()};
        try {
            result.before = observe(id + "-before");
            if (cmd.after_texts && cmd.after_texts.some(t => result.before.text.some(line => norm(line).includes(norm(t))))) {
                // A reward left on screen by a previous pickup cannot verify this step.
                await sleep(2000); result.before = observe(id + "-before");
                if (cmd.after_texts.some(t => result.before.text.some(line => norm(line).includes(norm(t))))) throw new Error("完成文字在动作前已经出现");
            }
            await execute(cmd, result);
            if (result.status === "running") result.status = cmd.kind === "probe" ? "observed" : (cmd.after_texts ? "verified" : "action_finished");
            result.after = observe(id + "-after");
            return result;
        } catch (error) {
            result.status = "failed"; result.error = String(error);
            // Do not call the foreground wait after cancellation: save the failure promptly.
            throw error;
        } finally {
            result.finished = stamp(); save("results/" + id + ".json", result);
        }
    }
    async function sequence(plan, runId) {
        if (!validName(plan.id) || !Array.isArray(plan.steps) || !plan.steps.length || plan.steps.length > 200) throw new Error("连续流程无效");
        const ids = new Set();
        for (const s of plan.steps) {
            validate(s);
            if (ids.has(s.id)) throw new Error("步骤编号重复");
            ids.add(s.id);
            if (s.kind === "path") {
                const route = JSON.parse(await file.readText("routes/" + s.route + ".json"));
                if (!Array.isArray(route.positions) || !route.positions.length || route.positions.some(p => !validPoint(p))) throw new Error("路线点位无效:" + s.route);
                if (dist(route.positions[route.positions.length - 1], s.target) > (s.radius || 8)) throw new Error("路线终点与验收坐标不符");
            }
        }
        const report = {id: runId, plan_id: plan.id, title: plan.title, scope: plan.scope || "configured_steps", status: "running", started: stamp(), total: plan.steps.length, events: [], real_route_completed: false};
        report.recoveries = []; let anchor = null; const navigated = [];
        const persist = () => { save("continuous-state.json", report); save("runs/" + runId + ".json", report); };
        persist();
        try {
            for (let i = 0; i < plan.steps.length; i++) {
                const s = plan.steps[i]; report.current = {index: i + 1, id: s.id, title: s.title || s.id}; persist();
                log.info("连续执行 " + (i + 1) + "/" + plan.steps.length + "：" + (s.title || s.id));
                let event;
                try {
                    event = await runStep(s, runId + "-" + s.id);
                } catch (error) {
                    // A global user stop must propagate; local fight/OCR failures continue.
                    await sleep(1);
                    const failed = JSON.parse(await file.readText("results/" + runId + "-" + s.id + ".json"));
                    if (s.kind === "path" && anchor && report.recoveries.length < 1) {
                        await genshin.returnMainUi(); await sleep(300);
                        let actual = null;
                        try { actual = point(); } catch (_) {}
                        const previous = failed.before && failed.before.position;
                        if (!actual || (previous && dist(actual, previous) > 250)) {
                            report.recoveries.push({step: s.id, started: stamp(), position: actual, reason: "导航中位置跨区变化或无法定位，返回最近传送检查点"}); persist();
                            log.info("自动返回路线检查点；只重走移动段，不重复领取或对话");
                            await execute(anchor, {});
                            for (const prior of navigated) await execute(Object.assign({}, prior, {start: null}), {});
                            event = await runStep(Object.assign({}, s, {start: null}), runId + "-" + s.id + "-recovery");
                            report.recoveries[report.recoveries.length - 1].finished = stamp();
                        }
                    }
                    if (!event && ["path", "tp", "main"].includes(s.kind)) {
                        const blocked = new Error("无法继续前进：" + String(error));
                        blocked.navigationBlocked = true; throw blocked;
                    }
                    if (!event) {
                        event = failed; event.status = "unconfirmed"; event.reason = "本轮先继续后续步骤：" + String(error);
                        save("results/" + runId + "-" + s.id + ".json", event);
                        log.info(event.reason);
                    }
                }
                report.events.push(event);
                if (s.kind === "tp") { anchor = s; navigated.length = 0; }
                else if (s.kind === "path") navigated.push(s);
                persist();
                await sleep(120);
            }
            report.status = report.events.some(s => s.status === "unconfirmed") ? "finished_with_unverified" : "steps_finished";
            log.info("连续流程结束：" + report.events.length + "/" + report.total + "，未确认收集 " + report.events.filter(s => s.status === "unconfirmed").length);
            return report;
        } catch (error) {
            report.status = error.navigationBlocked ? "blocked_navigation" : "stopped"; report.error = String(error); throw error;
        } finally { report.finished = stamp(); persist(); }
    }
    const started = Date.now(); let last = "";
    try {
        if (typeof settings !== "undefined" && settings.continuous) {
            const plan = JSON.parse(await file.readText("plan.json"));
            await sequence(plan, "run-" + Date.now()); return;
        }
        save("runner-state.json", {status: "ready", started: stamp()});
        while (Date.now() - started < 7200000) {
            const cmd = JSON.parse(await file.readText("command.json"));
            if (cmd.id === last) { await sleep(800); continue; }
            if (!validName(cmd.id) || cmd.plan_id !== "natlan-p4") throw new Error("指令标识无效");
            last = cmd.id;
            if (cmd.kind === "stop") { save("runner-state.json", {status: "stopped", id: cmd.id}); save("results/" + cmd.id + ".json", {id: cmd.id, status: "stopped"}); return; }
            let previous = "";
            try { previous = await file.readText("results/" + cmd.id + ".json"); } catch (_) {}
            if (previous) { save("runner-state.json", {status: "ready", skipped_id: cmd.id, reason: "已有执行记录，禁止重复发送"}); continue; }
            save("runner-state.json", {status: "running", id: cmd.id, started: stamp()});
            try {
                const result = cmd.kind === "sequence" ? await sequence(cmd.plan, cmd.id) : await runStep(cmd, cmd.id);
                save("results/" + cmd.id + ".json", result); save("runner-state.json", {status: "ready", last_result: result});
            } catch (error) {
                save("runner-state.json", {status: "ready", last_result: {id: cmd.id, status: "failed", error: String(error)}});
                // Propagate cancellation instead of silently restarting the service.
                await sleep(1);
            }
        }
    } catch (error) {
        save("runner-stopped.json", {time: stamp(), last_id: last, error: String(error)}); throw error;
    }
})();
