using BetterGenshinImpact.GameTask.AutoPathing;
using OpenCvSharp;

namespace BetterGenshinImpact.UnitTest.GameTaskTests;

public class MapDestinationTests
{
    [Fact]
    public void OnePixelBigMapQuantizationDoesNotRejectAStationaryTarget()
    {
        // 256 层的一个像素经 8 倍放大、2 倍坐标换算后，会抖动 4 个游戏坐标单位。
        Assert.Equal(new Point2f(102, 200),
            DestinationRoutePlanner.ConfirmTarget(new Point2f(100, 200), new Point2f(104, 200)));
    }

    [Theory]
    [InlineData(108, 200)]
    [InlineData(float.NaN, 200)]
    [InlineData(100, float.PositiveInfinity)]
    public void RejectsMovingOrInvalidMapConfirmation(float x, float y)
    {
        Assert.Throws<InvalidOperationException>(() =>
            DestinationRoutePlanner.ConfirmTarget(new Point2f(100, 200), new Point2f(x, y)));
    }


    [Fact]
    public void CursorProjectionAccountsForMapPanAndZoom()
    {
        var result = DestinationRoutePlanner.ProjectCursor(new Rect(1000, 2000, 900, 500),
            new Size(1920, 1080), new Point2f(960, 540));
        Assert.Equal(new Point2f(1450, 2250), result);
        var zoomed = DestinationRoutePlanner.ProjectCursor(new Rect(1300, 2100, 300, 300),
            new Size(1920, 1080), new Point2f(960, 540));
        Assert.Equal(new Point2f(1450, 2250), zoomed);
    }

    [Theory]
    [InlineData(-1, 540)]
    [InlineData(1920, 540)]
    [InlineData(960, 1080)]
    [InlineData(float.NaN, 540)]
    public void RejectsInvalidCursor(float x, float y) =>
        Assert.Throws<ArgumentException>(() => DestinationRoutePlanner.ProjectCursor(
            new Rect(1000, 2000, 900, 500), new Size(1920, 1080), new Point2f(x, y)));

    [Fact]
    public void RefusesMapUiRegionsAndMissingMapRecognition()
    {
        Assert.False(DestinationRoutePlanner.IsSelectablePoint(new Point2f(80, 100), new Size(1920, 1080)));
        Assert.False(DestinationRoutePlanner.IsSelectablePoint(new Point2f(1700, 500), new Size(1920, 1080)));
        Assert.True(DestinationRoutePlanner.IsSelectablePoint(new Point2f(960, 540), new Size(1920, 1080)));
        Assert.Throws<ArgumentException>(() => DestinationRoutePlanner.ProjectCursor(
            default, new Size(1920, 1080), new Point2f(960, 540)));
    }

    [Fact]
    public void SelectablePointScalesWithNativeGameResolution()
    {
        Assert.True(DestinationRoutePlanner.IsSelectablePoint(new Point2f(1280, 800), new Size(2560, 1600)));
        Assert.False(DestinationRoutePlanner.IsSelectablePoint(new Point2f(2300, 800), new Size(2560, 1600)));
        Assert.False(DestinationRoutePlanner.IsSelectablePoint(new Point2f(100, 100), default));
    }

    [Fact]
    public void StalledApproachStopsBeforeExistingTrapRecovery()
    {
        var state = new DestinationProgress();
        Assert.False(state.IsStalled(0, 100, 0));
        for (var time = 500; time < 6000; time += 500)
            Assert.False(state.IsStalled(0, 100, time));
        Assert.True(state.IsStalled(0, 100, 6000));
    }

    [Fact]
    public void ProgressOrNextWaypointResetsStallCounter()
    {
        var state = new DestinationProgress();
        for (var time = 0; time <= 20000; time += 500)
            Assert.False(state.IsStalled(0, 100 - time / 250d, time));
        Assert.False(state.IsStalled(1, 100, 20500));
    }

    [Fact]
    public void PauseAndFocusWaitDoNotCountAsStalling()
    {
        var state = new DestinationProgress();
        for (var time = 0; time < 6000; time += 500)
            Assert.False(state.IsStalled(0, 100, time));
        Assert.False(state.IsStalled(0, 100, 60000));
        Assert.False(state.IsStalled(0, 100, 60500));
        Assert.Throws<ArgumentException>(() => state.IsStalled(0, double.NaN, 61000));
    }
}
