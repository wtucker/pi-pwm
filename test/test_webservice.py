#!/usr/bin/env python

import pytest
import mock
import StringIO

import json
import yaml

from textwrap import dedent
from nose.tools import *

import pi_pwm.webservice

TEST_CONFIG = {
    'controllers': {
        'boil': {
            'class': 'BasePWMController',
            'args': {'interval': 1,'dead_interval': 3600}
        },
        'sousvide': {
            'class': 'BasePWMController',
            'args': {'interval': 5}
        }
    }
}

@pytest.fixture(scope='module')
def test_app():
    return pi_pwm.webservice.init_app(
        StringIO.StringIO(
            yaml.dump(TEST_CONFIG)
        )
    ).test_client()
     

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

@pytest.mark.parametrize(
    ['controller', 'expected', 'status'],
    [
        ['boil', {'old_dead_timer': int, 'dead_timer': 3600}, 200],
        ['sousvide',{'old_dead_timer': None, 'dead_timer': None}, 200],
        ['fakerfakey', {'error': 'controller fakerfakey not found'}, 404]
    ]
)
def test_controller_ping_get(test_app, controller, expected, status):
    resp = test_app.get('/{}/ping'.format(controller))
    assert resp.status_code == status
    assert resp.headers['Content-Type'] == 'application/json'
    data = json.loads(resp.data)
    if status != 200:
        assert data == expected
    else:
        for key, value in expected.iteritems():
            assert key in data
            if callable(value): #Case where don't care what value is
                assert type(data[key]) == value
            else:
                assert data[key] == value
                assert type(data[key]) == type(value)
            
@pytest.mark.parametrize(
    ['controller', 'expected', 'status'],
    [
        [ 
            'boil', 
            {
                'old': {'old_dead_timer': int, 'dead_timer': 3600}, 
                'new': {'old_dead_timer': int, 'dead_timer': 3600}
            },
            200
        ],
        [
            'sousvide',
            {
                'old': {'old_dead_timer': None, 'dead_timer': None},
                'new': {'old_dead_timer': None, 'dead_timer': None}
            },
            200
        ],
        [
            'fakerfakey',
            {
                'error': 'controller fakerfakey not found'
            }, 
            404
        ]
    ]
)
def test_controller_get(test_app, controller, expected, status):
    resp = test_app.get('/{}'.format(controller))
    assert resp.status_code == status
    assert resp.headers['Content-Type'] == 'application/json'
    data = json.loads(resp.data)
    if status != 200:
        assert data == expected
    else:
        expected_list = ['name', 'interval', 'min_interval', 'max_interval', 'duty', 'dead_interval', 'dead_timer', 'class']
        for key in expected_list:
            assert key in data
        for key, value in TEST_CONFIG['controllers'][controller][
        'args'].iteritems():
            assert data[key] == value

@pytest.mark.skipif(True, reason='Not implemented yet')
@pytest.mark.parametrize(
    ['controller', 'input', 'error'],
    [
        ['boil', {'interval': 5, 'dead_interval': 2000, 'duty': 0.5}, None],
        ['boil', {'interval': -3}, {'status_code': 400, 'error': 'Bad juju'}]
    ]
)
def test_controller_post(test_app, controller, input, error):
    pass
