"""
ENGINE — MILP Optimization: grouping (contiguous cut) + pairing (2-source) + quad-assignment
(4-source) รวมเป็นโมเดลเดียว เป้าหมาย: minimize max-fail-load (โหลดสูงสุดเมื่อ UPS 1 ตัวพัง)
ในบรรดาทุกกลุ่ม ไม่มี st. ใดๆ ในไฟล์นี้ (แยกจาก UI เหมือน engine อื่น)

หลักการโมเดล (ดู proof tab สำหรับรายละเอียด):
- Grouping: ใช้ cumulative-threshold binary t[i][g] = "แถว i อยู่กลุ่ม <= g" แทนการ enumerate
  cut point ทุกแบบ -> ทำให้ contiguity เป็น constraint เชิงเส้นล้วนๆ ไม่ต้องวนลูปนอก MILP
- Pairing (2-source): q[i][g][p] = binary ตรงๆ ว่า "แถว i อยู่กลุ่ม g และใช้ pair p (2 ตัวจาก
  n_ups_per_group)" ผูกกับ grouping ด้วย equality constraint
- Quad-assignment (4-source, ยืนยันโดยผู้ใช้ 2026-09): เมื่อ n_ups_per_group > 4 แถว 4-source
  (เสียบสายจริงแค่ 4 เส้นเสมอทางกายภาพ ไม่ว่ากลุ่มจะมี UPS กี่ตัว) ต้อง "เลือกว่าจะเสียบเข้า UPS
  4 ตัวไหนในกลุ่ม" ด้วย — ใช้ q4[i][g][quad] แบบเดียวกับ q[i][g][p] ทุกประการ (quad = 4 ตัวอักษร
  จาก combinations(ups_units, 4)) เมื่อ n_ups_per_group == 4 จะมี quad ให้เลือกแค่แบบเดียว
  (ครบทั้งกลุ่มพอดี) จึงพฤติกรรมเหมือนระบบเดิมทุกประการ (backward compatible)
- Coefficient table: ใช้สูตรเดียวกันทั้ง pair (2 ตัว) และ quad (4 ตัว) — โหลดแบ่งเท่ากันในหมู่
  สมาชิก subset ตอนปกติ (1/len(subset)) และแบ่งเท่ากันในหมู่สมาชิกที่ยังไม่พัง ตอน fault เป็นสมาชิก
  ของ subset นั้นเอง (1/(len(subset)-1)) — ดู _build_coeff_table()
- Objective: minimize M โดย M >= โหลด UPS ทุกจุดที่เป็นไปได้ (ทุกกลุ่ม x ทุกกรณี UPS พัง x ทุก UPS
  ที่เหลือ) บวก epsilon*sum(โหลดทั้งหมด) เป็น tie-break กันโซลูชันเบี้ยวโดยไม่จำเป็น
"""
import functools
import itertools
import re
import pulp

from constants import get_group_ups_units

EPS_TIE_BREAK = 1e-5
DEFAULT_TIME_LIMIT = 120
DEFAULT_GAP_REL = 0.01
BOTTLENECK_TOL = 1e-6
DEFAULT_N_UPS_PER_GROUP = 4
MAX_BRUTE_FORCE_COMBOS = 2_000_000  # เพดานรวม (pairs^k2 * quads^k4) ก่อนข้ามการ cross-check


def _subsets_of_size(ups_units: list, size: int) -> list:
    return ["".join(c) for c in itertools.combinations(ups_units, size)]


def get_pairs(ups_units: list) -> list:
    """2 ตัวจาก n_ups_per_group ตัว — ใช้กำหนดว่าแถว 2-source เสียบ UPS คู่ไหน"""
    return _subsets_of_size(ups_units, 2)


def get_quads(ups_units: list) -> list:
    """4 ตัวจาก n_ups_per_group ตัว — ใช้กำหนดว่าแถว 4-source เสียบ UPS 4 ตัวไหน
    (เสียบสายจริงแค่ 4 เส้นเสมอทางกายภาพไม่ว่ากลุ่มจะมี UPS ทั้งหมดกี่ตัว)
    ถ้า n_ups_per_group == 4 จะมี quad ให้เลือกแค่แบบเดียว (ครบทั้งกลุ่มพอดี)"""
    return _subsets_of_size(ups_units, 4)


