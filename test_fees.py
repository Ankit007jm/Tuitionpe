"""
Comprehensive test for all fee calculation scenarios.
Tests pro-rata, monthly, weekly, daily, per_class calculations.
Run: python test_fees.py
"""
import sys
import os
import math
from datetime import date
from calendar import monthrange

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Minimal Student mock for testing
class MockStudent:
    def __init__(self, fee_amount, payment_cycle='monthly', date_of_joining=None):
        self.fee_amount = fee_amount
        self.payment_cycle = payment_cycle
        self.date_of_joining = date_of_joining

# Import the function under test
from routes.fees import calculate_prorata_amount

passed = 0
failed = 0

def test(description, actual, expected, tolerance=0.01):
    global passed, failed
    if abs(actual - expected) <= tolerance:
        passed += 1
        print(f"  PASS: {description} -> {actual} (expected {expected})")
    else:
        failed += 1
        print(f"  FAIL: {description} -> {actual} (expected {expected})")


print("=" * 60)
print("TUITIONPE FEE CALCULATION TESTS")
print("=" * 60)

# ═══════════════════════════════════════════════════
# 1. MONTHLY — No date_of_joining (full fee)
# ═══════════════════════════════════════════════════
print("\n--- 1. Monthly: No date_of_joining (full fee) ---")
s = MockStudent(fee_amount=5000, payment_cycle='monthly', date_of_joining=None)
test("No DOJ -> full fee", calculate_prorata_amount(s, '2026-04'), 5000)

# ═══════════════════════════════════════════════════
# 2. MONTHLY — Joined on 1st (full month)
# ═══════════════════════════════════════════════════
print("\n--- 2. Monthly: Joined on 1st of month ---")
s = MockStudent(fee_amount=3000, payment_cycle='monthly', date_of_joining=date(2026, 4, 1))
test("Joined Apr 1 for Apr", calculate_prorata_amount(s, '2026-04'), 3000)

# ═══════════════════════════════════════════════════
# 3. MONTHLY — Joined mid-month (pro-rata)
# ═══════════════════════════════════════════════════
print("\n--- 3. Monthly: Joined mid-month (pro-rata) ---")
# April has 30 days, joining on 15th = 16 remaining days
s = MockStudent(fee_amount=3000, payment_cycle='monthly', date_of_joining=date(2026, 4, 15))
expected = round(3000 * 16 / 30, 2)
test("Joined Apr 15 for Apr (16/30 days)", calculate_prorata_amount(s, '2026-04'), expected)

# Joining on 25th = 6 remaining days
s = MockStudent(fee_amount=6000, payment_cycle='monthly', date_of_joining=date(2026, 4, 25))
expected = round(6000 * 6 / 30, 2)
test("Joined Apr 25 for Apr (6/30 days)", calculate_prorata_amount(s, '2026-04'), expected)

# Joining on last day = 1 day
s = MockStudent(fee_amount=3000, payment_cycle='monthly', date_of_joining=date(2026, 4, 30))
expected = round(3000 * 1 / 30, 2)
test("Joined Apr 30 for Apr (1/30 days)", calculate_prorata_amount(s, '2026-04'), expected)

# ═══════════════════════════════════════════════════
# 4. MONTHLY — Joined before the month (full fee)
# ═══════════════════════════════════════════════════
print("\n--- 4. Monthly: Joined before the month (full fee) ---")
s = MockStudent(fee_amount=4000, payment_cycle='monthly', date_of_joining=date(2026, 1, 10))
test("Joined Jan 10 for Apr", calculate_prorata_amount(s, '2026-04'), 4000)

s = MockStudent(fee_amount=4000, payment_cycle='monthly', date_of_joining=date(2025, 6, 1))
test("Joined Jun 2025 for Apr 2026", calculate_prorata_amount(s, '2026-04'), 4000)

# ═══════════════════════════════════════════════════
# 5. MONTHLY — Joined after the month (no fee)
# ═══════════════════════════════════════════════════
print("\n--- 5. Monthly: Joined after the month (zero fee) ---")
s = MockStudent(fee_amount=4000, payment_cycle='monthly', date_of_joining=date(2026, 5, 1))
test("Joined May 1 for Apr", calculate_prorata_amount(s, '2026-04'), 0.0)

