from datetime import datetime, timedelta

from lib import timer


def test_time_conversion():
    assert timer.msec(1000) == timedelta(milliseconds=1000)
    assert timer.to_msec(timedelta(milliseconds=1000)) == 1000.0

    assert timer.msec_str(timedelta(milliseconds=1000)) == "1000"

    assert timer.seconds(1) == timedelta(seconds=1)
    assert timer.to_seconds(timedelta(seconds=1)) == 1.0

    assert timer.sec_str(timedelta(seconds=1)) == "1"

    assert timer.minutes(1) == timedelta(minutes=1)
    assert timer.hours(1) == timedelta(hours=1)
    assert timer.days(1) == timedelta(days=1)
    assert timer.years(1) == timedelta(days=365)

    assert timer.to_msec(timer.seconds(1)) == 1000.0
    assert timer.to_seconds(timer.minutes(1)) == 60.0
    assert timer.to_seconds(timer.hours(1)) == 3600.0
    assert timer.to_seconds(timer.days(1)) == 86400.0
    assert timer.to_seconds(timer.years(1)) == 31536000.0


def test_init_default():
    t = timer.Timer()
    assert t.duration == timedelta(0)
    assert t.starting_time is not None

def test_init_custom_duration():
    duration = timedelta(seconds=10)
    t = timer.Timer(duration)
    assert t.duration == duration
    assert t.starting_time is not None

def test_init_backdated_timestamp():
    backdated_timestamp = datetime.now() - timedelta(seconds=10)
    t = timer.Timer(backdated_timestamp=backdated_timestamp)
    assert t.starting_time is not None
    assert t.time_since_reset() >= timedelta(seconds=10)

def test_is_expired_not_expired():
    t = timer.Timer(timedelta(seconds=10))
    assert not t.is_expired()

def test_is_expired_expired():
    t = timer.Timer(timedelta(seconds=0))
    assert t.is_expired()

def test_is_expired_expired_after_reset():
    t = timer.Timer(timedelta(seconds=10))
    t.reset()
    t.starting_time -= 10
    assert t.is_expired()

def test_reset():
    t = timer.Timer(timedelta(seconds=10))
    t.reset()
    assert t.starting_time is not None
    assert timer.sec_str(t.time_since_reset()) == timer.sec_str(timedelta(0))

def test_time_since_reset():
    t = timer.Timer(timedelta(seconds=10))
    t.starting_time -= 5
    assert timer.sec_str(t.time_since_reset()) == timer.sec_str(timedelta(seconds=5))

def test_time_until_expiration():
    t = timer.Timer(timedelta(seconds=10))
    t.starting_time -= 5
    assert timer.sec_str(t.time_until_expiration()) == timer.sec_str(timedelta(seconds=5))

def test_time_until_expiration_expired():
    t = timer.Timer(timedelta(seconds=10))
    t.starting_time -= 15  # Simulate time passing
    assert t.time_until_expiration() == timedelta(0)

def test_starting_timestamp():
    t = timer.Timer(timedelta(seconds=10))
    timestamp_format = "%Y-%m-%d %H:%M:%S"
    expected_timestamp = (datetime.now() - t.time_since_reset()).strftime(timestamp_format)
    assert t.starting_timestamp(timestamp_format) == expected_timestamp

def test_time_until_expiration_max_zero():
    t = timer.Timer(timedelta(seconds=10))
    t.starting_time -= 15
    assert t.time_until_expiration() == timedelta(0)

def test_time_until_expiration_max_positive():
    t = timer.Timer(timedelta(seconds=10))
    t.starting_time -= 5
    assert timer.sec_str(t.time_until_expiration()) == timer.sec_str(timedelta(seconds=5))
