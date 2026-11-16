using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.Core.Script;
using BetterGenshinImpact.Core.Simulator;
using BetterGenshinImpact.GameTask.AutoPathing.Model;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Common.BgiVision;
using BetterGenshinImpact.GameTask.Common.Map.Maps;
using BetterGenshinImpact.GameTask.Common.Map.Maps.Base;
using Microsoft.Extensions.Logging;
using OpenCvSharp;
using Vanara.PInvoke;
using static BetterGenshinImpact.GameTask.Common.TaskControl;

namespace BetterGenshinImpact.GameTask.AutoPathing;

public static class MapDestinationTask
{
    private static int _starting;
    private const string MapName = nameof(MapTypes.Teyvat);

    public static void StartFromCursor()
    {
        var browser = BrowserGameWindow.Current;
        if (!TaskContext.Instance().IsInitialized || !SystemControl.IsGenshinImpactActive())
        {
            Logger.LogWarning("选点赶路：请先启动截图器，在前台原神大地图中指向蒙德地面目的地。");
            return;
        }
        if (TaskSemaphore.CurrentCount == 0 || Interlocked.CompareExchange(ref _starting, 1, 0) != 0)
        {
            Logger.LogWarning("选点赶路：已有任务运行，请先停止当前任务。");
            return;
        }

        try
        {
            var handle = TaskContext.Instance().GameHandle;
            var cursor = GetCursor(handle, browser);
            _ = Task.Run(async () =>
            {
                try
                {
                    await new TaskRunner().RunCurrentAsync(() => Run(handle, browser, cursor, CancellationContext.Instance.Cts.Token));
                }
                catch (Exception ex)
                {
                    Logger.LogError(ex, "选点赶路启动失败");
                }
                finally { Interlocked.Exchange(ref _starting, 0); }
            });
        }
        catch (Exception ex)
        {
            Interlocked.Exchange(ref _starting, 0);
            Logger.LogWarning("选点赶路：{Reason}", ex.Message);
        }
    }

