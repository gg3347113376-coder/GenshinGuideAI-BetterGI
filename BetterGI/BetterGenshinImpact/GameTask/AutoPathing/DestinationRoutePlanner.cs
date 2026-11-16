using System;
using OpenCvSharp;

namespace BetterGenshinImpact.GameTask.AutoPathing;

// 选点坐标和到达判断；道路规划由 DestinationNavigationMesh 负责。
internal static class DestinationRoutePlanner
{
    internal const double ArrivalRadius = 3;

    internal static Point2f ProjectCursor(Rect mapImageRect, Size viewport, Point2f cursor)
    {
        if (mapImageRect.Width <= 0 || mapImageRect.Height <= 0 || viewport.Width <= 0 || viewport.Height <= 0
            || !IsFinite(cursor) || cursor.X < 0 || cursor.Y < 0 || cursor.X >= viewport.Width || cursor.Y >= viewport.Height)
            throw new ArgumentException("地图范围或鼠标坐标无效。");
        return new Point2f(
            (float)(mapImageRect.X + cursor.X / viewport.Width * mapImageRect.Width),
            (float)(mapImageRect.Y + cursor.Y / viewport.Height * mapImageRect.Height));
    }

    internal static Point2f ConfirmTarget(Point2f first, Point2f second)
    {
        // 大地图矩形按 256 层整数像素返回；一个像素相当于 4 个游戏坐标单位。
        // 容许取整抖动并取两次结果的中点，明显移动仍然拒绝。
        if (!IsFinite(first) || !IsFinite(second) || first.DistanceTo(second) > 6)
            throw new InvalidOperationException("地图定位结果不稳定或地图发生变化，请保持地图静止、调整缩放后重新选点。");
        return (first + second) * 0.5f;
    }


    internal static bool IsSelectablePoint(Point2f cursor, Size viewport) =>
        viewport.Width > 0 && viewport.Height > 0 && IsFinite(cursor)
        && cursor.X >= viewport.Width * 360d / 1920 && cursor.X < viewport.Width * 1480d / 1920
        && cursor.Y >= viewport.Height * 170d / 1080 && cursor.Y < viewport.Height * 940d / 1080;

    internal static bool IsFinite(Point2f point) => float.IsFinite(point.X) && float.IsFinite(point.Y);

}

internal sealed class DestinationProgress
{
    private int _waypoint = -1;
    private double _bestDistance;
    private long _lastTime;
    private long _stalledMs;

    internal bool IsStalled(int waypoint, double distance, long now)
    {
        if (!double.IsFinite(distance) || distance < 0)
            throw new ArgumentException("无法确认角色与路径点的距离。");
        var elapsed = now - _lastTime;
        if (waypoint != _waypoint || elapsed > 1000 || elapsed < 0 || distance < _bestDistance - 2)
        {
            _waypoint = waypoint;
            _bestDistance = distance;
            _stalledMs = 0;
        }
        else
            _stalledMs += elapsed;
        _lastTime = now;
        return _stalledMs >= 6000;
    }
}