# ═══════════════════════════════════════════════════
# 6. MONTHLY — February (28 days) and leap year
# ═══════════════════════════════════════════════════
print("\n--- 6. Monthly: February tests ---")
# 2026 is not a leap year, Feb has 28 days
s = MockStudent(fee_amount=2800, payment_cycle='monthly', date_of_joining=date(2026, 2, 15))
expected = round(2800 * 14 / 28, 2)
test("Joined Feb 15 2026 (14/28 days)", calculate_prorata_amount(s, '2026-02'), expected)

# 2028 IS a leap year, Feb has 29 days
s = MockStudent(fee_amount=2900, payment_cycle='monthly', date_of_joining=date(2028, 2, 15))
expected = round(2900 * 15 / 29, 2)
test("Joined Feb 15 2028 leap (15/29 days)", calculate_prorata_amount(s, '2028-02'), expected)

# ═══════════════════════════════════════════════════
# 7. WEEKLY — Pro-rata by remaining weeks
# ═══════════════════════════════════════════════════
print("\n--- 7. Weekly: Pro-rata by remaining weeks ---")
# April 30 days, 5 weeks (ceil), joining on 15th = 16 remaining days = 3 weeks (ceil)
s = MockStudent(fee_amount=1000, payment_cycle='weekly', date_of_joining=date(2026, 4, 15))
total_days = 30
remaining = 30 - 15 + 1  # 16
remaining_weeks = math.ceil(remaining / 7)  # 3
total_weeks = math.ceil(total_days / 7)  # 5
expected = round(1000 * remaining_weeks / total_weeks, 2)
test("Weekly: Joined Apr 15 (3/5 weeks)", calculate_prorata_amount(s, '2026-04'), expected)

# Joining on 1st = full fee
s = MockStudent(fee_amount=1000, payment_cycle='weekly', date_of_joining=date(2026, 4, 1))
test("Weekly: Joined Apr 1 (full)", calculate_prorata_amount(s, '2026-04'), 1000)

# ═══════════════════════════════════════════════════
# 8. DAILY — Always full rate (no proration)
# ═══════════════════════════════════════════════════
print("\n--- 8. Daily: Always full rate ---")
s = MockStudent(fee_amount=200, payment_cycle='daily', date_of_joining=date(2026, 4, 20))
test("Daily: Joined mid-month", calculate_prorata_amount(s, '2026-04'), 200)

s = MockStudent(fee_amount=200, payment_cycle='daily', date_of_joining=None)
test("Daily: No DOJ", calculate_prorata_amount(s, '2026-04'), 200)

# ═══════════════════════════════════════════════════
# 9. PER_CLASS — Always full rate (no proration)
# ═══════════════════════════════════════════════════
print("\n--- 9. Per Class: Always full rate ---")
s = MockStudent(fee_amount=500, payment_cycle='per_class', date_of_joining=date(2026, 4, 20))
test("Per Class: Joined mid-month", calculate_prorata_amount(s, '2026-04'), 500)

# ═══════════════════════════════════════════════════
# 10. Edge case — Joining on last day of month
# ═══════════════════════════════════════════════════
print("\n--- 10. Edge: Last day of month ---")
s = MockStudent(fee_amount=3100, payment_cycle='monthly', date_of_joining=date(2026, 1, 31))
expected = round(3100 * 1 / 31, 2)
test("Joined Jan 31 for Jan (1/31 days)", calculate_prorata_amount(s, '2026-01'), expected)

# Next month should be full
test("Joined Jan 31 for Feb (full)", calculate_prorata_amount(s, '2026-02'), 3100)

# ═══════════════════════════════════════════════════
# 11. MONTHLY — Paid early (already full month → should be full)
# ═══════════════════════════════════════════════════
print("\n--- 11. Monthly: Future month after join (full fee) ---")
s = MockStudent(fee_amount=5000, payment_cycle='monthly', date_of_joining=date(2026, 3, 10))
test("Joined Mar 10, fee for Apr (full)", calculate_prorata_amount(s, '2026-04'), 5000)
test("Joined Mar 10, fee for May (full)", calculate_prorata_amount(s, '2026-05'), 5000)

# ═══════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════
print("\n" + "=" * 60)
total = passed + failed
print(f"RESULTS: {passed}/{total} passed, {failed} failed")
if failed == 0:
    print("ALL TESTS PASSED!")
else:
    print("SOME TESTS FAILED — please review.")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
