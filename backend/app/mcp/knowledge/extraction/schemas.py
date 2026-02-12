# app/mcp/knowledge/extraction/schemas.py
"""
Extraction Schemas for Company Regulations
==========================================
Định nghĩa few-shot examples dạy langextract cách trích xuất
kiến thức có cấu trúc từ các văn bản quy định của công ty.

Mỗi schema bao gồm:
- ExampleData: đoạn text mẫu từ tài liệu
- Extraction: entity được trích xuất kèm attributes

langextract sẽ dùng các ví dụ này để hiểu cách trích xuất
từ toàn bộ tài liệu thực tế.
"""


# ===================================================================
# FEW-SHOT EXAMPLES
# ===================================================================
# Mỗi example gồm: input text + expected extractions
# langextract dùng format dict thay vì dataclass khi gọi qua API

LEAVE_POLICY_EXAMPLES = [
    {
        "text": (
            "NLĐ làm việc đủ 12 tháng: 12 ngày phép/năm, hưởng nguyên lương "
            "(tương ứng 01 ngày phép/tháng).\n"
            "NLĐ làm việc dưới 12 tháng: tính theo tỷ lệ tương ứng với số tháng "
            "thực tế làm việc."
        ),
        "extractions": [
            {
                "class": "LeaveRule",
                "text": "12 ngày phép/năm, hưởng nguyên lương",
                "attributes": {
                    "rule_type": "annual_leave_entitlement",
                    "condition": "làm việc đủ 12 tháng",
                    "duration": "12 ngày",
                    "period": "năm",
                    "pay_status": "hưởng nguyên lương",
                    "monthly_equivalent": "01 ngày/tháng"
                }
            },
            {
                "class": "LeaveRule",
                "text": "tính theo tỷ lệ tương ứng với số tháng thực tế làm việc",
                "attributes": {
                    "rule_type": "prorated_leave",
                    "condition": "làm việc dưới 12 tháng",
                    "calculation_method": "tỷ lệ theo số tháng thực tế"
                }
            },
        ]
    },
    {
        "text": (
            "Theo Bộ luật Lao động (Điều 65 Nghị định 145/2020/NĐ-CP): "
            "Thời gian thử việc được tính là thời gian làm việc để tính số ngày "
            "nghỉ hằng năm, nếu NLĐ tiếp tục làm việc cho công ty sau khi hết "
            "thời gian thử việc (tức là được nhận chính thức).\n"
            "Trong thời gian thử việc, ngày phép được tích lũy nhưng chưa sử dụng được. "
            "Khi được nhận chính thức, hệ thống sẽ truy cộng (backdate) số ngày phép "
            "đã tích lũy trong giai đoạn thử việc."
        ),
        "extractions": [
            {
                "class": "LeaveRule",
                "text": "Thời gian thử việc được tính là thời gian làm việc",
                "attributes": {
                    "rule_type": "probation_leave_counting",
                    "condition": "tiếp tục làm việc sau thử việc",
                    "legal_reference": "Điều 65 Nghị định 145/2020/NĐ-CP",
                    "mechanism": "truy cộng (backdate) khi nhận chính thức",
                    "during_probation": "tích lũy nhưng chưa sử dụng được"
                }
            },
        ]
    },
    {
        "text": (
            "Mỗi tháng làm việc (đủ điều kiện ≥50% ngày công), NLĐ tích lũy 01 ngày phép.\n"
            "Số ngày nghỉ phép sẽ được cộng vào ngày đầu tiên của tháng tiếp theo "
            "(tức phép tháng 7 sẽ được cộng vào ngày 01/08).\n"
            "NLĐ không được ứng trước ngày nghỉ phép của các tháng sau."
        ),
        "extractions": [
            {
                "class": "LeaveRule",
                "text": "Mỗi tháng làm việc (đủ điều kiện ≥50% ngày công), NLĐ tích lũy 01 ngày phép",
                "attributes": {
                    "rule_type": "monthly_leave_accrual",
                    "condition": "đủ ≥50% ngày công trong tháng",
                    "duration": "01 ngày",
                    "period": "tháng"
                }
            },
            {
                "class": "LeaveRule",
                "text": "cộng vào ngày đầu tiên của tháng tiếp theo",
                "attributes": {
                    "rule_type": "leave_credit_timing",
                    "mechanism": "cộng vào ngày 01 của tháng kế tiếp",
                    "example": "phép tháng 7 cộng vào 01/08"
                }
            },
            {
                "class": "LeaveRule",
                "text": "NLĐ không được ứng trước ngày nghỉ phép của các tháng sau",
                "attributes": {
                    "rule_type": "leave_advance_prohibition",
                    "restriction": "không được ứng trước phép tháng sau"
                }
            },
        ]
    },
]


