using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Recognition;
using GenshinApi = BetterGenshinImpact.Core.Script.Dependence.Genshin;
using Microsoft.Extensions.Logging;
using BetterGenshinImpact.Core.Simulator;
using BetterGenshinImpact.GameTask.AutoTrackPath;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Common.BgiVision;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using OpenCvSharp;
using Vanara.PInvoke;
using static BetterGenshinImpact.GameTask.Common.TaskControl;

namespace BetterGenshinImpact.GameTask.AutoPathing;

// A bounded live check, separate from evidence-only guide plans.
internal static class NativeTeleportWalkSmoke
{
    internal static async Task<string> Run(CancellationToken token)
    {
        var directory = Global.Absolute(Path.Combine("User", "LiveSmoke", DateTime.UtcNow.ToString("yyyyMMddTHHmmssfff") + "-" + Guid.NewGuid().ToString("N")[..8]));
        Directory.CreateDirectory(directory);
        var receipt = Path.Combine(directory, "receipt.json");
        var result = new JObject
        {
            ["schema_version"] = "1.0.0", ["kind"] = "selected_waypoint_teleport_walk",
            ["started_utc"] = DateTime.UtcNow.ToString("O"), ["status"] = "running",
            ["phase"] = "preflight", ["execution_attempted"] = false,
            ["teleport_confirmed"] = false, ["walk_confirmed"] = false, ["stop_confirmed"] = false,
            ["walk_duration_ms"] = 600, ["evidence_directory"] = directory
        };
        void Save() => File.WriteAllText(receipt, result.ToString(Formatting.Indented));
        void Phase(string name) { result["phase"] = name; Save(); }
        void Screenshot(string name)
        {
            using var frame = CaptureToRectArea();
            if (!Cv2.ImWrite(Path.Combine(directory, name + ".png"), frame.SrcMat))
                throw new IOException("无法保存实测截图。");
        }
        NativeDestinationInput? input = null;
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(token);
        timeout.CancelAfter(TimeSpan.FromSeconds(90));
        var ct = timeout.Token;
        Save();
        try
        {
            var context = TaskContext.Instance();
            if (!context.IsInitialized || BrowserGameWindow.Current != null || NativeDestinationInput.Current != null)
                throw new InvalidOperationException("此入口需要空闲的本地原神截图器。");
            if (User32.GetForegroundWindow() != context.GameHandle || !SystemControl.IsGenshinImpactActiveByProcess())
                throw new InvalidOperationException("本地原神不在前台，未发送游戏操作。");
            input = new NativeDestinationInput(context.GameHandle, ct);
            WaitForGameInput(ct);
            var selected = ReadSelectedWaypoint();
            Screenshot("01-selected-waypoint");
            await Delay(250, ct);
            if (selected != ReadSelectedWaypoint()) throw new InvalidOperationException("两帧锚点面板不一致，未传送。");
            result["selected_panel_text"] = selected;
            result["unlocked_evidence"] = "two_fresh_selected_panels_with_teleport_button";
            result["execution_attempted"] = true;
            Phase("teleport");
            await new TpTask(ct).TeleportSelectedWaypoint();
            result["teleport_confirmed"] = true;
            Phase("landed");
            await Delay(500, ct);
            var locator = new GenshinApi();
            Point2f Position()
            {
                using var frame = CaptureToRectArea();
                if (!Bv.IsInMainUi(frame) || Bv.GetMotionStatus(frame) != MotionStatus.Normal)
                    throw new InvalidOperationException("角色不在可确认的地面状态，停止短距离移动。");
                var position = locator.GetPositionFromMap("Teyvat", 0);
                if (position == null || !IsFinite(position.Value) || position.Value == default)
                    throw new InvalidOperationException("无法取得新的小地图定位，未确认移动或停稳。");
                return position.Value;
            }
            var start = Position();
            result["start_position"] = JArray.FromObject(new[] { start.X, start.Y });
            Screenshot("02-landed");
            Phase("walk");
            try
            {
                Simulation.SendInput.Keyboard.KeyDown(User32.VK.VK_W);
                await Delay(600, ct);
            }
            finally { input.Release(); }
            Phase("stop_check");
            await Delay(400, ct);
            var samples = new Point2f[3];
            for (var i = 0; i < samples.Length; i++)
            {
                samples[i] = Position();
                Screenshot("03-stopped-" + i);
                if (i < samples.Length - 1) await Delay(400, ct);
            }
            result["stop_positions"] = JArray.FromObject(samples.Select(p => new[] { p.X, p.Y }));
            result["held_input_count"] = input.HeldInputs().Length;
            result["forward_key_down"] = Simulation.IsKeyDown(User32.VK.VK_W);
            ValidateProgress(start, samples, input.HeldInputs().Length, Simulation.IsKeyDown(User32.VK.VK_W));
            result["walk_confirmed"] = true;
            result["stop_confirmed"] = true;
            result["status"] = "passed";
            result["phase"] = "finished";
        }
        catch (OperationCanceledException ex)
        {
            result["status"] = token.IsCancellationRequested ? "stopped" : "timed_out";
            result["error"] = ex.Message;
        }
        catch (Exception ex)
        {
            result["status"] = token.IsCancellationRequested ? "stopped" : "failed";
            result["error"] = ex.Message;
        }
        finally
        {
            try { input?.Dispose(); }
            catch (Exception ex)
            {
                result["status"] = "failed";
                result["stop_confirmed"] = false;
                result["release_error"] = ex.Message;
            }
            result["finished_utc"] = DateTime.UtcNow.ToString("O");
            Save();
        }
        Logger.LogInformation("实测结果 {Status}，记录：{Receipt}", result["status"], receipt);
        if (result["status"]?.Value<string>() != "passed")
            throw new InvalidOperationException("实测未通过，已保存记录：" + receipt);
        return receipt;
    }

    private static string ReadSelectedWaypoint()
    {
        using var frame = CaptureToRectArea();
        using var button = frame.Find(RecognitionAssets.Get("QuickTeleport", "TeleportButton", frame));
        if (!Bv.IsInBigMapUi(frame) || button.IsEmpty())
            throw new InvalidOperationException("请在大地图选中一个已解锁的地面锚点，保留右侧传送面板。");
        // Read the selected detail heading, not background region names or map legends.
        using var panel = frame.DeriveCrop(frame.Width * 2 / 3, 0, frame.Width - frame.Width * 2 / 3, frame.Height / 2);
        var hits = panel.FindMulti(RecognitionObject.OcrThis);
        try
        {
            var text = string.Join(" ", hits.Select(hit => hit.Text));
            if (!text.Contains("传送锚点") || text.Contains("未解锁") || text.Contains("未激活"))
                throw new InvalidOperationException("未确认选中的是已解锁传送锚点，未发送操作。");
            return text;
        }
        finally { foreach (var hit in hits) hit.Dispose(); }
    }

    internal static void ValidateProgress(Point2f start, Point2f[] samples, int heldInputs, bool forwardDown)
    {
        if (!IsFinite(start) || samples.Length != 3 || samples.Any(p => !IsFinite(p)))
            throw new InvalidOperationException("定位样本不完整或无效。");
        var moved = start.DistanceTo(samples[0]);
        if (moved < 1 || moved > 12) throw new InvalidOperationException("未确认合理的短距离位移。");
        if (heldInputs != 0 || forwardDown || samples.Any(p => p.DistanceTo(samples[0]) > 1.5))
            throw new InvalidOperationException("尚未确认角色停稳及输入释放。");
    }

    private static bool IsFinite(Point2f point) => float.IsFinite(point.X) && float.IsFinite(point.Y);
}
