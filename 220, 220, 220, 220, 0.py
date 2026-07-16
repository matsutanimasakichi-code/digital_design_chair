#! python 3
import math
import rhinoscriptsyntax as rs


def create_hyperboloid_curved_chair_with_tensegritiy_slits():
    # ==========================================
    # 1. パラメータ設定
    # ==========================================
    base_radius_x = 220
    base_radius_y = 220
    seat_radius_x = 220
    seat_radius_y = 220
    seat_height = 420
    seat_tilt_deg = 0

    div_count = 16
    shift_index = 4

    # 部材寸法
    member_thickness = 12.0
    squeeze_ratio = 0.25      # くびれ調整

    # メンブレン（糸張り）一括ON/OFFスイッチ
    show_membrane = True

    # --- 上部引っ掛け用矩形スリットのパラメータ ---
    top_cutout_shift = 15   # 上端からスリットが始まるまでの下方向への距離 (mm)
    top_cutout_width = 12.0   # スリットの幅方向への食い込み深さ (mm)
    top_cutout_height = 12.0  # スリットの高さ方向（長さ方向）の切り欠き量 (mm)

    # ==========================================
    # 2. 楕円の点（座標）の生成
    # ==========================================
    base_pts = []
    for i in range(div_count):
        angle = (2 * math.pi * i) / div_count
        base_pts.append([base_radius_x * math.cos(angle), base_radius_y * math.sin(angle), 0.0])

    seat_pts = []
    tilt_rad = math.radians(seat_tilt_deg)
    for i in range(div_count):
        angle = (2 * math.pi * i) / div_count
        local_x = seat_radius_x * math.cos(angle)
        local_y = seat_radius_y * math.sin(angle)
        
        global_x = local_x
        global_y = local_y * math.cos(tilt_rad)
        global_z = seat_height + local_y * math.sin(tilt_rad)
        seat_pts.append([global_x, global_y, global_z])

    # ==========================================
    # 3. 芯線のペアリングと幅の決定
    # ==========================================
    line_pairs = []
    for i in range(div_count):
        target_i = (i + shift_index) % div_count
        line_pairs.append((base_pts[i], seat_pts[target_i]))

    pt_a0, pt_b0 = line_pairs[0]
    pt_a1, pt_b1 = line_pairs[1]
    distance_to_next = rs.Distance(
        rs.PointScale(rs.PointAdd(pt_a0, pt_b0), 0.5),
        rs.PointScale(rs.PointAdd(pt_a1, pt_b1), 0.5)
    )
    member_width = distance_to_next * 1.0 

    # レイヤー設定
    if not rs.IsLayer("Frame_Curved_Solids"): rs.AddLayer("Frame_Curved_Solids", [180, 180, 180])

    # メンブレン用のスリット中心座標を記憶する配列
    top_hole_centers_l = [None] * div_count
    top_hole_centers_r = [None] * div_count

    # ==========================================
    # 4. 各パーツの計算・ソリッド化・穴あけ加工
    # ==========================================
    for i in range(div_count):
        pt_a, pt_b = line_pairs[i]
        
        vec_axis = rs.VectorCreate(pt_b, pt_a)
        vec_axis_unit = rs.VectorUnitize(vec_axis)

        next_i = (i + 1) % div_count
        next_pt_a, next_pt_b = line_pairs[next_i]
        mid_pt = rs.PointScale(rs.PointAdd(pt_a, pt_b), 0.5)
        next_mid_pt = rs.PointScale(rs.PointAdd(next_pt_a, next_pt_b), 0.5)
        vec_to_next = rs.VectorCreate(next_mid_pt, mid_pt)
        
        vec_width_dir = rs.VectorCrossProduct(vec_axis, rs.VectorCrossProduct(vec_to_next, vec_axis))
        vec_width_dir = rs.VectorUnitize(vec_width_dir)
        vec_thickness_dir = rs.VectorUnitize(rs.VectorCrossProduct(vec_axis, vec_width_dir))

        w_vec = vec_width_dir * member_width

        # 下側は地面と平行
        if abs(vec_axis_unit[2]) > 1e-6:
            p_left_bottom = rs.PointAdd(pt_a, vec_axis_unit * ((0.0 - pt_a[2]) / vec_axis_unit[2]))
            p_right_bottom = rs.PointAdd(rs.PointAdd(pt_a, w_vec), vec_axis_unit * ((0.0 - rs.PointAdd(pt_a, w_vec)[2]) / vec_axis_unit[2]))
        else:
            continue

        # 上端の形状生成（軸に対して垂直）
        p_left_top = pt_b
        p_right_top = rs.PointAdd(pt_b, w_vec)

        # 外形曲線の作成
        mid_left = rs.PointScale(rs.PointAdd(p_left_bottom, p_left_top), 0.5)
        mid_right = rs.PointScale(rs.PointAdd(p_right_bottom, p_right_top), 0.5)
        vec_mid_bridge = rs.VectorCreate(mid_right, mid_left)
        
        pt_2_param = rs.PointAdd(mid_left, vec_mid_bridge * squeeze_ratio)
        pt_1_param = rs.PointAdd(mid_left, vec_mid_bridge * (1.0 - squeeze_ratio))

        curve_left = rs.AddCurve([p_left_top, pt_2_param, p_left_bottom], degree=2)
        curve_right = rs.AddCurve([p_right_top, pt_1_param, p_right_bottom], degree=2)
        top_line = rs.AddLine(p_left_top, p_right_top)
        bottom_line = rs.AddLine(p_left_bottom, p_right_bottom)

        joined_crv = rs.JoinCurves([curve_left, top_line, curve_right, bottom_line], delete_input=True)
        if joined_crv and not rs.IsCurveClosed(joined_crv[0]):
            rs.CloseCurve(joined_crv[0])

        planar_srf = rs.AddPlanarSrf(joined_crv[0])
        if planar_srf:
            extrude_path = rs.AddLine([0, 0, 0], vec_thickness_dir * member_thickness)
            solid = rs.ExtrudeSurface(planar_srf[0], extrude_path)
            rs.DeleteObject(extrude_path)  
            
            if solid:
                rs.CapPlanarHoles(solid)
                cutters = []

                # --- 上部引っ掛け用・矩形スリットの作成と座標回収 ---
                margin = 15.0

                # [左側の矩形スリットカッター]
                base_l = rs.PointSubtract(p_left_top, vec_axis_unit * top_cutout_shift)
                # メンブレン用のフック位置（スリットの底面中央付近）として座標を計算・記録
                top_hole_centers_l[i] = rs.PointAdd(
                    rs.PointAdd(base_l, vec_width_dir * (top_cutout_width * 0.5)),
                    -vec_axis_unit * (top_cutout_height * 0.5)
                )

                l0 = rs.PointSubtract(base_l, vec_width_dir * margin + vec_thickness_dir * member_thickness)
                l1 = rs.PointAdd(base_l, vec_width_dir * top_cutout_width - vec_thickness_dir * member_thickness)
                l2 = rs.PointAdd(l1, vec_thickness_dir * member_thickness * 3.0)
                l3 = rs.PointAdd(l0, vec_thickness_dir * member_thickness * 3.0)
                l4 = rs.PointSubtract(l0, vec_axis_unit * top_cutout_height)
                l5 = rs.PointSubtract(l1, vec_axis_unit * top_cutout_height)
                l6 = rs.PointSubtract(l2, vec_axis_unit * top_cutout_height)
                l7 = rs.PointSubtract(l3, vec_axis_unit * top_cutout_height)
                cutters.append(rs.AddBox([l0, l1, l2, l3, l4, l5, l6, l7]))

                # [右側の矩形スリットカッター]
                base_r = rs.PointSubtract(p_right_top, vec_axis_unit * top_cutout_shift)
                # メンブレン用のフック位置（スリットの底面中央付近）として座標を計算・記録
                top_hole_centers_r[i] = rs.PointAdd(
                    rs.PointSubtract(base_r, vec_width_dir * (top_cutout_width * 0.5)),
                    -vec_axis_unit * (top_cutout_height * 0.5)
                )

                r0 = rs.PointSubtract(base_r, vec_width_dir * top_cutout_width + vec_thickness_dir * member_thickness)
                r1 = rs.PointAdd(base_r, vec_width_dir * margin - vec_thickness_dir * member_thickness)
                r2 = rs.PointAdd(r1, vec_thickness_dir * member_thickness * 3.0)
                r3 = rs.PointAdd(r0, vec_thickness_dir * member_thickness * 3.0)
                r4 = rs.PointSubtract(r0, vec_axis_unit * top_cutout_height)
                r5 = rs.PointSubtract(r1, vec_axis_unit * top_cutout_height)
                r6 = rs.PointSubtract(r2, vec_axis_unit * top_cutout_height)
                r7 = rs.PointSubtract(r3, vec_axis_unit * top_cutout_height)
                cutters.append(rs.AddBox([r0, r1, r2, r3, r4, r5, r6, r7]))

                # ブーリアン演算で削り出し（上部の矩形スリットのみ）
                final_frame = rs.BooleanDifference(solid, cutters)
                if final_frame:
                    rs.ObjectLayer(final_frame, "Frame_Curved_Solids")
                else:
                    rs.ObjectLayer(solid, "Frame_Curved_Solids")
                if cutters: rs.DeleteObjects(cutters)

            rs.DeleteObjects(planar_srf)
        if joined_crv: rs.DeleteObjects(joined_crv)

    # ==========================================
    # 5. スイッチ連動：上部スリットを使用したメンブレン（糸張り）生成
    # ==========================================
    if show_membrane:
        membrane_lines = []
        # ご提示いただいた編み込みスキップ設定の移植
        threads_config = [{"skip": 8}, {"skip": 7}, {"skip": 9}, {"skip": 6}]
        
        for config in threads_config:
            skip = config["skip"]
            for i in range(div_count):
                pt_left_curr = top_hole_centers_l[i]
                target_frame = (i + skip) % div_count
                pt_right_next = top_hole_centers_r[target_frame]
                
                if pt_left_curr and pt_right_next:
                    # 現フレームの左スリットから、ターゲットフレームの右スリットへ接続
                    membrane_lines.append(rs.AddLine(pt_left_curr, pt_right_next))
                    
                    pt_left_next = top_hole_centers_l[target_frame]
                    if pt_left_next:
                        # ターゲットフレームの右スリットから、そのまま左スリットへ巡回接続
                        membrane_lines.append(rs.AddLine(pt_right_next, pt_left_next))

        if membrane_lines:
            if not rs.IsLayer("Membrane"): 
                rs.AddLayer("Membrane", [255, 128, 0])
            rs.ObjectLayer(membrane_lines, "Membrane")


if __name__ == "__main__":
    create_hyperboloid_curved_chair_with_tensegritiy_slits()