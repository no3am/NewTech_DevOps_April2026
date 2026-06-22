#!/usr/bin/env python

import urllib.request
import json
import sys


def sendrequest(url, userid):
    url_call = "http://{url}:8080/users/{id}".format(url=url, id=userid)
    with urllib.request.urlopen(url_call) as url:
        data = json.loads(url.read().decode())
        print(data)


if __name__ == "__main__":
    sendrequest(url=sys.argv[1], userid=sys.argv[2])
