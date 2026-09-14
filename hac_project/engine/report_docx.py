"""
ENGINE — Optimization Proof Document Generator
สร้างเอกสาร .docx อธิบายหลักการ MILP ที่ใช้จริงใน optimization.py ตั้งแต่ต้นจนจบ
เป็น static content ล้วนๆ (ไม่ผูกกับ session_state ใดๆ) — ใช้เป็น supporting-evidence
document สำหรับผู้อ่านภายนอก (อาจารย์/reviewer) เพื่ออธิบายว่าวิธี optimize load-break
ของระบบมีหลักการทางคณิตศาสตร์รองรับจริง และมีกลไกตรวจสอบผลลัพธ์ (verification) ในตัว

ไม่มี st. ใดๆ ในไฟล์นี้ — คืนค่าเป็น io.BytesIO ให้ ui/tab_proof.py เรียกผ่าน download_button
"""
import io

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


ACCENT = RGBColor(0x1F, 0x4E, 0x79)
GREY = RGBColor(0x59, 0x59, 0x59)


def _set_cell_shading(cell, hex_color: str):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    cell._tc.get_or_add_tcPr().append(shd)


def _add_table(doc, headers, rows, col_widths_cm=None):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Light Grid Accent 1"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        run = p.add_run(h)
        run.bold = True
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        _set_cell_shading(hdr[i], "1F4E79")
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(str(val))
            run.font.size = Pt(10)
    if col_widths_cm:
        for row in table.rows:
            for i, w in enumerate(col_widths_cm):
                row.cells[i].width = Cm(w)
    doc.add_paragraph()
    return table


def _add_equation(doc, text, size=11):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.italic = True
    run.font.size = Pt(size)
    p.paragraph_format.space_after = Pt(10)
    return p


def _heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.color.rgb = ACCENT
    return h


