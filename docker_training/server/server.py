#!/usr/bin/env python
import web
import xml.etree.ElementTree as ET
import json

from pathlib import Path

xmlfile = Path('./user_data.xml')
tree = ET.parse(str(xmlfile))
root = tree.getroot()

urls = (
    '/users', 'list_users',
    '/users/(.*)', 'get_user'
)

app = web.application(urls, globals())


class list_users:
    def GET(self):
        output = 'users:['
        for child in root:
            print('child', child.tag, child.attrib)
            output += str(child.attrib) + ','
        output += ']'
        return output


class get_user:
    def GET(self, user):
        for child in root:
            if child.attrib['id'] == user:
                return json.dumps(child.attrib)


if __name__ == "__main__":
    app.run()
