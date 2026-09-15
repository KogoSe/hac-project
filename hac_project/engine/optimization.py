"""
ENGINE — MILP Optimization: grouping (contiguous cut) + pairing (2-source) รวมเป็นโมเดลเดียว
เป้าหมาย: minimize max-fail-load (โหลดสูงสุดเมื่อ UPS 1 ตัวพัง) ในบรรดาทุกกลุ่ม
ไม่มี st. ใดๆ ในไฟล์นี้ (แยกจาก UI เหมือน engine อื่น)

หลักการโมเดล (ดู proof tab สำหรับรายละเอียด):
- Grouping: ใช้ cumulative-threshold binary t[i][g] = "แถว i อยู่กลุ่ม <= g" แทนการ enumerate
  cut point ทุกแบบ -> ทำให้ contiguity เป็น constraint เชิงเส้นล้วนๆ ไม่ต้องวนลูปนอก MILP
- Pairing: q[i][g][p] = binary ตรงๆ ว่า "แถว i อยู่กลุ่ม g และใช้ pair p" ผูกกับ grouping
  ด้วย equality constraint (ไม่ใช้ McCormick/continuous linearization ซึ่งช้ากว่ามากที่ทดสอบแล้ว)
- Objective: minimize M โดย M >= โหลด UPS ทุกจุดที่เป็นไปได้ (ทุกกลุ่ม x ทุกกรณี UPS พัง x ทุก UPS ที่เหลือ)
  บวก epsilon*sum(โหลดทั้งหมด) เป็น tie-break กันโซลูชันเบี้ยวโดยไม่จำเป็น (epsilon เล็กมากจนไม่แย่ง
  ความสำคัญจาก M หลัก)
"""
import itertools
import pulp

from constants import UPS_UNITS

PAIRS = ["AB", "AC", "AD", "BC", "BD", "CD"]
EPS_TIE_BREAK = 1e-5
DEFAULT_TIME_LIMIT = 120
DEFAULT_GAP_REL = 0.01
BOTTLENECK_TOL = 1e-6


def _build_coeff_table() -> dict:
    """coeff[pair][faulted][unit] = สัดส่วนของ kw แถวที่ไป UPS `unit` เมื่อ `faulted` พัง
    ถ้าแถวนั้น pairing = pair (เฉพาะ 2-source) ค่าที่เป็นไปได้คือ 0, 0.5, 1.0"""
    coeff = {}
    for p in PAIRS:
        a, b = p[0], p[1]
        coeff[p] = {}
        for f in UPS_UNITS:
            coeff[p][f] = {}
            for u in UPS_UNITS:
                if u == f:
                    c = 0.0
                elif f in (a, b):
                    partner = b if f == a else a
                    c = 1.0 if u == partner else 0.0
                elif u in (a, b):
                    c = 0.5
                else:
                    c = 0.0
                coeff[p][f][u] = c
    return coeff


COEFF = _build_coeff_table()


def evaluate_group_max_fail(grp: list[dict]) -> float:
    """คำนวณ max-fail-load ของกลุ่มเดียวจาก coeff table ล้วนๆ (ไม่พึ่ง MILP)
    ใช้เป็น evaluator อิสระสำหรับตรวจผลลัพธ์ MILP และสำหรับ brute-force cross-check"""
    mx = 0.0
    for f in UPS_UNITS:
        for u in UPS_UNITS:
            if u == f:
                continue
            total = 0.0
            for row in grp:
                if row["source_type"] == "4-source":
                    total += row["kw"] / 3
                else:
                    total += row["kw"] * COEFF[row["pair"]][f][u]
            mx = max(mx, total)
    return mx