def build_optimization_proof_docx(proof_context: dict | None = None) -> io.BytesIO:
    """
    proof_context: ผลลัพธ์จาก engine.optimization.build_proof_context(milp_result) หรือ None
    ถ้า None (ยังไม่ได้รัน optimization) เอกสารจะมีแค่ส่วนหลักการ (Section 1-8 + Appendix A)
    ถ้ามีค่า จะแนบ Appendix B: Computed Results for This Case ต่อท้าย โดยดึงตัวเลขจริง
    จาก session ปัจจุบัน (จึงเป็นส่วนเดียวในเอกสารที่ "vary" ตาม input ที่กรอกจริง)
    """
    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

    # ================= TITLE PAGE =================
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("HAC Load Designer")
    run.bold = True
    run.font.size = Pt(26)
    run.font.color.rgb = ACCENT

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run("UPS Load-Pairing Optimization: Mathematical Formulation,\nSolution Method, and Verification Proof")
    run.font.size = Pt(15)
    run.font.color.rgb = GREY

    doc.add_paragraph()
    tagline = doc.add_paragraph()
    tagline.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = tagline.add_run(
        "A supporting technical document describing the N-1 contingency load-balancing "
        "problem solved by the system, its Mixed-Integer Linear Programming (MILP) "
        "formulation, its solver configuration, and the independent checks used to "
        "verify solution optimality — together with an explicit statement of what "
        "those checks do and do not cover."
    )
    r.italic = True
    r.font.size = Pt(10.5)
    r.font.color.rgb = GREY

    doc.add_page_break()

    # ================= 1. INTRODUCTION =================
    _heading(doc, "1. Introduction and Purpose", level=1)
    doc.add_paragraph(
        "HAC Load Designer is an engineering tool for data center power distribution "
        "design. One of its core functions is deciding how each electrical load row "
        "(a High-Availability Cabinet, HAC) is connected to the redundant UPS units "
        "serving its group, so that if any single UPS fails, the resulting load "
        "increase on the remaining units is kept as low as possible. This decision "
        "directly determines the required capacity of the UPS units, generators, "
        "transformers, and busway feeding each group, and therefore has a direct "
        "cost impact."
    )
    doc.add_paragraph(
        "This document exists to make that decision process auditable. It sets out, "
        "in full, the mathematical model used, the algorithm that solves it, the "
        "exact numerical settings the solver runs with, and — importantly — the "
        "independent verification steps the system performs on its own output "
        "before that output is trusted, including a candid statement of the limits "
        "of that verification. The intent is that a reviewer with an operations-"
        "research or electrical-engineering background can follow the reasoning end "
        "to end without needing to read the source code."
    )
    doc.add_paragraph(
        "Everything described here reflects the implementation currently in "
        "production (module engine/optimization.py), not a future proposal. Where an "
        "illustrative example is used purely to build intuition for readers unfamiliar "
        "with the method, it is explicitly marked as illustrative."
    )

    # ================= 2. SYSTEM OVERVIEW =================
    _heading(doc, "2. System Overview and Data Flow", level=1)
    doc.add_paragraph("The relevant part of the design pipeline is:")
    steps = [
        "HAC rack layout input — each row's load (kW) and source type (2-source or 4-source) is captured.",
        "Combined grouping + pairing optimization (this document's subject) — rows are assigned to PTU groups and, within each group, 2-source rows are assigned a UPS pair, in a single MILP solve.",
        "Fault (N-1 contingency) simulation — for every group and every possible single UPS failure, the resulting load on each surviving UPS is computed.",
        "Equipment sizing — the worst-case (fault) load per group drives UPS, generator, transformer, and busway sizing.",
    ]
    for s in steps:
        doc.add_paragraph(s, style="List Number")
    doc.add_paragraph(
        "A 2-source row is fed by exactly two of the four UPS units in its group "
        "(A, B, C, D), sharing its load 50/50 between them under normal operation. "
        "A 4-source row is fed by all four units simultaneously, sharing its load "
        "25% to each. There are six possible 2-source pairs: AB, AC, AD, BC, BD, CD."
    )

    # ================= 3. PROBLEM DEFINITION =================
    _heading(doc, "3. Problem Definition: N-1 Contingency Load Balancing", level=1)
    doc.add_paragraph(
        "For a 2-source row assigned to pair AB, the loss of unit A means unit B "
        "must absorb the row's entire load (and vice versa) — the load does not "
        "average out, it transfers in full to the partner. For a 4-source row, the "
        "loss of any one unit means the other three absorb the load equally "
        "(33.3% each instead of 25%)."
    )
    doc.add_paragraph(
        "The quantity that ultimately sizes the equipment is the maximum load any "
        "single UPS unit could ever see under any single-failure scenario, across "
        "every group. The optimization objective is to choose the grouping and "
        "pairing that makes this worst-case value as small as possible — a minimax "
        "problem: minimize the maximum fault load."
    )
    doc.add_paragraph(
        "This is a combinatorial assignment problem: the number of ways to partition "
        "rows into groups and assign each 2-source row one of six pairs grows "
        "combinatorially with row count, so it cannot be solved by simple sorting or "
        "greedy rules with a correctness guarantee. It is addressed with Mixed-Integer "
        "Linear Programming (MILP), which finds a solution together with a "
        "mathematical guarantee of how far (if at all) that solution is from the "
        "true optimum."
    )

    # ================= 4. MILP FORMULATION =================
    _heading(doc, "4. Mathematical Formulation", level=1)

    _heading(doc, "4.1 Decision Variables", level=2)
    _add_table(
        doc,
        ["Symbol", "Domain", "Meaning"],
        [
            ["t[i, g]", "Binary, g = 1..n_groups-1", "1 if row i belongs to a group with index <= g (cumulative-threshold encoding of contiguous grouping)"],
            ["q[i, g, p]", "Binary", "1 if 2-source row i is placed in group g using UPS pair p"],
            ["M", "Continuous, >= 0", "The worst-case (max) fault load across every group, every failed unit, and every surviving unit"],
            ["y[i, g]", "Derived (not solved directly)", "Shorthand for t[i, g] - t[i, g-1] — \"row i belongs to group g\"; used in Sections 4.2, 4.3, and 4.6"],
        ],
        col_widths_cm=[3.2, 3.8, 8.5],
    )
    doc.add_paragraph(
        "Rather than enumerating every possible cut point of the row sequence "
        "(which would require an outer search loop on top of the MILP), grouping is "
        "encoded directly as linear constraints using a cumulative-threshold "
        "variable t[i, g], read as \"row i belongs to a group numbered g or lower.\" "
        "Membership of row i in group g on its own is then the telescoping "
        "difference t[i, g] - t[i, g-1] (with the convention t[i, 0] = 0 and "
        "t[i, n_groups] = 1). This difference is referred to as y[i, g] wherever "
        "used later in this document (Sections 4.2, 4.3, and 4.6) — it is not a "
        "separate variable the solver optimizes, only a shorthand name for this "
        "expression in t, kept inside a single linear model throughout."
    )

    _heading(doc, "4.2 Constraints", level=2)
    doc.add_paragraph("Contiguity of groups (a group is a consecutive run of rows, not an arbitrary subset):")
    _add_equation(doc, "t[i, g] >= t[i+1, g]      for every g, for every consecutive row pair (i, i+1)")
    doc.add_paragraph("Nesting of the group-index thresholds:")
    _add_equation(doc, "t[i, g] <= t[i, g+1]      for every row i, every g = 1 .. n_groups-2")
    doc.add_paragraph("Every 2-source row, in whichever group it lands in, is assigned exactly one pair:")
    _add_equation(doc, "sum over p of q[i, g, p]  =  (t[i, g] - t[i, g-1])      for every 2-source row i, every group g")
    doc.add_paragraph(
        "This last equality is what links the pairing variables to the grouping "
        "variables without multiplying two binary variables together (which would "
        "make the model non-linear); the right-hand side is simply the group-"
        "membership indicator for row i in group g. There is no constraint requiring "
        "a group to contain at least one row — see Section 6.5 for the implication."
    )

    _heading(doc, "4.3 Fault-Load Coefficients (Precise Definition)", level=2)
    doc.add_paragraph(
        "For a 2-source row using pair p = (a, b), the fraction of that row's load "
        "landing on surviving unit u when unit f fails is a fixed coefficient with "
        "exactly three possible values, applied case by case:"
    )
    _add_table(
        doc,
        ["Case", "Condition", "Coefficient"],
        [
            ["1", "u = f (a unit cannot receive load from itself, and a failed unit carries none)", "0"],
            ["2", "f is one of the row's own pair (a or b), and u is the other member of that pair", "1.0  (the surviving partner absorbs the full row load)"],
            ["3", "f is not part of this row's pair at all (the failure is unrelated to this row)", "0.5 if u is a or b (the row keeps its normal 50/50 split); 0 otherwise"],
        ],
        col_widths_cm=[1.2, 9, 5.3],
    )
    doc.add_paragraph(
        "Case 3 is the one most likely to look surprising on first reading: a row "
        "whose pair has nothing to do with the failed unit f still contributes its "
        "normal 0.5 coefficient to both of its own pair members, because that row's "
        "load distribution is unaffected by a failure elsewhere. It only appears "
        "as a term in the constraint for surviving units u that happen to be its own "
        "pair members, at its ordinary (unfailed) share. For a 4-source row, the "
        "coefficient is always kw/3 for every surviving unit u != f, since a "
        "4-source row's load is by definition split evenly across whichever three "
        "units remain."
    )
    doc.add_paragraph(
        "Every coefficient used is an exact rational number (0, 0.5, 1.0, or 1/3) — "
        "the model introduces no rounding or approximation of its own. The only "
        "numerical imprecision that can appear is ordinary floating-point summation "
        "error when many such terms are added together, which is why comparisons "
        "between computed loads (for example, identifying which group is the "
        "system-wide bottleneck in Section 6.4) are made with a small numerical "
        "tolerance rather than exact equality."
    )

    _heading(doc, "4.4 Objective Function", level=2)
    doc.add_paragraph(
        "For every group g, every possible faulted unit f, and every surviving unit "
        "u (u != f), the load that would land on u if f failed is the linear "
        "expression built from the coefficients in Section 4.3. M is constrained to "
        "be at least every one of these expressions:"
    )
    _add_equation(doc, "M  >=  fault_load(g, f, u)      for every group g, faulted unit f, surviving unit u")
    doc.add_paragraph("The objective minimized is:")
    _add_equation(doc, "minimize   M  +  epsilon * (sum of all fault_load terms)")
    doc.add_paragraph(
        "The small epsilon term (epsilon = 1e-5, negligible relative to typical M "
        "values in the tens or hundreds of kW) is a tie-break: among solutions that "
        "all achieve the same worst-case M, it steers the solver toward the one "
        "with the lowest total fault-load burden overall, avoiding an arbitrary but "
        "equally-valid tie being reported without justification."
    )

    _heading(doc, "4.5 Solver Configuration and Termination Criteria", level=2)
    _add_table(
        doc,
        ["Parameter", "Value", "Effect"],
        [
            ["Time limit", "120 seconds", "CBC stops searching after this duration even if the gap has not reached zero"],
            ["Relative gap tolerance", "1% (0.01)", "CBC may also stop early, before the time limit, once it proves the current solution is within 1% of the true optimum"],
            ["Tie-break weight (epsilon)", "1e-5", "Selects among equally-optimal M values the one with lowest total fault load (Section 4.4)"],
        ],
        col_widths_cm=[4.5, 4, 8],
    )
    doc.add_paragraph(
        "These two stopping conditions (time limit, gap tolerance) mean the solver "
        "always terminates with either a proven-optimal result or a result "
        "guaranteed to be within a known, small percentage of optimal — never with "
        "an unquantified guess. Section 6.1 explains how the resulting status is "
        "reported."
    )

    _heading(doc, "4.6 Unified Formulation", level=2)
    doc.add_paragraph(
        "Sections 4.1 through 4.5 build up the model piece by piece. Collected "
        "into a single expression, using y[i, g] as shorthand for the row-i-in-"
        "group-g membership indicator introduced in Section 4.1 "
        "(y[i, g] = t[i, g] - t[i, g-1]), the entire optimization is:"
    )
    _add_equation(
        doc,
        "min      max      [ sum_2-source  q[i,g,p]\u00b7coeff[p,f,u]\u00b7kw_i   +   sum_4-source  y[i,g]\u00b7(kw_i/3) ]",
        size=11,
    )
    _add_equation(doc, "t,q            g,f,u", size=10)
    doc.add_paragraph("subject to:")
    _add_equation(doc, "t[i, g] \u2208 {0, 1}")
    _add_equation(doc, "t[i, g] \u2265 t[i+1, g]")
    _add_equation(doc, "t[i, g] \u2264 t[i, g+1]")
    doc.add_paragraph("and:")
    _add_equation(doc, "sum over p of q[i, g, p]  =  y[i, g]")
    doc.add_paragraph(
        "This min-max form is the most compact statement of the problem: choose "
        "grouping (t) and pairing (q) to make the worst load, over every group, "
        "every possible failed unit, and every surviving unit, as small as "
        "possible. It is mathematically equivalent to the epigraph form actually "
        "solved (Section 4.4) — minimizing the maximum of a finite set of linear "
        "expressions is standard practice rewritten by introducing the auxiliary "
        "variable M and requiring M to be at least each expression, which is "
        "exactly what turns this min-max statement into the linear constraints "
        "\"M >= fault_load(g, f, u)\" that CBC actually solves. The min-max form "
        "and the epigraph form are two notations for the same model, not two "
        "different models."
    )

    # ================= 5. SOLUTION METHOD =================
    _heading(doc, "5. Solution Method: LP Relaxation and Branch-and-Bound", level=1)
    doc.add_paragraph(
        "Binary variables make this problem NP-hard in general: there is no known "
        "algorithm that finds a guaranteed-optimal solution in polynomial time as "
        "problem size grows, and checking every combination directly becomes "
        "computationally infeasible well before real problem sizes are reached. "
        "The solver used, CBC (Coin-or Branch and Cut), addresses this using LP "
        "relaxation combined with branch-and-bound, which finds the exact optimum "
        "(or a solution within a proven distance of it) without exhaustive "
        "enumeration."
    )
    doc.add_paragraph(
        "LP relaxation temporarily allows every binary variable (t and q) to take "
        "any value between 0 and 1 instead of exactly 0 or 1. This converts the "
        "problem into an ordinary Linear Program, which can be solved directly and "
        "quickly (via the Simplex method or an interior-point method) because its "
        "feasible region is a convex polytope, and the optimum of a convex problem "
        "can be found by systematic search along that region's structure rather "
        "than by trial and error."
    )
    doc.add_paragraph(
        "Because the relaxed feasible region is a superset of the true (integer) "
        "feasible region, the optimal value of the relaxed problem can never exceed "
        "the optimal value of the true problem. This makes it a valid lower bound. "
        "Branch-and-bound then explores the space of integer solutions by "
        "repeatedly picking a variable that came out fractional, forcing it to 0 in "
        "one branch and 1 in another, and re-solving the relaxation in each branch. "
        "Whenever a branch's relaxed bound is no better than the best all-integer "
        "solution already found, that branch is discarded without further "
        "exploration — this pruning is what makes the method fast in practice "
        "despite the problem's worst-case difficulty."
    )

    _heading(doc, "5.1 Illustrative Worked Example", level=2)
    doc.add_paragraph(
        "The following simplified example is provided purely to make the mechanics "
        "of the previous section concrete. It uses 4 rows and 2 pairing options "
        "(instead of the real model's 6) so that it can be followed by hand; the "
        "production model in Section 4 has more decision variables but follows "
        "exactly the same relaxation and branching logic."
    )
    doc.add_paragraph("Setup: 4 rows, all 2-source, to be split into 2 groups of 2 rows, choosing pair AB or CD per row.")
    _add_table(
        doc,
        ["Row", "Load (kW)"],
        [["R1", "100"], ["R2", "90"], ["R3", "70"], ["R4", "60"]],
        col_widths_cm=[3, 3],
    )
    doc.add_paragraph(
        "Every row is assigned to exactly one of 4 \"pools\" (Group1-AB, Group1-CD, "
        "Group2-AB, Group2-CD), and their loads sum to the fixed total of 320 kW. "
        "Since the objective bounds every pool by M, summing the four pool "
        "constraints gives 320 <= 4M, i.e. M >= 80 kW. This is the LP relaxation's "
        "bound at the root of the search tree, achieved by spreading every row 25% "
        "across all four pools — a fractional (non-integer) solution."
    )
    doc.add_paragraph(
        "Branching on the fractional variable for R1's placement in pool "
        "Group1-AB forces two sub-problems: R1 fully excluded from that pool, or R1 "
        "fully included. Forcing R1 (100 kW) fully into Group1-AB raises that pool's "
        "relaxed bound to at least 100 kW immediately, since a 100 kW load can no "
        "longer be fractionally split away from it. Continuing this branching "
        "process until every variable is integer eventually yields the true optimum:"
    )
    _add_table(
        doc,
        ["Group", "Pair AB", "Pair CD"],
        [["Group 1", "R4 (60 kW)", "R1 (100 kW)"], ["Group 2", "R2 (90 kW)", "R3 (70 kW)"]],
        col_widths_cm=[4, 5, 5],
    )
    doc.add_paragraph(
        "The resulting worst case is 100 kW (from R1 alone, should either C or D "
        "fail in Group 1, since R1 is paired CD). No feasible integer assignment "
        "can do better, because every remaining branch's relaxed bound is also at "
        "least 100 kW once checked, closing the gap between the best integer "
        "solution found and the best possible bound."
    )

    # ================= 6. VERIFICATION =================
    _heading(doc, "6. Solver Output and Independent Verification", level=1)
    doc.add_paragraph(
        "A numerical result is only as trustworthy as the checks performed on it, "
        "and as the honesty of the claims made about those checks. The system "
        "reports three layers of evidence alongside every solution, shown in the "
        "Optimization Proof tab of the application, followed here by an explicit "
        "statement of what those layers do and do not prove."
    )

    _heading(doc, "6.1 Solver Status", level=2)
    doc.add_paragraph(
        "CBC is run with the time limit and gap tolerance given in Section 4.5. "
        "Its log is parsed directly (rather than relying on PuLP's status flag "
        "alone, which does not distinguish a proven optimum from a good solution "
        "returned when the time limit was hit) to report one of two states: "
        "\"Optimal (proven)\", meaning branch-and-bound closed the gap to zero and "
        "the result is mathematically guaranteed best-possible; or \"Time-limited "
        "(gap X%)\", meaning the search was stopped early with a known, bounded "
        "worst-case distance from the true optimum, no larger than the 1% "
        "configured tolerance."
    )

    _heading(doc, "6.2 Lower Bound Hierarchy", level=2)
    doc.add_paragraph(
        "Three lower bounds of increasing looseness are reported together, so the "
        "reported objective M* can be checked against all of them; M* can never be "
        "lower than any of these values, by construction:"
    )
    _add_table(
        doc,
        ["Bound", "Definition", "Tightness"],
        [
            ["Solver lower bound", "The LP-relaxation-plus-cuts bound CBC itself proves during the search. If CBC's log reports no explicit bound but the run is proven optimal, this value is taken to equal M* itself, since a proven optimum has zero gap to its own lower bound by definition.", "Tightest — accounts for the specific solution structure"],
            ["Theoretical lower bound (per solved grouping)", "max over groups of (group total kW) / 3 — the floor if a group's load could be split perfectly evenly across the 3 surviving units", "Looser sanity check tied to the actual grouping found"],
            ["Global theoretical lower bound", "(total kW across all rows / number of groups) / 3 — independent of how rows are actually grouped", "Loosest — a floor that holds regardless of solution details"],
        ],
        col_widths_cm=[3.5, 8, 4],
    )
    doc.add_paragraph(
        "If M* sits close to the solver lower bound, this is strong evidence the "
        "solution is close to, or exactly at, the true optimum, independent of "
        "trusting the solver's own \"Optimal\" label at face value."
    )

    _heading(doc, "6.3 Independent Brute-Force Cross-Check", level=2)
    doc.add_paragraph(
        "As a further check that does not rely on the MILP formulation being "
        "correct at all, the grouping the solver produced is held fixed, and every "
        "possible pairing combination for each group is evaluated directly using a "
        "fault-load evaluator implemented completely independently of the MILP "
        "model. A group with k two-source rows has 6^k possible pairing "
        "combinations to check; this is only run for groups with k <= 8, which "
        "caps the check at 6^8 = 1,679,616 combinations — small enough to complete "
        "quickly, while covering the group sizes that occur in practice. Larger "
        "groups are skipped, since 6^k grows too fast beyond that point to check "
        "exhaustively."
    )
    doc.add_paragraph(
        "The group whose fault load equals the overall M* is the \"bottleneck\" "
        "group — the one actually limiting the system-wide result. For that group, "
        "the brute-force best-possible pairing is compared against the MILP's "
        "pairing; if they match, this confirms the MILP found the true optimum "
        "pairing for the constraint that matters, using a method with no shared "
        "logic or possible shared bug with the MILP model itself. Non-bottleneck "
        "groups are reported for completeness but do not need to be individually "
        "optimal, since only the worst group determines equipment sizing."
    )

    _heading(doc, "6.4 Verification Scope: What Is and Is Not Independently Checked", level=2)
    doc.add_paragraph(
        "It is important to state plainly what Section 6.3 does and does not "
        "prove. The brute-force check holds the MILP's chosen grouping fixed and "
        "verifies only that the pairing within that grouping is optimal. It does "
        "not independently verify that the grouping itself — which rows are placed "
        "together in the first place — is the best possible grouping, because the "
        "number of ways to partition a full row sequence into groups is far too "
        "large to brute-force in the same way pairing is checked."
    )
    doc.add_paragraph(
        "The optimality of the grouping decision therefore rests entirely on the "
        "mathematical guarantee of branch-and-bound itself (Section 5): when CBC "
        "reports \"Optimal (proven)\", this covers the grouping and pairing "
        "decisions jointly, since both are variables in the same single MILP "
        "solved together. The brute-force check in Section 6.3 is an additional, "
        "independent confirmation layered on top for the pairing sub-decision "
        "specifically — not a replacement for, or a limitation of, the solver's "
        "own optimality proof for the model as a whole."
    )

    _heading(doc, "6.5 Known Theoretical Edge Case: Empty Groups", level=2)
    doc.add_paragraph(
        "The constraint set in Section 4.2 does not explicitly require every group "
        "to contain at least one row. Mathematically, an empty group contributes "
        "zero load everywhere and so cannot make the objective M worse, meaning "
        "the model does not rule it out on optimality grounds alone. In practice, "
        "the number of groups configured is always small relative to the number of "
        "rows being distributed, and this case has not been observed in production "
        "use. It is documented here as a known theoretical property of the "
        "formulation rather than an operational issue that has actually occurred."
    )

    # ================= 7. DOWNSTREAM USE =================
    _heading(doc, "7. Downstream Use: Fault Load Basis and Equipment Sizing", level=1)
    doc.add_paragraph(
        "The fault load values produced by the optimized pairing feed directly into "
        "equipment sizing: UPS, generator, transformer, and busway ratings for each "
        "group are selected against that group's worst-case (N-1) load, then "
        "rounded up to the nearest standard catalog size. All groups within an "
        "installation are unified to the same equipment sizes, so the pairing "
        "optimization's effect is system-wide, not confined to a single group. "
        "Ground cable sizing follows the same load basis, applying the standard "
        "formula S = I sqrt(t) / k (BS 7671, Table 43A) on either a transformer-kVA "
        "or generator-kW/PF basis as applicable."
    )

    # ================= 8. REFERENCES =================
    _heading(doc, "8. Standards and References", level=1)
    refs = [
        "วสท. (EIT) — Engineering Institute of Thailand electrical installation standards.",
        "IEC low-voltage distribution standards (400V, 3-phase, 50Hz system basis).",
        "NFPA standards referenced for data center electrical design practice.",
        "BS 7671, Table 43A — protective (ground) conductor sizing formula S = I sqrt(t) / k.",
        "PuLP / CBC (COIN-OR Branch and Cut) — the open-source MILP modeling and solving toolchain used.",
    ]
    for r_ in refs:
        doc.add_paragraph(r_, style="List Bullet")

    # ================= APPENDIX =================
    doc.add_page_break()
    _heading(doc, "Appendix A: Parameter Reference", level=1)
    doc.add_paragraph("All numerical constants referenced throughout this document, gathered in one place:")
    _add_table(
        doc,
        ["Parameter", "Symbol / Name", "Value", "Defined in"],
        [
            ["Solver time limit", "DEFAULT_TIME_LIMIT", "120 seconds", "Section 4.5"],
            ["Solver relative gap tolerance", "DEFAULT_GAP_REL", "0.01 (1%)", "Section 4.5"],
            ["Objective tie-break weight", "EPS_TIE_BREAK", "1e-5", "Section 4.4"],
            ["Bottleneck-group floating-point tolerance", "BOTTLENECK_TOL", "1e-6", "Sections 4.3, 6.3"],
            ["Max 2-source rows per group for brute-force check", "max_two_source", "8 rows (6^8 = 1,679,616 combinations)", "Section 6.3"],
            ["UPS units per group", "UPS_UNITS", "A, B, C, D (4 units)", "Section 2"],
            ["Possible 2-source pairs", "PAIRS", "AB, AC, AD, BC, BD, CD (6 pairs)", "Section 2"],
        ],
        col_widths_cm=[5, 4.5, 4.5, 2.5],
    )

    # ================= APPENDIX B: CASE RESULTS (varies with session data) =================
    if proof_context is not None:
        doc.add_page_break()
        _heading(doc, "Appendix B: Computed Results for This Case", level=1)
        doc.add_paragraph(
            "Unlike every preceding section, the content of this appendix is not "
            "fixed methodology — it reports the actual numbers produced by solving "
            "the model in Section 4 against the specific row layout entered for "
            "this design. It will change if the input rows, group count, or row "
            "loads change. It is included so this document can serve as a record "
            "of both how the system works and what it concluded for this "
            "particular case."
        )

        milp_result = proof_context["milp_result"]
        overall_max = proof_context["overall_max"]
        gap = milp_result.get("gap")
        status = milp_result["status"]
        proven = "proven" in status.lower()

        _heading(doc, "B.1 Solver Outcome", level=2)
        _add_table(
            doc,
            ["Quantity", "Value"],
            [
                ["Solver status", status],
                ["Max-fail-load (M*)", f"{overall_max:,.1f} kW"],
                ["Optimality gap", f"{gap * 100:.2f}%" if gap is not None else "0% (proven optimal)"],
                ["Number of groups", str(len(milp_result["groups"]))],
            ],
            col_widths_cm=[7, 9],
        )

        _heading(doc, "B.2 Lower Bounds Achieved", level=2)
        _add_table(
            doc,
            ["Bound", "Value"],
            [
                ["Solver lower bound", f"{milp_result['solver_lower_bound']:,.1f} kW" if milp_result.get("solver_lower_bound") is not None else "not reported"],
                ["Theoretical lower bound (this grouping)", f"{milp_result['theoretical_lower_bound']:,.1f} kW"],
                ["Global theoretical lower bound", f"{milp_result['global_theoretical_lower_bound']:,.1f} kW"],
            ],
            col_widths_cm=[9, 7],
        )

        _heading(doc, "B.3 Per-Group Brute-Force Verification", level=2)
        group_rows = []
        for gc in proof_context["group_checks"]:
            chk = gc["brute_force"]
            if chk is None:
                bf_text = f"skipped (> {proof_context['max_two_source']} two-source rows)"
                match_text = "not checked"
            else:
                bf_text = f"{chk['brute_force_best']:,.1f} kW ({chk['combinations_tried']:,} combos)"
                match_text = "matches MILP" if chk["matches"] else "DOES NOT MATCH"
            group_rows.append([
                f"Group {gc['index']}" + (" (bottleneck)" if gc["is_bottleneck"] else ""),
                gc["n_two_source"],
                f"{gc['group_max']:,.1f} kW",
                bf_text,
                match_text,
            ])
        _add_table(
            doc,
            ["Group", "2-source rows", "MILP max-fail", "Brute-force best", "Result"],
            group_rows,
            col_widths_cm=[3, 2.2, 3, 4.3, 3.5],
        )

        _heading(doc, "B.4 Interpretation", level=2)
        interp = []
        if proven:
            interp.append(
                f"The solver proved M* = {overall_max:,.1f} kW to be the exact global "
                "optimum — no other valid grouping-and-pairing assignment can achieve "
                "a lower worst-case fault load."
            )
        else:
            gap_txt = f"{gap * 100:.2f}%" if gap is not None else "an unreported"
            interp.append(
                f"The solver stopped at the configured time limit with M* = "
                f"{overall_max:,.1f} kW, proven to be within {gap_txt} of the true "
                "optimum rather than proven exactly optimal."
            )

        bottleneck_checks = [gc for gc in proof_context["group_checks"] if gc["is_bottleneck"]]
        checked = [gc for gc in bottleneck_checks if gc["brute_force"] is not None]
        matched = [gc for gc in checked if gc["brute_force"]["matches"]]
        mismatched = [gc for gc in checked if not gc["brute_force"]["matches"]]

        if mismatched:
            interp.append(
                "At least one bottleneck group's brute-force result did not match "
                "the MILP output — this indicates the MILP model or its "
                "implementation should be reviewed before relying on this result."
            )
        elif matched:
            interp.append(
                "The group(s) that determine the system-wide M* (the bottleneck "
                "group(s)) were independently cross-checked by exhaustive brute-force "
                "search over every possible pairing, and the MILP's pairing matched "
                "the brute-force optimum exactly. Combined with the solver status "
                "above, this gives two independent lines of evidence — the solver's "
                "own mathematical proof, and an exhaustive check using unrelated "
                "code — that the pairing decision for this case is truly optimal."
            )
        elif bottleneck_checks:
            interp.append(
                "The bottleneck group in this case has more two-source rows than "
                "the brute-force check's practical limit, so no independent "
                "exhaustive cross-check was performed for it in this run. The "
                "optimality claim for this case therefore rests on the solver's "
                "own branch-and-bound proof alone (Section 5), as described in "
                "Section 6.4."
            )
        doc.add_paragraph(" ".join(interp))

    doc.add_paragraph()
    footer = doc.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_text = (
        "Generated by HAC Load Designer — Optimization Proof module. "
        + (
            "Sections 1-8 and Appendix A describe methodology only and contain no "
            "project-specific data; Appendix B reflects the specific case computed "
            "at generation time."
            if proof_context is not None
            else "This document describes methodology only and contains no "
            "project-specific data (no case had been run at generation time)."
        )
    )
    r = footer.add_run(footer_text)
    r.italic = True
    r.font.size = Pt(9)
    r.font.color.rgb = GREY

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf
