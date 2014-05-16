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

def test_echo_post(test_app):
    resp = test_app.post('/echo', content_type='application/json', data=json.dumps({'first_param':'foo','second_param': 5 }))
    assert resp.status_code == 200
    assert resp.headers['Content-Type'] == 'application/json'
    data = json.loads(resp.data)
    assert data['content_type'] == 'application/json'
    assert data['content']['first_param'] == 'foo'
    assert data['content']['second_param'] == 5

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

# @pytest.mark.skipif(True, reason='Not implemented yet')
@pytest.mark.parametrize(
    ['controller', 'input', 'error'],
    [
        # Happy Path
        ['boil', {'interval': 5, 'duty': 0.5}, None],
        # If additional things are passed in, they don't 'take'
        ['boil', {'interval': 5, 'min_interval':20}, None],
        # If throw error for invalid values
        ['boil', {'interval': -3}, {'status_code': 400, 'error': 'interval must be between 1 and 10, inclusive'}],
        # If second param is invalid, throw error
        ['boil', {'interval': 5, 'duty': 2}, {'status_code': 400, 'error': 'duty cycle must be between 0 and 1, inclusive'}],
        ['faker_fakey', None, {'status_code':404, 'error': 'controller faker_fakey not found'}]
    ]
)
def test_controller_post(test_app, controller, input, error):
    checklist = ['name','interval','min_interval','max_interval','duty','dead_interval', 'class']
    before = test_app.get('/{}'.format(controller))
    before_data = json.loads(before.data)

    resp = test_app.post('/{}'.format(controller), content_type='application/json', data=json.dumps(input))
    assert resp.headers['Content-Type'] == 'application/json'
    data = json.loads(resp.data)

    after = test_app.get('/{}'.format(controller))
    after_data = json.loads(after.data)

    if error:
        assert resp.status_code == error['status_code']
        assert data['error'] == error['error']
        # With error, no changes happened!
        for key in checklist:
            if error['status_code'] == 404: 
                break
            assert before_data[key] == after_data[key]
    else:
        assert resp.status_code == 200
        for key in checklist:
            if key in ['duty', 'interval'] and key in input:
                assert data['old'][key] == before_data[key]
                assert data['new'][key] == input[key]
                assert data['new'][key] == after_data[key]
            else:
                assert before_data[key] == after_data[key]

def test_jason_io_content_type_error(test_app):
    resp = test_app.post('/echo', data = '{}')
    assert resp.status_code == 405
    assert resp.headers['Content-Type'] == 'application/json'
    data = json.loads(resp.data)
    assert data['error'] == 'Content-type must be application/json, not '


