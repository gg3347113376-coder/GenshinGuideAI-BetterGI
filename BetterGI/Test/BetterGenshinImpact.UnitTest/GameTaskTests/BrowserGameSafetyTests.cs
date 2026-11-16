using BetterGenshinImpact.GameTask;

namespace BetterGenshinImpact.UnitTest.GameTaskTests;

public class BrowserGameSafetyTests
{
    [Fact]
    public void UnknownFrameNeverAuthorizesInputAndEventuallyStops()
    {
        using var state = new BrowserGameSafety();
        state.BeginTask();
        state.Observe(BrowserScene.Unknown, true, false, 0);
        Assert.False(state.CanSendInput);
        state.Observe(BrowserScene.Unknown, true, false, 1999);
        Assert.Null(state.Failure);
        state.Observe(BrowserScene.Unknown, true, false, 2000);
        Assert.Contains("unknown_ui", state.Failure);
    }

    [Fact]
    public void OrdinaryMapTransitionDoesNotTripUnknownTimeout()
    {
        using var state = new BrowserGameSafety();
        state.BeginTask();
        state.Observe(BrowserScene.Main, true, false, 0);
        state.Observe(BrowserScene.Unknown, true, false, 100);
        state.Observe(BrowserScene.Map, true, false, 600);
        state.Observe(BrowserScene.Map, false, false, 20000);
        Assert.Null(state.Failure);
        Assert.True(state.CanSendInput);
    }

    [Fact]
    public void LoadingPermitsWaitingButNeverBlindInput()
    {
        using var state = new BrowserGameSafety();
        state.BeginTask();
        state.Teleporting = true;
        state.Observe(BrowserScene.Unknown, false, false, 0);
        state.Observe(BrowserScene.Unknown, false, false, 50000);
        Assert.Null(state.Failure);
        Assert.False(state.CanSendInput);
        Assert.True(state.ObservedLoading);
        state.Teleporting = false;
        state.Observe(BrowserScene.Main, true, false, 51000);
        Assert.True(state.CanSendInput);
    }

    [Theory]
    [InlineData(BrowserScene.Main)]
    [InlineData(BrowserScene.Map)]
    internal void IdleSceneMayRemainStill(BrowserScene scene)
    {
        using var state = new BrowserGameSafety();
        state.BeginTask();
        state.Observe(scene, false, false, 0);
        state.Observe(scene, false, false, 60000);
        Assert.Null(state.Failure);
    }

    [Fact]
    public void FrozenVideoDuringMovementStopsWithinBudget()
    {
        using var state = new BrowserGameSafety();
        state.BeginTask();
        state.Observe(BrowserScene.Main, true, true, 0);
        state.Observe(BrowserScene.Main, false, true, 2499);
        Assert.Null(state.Failure);
        state.Observe(BrowserScene.Main, false, true, 2500);
        Assert.Contains("stale_frame", state.Failure);
        Assert.False(state.CanSendInput);
    }

    [Fact]
    public void UpdatingVideoDoesNotTripMotionWatchdog()
    {
        using var state = new BrowserGameSafety();
        state.BeginTask();
        for (var t = 0; t < 60000; t += 200)
            state.Observe(BrowserScene.Main, t % 1000 == 0, true, t);
        Assert.Null(state.Failure);
    }

    [Fact]
    public void FocusLossAndPauseDiscardElapsedObservationTime()
    {
        using var state = new BrowserGameSafety();
        state.BeginTask();
        state.Observe(BrowserScene.Main, false, true, 0);
        state.ResetObservation();
        state.Observe(BrowserScene.Main, false, true, 60000);
        Assert.Null(state.Failure);
    }

    [Fact]
    public void FailureStaysLatchedUntilExplicitNewTask()
    {
        using var state = new BrowserGameSafety();
        state.BeginTask();
        state.Fail("stale_frame");
        state.Observe(BrowserScene.Main, true, true, 10000);
        state.EndTask();
        Assert.False(state.CanSendInput);
        state.BeginTask();
        state.Observe(BrowserScene.Main, true, false, 10100);
        Assert.Null(state.Failure);
        Assert.True(state.CanSendInput);
    }

    [Fact]
    public void RecoveryDoesNotAuthorizeUnknownUiOrEraseFailure()
    {
        using var state = new BrowserGameSafety();
        state.BeginTask();
        state.Recovering = true;
        state.Observe(BrowserScene.Menu, false, false, 0);
        state.Observe(BrowserScene.Menu, false, false, 10000);
        Assert.Null(state.Failure);
        Assert.False(state.CanSendInput);
        state.Fail("focus_unverified");
        state.Recovering = false;
        Assert.Contains("focus_unverified", state.Failure);
    }
}
