using System;
using System.Threading;
using BetterGenshinImpact.Core.Script;
using BetterGenshinImpact.GameTask.Common;
using Fischless.WindowsInput;
using Vanara.PInvoke;

namespace BetterGenshinImpact.GameTask.AutoPathing;

// 仅在选点任务期间启用，普通 BetterGI 任务的输入行为保持原样。
internal sealed class NativeDestinationInput : IDisposable
{
    internal static volatile NativeDestinationInput? Current;
    private readonly object _sync = new();
    private readonly PressedInputState _pressed = new();
    private readonly BrowserGameSafety _safety = new();
    internal BrowserGameSafety Safety => _safety;
    private readonly CancellationToken _token;
    private readonly nint _handle;
    private readonly RECT _rect;
    private readonly Timer _watchdog;
    private Action<User32.INPUT[]>? _send;
    private volatile bool _needsValidation = true;
    private bool _disposed;

    internal NativeDestinationInput(nint handle, CancellationToken token)
    {
        _handle = handle;
        _token = token;
        _rect = SystemControl.GetCaptureRect(handle);
        _safety.BeginTask();
        Current = this;
        _watchdog = new Timer(_ => Watch(), null, 0, 100);
    }

    private bool IsActive => User32.GetForegroundWindow() == _handle && !User32.IsIconic(_handle);
    private bool HasGeometry => User32.IsWindow(_handle)
        && SystemControl.GetCaptureRect(_handle) == _rect
        && TaskContext.Instance().GameHandle == _handle;

    private void Watch()
    {
        try
        {
            lock (_sync)
            {
                if (_disposed) return;
                if (!HasGeometry)
                {
                    _safety.Fail("本地原神窗口位置或尺寸发生变化，请重新启动选点任务。");
                    Release();
                }
                if (_token.IsCancellationRequested || RunnerContext.Instance.IsSuspend || !IsActive)
                {
                    _needsValidation = true;
                    Release();
                }
            }
        }
        catch (Exception ex)
        {
            _safety.Fail("本地输入监控失败：" + ex.Message);
            CancellationContext.Instance.Cancel();
        }
    }

    internal void Wait(CancellationToken token)
    {
        while (true)
        {
            token.ThrowIfCancellationRequested();
            _token.ThrowIfCancellationRequested();
            if (!HasGeometry) throw new InvalidOperationException("本地原神窗口位置或尺寸发生变化，请重新启动选点任务。");
            if (_safety.Failure is { } failure) throw new InvalidOperationException(failure);
            if (!IsActive || RunnerContext.Instance.IsSuspend)
            {
                Release();
                _needsValidation = true;
                if (System.Windows.Application.Current?.Dispatcher.CheckAccess() == true)
                    throw new InvalidOperationException("本地原神没有焦点或任务已暂停，未发送操作。");
                TaskControl.TrySuspend(token);
                token.WaitHandle.WaitOne(100);
                continue;
            }
            if (_needsValidation)
            {
                _safety.ResetObservation();
                _needsValidation = false;
                using var first = TaskTriggerDispatcher.GlobalGameCapture?.Capture();
                if (first == null) throw new InvalidOperationException("无法获取本地游戏画面。");
                var scene = BrowserGameSafety.Classify(first.Frame);
                token.WaitHandle.WaitOne(150);
                token.ThrowIfCancellationRequested();
                using var second = TaskTriggerDispatcher.GlobalGameCapture?.Capture();
                if (second == null || scene is not (BrowserScene.Main or BrowserScene.Map)
                    || BrowserGameSafety.Classify(second.Frame) != scene)
                    throw new InvalidOperationException("恢复前无法确认稳定游戏界面，请回到游戏后重新选点。");
                if (!IsActive || RunnerContext.Instance.IsSuspend) continue;
            }
            using var frame = TaskTriggerDispatcher.GlobalGameCapture?.Capture();
            if (frame == null) throw new InvalidOperationException("本地游戏截图不可用，已停止。");
            bool moving;
            lock (_sync) moving = _pressed.HasHeldInput;
            _safety.ObserveFrame(frame.Frame, moving);
            if (_safety.Failure is { } reason) throw new InvalidOperationException(reason);
            if (_safety.CanSendInput) return;
            Release();
            token.WaitHandle.WaitOne(100);
        }
    }

    internal void Dispatch(User32.INPUT[] inputs, Action<User32.INPUT[]> send)
    {
        if (PressedInputState.IsReleaseOnly(inputs))
        {
            lock (_sync) { send(inputs); _pressed.Record(inputs); }
            return;
        }
        while (true)
        {
            Wait(_token);
            lock (_sync)
            {
                _token.ThrowIfCancellationRequested();
                if (_disposed) throw new OperationCanceledException();
                if (!HasGeometry) throw new InvalidOperationException("原神窗口发生变化，未发送操作。");
                if (!IsActive || RunnerContext.Instance.IsSuspend) continue;
                _send = send;
                send(inputs);
                _pressed.Record(inputs);
                return;
            }
        }
    }

    internal User32.INPUT[] HeldInputs()
    {
        lock (_sync) return _pressed.GetPressedInputs();
    }

    internal void Restore(User32.INPUT[] held)
    {
        Action<User32.INPUT[]>? send;
        lock (_sync)
        {
            if (_pressed.HasHeldInput || held.Length == 0) return;
            send = _send;
        }
        if (send != null) Dispatch(held, send);
    }

    internal void Release()
    {
        lock (_sync)
        {
            var releases = _pressed.GetReleaseInputs();
            if (releases.Length == 0) return;
            _send!(releases);
            _pressed.Record(releases);
        }
    }

    public void Dispose()
    {
        _watchdog.Dispose();
        lock (_sync)
        {
            _disposed = true;
            Release();
            if (Current == this) Current = null;
            _safety.Dispose();
        }
    }
}