def _parse_cbc_log(log_text: str) -> dict:
    """ดึงสถานะจริงจาก CBC log (PuLP's LpStatus ไม่แยกแยะ 'proven optimal' กับ
    'best found ก่อนโดน time limit' — ทั้งคู่รายงานเป็น 'Optimal' เหมือนกัน)"""
    proven_optimal = "Result - Optimal solution found" in log_text
    time_limited = "Stopped on time limit" in log_text
    gap = None
    lower_bound = None
    for line in log_text.splitlines():
        s = line.strip()
        if s.startswith("Gap:"):
            try:
                gap = float(s.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif s.startswith("Lower bound:"):
            try:
                lower_bound = float(s.split(":", 1)[1].strip())
            except ValueError:
                pass
    return {
        "proven_optimal": proven_optimal,
        "time_limited": time_limited,
        "gap": gap,
        "solver_lower_bound": lower_bound,
    }


def solve_pairing_milp(
    row_units: list[dict],
    n_groups: int,
    time_limit: int = DEFAULT_TIME_LIMIT,
    gap_rel: float = DEFAULT_GAP_REL,
) -> dict:
    """
    MILP เดียว รวม grouping (contiguous cut) + pairing (2-source) เพื่อ minimize
    max-fail-load ในบรรดาทุกกลุ่ม (ทุกกลุ่มใช้ UPS ขนาดเท่ากัน -> bottleneck ของกลุ่มที่แย่สุด
    เป็นตัวกำหนด sizing)

    Returns dict:
        groups: list[list[dict]]  โครงสร้างเดียวกับที่ assign_pairing() เคยคืน (มี 'pair' ต่อแถว)
        status: str               "Optimal" (proven) / "Time-limited (gap X%)" / อื่นๆ
        objective: float          max-fail-load ที่ได้ (M*)
        gap: float | None         relative gap ที่ CBC รายงาน ณ จุดหยุด (0 ถ้า proven optimal)
        solver_lower_bound: float | None   LP/B&B lower bound จริงจาก CBC (แน่นกว่า theoretical)
        theoretical_lower_bound: float     max(group total kw)/3 ของกลุ่มที่ได้ (ฟังก์ชัน sanity)
        global_theoretical_lower_bound: float  (total kw ทั้งหมด / n_groups) / 3 — floor ที่เป็นไปได้ในทางทฤษฎี
                                                ไม่ขึ้นกับคำตอบที่ solve ได้จริง
    """
    n = len(row_units)
    two_idx = [i for i, r in enumerate(row_units) if r["source_type"] != "4-source"]
    four_idx = [i for i, r in enumerate(row_units) if r["source_type"] == "4-source"]

    prob = pulp.LpProblem("hac_grouping_pairing", pulp.LpMinimize)

    # ── contiguous-cut threshold: t[i][g] = "แถว i อยู่กลุ่ม <= g" (g = 1..n_groups-1) ──
    t = {}
    for i in range(n):
        for g in range(1, n_groups):
            t[i, g] = pulp.LpVariable(f"t_{i}_{g}", cat="Binary")
    for g in range(1, n_groups):
        for i in range(n - 1):
            prob += t[i, g] >= t[i + 1, g]          # ตัดแล้วตัดเลย (ตัด i แล้ว i+1 ต้องอยู่กลุ่มถัดไปด้วย)
    for i in range(n):
        for g in range(1, n_groups - 1):
            prob += t[i, g] <= t[i, g + 1]           # กลุ่ม<=g เป็น subset ของกลุ่ม<=g+1

    def y_expr(i, g):
        """นิพจน์เชิงเส้นของ 'แถว i อยู่กลุ่ม g' (g = 1..n_groups) จาก telescoping ของ t"""
        lo = t[i, g - 1] if g - 1 >= 1 else 0
        hi = t[i, g] if g <= n_groups - 1 else 1
        return hi - lo

    # ── pairing: q[i][g][p] binary ตรงๆ ผูกกับ grouping ผ่าน equality (ไม่ bilinear) ──
    q = {}
    for i in two_idx:
        for g in range(1, n_groups + 1):
            for p in PAIRS:
                q[i, g, p] = pulp.LpVariable(f"q_{i}_{g}_{p}", cat="Binary")
            prob += pulp.lpSum(q[i, g, p] for p in PAIRS) == y_expr(i, g)

    # ── objective: M >= โหลดทุกจุดที่เป็นไปได้ ──
    M = pulp.LpVariable("M", lowBound=0)
    all_load_terms = []
    for g in range(1, n_groups + 1):
        for f in UPS_UNITS:
            for u in UPS_UNITS:
                if u == f:
                    continue
                terms = []
                for i in two_idx:
                    for p in PAIRS:
                        c = COEFF[p][f][u]
                        if c != 0.0:
                            terms.append(c * row_units[i]["kw"] * q[i, g, p])
                for i in four_idx:
                    terms.append((row_units[i]["kw"] / 3) * y_expr(i, g))
                expr = pulp.lpSum(terms)
                prob += M >= expr
                all_load_terms.append(expr)

    prob += M + EPS_TIE_BREAK * pulp.lpSum(all_load_terms)

    import tempfile, os
    log_fd, log_path = tempfile.mkstemp(suffix=".log")
    os.close(log_fd)
    solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit, gapRel=gap_rel, logPath=log_path)
    prob.solve(solver)

    log_text = ""
    try:
        with open(log_path, "r", errors="ignore") as f:
            log_text = f.read()
    except OSError:
        pass
    finally:
        try:
            os.remove(log_path)
        except OSError:
            pass

    solver_info = _parse_cbc_log(log_text)
    if solver_info["proven_optimal"]:
        status_label = "Optimal (proven)"
    elif solver_info["time_limited"]:
        gap_pct = solver_info["gap"] * 100 if solver_info["gap"] is not None else None
        status_label = f"Time-limited (gap {gap_pct:.2f}%)" if gap_pct is not None else "Time-limited"
    else:
        status_label = pulp.LpStatus[prob.status]

    # ── extract solution ──
    groups_out = [[] for _ in range(n_groups)]
    for i in range(n):
        for g in range(1, n_groups + 1):
            val = y_expr(i, g)
            v = pulp.value(val) if not isinstance(val, int) else val
            if v is not None and v > 0.5:
                row = dict(row_units[i])
                if row["source_type"] == "4-source":
                    row["pair"] = "ABCD"
                else:
                    for p in PAIRS:
                        if pulp.value(q[i, g, p]) > 0.5:
                            row["pair"] = p
                            break
                groups_out[g - 1].append(row)
                break

    objective_value = pulp.value(M)

    theoretical_lb = max(sum(r["kw"] for r in grp) / 3 for grp in groups_out) if groups_out else 0.0
    total_kw_all = sum(r["kw"] for r in row_units)
    global_theoretical_lb = (total_kw_all / n_groups) / 3

    solver_lower_bound = solver_info["solver_lower_bound"]
    if solver_lower_bound is None and solver_info["proven_optimal"]:
        # proven optimal -> objective ตัวมันเองคือ lower bound ที่แน่นที่สุด (gap 0%)
        solver_lower_bound = objective_value

    return {
        "groups": groups_out,
        "status": status_label,
        "objective": objective_value,
        "gap": solver_info["gap"] if solver_info["gap"] is not None else (0.0 if solver_info["proven_optimal"] else None),
        "solver_lower_bound": solver_lower_bound,
        "theoretical_lower_bound": theoretical_lb,
        "global_theoretical_lower_bound": global_theoretical_lb,
        "mode": "contiguous",
        "time_limit": time_limit,
    }