def _build_coeff_table(subsets: list, ups_units: list) -> dict:
    """coeff[subset][faulted][unit] = สัดส่วนของ kw แถวที่ไป UPS `unit` เมื่อ `faulted` พัง
    ถ้าแถวนั้นเสียบเข้ากับสมาชิกใน subset พอดี — สูตรเดียวใช้ได้ทั้ง pair (size=2, 2-source)
    และ quad (size=4, 4-source): แบ่งเท่ากันในหมู่สมาชิก subset ตอนปกติ (1/len(subset)) และ
    แบ่งเท่ากันในหมู่สมาชิกที่ยังไม่พังตอน fault เป็นสมาชิกของ subset นั้นเอง (1/(len(subset)-1))
    ถ้า fault ไม่ใช่สมาชิกของ subset แถวนี้ไม่ถูกกระทบเลย (ยังคงแบ่งแบบปกติ)"""
    coeff = {}
    for s in subsets:
        members = list(s)
        n_members = len(members)
        coeff[s] = {}
        for f in ups_units:
            in_subset = f in members
            survivors = [m for m in members if m != f]
            share = (1.0 / len(survivors)) if in_subset else (1.0 / n_members if n_members else 0.0)
            row_coeff = {}
            for u in ups_units:
                if u == f or u not in members:
                    row_coeff[u] = 0.0
                else:
                    row_coeff[u] = share
            coeff[s][f] = row_coeff
    return coeff


@functools.lru_cache(maxsize=None)
def _get_coeff_table(ups_units_tuple: tuple) -> dict:
    ups_units = list(ups_units_tuple)
    subsets = get_pairs(ups_units) + get_quads(ups_units)
    return _build_coeff_table(subsets, ups_units)


def evaluate_group_max_fail(grp: list[dict], ups_units: list) -> float:
    """คำนวณ max-fail-load ของกลุ่มเดียวจาก coeff table ล้วนๆ (ไม่พึ่ง MILP)
    ใช้เป็น evaluator อิสระสำหรับตรวจผลลัพธ์ MILP และสำหรับ brute-force cross-check
    ทุกแถว (ทั้ง 2-source และ 4-source) ต้องมี row['pair'] เป็น subset string ที่ตรงกับ
    source_type ของแถวนั้นแล้ว (2 ตัวอักษรสำหรับ 2-source, 4 ตัวอักษรสำหรับ 4-source)"""
    coeff = _get_coeff_table(tuple(ups_units))
    mx = 0.0
    for f in ups_units:
        for u in ups_units:
            if u == f:
                continue
            total = sum(row["kw"] * coeff[row["pair"]][f][u] for row in grp)
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


_CBC_BB_RE = re.compile(
    r"After\s+(?P<nodes>\d+)\s+nodes.*?"
    r"(?P<best>[\d.eE+-]+)\s+best solution,\s+best possible\s+(?P<bound>[\d.eE+-]+)"
)
_CBC_INCUMBENT_RE = re.compile(r"Integer solution of\s+(?P<val>[\d.eE+-]+)\s+found")
_CBC_ROOT_BOUND_RE = re.compile(r"cuts changed objective from\s+[\d.eE+-]+\s+to\s+(?P<bound>[\d.eE+-]+)")


def parse_cbc_progress(log_text: str) -> dict:
    """อ่านสถานะระหว่างรันจาก CBC log ที่ยัง solve ไม่เสร็จ (ต่าง _parse_cbc_log ที่คาดว่า log จบแล้ว)
    ใช้ข้อมูลล่าสุดที่เจอ — ไม่มีผลต่อการ solve เอง เป็นแค่การอ่านไฟล์ log ที่ CBC เขียนอยู่แล้วเฉยๆ

    หมายเหตุ: CBC ไม่ได้เข้า branch & bound (บรรทัด "After N nodes, ... best possible X") เสมอไป —
    เคสที่โมเดลใหญ่/ซับซ้อน มันอาจใช้เวลาทั้งหมดอยู่กับ root-node cut generation / feasibility pump
    (0 nodes ตลอด) ซึ่งไม่มีบรรทัดนั้นเลยทั้ง run ก่อนโดน time limit เลยต้อง fallback ไปอ่าน
    "Integer solution of X found" (best จาก incumbent ล่าสุด) และ "cuts changed objective from A
    to B" (bound จาก root-node cuts ล่าสุด) แทน เพื่อให้ยังมีอะไรให้โชว์ระหว่างช่วง cut generation"""
    bb_matches = list(_CBC_BB_RE.finditer(log_text))
    nodes = best = bound = None
    if bb_matches:
        last = bb_matches[-1]
        nodes = int(last.group("nodes"))
        best = float(last.group("best"))
        bound = float(last.group("bound"))
    else:
        incumbents = list(_CBC_INCUMBENT_RE.finditer(log_text))
        if incumbents:
            best = float(incumbents[-1].group("val"))
        root_bounds = list(_CBC_ROOT_BOUND_RE.finditer(log_text))
        if root_bounds:
            bound = float(root_bounds[-1].group("bound"))

    gap_pct = abs(best - bound) / abs(bound) * 100 if best is not None and bound not in (None, 0.0) else None
    return {
        "nodes": nodes,
        "best": best,
        "bound": bound,
        "gap_pct": gap_pct,
        "incumbent_count": len(_CBC_INCUMBENT_RE.findall(log_text)),
    }


def _add_subset_assignment_vars(prob, idx_list, subsets, y_expr, n_groups, var_prefix):
    """สร้าง binary var[i][g][subset] + equality constraint sum_subset var == y_expr(i,g)
    ใช้ร่วมกันทั้ง q[i][g][p] (2-source, subsets=pairs) และ q4[i][g][quad] (4-source, subsets=quads)"""
    var = {}
    for i in idx_list:
        for g in range(1, n_groups + 1):
            for s in subsets:
                var[i, g, s] = pulp.LpVariable(f"{var_prefix}_{i}_{g}_{s}", cat="Binary")
            prob += pulp.lpSum(var[i, g, s] for s in subsets) == y_expr(i, g)
    return var


def _build_objective(prob, n_groups, ups_units, two_idx, four_idx, row_units, q, q4, pairs, quads, y_expr):
    """สร้าง M >= โหลดทุกจุดที่เป็นไปได้ (ทุกกลุ่ม x ทุกกรณี UPS พัง x ทุก UPS ที่เหลือ)
    ใช้ร่วมกันทั้ง solve_pairing_milp / solve_pairing_milp_free"""
    coeff = _get_coeff_table(tuple(ups_units))
    M = pulp.LpVariable("M", lowBound=0)
    all_load_terms = []
    for g in range(1, n_groups + 1):
        for f in ups_units:
            for u in ups_units:
                if u == f:
                    continue
                terms = []
                for i in two_idx:
                    for p in pairs:
                        c = coeff[p][f][u]
                        if c != 0.0:
                            terms.append(c * row_units[i]["kw"] * q[i, g, p])
                for i in four_idx:
                    for qd in quads:
                        c = coeff[qd][f][u]
                        if c != 0.0:
                            terms.append(c * row_units[i]["kw"] * q4[i, g, qd])
                expr = pulp.lpSum(terms)
                prob += M >= expr
                all_load_terms.append(expr)
    prob += M + EPS_TIE_BREAK * pulp.lpSum(all_load_terms)
    return M


def _extract_solution(row_units, n, n_groups, y_expr, q, q4, pairs, quads, two_idx_set):
    groups_out = [[] for _ in range(n_groups)]
    for i in range(n):
        for g in range(1, n_groups + 1):
            val = y_expr(i, g)
            v = pulp.value(val) if not isinstance(val, int) else val
            if v is not None and v > 0.5:
                row = dict(row_units[i])
                if i in two_idx_set:
                    for p in pairs:
                        if pulp.value(q[i, g, p]) > 0.5:
                            row["pair"] = p
                            break
                else:
                    for qd in quads:
                        if pulp.value(q4[i, g, qd]) > 0.5:
                            row["pair"] = qd
                            break
                groups_out[g - 1].append(row)
                break
    return groups_out


