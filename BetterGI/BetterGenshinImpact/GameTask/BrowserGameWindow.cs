using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Automation;
using Vanara.PInvoke;

namespace BetterGenshinImpact.GameTask;

public sealed class BrowserGameWindow
{
    public const int GameWidth = 1920;
    public const int GameHeight = 1080;
    public static BrowserGameWindow? Current { get; private set; }

    private readonly AutomationElement _document;
    private readonly AutomationElement _gameLayer;
    private readonly RECT _windowRect;
    private readonly string _title;
    private int _focusRecoveryNeeded = 1;
    private nint _imeWindow;
    internal BrowserGameSafety Safety { get; } = new();
    internal BrowserScene SceneBeforeFocusLoss { get; private set; }
    internal bool NeedsFocusRecovery => Volatile.Read(ref _focusRecoveryNeeded) != 0;

    public nint Handle { get; }
    public RECT ScreenRect { get; }

    private BrowserGameWindow(nint handle, AutomationElement document, AutomationElement gameLayer)
    {
        Handle = handle;
        _document = document;
        _gameLayer = gameLayer;
        ScreenRect = ToRect(gameLayer.Current.BoundingRectangle);
        _windowRect = GetPhysicalWindowRect(handle);
        _title = GetTitle(handle);
    }

    public static bool IsCloudGameUrl(string? value)
    {
        return Uri.TryCreate(value, UriKind.Absolute, out var uri)
               && uri.Scheme == Uri.UriSchemeHttps && uri.Port == 443
               && uri.UserInfo.Length == 0
               && uri.Host.Equals("ys.mihoyo.com", StringComparison.OrdinalIgnoreCase)
               && uri.AbsolutePath.StartsWith("/cloud/", StringComparison.Ordinal);
    }

    public static bool IsCandidate(nint handle)
    {
        if (handle == 0 || !GetTitle(handle).StartsWith("云·原神", StringComparison.Ordinal))
            return false;
        using var process = SystemControl.GetProcessByHandle(handle);
        return process != null && process.SessionId == Process.GetCurrentProcess().SessionId
               && (process.ProcessName.Equals("chrome", StringComparison.OrdinalIgnoreCase)
                   || process.ProcessName.Equals("msedge", StringComparison.OrdinalIgnoreCase));
    }

    public static nint Find()
    {
        nint found = 0;
        User32.EnumWindows((handle, _) =>
        {
            if (User32.IsWindowVisible(handle) && IsCandidate((nint)handle))
            {
                found = (nint)handle;
                return false;
            }
            return true;
        }, 0);
        return found;
    }

    public static void Bind(nint handle) => Current = IsCandidate(handle) ? Create(handle) : null;
    public static void Unbind()
    {
        Current?.RestoreKeyboardInput();
        Current?.Safety.Dispose();
        Current = null;
    }

    public static BrowserGameWindow Create(nint handle)
    {
        var root = AutomationElement.FromHandle(handle);
        AutomationElement? document = null, layer = null;
        // Chrome 可能同时暴露其他标签页的 Document，不能直接绑定第一个。
        foreach (AutomationElement candidate in root.FindAll(TreeScope.Descendants,
                     new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Document)))
        {
            if (candidate.Current.IsOffscreen || !IsCloudGameUrl(ReadUrl(candidate))) continue;
            var gameLayer = candidate.FindFirst(TreeScope.Descendants,
                new PropertyCondition(AutomationElement.ClassNameProperty, "game-player__event-layer"));
            if (gameLayer == null) continue;
            if (document != null)
                throw new InvalidOperationException("检测到多个云原神游戏页面，请只保留一个游戏页后重试。");
            document = candidate;
            layer = gameLayer;
        }
        if (document == null || layer == null)
            throw new InvalidOperationException("请在 https://ys.mihoyo.com/cloud/ 进入游戏画面，再启动截图器。");

