from detection import AVAILABLE, BLOCKED, UNAVAILABLE, UNKNOWN, Result
from tracker import BLOCKED_WARNING_AFTER, PageTracker


def available(price):
    return Result(AVAILABLE, "", price, "EUR")


def kinds(tracker, results):
    return [event.kind if event else None for event in map(tracker.update, results)]


def test_one_alert_per_restock():
    tracker = PageTracker()
    out = Result(UNAVAILABLE, "")
    assert kinds(tracker, [out, available(549), available(549), out, available(549)]) == \
        [None, "available", None, None, "available"]


def test_unknown_check_does_not_repeat_the_alert():
    tracker = PageTracker()
    assert kinds(tracker, [available(549), Result(UNKNOWN, ""), available(549)]) == ["available", None, None]


def test_lower_price_sends_a_new_alert():
    tracker = PageTracker()
    assert kinds(tracker, [available(549), available(560), available(520)]) == ["available", None, "cheaper"]
    assert tracker.alerted_price == 520


def test_cheaper_event_carries_the_old_price():
    tracker = PageTracker()
    tracker.update(available(549))
    assert tracker.update(available(499)).old_price == 549


def test_blocked_warning_once():
    tracker = PageTracker()
    events = kinds(tracker, [Result(BLOCKED, "")] * (BLOCKED_WARNING_AFTER + 3))
    assert events.count("blocked") == 1
    assert events[BLOCKED_WARNING_AFTER - 1] == "blocked"
