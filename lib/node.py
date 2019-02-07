# -*- coding: utf8 -*-

"""
This module implements the Node class.
The node
* handles communications with the collector
* holds the list of services
* has a scheduler
"""
from __future__ import print_function
from __future__ import absolute_import
from __future__ import division

import os
import datetime
import sys
import fnmatch
import json
import socket
import time
import re

import six
try:
    from six.moves.urllib.request import Request, urlopen
    from six.moves.urllib.error import HTTPError
    from six.moves.urllib.parse import urlencode
except ImportError:
    # pylint false positive
    pass

import svcBuilder
import xmlrpcClient
from rcGlobalEnv import rcEnv
from storage import Storage
import rcLogger
import rcExceptions as ex
import rcConfigParser
from freezer import Freezer
from rcScheduler import Scheduler, SchedOpts, sched_action
from rcColor import formatter
from rcUtilities import justcall, lazy, lazy_initialized, vcall, check_privs, \
                        call, which, purge_cache_expired, read_cf, unset_lazy, \
                        drop_option, is_string, try_decode, is_service, \
                        bencode, bdecode, \
                        list_services, init_locale, ANSI_ESCAPE, svc_pathetc, \
                        makedirs, exe_link_exists, fmt_svcpath, \
                        glob_services_config, split_svcpath, validate_name, \
                        unset_all_lazy
from converters import *
from comm import Crypt
from extconfig import ExtConfigMixin
from lock import LOCK_EXCEPTIONS
from jsonpath_ng import jsonpath
from jsonpath_ng.ext import parse
from ipaddress import ip_network, ip_address, summarize_address_range

if six.PY2:
    BrokenPipeError = IOError

init_locale()

DEFAULT_STATUS_GROUPS = [
    "hb",
    "arbitrator",
]

ACTION_ASYNC = {
    "freeze": {
        "target": "frozen",
        "progress": "freezing",
    },
    "thaw": {
        "target": "thawed",
        "progress": "thawing",
    },
}

REMOTE_ACTIONS = [
    "freeze",
    "reboot",
    "shutdown",
    "thaw",
    "updatepkg",
    "updatecomp",
]

ACTIONS_NO_PARALLEL = [
    "edit_config",
    "get",
    "print_config",
    "print_resource_status",
    "print_schedule",
    "print_status",
]

ACTIONS_NO_MULTIPLE_SERVICES = [
    "print_resource_status",
]

CONFIG_DEFAULTS = {
    "node_env": "TST",
    "push_schedule": "00:00-06:00",
    "sync_schedule": "04:00-06:00",
    "comp_schedule": "02:00-06:00",
    "collect_stats_schedule": "@10",
    "no_schedule": "",
}

UNPRIVILEGED_ACTIONS = [
    "collector_cli",
]

STATS_INTERVAL = 30

