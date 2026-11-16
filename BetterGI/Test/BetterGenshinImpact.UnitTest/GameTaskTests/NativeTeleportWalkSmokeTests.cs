using BetterGenshinImpact.GameTask.AutoPathing;
using OpenCvSharp;

namespace BetterGenshinImpact.UnitTest.GameTaskTests;

public class NativeTeleportWalkSmokeTests
{
    private static readonly Point2f Start = new(10, 10);
    private static Point2f[] Stopped => [new(13, 10), new(13.1f, 10), new(12.9f, 10)];

    [Fact]
    public void DisplacedThenStableWithNoHeldInputPasses() =>
        NativeTeleportWalkSmoke.ValidateProgress(Start, Stopped, 0, false);

    [Fact]
    public void NoDisplacementCannotBeMovementSuccess() => Assert.Throws<InvalidOperationException>(() =>
        NativeTeleportWalkSmoke.ValidateProgress(Start, [Start, Start, Start], 0, false));

    [Fact]
    public void ContinuedMovementCannotBeStopped() => Assert.Throws<InvalidOperationException>(() =>
        NativeTeleportWalkSmoke.ValidateProgress(Start, [new(13, 10), new(15, 10), new(18, 10)], 0, false));

    [Theory]
    [InlineData(1, false)]
    [InlineData(0, true)]
    public void HeldInputCannotBeStopped(int held, bool keyDown) => Assert.Throws<InvalidOperationException>(() =>
        NativeTeleportWalkSmoke.ValidateProgress(Start, Stopped, held, keyDown));

    [Fact]
    public void MissingObservationCannotPass() => Assert.Throws<InvalidOperationException>(() =>
        NativeTeleportWalkSmoke.ValidateProgress(Start, [new(13, 10)], 0, false));

    [Fact]
    public void InvalidCoordinateCannotPass() => Assert.Throws<InvalidOperationException>(() =>
        NativeTeleportWalkSmoke.ValidateProgress(Start, [new(float.NaN, 10), new(13, 10), new(13, 10)], 0, false));

    [Fact]
    public void LargeJumpCannotPassAsShortWalk() => Assert.Throws<InvalidOperationException>(() =>
        NativeTeleportWalkSmoke.ValidateProgress(Start, [new(40, 10), new(40, 10), new(40, 10)], 0, false));
}
