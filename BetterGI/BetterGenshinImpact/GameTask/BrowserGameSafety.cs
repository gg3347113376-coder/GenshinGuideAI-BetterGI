using System;
using BetterGenshinImpact.Core.Recognition;
using OpenCvSharp;
using BetterGenshinImpact.GameTask.Common.BgiVision;
using BetterGenshinImpact.GameTask.Common.Element.Assets;

namespace BetterGenshinImpact.GameTask;

internal enum BrowserScene { Unknown, Main, Map, Menu }

internal sealed class BrowserGameSafety : IDisposable
{
    private readonly object _sync = new();
    private Mat? _previous;
    private long _sampleAt;
    private long? _unknownSince;
    private long? _motionSince;
    private BrowserScene _scene;
    private string? _failure;
    private bool _monitoring;
    private bool _failureReported;
    private bool _recovering;
    private bool _teleporting;
    private bool _observedLoading;

    public BrowserScene Scene { get { lock (_sync) return _scene; } }
    public string? Failure { get { lock (_sync) return _failure; } }
    public bool ObservedLoading { get { lock (_sync) return _observedLoading; } }
    public bool Teleporting
    {
        get { lock (_sync) return _teleporting; }
        set { lock (_sync) { if (value && !_teleporting) _observedLoading = false; _teleporting = value; } }
    }
    public bool Recovering { get { lock (_sync) return _recovering; } set { lock (_sync) { _recovering = value; ResetObservation(); } } }
    public bool CanSendInput { get { lock (_sync) return _failure == null && _scene is BrowserScene.Main or BrowserScene.Map; } }

    public void BeginTask()
    {
        lock (_sync)
        {
            _monitoring = true;
            _failure = null;
            _failureReported = false;
            _teleporting = false;
            ResetObservation();
        }
    }

    public void EndTask()
    {
        lock (_sync)
        {
            _monitoring = false;
            _teleporting = false;
            ResetObservation();
        }
    }

    public void ResetObservation()
    {
        lock (_sync)
        {
            _unknownSince = null;
            _motionSince = null;
            _sampleAt = 0;
            _previous?.Dispose();
            _previous = null;
        }
    }

    public bool TryReportFailure()
    {
        lock (_sync)
        {
            if (_failure == null || _failureReported) return false;
            _failureReported = true;
            return true;
        }
    }

    public void Fail(string reason)
    {
        lock (_sync) _failure ??= reason;
    }

    // Only demand visual progress while our own movement input is active.
    // An idle scene or a stationary map is allowed to remain unchanged.
    internal void Observe(BrowserScene scene, bool changed, bool expectsMotion, long now)
    {
        lock (_sync)
        {
            _scene = scene;
            if (_teleporting && scene == BrowserScene.Unknown) _observedLoading = true;
            if (!_monitoring || _recovering || _failure != null)
                return;
            if (scene is BrowserScene.Unknown or BrowserScene.Menu)
            {
                _motionSince = null;
                _unknownSince ??= now;
                if (!_teleporting && now - _unknownSince >= 2000)
                    _failure = "unknown_ui: 无法确认当前游戏界面，已停止任务，请手动返回游戏后重新启动。";
            }
            else
            {
                _unknownSince = null;
                if (scene == BrowserScene.Main && expectsMotion)
                {
                    if (changed || _motionSince == null) _motionSince = now;
                    if (now - _motionSince >= 2500)
                        _failure = "stale_frame: 持续操作时画面超过 2.5 秒没有有效更新，已停止任务，请检查云游戏连接。";
                }
                else
                    _motionSince = null;
            }
        }
    }

    internal static BrowserScene Classify(Mat frame)
    {
        using var content = new CaptureContent(frame.Clone(), 0, 0);
        var area = content.CaptureRectArea;
        using var back = area.Find(ElementRecognition.GetChatBackButton());
        if (back.IsExist()) return BrowserScene.Menu;
        if (Bv.IsInMainUi(area)) return BrowserScene.Main;
        // 地图区划面板会移动关闭按钮；用缩放条识别，菜单返回按钮在上方优先排除。
        using var scale = area.Find(RecognitionAssets.Get("QuickTeleport", "MapScaleButton", area));
        return scale.IsExist() ? BrowserScene.Map : BrowserScene.Unknown;
    }

    public void ObserveFrame(Mat frame, bool expectsMotion)
    {
        lock (_sync)
        {
            var now = Environment.TickCount64;
            if (now - _sampleAt < 125) return;
            _sampleAt = now;
            var scene = Classify(frame);
            // Exclude the HUD, cursor and the cloud overlay in the corners.
            using var center = new Mat(frame, new Rect(frame.Width / 5, frame.Height / 5,
                frame.Width * 3 / 5, frame.Height * 3 / 5));
            using var small = new Mat();
            Cv2.Resize(center, small, new Size(160, 90), 0, 0, InterpolationFlags.Area);
            var changed = _previous == null || Cv2.Norm(small, _previous, NormTypes.L1) / (small.Total() * small.Channels()) > 0.2;
            _previous?.Dispose();
            _previous = small.Clone();
            Observe(scene, changed, expectsMotion, now);
        }
    }

    public void Dispose() => ResetObservation();
}