def solve_pairing_milp_free(
    row_units: list[dict],
    n_groups: int,
    time_limit: int = DEFAULT_TIME_LIMIT,
    gap_rel: float = DEFAULT_GAP_REL,
    warm_start_groups: list[list[dict]] | None = None,
) -> dict:
    """
    เหมือน solve_pairing_milp() ทุกประการ ยกเว้น "วิธี assign แถวเข้ากลุ่ม" — ตัวนี้ไม่บังคับ
    contiguous cut ใช้ x[i][g] เป็น binary assignment ตรงๆ (แถวไหนไปกลุ่มไหนก็ได้ ข้ามหัวกันได้)
    เพื่อเป็น "เพดานทางทฤษฎี" เทียบกับ solve_pairing_milp() ที่ต้อง contiguous ตามข้อจำกัดทางกายภาพ
    จริง — ผลลัพธ์จากฟังก์ชันนี้ *ห้ามเอาไปเดินสายจริง*

    Symmetry-breaking แบบง่าย (ไม่ full lexicographic — รับทราบว่าตัด symmetry ไม่สมบูรณ์
    กรณี tie total_kw พอดี แต่ยอมรับได้ที่ scale งานนี้):
      - weight ordering: total_kw(group 1) >= total_kw(group 2) >= ... >= total_kw(group k)
      - warm-start: ถ้ามี warm_start_groups (เช่นจาก contiguous solution) ให้ set เป็นค่าเริ่มต้น
        ของ x[i][g] ให้ CBC มี incumbent ตั้งแต่แรก
    """
    n = len(row_units)
    two_idx = [i for i, r in enumerate(row_units) if r["source_type"] != "4-source"]
    four_idx = [i for i, r in enumerate(row_units) if r["source_type"] == "4-source"]

    prob = pulp.LpProblem("hac_grouping_pairing_free", pulp.LpMinimize)

    # ── free assignment: x[i][g] = "แถว i อยู่กลุ่ม g" ไม่มีข้อจำกัดเรื่องลำดับ ──
    x = {}
    for i in range(n):
        for g in range(1, n_groups + 1):
            x[i, g] = pulp.LpVariable(f"x_{i}_{g}", cat="Binary")
        prob += pulp.lpSum(x[i, g] for g in range(1, n_groups + 1)) == 1

    def y_expr(i, g):
        return x[i, g]

    # ── weight ordering symmetry-break: total_kw(g) >= total_kw(g+1) ──
    for g in range(1, n_groups):
        prob += (
            pulp.lpSum(row_units[i]["kw"] * x[i, g] for i in range(n))
            >= pulp.lpSum(row_units[i]["kw"] * x[i, g + 1] for i in range(n))
        )

    # ── pairing: q[i][g][p] binary ตรงๆ ผูกกับ grouping ผ่าน equality (ไม่ bilinear) ──
    q = {}
    for i in two_idx:
        for g in range(1, n_groups + 1):
            for p in PAIRS:
                q[i, g, p] = pulp.LpVariable(f"q_{i}_{g}_{p}", cat="Binary")
            prob += pulp.lpSum(q[i, g, p] for p in PAIRS) == y_expr(i, g)

    # ── objective: M >= โหลดทุกจุดที่เป็นไปได้ ──
    M = pulp.LpVariable("M", lowBound=0)
    all_load_terms = []
    for g in range(1, n_groups + 1):
        for f in UPS_UNITS:
            for u in UPS_UNITS:
                if u == f:
                    continue
                terms = []
                for i in two_idx:
                    for p in PAIRS:
                        c = COEFF[p][f][u]
                        if c != 0.0:
                            terms.append(c * row_units[i]["kw"] * q[i, g, p])
                for i in four_idx:
                    terms.append((row_units[i]["kw"] / 3) * y_expr(i, g))
                expr = pulp.lpSum(terms)
                prob += M >= expr
                all_load_terms.append(expr)

    prob += M + EPS_TIE_BREAK * pulp.lpSum(all_load_terms)

    # ── warm start: ตรึงค่าเริ่มต้นของ x[i][g] จาก grouping ที่ให้มา (เช่น contiguous solution) ──
    # สำคัญ: ต้อง relabel กลุ่มตาม total_kw มาก->น้อยก่อน ไม่งั้นจะขัดกับ weight-ordering
    # constraint ด้านบน (contiguous ไม่มีเหตุผลอะไรที่กลุ่มจะเรียงตาม weight พอดี) แล้ว CBC
    # จะทิ้ง warm start นั้นเงียบๆ เพราะ infeasible ตั้งแต่แรก
    warm_start_used = False
    if warm_start_groups is not None:
        groups_sorted = sorted(
            warm_start_groups, key=lambda grp: sum(r["kw"] for r in grp), reverse=True
        )
        row_to_group = {}
        for g_idx, grp in enumerate(groups_sorted, 1):
            for row in grp:
                key = (row["hac"], row["side"])
                row_to_group[key] = g_idx
        # map key -> row index ใน row_units (order เดียวกับที่ build_row_units คืนมา)
        key_to_i = {(r["hac"], r["side"]): i for i, r in enumerate(row_units)}
        if len(row_to_group) == n and all(k in key_to_i for k in row_to_group):
            for key, g_assigned in row_to_group.items():
                i = key_to_i[key]
                for g in range(1, n_groups + 1):
                    x[i, g].setInitialValue(1.0 if g == g_assigned else 0.0)
            warm_start_used = True

    import platform, tempfile, os
    log_fd, log_path = tempfile.mkstemp(suffix=".log")
    os.close(log_fd)
    # PuLP: on Windows, warmStart is silently ignored unless keepFiles=True (writes the
    # .mps/.sol/.mst files next to lp.name in cwd instead of a tmp dir) — we clean them up below.
    keep_files = warm_start_used and platform.system() == "Windows"
    solver = pulp.PULP_CBC_CMD(
        msg=0, timeLimit=time_limit, gapRel=gap_rel, logPath=log_path,
        warmStart=warm_start_used, keepFiles=keep_files,
    )
    prob.solve(solver)

    log_text = ""
    try:
        with open(log_path, "r", errors="ignore") as f:
            log_text = f.read()
    except OSError:
        pass
    finally:
        try:
            os.remove(log_path)
        except OSError:
            pass

    if keep_files:
        for ext in ("lp", "mps", "sol", "mst"):
            try:
                os.remove(f"{prob.name}-pulp.{ext}")
            except OSError:
                pass

    solver_info = _parse_cbc_log(log_text)
    if solver_info["proven_optimal"]:
        status_label = "Optimal (proven)"
    elif solver_info["time_limited"]:
        gap_pct = solver_info["gap"] * 100 if solver_info["gap"] is not None else None
        status_label = f"Time-limited (gap {gap_pct:.2f}%)" if gap_pct is not None else "Time-limited"
    else:
        status_label = pulp.LpStatus[prob.status]

    # ── extract solution ──
    groups_out = [[] for _ in range(n_groups)]
    for i in range(n):
        for g in range(1, n_groups + 1):
            val = y_expr(i, g)
            v = pulp.value(val) if not isinstance(val, int) else val
            if v is not None and v > 0.5:
                row = dict(row_units[i])
                if row["source_type"] == "4-source":
                    row["pair"] = "ABCD"
                else:
                    for p in PAIRS:
                        if pulp.value(q[i, g, p]) > 0.5:
                            row["pair"] = p
                            break
                groups_out[g - 1].append(row)
                break

    objective_value = pulp.value(M)

    theoretical_lb = max(sum(r["kw"] for r in grp) / 3 for grp in groups_out) if groups_out else 0.0
    total_kw_all = sum(r["kw"] for r in row_units)
    global_theoretical_lb = (total_kw_all / n_groups) / 3

    solver_lower_bound = solver_info["solver_lower_bound"]
    if solver_lower_bound is None and solver_info["proven_optimal"]:
        solver_lower_bound = objective_value

    return {
        "groups": groups_out,
        "status": status_label,
        "objective": objective_value,
        "gap": solver_info["gap"] if solver_info["gap"] is not None else (0.0 if solver_info["proven_optimal"] else None),
        "solver_lower_bound": solver_lower_bound,
        "theoretical_lower_bound": theoretical_lb,
        "global_theoretical_lower_bound": global_theoretical_lb,
        "mode": "free",
        "time_limit": time_limit,
    }


