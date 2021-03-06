#!/usr/bin/env python

import pytest
import mock
import tempfile
import StringIO
import itertools
import time

import yaml

from textwrap import dedent
from nose.tools import (
    assert_dict_equal, assert_dict_contains_subset, assert_raises
)
from pi_pwm import controllers
from pi_pwm.controllers import ConfigurationError

def is_exception(v):
    try:
        return issubclass(v, BaseException)
    except:
        return False

@pytest.fixture
def test_controller():
    return controllers.BasePWMController()


def test_dict(test_controller):
    """verify that __iter__() (used by dict()) works"""
    test_controller.duty = .1
    assert_dict_contains_subset(
        {
            'interval': 1,
            'duty': .1,
        },
        dict(test_controller)
    )


def test_on_off(test_controller):
    """verify that the controller turns the load off and on as expected"""
    with mock.patch("pi_pwm.controllers.BasePWMController._on", mock.Mock()) as _on:
        with mock.patch("pi_pwm.controllers.BasePWMController._off", mock.Mock()) as _off:
            assert _on.call_count == 0
            assert _off.call_count == 0
            # turn it on
            assert not test_controller.is_on
            assert test_controller.on()
            assert test_controller.is_on
            assert _on.call_count == 1
            assert _off.call_count == 0
            # attempt to turn it on while it's already on
            assert test_controller.on()
            assert test_controller.is_on
            assert _on.call_count == 1
            assert _off.call_count == 0
            # turn it off
            assert not test_controller.off()
            assert not test_controller.is_on
            assert _on.call_count == 1
            assert _off.call_count == 1
            # attempt to turn it off while it's already off
            assert not test_controller.off()
            assert not test_controller.is_on
            assert _on.call_count == 1
            assert _off.call_count == 1


@pytest.mark.parametrize(
    ["name", "low", "high", "value", "expected"],
    [
        ["foo", 0.0, 1.0, 1.0, 1.0],
        ["foo", 0.0, 10.0, 1, 1.0],
        ["foo", -1, 1, 0, 0.0],
        ["foo", 0.0, 10.0, 10.1, ValueError],
        ["foo", 0.0, 10.0, -1, ValueError],
    ]
)
def test_validate_float(test_controller, name, low, high, value, expected):
    if is_exception(expected):
        with assert_raises(expected) as ar:
            test_controller._validate_float(name, low, high, value)
    else:
        v = test_controller._validate_float(name, low, high, value)
        assert v == expected
        assert type(v) == float


@pytest.mark.parametrize(
    ["name", "low", "high", "value", "expected"],
    [
        ["foo", 0, 1, 1, 1],
        ["foo", 0, 10, 1.1, 1],
        ["foo", -1, 1, 0, 0],
        ["foo", 0, 10, 11, ValueError],
        ["foo", 0, 10, -1, ValueError],
    ]
)
def test_validate_integer(test_controller, name, low, high, value, expected):
    if is_exception(expected):
        with assert_raises(expected) as ar:
            test_controller._validate_integer(name, low, high, value)
    else:
        v = test_controller._validate_integer(name, low, high, value)
        assert v == expected
        assert type(v) == int


@pytest.mark.parametrize(
    ["interval", "expected", "extra"],
    [
        [controllers.DEFAULT_MIN_INTERVAL, controllers.DEFAULT_MIN_INTERVAL, None],
        [controllers.DEFAULT_MAX_INTERVAL, controllers.DEFAULT_MAX_INTERVAL, None],
        [1.1, 1.1, None],
        [1.5, 1.5, None],
        # out of bounds
        [controllers.DEFAULT_MIN_INTERVAL-1, ValueError, "interval must be between"],
        [controllers.DEFAULT_MAX_INTERVAL+1, ValueError, "interval must be between"],
    ]
)
def test_interval_validation(test_controller, interval, expected, extra):
    if is_exception(expected):
        with assert_raises(expected) as ar:
            test_controller.interval = interval
        if extra:
            if not extra in str(ar.exception):
                raise AssertionError(
                    "{} missing expected string '{}', got '{:s}' instead"
                    .format(expected, extra, ar.exception)
                )
    else:
        test_controller.interval = interval
        assert test_controller.interval == expected

@pytest.mark.parametrize(
    ["duty", "expected", "extra"],
    [
        [0, 0, None],
        [1, 1, None],
        [.1, .1, None],
        [.5, .5, None],
        # out of bounds
        [-1, ValueError, "duty cycle must be between"],
        [1.1, ValueError, "duty cycle must be between"],
    ]
)
def test_duty_validation(test_controller, duty, expected, extra):
    if is_exception(expected):
        with assert_raises(expected) as ar:
            test_controller.duty = duty
        if extra:
            if not extra in str(ar.exception):
                raise AssertionError(
                    "{} missing expected string '{}', got '{:s}' instead"
                    .format(expected, extra, ar.exception)
                )
    else:
        test_controller.duty = duty
        assert test_controller.duty == expected


