#!/usr/bin/env python

import logging
import atexit
import functools
import json
import os

import pi_pwm.controllers

from flask import Flask, request
from werkzeug.wrappers import Response

log = logging.getLogger(__name__)

controllers = {}
initialized = False

def create_app(config_file):
    app = Flask("pi_pwm")
    app.config['DEBUG'] = True

    #app.logger.addHandler(logging.StreamHandler())
    app.logger.setLevel(logging.INFO)

    def start():
        global controllers
        controllers = pi_pwm.controllers.from_config(config_file)

    def stop():
        global controllers
        for c, o in controllers.iteritems():
            try:
                o.stop()
            except:
                log.exception("exception while calling %s.stop", c)

    def json_io(wrapped_function):
        @functools.wraps(wrapped_function)
        def decorated_function(*args, **kwargs):
            if request.method != "GET" and request.content_type != "application/json":
                return Response(
                    json.dumps(
                        {"error": "Content-type must be application/json, not {}".format(request.content_type)},
                        indent=4
                    ),
                    status=405,
                    mimetype="application/json"
                )
            r = wrapped_function(*args, **kwargs)
            if isinstance(r, dict):
                return Response(
                    json.dumps(r, indent=4),
                    mimetype="application/json"
                )
            if isinstance(r, tuple):
                if len(r) == 1 and isinstance(r[0], dict):
                    return Response(
                        json.dumps(r[0], indent=4),
                        mimetype="application/json"
                    )
                if len(r) == 2 and isinstance(r[0], dict):
                    return Response(
                        json.dumps(r[0], indent=4),
                        status=r[1],
                        mimetype="application/json"
                    )
            return Response(r, mimetype="application/json")
        return decorated_function

    @app.route("/")
    @json_io
    def index():
        global controllers
        return {c: dict(controllers[c]) for c in controllers}

    @app.route("/echo/", methods=["POST"])
    @json_io
    def echo():
        return {
            "content_type": request.content_type,
            "content": request.json
        }

    @app.route("/<string:controller>/ping", methods=["GET"])
    @json_io
    def ping(controller):
        global controllers
        c = controllers.get(controller)
        if not c:
            return (
                {
                    "error": "controller {} not found".format(controller)
                },
                404
            )
        return {
            "old_dead_timer": c.dead_timer,
            "dead_timer": c.ping()
        }

    @app.route("/<string:controller>/", methods=["GET", "POST"], strict_slashes=False)
    @json_io
    def controller(controller):
        global controllers
        c = controllers.get(controller)
        if not c:
            return ({"error": "controller {} not found".format(controller)}, 404)
        if request.method == "GET":
            return dict(c)
        elif request.method == "POST":
            old_values = {}
            new_values = {}
            for k in ('interval', 'duty', 'dead_interval'):
                if k in request.json:
                    old, new = getattr(c, k), request.json[k]
                    old_values[k] = old
                    new_values[k] = new
                    try:
                        setattr(c, k, new)
                    except Exception as exc:
                        for k, v in old_values.iteritems():
                            setattr(c, k, v)
                        return ({"error": exc.message}, 400)

            return {"old": old_values, "new": new_values}

    start()
    atexit.register(stop)
    return app

def init_app(config=None):
    if not config:
        config = os.environ.get("PWM_CONFIG", "config.yaml")
    app = create_app(config)
    app.debug = True
    return app

if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)s %(thread)d %(levelname)s %(message)s")
    logging.getLogger("").setLevel(logging.DEBUG)
    #app = init_app().test_client()
    app = init_app()
    #import pdb; pdb.set_trace()
    #app.run(host="::", port=8080)