def brute_force_pairing_check(grp: list[dict], max_two_source: int = 8) -> dict | None:
    """
    Cross-check: ตรึง grouping ตามที่ MILP หาได้ แล้ววน brute force (6^k) หา pairing
    ที่ optimal จริงสำหรับกลุ่มนี้ (k = จำนวนแถว 2-source ในกลุ่ม) เพื่อยืนยันว่า MILP
    ไม่ได้ทำพลาด (เฉพาะกลุ่มที่ k <= max_two_source เพราะ 6^k โตเร็วมาก)
    Returns None ถ้ากลุ่มมี 2-source เกิน max_two_source (ข้ามการเช็ค)
    """
    two_rows = [r for r in grp if r["source_type"] != "4-source"]
    four_rows = [r for r in grp if r["source_type"] == "4-source"]
    k = len(two_rows)
    if k > max_two_source:
        return None

    best_max = float("inf")
    best_pairs = None
    if k == 0:
        best_max = evaluate_group_max_fail(four_rows)
        best_pairs = ()
    else:
        for combo in itertools.product(PAIRS, repeat=k):
            candidate = [dict(r, pair=combo[j]) for j, r in enumerate(two_rows)] + four_rows
            val = evaluate_group_max_fail(candidate)
            if val < best_max:
                best_max = val
                best_pairs = combo

    milp_max = evaluate_group_max_fail(grp)
    return {
        "brute_force_best": best_max,
        "milp_result": milp_max,
        "matches": abs(best_max - milp_max) < 1e-6,
        "best_pairing": best_pairs,
        "n_two_source": k,
        "combinations_tried": len(PAIRS) ** k,
    }