WORKING_TIME_EXAMPLES = [
    {
        "text": (
            "Khối chức năng:\n"
            "Ngày làm việc: Từ thứ 2 đến thứ 6.\n"
            "Giờ làm việc:\n"
            "Buổi sáng: Từ 8h30 đến 12h (Sau 8h40 sẽ bị tính là đi muộn).\n"
            "Buổi chiều: Từ 13h đến 17h30."
        ),
        "extractions": [
            {
                "class": "WorkingTimeRule",
                "text": "Từ thứ 2 đến thứ 6",
                "attributes": {
                    "rule_type": "working_days",
                    "days": "thứ 2 đến thứ 6",
                    "applies_to": "khối chức năng"
                }
            },
            {
                "class": "WorkingTimeRule",
                "text": "Từ 8h30 đến 12h (Sau 8h40 sẽ bị tính là đi muộn)",
                "attributes": {
                    "rule_type": "working_hours_morning",
                    "start": "8h30",
                    "end": "12h",
                    "late_threshold": "8h40"
                }
            },
            {
                "class": "WorkingTimeRule",
                "text": "Từ 13h đến 17h30",
                "attributes": {
                    "rule_type": "working_hours_afternoon",
                    "start": "13h",
                    "end": "17h30"
                }
            },
        ]
    },
]


BENEFIT_EXAMPLES = [
    {
        "text": (
            "Nghỉ việc riêng hưởng lương:\n"
            "Bản thân kết hôn: 03 ngày.\n"
            "Con đẻ, con nuôi kết hôn: 01 ngày.\n"
            "Cha đẻ, mẹ đẻ, cha nuôi, mẹ nuôi; vợ hoặc chồng; con đẻ, con nuôi chết: 03 ngày."
        ),
        "extractions": [
            {
                "class": "BenefitRule",
                "text": "Bản thân kết hôn: 03 ngày",
                "attributes": {
                    "rule_type": "special_leave_paid",
                    "event": "bản thân kết hôn",
                    "duration": "03 ngày",
                    "pay_status": "hưởng lương"
                }
            },
            {
                "class": "BenefitRule",
                "text": "Con đẻ, con nuôi kết hôn: 01 ngày",
                "attributes": {
                    "rule_type": "special_leave_paid",
                    "event": "con đẻ/con nuôi kết hôn",
                    "duration": "01 ngày",
                    "pay_status": "hưởng lương"
                }
            },
            {
                "class": "BenefitRule",
                "text": "Cha đẻ, mẹ đẻ, cha nuôi, mẹ nuôi; vợ hoặc chồng; con đẻ, con nuôi chết: 03 ngày",
                "attributes": {
                    "rule_type": "special_leave_paid",
                    "event": "người thân qua đời (cha mẹ, vợ/chồng, con)",
                    "duration": "03 ngày",
                    "pay_status": "hưởng lương"
                }
            },
        ]
    },
]

MATERNITY_EXAMPLES = [
    {
        "text": (
            "Nghỉ thai sản nữ: 06 tháng.\n"
            "Nghỉ thai sản nam (vợ sinh):\n"
            "Sinh thường: 05 ngày.\n"
            "Sinh mổ, sinh con dưới 32 tuần: 07 ngày.\n"
            "Sinh đôi: 10 ngày (sinh 3 trở lên: thêm 03 ngày/con)."
        ),
        "extractions": [
            {
                "class": "BenefitRule",
                "text": "Nghỉ thai sản nữ: 06 tháng",
                "attributes": {
                    "rule_type": "maternity_leave_female",
                    "duration": "06 tháng",
                    "pay_status": "BHXH"
                }
            },
            {
                "class": "BenefitRule",
                "text": "Sinh thường: 05 ngày",
                "attributes": {
                    "rule_type": "paternity_leave",
                    "condition": "sinh thường",
                    "duration": "05 ngày",
                    "pay_status": "BHXH"
                }
            },
        ]
    },
]


# ===================================================================
# PROMPT DESCRIPTION cho langextract
# ===================================================================

REGULATION_EXTRACTION_PROMPT = """Extract all rules, policies, entitlements, conditions, and regulations from Vietnamese company labor documents.

Entity classes to extract:
- LeaveRule: Rules about annual leave, sick leave, probation leave, leave accrual, leave advance
- WorkingTimeRule: Rules about working hours, working days, overtime, lateness
- BenefitRule: Rules about special leave, maternity, wedding, funeral, allowances
- DisciplinaryRule: Rules about disciplinary actions, termination, violations
- FinancialRule: Rules about loans, expense allowances, travel budgets
- ProcedureRule: Rules about procedures (leave request timing, resignation notice)

For each rule, capture these attributes where applicable:
- rule_type: Specific category (e.g. annual_leave_entitlement, probation_leave_counting, working_hours_morning)
- condition: When/who this rule applies to
- duration: Time period or number of days
- amount: Monetary values if applicable
- calculation_method: How to compute (if applicable)
- mechanism: How it works in practice
- pay_status: Paid/unpaid/BHXH (if applicable)
- applies_to: Who this applies to (if specified)
- legal_reference: Legal basis if cited
- restriction: Any prohibition or limitation
- example: Concrete example if provided in text

Extract text must be copied verbatim from the source document."""


# ===================================================================
# ALL EXAMPLES combined for extraction
# ===================================================================

ALL_EXAMPLES = (
    LEAVE_POLICY_EXAMPLES
    + WORKING_TIME_EXAMPLES
    + BENEFIT_EXAMPLES
    + MATERNITY_EXAMPLES
)
