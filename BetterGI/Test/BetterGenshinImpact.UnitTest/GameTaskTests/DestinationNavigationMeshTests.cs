using BetterGenshinImpact.GameTask.AutoPathing;
using OpenCvSharp;

namespace BetterGenshinImpact.UnitTest.GameTaskTests;

public class DestinationNavigationMeshTests
{
    private static DestinationNavigationMesh Map(Func<int, int, bool> allowed, bool upperFloor = false)
    {
        var vertices = new List<float>();
        var triangles = new List<int>();
        void Floor(float y)
        {
            for (var x = 0; x < 30; x++)
            for (var z = 0; z < 30; z++)
            {
                if (!allowed(x, z)) continue;
                var n = vertices.Count / 3;
                vertices.AddRange([x, y, z, x + 1, y, z, x + 1, y, z + 1, x, y, z + 1]);
                triangles.AddRange([n, n + 2, n + 1, n, n + 3, n + 2]);
            }
        }
        Floor(0);
        if (upperFloor) Floor(5);
        return new DestinationNavigationMesh(vertices.ToArray(), triangles.ToArray());
    }

    [Fact]
    public void NewDestinationFindsAWayAroundAnObstacleWithoutAnyRecordedRoute()
    {
        var map = Map((x, z) => x < 10 || x >= 20 || z < 10 || z >= 20);
        var route = map.Plan(new Point2f(4, 15), new Point2f(26, 15));
        Assert.True(route.Count > 2);
        Assert.Equal(26, route[^1].X, 3);
        Assert.Equal(15, route[^1].Y, 3);
        Assert.All(route, p => Assert.NotEqual("teleport", p.Type));
        for (var i = 1; i < route.Count; i++)
        for (var sample = 0; sample <= 100; sample++)
        {
            var t = sample / 100d;
            var x = route[i - 1].X * (1 - t) + route[i].X * t;
            var y = route[i - 1].Y * (1 - t) + route[i].Y * t;
            Assert.False(x > 10 && x < 20 && y > 10 && y < 20, "Planned segment cuts through the obstacle.");
        }
    }

    [Fact]
    public void RejectsPartialPathAcrossDisconnectedGround()
    {
        var map = Map((x, z) => x < 12 || x >= 18);
        Assert.Throws<InvalidOperationException>(() => map.Plan(new Point2f(5, 15), new Point2f(25, 15)));
    }

    [Fact]
    public void RejectsUncoveredTargetInsteadOfFallingBackToAStraightLine()
    {
        var map = Map((x, z) => true);
        Assert.Throws<InvalidOperationException>(() => map.Plan(new Point2f(5, 5), new Point2f(31, 15)));
        Assert.Throws<ArgumentException>(() => map.Plan(new Point2f(float.NaN, 5), new Point2f(15, 15)));
    }

    [Fact]
    public void RejectsAmbiguousFloors()
    {
        var map = Map((x, z) => true, upperFloor: true);
        Assert.Throws<InvalidOperationException>(() => map.Plan(new Point2f(5, 5), new Point2f(25, 25)));
    }

    [Fact]
    public void RealMondstadtGeometryCanPlanANewNearbyRoadDestination()
    {
        var route = DestinationNavigationMesh.Current.Plan(new Point2f(-893.83f, 2249.09f), new Point2f(-900, 2260));
        Assert.Equal(-900, route[^1].X, 2);
        Assert.Equal(2260, route[^1].Y, 2);
    }
    [Fact]
    public void RealMondstadtAnchorCanReachSelectedGroundRoad()
    {
        var start = new Point2f(-867.68f, 2281.38f);
        var target = new Point2f(-851.50f, 2240.77f);
        var route = DestinationNavigationMesh.Current.Plan(start, target);
        Assert.Equal(start.X, route[0].X, 2);
        Assert.Equal(start.Y, route[0].Y, 2);
        Assert.Equal(target.X, route[^1].X, 2);
        Assert.Equal(target.Y, route[^1].Y, 2);
    }

    [Fact]
    public void RejectsLargeHeightStepEvenWhenSurfacesTouchInPlanView()
    {
        var map = new DestinationNavigationMesh(
            [0, 0, 0, 14, 0, 0, 14, 0, 30, 0, 0, 30,
             14, 4, 0, 30, 4, 0, 30, 4, 30, 14, 4, 30],
            [0, 2, 1, 0, 3, 2, 4, 6, 5, 4, 7, 6]);
        Assert.Throws<InvalidOperationException>(() => map.Plan(new Point2f(5, 15), new Point2f(25, 15)));
    }
}