def build_proof_context(milp_result: dict, max_two_source: int = 8) -> dict:
    """
    รวมทุกอย่างที่ต้องใช้ "แสดงผล" หรือ "สร้างเอกสาร proof" จาก milp_result เดียว —
    single source of truth ให้ ui/tab_proof.py (แสดงใน UI) และ engine/report_docx.py
    (สร้าง .docx) เรียกใช้ร่วมกัน ไม่คำนวณ evaluate_group_max_fail / brute_force_pairing_check
    ซ้ำกันคนละที่ (ผลอาจไม่ sync กันถ้าแก้ที่หนึ่งแล้วลืมอีกที่)
    """
    groups = milp_result["groups"]
    overall_max = milp_result["objective"]
    group_checks = []
    for gi, grp in enumerate(groups, 1):
        group_max = evaluate_group_max_fail(grp)
        is_bottleneck = abs(group_max - overall_max) < BOTTLENECK_TOL
        n_two = sum(1 for r in grp if r["source_type"] != "4-source")
        chk = brute_force_pairing_check(grp, max_two_source=max_two_source)
        group_checks.append({
            "index": gi,
            "group": grp,
            "n_two_source": n_two,
            "group_max": group_max,
            "is_bottleneck": is_bottleneck,
            "brute_force": chk,  # None ถ้าข้าม (2-source > max_two_source)
        })
    return {
        "milp_result": milp_result,
        "overall_max": overall_max,
        "group_checks": group_checks,
        "max_two_source": max_two_source,
    }
