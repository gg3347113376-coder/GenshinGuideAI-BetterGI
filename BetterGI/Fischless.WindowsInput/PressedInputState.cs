using Vanara.PInvoke;

namespace Fischless.WindowsInput;

public sealed class PressedInputState
{
    private readonly Dictionary<(ushort Key, ushort Scan, uint Flags), User32.INPUT> _keys = new();
    private readonly Dictionary<int, User32.INPUT> _buttons = new();
    private static readonly (uint Down, uint Up, int Button)[] MouseButtons =
        [(0x2, 0x4, 1), (0x8, 0x10, 2), (0x20, 0x40, 3), (0x80, 0x100, 4)];

    public static bool IsReleaseOnly(User32.INPUT[] inputs) => inputs.Length > 0 && inputs.All(input =>
        input.type == User32.INPUTTYPE.INPUT_KEYBOARD
            ? (input.ki.dwFlags & User32.KEYEVENTF.KEYEVENTF_KEYUP) != 0
            : input.type == User32.INPUTTYPE.INPUT_MOUSE && (uint)input.mi.dwFlags != 0
              && ((uint)input.mi.dwFlags & ~0x154u) == 0);

    public static bool IsPressReleasePair(User32.INPUT[] inputs)
    {
        if (inputs.Length != 2 || !IsReleaseOnly([inputs[1]]))
            return false;
        var down = inputs[0];
        var up = inputs[1];
        if (down.type == User32.INPUTTYPE.INPUT_KEYBOARD && up.type == down.type)
            return (down.ki.dwFlags & User32.KEYEVENTF.KEYEVENTF_KEYUP) == 0
                   && down.ki.wVk == up.ki.wVk && down.ki.wScan == up.ki.wScan
                   && (down.ki.dwFlags | User32.KEYEVENTF.KEYEVENTF_KEYUP) == up.ki.dwFlags;
        return down.type == User32.INPUTTYPE.INPUT_MOUSE && up.type == down.type
               && (((uint)down.mi.dwFlags & 0xAAu) << 1) == (uint)up.mi.dwFlags
               && down.mi.mouseData == up.mi.mouseData;
    }

    public void Record(User32.INPUT[] inputs)
    {
        foreach (var input in inputs)
        {
            if (input.type == User32.INPUTTYPE.INPUT_KEYBOARD)
            {
                var key = (input.ki.wVk, input.ki.wScan, (uint)input.ki.dwFlags & ~2u);
                if ((input.ki.dwFlags & User32.KEYEVENTF.KEYEVENTF_KEYUP) != 0)
                    _keys.Remove(key);
                else
                    _keys[key] = input;
            }
            else if (input.type == User32.INPUTTYPE.INPUT_MOUSE)
            {
                foreach (var (down, up, button) in MouseButtons)
                {
                    var id = button == 4 && input.mi.mouseData == 2 ? 5 : button;
                    if (((uint)input.mi.dwFlags & down) != 0) _buttons[id] = input;
                    if (((uint)input.mi.dwFlags & up) != 0) _buttons.Remove(id);
                }
            }
        }
    }

    public bool HasHeldInput => _keys.Count > 0 || _buttons.Count > 0;

    public User32.INPUT[] GetPressedInputs() => _keys.Values.Concat(_buttons.Values).ToArray();

    public User32.INPUT[] GetReleaseInputs()
    {
        var releases = new List<User32.INPUT>();
        foreach (var pressed in _keys.Values)
        {
            var release = pressed;
            var keyboard = release.ki;
            keyboard.dwFlags |= User32.KEYEVENTF.KEYEVENTF_KEYUP;
            release.ki = keyboard;
            releases.Add(release);
        }
        foreach (var entry in _buttons)
        {
            var release = entry.Value;
            var mouse = release.mi;
            mouse.dx = 0;
            mouse.dy = 0;
            mouse.dwFlags = (User32.MOUSEEVENTF)(entry.Key switch
            {
                1 => 0x4, 2 => 0x10, 3 => 0x40, _ => 0x100
            });
            release.mi = mouse;
            releases.Add(release);
        }
        return releases.ToArray();
    }
}