    private static async Task Run(nint handle, BrowserGameWindow? browser, Point2f cursor, CancellationToken token)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(token);
        timeout.CancelAfter(TimeSpan.FromMinutes(3));
        var ct = timeout.Token;
        using var nativeInput = browser == null ? new NativeDestinationInput(handle, ct) : null;
        try
        {
            var screen = SystemControl.GetGameScreenRect(handle);
            var viewport = new Size(screen.Width, screen.Height);
            if (!DestinationRoutePlanner.IsSelectablePoint(cursor, viewport))
                throw new InvalidOperationException("请关闭地图详情面板，把目的地移到地图中央区域后重新选点。");
            var method = TaskContext.Instance().Config.PathingConditionConfig.MapMatchingMethod;
            var target = ReadTarget(handle, browser, cursor, method);
            // 给热键松开和地图动画留出时间，再用新画面确认地图没有被拖动或缩放。
            await Task.Delay(200, ct);
            var confirmed = ReadTarget(handle, browser, cursor, method);
            target = DestinationRoutePlanner.ConfirmTarget(target, confirmed);

            var waitStarted = Environment.TickCount64;
            while (Simulation.IsKeyDown(User32.VK.VK_CONTROL) || Simulation.IsKeyDown(User32.VK.VK_MENU)
                   || Simulation.IsKeyDown(User32.VK.VK_SHIFT))
            {
                if (Environment.TickCount64 - waitStarted > 3000)
                    throw new InvalidOperationException("请松开组合快捷键后重新选点。");
                await Task.Delay(50, ct);
            }
            if (!IsSameWindow(handle, browser))
                throw new InvalidOperationException("选点期间游戏失去焦点，已取消此次选点。");

            Logger.LogInformation("DESTINATION_SELECTED {Client} {X:F2},{Y:F2}", browser == null ? "native" : "web", target.X, target.Y);
            Logger.LogInformation("目的地已设定：({X:F1}, {Y:F1})。将根据蒙德场景几何规划地面道路。", target.X, target.Y);
            await CloseMap(browser, ct);
            Navigation.WarmUp(method);
            var start = ReadPosition(method);
            Logger.LogInformation("DESTINATION_START {X:F2},{Y:F2}", start.X, start.Y);
            var route = DestinationNavigationMesh.Current.Plan(start, target);
            ct.ThrowIfCancellationRequested();

            Logger.LogInformation("DESTINATION_PLAN navmesh {Count} start={X:F2},{Y:F2}", route.Count, start.X, start.Y);
            foreach (var point in route)
                Logger.LogInformation("DESTINATION_CORNER {X:F2},{Y:F2} {Mode}", point.X, point.Y, point.MoveMode);
            var task = new PathingTask
            {
                Info = new PathingTaskInfo { Name = "地图选点赶路", MapName = MapName, MapMatchMethod = method },
                Positions = route,
                Config = new PathingTaskConfig { RealtimeTriggers = new() { ["AutoPick"] = false } }
            };
            var progress = new DestinationProgress();
            var executor = new PathExecutor(ct)
            {
                StopOnObstacle = true,
                PartyConfig = new PathingPartyConfig
                {
                    Enabled = true, SkipPartySwitch = true, AutoPickEnabled = false,
                    AutoSkipEnabled = false, AutoFightEnabled = false, AutoEatEnabled = false,
                    RecoverTiming = RecoverTiming.Never
                }
            };
            executor.EndAction = frame =>
            {
                ct.ThrowIfCancellationRequested();
                if (!Bv.IsInMainUi(frame) || Bv.GetMotionStatus(frame) != MotionStatus.Normal)
                    throw new InvalidOperationException("选点赶路遇到非地面状态或未知界面，已停止，请人工接管。");
                var position = Navigation.GetPosition(frame, MapName, method);
                if (position == default)
                    throw new InvalidOperationException("选点赶路无法确认角色位置，已停止。");
                var waypoint = executor.CurWaypoint;
                if (progress.IsStalled(waypoint.Item1, Navigation.GetDistance(waypoint.Item2, position), Environment.TickCount64))
                    throw new InvalidOperationException("选点赶路连续没有接近路径点，可能遇到障碍，已停止。");
                return false;
            };
            await executor.Pathing(task);
            ct.ThrowIfCancellationRequested();
            Simulation.ReleaseAllKey();
            if (!executor.SuccessEnd)
                throw new InvalidOperationException("赶路过程未完成，未判定到达。");
            for (var i = 0; i < 3; i++)
            {
                await Delay(200, ct);
                var actual = ReadPosition(method);
                Logger.LogInformation("DESTINATION_POSITION {X:F2},{Y:F2} distance={Distance:F2}", actual.X, actual.Y, actual.DistanceTo(target));
                if (actual.DistanceTo(target) > DestinationRoutePlanner.ArrivalRadius)
                    throw new InvalidOperationException("路线执行结束，但仍未到标记附近，已停止。");
            }
            Logger.LogInformation("DESTINATION_ARRIVED {X:F2},{Y:F2}", target.X, target.Y);
            Logger.LogInformation("已到达标记附近。已核验平面坐标；当前仅支持模型中高度明确的地面道路。");
        }
        catch (OperationCanceledException) when (!token.IsCancellationRequested)
        {
            throw new TimeoutException("选点赶路超过3分钟（包括长时间暂停），已停止。");
        }
        finally { Simulation.ReleaseAllKey(); }
    }

    private static Point2f ReadTarget(nint handle, BrowserGameWindow? browser, Point2f cursor, string method)
    {
        if (!IsSameWindow(handle, browser))
            throw new InvalidOperationException("地图窗口或焦点发生变化，请重新选点。");
        using var frame = TaskTriggerDispatcher.GlobalGameCapture?.Capture()
            ?? throw new InvalidOperationException("无法获取地图画面，请重新启动截图器。");
        if (BrowserGameSafety.Classify(frame.Frame) != BrowserScene.Map)
            throw new InvalidOperationException("当前不是大地图界面，请按M打开地图后再选点。");
        using var content = new CaptureContent(frame.Frame.Clone(), 0, 0);
        if (Bv.BigMapIsUnderground(content.CaptureRectArea))
            throw new InvalidOperationException("首版只支持地表选点，请切回地表地图。");
        var map = MapManager.GetMap(MapName, method);
        var rect = map.GetBigMapRect(content.CaptureRectArea.CacheGreyMat);
        const int scale = TeyvatMap.BigMap256ScaleTo2048;
        rect = new Rect(rect.X * scale, rect.Y * scale, rect.Width * scale, rect.Height * scale);
        var imagePoint = DestinationRoutePlanner.ProjectCursor(rect, frame.Frame.Size(), cursor);
        var target = map.ConvertImageCoordinatesToGenshinMapCoordinates(imagePoint);
        return target is { } value && DestinationRoutePlanner.IsFinite(value)
            ? value : throw new InvalidOperationException("未能识别目的地坐标，请调整地图缩放后重试。");
    }

    private static async Task CloseMap(BrowserGameWindow? browser, CancellationToken ct)
    {
        WaitForGameInput(ct);
        using (var frame = TaskTriggerDispatcher.GlobalGameCapture?.Capture())
        {
            if (frame == null || BrowserGameSafety.Classify(frame.Frame) != BrowserScene.Map)
                throw new InvalidOperationException("关闭前地图界面已变化，请重新选点。");
        }
        Simulation.SendInput.Keyboard.KeyPress(User32.VK.VK_M);
        // 用地图键关闭，避开浏览器对 Escape 的捕获；等待动画期间不重复发键。
        for (var i = 0; i < 30; i++)
        {
            await Delay(200, ct);
            using var frame = TaskTriggerDispatcher.GlobalGameCapture?.Capture();
            if (frame == null || BrowserGameSafety.Classify(frame.Frame) != BrowserScene.Main)
                continue;
            browser?.RequireFocusRecovery();
            WaitForGameInput(ct);
            return;
        }
        throw new InvalidOperationException("未能从地图返回游戏画面，已停止。");
    }


    private static Point2f ReadPosition(string method)
    {
        using var frame = CaptureToRectArea();
        if (!Bv.IsInMainUi(frame) || Bv.GetMotionStatus(frame) != MotionStatus.Normal)
            throw new InvalidOperationException("当前不是可确认的地面状态。");
        var imagePosition = Navigation.GetPositionStable(frame, MapName, method);
        return MapManager.GetMap(MapName, method).ConvertImageCoordinatesToGenshinMapCoordinates(imagePosition)
            ?? throw new InvalidOperationException("无法识别当前位置，已停止。");
    }

    private static bool IsSameWindow(nint handle, BrowserGameWindow? browser) =>
        TaskContext.Instance().IsInitialized && TaskContext.Instance().GameHandle == handle
        && BrowserGameWindow.Current == browser && SystemControl.IsGenshinImpactActive();

    private static Point2f GetCursor(nint handle, BrowserGameWindow? browser)
    {
        if (browser != null) return browser.GetCursorPositionInGame();
        var previous = SetThreadDpiAwarenessContext(-4);
        try
        {
            if (!User32.GetCursorPos(out var point))
                throw new InvalidOperationException("无法读取鼠标位置。");
            POINT origin = default;
            if (!User32.ClientToScreen(handle, ref origin))
                throw new InvalidOperationException("无法确定本地原神窗口坐标。");
            return new Point2f(point.X - origin.X, point.Y - origin.Y);
        }
        finally { SetThreadDpiAwarenessContext(previous); }
    }

    [DllImport("user32.dll")]
    private static extern nint SetThreadDpiAwarenessContext(nint context);
}