class Node(Crypt, ExtConfigMixin):
    """
    Defines a cluster node.  It contain list of Svc.
    Implements node-level actions and checks.
    """
    def __str__(self):
        return self.nodename

    def __init__(self):
        ExtConfigMixin.__init__(self, default_status_groups=DEFAULT_STATUS_GROUPS)
        self.listener = None
        self.config = None
        self.auth_config = None
        self.clouds = None
        self.paths = Storage(
            reboot_flag=os.path.join(rcEnv.paths.pathvar, "REBOOT_FLAG"),
            last_boot_id=os.path.join(rcEnv.paths.pathvar, "last_boot_id"),
            tmp_cf=os.path.join(rcEnv.paths.pathvar, "node.conf.tmp"),
            cf=rcEnv.paths.nodeconf,
        )
        self.services = None
        self.load_config()
        self.options = Storage(
            cron=False,
            syncrpc=False,
            force=False,
            debug=False,
            stats_dir=None,
            begin=None,
            end=None,
            moduleset="",
            module="",
            node=None,
            ruleset_date="",
            objects=[],
            format=None,
            user=None,
            api=None,
            resource=[],
            mac=None,
            broadcast=None,
            param=None,
            value=None,
            extra_argv=[],
        )
        self.set_collector_env()
        self.log = rcLogger.initLogger(rcEnv.nodename)
        self.stats_data = {}
        self.stats_updated = 0

    @lazy
    def kwdict(self):
        return __import__("nodedict")

    @lazy
    def devnull(self):
        return os.open(os.devnull, os.O_RDWR)

    @lazy
    def var_d(self):
        var_d = os.path.join(rcEnv.paths.pathvar, "node")
        makedirs(var_d)
        return var_d

    @property
    def svcs(self):
        if self.services is None:
            return None
        return list(self.services.values())

    @lazy
    def freezer(self):
        """
        Lazy allocator for the freezer object.
        """
        return Freezer("node")

    @lazy
    def sched(self):
        """
        Lazy initialization of the node Scheduler object.
        """
        return Scheduler(
            config_defaults=CONFIG_DEFAULTS,
            options=self.options,
            config=self.config,
            log=self.log,
            scheduler_actions={
                "checks": SchedOpts(
                    "checks"
                ),
                "dequeue_actions": SchedOpts(
                    "dequeue_actions",
                    schedule_option="no_schedule"
                ),
                "pushstats": SchedOpts(
                    "stats"
                ),
                "collect_stats": SchedOpts(
                    "stats_collection",
                    schedule_option="collect_stats_schedule"
                ),
                "pushpkg": SchedOpts(
                    "packages"
                ),
                "pushpatch": SchedOpts(
                    "patches"
                ),
                "pushasset": SchedOpts(
                    "asset"
                ),
                "pushnsr": SchedOpts(
                    "nsr",
                    schedule_option="no_schedule"
                ),
                "pushhp3par": SchedOpts(
                    "hp3par",
                    schedule_option="no_schedule"
                ),
                "pushemcvnx": SchedOpts(
                    "emcvnx",
                    schedule_option="no_schedule"
                ),
                "pushcentera": SchedOpts(
                    "centera",
                    schedule_option="no_schedule"
                ),
                "pushnetapp": SchedOpts(
                    "netapp",
                    schedule_option="no_schedule"
                ),
                "pushibmds": SchedOpts(
                    "ibmds",
                    schedule_option="no_schedule"
                ),
                "pushdcs": SchedOpts(
                    "dcs",
                    schedule_option="no_schedule"
                ),
                "pushfreenas": SchedOpts(
                    "freenas",
                    schedule_option="no_schedule"
                ),
                "pushxtremio": SchedOpts(
                    "xtremio",
                    schedule_option="no_schedule"
                ),
                "pushgcedisks": SchedOpts(
                    "gcedisks",
                    schedule_option="no_schedule"
                ),
                "pushhds": SchedOpts(
                    "hds",
                    schedule_option="no_schedule"
                ),
                "pushnecism": SchedOpts(
                    "necism",
                    schedule_option="no_schedule"
                ),
                "pusheva": SchedOpts(
                    "eva",
                    schedule_option="no_schedule"
                ),
                "pushibmsvc": SchedOpts(
                    "ibmsvc",
                    schedule_option="no_schedule"
                ),
                "pushvioserver": SchedOpts(
                    "vioserver",
                    schedule_option="no_schedule"
                ),
                "pushsym": SchedOpts(
                    "sym",
                    schedule_option="no_schedule"
                ),
                "pushbrocade": SchedOpts(
                    "brocade", schedule_option="no_schedule"
                ),
                "pushdisks": SchedOpts(
                    "disks"
                ),
                "sysreport": SchedOpts(
                    "sysreport"
                ),
                "compliance_auto": SchedOpts(
                    "compliance",
                    fname="last_comp_check",
                    schedule_option="comp_schedule"
                ),
                "rotate_root_pw": SchedOpts(
                    "rotate_root_pw",
                    fname="last_rotate_root_pw",
                    schedule_option="no_schedule"
                ),
                "auto_reboot": SchedOpts(
                    "reboot",
                    fname="last_auto_reboot",
                    schedule_option="no_schedule"
                )
            },
        )

    @lazy
    def collector(self):
        """
        Lazy initialization of the node Collector object.
        """
        self.log.debug("initialize node::collector")
        return xmlrpcClient.Collector(node=self)

    @lazy
    def nodename(self):
        """
        Lazy initialization of the node name.
        """
        self.log.debug("initialize node::nodename")
        return socket.gethostname().lower()

    @lazy
    def system(self):
        """
        Lazy initialization of the operating system object, which implements
        specific methods like crash or fast-reboot.
        """
        try:
            rcos = __import__('rcOs'+rcEnv.sysname)
        except ImportError:
            rcos = __import__('rcOs')
        return rcos.Os()

    @lazy
    def compliance(self):
        from compliance import Compliance
        comp = Compliance(self)
        return comp

    @staticmethod
    def check_privs(action):
        """
        Raise if the action requires root privileges but the current
        running user is not root.
        """
        if action in UNPRIVILEGED_ACTIONS:
            return
        check_privs()

    @lazy
    def quorum(self):
        try:
            return self.conf_get("cluster", "quorum")
        except ex.OptNotFound as exc:
            return exc.default

    @lazy
    def dns(self):
        try:
            return self.conf_get("cluster", "dns")
        except ex.OptNotFound as exc:
            return exc.default

    @lazy
    def env(self):
        try:
            return self.conf_get("node", "env")
        except ex.OptNotFound as exc:
            return exc.default

    def get_min_avail(self, keyword, metric, limit=100):
        total = self.stats().get(metric) # mb
        if total in (0, None):
            return 0
        try:
            val = self.conf_get("node", keyword)
        except ex.OptNotFound as exc:
            val = exc.default
        if str(val).endswith("%"):
            val = int(val.rstrip("%"))
        else:
            val = val // 1024 // 1024 # b > mb
            val = int(val/total*100)
            if val > limit:
                # unreasonable
                val = limit
        return val

    @lazy
    def min_avail_mem(self):
        return self.get_min_avail("min_avail_mem", "mem_total", 50)

    @lazy
    def min_avail_swap(self):
        return self.get_min_avail("min_avail_swap", "swap_total", 100)

    @lazy
    def max_parallel(self):
        try:
            return self.conf_get("node", "max_parallel")
        except ex.OptNotFound as exc:
            return self.default_max_parallel()

    def default_max_parallel(self):
        nr = int(self.asset.get_cpu_threads()["value"])
        if nr == 0:
            nr = int(self.asset.get_cpu_cores()["value"])
        return max(2, nr//2)

    @lazy
    def dnsnodes(self):
        nodes = []
        for ip in self.dns:
            try:
                data = socket.gethostbyaddr(ip)
                names = [data[0]] + data[1]
            except Exception as exc:
                names = []
            for node in names:
                if node in self.cluster_nodes:
                    nodes.append(node)
                    break
        return nodes

    @lazy
    def arbitrators(self):
        arbitrators = []
        for section in self.config.sections():
            if not section.startswith("arbitrator#"):
                continue
            data = {
                "id": section,
            }
            try:
                data["name"] = self.conf_get(section, "name")
            except Exception:
                continue
            try:
                data["secret"] = self.conf_get(section, "secret")
            except Exception:
                continue
            try:
                data["timeout"] = self.conf_get(section, "timeout")
            except ex.OptNotFound as exc:
                data["timeout"] = exc.default
            arbitrators.append(data)
        return arbitrators

    @staticmethod
    def split_url(url, default_app=None):
        """
        Split a node.conf node.dbopensvc style url into a
        (protocol, host, port, app) tuple.
        """
        if url == 'None':
            return 'https', '127.0.0.1', '443', '/'

        # transport
        if url.startswith('https'):
            transport = 'https'
            url = url.replace('https://', '')
        elif url.startswith('http'):
            transport = 'http'
            url = url.replace('http://', '')
        else:
            transport = 'https'

        elements = url.split('/')
        if len(elements) < 1:
            raise ex.excError("url %s should have at least one slash")

        # app
        if len(elements) > 1:
            app = elements[1]
        else:
            app = default_app

        # host/port
        subelements = elements[0].split(':')
        if len(subelements) == 1:
            host = subelements[0]
            if transport == 'http':
                port = '80'
            else:
                port = '443'
        elif len(subelements) == 2:
            host = subelements[0]
            port = subelements[1]
        else:
            raise ex.excError("too many columns in %s" % ":".join(subelements))

        return transport, host, port, app

    def set_collector_env(self):
        """
        Store the collector connection elements parsed from the node.conf
        node.uuid, node.dbopensvc and node.dbcompliance as properties of the
        rcEnv class.
        """
        if self.config is None:
            self.load_config()
        if self.config is None:
            return
        if self.config.has_option('node', 'dbopensvc'):
            url = self.config.get('node', 'dbopensvc')
            try:
                (
                    rcEnv.dbopensvc_transport,
                    rcEnv.dbopensvc_host,
                    rcEnv.dbopensvc_port,
                    rcEnv.dbopensvc_app
                ) = self.split_url(url, default_app="feed")
                rcEnv.dbopensvc = "%s://%s:%s/%s/default/call/xmlrpc" % (
                    rcEnv.dbopensvc_transport,
                    rcEnv.dbopensvc_host,
                    rcEnv.dbopensvc_port,
                    rcEnv.dbopensvc_app
                )
            except ex.excError as exc:
                self.log.error("malformed dbopensvc url: %s (%s)",
                               rcEnv.dbopensvc, str(exc))
        else:
            rcEnv.dbopensvc_transport = None
            rcEnv.dbopensvc_host = None
            rcEnv.dbopensvc_port = None
            rcEnv.dbopensvc_app = None
            rcEnv.dbopensvc = None

        if self.config.has_option('node', 'dbcompliance'):
            url = self.config.get('node', 'dbcompliance')
            try:
                (
                    rcEnv.dbcompliance_transport,
                    rcEnv.dbcompliance_host,
                    rcEnv.dbcompliance_port,
                    rcEnv.dbcompliance_app
                ) = self.split_url(url, default_app="init")
                rcEnv.dbcompliance = "%s://%s:%s/%s/compliance/call/xmlrpc" % (
                    rcEnv.dbcompliance_transport,
                    rcEnv.dbcompliance_host,
                    rcEnv.dbcompliance_port,
                    rcEnv.dbcompliance_app
                )
            except ex.excError as exc:
                self.log.error("malformed dbcompliance url: %s (%s)",
                               rcEnv.dbcompliance, str(exc))
        else:
            rcEnv.dbcompliance_transport = rcEnv.dbopensvc_transport
            rcEnv.dbcompliance_host = rcEnv.dbopensvc_host
            rcEnv.dbcompliance_port = rcEnv.dbopensvc_port
            rcEnv.dbcompliance_app = "init"
            rcEnv.dbcompliance = "%s://%s:%s/%s/compliance/call/xmlrpc" % (
                rcEnv.dbcompliance_transport,
                rcEnv.dbcompliance_host,
                rcEnv.dbcompliance_port,
                rcEnv.dbcompliance_app
            )

        if self.config.has_option('node', 'uuid'):
            rcEnv.uuid = self.config.get('node', 'uuid')
        else:
            rcEnv.uuid = ""

    def call(self, *args, **kwargs):
        """
        Wrap rcUtilities call function, setting the node logger.
        """
        kwargs["log"] = self.log
        return call(*args, **kwargs)

    def vcall(self, *args, **kwargs):
        """
        Wrap rcUtilities vcall function, setting the node logger.
        """
        kwargs["log"] = self.log
        return vcall(*args, **kwargs)

    @staticmethod
    def strip_ns(paths, namespace):
        if namespace:
            return [path.split("/")[-1] for path in paths]
        else:
            return paths

    @staticmethod
    def filter_ns(paths, namespace):
        if not namespace:
            return paths
        if namespace == "root":
            return [path for path in paths if "/" not in path]
        return [path for path in paths if path.startswith(namespace+"/")]

    def svcs_selector(self, selector, namespace=None, data=None):
        """
        Given a selector string, return a list of service names.
        This exposed method only aggregates ORed elements.
        """
        if data is None or not data.get("retryable"):
            try:
                data = self._daemon_status(silent=True)["monitor"]
            except Exception as exc:
                data = None
        else:
            data = data["monitor"]

        # fully qualified svcname
        path = is_service(selector, namespace)
        if path:
            self.options.single_service = True
            return [path]

        # full listing and namespace full listing
        if selector is None or "*" in selector.split(","):
            if data:
                paths = [path for path in data["services"]]
                paths = self.filter_ns(paths, namespace)
            else:
                paths = list_services(namespace)
            return paths

        # fnmatch on names and service config/status filtering
        try:
            paths = self._svcs_selector(selector, data, namespace)
        finally:
            del self.services
            self.services = None
        return paths

    def _svcs_selector(self, selector, data=None, namespace=None):
        self.build_services()
        cluster_data = self._daemon_status()
        if data and "services" in data:
            paths = [path for path in data["services"]]
        else:
            paths = [svc.svcpath for svc in self.svcs]
        paths = self.filter_ns(paths, namespace)
        if "," in selector:
            ored_selectors = selector.split(",")
        else:
            ored_selectors = [selector]
        result = []
        for _selector in ored_selectors:
            for path in self.__svcs_selector(_selector, data, paths,
                                             namespace=namespace,
                                             cluster_data=cluster_data):
                if path not in result:
                    result.append(path)
        if len(result) == 0 and not re.findall(r"[,\+\*=\^:~><]", selector):
            raise ex.excError("service not found")
        return result

    def __svcs_selector(self, selector, data, paths, namespace=None,
                        cluster_data=None):
        """
        Given a selector string, return a list of service names.
        This method only intersect the ANDed elements.
        """
        if selector in (None, ""):
            return []
        path = is_service(selector, namespace)
        if path:
            return [path]
        if "+" in selector:
            anded_selectors = selector.split("+")
        else:
            anded_selectors = [selector]
        if selector in (None, ""):
            result = paths
        else:
            result = None
            for _selector in anded_selectors:
                _paths = self.___svcs_selector(_selector, paths, cluster_data, namespace)
                if result is None:
                    result = _paths
                else:
                    common = set(result) & set(_paths)
                    result = [svcname for svcname in result if svcname in common]
        return result

    def ___svcs_selector(self, selector, paths, cluster_data, namespace):
        """
        Given a basic selector string (no AND nor OR), return a list of service
        names.
        """
        ops = r"(<=|>=|<|>|=|~|:)"
        negate = selector[0] == "!"
        selector = selector.lstrip("!")
        elts = re.split(ops, selector)

        def matching(current, op, value):
            if op in ("<", ">", ">=", "<="):
                try:
                    current = float(current)
                except (ValueError, TypeError):
                    return False
            if op == "=":
                if current.lower() in ("true", "false"):
                    match = current.lower() == value.lower()
                else:
                    match = current == value
            elif op == "~":
                match = re.search(value, current)
            elif op == ">":
                match = current > value
            elif op == ">=":
                match = current >= value
            elif op == "<":
                match = current < value
            elif op == "<=":
                match = current <= value
            elif op == ":":
                match = True
            return match

        def svc_matching(svc, param, op, value, cluster_data):
            param = param.lstrip(".")
            if param.startswith("$."):
                try:
                    jsonpath_expr = parse(param)
                    data = self.cluster_svc_data(svc.svcpath, cluster_data)
                    matches = jsonpath_expr.find(data)
                    for match in matches:
                        current = match.value
                        if matching(current, op, value):
                            return True
                except Exception as exc:
                    current = None
            else:
                try:
                    current = svc._get(param, evaluate=True)
                except (ex.excError, ex.OptNotFound, ex.RequiredOptNotFound):
                    current = None
                if current is None:
                    if "." in param:
                        group, _param = param.split(".", 1)
                    else:
                        group = param
                        _param = None
                    rids = [section for section in svc.config.sections() if group == "" or section.split('#')[0] == group]
                    if op == ":" and len(rids) > 0 and _param is None:
                        return True
                    elif _param:
                        for rid in rids:
                            try:
                                _current = svc._get(rid+"."+_param, evaluate=True)
                            except (ex.excError, ex.OptNotFound, ex.RequiredOptNotFound):
                                continue
                            if matching(_current, op, value):
                                return True
                    return False
                if current is None:
                    return op == ":"
                if matching(current, op, value):
                    return True
            return False

        if len(elts) == 1:
            if selector.startswith("root/"):
                selector = selector[5:]
                return [path for path in paths if negate ^ ("/" not in path and fnmatch.fnmatch(path, selector))]
            elif "/" in selector:
                return [path for path in paths if negate ^ fnmatch.fnmatch(path, selector)]
            else:
                if namespace:
                    selector = fmt_svcpath(selector, namespace)
                return [path for path in paths if negate ^ fnmatch.fnmatch(path, selector)]
        elif len(elts) != 3:
            return []
        param, op, value = elts
        if op in ("<", ">", ">=", "<="):
            try:
                value = float(value)
            except (TypeError, ValueError):
                return []

        # status data jsonpath or config keyword match
        if cluster_data is None:
            return []
        result = []
        for svc in self.svcs:
            ret = svc_matching(svc, param, op, value, cluster_data)
            if ret ^ negate:
                result.append(svc.svcpath)

        return result

    def cluster_svc_data(self, svcpath, cluster_data):
        """
        Extract from the cluster data the structures refering to a
        svcpath.
        """
        if not cluster_data:
            return
        try:
            data = cluster_data.get("monitor", {}).get("services", {}).get(svcpath, {})
            data["nodes"] = {}
        except KeyError:
            return
        for node, ndata in cluster_data.get("monitor", {}).get("nodes", {}).items():
            try:
                data["nodes"][node] = {
                    "status": ndata["services"]["status"][svcpath],
                    "config": ndata["services"]["config"][svcpath],
                }
            except KeyError:
                pass
        return data

    def build_services(self, *args, **kwargs):
        """
        Instanciate a Svc objects for each requested services and add it to
        the node.
        """
        if self.svcs is not None and \
           ('svcpaths' not in kwargs or \
           (isinstance(kwargs['svcpaths'], list) and len(kwargs['svcpaths']) == 0)):
            return

        if 'svcpaths' in kwargs and \
           isinstance(kwargs['svcpaths'], list) and \
           len(kwargs['svcpaths']) > 0 and \
           self.svcs is not None:
            svcpaths_request = set(kwargs['svcpaths'])
            svcpaths_actual = set([s.svcpath for s in self.svcs])
            if len(svcpaths_request-svcpaths_actual) == 0:
                return

        self.services = {}

        kwargs["node"] = self
        svcs, errors = svcBuilder.build_services(*args, **kwargs)
        if 'svcpaths' in kwargs:
            self.check_build_errors(kwargs['svcpaths'], svcs, errors)

        opt_status = kwargs.get("status")
        for svc in svcs:
            if opt_status is not None and not svc.status() in opt_status:
                continue
            self += svc

        rcLogger.set_namelen(self.svcs)

    @staticmethod
    def check_build_errors(svcpaths, svcs, errors):
        """
        Raise error if the service builder did not return a Svc object for
        each service we requested.
        """
        if isinstance(svcpaths, list):
            n_args = len(svcpaths)
        else:
            n_args = 1
        n_svcs = len(svcs)
        if n_svcs == n_args:
            return 0
        msg = ""
        if n_args > 1:
            msg += "%d services validated out of %d\n" % (n_svcs, n_args)
        if len(errors) == 1:
            msg += errors[0]
        else:
            msg += "\n".join(["- "+err for err in errors])
        raise ex.excError(msg)

    def rebuild_services(self, svcpaths):
        """
        Delete the list of Svc objects in the Node object and create a new one.

        Args:
          svcpaths: add only Svc objects for services specified
        """
        del self.services
        self.services = None
        self.build_services(svcpaths=svcpaths, node=self)

    def close(self):
        """
        Stop the node class workers
        """
        if lazy_initialized(self, "devnull"):
            os.close(self.devnull)

        import gc
        import threading
        gc.collect()
        for thr in threading.enumerate():
            if thr.name == 'QueueFeederThread' and thr.ident is not None:
                thr.join(1)


    def make_temp_config(self):
        """
        Copy the current service configuration file to a temporary
        location for edition.
        If the temp file already exists, propose the --discard
        or --recover options.
        """
        import shutil
        if os.path.exists(self.paths.tmp_cf):
            if self.options.recover:
                pass
            elif self.options.discard:
                shutil.copy(rcEnv.paths.nodeconf, self.paths.tmp_cf)
            else:
                self.edit_config_diff()
                print("%s exists: node conf is already being edited. Set "
                      "--discard to edit from the current configuration, "
                      "or --recover to open the unapplied config" % \
                      self.paths.tmp_cf, file=sys.stderr)
                raise ex.excError
        else:
            shutil.copy(rcEnv.paths.nodeconf, self.paths.tmp_cf)
        return self.paths.tmp_cf

    def edit_config_diff(self):
        """
        Display the diff between the current config and the pending
        unvalidated config.
        """
        from subprocess import call

        def diff_capable(opts):
            cmd = ["diff"] + opts + [rcEnv.paths.nodeconf, self.paths.cf]
            cmd_results = justcall(cmd)
            if cmd_results[2] == 0:
                return True
            return False

        if not os.path.exists(self.paths.tmp_cf):
            return
        if diff_capable(["-u", "--color"]):
            cmd = ["diff", "-u", "--color", rcEnv.paths.nodeconf, self.paths.tmp_cf]
        elif diff_capable(["-u"]):
            cmd = ["diff", "-u", rcEnv.paths.nodeconf, self.paths.tmp_cf]
        else:
            cmd = ["diff", rcEnv.paths.nodeconf, self.paths.tmp_cf]
        call(cmd)

    def edit_config(self):
        """
        Execute an editor on the node configuration file.
        When the editor exits, validate the new configuration file.
        If validation pass, install the new configuration,
        else keep the previous configuration in place and offer the
        user the --recover or --discard choices for its next edit
        config action.
        """
        if "EDITOR" in os.environ:
            editor = os.environ["EDITOR"]
        elif os.name == "nt":
            editor = "notepad"
        else:
            editor = "vi"
        from rcUtilities import which, fsum
        if not which(editor):
            print("%s not found" % editor, file=sys.stderr)
            return 1
        path = self.make_temp_config()
        os.system(' '.join((editor, path)))
        if fsum(path) == fsum(rcEnv.paths.nodeconf):
            os.unlink(path)
            return 0
        results = self._validate_config(path=path)
        if results["errors"] == 0:
            import shutil
            shutil.copy(path, rcEnv.paths.nodeconf)
            os.unlink(path)
        else:
            print("your changes were not applied because of the errors "
                  "reported above. you can use the edit config command "
                  "with --recover to try to fix your changes or with "
                  "--discard to restart from the live config")
        return results["errors"] + results["warnings"]

    def edit_authconfig(self):
        """
        edit_authconfig node action entrypoint
        """
        fpath = os.path.join(rcEnv.paths.pathetc, "auth.conf")
        return self.edit_cf(fpath)

    @staticmethod
    def edit_cf(fpath):
        """
        Choose an editor, setup the LANG, and exec the editor on the
        file passed as argument.
        """
        if "EDITOR" in os.environ:
            editor = os.environ["EDITOR"]
        elif os.name == "nt":
            editor = "notepad"
        else:
            editor = "vi"
        if not which(editor):
            print("%s not found" % editor, file=sys.stderr)
            return 1
        return os.system(' '.join((editor, fpath)))

    def write_config(self):
        """
        Rewrite node.conf using the in-memory ConfigParser object as reference.
        """
        for option in CONFIG_DEFAULTS:
            if self.config.has_option('DEFAULT', option):
                self.config.remove_option('DEFAULT', option)
        for section in self.config.sections():
            if '#sync#' in section:
                self.config.remove_section(section)
        import tempfile
        import shutil
        import codecs
        try:
            tmpf = tempfile.NamedTemporaryFile()
            fpath = tmpf.name
            tmpf.close()
            if six.PY2:
                with codecs.open(fpath, "w", "utf-8") as tmpf:
                    self.config.write(tmpf)
            else:
                with open(fpath, "w") as tmpf:
                    self.config.write(tmpf)
            shutil.move(fpath, rcEnv.paths.nodeconf)
        except (OSError, IOError) as exc:
            print("failed to write new %s (%s)" % (rcEnv.paths.nodeconf, str(exc)),
                  file=sys.stderr)
            raise ex.excError
        try:
            os.chmod(rcEnv.paths.nodeconf, 0o0600)
        except OSError:
            pass
        self.load_config()

    def purge_status_last(self):
        """
        Purge the cached status of each and every services and resources.
        """
        for svc in self.svcs:
            svc.purge_status_last()

    def load_config(self):
        """
        Parse the node.conf configuration file and store the RawConfigParser
        object as self.config.
        IOError is catched and self.config is left to its current value, which
        initially is None. So users of self.config should check for this None
        value before use.
        """
        try:
            self.config = read_cf(rcEnv.paths.nodeconf, CONFIG_DEFAULTS)
        except rcConfigParser.ParsingError as exc:
            print(str(exc), file=sys.stderr)
        except IOError:
            # some action don't need self.config
            pass

    def load_auth_config(self):
        """
        Parse the auth.conf configuration file and store the RawConfigParser
        object as self.auth_config.
        The actual parsing is done only on first call. This method is a noop
        on subsequent calls.
        """
        if self.auth_config is not None:
            return
        try:
            self.auth_config = read_cf(rcEnv.paths.authconf)
        except rcConfigParser.ParsingError as exc:
            print(str(exc), file=sys.stderr)
        except IOError:
            # some action don't need self.auth_config
            pass

    def __iadd__(self, svc):
        """
        Implement the Node() += Svc() operation, setting the node backpointer
        in the added service, storing the service in a list
        """
        if not hasattr(svc, "svcname"):
            return self
        if self.services is None:
            self.services = {}
        self.services[svc.svcpath] = svc
        return self

    def action(self, action, options=None):
        """
        The node action wrapper.
        Looks up which method to handle the action (some are not implemented
        in the Node class), and call the handling method.
        """
        try:
            self.async_action(action)
        except ex.excAbortAction:
            return 0
        try:
            return self._action(action, options)
        except LOCK_EXCEPTIONS as exc:
            self.log.warning(exc)
            return 1

    @sched_action
    def _action(self, action, options=None):
        if "_json_" in action:
            self.options.format = "json"
            action = action.replace("_json_", "_")
        if action.startswith("json_"):
            self.options.format = "json"
            action = "print" + action[4:]

        if action.startswith("compliance_"):
            if self.options.cron and action == "compliance_auto" and \
               self.config.has_option('compliance', 'auto_update') and \
               self.config.getboolean('compliance', 'auto_update'):
                self.compliance.updatecomp = True
                self.compliance.node = self
            ret = getattr(self.compliance, action)()
        elif action.startswith("collector_") and action != "collector_cli":
            from collector import Collector
            coll = Collector(self.options, self)
            data = getattr(coll, action)()
            self.print_data(data)
            ret = 0
        elif action.startswith("print"):
            getattr(self, action)()
            ret = 0
        else:
            ret = getattr(self, action)()

        if action in REMOTE_ACTIONS and os.environ.get("OSVC_ACTION_ORIGIN") != "daemon":
            self.wake_monitor()

        if ret is None:
            ret = 0
        elif isinstance(ret, bool):
            if ret:
                return 1
            else:
                return 0
        return ret

    @formatter
    def print_data(self, data, default_fmt=None):
        """
        A dummy method decorated by the formatter function.
        The formatter needs self to access the formatting options, so this
        can't be a staticmethod.
        """
        return data

    def print_schedule(self):
        """
        The 'print schedule' node and service action entrypoint.
        """
        return self.sched.print_schedule()

    def get_push_objects(self, section):
        """
        Returns the object names to do inventory on.
        Object names passed as nodemgr argument take precedence.
        If not specified by argument, objet names found in the
        configuration file section are returned.
        """
        if len(self.options.objects) > 0:
            return self.options.objects
        if self.config and self.config.has_option(section, "objects"):
            return self.config.get(section, "objects").split(",")
        return []

    def collect_stats(self):
        """
        Choose the os specific stats collection module and call its collect
        method.
        """
        try:
            mod = __import__("rcStatsCollect"+rcEnv.sysname)
        except ImportError:
            return
        mod.collect(self)

    def pushstats(self):
        """
        Set stats range to push to "last successful pushstat => now"

        Enforce a minimum interval of 21m, and a maximum of 1450m.

        The scheduled task that collects system statistics from system tools
        like sar, and sends the data to the collector.
        A list of metrics can be disabled from the task configuration section,
        using the 'disable' option.
        """
        fpath = self.sched.get_timestamp_f(self.sched.scheduler_actions["pushstats"].fname,
                                           success=True)
        try:
            with open(fpath, "r") as ofile:
                buff = ofile.read()
            start = datetime.datetime.strptime(buff, "%Y-%m-%d %H:%M:%S.%f\n")
            now = datetime.datetime.now()
            delta = now - start
            interval = delta.days * 1440 + delta.seconds // 60 + 10
        except:
            interval = 1450
        if interval < 21:
            interval = 21

        def get_disable_stats():
            """
            Returns the list of stats metrics collection disabled through the
            configuration file stats.disable option.
            """
            if not self.config.has_option("stats", "disable"):
                return []
            disable = self.config.get("stats", "disable")
            try:
                return json.loads(disable)
            except ValueError:
                pass
            if ',' in disable:
                return disable.replace(' ', '').split(',')
            return disable.split()

        disable = get_disable_stats()
        return self.collector.call('push_stats',
                                   stats_dir=self.options.stats_dir,
                                   stats_start=self.options.begin,
                                   stats_end=self.options.end,
                                   interval=interval,
                                   disable=disable)

    @lazy
    def asset(self):
        try:
            m = __import__('rcAsset'+rcEnv.sysname)
        except ImportError:
            raise ex.excError("pushasset methods not implemented on %s"
                              "" % rcEnv.sysname)
        return m.Asset(self)

    def pushpkg(self):
        """
        The pushpkg action entrypoint.
        Inventories the installed packages.
        """
        self.collector.call('push_pkg')

    def pushpatch(self):
        """
        The pushpatch action entrypoint.
        Inventories the installed patches.
        """
        self.collector.call('push_patch')

    def pushasset(self):
        """
        The pushasset action entrypoint.
        Inventories the server properties.
        """
        data = self.asset.get_asset_dict()
        try:
            if self.options.format is None:
                self.print_asset(data)
                return
            self.print_data(data)
        finally:
            self.collector.call('push_asset', self, data)

    def print_asset(self, data):
        from forest import Forest
        from rcColor import color
        tree = Forest()
        head_node = tree.add_node()
        head_node.add_column(rcEnv.nodename, color.BOLD)
        head_node.add_column("Value", color.BOLD)
        head_node.add_column("Source", color.BOLD)
        for key in sorted(data):
            _data = data[key]
            node = head_node.add_node()
            if key not in ("targets", "lan", "uids", "gids", "hba", "hardware"):
                if _data["value"] is None:
                    _data["value"] = ""
                node.add_column(_data["title"], color.LIGHTBLUE)
                if "formatted_value" in _data:
                    node.add_column(_data["formatted_value"])
                else:
                    node.add_column(_data["value"])
                node.add_column(_data["source"])

        if 'uids' in data:
            node = head_node.add_node()
            node.add_column("uids", color.LIGHTBLUE)
            node.add_column(str(len(data['uids'])))
            node.add_column(self.asset.s_probe)

        if 'gids' in data:
            node = head_node.add_node()
            node.add_column("gids", color.LIGHTBLUE)
            node.add_column(str(len(data['gids'])))
            node.add_column(self.asset.s_probe)

        if 'hardware' in data:
            node = head_node.add_node()
            node.add_column("hardware", color.LIGHTBLUE)
            node.add_column(str(len(data['hardware'])))
            node.add_column(self.asset.s_probe)
            for _data in data['hardware']:
                _node = node.add_node()
                _node.add_column("%s %s" % (_data["type"], _data["path"]))
                _node.add_column("%s: %s [%s]" % (_data["class"], _data["description"], _data["driver"]))

        if 'hba' in data:
            node = head_node.add_node()
            node.add_column("host bus adapters", color.LIGHTBLUE)
            node.add_column(str(len(data['hba'])))
            node.add_column(self.asset.s_probe)
            for _data in data['hba']:
                _node = node.add_node()
                _node.add_column(_data["hba_id"])
                _node.add_column(_data["hba_type"])

                if 'targets' in data:
                    hba_targets = [_d for _d in data['targets'] if _d["hba_id"] == _data["hba_id"]]
                    if len(hba_targets) == 0:
                        continue
                    __node = _node.add_node()
                    __node.add_column("targets")
                    for _d in hba_targets:
                        ___node = __node.add_node()
                        ___node.add_column(_d["tgt_id"])

        if 'lan' in data:
            node = head_node.add_node()
            node.add_column("ip addresses", color.LIGHTBLUE)
            n = 0
            for mac, _data in data['lan'].items():
                for __data in _data:
                    _node = node.add_node()
                    addr = __data["addr"]
                    if __data["mask"]:
                        addr += "/" + __data["mask"]
                    _node.add_column(addr)
                    _node.add_column(__data["intf"])
                    n += 1
            node.add_column(str(n))
            node.add_column(self.asset.s_probe)

        tree.print()


    def pushnsr(self):
        """
        The pushnsr action entrypoint.
        Inventories Networker Backup Server index databases.
        """
        self.collector.call('push_nsr')

    def pushhp3par(self):
        """
        The push3par action entrypoint.
        Inventories HP 3par storage arrays.
        """
        self.collector.call('push_hp3par', self.options.objects)

    def pushnetapp(self):
        """
        The pushnetapp action entrypoint.
        Inventories NetApp storage arrays.
        """
        self.collector.call('push_netapp', self.options.objects)

    def pushcentera(self):
        """
        The pushcentera action entrypoint.
        Inventories Centera storage arrays.
        """
        self.collector.call('push_centera', self.options.objects)

    def pushemcvnx(self):
        """
        The pushemcvnx action entrypoint.
        Inventories EMC VNX storage arrays.
        """
        self.collector.call('push_emcvnx', self.options.objects)

    def pushibmds(self):
        """
        The pushibmds action entrypoint.
        Inventories IBM DS storage arrays.
        """
        self.collector.call('push_ibmds', self.options.objects)

    def pushgcedisks(self):
        """
        The pushgcedisks action entrypoint.
        Inventories Google Compute Engine disks.
        """
        self.collector.call('push_gcedisks', self.options.objects)

    def pushfreenas(self):
        """
        The pushfreenas action entrypoint.
        Inventories FreeNas storage arrays.
        """
        self.collector.call('push_freenas', self.options.objects)

    def pushxtremio(self):
        """
        The pushxtremio action entrypoint.
        Inventories XtremIO storage arrays.
        """
        self.collector.call('push_xtremio', self.options.objects)

    def pushdcs(self):
        """
        The pushdcs action entrypoint.
        Inventories DataCore SAN Symphony storage arrays.
        """
        self.collector.call('push_dcs', self.options.objects)

    def pushhds(self):
        """
        The pushhds action entrypoint.
        Inventories Hitachi storage arrays.
        """
        self.collector.call('push_hds', self.options.objects)

    def pushnecism(self):
        """
        The pushnecism action entrypoint.
        Inventories NEC iSM storage arrays.
        """
        self.collector.call('push_necism', self.options.objects)

    def pusheva(self):
        """
        The pusheva action entrypoint.
        Inventories HP EVA storage arrays.
        """
        self.collector.call('push_eva', self.options.objects)

    def pushibmsvc(self):
        """
        The pushibmsvc action entrypoint.
        Inventories IBM SVC storage arrays.
        """
        self.collector.call('push_ibmsvc', self.options.objects)

    def pushvioserver(self):
        """
        The pushvioserver action entrypoint.
        Inventories IBM vio server storage arrays.
        """
        self.collector.call('push_vioserver', self.options.objects)

    def pushsym(self):
        """
        The pushsym action entrypoint.
        Inventories EMC Symmetrix server storage arrays.
        """
        objects = self.get_push_objects("sym")
        self.collector.call('push_sym', objects)

    def pushbrocade(self):
        """
        The pushsym action entrypoint.
        Inventories Brocade SAN switches.
        """
        self.collector.call('push_brocade', self.options.objects)

    def auto_rotate_root_pw(self):
        """
        The rotate_root_pw node action entrypoint.
        """
        self.rotate_root_pw()

    def unschedule_reboot(self):
        """
        Unflag the node for reboot during the next allowed period.
        """
        if not os.path.exists(self.paths.reboot_flag):
            print("reboot already not scheduled")
            return
        os.unlink(self.paths.reboot_flag)
        print("reboot unscheduled")

    def schedule_reboot(self):
        """
        Flag the node for reboot during the next allowed period.
        """
        if not os.path.exists(self.paths.reboot_flag):
            with open(self.paths.reboot_flag, "w") as ofile:
                ofile.write("")
        import stat
        statinfo = os.stat(self.paths.reboot_flag)
        if statinfo.st_uid != 0:
            os.chown(self.paths.reboot_flag, 0, -1)
            print("set %s root ownership"%self.paths.reboot_flag)
        if statinfo.st_mode & stat.S_IWOTH:
            mode = statinfo.st_mode ^ stat.S_IWOTH
            os.chmod(self.paths.reboot_flag, mode)
            print("set %s not world-writable"%self.paths.reboot_flag)
        print("reboot scheduled")

    def schedule_reboot_status(self):
        """
        Display information about the next scheduled reboot
        """
        import stat
        if os.path.exists(self.paths.reboot_flag):
            statinfo = os.stat(self.paths.reboot_flag)
        else:
            statinfo = None

        if statinfo is None or \
           statinfo.st_uid != 0 or statinfo.st_mode & stat.S_IWOTH:
            print("reboot is not scheduled")
            return

        sch = self.sched.scheduler_actions["auto_reboot"]
        schedule = self.sched.sched_get_schedule_raw(sch.section, sch.schedule_option)
        print("reboot is scheduled")
        print("reboot schedule: %s" % schedule)

        result = self.sched.get_next_schedule("auto_reboot")
        if result["next_sched"]:
            print("next reboot slot:",
                  result["next_sched"].strftime("%a %Y-%m-%d %H:%M"))
        elif result["minutes"] is None:
            print("next reboot slot: none")
        else:
            print("next reboot slot: none in the next %d days" % (result["minutes"]/144))

    def auto_reboot(self):
        """
        The scheduler task executing the node reboot if the scheduler
        constraints are satisfied and the reboot flag is set.
        """
        if not os.path.exists(self.paths.reboot_flag):
            print("%s is not present. no reboot scheduled" % self.paths.reboot_flag)
            return
        import stat
        statinfo = os.stat(self.paths.reboot_flag)
        if statinfo.st_uid != 0:
            print("%s does not belong to root. abort scheduled reboot" % self.paths.reboot_flag)
            return
        if statinfo.st_mode & stat.S_IWOTH:
            print("%s is world writable. abort scheduled reboot" % self.paths.reboot_flag)
            return
        try:
            once = self.config.get("reboot", "once")
            once = convert_boolean(once)
        except:
            once = True
        if once:
            print("remove %s and reboot" % self.paths.reboot_flag)
            os.unlink(self.paths.reboot_flag)
        self.reboot()

    def pushdisks(self):
        """
        The pushdisks node action entrypoint.

        Send to the collector the list of disks visible on this node, and
        their use by service.
        """
        data = self.push_disks_data()
        if self.options.format is None:
            self.print_push_disks(data)
        else:
            self.print_data(data)
        self.collector.call('push_disks', data)

    def print_push_disks(self, data):
        from forest import Forest
        from rcColor import color

        tree = Forest()
        head_node = tree.add_node()
        head_node.add_column(rcEnv.nodename, color.BOLD)
        head_node.add_column("DiskGroup", color.BOLD)
        head_node.add_column("Size.Used", color.BOLD)
        head_node.add_column("Vendor", color.BOLD)
        head_node.add_column("Model", color.BOLD)

        if len(data["disks"]) > 0:
            disks_node = head_node.add_node()
            disks_node.add_column("disks", color.BROWN)

        if len(data["served_disks"]) > 0:
            sdisks_node = head_node.add_node()
            sdisks_node.add_column("served disks", color.BROWN)

        for disk_id, disk in data["disks"].items():
            disk_node = disks_node.add_node()
            disk_node.add_column(disk_id, color.LIGHTBLUE)
            disk_node.add_column(disk["dg"])
            disk_node.add_column(print_size(disk["size"]))
            disk_node.add_column(disk["vendor"])
            disk_node.add_column(disk["model"])

            for svcpath, service in disk["services"].items():
                svc_node = disk_node.add_node()
                svc_node.add_column(svcpath, color.LIGHTBLUE)
                svc_node.add_column(disk["dg"])
                svc_node.add_column(print_size(service["used"]))

            if disk["used"] < disk["size"]:
                svc_node = disk_node.add_node()
                svc_node.add_column(rcEnv.nodename, color.LIGHTBLUE)
                svc_node.add_column(disk["dg"])
                svc_node.add_column(print_size(disk["size"] - disk["used"]))

        for disk_id, disk in data["served_disks"].items():
            disk_node = disks_node.add_node()
            disk_node.add_column(disk_id, color.LIGHTBLUE)
            disk_node.add_column(disk["dg"])
            disk_node.add_column(print_size(disk["size"]))
            disk_node.add_column(disk["vdisk_id"])

        tree.print()

    def push_disks_data(self):
        if self.svcs is None:
            self.build_services()

        di = __import__('rcDiskInfo'+rcEnv.sysname)
        data = {
            "disks": {},
            "served_disks": {},
        }

        for svc in self.svcs:
            # hash to add up disk usage inside a service
            for r in svc.get_resources():
                if hasattr(r, 'devmap') and hasattr(r, 'vm_hostname'):
                    for dev_id, vdev_id in r.devmap():
                        try:
                            disk_id = self.diskinfo.disk_id(dev_id)
                        except:
                            continue
                        try:
                            disk_size = self.diskinfo.disk_size(dev_id)
                        except:
                            continue
                        data["served_disks"][disk_id] = {
                            "dev_id": dev_id,
                            "vdev_id": vdev_id,
                            "vdisk_id": r.vm_hostname+'.'+vdev_id,
                            "size": disk_size,
                            "cluster": self.cluster_name,
                        }

                try:
                    devpaths = r.sub_devs()
                except Exception as e:
                    print(e)
                    devpaths = []

                for devpath in devpaths:
                    for d, used, region in self.devtree.get_top_devs_usage_for_devpath(devpath):
                        disk_id = self.diskinfo.disk_id(d)
                        if disk_id is None or disk_id == "":
                            continue
                        if disk_id.startswith(rcEnv.nodename+".loop"):
                            continue
                        dev = self.devtree.get_dev_by_devpath(d)
                        disk_size = dev.size

                        if disk_id not in data["disks"]:
                            data["disks"][disk_id] = {
                                "size": disk_size,
                                "dg": dev.dg,
                                "vendor": self.diskinfo.disk_vendor(d),
                                "model": self.diskinfo.disk_model(d),
                                "used": 0,
                                "services": {},
                            }

                        if svc.svcpath not in data["disks"][disk_id]["services"]:
                            data["disks"][disk_id]["services"][svc.svcpath] = {
                                "svcname": svc.svcpath,
                                "used": used,
                                "region": region
                            }
                        else:
                            # consume space at service level
                            data["disks"][disk_id]["services"][svc.svcpath]["used"] += used
                            if data["disks"][disk_id]["services"][svc.svcpath]["used"] > disk_size:
                                data["disks"][disk_id]["services"][svc.svcpath]["used"] = disk_size

                        # consume space at disk level
                        data["disks"][disk_id]["used"] += used
                        if data["disks"][disk_id]["used"] > disk_size:
                            data["disks"][disk_id]["used"] = disk_size

        done = []

        try:
            devpaths = self.devlist()
        except Exception as e:
            print(e)
            devpaths = []

        for devpath in devpaths:
            disk_id = self.diskinfo.disk_id(devpath)
            if disk_id is None or disk_id == "":
                continue
            if disk_id.startswith(rcEnv.nodename+".loop"):
                continue
            if re.match(r"/dev/rdsk/.*s[01345678]", devpath):
                # don't report partitions
                continue

            # Linux Node:devlist() reports paths, so we can have duplicate
            # disks here.
            if disk_id in done:
                continue
            done.append(disk_id)
            if disk_id in data["disks"]:
                continue

            dev = self.devtree.get_dev_by_devpath(devpath)
            disk_size = dev.size

            data["disks"][disk_id] = {
                "size": disk_size,
                "dg": dev.dg,
                "vendor": self.diskinfo.disk_vendor(devpath),
                "model": self.diskinfo.disk_model(devpath),
                "used": 0,
                "services": {},
            }

        return data

    def shutdown(self):
        """
        The shutdown node action entrypoint.
        To be overloaded by child classes.
        """
        self.log.warning("to be implemented")

    def reboot(self):
        """
        The reboot node action entrypoint.
        """
        self.do_triggers("reboot", "pre")
        self.log.info("reboot")
        self._reboot()

    def do_triggers(self, action, when):
        """
        Determine which triggers need to be executed for the action and
        executes them when appropriate.
        """
        trigger = None
        blocking_trigger = None
        try:
            trigger = self.config.get(action, when)
        except:
            pass
        try:
            blocking_trigger = self.config.get(action, "blocking_"+when)
        except:
            pass
        if trigger:
            self.log.info("execute trigger %s", trigger)
            try:
                self.do_trigger(trigger)
            except ex.excError:
                pass
        if blocking_trigger:
            self.log.info("execute blocking trigger %s", blocking_trigger)
            try:
                self.do_trigger(blocking_trigger)
            except ex.excError:
                if when == "pre":
                    self.log.error("blocking pre trigger error: abort %s", action)
                raise

    def do_trigger(self, cmd, err_to_warn=False):
        """
        The trigger execution wrapper.
        """
        import shlex
        _cmd = shlex.split(cmd)
        ret, out, err = self.vcall(_cmd, err_to_warn=err_to_warn)
        if ret != 0:
            raise ex.excError((ret, out, err))

    def _reboot(self):
        """
        A system reboot method to be implemented by child classes.
        """
        self.log.warning("to be implemented")

    @lazy
    def sysreport_mod(self):
        try:
            return __import__('rcSysReport'+rcEnv.sysname)
        except ImportError:
            print("sysreport is not supported on this os")
            return

    def sysreport(self):
        """
        The sysreport node action entrypoint.

        Send to the collector a tarball of the files the user wants to track
        that changed since the last call.
        If the force option is set, send all files the user wants to track.
        """
        if self.sysreport_mod is None:
            return
        self.sysreport_mod.SysReport(node=self).sysreport(force=self.options.force)

    def get_prkey(self):
        """
        Returns the persistent reservation key.
        Once generated from the algorithm, the prkey is written to the config
        file to ensure its stability.
        """
        if self.config.has_option("node", "prkey"):
            hostid = self.config.get("node", "prkey")
            if len(hostid) > 18 or not hostid.startswith("0x") or \
               len(set(hostid[2:]) - set("0123456789abcdefABCDEF")) > 0:
                raise ex.excError("prkey in node.conf must have 16 significant"
                                  " hex digits max (ex: 0x90520a45138e85)")
            return hostid
        self.log.info("can't find a prkey forced in node.conf. generate one.")
        hostid = "0x"+self.hostid()
        if not self.config.has_section("node"):
            self.config.add_section("node")
        self.config.set('node', 'prkey', hostid)
        self.write_config()
        return hostid

    def prkey(self):
        """
        Print the persistent reservation key.
        """
        print(self.get_prkey())

    @staticmethod
    def hostid():
        """
        Return a stable host unique id
        """
        mod = __import__('hostid'+rcEnv.sysname)
        return mod.hostid()

    def checks(self):
        """
        The checks node action entrypoint.
        Runs health checks.
        """
        import checks
        if self.svcs is None:
            self.build_services()
        checkers = checks.checks(self.svcs)
        checkers.node = self
        data = checkers.do_checks()
        self.print_data(data)

    def wol(self):
        """
        Send a Wake-On-LAN packet to a mac address on the broadcast address.
        """
        import rcWakeOnLan
        if self.options.mac is None:
            print("missing parameter. set --mac argument. multiple mac "
                  "addresses must be separated by comma", file=sys.stderr)
            print("example 1 : --mac 00:11:22:33:44:55", file=sys.stderr)
            print("example 2 : --mac 00:11:22:33:44:55,66:77:88:99:AA:BB",
                  file=sys.stderr)
            return 1
        if self.options.broadcast is None:
            print("missing parameter. set --broadcast argument. needed to "
                  "identify accurate network to use", file=sys.stderr)
            print("example 1 : --broadcast 10.25.107.255", file=sys.stderr)
            print("example 2 : --broadcast 192.168.1.5,10.25.107.255",
                  file=sys.stderr)
            return 1
        macs = self.options.mac.split(',')
        broadcasts = self.options.broadcast.split(',')
        udpports = str(self.options.port).split(',')
        for brdcast in broadcasts:
            for mac in macs:
                for port in udpports:
                    req = rcWakeOnLan.wolrequest(macaddress=mac, broadcast=brdcast, udpport=port)
                    if not req.check_broadcast():
                        print("Error : skipping broadcast address <%s>, not in "
                              "the expected format 123.123.123.123" % req.broadcast,
                              file=sys.stderr)
                        break
                    if not req.check_mac():
                        print("Error : skipping mac address <%s>, not in the "
                              "expected format 00:11:22:33:44:55" % req.mac,
                              file=sys.stderr)
                        continue
                    if req.send():
                        print("Sent Wake On Lan packet to mac address <%s>"%req.mac)
                    else:
                        print("Error while trying to send Wake On Lan packet to "
                              "mac address <%s>" % req.mac, file=sys.stderr)

    def allocate_rid(self, group, sections):
        """
        Return an unused rid in <group>.
        """
        prefix = group + "#"
        rids = [section for section in sections if section.startswith(prefix)]
        idx = 1
        while True:
            rid = "#".join((group, str(idx)))
            if rid in rids:
                idx += 1
                continue
            return rid

    def register_as_node(self):
        """
        Returns a node registration unique id, authenticating to the
        collector as a user.
        """
        data = self.collector.call('register_node')
        if data is None:
            raise ex.excError("failed to obtain a registration number")
        elif isinstance(data, dict) and "ret" in data and data["ret"] != 0:
            msg = "failed to obtain a registration number"
            if "msg" in data and len(data["msg"]) > 0:
                msg += "\n" + data["msg"]
            raise ex.excError(msg)
        elif isinstance(data, list):
            raise ex.excError(data[0])
        return data

    def snooze(self):
        """
        Snooze notifications on the node.
        """
        if self.options.duration is None:
            print("set --duration", file=sys.stderr)
            raise ex.excError
        try:
            data = self.collector_rest_post("/nodes/self/snooze", {
                "duration": self.options.duration,
            })
        except Exception as exc:
            raise ex.excError(str(exc))
        if "error" in data:
            raise ex.excError(data["error"])
        print(data.get("info", ""))

    def unsnooze(self):
        """
        Unsnooze notifications on the node.
        """
        try:
            data = self.collector_rest_post("/nodes/self/snooze")
        except Exception as exc:
            raise ex.excError(str(exc))
        if "error" in data:
            raise ex.excError(data["error"])
        print(data.get("info", ""))

    def register_as_user(self):
        """
        Returns a node registration unique id, authenticating to the
        collector as a node.
        """
        try:
            data = self.collector_rest_post("/register", {
                "nodename": rcEnv.nodename,
                "app": self.options.app
            })
        except Exception as exc:
            raise ex.excError(str(exc))
        if "error" in data:
            raise ex.excError(data["error"])
        return data["data"]["uuid"]

    def register(self):
        """
        Do anonymous or indentified node register to obtain a node uuid
        that will be used as a password valid for the current hostname used
        as a username in the application code context.
        """
        if self.options.user is not None:
            register_fn = "register_as_user"
        else:
            register_fn = "register_as_node"
        try:
            rcEnv.uuid = getattr(self, register_fn)()
        except ex.excError as exc:
            print(exc, file=sys.stderr)
            return 1

        if not self.config.has_section('node'):
            self.config.add_section('node')
        self.config.set('node', 'uuid', rcEnv.uuid)

        try:
            self.write_config()
        except ex.excError:
            print("failed to write registration number: %s" % rcEnv.uuid,
                  file=sys.stderr)
            return 1

        print("registered")
        self.pushasset()
        self.pushdisks()
        self.pushpkg()
        self.pushpatch()
        self.sysreport()
        self.checks()
        return 0

    def service_action_worker(self, svc, action, options):
        """
        The method the per-service subprocesses execute
        """
        try:
            ret = svc.action(action, options)
        except Exception:
            self.close()
            sys.exit(1)
        finally:
            self.close()
        sys.exit(ret)

    @lazy
    def diskinfo(self):
        di = __import__('rcDiskInfo'+rcEnv.sysname)
        return di.diskInfo()

    @lazy
    def devtree(self):
        try:
            mod = __import__("rcDevTree"+rcEnv.sysname)
        except ImportError:
            return
        tree = mod.DevTree()
        tree.load()
        return tree

    def devlist(self):
        """
        Return the node's top-level device paths
        """
        devpaths = []
        for dev in self.devtree.get_top_devs():
            if len(dev.devpath) > 0:
                devpaths.append(dev.devpath[0])
        return devpaths

    def updatecomp(self):
        """
        Downloads and installs the compliance module archive from the url
        specified as node.repocomp or node.repo in node.conf.
        """
        if self.config.has_option('node', 'repocomp'):
            pkg_name = self.config.get('node', 'repocomp').strip('/') + "/current"
        elif self.config.has_option('node', 'repo'):
            pkg_name = self.config.get('node', 'repo').strip('/') + "/compliance/current"
        else:
            if self.options.cron:
                return 0
            print("node.repo or node.repocomp must be set in node.conf",
                  file=sys.stderr)
            return 1
        import tempfile
        tmpf = tempfile.NamedTemporaryFile()
        fpath = tmpf.name
        tmpf.close()
        try:
            ret = self._updatecomp(pkg_name, fpath)
        finally:
            if os.path.exists(fpath):
                os.unlink(fpath)
        return ret

    def _updatecomp(self, pkg_name, fpath):
        """
        Downloads and installs the compliance module archive from the url
        specified by the pkg_name argument. The download destination file
        is specified by fpath. The caller is responsible for its deletion.
        """
        print("get %s (%s)"%(pkg_name, fpath))
        try:
            self.urlretrieve(pkg_name, fpath)
        except IOError as exc:
            print("download failed", ":", exc, file=sys.stderr)
            if self.options.cron:
                return 0
            return 1
        tmpp = os.path.join(rcEnv.paths.pathtmp, 'compliance')
        backp = os.path.join(rcEnv.paths.pathtmp, 'compliance.bck')
        compp = os.path.join(rcEnv.paths.pathvar, 'compliance')
        makedirs(compp)
        import shutil
        try:
            shutil.rmtree(backp)
        except (OSError, IOError):
            pass
        print("extract compliance in", rcEnv.paths.pathtmp)
        import tarfile
        tar = tarfile.open(fpath)
        os.chdir(rcEnv.paths.pathtmp)
        try:
            tar.extractall()
            tar.close()
        except (OSError, IOError):
            print("failed to unpack", file=sys.stderr)
            return 1
        upstream_mods_d = os.path.join(tmpp, "com.opensvc")
        prev_upstream_mods_d = os.path.join(compp, "com.opensvc")
        if not os.path.exists(upstream_mods_d) and \
           os.path.exists(prev_upstream_mods_d):
            print("merge upstream com.opensvc compliance objects")
            shutil.copytree(prev_upstream_mods_d, upstream_mods_d,
                            symlinks=True)
        print("install new compliance")
        for root, dirs, files in os.walk(tmpp):
            for fpath in dirs:
                os.chown(os.path.join(root, fpath), 0, 0)
                for fpath in files:
                    os.chown(os.path.join(root, fpath), 0, 0)
        shutil.move(compp, backp)
        shutil.move(tmpp, compp)
        return 0

    def updatepkg(self):
        """
        Downloads and upgrades the OpenSVC agent, using the system-specific
        packaging tools.
        """
        try:
            branch = self.config.get("node", "branch")
            if branch != "":
                branch = "/" + branch
        except Exception:
            branch = ""

        try:
            pkg_format = self.conf_get("node", "pkg_format")
        except ex.OptNotFound as exc:
            pkg_format = exc.default

        if pkg_format == "tar":
            modname = 'rcUpdatePkgOSF1'
        else:
            modname = 'rcUpdatePkg'+rcEnv.sysname

        if not os.path.exists(os.path.join(rcEnv.paths.pathlib, modname+'.py')):
            print("updatepkg not implemented on", rcEnv.sysname, file=sys.stderr)
            return 1
        mod = __import__(modname)
        if self.config.has_option('node', 'repopkg'):
            pkg_name = self.config.get('node', 'repopkg').strip('/') + \
                       "/" + mod.repo_subdir + branch + '/current'
        elif self.config.has_option('node', 'repo'):
            pkg_name = self.config.get('node', 'repo').strip('/') + \
                       "/packages/" + mod.repo_subdir + branch + '/current'
        else:
            print("node.repo or node.repopkg must be set in node.conf",
                  file=sys.stderr)
            return 1
        import tempfile
        tmpf = tempfile.NamedTemporaryFile()
        fpath = tmpf.name
        tmpf.close()
        print("get %s (%s)"%(pkg_name, fpath))
        try:
            self.urlretrieve(pkg_name, fpath)
        except IOError as exc:
            print("download failed", ":", exc, file=sys.stderr)
            try:
                os.unlink(fpath)
            except OSError:
                pass
            return 1
        print("updating opensvc")
        mod.update(fpath)
        print("clean up")
        try:
            os.unlink(fpath)
        except OSError:
            pass
        os.system("%s pushasset" % rcEnv.paths.nodemgr)
        return 0

    def array(self):
        """
        Execute a array command, passing extra_argv to the array driver.
        """
        array_name = None
        for idx, arg in enumerate(self.options.extra_argv):
            if arg.startswith("--array="):
                array_name = arg[arg.index("=")+1:]
                break
            if (arg == "-a" or arg == "--array") and idx+1 < len(self.options.extra_argv):
                array_name = self.options.extra_argv[idx+1]
                break

        if array_name is None:
            raise ex.excError("can not determine array driver (no --array)")

        self.load_auth_config()

        section = None

        for _section in self.auth_config.sections():
            if _section == array_name:
                section = _section
                break
            if self.auth_config.has_option(_section, "array") and \
               array_name in self.auth_config.get(_section, "array").split():
                section = _section
                break

        if section is None:
            raise ex.excError("array '%s' not found in %s" % (array_name, rcEnv.paths.authconf))

        if not self.auth_config.has_option(section, "type"):
            raise ex.excError("%s must have a '%s.type' option" % (rcEnv.paths.authconf, section))

        driver = self.auth_config.get(section, "type")
        rtype = driver[0].upper() + driver[1:].lower()
        modname = "rc" + rtype
        try:
            mod = __import__(modname)
        except ImportError as exc:
            raise ex.excError("driver %s load error: %s" % (modname, str(exc)))
        return mod.main(self.options.extra_argv, node=self)

    def get_ruser(self, node):
        """
        Returns the remote user to use for remote commands on the node
        specified as argument.
        If not specified as node.ruser in the node configuration file,
        the root user is returned.
        """
        default = "root"
        if not self.config.has_option('node', "ruser"):
            return default
        node_ruser = {}
        elements = self.config.get('node', 'ruser').split()
        for element in elements:
            subelements = element.split("@")
            if len(subelements) == 1:
                default = element
            elif len(subelements) == 2:
                _ruser, _node = subelements
                node_ruser[_node] = _ruser
            else:
                continue
        if node in node_ruser:
            return node_ruser[node]
        return default

    def dequeue_actions(self):
        """
        The dequeue_actions node action entrypoint.
        Poll the collector action queue until emptied.
        """
        while True:
            actions = self.collector.call('collector_get_action_queue')
            if actions is None:
                raise ex.excError("unable to fetch actions scheduled by the collector")
            n_actions = len(actions)
            if n_actions == 0:
                break
            data = []
            reftime = time.time()
            for action in actions:
                ret, out, err = self.dequeue_action(action)
                out = ANSI_ESCAPE.sub('', out)
                err = ANSI_ESCAPE.sub('', err)
                data.append((action.get('id'), ret, out, err))
                now = time.time()
                if now > reftime + 2:
                    # this action was long, update the collector now
                    self.collector.call('collector_update_action_queue', data)
                    reftime = time.time()
                    data = []
            if len(data) > 0:
                self.collector.call('collector_update_action_queue', data)

    @staticmethod
    def dequeue_action(action):
        """
        Execute the nodemgr or svcmgr action described in payload element
        received from the collector's action queue.
        """
        if action.get("svc_id") in (None, "") or action.get("svcname") in (None, ""):
            cmd = [rcEnv.paths.nodemgr]
        else:
            cmd = [rcEnv.paths.svcmgr, "-s", action.get("svcname")]
        import shlex
        cmd += shlex.split(action.get("command", ""))
        print("dequeue action %s" % " ".join(cmd))
        out, err, ret = justcall(cmd)
        return ret, out, err

    def rotate_root_pw(self):
        """
        Generate a random password, send it to the collector and set it as
        the root user password.
        """
        passwd = self.genpw()

        from collector import Collector
        coll = Collector(self.options, self)
        try:
            getattr(coll, 'rotate_root_pw')(passwd)
        except Exception as exc:
            print("unexpected error sending the new password to the collector "
                  "(%s). Abording password change." % str(exc), file=sys.stderr)
            return 1

        try:
            mod = __import__('rcPasswd'+rcEnv.sysname)
        except ImportError:
            print("not implemented")
            return 1
        ret = mod.change_root_pw(passwd)
        if ret == 0:
            print("root password changed")
        else:
            print("failed to change root password")
        return ret

    @staticmethod
    def genpw():
        """
        Returns a random password.
        """
        import string
        chars = string.ascii_letters + string.digits + r'+/'
        assert 256 % len(chars) == 0
        pwd_len = 16
        return ''.join(chars[ord(c) % len(chars)] for c in os.urandom(pwd_len))

    def scanscsi(self):
        """
        Rescans the scsi host buses for new logical units discovery.
        """
        self._scanscsi(self.options.hba, self.options.target, self.options.lun)

    def _scanscsi(self, hba=None, target=None, lun=None):
        try:
            mod = __import__("rcDiskInfo"+rcEnv.sysname)
        except ImportError:
            print("scanscsi is not supported on", rcEnv.sysname, file=sys.stderr)
            return 1
        diskinfo = mod.diskInfo()
        if not hasattr(diskinfo, 'scanscsi'):
            print("scanscsi is not implemented on", rcEnv.sysname, file=sys.stderr)
            return 1
        return diskinfo.scanscsi(
            hba=hba,
            target=target,
            lun=lun,
        )

    def cloud_get(self, section):
        """
        Get the cloud object instance handling the config file section passed
        as argument. If not already instanciated, create the instance and
        store it in a dict hashed by section name.
        """
        if not section.startswith("cloud"):
            return

        if not section.startswith("cloud#"):
            raise ex.excInitError("cloud sections must have a unique name in "
                                  "the form '[cloud#n] in %s" % rcEnv.paths.nodeconf)

        if self.clouds and section in self.clouds:
            return self.clouds[section]

        if not self.config.has_option(section, "type"):
            raise ex.excInitError("type option is mandatory in cloud section "
                                  "in %s" % rcEnv.paths.nodeconf)
        cloud_type = self.config.get(section, 'type')

        if len(cloud_type) == 0:
            raise ex.excInitError("invalid cloud type in %s"%rcEnv.paths.nodeconf)

        self.load_auth_config()
        if not self.auth_config.has_section(section):
            raise ex.excInitError("%s must have a '%s' section" % (rcEnv.paths.authconf, section))

        auth_dict = {}
        for key, val in self.auth_config.items(section):
            auth_dict[key] = val

        mod_name = "rcCloud" + cloud_type[0].upper() + cloud_type[1:].lower()

        try:
            mod = __import__(mod_name)
        except ImportError:
            raise ex.excInitError("cloud type '%s' is not supported"%cloud_type)

        if self.clouds is None:
            self.clouds = {}
        cloud = mod.Cloud(section, auth_dict)
        self.clouds[section] = cloud
        return cloud

    def can_parallel(self, action, options):
        """
        Returns True if the action can be run in a subprocess per service
        """
        if rcEnv.sysname == "Windows":
            return False
        if len(self.svcs) < 2:
            return False
        if options.parallel and action not in ACTIONS_NO_PARALLEL:
            return True
        return False

    @staticmethod
    def action_need_aggregate(action, options):
        """
        Returns True if the action returns data from multiple sources (nodes
        or services) to arrange for display.
        """
        if action.startswith("print_") and options.format in ("json", "flat_json"):
            return True
        if action.startswith("json_"):
            return True
        if action.startswith("collector_"):
            return True
        if "_json_" in action:
            return True
        return False

    def do_svcs_action(self, action, options):
        """
        The services action wrapper.
        Takes care of
        * parallelization of the action in per-service subprocesses
        * collection and aggregation of returned data and errors
        """
        if action == "ls":
            data = self.strip_ns(sorted([svc.svcpath for svc in self.svcs]), options.namespace)
            if options.format == "json":
                print(json.dumps(data, indent=4, sort_keys=True))
            else:
                print("\n".join(data))
            return

        err = 0
        data = Storage()
        data.outs = {}
        need_aggregate = self.action_need_aggregate(action, options)

        # generic cache janitoring
        purge_cache_expired()
        self.log.debug("session uuid: %s", rcEnv.session_uuid)

        if action in ACTIONS_NO_MULTIPLE_SERVICES and len(self.svcs) > 1:
            print("action '%s' is not allowed on multiple services" % action, file=sys.stderr)
            return 1

        if self.can_parallel(action, options):
            from multiprocessing import Process
            data.procs = {}
            data.svcs = {}

        timeout = 0
        if not options.local and options.wait:
            # submit all async actions and wait only after to avoid
            # max_parallel breaking inter service dependencies
            timeout = convert_duration(options.time)
            options.wait = False

        def running():
            count = 0
            for proc in data.procs.values():
                if proc.is_alive():
                    count += 1
            return count

        for svc in self.svcs:
            if self.can_parallel(action, options):
                while running() >= self.max_parallel:
                    time.sleep(1)
                data.svcs[svc.svcpath] = svc
                data.procs[svc.svcpath] = Process(
                    target=self.service_action_worker,
                    name='worker_'+svc.svcpath,
                    args=[svc, action, options],
                )
                data.procs[svc.svcpath].start()
            else:
                try:
                    ret = svc.action(action, options)
                    if need_aggregate:
                        if ret is not None:
                            data.outs[svc.svcpath] = ret
                    elif action.startswith("print_"):
                        self.print_data(ret)
                        if isinstance(ret, dict):
                            if "error" in ret:
                                err += 1
                    else:
                        if ret is None:
                            ret = 0
                        elif isinstance(ret, list):
                            ret = 0
                        elif isinstance(ret, dict):
                            if "error" in ret:
                                print(ret["error"], file=sys.stderr)
                            else:
                                print("unsupported format for this action", file=sys.stderr)
                            ret = 1
                        err += ret
                except ex.excError as exc:
                    ret = 1
                    err += ret
                    if not need_aggregate:
                        print("%s: %s" % (svc.svcpath, exc), file=sys.stderr)
                    continue
                except ex.excSignal:
                    break

        if self.can_parallel(action, options):
            for svcpath in data.procs:
                data.procs[svcpath].join()
                ret = data.procs[svcpath].exitcode
                if ret > 0:
                    # r is negative when data.procs[svcpath] is killed by signal.
                    # in this case, we don't want to decrement the err counter.
                    err += ret
        if timeout:
            for svc in self.svcs:
                global_expect = svc.prepare_global_expect(action)
                begin = time.time()
                svc.wait_daemon_mon_action(global_expect, wait=True, timeout=timeout, log_progress=False)
                timeout = timeout - (time.time() - begin)
                if timeout < 0:
                    break

        if need_aggregate:
            if self.options.single_service:
                svcpath = self.svcs[0].svcpath
                if svcpath not in data.outs:
                    return 1
                self.print_data(data.outs[svcpath])
            else:
                self.print_data(data.outs)

        return err

    def collector_cli(self):
        """
        The collector cli entrypoint.
        """
        data = {}

        if self.options.user is None and self.options.config is None and os.getuid() == 0:
            if self.options.user is None:
                user, password = self.collector_auth_node()
                data["user"] = user
                data["password"] = password
                data["save"] = False
            if self.options.api is None:
                if rcEnv.dbopensvc is None:
                    raise ex.excError("node.dbopensvc is not set in node.conf")
                data["api"] = rcEnv.dbopensvc.replace("/feed/default/call/xmlrpc", "/init/rest/api")
        else:
            data["user"] = self.options.user
            data["password"] = self.options.password
            data["api"] = self.options.api
            data["save"] = self.options.save

        data["insecure"] = self.options.insecure
        data["refresh_api"] = self.options.refresh_api
        data["fmt"] = self.options.format
        if self.options.config:
            data["config"] = self.options.config
        argv = [word for word in self.options.extra_argv]
        argv = drop_option("--refresh-api", argv, drop_value=False)
        argv = drop_option("--insecure", argv, drop_value=False)
        argv = drop_option("--save", argv, drop_value=False)
        argv = drop_option("--help", argv, drop_value=False)
        argv = drop_option("--debug", argv, drop_value=False)
        argv = drop_option("--format", argv, drop_value=True)
        argv = drop_option("--color", argv, drop_value=True)
        argv = drop_option("--api", argv, drop_value=True)
        argv = drop_option("--config", argv, drop_value=True)
        argv = drop_option("--user", argv, drop_value=True)
        argv = drop_option("--password", argv, drop_value=True)
        return self._collector_cli(data, argv)

    def _collector_cli(self, data, argv):
        from rcCollectorCli import Cli
        cli = Cli(**data)
        return cli.run(argv=argv)

    def download_from_safe(self, safe_id, svcname=None):
        import base64
        from rcUtilities import bdecode
        if safe_id.startswith("safe://"):
            safe_id = safe_id[7:].lstrip("/")
        fpath = os.path.join(rcEnv.paths.safe, safe_id)
        if os.path.exists(fpath):
            with open(fpath, "r") as ofile:
                buff = ofile.read()
            nodename, data = self.decrypt(buff)
            if data is None:
                raise ex.excError("no data")
            data = data["data"]
            try:
                return base64.urlsafe_b64decode(data)
            except TypeError:
                return base64.urlsafe_b64decode(data.encode())
        path = "/safe/%s/download" % safe_id
        api = self.collector_api(svcname=svcname)
        request = self.collector_request(path)
        if api["url"].startswith("https"):
            try:
                import ssl
                kwargs = {"context": ssl._create_unverified_context()}
            except:
                kwargs = {}
        else:
            raise ex.excError("refuse to submit auth tokens through a non-encrypted transport")
        try:
            f = urlopen(request, **kwargs)
        except HTTPError as e:
            try:
                err = json.loads(e.read())["error"]
                e = ex.excError(err)
            except ValueError:
                pass
            raise e
        buff = b""
        for chunk in iter(lambda: f.read(4096), b""):
            buff += chunk
        data = {"data": bdecode(base64.urlsafe_b64encode(buff))}
        makedirs(rcEnv.paths.safe)
        with open(fpath, 'w') as df:
            pass
        os.chmod(fpath, 0o0600)
        with open(fpath, 'w') as df:
            df.write(self.encrypt(data, encode=False))
        f.close()
        return buff

    def collector_api(self, svcname=None):
        """
        Prepare the authentication info, either as node or as user.
        Fetch and cache the collector's exposed rest api metadata.
        """
        if rcEnv.dbopensvc is None:
            raise ex.excError("node.dbopensvc is not set in node.conf")
        elif rcEnv.dbopensvc_host == "none":
            raise ex.excError("node.dbopensvc is set to 'none' in node.conf")
        data = {}
        if self.options.user is None:
            username, password = self.collector_auth_node()
            if svcname:
                username = svcname+"@"+username
        else:
            username, password = self.collector_auth_user()
        data["username"] = username
        data["password"] = password
        data["url"] = rcEnv.dbopensvc.replace("/feed/default/call/xmlrpc", "/init/rest/api")
        if not data["url"].startswith("http"):
            data["url"] = "https://%s" % data["url"]
        return data

    def collector_auth_node(self):
        """
        Returns the authentcation info for login as node
        """
        username = rcEnv.nodename
        if not self.config.has_option("node", "uuid"):
            raise ex.excError("the node is not registered yet. use 'nodemgr register [--user <user>]'")
        password = self.config.get("node", "uuid")
        return username, password

    def collector_auth_user(self):
        """
        Returns the authentcation info for login as user
        """
        username = self.options.user

        if self.options.password and self.options.password != "?":
            return username, self.options.password

        import getpass
        try:
            password = getpass.getpass()
        except EOFError:
            raise KeyboardInterrupt()
        return username, password

    def collector_request(self, path, svcname=None):
        """
        Make a request to the collector's rest api
        """
        import base64
        api = self.collector_api(svcname=svcname)
        url = api["url"]
        if not url.startswith("https"):
            raise ex.excError("refuse to submit auth tokens through a "
                              "non-encrypted transport")
        request = Request(url+path)
        auth_string = '%s:%s' % (api["username"], api["password"])
        if six.PY3:
            base64string = base64.encodestring(auth_string.encode()).decode()
        else:
            base64string = base64.encodestring(auth_string)
        base64string = base64string.replace('\n', '')
        request.add_header("Authorization", "Basic %s" % base64string)
        return request

    def collector_rest_get(self, path, data=None, svcname=None):
        """
        Make a GET request to the collector's rest api
        """
        return self.collector_rest_request(path, data=data, svcname=svcname)

    def collector_rest_post(self, path, data=None, svcname=None):
        """
        Make a POST request to the collector's rest api
        """
        return self.collector_rest_request(path, data, svcname=svcname, get_method="POST")

    def collector_rest_put(self, path, data=None, svcname=None):
        """
        Make a PUT request to the collector's rest api
        """
        return self.collector_rest_request(path, data, svcname=svcname, get_method="PUT")

    def collector_rest_delete(self, path, data=None, svcname=None):
        """
        Make a DELETE request to the collector's rest api
        """
        return self.collector_rest_request(path, data, svcname=svcname, get_method="DELETE")

    @staticmethod
    def set_ssl_context(kwargs):
        """
        Python 2.7.9+ verifies certs by default and support the creationn
        of an unverified context through ssl._create_unverified_context().
        This method add an unverified context to a kwargs dict, when
        necessary.
        """
        try:
            import ssl
            kwargs["context"] = ssl._create_unverified_context()
        except (ImportError, AttributeError):
            pass
        return kwargs

    def urlretrieve(self, url, fpath):
        """
        A chunked download method
        """
        request = Request(url)
        kwargs = {}
        kwargs = self.set_ssl_context(kwargs)
        ufile = urlopen(request, **kwargs)
        with open(fpath, 'wb') as ofile:
            for chunk in iter(lambda: ufile.read(4096), b""):
                ofile.write(chunk)
        ufile.close()

    def collector_rest_request(self, path, data=None, svcname=None, get_method="GET"):
        """
        Make a request to the collector's rest api
        """
        if data is not None and get_method == "GET":
            if len(data) == 0 or not isinstance(data, dict):
                data = None
            else:
                path += "?" + urlencode(data)
                data = None

        request = self.collector_request(path, svcname=svcname)
        if get_method:
            request.get_method = lambda: get_method
        if data is not None:
            try:
                request.add_data(urlencode(data))
            except AttributeError:
                request.data = urlencode(data).encode('utf-8')
        kwargs = {}
        kwargs = self.set_ssl_context(kwargs)
        try:
            ufile = urlopen(request, **kwargs)
        except HTTPError as exc:
            try:
                err = json.loads(exc.read())["error"]
                exc = ex.excError(err)
            except (ValueError, TypeError):
                pass
            raise exc
        except IOError as exc:
            if hasattr(exc, "reason"):
                raise ex.excError(getattr(exc, "reason"))
            raise ex.excError(str(exc))
        data = json.loads(ufile.read().decode("utf-8"))
        ufile.close()
        return data

    def collector_rest_get_to_file(self, path, fpath):
        """
        Download bulk chunked data from the collector's rest api
        """
        request = self.collector_request(path)
        kwargs = {}
        kwargs = self.set_ssl_context(kwargs)
        try:
            ufile = urlopen(request, **kwargs)
        except HTTPError as exc:
            try:
                err = json.loads(exc.read())["error"]
                exc = ex.excError(err)
            except ValueError:
                pass
            raise exc
        with open(fpath, 'wb') as ofile:
            for chunk in iter(lambda: ufile.read(4096), b""):
                ofile.write(chunk)
        ufile.close()

    def install_svc_conf_from_templ(self, svcname, namespace, template, restore=False):
        """
        Download a provisioning template from the collector's rest api,
        and installs it as the service configuration file.
        """
        pathetc = svc_pathetc(svcname, namespace)
        fpath = os.path.join(pathetc, svcname+'.conf')
        makedirs(pathetc)
        try:
            int(template)
            url = "/provisioning_templates/"+str(template)+"?props=tpl_definition&meta=0"
        except ValueError:
            url = "/provisioning_templates?filters=tpl_name="+template+"&props=tpl_definition&meta=0"
        data = self.collector_rest_get(url)
        if "error" in data:
            raise ex.excError(data["error"])
        if len(data["data"]) == 0:
            raise ex.excError("service not found on the collector")
        if len(data["data"][0]["tpl_definition"]) == 0:
            raise ex.excError("service has an empty configuration")
        with open(fpath, "w") as ofile:
            ofile.write(data["data"][0]["tpl_definition"].replace("\\n", "\n").replace("\\t", "\t"))
        self.install_svc_conf_from_file(svcname, namespace, fpath, restore)

    def install_svc_conf_from_uri(self, svcname, namespace, fpath, restore=False):
        """
        Download a provisioning template from an arbitrary uri,
        and installs it as the service configuration file.
        """
        import tempfile
        tmpf = tempfile.NamedTemporaryFile()
        tmpfpath = tmpf.name
        tmpf.close()
        print("get %s (%s)" % (fpath, tmpfpath))
        try:
            self.urlretrieve(fpath, tmpfpath)
        except IOError as exc:
            print("download failed", ":", exc, file=sys.stderr)
            try:
                os.unlink(tmpfpath)
            except OSError:
                pass
        self.install_svc_conf_from_file(svcname, namespace, tmpfpath, restore)

    def install_svc_conf_from_file(self, svcname, namespace, fpath, restore=False):
        """
        Installs a local template as the service configuration file.
        """
        if not os.path.exists(fpath):
            raise ex.excError("%s does not exists" % fpath)

        pathetc = svc_pathetc(svcname, namespace)
        makedirs(pathetc)
        src_cf = os.path.realpath(fpath)
        dst_cf = os.path.join(pathetc, svcname+'.conf')
        if dst_cf == src_cf:
            return

        import tempfile
        tmpf = tempfile.NamedTemporaryFile()
        tmpfpath = tmpf.name
        tmpf.close()

        import shutil
        shutil.copy2(src_cf, tmpfpath)

        from svc import Svc
        import uuid
        svc = Svc(svcname, cf=tmpfpath, node=self)
        if not restore:
            try:
                svc.conf_get("DEFAULT", "id")
                svc._unset("DEFAULT", "id")
            except ex.OptNotFound:
                pass
        svc.validate_config(tmpfpath)

        # install the configuration file in etc/
        shutil.move(tmpfpath, dst_cf)

        if src_cf.startswith(rcEnv.paths.pathtmp):
            os.unlink(src_cf)

    @staticmethod
    def install_svc_conf_from_data(svcname, namespace, data, restore=False):
        """
        Installs a service configuration file from section, keys and values
        fed from a data structure.
        """
        pathetc = svc_pathetc(svcname, namespace)
        fpath = os.path.join(pathetc, svcname+'.conf')
        config = rcConfigParser.RawConfigParser()

        for section_name, section in data.items():
            if section_name != "DEFAULT":
                config.add_section(section_name)
            for key, value in section.items():
                if not restore:
                    if section_name == "DEFAULT" and key == "id":
                        continue
                config.set(section_name, key, value)
        makedirs(pathetc)
        import codecs
        try:
            if six.PY2:
                with codecs.open(fpath, "w", "utf-8") as ofile:
                    config.write(ofile)
            else:
                with open(fpath, "w") as ofile:
                    config.write(ofile)
        except Exception as exc:
            print("failed to write %s: %s" % (fpath, exc), file=sys.stderr)
            raise Exception()

    def install_service(self, svcpath, fpath=None, template=None,
                        restore=False, resources=[], namespace=None):
        """
        Pick a collector's template, arbitrary uri, or local file service
        configuration file fetching method. Run it, and create the
        service symlinks and launchers directory.
        """
        data = None
        if sys.stdin and fpath in ("-", "/dev/stdin"):
            feed = ""
            for line in sys.stdin.readlines():
                feed += line
            if feed:
                try:
                    data = json.loads("".join(feed))
                except ValueError:
                    raise ex.excError("invalid json feed")

        if fpath is not None and template is not None:
            raise ex.excError("--config and --template can't both be specified")

        if namespace:
            validate_name(namespace)

        if svcpath:
            svcname, namespace = split_svcpath(svcpath)
            validate_name(svcname)
            if namespace:
                validate_name(namespace)
        elif not data:
            raise ex.excError("feed service configurations to stdin and set --config=-")
        else:
            for _svcpath, _data in data.items():
                if namespace:
                    # discard namespace in svcpath, use --namespace value instead
                    svcname, _ = split_svcpath(_svcpath)
                    _namespace = namespace
                else:
                    svcname, _namespace = split_svcpath(_svcpath)
                validate_name(svcname)
                print("create %s" % fmt_svcpath(svcname, _namespace))
                self.install_svc_conf_from_data(svcname, _namespace, _data, restore)
                self.install_service_files(svcname, namespace)
            return

        if not exe_link_exists(svcname, namespace):
            # freeze before the installing the config so the daemon never
            # has a chance to consider the new service unfrozen and take undue
            # action before we have the change to modify the service config
            Freezer(svcpath).freeze()

        if data is not None:
            self.install_svc_conf_from_data(svcname, namespace, data, restore)
        elif template is not None:
            if "://" in template:
                self.install_svc_conf_from_uri(svcname, namespace, template, restore)
            elif os.path.exists(template):
                self.install_svc_conf_from_file(svcname, namespace, template, restore)
            else:
                self.install_svc_conf_from_templ(svcname, namespace, template, restore)
        elif fpath is not None:
            if "://" in fpath:
                self.install_svc_conf_from_uri(svcname, namespace, fpath, restore)
            else:
                self.install_svc_conf_from_file(svcname, namespace, fpath, restore)
        else:
            self.install_svc_from_args(svcname, namespace, resources)

        self.install_service_files(svcname, namespace)
        self.wake_monitor()

    @staticmethod
    def install_service_files(svcname, namespace=None):
        """
        Given a service name, install the symlink to svcmgr.
        """
        if rcEnv.sysname == 'Windows':
            return

        # install svcmgr link
        pathetc = svc_pathetc(svcname, namespace)
        makedirs(pathetc)
        svcmgr_l = os.path.join(pathetc, svcname)
        if not os.path.exists(svcmgr_l):
            os.symlink(rcEnv.paths.svcmgr, svcmgr_l)
        elif os.path.realpath(rcEnv.paths.svcmgr) != os.path.realpath(svcmgr_l):
            os.unlink(svcmgr_l)
            os.symlink(rcEnv.paths.svcmgr, svcmgr_l)

    def set_rlimit(self, nofile=4096):
        """
        Set the operating system nofile rlimit to a sensible value for the
        number of services configured.
        """
        #self.log.debug("len self.svcs <%s>", len(self.svcs))
        n_conf = len(glob_services_config())
        proportional_nofile = 64 * n_conf
        if proportional_nofile > nofile:
            nofile = proportional_nofile

        try:
            import resource
            _vs, _vg = resource.getrlimit(resource.RLIMIT_NOFILE)
            if _vs < nofile:
                self.log.debug("raise nofile resource from %d limit to %d", _vs, nofile)
                if nofile > _vg:
                    _vg = nofile
                resource.setrlimit(resource.RLIMIT_NOFILE, (nofile, _vg))
            else:
                self.log.debug("current nofile %d already over minimum %d", _vs, nofile)
        except Exception as exc:
            self.log.debug(str(exc))

    def install_svc_from_args(self, svcname, namespace=None, resources=[]):
        """
        Create a new service from resource definitions passed as individual
        dictionaries in json format.
        """
        if len(svcname) == 0:
            print("service name must not be empty", file=sys.stderr)
            return {"ret": 1}
        if svcname in list_services(namespace):
            print("service", svcname, "already exists", file=sys.stderr)
            return {"ret": 1}
        pathetc = svc_pathetc(svcname, namespace)
        cf = os.path.join(pathetc, svcname+'.conf')
        if os.path.exists(cf):
            import shutil
            print(cf, "already exists. save as "+svcname+".conf.bak", file=sys.stderr)
            shutil.move(cf, os.path.join(rcEnv.paths.pathtmp, svcname+".conf.bak"))
        makedirs(pathetc)
        try:
            f = open(cf, 'w')
        except:
            print("failed to open", cf, "for writing", file=sys.stderr)
            return {"ret": 1}

        import uuid

        defaults = {
           "id": str(uuid.uuid4()),
        }
        sections = {}
        rtypes = {}

        for r in resources:
            try:
                d = json.loads(r)
            except:
                print("can not parse resource:", r, file=sys.stderr)
                return {"ret": 1}
            if 'rid' in d:
                section = d['rid']
                if '#' not in section:
                    print(section, "must be formatted as 'rtype#n'", file=sys.stderr)
                    return {"ret": 1}
                l = section.split('#')
                if len(l) != 2:
                    print(section, "must be formatted as 'rtype#n'", file=sys.stderr)
                    return {"ret": 1}
                rtype = l[1]
                if rtype in rtypes:
                    rtypes[rtype] += 1
                else:
                    rtypes[rtype] = 0
                del d['rid']
                if section in sections:
                    sections[section].update(d)
                else:
                    sections[section] = d
            elif 'rtype' in d and d["rtype"] == "env":
                del d["rtype"]
                if "env" in sections:
                    sections["env"].update(d)
                else:
                    sections["env"] = d
            elif 'rtype' in d and d["rtype"] != "DEFAULT":
                if 'rid' in d:
                    del d['rid']
                rtype = d['rtype']
                if rtype in rtypes:
                    section = '%s#%d'%(rtype, rtypes[rtype])
                    rtypes[rtype] += 1
                else:
                    section = '%s#0'%rtype
                    rtypes[rtype] = 1
                if section in sections:
                    sections[section].update(d)
                else:
                    sections[section] = d
            else:
                if "rtype" in d:
                    del d["rtype"]
                defaults.update(d)

        from svcdict import KEYS
        from keywords import MissKeyNoDefault, KeyInvalidValue
        try:
            defaults.update(KEYS.update('DEFAULT', defaults))
            for section, d in sections.items():
                sections[section].update(KEYS.update(section, d))
        except (MissKeyNoDefault, KeyInvalidValue):
            return {"ret": 1}

        conf = rcConfigParser.RawConfigParser(defaults)
        for section, d in sections.items():
            conf.add_section(section)
            for key, val in d.items():
                if key == 'rtype':
                    continue
                conf.set(section, key, val)

        conf.write(f)
        self.install_service_files(svcname, namespace)
        return {"ret": 0, "rid": sections.keys()}

    def create_svcpath(self, svcpaths, namespace):
        if isinstance(svcpaths, list):
            if len(svcpaths) != 1:
                raise ex.excError("only one service must be specified")
            svcpath = svcpaths[0]

        try:
           svcpath.encode("ascii")
        except Exception:
           raise ex.excError("the service name must be ascii-encodable")

        if "/" not in svcpath and namespace:
            svcpath = fmt_svcpath(svcpath, namespace)

        if svcpath.count("/") > 1:
            raise ex.excError("invalid namespace name: slash is not allowed.")
        return svcpath

    def create_service(self, svcpaths, options):
        """
        The "svcmgr create" entrypoint.
        """
        ret = 0
        if svcpaths:
            svcpath = self.create_svcpath(svcpaths, options.namespace)
        else:
            svcpath = None

        try:
            self.install_service(svcpath, fpath=options.config,
                                   template=options.template,
                                   restore=options.restore,
                                   resources=options.resource,
                                   namespace=options.namespace)
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1

        # force a refresh of self.svcs
        try:
            self.rebuild_services(svcpaths)
        except ex.excError as exc:
            print(exc, file=sys.stderr)
            ret = 1

        if len(self.svcs) == 1:
            self.svcs[0].setenv(options.env, options.interactive)
            # setenv changed the service config file
            # we need to rebuild again
            try:
                self.rebuild_services(svcpaths)
            except ex.excError as exc:
                print(exc, file=sys.stderr)
                ret = 1

            if options.provision:
                self.svcs[0].action("provision", options)

        return ret

    def wait(self):
        """
        Wait for a condition on the monitor thread data.
        Catch broken pipe.
        """
        path = self.options.jsonpath_filter
        nodename = self.options.node
        duration = self.options.duration
        try:
            self._wait(nodename, path, duration)
        except KeyboardInterrupt:
            return 1
        except (OSError, IOError) as exc:
            if exc.errno == 32:
                # broken pipe
                return 1

    def _wait(self, nodename=None, path=None, duration=None):
        """
        Wait for a condition on the monitor thread data or
        a local event data.
        """
        import json_delta

        if not path:
            return

        if nodename is None:
            nodename = rcEnv.nodename

        ops = (">=", "<=", "=", ">", "<", "~")
        oper = None
        val = None

        if path[0] == "!":
            path = path[1:]
            neg = True
        else:
            neg = False

        for op in ops:
            idx = path.rfind(op)
            if idx < 0:
                continue
            val = path[idx+len(op):].strip()
            path = path[:idx].strip()
            oper = op
            if op == "~":
                if not val.startswith(".*") and not val.startswith("^"):
                    val = ".*" + val
                if not val.endswith(".*") and not val.endswith("$"):
                    val = val + ".*"
            break

        try:
            jsonpath_expr = parse(path)
        except Exception as exc:
            raise ex.excError(exc)

        def eval_cond(val, data):
            for match in jsonpath_expr.find(data):
                if oper is None:
                    if match.value:
                        return True
                    else:
                        continue
                obj_class = type(match.value)
                try:
                    if obj_class == bool:
                        val = convert_boolean(val)
                    else:
                        val = obj_class(val)
                except Exception as exc:
                    raise ex.excError("can not convert to a common type")
                if oper is None:
                    if match.value:
                        return True
                if oper == "=":
                    if match.value == val:
                        return True
                elif oper == ">":
                    if match.value > val:
                        return True
                elif oper == "<":
                    if match.value < val:
                        return True
                elif oper == ">=":
                    if match.value >= val:
                        return True
                elif oper == "<=":
                    if match.value <= val:
                        return True
                elif is_string(match.value) and oper == "~":
                    if re.match(val, match.value):
                        return True
            return False

        def match_patch(msg):
            if neg ^ eval_cond(val, cluster_data):
                return True
            return False

        def match_event(msg):
            if neg ^ eval_cond(val, msg):
                return True
            return False

        cluster_data = self._daemon_status()["monitor"]["nodes"]
        if neg ^ eval_cond(val, cluster_data):
            return

        if duration:
            import signal
            def alarm_handler(signum, frame):
                print("timeout", file=sys.stderr)
                raise KeyboardInterrupt
            signal.signal(signal.SIGALRM, alarm_handler)
            signal.alarm(convert_duration(duration))

        for msg in self.daemon_events(nodename):
            kind = msg.get("kind")
            if kind == "patch":
                _nodename = msg.get("nodename")
                json_delta.patch(cluster_data[_nodename], msg["data"])
                if match_patch(msg):
                    break
            elif kind == "event":
                if match_event(msg):
                    break

    def events(self, nodename=None):
        try:
            self._events(nodename=nodename)
        except ex.excSignal:
            return
        except (OSError, IOError) as exc:
            if exc.errno == 32:
                # broken pipe
                return

    def _events(self, nodename=None):
        if self.options.node:
            nodename = self.options.node
        elif nodename is None:
            nodename = rcEnv.nodename
        for msg in self.daemon_events(nodename):
            if self.options.format == "json":
                print(json.dumps(msg))
                sys.stdout.flush()
            else:
                kind = msg.get("kind")
                print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"), msg.get("nodename", ""), kind)
                if kind == "patch":
                    for event in msg["data"]:
                        try:
                            key, val = event
                            line = "  %s => %s" % (".".join([str(k) for k in key]), str(val))
                        except ValueError:
                            line = "  %s deleted" % ".".join([str(k) for k in event[0]])
                        print(line)
                        sys.stdout.flush()
                elif kind == "event":
                    for key, val in msg.get("data", {}).items():
                        print("  %s=%s" % ((str(key).upper(), str(val))))

    def logs(self, nodename=None):
        try:
            self._logs(nodename=nodename)
        except ex.excSignal:
            return
        except (OSError, IOError) as exc:
            if exc.errno == 32:
                # broken pipe
                return

    def _logs(self, nodename=None):
        if nodename is None:
            nodename = self.options.node
        if self.options.local:
            nodes = [rcEnv.nodename]
        elif self.options.node:
            nodes = [self.options.node]
        else:
            nodes = self.cluster_nodes
        from rcColor import colorize_log_line
        lines = []
        auto = sorted(nodes, reverse=True) + sorted(list_services(), reverse=True)
        for nodename in nodes:
            lines += self.daemon_backlogs(nodename)
            for line in sorted(lines):
                line = colorize_log_line(line, auto=auto)
                if line:
                    print(line)
        if not self.options.follow:
            return
        for line in self.daemon_logs(nodes):
            line = colorize_log_line(line, auto=auto)
            if line:
                print(line)
                sys.stdout.flush()


    def print_config_data(self, src_config=None, evaluate=False, impersonate=None):
        if src_config is None:
            src_config = self.config
        return ExtConfigMixin.print_config_data(self, src_config=src_config,
                                           evaluate=evaluate,
                                           impersonate=impersonate)

    def print_devs(self):
        if self.options.reverse:
            self.devtree.print_tree_bottom_up(devices=self.options.devices,
                                              verbose=self.options.verbose)
        else:
            self.devtree.print_tree(devices=self.options.devices,
                                    verbose=self.options.verbose)

    @formatter
    def print_config(self):
        """
        print_config node action entrypoint
        """
        if self.options.format is not None:
            return self.print_config_data(self.config)
        if not os.path.exists(rcEnv.paths.nodeconf):
            return
        from rcColor import print_color_config
        print_color_config(rcEnv.paths.nodeconf)

    @formatter
    def print_authconfig(self):
        """
        print_authconfig node action entrypoint
        """
        if self.options.format is not None:
            self.load_auth_config()
            return self.print_config_data(self.auth_config)
        if not os.path.exists(rcEnv.paths.authconf):
            return
        from rcColor import print_color_config
        print_color_config(rcEnv.paths.authconf)

    @formatter
    def ls(self):
        data = self.nodes_selector(self.options.node)
        if self.options.format is not None:
            return data
        for node in data:
            print(node)

    def nodes_selector(self, selector, data=None):
        if selector in ("*", None):
            return self.cluster_nodes
        if selector == "":
            return []
        if isinstance(selector, (list, tuple, set)):
            return selector
        if not re.search("\*?=,\+", selector) and re.search("\s", selector):
            # simple node list
            return selector.split()

        # compat with pre-selector nodes list
        selector = ",".join([node.lower() for node in selector.split()])

        if data is None:
            data = self.nodes_info
        if data is None:
            # daemon down, at least decide if the local node matches
            data = {rcEnv.nodename: {"labels": self.labels}}
        nodes = set([node for node in data])
        anded_selectors = selector.split("+")
        for _selector in anded_selectors:
            nodes = nodes & self._nodes_selector(_selector, data)
        return sorted(list(nodes))

    def _nodes_selector(self, selector, data):
        nodes = set()
        ored_selectors = selector.split(",")
        for _selector in ored_selectors:
            nodes = nodes | self.__nodes_selector(_selector, data)
        return nodes

    def __nodes_selector(self, selector, data):
        try:
            negate = selector[0] == "!"
            selector = selector.lstrip("!")
        except IndexError:
            negate = False
        if selector == "*":
            matching = set([node for node in data])
        elif selector.endswith(":"):
            label = selector.rstrip(":")
            matching = set([node for node, _data in data.items() \
                            if label in _data.get("labels", {})])
        elif "=" in selector:
            label, value = selector.split("=", 1)
            matching = set([node for node, _data in data.items() \
                            if _data.get("labels", {}).get(label) == value])
        else:
            matching = set([node for node in data if fnmatch.fnmatch(node, selector)])
        if negate:
            return set([node for node in data]) - matching
        else:
            return matching

    @lazy
    def agent_version(self):
        try:
            import version
        except ImportError:
            pass

        try:
            reload(version)
            return version.version
        except (NameError, AttributeError):
            pass

        try:
            import imp
            imp.reload(version)
            return version.version
        except (AttributeError, UnboundLocalError):
            pass

        try:
            import importlib
            importlib.reload(version)
            return version.version
        except (ImportError, AttributeError, UnboundLocalError):
            pass
        if which("git"):
            cmd = ["git", "--git-dir", os.path.join(rcEnv.paths.pathsvc, ".git"),
                   "describe", "--tags", "--abbrev=0"]
            out, err, ret = justcall(cmd)
            if ret != 0:
                return "dev"
            _version = out.strip()
            cmd = ["git", "--git-dir", os.path.join(rcEnv.paths.pathsvc, ".git"),
                   "describe", "--tags"]
            out, err, ret = justcall(cmd)
            if ret != 0:
                return "dev"
            _release = out.strip().split("-")[1]
            return "-".join((_version, _release+"dev"))

        return "dev"

    def frozen(self):
        """
        Return True if the node frozen flag is set.
        """
        return self.freezer.node_frozen()

    def freeze(self):
        """
        Set the node frozen flag.
        """
        self.freezer.node_freeze()

    def thaw(self):
        """
        Unset the node frozen flag.
        """
        self.freezer.node_thaw()

    def stonith(self):
        self._stonith(self.options.node)

    def _stonith(self, node):
        if node in (None, ""):
            raise ex.excError("--node is mandatory")
        if node == rcEnv.nodename:
            raise ex.excError("refuse to stonith ourself")
        if node not in self.cluster_nodes:
            raise ex.excError("refuse to stonith node %s not member of our cluster" % node)
        try:
            cmd = self._get("stonith#%s.cmd" % node)
        except ex.excError as exc:
            raise ex.excError("the stonith#%s.cmd keyword must be set in "
                              "node.conf" % node)
        import shlex
        cmd = shlex.split(cmd)
        self.log.info("stonith node %s", node)
        ret, out, err = self.vcall(cmd)
        if ret != 0:
            raise ex.excError()

    def prepare_async_cmd(self):
        cmd = sys.argv[1:]
        cmd = drop_option("--node", cmd, drop_value=True)
        cmd = drop_option("--cluster", cmd, drop_value=False)
        return cmd

    def async_action(self, action, timeout=None, wait=None):
        """
        Set the daemon global expected state if the action can be handled
        by the daemons.
        """
        if wait is None:
            wait = self.options.wait
        if timeout is None:
            timeout = self.options.time
        if timeout is not None:
            timeout = convert_duration(timeout)
        if self.options.node is not None and self.options.node != "" and \
           action in REMOTE_ACTIONS:
            cmd = self.prepare_async_cmd()
            sync = action not in ("reboot", "shutdown", "updatepkg", "updatecomp")
            ret = self.daemon_node_action(cmd, sync=sync)
            if ret == 0:
                raise ex.excAbortAction()
            else:
                raise ex.excError()
        if self.options.cluster and action in REMOTE_ACTIONS:
            cmd = self.prepare_async_cmd()
            sync = action not in ("reboot", "shutdown", "updatepkg", "updatecomp")
            ret = self.daemon_cluster_action(cmd, sync=sync)
            if ret == 0:
                raise ex.excAbortAction()
            else:
                raise ex.excError()
        if self.options.local:
            return
        if action not in ACTION_ASYNC:
            return
        self.set_node_monitor(global_expect=ACTION_ASYNC[action]["target"])
        self.log.info("%s action requested", action)
        if not wait:
            raise ex.excAbortAction()
        self.poll_async_action(ACTION_ASYNC[action]["target"], timeout=timeout)

    def poll_async_action(self, state, timeout=None):
        """
        Display an asynchronous action progress until its end or timeout
        """
        prev_global_expect_set = set()

        for _ in range(timeout):
            data = self._daemon_status()
            if data is None:
                raise ex.excError("the daemon is not running")
            global_expect_set = []
            for nodename in data["monitor"]["nodes"]:
                try:
                    _data = data["monitor"]["nodes"][nodename]
                except (KeyError, TypeError) as exc:
                    continue
                if _data["monitor"].get("global_expect") == state:
                    global_expect_set.append(nodename)
            if prev_global_expect_set != global_expect_set:
                for nodename in set(global_expect_set) - prev_global_expect_set:
                    self.log.info(" work starting on %s", nodename)
                for nodename in prev_global_expect_set - set(global_expect_set):
                    self.log.info(" work over on %s", nodename)
            if not global_expect_set:
                self.log.info("final status: frozen=%s",
                              data["monitor"]["frozen"])
                return
            prev_global_expect_set = set(global_expect_set)
            time.sleep(1)
        raise ex.excError("wait timeout exceeded")

    #
    # daemon actions
    #
    def daemon_collector_xmlrpc(self, *args, **kwargs):
        data = self.daemon_send(
            {
                "action": "collector_xmlrpc",
                "options": {
                    "args": args,
                    "kwargs": kwargs,
                },
            },
            nodename=self.options.node,
            silent=True,
        )
        if data["status"] != 0:
            # the daemon is not running or refused the connection,
            # tell the collector ourselves
            self.collector.call(*args, **kwargs)

    @lazy
    def nodes_info(self):
        try:
            return self._daemon_nodes_info(silent=True)["data"]
        except (KeyError, TypeError):
            return

    def _daemon_nodes_info(self, silent=False, refresh=False, node=None):
        data = self.daemon_send(
            {
                "action": "nodes_info",
            },
            nodename=node,
            silent=silent,
        )
        return data

    def _daemon_lock(self, name, timeout=None, silent=False, on_error=None):
        data = self.daemon_send(
            {
                "action": "lock",
                "options": {"name": name, "timeout": timeout},
            },
            silent=silent,
        )
        lock_id = data.get("data", {}).get("id")
        if not lock_id and on_error == "raise":
            raise ex.excError("cluster lock error")
        return lock_id

    def _daemon_unlock(self, name, lock_id, silent=False):
        data = self.daemon_send(
            {
                "action": "unlock",
                "options": {"name": name, "id": lock_id},
            },
            silent=silent,
        )

    def _daemon_status(self, silent=False, refresh=False, node=None):
        data = self.daemon_send(
            {
                "action": "daemon_status",
                "options": {
                    "refresh": refresh,
                },
            },
            nodename=node,
            silent=silent,
        )
        return data

    def cluster_stats(self, svcpaths=None):
        data = {}
        for node in self.cluster_nodes:
            try:
                data[node] = self._daemon_stats(svcpaths=svcpaths, node=node)["data"]
            except Exception:
                pass
        return data

    def daemon_lock_release(self):
        self._daemon_unlock(self.options.name, self.options.id)

    def daemon_stats(self, svcpaths=None, node=None):
        if node:
            daemon_node = node
        elif self.options.node:
            daemon_node = self.options.node
        else:
            daemon_node = rcEnv.nodename
        data = self._daemon_stats(svcpaths=svcpaths, node=daemon_node)
        if data is None or data.get("status", 0) != 0:
            return
        return self.print_data(data["data"], default_fmt="flat_json")

    def _daemon_stats(self, svcpaths=None, silent=False, node=None):
        data = self.daemon_send(
            {
                "action": "daemon_stats",
                "options": {
                    "svcpaths": svcpaths,
                }
            },
            nodename=node,
            silent=silent,
        )
        return data

    def daemon_status(self, svcpaths=None, node=None):
        if node:
            daemon_node = node
        elif self.options.node:
            daemon_node = self.options.node
        else:
            daemon_node = rcEnv.nodename
        data = self._daemon_status(node=daemon_node)
        if data is None or data.get("status", 0) != 0:
            return

        if self.options.format in ("json", "flat_json") or self.options.jsonpath_filter:
            self.print_data(data)
            return

        from fmt_cluster import format_cluster
        return format_cluster(svcpaths=svcpaths, node=self.cluster_nodes, data=data)

    def daemon_blacklist_clear(self):
        """
        Tell the daemon to clear the senders blacklist
        """
        data = self.daemon_send(
            {"action": "daemon_blacklist_clear"},
            nodename=self.options.node,
        )
        if data is None:
            return 1
        for error in data.get("errors", []):
             print(error, file=sys.stderr)
        return data.get("status")

    def dns_dump(self):
        """
        Dump the content of the cluster zone.
        """
        try:
            dns = self.dns
        except Exception:
            return
        request = {
            "method": "list",
            "parameters": {
                "zonename": self.cluster_name + "."
            }
        }
        for node in dns:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(rcEnv.paths.dnsuxsock)
                sock.send(bencode(json.dumps(request)+"\n"))
                response = ""
                while True:
                    buff = sock.recv(4096)
                    if not buff:
                        break
                    response += bdecode(buff)
                    if response[-1] == "\n":
                        break
            finally:
                sock.close()
            if not response:
                return
            try:
                data = json.loads(response)["result"]
            except ValueError:
                print("invalid response format", file=sys.stderr)
                raise ex.excError
            if self.options.format in ("json", "flat_json"):
                self.print_data(data)
                return
            widths = {
                "qname": 0,
                "qtype": 0,
                "ttl": 0,
                "content": 0,
            }
            for record in data:
                for key in ("qname", "qtype", "ttl", "content"):
                    length = len(str(record[key]))
                    if length > widths[key]:
                        widths[key] = length
            fmt = "{:%d}  IN   {:%d}  {:%d}  {:%d}" % (widths["qname"], widths["qtype"], widths["ttl"], widths["content"])
            for record in sorted(data, key=lambda x: x["qname"]):
                print(fmt.format(record["qname"], record["qtype"], record["ttl"], record["content"]))
            return

    def daemon_relay_status(self):
        """
        Show the daemon senders blacklist
        """
        secret = None
        cluster_name = None
        if self.options.node and self.options.node != rcEnv.nodename:
            cluster_name = "join"
            for section in self.config.sections():
                if not section.startswith("hb#"):
                    continue
                try:
                    relay = self.conf_get(section, "relay")
                except (ValueError, ex.OptNotFound):
                    continue
                if relay != self.options.node:
                    continue
                try:
                    secret = self.conf_get(section, "secret")
                    break
                except ex.OptNotFound:
                    continue

        data = self.daemon_send(
            {"action": "daemon_relay_status"},
            nodename=self.options.node,
            secret=secret,
            cluster_name=cluster_name,
        )
        if self.options.format in ("json", "flat_json") or self.options.jsonpath_filter:
            self.print_data(data)
            return

        if data is None:
            return

        from forest import Forest
        from rcColor import color

        tree = Forest()
        head = tree.add_node()
        head.add_column("cluster_id/node")
        head.add_column("cluster_name")
        head.add_column("last")
        head.add_column("elapsed")
        head.add_column("ipaddr")
        head.add_column("size")
        now = time.time()

        for nodename, _data in sorted(data.items(), key=lambda x: x[0]):
             try:
                 updated = _data.get("updated", 0)
                 size = _data.get("size", 0)
                 ipaddr = _data.get("ipaddr", "")
                 cluster_name = _data.get("cluster_name", "")
             except AttributeError:
                 continue
             node = head.add_node()
             node.add_column(nodename, color.BOLD)
             node.add_column(cluster_name)
             node.add_column("%s" % datetime.datetime.fromtimestamp(updated).strftime("%Y-%m-%d %H:%M:%S"))
             node.add_column("%s" % print_duration(now-updated))
             node.add_column("%s" % ipaddr)
             node.add_column("%s" % print_size(size, unit="B"))
        tree.print()

    def daemon_blacklist_status(self):
        """
        Show the daemon senders blacklist
        """
        data = self.daemon_send(
            {"action": "daemon_blacklist_status"},
            nodename=self.options.node,
        )
        print(json.dumps(data, indent=4, sort_keys=True))

    def _ping(self, node, timeout=5):
        """
        Fetch the daemon senders blacklist as a ping test, from either
        a peer or an arbitrator node, swiching between secrets as appropriate.
        """
        if node in self.cluster_nodes or node in (rcEnv.nodename, "127.0.0.1"):
            cluster_name = None
            secret = None
        elif node in self.cluster_drpnodes:
            try:
                secret = self.conf_get("cluster", "secret", impersonate=node)
            except ex.OptNotFound:
                raise ex.excError("unable to find the node %(node)s cluster secret. set cluster.secret@drpnodes or cluster.secret@%(node)s" % dict(node=node))
            try:
                cluster_name = self.conf_get("cluster", "name", impersonate=node)
            except ex.OptNotFound:
                raise ex.excError("unable to find the node %(node)s cluster name. set cluster.name@drpnodes or cluster.name@%(node)s" % dict(node=node))
        else:
            secret = None
            for section in self.config.sections():
                if not section.startswith("arbitrator#"):
                    continue
                try:
                    arbitrator = self.config.get(section, "name")
                except Exception:
                    continue
                if arbitrator != node:
                    continue
                try:
                    secret = self.config.get(section, "secret")
                    cluster_name = "join"
                    break
                except Exception:
                    self.log.warning("missing 'secret' in configuration section %s" % section)
                    continue
            if secret is None:
                raise ex.excError("unable to find a secret for node '%s': neither in cluster.nodes, cluster.drpnodes nor arbitrator#*.name" % node)
        data = self.daemon_send(
            {"action": "daemon_blacklist_status"},
            nodename=node,
            cluster_name=cluster_name,
            secret=secret,
            timeout=timeout,
        )
        if data is None or "status" not in data or data["status"] != 0:
            return 1
        return 0

    def ping(self):
        if self.options.cluster:
            ret = 0
            for node in self.sorted_cluster_nodes:
                if self.ping_node(node):
                    ret = 1
            return ret
        else:
            return self.ping_node(self.options.node)

    def ping_node(self, node):
        try:
            ret = self._ping(node)
        except ex.excError as exc:
            print(exc)
            ret = 2
        if ret == 0:
            print("%s is alive" % node)
        elif ret == 1:
            print("%s is not alive" % node)
        return ret

    def daemon_shutdown(self):
        """
        Tell the daemon to shutdown all local service instances then die.
        """
        data = self.daemon_send(
            {"action": "daemon_shutdown"},
            nodename=self.options.node,
        )
        if data is None:
            return 1
        for error in data.get("errors", []):
             print(error, file=sys.stderr)
        return data.get("status")

    def _daemon_stop(self):
        """
        Tell the daemon to die or stop a specified thread.
        """
        if not self._daemon_running():
            return
        options = {}
        if self.options.thr_id:
            options["thr_id"] = self.options.thr_id
        if os.environ.get("OPENSVC_AGENT_UPGRADE"):
            options["upgrade"] = True
        data = self.daemon_send(
            {"action": "daemon_stop", "options": options},
            nodename=self.options.node,
        )
        while True:
            if not self._daemon_running():
                break
            time.sleep(0.1)
        return data

    def daemon_stop(self):
        data = None
        if self.options.thr_id is None and self.daemon_handled_by_systemd():
            # 'systemctl restart <osvcunit>' when the daemon has been started
            # manually causes a direct 'nodemgr daemon start', which fails,
            # and systemd fallbacks to 'nodemgr daemon stop' and leaves the
            # daemon stopped.
            # Detect this situation and stop the daemon ourselves.
            if self.daemon_active_systemd():
                self.daemon_stop_systemd()
            else:
                if self._daemon_running():
                    data = self._daemon_stop()
        elif self._daemon_running():
            data = self._daemon_stop()
        if data is None:
            return
        if data.get("status") == 0:
            return
        raise ex.excError(json.dumps(data, indent=4, sort_keys=True))

    def daemon_start(self):
        if self.options.thr_id:
            return self.daemon_start_thread()
        return self.daemon_start_native()

    def daemon_start_native(self):
        """
        Can be overloaded by node<os>
        """
        if self.daemon_handled_by_systemd():
            return self.daemon_start_systemd()
        return os.system(sys.executable+" "+os.path.join(rcEnv.paths.pathlib, "osvcd.py"))

    def daemon_start_thread(self):
        options = {}
        options["thr_id"] = self.options.thr_id
        data = self.daemon_send(
            {"action": "daemon_start", "options": options},
            nodename=self.options.node,
        )
        if data.get("status") == 0:
            return
        raise ex.excError(json.dumps(data, indent=4, sort_keys=True))

    def daemon_running(self):
        if self._daemon_running():
            return
        else:
            raise ex.excError

    def _daemon_running(self):
        if self.options.thr_id:
            data = self._daemon_status()
            if self.options.thr_id not in data:
                return False
            return data[self.options.thr_id].get("state") == "running"
        from lock import lock, unlock
        lockfd = None
        try:
            lockfd = lock(lockfile=rcEnv.paths.daemon_lock, timeout=0, delay=0)
        except:
            return True
        finally:
            unlock(lockfd)
        return False

    def daemon_start_systemd(self):
        """
        Do daemon start through the systemd, so that the daemon is
        service status is correctly reported.
        """
        os.system("systemctl reset-failed opensvc-agent")
        if os.environ.get("OPENSVC_AGENT_UPGRADE"):
            os.system("systemctl set-environment OPENSVC_AGENT_UPGRADE=1")
        os.system("systemctl restart opensvc-agent")
        os.system("systemctl unset-environment OPENSVC_AGENT_UPGRADE")

    def daemon_stop_systemd(self):
        """
        Do daemon stop through the systemd, so that the daemon is not restarted
        by systemd, and the systemd service status is correctly reported.
        """
        if os.environ.get("OPENSVC_AGENT_UPGRADE"):
            os.system("systemctl set-environment OPENSVC_AGENT_UPGRADE=1")
        os.system("systemctl stop opensvc-agent")
        os.system("systemctl unset-environment OPENSVC_AGENT_UPGRADE")

    def daemon_restart_systemd(self):
        """
        Do daemon restart through the systemd, so that the daemon pid is updated
        in systemd, and the systemd service status is correctly reported.
        """
        os.system("systemctl restart opensvc-agent")

    def daemon_handled_by_systemd(self):
        """
        Return True if the system has systemd.
        """
        if which("systemctl") is None:
            return False
        if os.environ.get("LOGNAME") is None:
            # do as if we're not handled by systemd if we're already run by
            # systemd
            return False
        return True

    def daemon_active_systemd(self):
        cmd = ["systemctl", "show", "-p" "ActiveState", "opensvc-agent.service"]
        out, err, ret = justcall(cmd)
        if ret != 0:
            return False
        if out.split("=")[-1].strip() == "active":
            return True
        return False

    def daemon_restart(self):
        if self.daemon_handled_by_systemd():
            # 'systemctl restart <osvcunit>' when the daemon has been started
            # manually causes a direct 'nodemgr daemon start', which fails,
            # and systemd fallbacks to 'nodemgr daemon stop' and leaves the
            # daemon stopped.
            # Detect this situation and stop the daemon ourselves.
            if not self.daemon_active_systemd():
                if self._daemon_running():
                    self._daemon_stop()
            return self.daemon_restart_systemd()
        if self._daemon_running():
            self._daemon_stop()
        self.daemon_start()

    @lazy
    def sorted_cluster_nodes(self):
        return sorted(self.cluster_nodes)

    def daemon_leave(self):
        cluster_nodes = self.sorted_cluster_nodes
        if len(self.sorted_cluster_nodes) == 0:
            self.log.info("local node is not member of a cluster")
            return
        if rcEnv.nodename in cluster_nodes:
            cluster_nodes.remove(rcEnv.nodename)

        # freeze and remember the initial frozen state
        if not self.frozen():
            self.freeze()
            self.log.info("freeze local node")
        else:
            self.log.info("local node is already frozen")
        self.log.warning = "DO NOT UNFREEZE before verifying split services won't double-start"

        # leave other nodes
        options = {"thr_id": "tx", "wait": True}
        data = self.daemon_send(
            {"action": "daemon_stop", "options": options},
            nodename=rcEnv.nodename,
        )

        errors = 0
        for nodename in cluster_nodes:
            data = self.daemon_send(
                {"action": "leave"},
                nodename=nodename,
            )
            if data is None:
                self.log.error("leave node %s failed", nodename)
                errors += 1
            else:
                self.log.info("leave node %s", nodename)

        # remove obsolete hb configurations
        for section in self.config.sections():
            if section.startswith("hb#") or \
               section.startswith("arbitrator#"):
                self.log.info("remove configuration %s", section)
                self.config.remove_section(section)
            self.config.remove_section("cluster")

        self.write_config()
        self.unset_lazy("cluster_nodes")

    def daemon_join(self):
        if self.options.secret is None:
            raise ex.excError("--secret must be set")
        if self.options.node is None:
            raise ex.excError("--node must be set")
        self._daemon_join(self.options.node, self.options.secret)

    def daemon_rejoin(self):
        if self.options.node is None:
            raise ex.excError("--node must be set")
        self._daemon_join(self.options.node, self.cluster_key)

    def _daemon_join(self, joined, secret):
        # freeze and remember the initial frozen state
        initially_frozen = self.frozen()
        if not initially_frozen:
            self.freeze()
            self.log.info("freeze local node")
        else:
            self.log.info("local node is already frozen")

        if not self.config.has_section("cluster"):
            self.config.add_section("cluster")
        data = self.daemon_send(
            {"action": "join"},
            nodename=joined,
            cluster_name="join",
            secret=secret,
        )
        if data is None:
            raise ex.excError("join node %s failed" % joined)
        data = data.get("data")
        if data is None:
            raise ex.excError("join failed: no data in response")
        cluster_name = data.get("cluster", {}).get("name")
        if cluster_name is None:
            raise ex.excError("join failed: no cluster.name in response")
        cluster_id = data.get("cluster", {}).get("id")
        if cluster_id is None:
            raise ex.excError("join failed: no cluster.id in response")
        cluster_nodes = data.get("cluster", {}).get("nodes")
        if cluster_nodes is None:
            raise ex.excError("join failed: no cluster.nodes in response")
        if not isinstance(cluster_nodes, list):
            raise ex.excError("join failed: cluster.nodes value is not a list")
        cluster_drpnodes = data.get("cluster", {}).get("drpnodes")
        dns = data.get("cluster", {}).get("dns")
        quorum = data.get("cluster", {}).get("quorum", False)

        peer_env = data.get("node", {}).get("env")
        if peer_env and peer_env != rcEnv.node_env:
            self.log.info("update node.env %s => %s", rcEnv.node_env, peer_env)
            if not self.config.has_section("node"):
                self.config.add_section("node")
            self.config.set("node", "env", peer_env)

        self.config.set("cluster", "name", cluster_name)
        self.config.set("cluster", "id", cluster_id)
        self.config.set("cluster", "nodes", " ".join(cluster_nodes))
        self.config.set("cluster", "secret", secret)
        if isinstance(dns, list) and len(dns) > 0:
            self.config.set("cluster", "dns", " ".join(dns))
        if isinstance(cluster_drpnodes, list) and len(cluster_drpnodes) > 0:
            self.config.set("cluster", "drpnodes", " ".join(cluster_drpnodes))
        if quorum:
            self.config.set("cluster", "quorum", "true")
        elif self.config.has_option("cluster", "quorum"):
            self.config.remove_option("cluster", "quorum")

        for section, _data in data.items():
            if section.startswith("hb#"):
                if self.config.has_section(section):
                    self.log.info("update heartbeat %s", section)
                    self.config.remove_section(section)
                else:
                    self.log.info("add heartbeat %s", section)
                self.config.add_section(section)
                for option, value in _data.items():
                    self.config.set(section, option, value)
            elif section.startswith("stonith#"):
                if self.config.has_section(section):
                    self.log.info("update stonith %s", section)
                    self.config.remove_section(section)
                else:
                    self.log.info("add stonith %s", section)
                self.config.add_section(section)
                for option, value in _data.items():
                    self.config.set(section, option, value)
            elif section.startswith("arbitrator#"):
                if self.config.has_section(section):
                    self.log.info("update arbitrator %s", section)
                    self.config.remove_section(section)
                else:
                    self.log.info("add arbitrator %s", section)
                self.config.add_section(section)
                for option, value in _data.items():
                    self.config.set(section, option, value)
            elif section.startswith("pool#"):
                if self.config.has_section(section):
                    self.log.info("update pool %s", section)
                    self.config.remove_section(section)
                else:
                    self.log.info("add pool %s", section)
                self.config.add_section(section)
                for option, value in _data.items():
                    self.config.set(section, option, value)
            elif section.startswith("network#"):
                if self.config.has_section(section):
                    self.log.info("update network %s", section)
                    self.config.remove_section(section)
                else:
                    self.log.info("add network %s", section)
                self.config.add_section(section)
                for option, value in _data.items():
                    self.config.set(section, option, value)

        # remove obsolete hb configurations
        for section in self.config.sections():
            if section.startswith("hb#") and section not in data:
                self.log.info("remove heartbeat %s", section)
                self.config.remove_section(section)

        # remove obsolete stonith configurations
        for section in self.config.sections():
            if section.startswith("stonith#") and section not in data:
                self.log.info("remove stonith %s", section)
                self.config.remove_section(section)

        # remove obsolete arbitrator configurations
        for section in self.config.sections():
            if section.startswith("arbitrator#") and section not in data:
                self.log.info("remove arbitrator %s", section)
                self.config.remove_section(section)

        # remove obsolete pool configurations
        for section in self.config.sections():
            if section.startswith("pool#") and section not in data:
                self.log.info("remove pool %s", section)
                self.config.remove_section(section)

        # remove obsolete network configurations
        for section in self.config.sections():
            if section.startswith("network#") and section not in data:
                self.log.info("remove network %s", section)
                self.config.remove_section(section)

        self.write_config()
        self.log.info("join node %s", joined)

        # join other nodes
        errors = 0
        for nodename in cluster_nodes:
            if nodename in (rcEnv.nodename, joined):
                continue
            data = self.daemon_send(
                {"action": "join"},
                nodename=nodename,
                cluster_name="join",
                secret=secret,
            )
            if data is None:
                self.log.error("join node %s failed", nodename)
                errors += 1
            else:
                self.log.info("join node %s", nodename)

        # leave node frozen if initially frozen or we failed joining all nodes
        if initially_frozen:
            self.log.warning("local node is left frozen as it was already before join")
        elif errors > 0:
            self.log.warning("local node is left frozen due to join errors")
        else:
            self.thaw()
            self.log.info("thaw local node")

    def set_node_monitor(self, status=None, local_expect=None, global_expect=None):
        options = {
            "status": status,
            "local_expect": local_expect,
            "global_expect": global_expect,
        }
        try:
            data = self.daemon_send(
                {"action": "set_node_monitor", "options": options},
                nodename=self.options.node,
                silent=True,
            )
            if data is None:
                raise ex.excError("the daemon is not running")
            if data and data["status"] != 0:
                raise ex.excError("set monitor status failed")
        except Exception as exc:
            raise ex.excError("set monitor status failed: %s" % str(exc))

    def daemon_cluster_action(self, cmd, sync=True):
        ret = 0
        for node in self.sorted_cluster_nodes:
            if self.daemon_node_action(cmd, nodename=node, sync=sync):
                ret = 1
        return ret

    def daemon_node_action(self, cmd, nodename=None, sync=True):
        """
        Execute a node action on a peer node.
        If sync is set, wait for the action result.
        """
        if nodename is None:
            nodename = self.options.node
        options = {
            "cmd": cmd,
            "sync": sync,
        }
        self.log.info("request node action '%s' on node %s", " ".join(cmd), nodename)
        try:
            data = self.daemon_send(
                {"action": "node_action", "options": options},
                nodename=nodename,
                silent=True,
            )
        except Exception as exc:
            self.log.error("node action on node %s failed: %s",
                           nodename, exc)
            return 1
        if data is None or data["status"] != 0:
            self.log.error("node action on node %s failed",
                           nodename)
            return 1
        if "data" not in data:
            return 0
        data = data["data"]
        if data.get("out") and len(data["out"]) > 0:
            for line in data["out"].splitlines():
               print(line)
        if data.get("err") and len(data["err"]) > 0:
            for line in data["err"].splitlines():
               print(line, file=sys.stderr)
        return data["ret"]

    def daemon_backlogs(self, nodename):
        options = {
            "debug": self.options.debug,
            "backlog": self.options.backlog,
        }
        for lines in self.daemon_get_stream(
            {"action": "node_logs", "options": options},
            nodename=nodename,
        ):
            if lines is None:
                break
            for line in lines:
                yield line

    def daemon_events(self, nodename=None):
        options = {}
        while True:
            for msg in self.daemon_get_streams(
                {"action": "events", "options": options},
                nodenames=[nodename],
            ):
                if msg is None:
                    break
                yield msg

            # retry until daemon restart
            time.sleep(1)

            # the node.conf might have changed (join, set, ...)
            self.unset_lazy("cluster_name")
            self.unset_lazy("cluster_key")

    def daemon_logs(self, nodes=None):
        options = {
            "debug": self.options.debug,
            "backlog": 0,
        }
        for lines in self.daemon_get_streams(
            {"action": "node_logs", "options": options},
            nodenames=nodes,
        ):
            if lines is None:
                break
            for line in lines:
                yield line

    def wake_monitor(self):
        options = {}
        try:
            data = self.daemon_send(
                {"action": "wake_monitor", "options": options},
                nodename=self.options.node,
                silent=True,
            )
            if data and data["status"] != 0:
                self.log.warning("wake monitor failed")
        except Exception as exc:
            self.log.warning("wake monitor failed: %s", str(exc))


    ##########################################################################
    #
    # Pool
    #
    ##########################################################################
    @formatter
    def pool_ls(self):
        data = self.pool_ls_data()
        if self.options.format in ("json", "flat_json"):
            return data
        print("\n".join([name for name in data]))

    def pool_ls_data(self):
        data = set(["default"])
        for section in self.config.sections():
            if section.startswith("pool#"):
                data.add(section.split("#")[-1])
        return sorted(list(data))

    @formatter
    def pool_status(self):
        data = self.pool_status_data()
        if self.options.format in ("json", "flat_json"):
            return data
        from forest import Forest
        from rcColor import color
        tree = Forest()
        node = tree.add_node()
        node.add_column("name", color.BOLD)
        node.add_column("type", color.BOLD)
        node.add_column("caps", color.BOLD)
        node.add_column("head", color.BOLD)
        node.add_column("vols", color.BOLD)
        node.add_column("size", color.BOLD)
        node.add_column("used", color.BOLD)
        node.add_column("free", color.BOLD)
        for name, _data in data.items():
            leaf = node.add_node()
            leaf.add_column(name, color.BROWN)
            if _data is None:
                continue
            leaf.add_column(_data["type"])
            leaf.add_column(",".join(_data["capabilities"]))
            leaf.add_column(_data.get("head",""))
            leaf.add_column(len(_data["volumes"]))
            for key in ("size", "used", "free"):
                if _data.get(key, -1) < 0:
                    val = "-"
                else:
                    val = print_size(_data[key], unit="k", compact=True)
                leaf.add_column(val)
        print(tree)

    def pools_volumes(self):
        try:
            data = self._daemon_status(silent=True)["monitor"]["nodes"]
        except Exception as exc:
            return {}
        pools = {}
        for nodename, ndata in data.items():
            if not isinstance(ndata, dict):
                continue
            for svcpath, sdata in ndata.get("services", {}).get("status", {}).items():
                poolname = sdata.get("pool")
                try:
                    pools[poolname].add(svcpath)
                except Exception:
                    pools[poolname] = set([svcpath])
        return pools

    def pool_status_data(self):
        data = {}
        volumes = self.pools_volumes()
        for name in self.pool_ls_data():
            pool = self.get_pool(name)
            data[name] = pool.status()
            if name in volumes:
                data[name]["volumes"] = sorted(list(volumes[name]))
            else:
                data[name]["volumes"] = []
        return data

    def find_pool(self, poolname=None, pooltype=None, access=None, size=None, fmt=None, shared=False):
        candidates = []
        for pool in self.pool_status_data().values():
            if shared is True and "shared" not in pool["capabilities"]:
                self.log.debug("discard pool %s: not shared capable",
                               pool["name"])
                continue
            if fmt is False and "blk" not in pool["capabilities"]:
                self.log.debug("discard pool %s: not blk capable",
                               pool["name"])
                continue
            if access and access not in pool["capabilities"]:
                self.log.debug("discard pool %s: not %s capable (%s)",
                               pool["name"], access, ','.join(pool["capabilities"]))
                continue
            if pooltype and pool["type"] != pooltype:
                self.log.debug("discard pool %s: not typed %s",
                               pool["name"], pooltype)
                continue
            if poolname and pool["name"] != poolname:
                self.log.debug("discard pool %s: not named %s",
                               pool["name"], poolname)
                continue
            if size and "free" in pool and pool["free"] < size//1024+1:
                self.log.debug("discard pool %s: not enough free space %d/%d",
                               pool["name"], pool["free"], size)
                continue
            candidates.append(pool)
        if not candidates:
            return
        candidates = sorted(candidates, key=lambda x: x.get("free", 0))
        return self.get_pool(candidates[-1]["name"])

    def get_pool(self, poolname):
        try:
            section = "pool#"+poolname
        except TypeError:
            raise ex.excError("invalid pool name: %s" % poolname)
        if poolname != "default" and not self.config.has_section(section):
            raise ex.excError("pool not found: %s" % poolname)
        try:
            ptype = self.conf_get(section, "type")
        except ex.OptNotFound as exc:
            ptype = exc.default
        from rcUtilities import mimport
        mod = mimport("pool", ptype)
        return mod.Pool(node=self, name=poolname)

    def pool_create_volume(self):
        nodes = self.nodes_selector(self.options.node)
        self._pool_create_volume(poolname=self.options.pool,
                                 name=self.options.name,
                                 namespace=self.options.namespace,
                                 size=self.options.size,
                                 access=self.options.access,
                                 nodes=nodes,
                                 shared=self.options.shared)

    def _pool_create_volume(self, poolname=None, **kwargs):
        try:
            pool = self.get_pool(poolname)
        except ImportError as exc:
            raise ex.excError(str(exc))
        pool.create_volume(**kwargs)

    ##########################################################################
    #
    # Network
    #
    ##########################################################################

    @lazy
    def cni_config(self):
        try:
            return self.conf_get("cni", "config").rstrip("/")
        except ex.OptNotFound as exc:
            return exc.default

    def network_data(self, id):
        if id:
            return self.networks_data()[id]
        else:
            return self.networks_data()

    def networks_data(self):
        import glob
        nets = {}
        for cf in glob.glob(self.cni_config+"/*.conf"):
            try:
                with open(cf, "r") as ofile:
                    data = json.load(ofile)
            except ValueError:
                data = {}
            if data.get("type") == "portmap":
                continue
            name = os.path.basename(cf)
            name = re.sub(".conf$", "", name)
            nets[name] = {
                "cni": {
                    "cf": cf,
                    "mtime": os.path.getmtime(cf),
                    "data": data,
                },
                "config": {
                    "type": "undef",
                    "network": "undef",
                },
            }
        sections = list(self.conf_sections("network"))
        if "network#default" not in sections:
            sections.append("network#default")
        for section in sections:
            _, name = section.split("#", 1)
            config = {}
            config["type"] = self.oget(section, "type")
            for key in self.section_kwargs(section, config["type"]):
                config[key] = self.oget(section, key)
            if config:
                if name not in nets:
                    nets[name] = {}
                nets[name]["config"] = config
                nets[name]["routes"] = self.routes(name)
        return nets

    @formatter
    def network_ls(self):
        nets = self.networks_data()
        if self.options.format in ("json", "flat_json"):
            return nets
        print("\n".join([net for net in nets]))

    @formatter
    def network_show(self):
        data = {}
        for name, netdata in self.networks_data().items():
            if self.options.name and name != self.options.name:
                continue
            data[name] = netdata
        if self.options.format in ("json", "flat_json"):
            return data
        if not data:
            return
        from forest import Forest
        from rcColor import color
        tree = Forest()
        tree.load(data, title="networks")
        print(tree)

    def node_subnet(self, name, nodename=None):
        if nodename is None:
            nodename = rcEnv.nodename
        idx = self.cluster_nodes.index(nodename)
        network = self.oget("network#" + name, "network") 
        ips_per_node = self.oget("network#" + name, "ips_per_node") 
        ips_per_node = 1 << (ips_per_node - 1).bit_length()
        net = ip_network(six.text_type(network))
        first = net[0] + (idx * ips_per_node)
        last = first + ips_per_node - 1
        subnet = next(summarize_address_range(first, last))
        return subnet

    def routes(self, name):
        routes = []
        ntype = self.oget("network#"+name, "type")
        if ntype != "routed_bridge":
            return routes
        for nodename in self.cluster_nodes:
            if nodename == rcEnv.nodename:
                continue
            try:
                gw = socket.getaddrinfo(nodename, None)[0][4][0]
            except socket.gaierror:
                self.log.warning("node %s is not resolvable", nodename)
                continue
            routes.append({
                "dst": str(self.node_subnet(name, nodename)),
                "gw": gw,
            })
        return routes

    def network_overlaps(self, name, nets=None):
        def get_val(key, net):
            try:
                return net["config"][key]
            except KeyError:
                try:
                    return net["cni"]["data"][key]
                except KeyError:
                    return
        if nets is None:
            nets = self.networks_data()
        net = nets.get(name)
        if not net:
            return
        try:
            network = ip_network(six.text_type(get_val("network", net)))
        except Exception:
            return
        for other_name, other in nets.items():
            if name == other_name:
                continue
            try:
                other_network = ip_network(six.text_type(get_val("network", other)))
            except Exception:
                continue
            if other_network and network.overlaps(other_network):
                raise ex.excError("network %s %s overlaps with %s %s" % \
                                  (name, network, other_name, other_network))

    def network_setup(self):
        sections = list(self.conf_sections("network"))
        if "network#default" not in sections:
            sections.append("network#default")
        for section in sections:
            _, name = section.split("#", 1)
            try:
                self.network_overlaps(name)
            except ex.excError as exc:
                self.log.warning("skip setup: %s", exc)
                continue
            self.network_create_config(name)
            self.network_create_routes(name)
            self.network_create_bridge(name)

    def network_create_bridge(self, name):
        ntype = self.oget("network#"+name, "type")
        if ntype != "routed_bridge":
            return
        net = self.node_subnet(name)
        ip = str(net[1])+"/"+str(net.prefixlen)
        self.network_bridge_add("obr_"+name, ip)

    def network_bridge_add(self, *args, **kwargs):
        """
        OS specific
        """
        pass

    def network_create_routes(self, name):
        routes = self.routes(name)
        for route in routes:
            self.network_route_add(**route)

    def network_route_add(self, *args, **kwargs):
        """
        OS specific
        """
        pass
 
    def network_create_config(self, name="default"):
        ntype = self.oget("network#"+name, "type")
        fn = "network_create_%s_config" % ntype
        if hasattr(self, fn):
            getattr(self, fn)(name)

    def network_create_weave_config(self, name="default"):
        cf = os.path.join(self.cni_config, name+".conf")
        if os.path.exists(cf):
            return
        self.log.info("create %s", cf)
        network = self.oget("network#"+name, "network")
        conf = {
            "cniVersion": "0.2.0",
            "name": name,
            "type": "weave-net",
            "ipam": {
                "subnet": network,
            },
        }
        makedirs(self.cni_config)
        with open(cf, "w") as ofile:
            json.dump(conf, ofile, indent=4)

    def network_create_routed_bridge_config(self, name="default"):
        cf = os.path.join(self.cni_config, name+".conf")
        if os.path.exists(cf):
            return
        self.log.info("create %s", cf)
        conf = {
            "cniVersion": "0.2.0",
            "name": name,
            "type": "bridge",
            "bridge": "obr_"+name,
            "isGateway": True,
            "ipMasq": True,
            "ipam": {
                "type": "host-local",
                "routes": [
                    { "dst": "0.0.0.0/0" }
                ]
            }
        }
        makedirs(self.cni_config)
        conf["ipam"]["subnet"] = str(self.node_subnet(name))
        with open(cf, "w") as ofile:
            json.dump(conf, ofile, indent=4)

    def network_create_bridge_config(self, name="default"):
        cf = os.path.join(self.cni_config, name+".conf")
        if os.path.exists(cf):
            return
        self.log.info("create %s", cf)
        conf = {
            "cniVersion": "0.2.0",
            "name": name,
            "type": "bridge",
            "bridge": "obr_"+name,
            "isGateway": True,
            "ipMasq": True,
            "ipam": {
                "type": "host-local",
                "routes": [
                    { "dst": "0.0.0.0/0" }
                ]
            }
        }
        makedirs(self.cni_config)
        conf["ipam"]["subnet"] = self.oget("network#"+name, "network")
        with open(cf, "w") as ofile:
            json.dump(conf, ofile, indent=4)

    @formatter
    def network_status(self):
        data = self.network_status_data(self.options.name)
        if self.options.format in ("json", "flat_json"):
            return data
        from forest import Forest
        from rcColor import color
        tree = Forest()
        head = tree.add_node()
        head.add_column("name", color.BOLD)
        head.add_column("type", color.BOLD)
        head.add_column("network", color.BOLD)
        head.add_column("size", color.BOLD)
        head.add_column("used", color.BOLD)
        head.add_column("free", color.BOLD)
        head.add_column("pct", color.BOLD)
        for name in sorted(data):
            ndata = data[name]
            net_node = head.add_node()
            net_node.add_column(name, color.BROWN)
            net_node.add_column(data[name]["type"])
            net_node.add_column(data[name]["network"])
            net_node.add_column("%d" % data[name]["size"])
            net_node.add_column("%d" % data[name]["used"])
            net_node.add_column("%d" % data[name]["free"])
            net_node.add_column("%.2f%%" % data[name]["pct"])
            if not self.options.verbose:
                continue
            ips_node = net_node.add_node()
            ips_node.add_column("ip", color.BOLD)
            ips_node.add_column("node", color.BOLD)
            ips_node.add_column("service", color.BOLD)
            ips_node.add_column("resource", color.BOLD)
            for ip in sorted(ndata.get("ips", []), key=lambda x: (x["ip"], x["node"], x["svcpath"], x["rid"])):
                ip_node = ips_node.add_node()
                ip_node.add_column(ip["ip"])
                ip_node.add_column(ip["node"])
                ip_node.add_column(ip["svcpath"])
                ip_node.add_column(ip["rid"])
        print(tree)

    def network_ip_data(self):
        data = []
        cdata = self._daemon_status(silent=True)["monitor"]["nodes"]
        for nodename, node in cdata.items():
            for svcpath, sdata in node.get("services", {}).get("status", {}).items():
                for rid, rdata in sdata.get("resources", {}).items():
                    ip = rdata.get("info", {}).get("ipaddr")
                    if not ip:
                        continue
                    data.append({
                        "ip": ip,
                        "node": nodename,
                        "svcpath": svcpath,
                        "rid": rid,
                    })
        return data

    def network_status_data(self, name=None):
        data = {}
        nets = self.networks_data()
        ipdata = self.network_ip_data()
        for _name, ndata in nets.items():
            if name and name != _name:
                continue
            network = ip_network(six.text_type(self.oget("network#"+_name, "network")))
            _data = {
                "type": ndata["config"]["type"],
                "network": ndata["config"]["network"],
                "size": network.num_addresses,
                "ips": [],
            }
            for idata in ipdata:
                ip = ip_address(idata["ip"])
                if ip not in network:
                    continue
                _data["ips"].append(idata)
            _data["used"] = len(_data["ips"])
            _data["free"] = _data["size"] - _data["used"]
            _data["pct"] = 100 * _data["used"] / _data["size"]
            data[_name] = _data
        return data

    ##########################################################################
    #
    # Stats
    #
    ##########################################################################
    def score(self, data):
        """
        Higher scoring nodes get best placement ranking.
        """
        score = 100 / max(data.get("load_15m", 1), 1)
        score += 100 + data.get("mem_avail", 0)
        score += 2 * (100 + data.get("swap_avail", 0))
        return int(score // 7)

    def stats_meminfo(self):
        """
        OS-specific implementations
        """
        return {}

    def stats(self, refresh=False):
        now = time.time()
        if not refresh and self.stats_data and \
           self.stats_updated > now - STATS_INTERVAL:
            return self.stats_data
        data = {}
        self.stats_updated = now
        try:
            data["load_15m"] = round(os.getloadavg()[2], 1)
        except:
            # None < 0 == True
            pass
        try:
            meminfo = self.stats_meminfo()
        except OSError as exc:
            self.log.error("failed to get mem/swap info: %s", exc)
            meminfo = None
        if isinstance(meminfo, dict):
            data.update(meminfo)
        data["score"] = self.score(data)
        self.stats_data = data
        return data

    def get_tid(self):
        return

    def cpu_time(self, stat_path='/proc/stat'):
        return 0.0

    def pid_cpu_time(self, pid):
        return 0.0

    def tid_cpu_time(self, tid):
        return 0.0

    def pid_mem_total(self, pid):
        return 0.0

    def tid_mem_total(self, tid):
        return 0.0

    ##########################################################################

    def unset_lazy(self, prop):
        """
        Expose the unset_lazy(self, ...) utility function as a method,
        so Node() users don't have to import it from rcUtilities.
        """
        unset_lazy(self, prop)

    @lazy
    def hooks(self):
        """
        A hash of hook command sets, indexed by event.
        """
        data = {}
        for section in self.conf_sections("hook"):
            try:
                command = tuple(self.conf_get(section, "command"))
            except Exception:
                continue
            events = self.conf_get(section, "events")
            for event in events:
                if event not in data:
                    data[event] = set()
                data[event].add(command)
        return data

    def write_boot_id(self):
        with open(self.paths.last_boot_id, "w") as ofile:
            ofile.write(self.asset.get_boot_id())

    def last_boot_id(self):
        try:
            with open(self.paths.last_boot_id, "r") as ofile:
                return ofile.read()
        except Exception:
            return

    @lazy
    def targets(self):
        return self.asset.get_targets()

    def unset_all_lazy(self):
        unset_all_lazy(self)

    def delete(self):
        self.delete_sections(self.options.kw)
