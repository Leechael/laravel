#!/usr/bin/env python
# -*- encoding: utf-8 -*-

from fabric.api import *

from os import path
from datetime import datetime
from time import time
import json
import httplib
import socket
from urllib import quote


__pwd__ = path.dirname(__file__)


def read_config():
    php = path.join(__pwd__, ".env.local.php")
    if not path.exists(php):
        raise Error(".env.local.php not exists.")
    output = local("php -r 'echo(json_encode(include(\"%s\")));'" % php,
                   capture=True)
    return json.loads(output)


@task
def deploy():
    start_at = time()
    prefix = datetime.now().strftime("%Y%m%d%H%M")
    config = read_config()
    dest = config["DEPLOY_TARGET"]

    with lcd(__pwd__):
        local("git archive HEAD --prefix={p}/ | bzip2 > dist/{p}.tbz2".format(p=prefix))

    src = path.join(__pwd__, "dist", prefix + ".tbz2")
    put(src, "/tmp")
    sudo("mv /tmp/%s.tbz2 %s" % (prefix, config["DEPLOY_TARGET"]))

    with cd(dest):
        sudo("tar xf %s.tbz2" % prefix)
        sudo("ln -s %s/env.php %s/%s/.env.php" % (dest, dest, prefix))
    with cd(path.join(dest, prefix)):
        sudo("composer install")
        sudo("php artisan migrate")
        sudo("rm -rf public/img && ln -s %s/img public/img" % dest)

    with cd(dest):
        sudo("chown -R www-data:www-data %s" % prefix)
        sudo("rm %s/%s.tbz2" % (dest, prefix))
        sudo("rm stable && ln -s %s/%s stable" % (dest, prefix))
        sudo("service php5-fpm restart")

    workers = config.get("SUPERVISOR_WORKERS", "").split(";")
    for worker in workers:
        sudo("supervisorctl restart %s" % worker)

    elapsed = "%2.f" % (time() - start_at, )
    if "HIPCHAT_TOKEN" in config and "HIPCHAT_ROOM" in config:
        token = config["HIPCHAT_TOKEN"]
        room = config["HIPCHAT_ROOM"]
        prj_name = config.get("PROJECT_NAME")
        if not prj_name:
            path.basename(__pwd__)
        host = env.host_string.split("@")[-1]
        msg = "<strong class='project_name'>" + prj_name + "<strong>" + \
              " has been deploy an new version <code class='version'" + \
              " style='color: green'>" + prefix + "</code> to server " + \
              host + " in " + elapsed + " seconds."
        hipchat_notify(token, room, msg, config.get("HIPCHAT_HOST"), config.get("HIPCHAT_PREFIX"))


def hipchat_notify(token, room, msg, host=None, prefix=None):
    body = "room_id="+quote(room)+"&from=Fabric&message="+quote(msg)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    endpoint = "/v1/rooms/message?format=json&auth_token="+token
    if prefix:
        endpoint = prefix.rstrip("/") + "/v1/rooms/message?format=json&auth_token="+token

    if not host:
        host = "api.hipchat.com"
    socket.setdefaulttimeout(30)
    conn = httplib.HTTPSConnection(host, 443, timeout=30)
    conn.request("POST", endpoint, body, headers)
    resp = conn.getresponse()
    body = resp.read()


@task
def hipchat_test(token, room):
    hipchat_notify(token, room, "Test message, your token and room is valid, and enjoy it!")
