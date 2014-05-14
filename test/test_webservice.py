#!/usr/bin/env python

import pytest
import mock
import StringIO

import json

from textwrap import dedent
from nose.tools import *

import pi_pwm.webservice

TEST_CONFIG = StringIO.StringIO(dedent("""\
    controllers:
        boil:
            class: BasePWMController
            args:
                interval: 1
                dead_interval: 3600
        sousvide:
            class: BasePWMController
            args:
                interval: 5
    """))

@pytest.fixture
def test_app():
    return pi_pwm.webservice.init_app(TEST_CONFIG).test_client()

def test_root_get(test_app):
    resp = test_app.get('/')
    assert resp.status_code == 200
    assert resp.headers['Content-Type'] == 'application/json'
    data = json.loads(resp.data)
    assert isinstance(data, dict)
    assert_items_equal(['boil', 'sousvide'], data.keys())
    assert data['boil']['interval'] == 1
    expected_list = ['name', 'interval', 'min_interval', 'max_interval', 'duty', 'dead_interval', 'dead_timer', 'class']
    for expected in expected_list:
        assert expected in data['boil']
