using BetterGenshinImpact.GameTask;
using Fischless.WindowsInput;
using Vanara.PInvoke;

namespace BetterGenshinImpact.UnitTest.GameTaskTests;

public class BrowserGameWindowTests
{
    [Theory]
    [InlineData("https://ys.mihoyo.com/cloud/#/", true)]
    [InlineData("https://ys.mihoyo.com/cloud/?autobegin=1", true)]
    [InlineData("https://YS.MIHOYO.COM/cloud/", true)]
    [InlineData("http://ys.mihoyo.com/cloud/", false)]
    [InlineData("https://ys.mihoyo.com.evil.example/cloud/", false)]
    [InlineData("https://user@ys.mihoyo.com/cloud/", false)]
    [InlineData("https://ys.mihoyo.com:8443/cloud/", false)]
    [InlineData("https://ys.mihoyo.com/cloud-other/", false)]
    [InlineData("https://ys.mihoyo.com/", false)]
    [InlineData(null, false)]
    public void OnlyAcceptsOfficialCloudGameUrl(string? url, bool expected)
    {
        Assert.Equal(expected, BrowserGameWindow.IsCloudGameUrl(url));
    }


}

public class PressedInputStateTests
{
    private static User32.INPUT Key(bool release = false) => new()
    {
        type = User32.INPUTTYPE.INPUT_KEYBOARD,
        ki = new User32.KEYBDINPUT { wVk = 0x57, wScan = 0x11,
            dwFlags = release ? User32.KEYEVENTF.KEYEVENTF_KEYUP : 0 }
    };

    private static User32.INPUT Mouse(uint flags, int data = 0) => new()
    {
        type = User32.INPUTTYPE.INPUT_MOUSE,
        mi = new User32.MOUSEINPUT { dwFlags = (User32.MOUSEEVENTF)flags, mouseData = data, dx = 42, dy = 17 }
    };

    [Fact]
    public void StopReleasesForwardAndSprintWithoutMovingMouse()
    {
        var state = new PressedInputState();
        state.Record([Key(), Mouse(0x8)]);
        var releases = state.GetReleaseInputs();
        Assert.Equal(2, releases.Length);
        Assert.True(PressedInputState.IsReleaseOnly(releases));
        Assert.Contains(releases, x => x.type == User32.INPUTTYPE.INPUT_KEYBOARD && x.ki.wVk == 0x57);
        Assert.Contains(releases, x => x.type == User32.INPUTTYPE.INPUT_MOUSE
                                      && (uint)x.mi.dwFlags == 0x10 && x.mi.dx == 0 && x.mi.dy == 0);
        state.Record(releases);
        Assert.Empty(state.GetReleaseInputs());
    }

    [Fact]
    public void CompletedClicksAndReleasedKeysAreNotHeld()
    {
        var state = new PressedInputState();
        state.Record([Key(), Key(true), Mouse(0x2), Mouse(0x4)]);
        Assert.Empty(state.GetReleaseInputs());
    }

    [Fact]
    public void SideButtonsRemainDistinct()
    {
        var state = new PressedInputState();
        state.Record([Mouse(0x80, 1), Mouse(0x80, 2), Mouse(0x100, 1)]);
        var release = Assert.Single(state.GetReleaseInputs());
        Assert.Equal(2, release.mi.mouseData);
        Assert.Equal(0x100u, (uint)release.mi.dwFlags);
    }

    [Fact]
    public void DetectsOnlyMatchingKeyboardPressReleasePairs()
    {
        Assert.True(PressedInputState.IsPressReleasePair([Key(), Key(true)]));
        Assert.False(PressedInputState.IsPressReleasePair([Key(true), Key()]));
        Assert.False(PressedInputState.IsPressReleasePair([Key()]));
        var other = Key(true);
        var key = other.ki;
        key.wVk = 0x41;
        other.ki = key;
        Assert.False(PressedInputState.IsPressReleasePair([Key(), other]));
    }

    [Fact]
    public void DetectsClicksWithoutDelayingStandaloneRelease()
    {
        Assert.True(PressedInputState.IsPressReleasePair([Mouse(0x8), Mouse(0x10)]));
        Assert.True(PressedInputState.IsPressReleasePair([Mouse(0x80, 2), Mouse(0x100, 2)]));
        Assert.False(PressedInputState.IsPressReleasePair([Mouse(0x80, 1), Mouse(0x100, 2)]));
        Assert.False(PressedInputState.IsPressReleasePair([Mouse(0x10)]));
    }
    [Fact]
    public void PauseOnlyAllowsReleaseMessages()
    {
        Assert.True(PressedInputState.IsReleaseOnly([Key(true), Mouse(0x10)]));
        Assert.False(PressedInputState.IsReleaseOnly([Key(), Key(true)]));
        Assert.False(PressedInputState.IsReleaseOnly([Mouse(0x11)]));
        Assert.False(PressedInputState.IsReleaseOnly([]));
    }
}