using Fischless.WindowsInput;
using BetterGenshinImpact.GameTask.AutoPathing;
using System;
using System.Threading;
using BetterGenshinImpact.GameTask.Common.Map;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.Core.Script;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.AutoGeniusInvokation.Exception;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Common.Element.Assets;
using BetterGenshinImpact.GameTask.Common.BgiVision;
using BetterGenshinImpact.Core.Script.Dependence;
using Microsoft.Extensions.Logging;
using Vanara.PInvoke;

namespace BetterGenshinImpact.Core.Simulator;

public class Simulation
{
    public static InputSimulator SendInput { get; } = new();
    public static MouseEventSimulator MouseEvent { get; } = new();
    private static readonly object BrowserInputLock = new();
    private static readonly object BrowserRecoveryLock = new();
    [ThreadStatic] private static bool _recoveringBrowserFocus;
    private static readonly PressedInputState BrowserPressedInputs = new();
    private static Action<User32.INPUT[]>? _browserNativeDispatch;
    private static long _lastBrowserActionAt;
    internal static bool ExpectsBrowserMotion
    {
        get { lock (BrowserInputLock) return BrowserPressedInputs.HasHeldInput || Environment.TickCount64 - _lastBrowserActionAt < 2000; }
    }

    internal static User32.INPUT[] GetHeldBrowserInputs()
    {
        if (NativeDestinationInput.Current is { } native) return native.HeldInputs();
        lock (BrowserInputLock) return BrowserPressedInputs.GetPressedInputs();
    }

    internal static void RestoreBrowserInputs(User32.INPUT[] inputs)
    {
        if (NativeDestinationInput.Current is { } native) { native.Restore(inputs); return; }
        lock (BrowserInputLock)
        {
            if (BrowserPressedInputs.HasHeldInput || inputs.Length == 0) return;
        }
        if (_browserNativeDispatch != null)
            DispatchGameInput(inputs, _browserNativeDispatch);
    }

    internal static void StopForBrowserFailure(BrowserGameWindow browser)
    {
        var reason = browser.Safety.Failure;
        if (reason == null) return;
        CancelForBrowserFailure(browser);
        throw new NormalEndException("WEB_GUARD_STOP " + reason);
    }

    internal static void CancelForBrowserFailure(BrowserGameWindow browser)
    {
        if (browser.Safety.TryReportFailure())
            TaskControl.Logger.LogWarning("WEB_GUARD_STOP {Reason}", browser.Safety.Failure);
        CancellationContext.Instance.Cancel();
        ReleaseAllKey();
    }

    static Simulation() => InputSimulator.DispatchHandler = DispatchGameInput;

    public static PostMessageSimulator PostMessage(IntPtr hWnd) => new(hWnd);

    private static void DispatchGameInput(User32.INPUT[] inputs, Action<User32.INPUT[]> dispatch)
    {
        if (NativeDestinationInput.Current is { } native) { native.Dispatch(inputs, dispatch); return; }
        var browser = BrowserGameWindow.Current;
        if (browser == null)
        {
            dispatch(inputs);
            return;
        }
        if (PressedInputState.IsReleaseOnly(inputs))
        {
            lock (BrowserInputLock)
            {
                dispatch(inputs);
                BrowserPressedInputs.Record(inputs);
            }
            return;
        }

        var runningTask = TaskControl.TaskSemaphore.CurrentCount == 0;
        var token = runningTask ? CancellationContext.Instance.Cts.Token : CancellationToken.None;
        var unavailableSince = Environment.TickCount64;
        while (true)
        {
            token.ThrowIfCancellationRequested();
            if (!runningTask || System.Windows.Application.Current?.Dispatcher.CheckAccess() == true)
            {
                if (RunnerContext.Instance.IsSuspend || !browser.IsActive())
                    throw new NormalEndException("云原神网页没有游戏焦点，未发送键鼠操作。");
            }
            else
            {
                TaskControl.WaitForGameInput(token);
            }
            if (!_recoveringBrowserFocus)
            {
                using var frame = TaskTriggerDispatcher.GlobalGameCapture?.Capture();
                StopForBrowserFailure(browser);
                if (frame == null || !browser.Safety.CanSendInput)
                {
                    ReleaseAllKey();
                    if (!runningTask || System.Windows.Application.Current?.Dispatcher.CheckAccess() == true)
                        throw new NormalEndException("未确认网页游戏画面，未发送输入。");
                    if (frame == null && Environment.TickCount64 - unavailableSince > 2000)
                    {
                        browser.Safety.Fail("capture_unavailable: 无法取得有效游戏画面，已停止任务。");
                        StopForBrowserFailure(browser);
                    }
                    token.WaitHandle.WaitOne(100);
                    continue;
                }
            }
            lock (BrowserInputLock)
            {
                token.ThrowIfCancellationRequested();
                if (BrowserGameWindow.Current != browser)
                    throw new NormalEndException("云原神网页绑定已经结束。");
                if (RunnerContext.Instance.IsSuspend || !browser.IsActive())
                    continue;
                _browserNativeDispatch = dispatch;
                _lastBrowserActionAt = Environment.TickCount64;
                if (PressedInputState.IsPressReleasePair(inputs))
                {
                    User32.INPUT[] down = [inputs[0]], up = [inputs[1]];
                    dispatch(down);
                    BrowserPressedInputs.Record(down);
                    try { token.WaitHandle.WaitOne(80); }
                    finally
                    {
                        dispatch(up);
                        BrowserPressedInputs.Record(up);
                    }
                    token.ThrowIfCancellationRequested();
                    return;
                }
                dispatch(inputs);
                BrowserPressedInputs.Record(inputs);
                return;
            }
        }
    }

