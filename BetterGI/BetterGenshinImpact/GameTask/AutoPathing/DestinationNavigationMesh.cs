using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.GameTask.AutoPathing.Model;
using DotRecast.Core.Numerics;
using DotRecast.Detour;
using DotRecast.Recast;
using DotRecast.Recast.Geom;
using OpenCvSharp;

namespace BetterGenshinImpact.GameTask.AutoPathing;

// 根据场景几何生成可通行面；不读取录制路线。高度不明确时不猜测所在楼层。
internal sealed class DestinationNavigationMesh
{
    private readonly DtNavMesh _mesh;
    private readonly float _minHeight;
    private readonly float _maxHeight;
    private const int MaxPath = 2048;
    private static readonly Lazy<DestinationNavigationMesh> Mondstadt = new(LoadMondstadt);

    internal static DestinationNavigationMesh Current => Mondstadt.Value;

    internal DestinationNavigationMesh(float[] vertices, int[] triangles)
    {
        var geometry = new RcSampleInputGeomProvider(vertices, triangles);
        _minHeight = geometry.GetMeshBoundsMin().Y;
        _maxHeight = geometry.GetMeshBoundsMax().Y;
        const float cell = 0.3f, heightCell = 0.15f, agentHeight = 1.8f, radius = 1.2f, step = 1.2f;
        var config = new RcConfig(RcPartition.WATERSHED, cell, heightCell,
            45, agentHeight, radius, step, 4, 20, 12, 0.5f, 6, 6, 1,
            true, true, true, new RcAreaModification(1), true);
        var result = new RcBuilder().Build(geometry,
            new RcBuilderConfig(config, geometry.GetMeshBoundsMin(), geometry.GetMeshBoundsMax()), false);
        var polygons = result.Mesh;
        var detail = result.MeshDetail;
        for (var i = 0; i < polygons.npolys; i++) polygons.flags[i] = 1;
        var data = DtNavMeshBuilder.CreateNavMeshData(new DtNavMeshCreateParams
        {
            verts = polygons.verts, vertCount = polygons.nverts,
            polys = polygons.polys, polyAreas = polygons.areas, polyFlags = polygons.flags,
            polyCount = polygons.npolys, nvp = polygons.nvp,
            detailMeshes = detail.meshes, detailVerts = detail.verts, detailVertsCount = detail.nverts,
            detailTris = detail.tris, detailTriCount = detail.ntris,
            walkableHeight = agentHeight, walkableRadius = radius, walkableClimb = step,
            bmin = polygons.bmin, bmax = polygons.bmax, cs = cell, ch = heightCell, buildBvTree = true
        });
        _mesh = new DtNavMesh();
        if (data == null || _mesh.Init(data, 6, 0).Failed())
            throw new InvalidOperationException("蒙德导航地图没有可用的通行面。");
    }

    private static DestinationNavigationMesh LoadMondstadt()
    {
        var path = Global.Absolute(@"GameTask\AutoPathing\Assets\Navigation\mondstadt.obj");
        if (!File.Exists(path))
            throw new InvalidOperationException("缺少蒙德导航地图，请使用包含地图数据的测试版。");
        var source = RcSampleInputGeomProvider.LoadFile(path);
        var vertices = source.vertices.ToArray();
        for (var i = 0; i < vertices.Length; i += 3)
        {
            var localX = vertices[i];
            // OBJ 的水平 X 轴与游戏世界相反；BetterGI 的平面坐标顺序为世界 Z、X。
            vertices[i] = vertices[i + 2] - 783;
            vertices[i + 1] += 263;
            vertices[i + 2] = 2275 - localX;
        }
        return new DestinationNavigationMesh(vertices, source.faces);
    }

    internal List<Waypoint> Plan(Point2f start, Point2f target)
    {
        if (!DestinationRoutePlanner.IsFinite(start) || !DestinationRoutePlanner.IsFinite(target))
            throw new ArgumentException("角色或目的地坐标无效。");
        var query = new DtNavMeshQuery(_mesh);
        var filter = new DtQueryDefaultFilter();
        var (startRef, start3) = Surface(query, filter, start);
        var (endRef, end3) = Surface(query, filter, target);
        var corridor = new long[MaxPath];
        var status = query.FindPath(startRef, endRef, start3, end3, filter, corridor, out var count, MaxPath);
        if (!status.Succeeded() || status.IsPartial() || status.Has(DtStatus.DT_BUFFER_TOO_SMALL)
            || count == 0 || corridor[count - 1] != endRef)
            throw new InvalidOperationException("起点与目标之间没有连通的地面道路，已停止；不会用直线或旧路线代替。");
        var corners = new DtStraightPath[MaxPath];
        status = query.FindStraightPath(start3, end3, corridor, count, corners, out var cornerCount, MaxPath, 0);
        if (!status.Succeeded() || status.IsPartial() || status.Has(DtStatus.DT_BUFFER_TOO_SMALL) || cornerCount < 1
            || Math.Abs(corners[cornerCount - 1].pos.X - end3.X) > 0.01
            || Math.Abs(corners[cornerCount - 1].pos.Z - end3.Z) > 0.01)
            throw new InvalidOperationException("无法生成完整的转弯路径。");

        var route = new List<Waypoint> { new() { X = start.X, Y = start.Y, Type = "path", MoveMode = "walk" } };
        for (var i = 1; i < cornerCount; i++)
        {
            var a = corners[i - 1].pos;
            var b = corners[i].pos;
            var distance = Math.Sqrt(Math.Pow(b.X - a.X, 2) + Math.Pow(b.Z - a.Z, 2));
            var segments = Math.Max(1, (int)Math.Ceiling(distance / 20));
            for (var part = 1; part <= segments; part++)
            {
                var t = (float)part / segments;
                route.Add(new Waypoint
                {
                    X = a.X + (b.X - a.X) * t, Y = a.Z + (b.Z - a.Z) * t,
                    // 所有转弯点都必须精确接近，防止旧执行器提前转弯切过墙角。
                    Type = "target", MoveMode = distance / segments > 12 ? "run" : "walk"
                });
            }
        }
        if (route.Count == 1)
            route.Add(new Waypoint { X = target.X, Y = target.Y, Type = "target", MoveMode = "walk" });
        return route;
    }

    private (long Reference, RcVec3f Position) Surface(DtNavMeshQuery query, IDtQueryFilter filter, Point2f point)
    {
        var candidates = new long[128];
        var center = new RcVec3f(point.X, (_minHeight + _maxHeight) / 2, point.Y);
        var status = query.QueryPolygons(center, new RcVec3f(0.05f, (_maxHeight - _minHeight) / 2 + 1, 0.05f),
            filter, candidates, out var count, candidates.Length);
        if (!status.Succeeded() || status.Has(DtStatus.DT_BUFFER_TOO_SMALL))
            throw new InvalidOperationException("无法确定目的地的通行面。");
        var surfaces = new List<(long Reference, float Height)>();
        for (var i = 0; i < count; i++)
            if (query.GetPolyHeight(candidates[i], center, out var h).Succeeded())
                surfaces.Add((candidates[i], h));
        if (surfaces.Count == 0)
            throw new InvalidOperationException("起点或目标不在蒙德已建模的可通行区域内，请选择道路中间。");
        if (surfaces.Max(p => p.Height) - surfaces.Min(p => p.Height) > 1.5)
            throw new InvalidOperationException("起点或目标存在上下重叠的通行面，当前无法确认楼层，已停止。");
        return (surfaces[0].Reference, new RcVec3f(point.X, surfaces[0].Height, point.Y));
    }
}