def solve_pairing_milp(
    row_units: list[dict],
    n_groups: int,
    n_ups_per_group: int = DEFAULT_N_UPS_PER_GROUP,
    time_limit: int = DEFAULT_TIME_LIMIT,
    gap_rel: float = DEFAULT_GAP_REL,
    log_path: str | None = None,
) -> dict:
    """
    MILP เดียว รวม grouping (contiguous cut) + pairing (2-source) + quad-assignment (4-source)
    เพื่อ minimize max-fail-load ในบรรดาทุกกลุ่ม (ทุกกลุ่มใช้ UPS ขนาดเท่ากันและจำนวนเท่ากัน
    n_ups_per_group -> bottleneck ของกลุ่มที่แย่สุดเป็นตัวกำหนด sizing)

    Returns dict:
        groups: list[list[dict]]  แต่ละแถวมี 'pair' (2 ตัวอักษรถ้า 2-source, 4 ตัวอักษรถ้า 4-source)
        status: str               "Optimal" (proven) / "Time-limited (gap X%)" / อื่นๆ
        objective: float          max-fail-load ที่ได้ (M*)
        gap: float | None         relative gap ที่ CBC รายงาน ณ จุดหยุด (0 ถ้า proven optimal)
        solver_lower_bound: float | None   LP/B&B lower bound จริงจาก CBC (แน่นกว่า theoretical)
        theoretical_lower_bound: float     max(group total kw)/(n_ups_per_group-1) ของกลุ่มที่ได้ (ฟังก์ชัน sanity —
                                                หาร n_ups_per_group-1 เพราะเหลือผู้รอด n_ups_per_group-1 ตัวตอน fault)
        global_theoretical_lower_bound: float  (total kw ทั้งหมด / n_groups) / (n_ups_per_group-1) — floor ที่เป็นไปได้
                                                ในทางทฤษฎี ไม่ขึ้นกับคำตอบที่ solve ได้จริง
        n_ups_per_group: int      จำนวน UPS ต่อกลุ่มที่ใช้ solve ครั้งนี้
    """
    ups_units = get_group_ups_units(n_ups_per_group)
    pairs = get_pairs(ups_units)
    quads = get_quads(ups_units)

    n = len(row_units)
    two_idx = [i for i, r in enumerate(row_units) if r["source_type"] != "4-source"]
    four_idx = [i for i, r in enumerate(row_units) if r["source_type"] == "4-source"]
    two_idx_set = set(two_idx)

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

    # ── pairing (2-source) + quad-assignment (4-source) ผูกกับ grouping ผ่าน equality ──
    q = _add_subset_assignment_vars(prob, two_idx, pairs, y_expr, n_groups, "q")
    q4 = _add_subset_assignment_vars(prob, four_idx, quads, y_expr, n_groups, "q4")

    M = _build_objective(prob, n_groups, ups_units, two_idx, four_idx, row_units, q, q4, pairs, quads, y_expr)

    import tempfile, os
    # log_path: ถ้าผู้เรียกส่งมาเอง (เช่นจะ tail ไฟล์นี้ดู progress ระหว่าง solve) ให้ใช้ตามนั้นและ
    # ไม่ลบทิ้งหลัง solve — ผู้เรียกเป็นเจ้าของไฟล์และรับผิดชอบลบเอง ถ้าไม่ส่งมา พฤติกรรมเดิมทุกประการ
    own_log = log_path is None
    if own_log:
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
        if own_log:
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

    groups_out = _extract_solution(row_units, n, n_groups, y_expr, q, q4, pairs, quads, two_idx_set)

    objective_value = pulp.value(M)

    n_survivors = n_ups_per_group - 1
    theoretical_lb = max(sum(r["kw"] for r in grp) / n_survivors for grp in groups_out) if groups_out else 0.0
    total_kw_all = sum(r["kw"] for r in row_units)
    global_theoretical_lb = (total_kw_all / n_groups) / n_survivors

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
        "n_ups_per_group": n_ups_per_group,
    }


def solve_pairing_milp_free(
    row_units: list[dict],
    n_groups: int,
    n_ups_per_group: int = DEFAULT_N_UPS_PER_GROUP,
    time_limit: int = DEFAULT_TIME_LIMIT,
    gap_rel: float = DEFAULT_GAP_REL,
    warm_start_groups: list[list[dict]] | None = None,
    log_path: str | None = None,
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
    ups_units = get_group_ups_units(n_ups_per_group)
    pairs = get_pairs(ups_units)
    quads = get_quads(ups_units)

    n = len(row_units)
    two_idx = [i for i, r in enumerate(row_units) if r["source_type"] != "4-source"]
    four_idx = [i for i, r in enumerate(row_units) if r["source_type"] == "4-source"]
    two_idx_set = set(two_idx)

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

    # ── pairing (2-source) + quad-assignment (4-source) ผูกกับ grouping ผ่าน equality ──
    q = _add_subset_assignment_vars(prob, two_idx, pairs, y_expr, n_groups, "q")
    q4 = _add_subset_assignment_vars(prob, four_idx, quads, y_expr, n_groups, "q4")

    M = _build_objective(prob, n_groups, ups_units, two_idx, four_idx, row_units, q, q4, pairs, quads, y_expr)

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
    # log_path: ถ้าผู้เรียกส่งมาเอง (เช่นจะ tail ไฟล์นี้ดู progress ระหว่าง solve) ให้ใช้ตามนั้นและ
    # ไม่ลบทิ้งหลัง solve — ผู้เรียกเป็นเจ้าของไฟล์และรับผิดชอบลบเอง ถ้าไม่ส่งมา พฤติกรรมเดิมทุกประการ
    own_log = log_path is None
    if own_log:
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
        if own_log:
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

    groups_out = _extract_solution(row_units, n, n_groups, y_expr, q, q4, pairs, quads, two_idx_set)

    objective_value = pulp.value(M)

    n_survivors = n_ups_per_group - 1
    theoretical_lb = max(sum(r["kw"] for r in grp) / n_survivors for grp in groups_out) if groups_out else 0.0
    total_kw_all = sum(r["kw"] for r in row_units)
    global_theoretical_lb = (total_kw_all / n_groups) / n_survivors

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
        "n_ups_per_group": n_ups_per_group,
    }