def test_deadman(test_controller):
    DEAD_INTERVAL = 10
    # ping is noop if dead_interval isn't set
    assert not test_controller.ping()
    test_controller.dead_interval = DEAD_INTERVAL
    assert test_controller._dead_time is None
    t = time.time()
    with mock.patch('pi_pwm.controllers.time.time', mock.Mock()) as time_time:
        time_time.side_effect = itertools.repeat(t)
        # ordinarily the first ping() will be handled in run() - we have to do it manually since
        # run() isn't being called
        assert test_controller.ping() == DEAD_INTERVAL
        assert test_controller.dead_timer == DEAD_INTERVAL
        assert test_controller.on()
        assert not test_controller.off()
        # t+5 is still within dead_interval
        time_time.side_effect = itertools.repeat(t+5)
        assert test_controller.dead_timer == 5
        assert test_controller.on()
        assert not test_controller.off()
        # belt and suspenders ... t+10 is outside of dead_interval - make sure on() doesn't turn on the output
        time_time.side_effect = itertools.repeat(t+10)
        assert test_controller.dead_timer == 0
        assert not test_controller.on()
        assert not test_controller.off()
        # status of dead_timer shouldn't interfere with off()
        test_controller.is_on = True
        assert not test_controller.off()
        # make sure we recover when pinged
        time_time.side_effect = itertools.repeat(t+60)
        assert test_controller.ping() == DEAD_INTERVAL
        assert test_controller.dead_timer == DEAD_INTERVAL
        assert test_controller.on()
        assert not test_controller.off()
        # updating self.duty is an implicit ping
        time_time.side_effect = itertools.repeat(t+120)
        assert test_controller.dead_timer == -50
        assert not test_controller.on()
        test_controller.duty = .5
        assert test_controller.dead_timer == DEAD_INTERVAL
        assert test_controller.on()


@pytest.mark.parametrize(
    ["interval", "duty", "expected_on_duration", "expected_off_duration"],
    [
        # full off
        [1, 0, 0.0, 1.0],
        # full on
        [1, 1, 1.0, 0.0],
        # 25%
        [1, .25, .25, .75],
        # 25% with different interval
        [10, .25, 2.5, 7.5],
    ]
)
def test_calculate_durations(test_controller, interval, duty, expected_on_duration, expected_off_duration):
    test_controller.interval = interval
    test_controller.duty = duty
    on_duration, off_duration = test_controller._calculate_durations()
    assert expected_on_duration == on_duration
    assert expected_off_duration == off_duration


def test_body(test_controller):
    """verify that _body() works as expected"""
    with mock.patch("pi_pwm.controllers.BasePWMController.on", mock.Mock()) as on:
        with mock.patch("pi_pwm.controllers.BasePWMController.off", mock.Mock()) as off:
            with mock.patch("pi_pwm.controllers.time.sleep", mock.Mock()) as time_sleep:
                assert on.call_count == 0
                assert off.call_count == 0
                # if duty == 0 then off() should be called and on() should not
                test_controller.duty = 0
                test_controller._body()
                assert not on.called
                assert off.called
                assert time_sleep.called_once_with(test_controller.interval)
                # if duty == 1 then on() should be called and off() should not
                on.reset_mock()
                off.reset_mock()
                time_sleep.reset_mock()
                test_controller.duty = 1
                test_controller._body()
                assert on.called
                assert not off.called
                assert time_sleep.called_once_with(test_controller.interval)
                # cleanup
                on.reset_mock()
                off.reset_mock()
                time_sleep.reset_mock()
                test_controller.duty = .25
                test_controller._body()
                assert on.called
                assert off.called
                assert time_sleep.call_args_list == [mock.call(0.25), mock.call(0.75)]


def test_body_shutoff_on_deadman(test_controller):
    """verify that _body() behaves appropriately when the dead timer expires"""
    DEAD_INTERVAL = 10
    t = time.time()
    with mock.patch('pi_pwm.controllers.time.time', mock.Mock()) as time_time:
        with mock.patch('pi_pwm.controllers.time.sleep', mock.Mock()) as time_sleep:
            test_controller.dead_interval = DEAD_INTERVAL
            time_time.side_effect = itertools.repeat(t)
            test_controller.duty = 1
            assert not test_controller.is_on
            test_controller._body()
            assert test_controller.is_on
            # half-way to dead time
            time_time.side_effect = itertools.repeat(t+(DEAD_INTERVAL/2))
            test_controller._body()
            assert test_controller.is_on
            # dead time has expired
            time_time.side_effect = itertools.repeat(t+DEAD_INTERVAL)
            test_controller._body()
            assert test_controller.dead_timer == 0
            assert not test_controller.is_on
            # reset it
            test_controller.ping()
            test_controller._body()
            assert test_controller.dead_timer == 10
            assert test_controller.is_on

