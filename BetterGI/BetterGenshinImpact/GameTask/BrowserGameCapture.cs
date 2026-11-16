using Fischless.GameCapture;
using OpenCvSharp.Extensions;
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using Microsoft.Extensions.Logging;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.Core.Simulator;

namespace BetterGenshinImpact.GameTask;

public sealed class BrowserGameCapture(BrowserGameWindow browser) : IGameCapture
{
    private readonly object _lock = new();
    private Bitmap? _bitmap;
    private Graphics? _graphics;
    private bool _reportedGeometry;
    public bool IsCapturing { get; private set; }

    public void Start(nint handle, Dictionary<string, object>? settings = null)
    {
        lock (_lock)
        {
            Stop();
            if (handle != browser.Handle)
                throw new ArgumentException("云原神捕获窗口与绑定目标不一致。", nameof(handle));
            _bitmap = new Bitmap(BrowserGameWindow.GameWidth, BrowserGameWindow.GameHeight, PixelFormat.Format24bppRgb);
            _graphics = Graphics.FromImage(_bitmap);
            IsCapturing = true;
        }
    }

    public GameCaptureFrame? Capture()
    {
        GameCaptureFrame? result;
        var expectsMotion = Simulation.ExpectsBrowserMotion;
        lock (_lock)
        {
            if (!IsCapturing || !browser.IsActive())
                return null;
            var area = browser.ScreenRect;
            var previousDpi = SetThreadDpiAwarenessContext(-4);
            try
            {
                _graphics!.CopyFromScreen(area.Left, area.Top, 0, 0, _bitmap!.Size, CopyPixelOperation.SourceCopy);
            }
            catch (Win32Exception) { return null; }
            finally { SetThreadDpiAwarenessContext(previousDpi); }
            if (!browser.IsActive())
                return null;
            var mat = BitmapConverter.ToMat(_bitmap!);
            try { browser.Safety.ObserveFrame(mat, expectsMotion); }
            catch { mat.Dispose(); throw; }
            if (!_reportedGeometry)
            {
                TaskControl.Logger.LogInformation("云原神前台截图已就绪 {Width}x{Height}，游戏区域 {Area}", mat.Width, mat.Height, area);
                _reportedGeometry = true;
            }
            result = new GameCaptureFrame(mat, area);
        }
        if (!browser.Safety.Recovering && browser.Safety.Scene is BrowserScene.Unknown or BrowserScene.Menu)
            Simulation.ReleaseAllKey();
        if (browser.Safety.Failure != null)
        {
            result.Dispose();
            Simulation.CancelForBrowserFailure(browser);
            return null;
        }
        return result;
    }

    public void Stop()
    {
        lock (_lock)
        {
            IsCapturing = false;
            _graphics?.Dispose();
            _graphics = null;
            _bitmap?.Dispose();
            _bitmap = null;
        }
    }

    public void Dispose() => Stop();

    [DllImport("user32.dll")]
    private static extern nint SetThreadDpiAwarenessContext(nint context);
}