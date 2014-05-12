# pi-pwm #

PWM (Pulse Width Modulation) controller service for Raspberry Pi.

## controllers.py ##

pi_pwm.controllers contains classes intended to run as background threads and toggle outputs on and off based on *interval* and *duty* (duty cycle) parameters.  The main loop (contained in `run()`) will run approximately once every *interval* seconds, and the output will be on for *duty*% of each interval.

These controllers are not intended for use in applications that require precision output.  Intended loads are heating elements and DC pump motors (wired to the Pi's GPIO via solid state relays or similar).

### BasePWMController ###

This controller implements all of the consumer-facing methods.  The low-level hardware interfaces are stubbed out and must be replaced by child classes.

### SysFSPWMController ###

This controller class allows control of a GPIO pin that has been exported to sysfs (/sys/class/gpio/*).  This requires setup beforehand but has the benefit of not requiring root privileges once the pins are exported.  This has been developed for and tested on Raspbian 7 (wheezy).

#### Example export ####
    echo 24 | sudo tee /sys/class/gpio/export
    sudo chown -R *youruser* /sys/class/gpio/gpio24/
    echo out > /sys/class/gpio/gpio24/direction

#### Example usage ####
    >>> import pi_pwm.controllers
    >>> c = pi_pwm.controllers.SysFSPWMController(gpio_id=24)
    >>> c.duty = 50
    >>> c.start()
    # duty can be changed on the fly
    >>> c.duty = 20
    # so can interval, if you're so inclined
    >>> c.interval = 2
    # note that the output is not toggled at the end of the interval if duty is set to 0 or 100 (to help prevent short-cycling the load)
    >>> c.duty = 100
    # current values can be retrieved directly
    >>> c.duty
    100
    # the base class also implements an __iter__() method meaning you can dict() it
    >>> dict(c)
    {'duty': 100, 'dead_interval': 0, 'interval': 1, 'dead_timer': None}
    # when you're done, tell it to clean up and exit
    c.stop()
