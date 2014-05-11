#!/usr/bin/env python

import logging
import threading
import time
import sys

import yaml

from contextlib import closing

MIN_INTERVAL = 1
MAX_INTERVAL = 10

log = logging.getLogger(__name__)


class ConfigurationError(ValueError):
    pass


class BasePWMController(threading.Thread):
    """A base (non-functional) PWM controller class

    Parameters
    ----------
    interval : int
        The cycle interval, in seconds.  Must be between MIN_INTERVAL and MAX_INTERVAL,
        inclusive.

    """
    def __init__(self, interval=1, dead_interval=0, *args, **kwargs):
        super(BasePWMController, self).__init__(*args, **kwargs)
        self.lock = threading.Lock()
        self.interval = interval
        self.dead_interval = dead_interval
        # internals
        self.dead_time = None
        self.shutdown = False
        self.is_on = False
        # must be set after the internals
        self.duty = 0

    def __iter__(self):
        for k in ["interval", "duty", "dead_interval", "dead_timer"]:
            yield (k, getattr(self, k))

    def __del__(self):
        self.off()

    def _on(self):  # pragma: no cover
        """low level function to turn on the output (stub to be overridden by subclasses)"""
        pass

    def _off(self):  # pragma: no cover
        """low level function to turn off the output (stub to be overridden by subclasses)"""
        pass

    def on(self):
        if not self.is_on:
            if self.dead_interval and self.dead_timer <= 0:
                log.warn("dead timer has expired by %d seconds; refusing to enable output", abs(self.dead_time))
                return self.is_on
            with self.lock:
                self.is_on = True
                self._on()
        return self.is_on

    def off(self):
        if self.is_on:
            with self.lock:
                self.is_on = False
                self._off()
        return self.is_on

    @staticmethod
    def _validate_integer(name, low, high, value):
        value = int(round(value))
        if value < low or value > high:
            raise ValueError(
                "{} must be between {} and {}, inclusive"
                .format(name, low, high)
            )
        return value

    def get_interval(self):
        with self.lock:
            return self._interval

    def set_interval(self, interval):
        interval = self._validate_integer("interval", MIN_INTERVAL, MAX_INTERVAL, interval)
        with self.lock:
            self._interval = interval

    interval = property(
        get_interval,
        set_interval,
        None,
        "the duration of each cycle"
    )

    def get_duty(self):
        with self.lock:
            return self._duty

    def set_duty(self, duty):
        duty = self._validate_integer("duty cycle", 0, 100, duty)
        with self.lock:
            self._duty = duty
        self.ping()

    duty = property(
        get_duty,
        set_duty,
        None,
        "the percentage of time (expressed as an integer between 0 and 100) that the output should be on for each cycle"
    )

    def ping(self):
        with self.lock:
            if not self.dead_interval:
                return None
            self.dead_time = time.time() + self.dead_interval
            return self.dead_interval

    @property
    def dead_timer(self):
        with self.lock:
            if not self.dead_time:
                return None
            return int(self.dead_time - time.time())

    def _calculate_durations(self):
        on_duration = self.interval * (self.duty / 100.0)
        off_duration = self.interval - on_duration
        return [on_duration, off_duration]

    def _body(self):
        if self.dead_interval and self.dead_timer <= 0:
            if self.is_on:
                log.warn("dead timer has expired; disabling output")
                self.off()
                time.sleep(self.interval)
                return
        on_duration, off_duration = self._calculate_durations()
        if not on_duration:
            self.off()
            time.sleep(off_duration)
        elif not off_duration:
            self.on()
            time.sleep(on_duration)
        else:
            self.on()
            time.sleep(on_duration)
            self.off()
            time.sleep(off_duration)

    def run(self):
        self.shutdown = False
        self.ping()
        try:
            while not self.shutdown:
                self._body()
        finally:
            self.off()

    def stop(self):
        with self.lock:
            self.shutdown = True


class SysFSPWMController(BasePWMController):
    def __init__(self, gpio_id, *args, **kwargs):
        super(SysFSPWMController, self).__init__(*args, **kwargs)
        self.gpio_id = gpio_id
        self.gpio = file(
            "/sys/class/gpio/gpio{}/value".format(gpio_id),
            "w+",
            buffering=0
        )

    def _on(self):
        self.gpio.write("1")

    def _off(self):
         self.gpio.write("0")


def from_config(config_file):
    """Initialize one or more PWM controllers from a configuration file

    Parameters
    ----------
    config_file : str or file_like
        The file containing the configuration.  Can be a string (to be interpreted as the
        path to the file) or an open file handle.

    Returns
    -------
    dict
        A dictionary containing the controllers as defined in config_file

    Raises
    ------
    IOError
        If config_file cannot be opened or read.
    ConfigurationError
        If a syntax or content problem is encountered in config_file

    Any errors encountered while initializing the controllers are sent through
    unaltered.

    """
    if isinstance(config_file, basestring):
        config_file = file(config_file, 'r')
    config_name = getattr(config_file, 'name', '<stream>')
    log.debug("using configuration from %s", config_name)
    with closing(config_file):
        try:
            config = yaml.load(config_file)
        except yaml.YAMLError as e:
            raise ConfigurationError(
                "error while loading configuration from '{}': {:s}"
                .format(config_name, e)
            )
    controllers = {}
    if not isinstance(config, dict):
        raise ConfigurationError(
            "top level of configuration must be a dict, not '{:s}'"
            .format(type(config))
        )
    if not 'controllers' in config:
        raise ConfigurationError(
            "'controllers' section missing from configuration file '{}'"
            .format(config_name)
        )
    for cname, ccfg in sorted(config['controllers'].iteritems()):
        if not isinstance(ccfg, dict):
            raise ConfigurationError(
                "controller '{}' must be a dict, not '{:s}'"
                .format(cname, type(ccfg))
            )
        if not 'class' in ccfg:
            raise ConfigurationError(
                "controller '{}' missing 'class' specification"
                .format(cname)
            )
        cclass = getattr(sys.modules[__name__], ccfg['class'], None)
        try:
            if not issubclass(cclass, BasePWMController):
                raise ConfigurationError(
                    "controller '{}' class '{}' is not a descendant of BasePWMController"
                    .format(cname, ccfg['class'])
                )
        except TypeError:
            raise ConfigurationError(
                "controller '{}' class '{}' is not a class"
                .format(cname, cclass)
            )
        cargs = ccfg.get('args', {})
        if not isinstance(cargs, dict):
            raise ConfigurationError(
                "controler '{}' args must be a dict, not '{:s}'"
                .format(cname, type(cargs))
            )
        controllers[cname] = cclass(**cargs)
    return controllers
