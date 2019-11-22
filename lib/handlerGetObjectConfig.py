import codecs
import os
import time
import traceback

import handler
import osvcd_shared as shared
from rcGlobalEnv import rcEnv
from rcUtilities import svc_pathcf, split_path

class Handler(handler.Handler):
    """
    Send the last relay heartbeat payload emitted by <nodename>.
    """
    routes = (
        ("GET", "object_config"),
        (None, "get_service_config"),
    )
    access = {
        "role": ["admin"],
        "namespace": "FROM:path",
    }
    prototype = [
        {
            "name": "path",
            "desc": "The object path.",
            "required": True,
            "format": "object_path",
        },
        {
            "name": "format",
            "desc": "The data format to provide.",
            "candidates": ["json", "ini"],
            "default": "ini",
            "required": False,
            "format": "string",
        },
        {
            "name": "evaluate",
            "desc": "Provide evaluated configuration, ie scoped, dereferenced and computed.",
            "default": False,
            "required": False,
            "requires": [
                {
                    "option": "format",
                    "op": "equals",
                    "value": "json",
                },
            ],
            "format": "boolean",
        },
        {
            "name": "impersonate",
            "desc": "Provide impersonated configuration, ie scoped with the specified node name.",
            "required": False,
            "requires": [
                {
                    "option": "format",
                    "op": "equals",
                    "value": "json",
                },
            ],
            "format": "string",
        },
    ]

    def action(self, nodename, thr=None, **kwargs):
        options = self.parse_options(kwargs)
        if options.format == "json":
            return self._object_config_json(nodename, options.path, evaluate=options.evaluate, impersonate=options.impersonate, thr=thr, **kwargs)
        else:
            return self._object_config_file(nodename, options.path, thr=thr, **kwargs)

    def _object_config_json(self, nodename, path, thr=None, evaluate=False, impersonate=None, **kwargs):
        try:
            return shared.SERVICES[path].print_config_data(evaluate=evaluate, impersonate=impersonate)
        except Exception as exc:
            return {"status": "1", "error": str(exc), "traceback": traceback.format_exc()}

    def _object_config_file(self, nodename, path, thr=None, **kwargs):
        if shared.SMON_DATA.get(path, {}).get("status") in ("purging", "deleting") or \
           shared.SMON_DATA.get(path, {}).get("global_expect") in ("purged", "deleted"):
            return {"error": "delete in progress", "status": 2}
        fpath = svc_pathcf(path)
        if not os.path.exists(fpath):
            return {"error": "%s does not exist" % fpath, "status": 3}
        mtime = os.path.getmtime(fpath)
        with codecs.open(fpath, "r", "utf8") as filep:
            buff = filep.read()
        thr.log.info("serve service %s config to %s", path, nodename)
        return {"status": 0, "data": buff, "mtime": mtime}