    internal static void RecoverBrowserFocus(CancellationToken token)
    {
        if (_recoveringBrowserFocus || BrowserGameWindow.Current == null)
            return;
        lock (BrowserRecoveryLock)
        {
            var browser = BrowserGameWindow.Current;
            if (browser == null || !browser.NeedsFocusRecovery)
                return;
            StopForBrowserFailure(browser);
            _recoveringBrowserFocus = true;
            browser.Safety.Recovering = true;
            ReleaseAllKey();
            var recovered = false;
            try
            {
                browser.PrepareKeyboardInput();
                TaskControl.Sleep(400, token);
                var started = Environment.TickCount64;
                var menuAttempts = 0;
                while (Environment.TickCount64 - started < (browser.Safety.Teleporting ? 60000 : 5000))
                {
                    token.ThrowIfCancellationRequested();
                    using var frame = TaskTriggerDispatcher.GlobalGameCapture?.Capture();
                    if (frame == null)
                    {
                        TaskControl.Sleep(100, token);
                        continue;
                    }
                    var scene = BrowserGameSafety.Classify(frame.Frame);
                    if (scene == BrowserScene.Map)
                    {
                        // Do not accept a transient menu animation as a map.
                        TaskControl.Sleep(150, token);
                        using var confirmedMap = TaskTriggerDispatcher.GlobalGameCapture?.Capture();
                        if (confirmedMap == null || BrowserGameSafety.Classify(confirmedMap.Frame) != BrowserScene.Map)
                            continue;
                        browser.CompleteFocusRecovery();
                        recovered = true;
                        TaskControl.Logger.LogInformation("WEB_FOCUS_READY map");
                        return;
                    }
                    if (scene == BrowserScene.Menu && menuAttempts++ < 3)
                    {
                        SendInput.Keyboard.KeyPress(User32.VK.VK_ESCAPE);
                        TaskControl.Sleep(500, token);
                        continue;
                    }
                    if (scene == BrowserScene.Main)
                    {
                        GlobalMethod.Click(BrowserGameWindow.GameWidth / 2, BrowserGameWindow.GameHeight / 2);
                        TaskControl.Sleep(250, token);
                        using var before = TaskTriggerDispatcher.GlobalGameCapture?.Capture();
                        if (before == null || BrowserGameSafety.Classify(before.Frame) != BrowserScene.Main)
                            continue;
                        var angle = CameraOrientation.Compute(before.Frame);
                        SendInput.Mouse.MoveMouseBy(80, 0);
                        var responded = false;
                        for (var i = 0; i < 10; i++)
                        {
                            TaskControl.Sleep(100, token);
                            using var after = TaskTriggerDispatcher.GlobalGameCapture?.Capture();
                            if (after == null || BrowserGameSafety.Classify(after.Frame) != BrowserScene.Main)
                                continue;
                            var difference = Math.Abs((CameraOrientation.Compute(after.Frame) - angle + 540) % 360 - 180);
                            if (difference >= 3)
                            {
                                responded = true;
                                break;
                            }
                        }
                        SendInput.Mouse.MoveMouseBy(-80, 0);
                        TaskControl.Sleep(200, token);
                        if (!responded) break;
                        browser.CompleteFocusRecovery();
                        recovered = true;
                        TaskControl.Logger.LogInformation("WEB_FOCUS_READY main camera_verified");
                        if (browser.SceneBeforeFocusLoss == BrowserScene.Map && !browser.Safety.Teleporting)
                            throw new RetryException("焦点恢复后地图已关闭，重新定位传送目标。");
                        return;
                    }
                    // Unknown/loading screens receive no Escape, click or movement.
                    TaskControl.Sleep(100, token);
                }
                browser.Safety.Fail("focus_unverified: 未能确认游戏界面和视角响应，已停止任务，请手动检查画面后重启。");
                StopForBrowserFailure(browser);
            }
            finally
            {
                browser.Safety.Recovering = false;
                _recoveringBrowserFocus = false;
                if (!recovered)
                {
                    ReleaseAllKey();
                    browser.RestoreKeyboardInput();
                }
            }
        }
    }

    public static void ReleaseAllKey()
    {
        if (NativeDestinationInput.Current is { } native) { native.Release(); return; }
        if (BrowserGameWindow.Current != null)
        {
            lock (BrowserInputLock)
            {
                _lastBrowserActionAt = 0;
                var releases = BrowserPressedInputs.GetReleaseInputs();
                if (releases.Length > 0)
                {
                    _browserNativeDispatch!(releases);
                    BrowserPressedInputs.Record(releases);
                }
            }
            return;
        }
        foreach (User32.VK key in Enum.GetValues(typeof(User32.VK)))
        {
            if (IsKeyDown(key))
            {
                TaskControl.Logger.LogDebug($"解除{key}的按下状态.");
                SendInput.Keyboard.KeyUp(key);
            }
        }
        SendInput.Mouse.LeftButtonUp();
        SendInput.Mouse.RightButtonUp();
        SendInput.Mouse.MiddleButtonUp();
    }

    public static bool IsKeyDown(User32.VK key)
    {
        var state = User32.GetAsyncKeyState((int)key);
        return (state & 0x8000) != 0;
    }
}