def brute_force_pairing_check(grp: list[dict], ups_units: list, max_combos: int = MAX_BRUTE_FORCE_COMBOS) -> dict | None:
    """
    Cross-check: ตรึง grouping ตามที่ MILP หาได้ แล้ววน brute force หา pairing (2-source) +
    quad-assignment (4-source) ที่ optimal จริงสำหรับกลุ่มนี้ เพื่อยืนยันว่า MILP ไม่ได้ทำพลาด
    (เฉพาะกลุ่มที่ combos รวม <= max_combos เพราะโตเร็วมากถ้ามีทั้ง 2-source และ 4-source เยอะ)
    Returns None ถ้ากลุ่มมี combos รวมเกิน max_combos (ข้ามการเช็ค)
    """
    two_rows = [r for r in grp if r["source_type"] != "4-source"]
    four_rows = [r for r in grp if r["source_type"] == "4-source"]
    k2 = len(two_rows)
    k4 = len(four_rows)
    pairs = get_pairs(ups_units)
    quads = get_quads(ups_units)

    combos_two = len(pairs) ** k2
    combos_four = (len(quads) ** k4) if k4 else 1
    total_combos = combos_two * combos_four
    if total_combos > max_combos:
        return None

    best_max = float("inf")
    best_assignment = None
    two_choices = list(itertools.product(pairs, repeat=k2)) if k2 else [()]
    four_choices = list(itertools.product(quads, repeat=k4)) if k4 else [()]
    for two_combo in two_choices:
        for four_combo in four_choices:
            candidate = (
                [dict(r, pair=two_combo[j]) for j, r in enumerate(two_rows)]
                + [dict(r, pair=four_combo[j]) for j, r in enumerate(four_rows)]
            )
            val = evaluate_group_max_fail(candidate, ups_units)
            if val < best_max:
                best_max = val
                best_assignment = (two_combo, four_combo)

    milp_max = evaluate_group_max_fail(grp, ups_units)
    return {
        "brute_force_best": best_max,
        "milp_result": milp_max,
        "matches": abs(best_max - milp_max) < 1e-6,
        "best_pairing": best_assignment,
        "n_two_source": k2,
        "n_four_source": k4,
        "combinations_tried": total_combos,
    }


def build_proof_context(milp_result: dict, max_combos: int = MAX_BRUTE_FORCE_COMBOS) -> dict:
    """
    รวมทุกอย่างที่ต้องใช้ "แสดงผล" หรือ "สร้างเอกสาร proof" จาก milp_result เดียว —
    single source of truth ให้ ui/tab_proof.py (แสดงใน UI) และ engine/report_docx.py
    (สร้าง .docx) เรียกใช้ร่วมกัน ไม่คำนวณ evaluate_group_max_fail / brute_force_pairing_check
    ซ้ำกันคนละที่ (ผลอาจไม่ sync กันถ้าแก้ที่หนึ่งแล้วลืมอีกที่)
    """
    groups = milp_result["groups"]
    overall_max = milp_result["objective"]
    n_ups_per_group = milp_result.get("n_ups_per_group", DEFAULT_N_UPS_PER_GROUP)
    ups_units = get_group_ups_units(n_ups_per_group)
    group_checks = []
    for gi, grp in enumerate(groups, 1):
        group_max = evaluate_group_max_fail(grp, ups_units)
        is_bottleneck = abs(group_max - overall_max) < BOTTLENECK_TOL
        n_two = sum(1 for r in grp if r["source_type"] != "4-source")
        n_four = sum(1 for r in grp if r["source_type"] == "4-source")
        chk = brute_force_pairing_check(grp, ups_units, max_combos=max_combos)
        group_checks.append({
            "index": gi,
            "group": grp,
            "n_two_source": n_two,
            "n_four_source": n_four,
            "group_max": group_max,
            "is_bottleneck": is_bottleneck,
            "brute_force": chk,  # None ถ้าข้าม (combos รวม > max_combos)
        })
    return {
        "milp_result": milp_result,
        "overall_max": overall_max,
        "group_checks": group_checks,
        "max_combos": max_combos,
        "n_ups_per_group": n_ups_per_group,
    }