def test_run_normal_shutdown(test_controller):
    """verify that we exit correctly when stop() is called"""
    def body_side_effect(controller, off):
        for i in range(5):
            yield
        controller.stop()
        assert off.call_count == 1
        yield
        raise AssertionError("controller did not respond to shutdown")
    with mock.patch("pi_pwm.controllers.BasePWMController.off", mock.Mock()) as off:
        with mock.patch("pi_pwm.controllers.BasePWMController._body", mock.Mock()) as body:
            test_controller.duty = 1
            body.side_effect = body_side_effect(test_controller, off)
            assert off.call_count == 0
            test_controller.run()
            # .stop() calls .off() and it should also be called in the finally stanza
            assert off.call_count == 2


def test_run_unclean_shutdown(test_controller):
    def body_side_effect(controller):
        for i in range(5):
            yield
        raise RuntimeError("triggering unclean shutdown")
        yield
        raise AssertionError("controller did not respond to shutdown")
    with mock.patch("pi_pwm.controllers.BasePWMController.off", mock.Mock()) as off:
        with mock.patch("pi_pwm.controllers.BasePWMController._body", mock.Mock()) as body:
            test_controller.duty = 1
            body.side_effect = body_side_effect(test_controller)
            assert off.call_count == 0
            with assert_raises(RuntimeError) as ar:
                test_controller.run()
            assert not test_controller.is_on


def test_SysFSPWMController():
    f = StringIO.StringIO()
    with mock.patch("__builtin__.file", mock.Mock()) as m_file:
        m_file.side_effect = [f]
        controller = controllers.SysFSPWMController(gpio_id=24)
        m_file.assert_called_once_with(
            "/sys/class/gpio/gpio24/value",
            "w+",
            buffering=0
        )
        controller._on()
        f.seek(0)
        assert f.read() == "1"
        f.seek(0)
        controller._off()
        f.seek(0)
        assert f.read() == "0"


@pytest.mark.parametrize(
    ["config", "expected", "extra",],
    [
        [
            "foo:\n  bar:\n baz:",
            ConfigurationError,
            'error while loading configuration'
        ],
        [
            "hello",
            ConfigurationError,
            'top level of configuration must be a dict'
        ],
        [
            "not_controllers:",
            ConfigurationError,
            "'controllers' section missing"
        ],
        [
            dedent("""\
                controllers:
                    boil: nope
            """),
            ConfigurationError,
            "must be a dict, not "
        ],
        [
            dedent("""\
                controllers:
                    boil: {}
            """),
            ConfigurationError,
            "missing 'class' specification"
        ],
        [
            dedent("""\
                controllers:
                    boil:
                        class: ConfigurationError
            """),
            ConfigurationError,
            "is not a descendant"
        ],
        [
            dedent("""\
                controllers:
                    boil:
                        class: yaml
            """),
            ConfigurationError,
            "is not a class"
        ],
        [
            dedent("""\
                controllers:
                    boil:
                        class: BasePWMController
                        args: invalid
            """),
            ConfigurationError,
            "args must be a dict"
        ],
        [
            dedent("""\
                controllers:
                    boil:
                        class: BasePWMController
                        args: {}
                    mash:
                        class: BasePWMController
                        args: {}
            """),
            None,
            None
        ],
    ]
)
def test_from_config(config, expected, extra):
    cfg_fh = tempfile.NamedTemporaryFile(suffix='.yaml')
    cfg_fh.write(config)
    cfg_fh.seek(0)
    if is_exception(expected):
        for c in [cfg_fh.name, cfg_fh, StringIO.StringIO(config)]:
            with assert_raises(expected) as ar:
                controllers.from_config(c)
            if not extra in str(ar.exception):
                raise AssertionError(
                    "{} missing expected string '{}', got '{:s}' instead"
                    .format(expected, extra, ar.exception)
                )
    else:
        cf_fh = StringIO.StringIO(config)
        cf = yaml.load(cf_fh)
        cf_fh.seek(0)
        cons = controllers.from_config(cf_fh)
        assert sorted(cons) == sorted(cf['controllers'])