        // 固定物理像素视口，让现有 1080P 识图和鼠标坐标共用同一画面。
        for (var attempt = 0; attempt < 4; attempt++)
        {
            var viewport = document.Current.BoundingRectangle;
            if (viewport.Width == GameWidth && viewport.Height == GameHeight)
                break;
            if (attempt == 0)
            {
                User32.ShowWindow(handle, ShowWindowCommand.SW_RESTORE);
                Thread.Sleep(150);
                viewport = document.Current.BoundingRectangle;
            }
            var window = GetPhysicalWindowRect(handle);
            var width = window.Width + GameWidth - (int)Math.Round(viewport.Width);
            var height = window.Height + GameHeight - (int)Math.Round(viewport.Height);
            var monitor = System.Windows.Forms.Screen.FromHandle(handle).Bounds;
            if (width > monitor.Width || height > monitor.Height)
                throw new InvalidOperationException("屏幕无法容纳 1080P 网页视口，请先将浏览器全屏，再启动截图器。");
            var left = Math.Clamp(window.Left, monitor.Left, monitor.Right - width);
            var top = Math.Clamp(window.Top, monitor.Top, monitor.Bottom - height);
            var previousDpi = SetThreadDpiAwarenessContext(-4);
            try
            {
                if (!SetWindowPos(handle, 0, left, top, width, height, 0x14))
                    throw new InvalidOperationException("调整云原神浏览器窗口失败。");
            }
            finally { SetThreadDpiAwarenessContext(previousDpi); }
            Thread.Sleep(200);
        }
        var gameRect = layer.Current.BoundingRectangle;
        if (gameRect.Width != GameWidth || gameRect.Height != GameHeight
            || gameRect != document.Current.BoundingRectangle)
            throw new InvalidOperationException("云原神游戏视口未能校准为 1920x1080，请关闭浏览器分屏或侧边栏后重试。");
        layer.SetFocus();
        return new BrowserGameWindow(handle, document, layer);
    }

    public bool HasStableGeometry()
    {
        try
        {
            return User32.IsWindow(Handle) && !User32.IsIconic(Handle)
                   && GetPhysicalWindowRect(Handle) == _windowRect
                   && ToRect(_document.Current.BoundingRectangle) == ScreenRect
                   && ToRect(_gameLayer.Current.BoundingRectangle) == ScreenRect;
        }
        catch (ElementNotAvailableException) { return false; }
        catch (InvalidOperationException) { return false; }
    }

    public bool HasForegroundPage()
    {
        try
        {
            var active = (nint)User32.GetForegroundWindow() == Handle && GetTitle(Handle) == _title
                   && !_document.Current.IsOffscreen && IsCloudGameUrl(ReadUrl(_document));
            if (!active) RequireFocusRecovery();
            return active;
        }
        catch (ElementNotAvailableException) { return false; }
        catch (InvalidOperationException) { return false; }
    }

    internal void RequireFocusRecovery()
    {
        if (Interlocked.Exchange(ref _focusRecoveryNeeded, 1) == 0)
        {
            RestoreKeyboardInput();
            SceneBeforeFocusLoss = Safety.Scene;
            Safety.ResetObservation();
        }
    }

    internal void PrepareForTask()
    {
        Safety.BeginTask();
        SceneBeforeFocusLoss = BrowserScene.Unknown;
        Interlocked.Exchange(ref _focusRecoveryNeeded, 1);
    }

    internal void CompleteFocusRecovery() => Interlocked.Exchange(ref _focusRecoveryNeeded, 0);

    public bool IsActive()
    {
        try
        {
            var active = HasForegroundPage() && HasStableGeometry()
                   && !_gameLayer.Current.IsOffscreen && _gameLayer.Current.HasKeyboardFocus;
            if (!active) RequireFocusRecovery();
            return active;
        }
        catch (ElementNotAvailableException) { return false; }
        catch (InvalidOperationException) { return false; }
    }

    internal void PrepareKeyboardInput()
    {
        var thread = GetWindowThreadProcessId(Handle, out _);
        var info = new GuiThreadInfo { Size = Marshal.SizeOf<GuiThreadInfo>() };
        if (!GetGUIThreadInfo(thread, ref info))
            throw new InvalidOperationException("无法确认浏览器键盘输入窗口。");
        var ime = ImmGetDefaultIMEWnd(info.Focus);
        if (ime == 0) return;
        if (!TryImeMessage(ime, 5, 0, out var open))
            throw new InvalidOperationException("无法读取游戏窗口输入法状态，请切换英文输入后重试。");
        if (open == 0) return;
        _imeWindow = ime;
        if (!TryImeMessage(ime, 6, 0, out _) || !TryImeMessage(ime, 5, 0, out open) || open != 0)
            throw new InvalidOperationException("游戏窗口输入法未切换为直接按键模式，请切换英文输入后重试。");
    }

    internal void RestoreKeyboardInput()
    {
        var ime = Interlocked.Exchange(ref _imeWindow, 0);
        if (ime != 0 && User32.IsWindow(ime) && TryImeMessage(ime, 5, 0, out var open) && open == 0)
            TryImeMessage(ime, 6, 1, out _);
    }

    private static bool TryImeMessage(nint window, nuint command, nint value, out nuint result) =>
        SendMessageTimeout(window, 0x283, command, value, 2, 200, out result) != 0;

    [StructLayout(LayoutKind.Sequential)]
    private struct GuiThreadInfo
    {
        public int Size;
        public uint Flags;
        public nint Active, Focus, Capture, MenuOwner, MoveSize, Caret;
        public RECT CaretRect;
    }

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(nint window, out uint process);
    [DllImport("user32.dll")]
    private static extern bool GetGUIThreadInfo(uint thread, ref GuiThreadInfo info);
    [DllImport("imm32.dll")]
    private static extern nint ImmGetDefaultIMEWnd(nint window);
    [DllImport("user32.dll")]
    private static extern nint SendMessageTimeout(nint window, uint message, nuint command,
        nint value, uint flags, uint timeout, out nuint result);

    internal OpenCvSharp.Point2f GetCursorPositionInGame()
    {
        var previousDpi = SetThreadDpiAwarenessContext(-4);
        try
        {
            if (!User32.GetCursorPos(out var point))
                throw new InvalidOperationException("无法读取鼠标位置。");
            return new OpenCvSharp.Point2f(point.X - ScreenRect.Left, point.Y - ScreenRect.Top);
        }
        finally { SetThreadDpiAwarenessContext(previousDpi); }
    }

    public POINT GetClientOrigin()
    {
        var previousDpi = SetThreadDpiAwarenessContext(-4);
        try
        {
            POINT point = default;
            User32.ClientToScreen(Handle, ref point);
            return point;
        }
        finally { SetThreadDpiAwarenessContext(previousDpi); }
    }

    private static RECT GetPhysicalWindowRect(nint handle)
    {
        var previousDpi = SetThreadDpiAwarenessContext(-4);
        try { User32.GetWindowRect(handle, out var rect); return rect; }
        finally { SetThreadDpiAwarenessContext(previousDpi); }
    }

    private static RECT ToRect(System.Windows.Rect rect) => new(
        (int)Math.Round(rect.Left), (int)Math.Round(rect.Top),
        (int)Math.Round(rect.Right), (int)Math.Round(rect.Bottom));

    private static string ReadUrl(AutomationElement document) =>
        document.TryGetCurrentPattern(ValuePattern.Pattern, out var pattern)
            ? ((ValuePattern)pattern).Current.Value : string.Empty;

    private static string GetTitle(nint handle)
    {
        var text = new StringBuilder(512);
        User32.GetWindowText(handle, text, text.Capacity);
        return text.ToString();
    }

    [DllImport("user32.dll")]
    private static extern nint SetThreadDpiAwarenessContext(nint context);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SetWindowPos(nint handle, nint after, int x, int y, int width, int height, uint flags);
}