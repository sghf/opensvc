from __future__ import print_function

import os

import rcExceptions as ex
from rcUtilities import lazy, fmt_svcpath
from converters import convert_size
from svc import Svc

class Pool(object):
    type = None

    def __init__(self, node=None, name=None):
        self.node = node
        self.name = name.strip(os.sep)
        if node:
            self.log = self.node.log

    def conf_get(self, kw, **kwargs):
        return self.node.conf_get(self.section, kw, **kwargs)

    def oget(self, kw, **kwargs):
        return self.node.oget(self.section, kw, **kwargs)

    @lazy
    def array(self):
        """
        Implemented by child classes
        """
        return

    @lazy
    def section(self):
        return "pool#"+self.name

    @lazy
    def fs_type(self):
        try:
            return self.conf_get("fs_type")
        except ex.OptNotFound as exc:
            return exc.default

    @lazy
    def mkfs_opt(self):
        try:
            return self.conf_get("mkfs_opt")
        except ex.OptNotFound as exc:
            return exc.default

    @lazy
    def mkblk_opt(self):
        try:
            return self.conf_get("mkblk_opt")
        except ex.OptNotFound as exc:
            return exc.default

    @lazy
    def mnt_opt(self):
        try:
            return self.conf_get("mnt_opt")
        except ex.OptNotFound as exc:
            return exc.default

    def mount_point(self, name):
        return os.path.join(os.sep, "srv", name)

    def default_disk_name(self, volume):
        return "%s.%s.svc.%s" % (
            volume.svcname,
            volume.namespace if volume.namespace else "root",
            self.node.cluster_name,
        )

    def configure_volume(self, volume, size=None, fmt=True, access="rwo", shared=False, nodes=None):
        name = self.default_disk_name(volume)
        data = self.translate(name=name, size=size, fmt=fmt, shared=shared)
        defaults = {
            "rtype": "DEFAULT",
            "kind": "vol",
            "pool": self.name,
            "access": access,
        }
        if access in ("rox", "rwx"):
            defaults["topology"] = "flex"
            defaults["flex_min_nodes"] = 0
        if nodes:
            defaults["nodes"] = nodes
        data.append(defaults)
        volume._update(data)
        self.node.install_service_files(volume.svcname, namespace=volume.namespace)

    def status(self):
        pass

    def translate(self, name=None, size=None, fmt=True, shared=False):
        return []

    def create_disk(self, name, size, nodes=None):
        return {}

    def delete_disk(self, name=None, disk_id=None):
        return {}

    def delete_volume(self, name, namespace=None):
        volume = Svc(svcname=name, namespace=namespace, node=self.node)
        if not volume.exists():
            self.log("volume does not exist")
        self.log.info("delete volume %s", volume.svcpath)
        volume.action("delete", options={"wait": True, "unprovision": True, "time": "5m"})
        
    def create_volume(self, name, namespace=None, size=None, access="rwo", fmt=False, nodes=None, shared=False):
        volume = Svc(svcname=name, namespace=namespace, node=self.node)
        if volume.exists():
            self.log.info("volume %s already exists", name)
            return volume
        if nodes is None:
            nodes = ""
        self.log.info("create volume %s (pool name: %s, pool type: %s, "
                           "access: %s, size: %s, format: %s, nodes: %s, shared: %s)",
                           volume.svcpath, self.name, self.type, access, size,
                           fmt, nodes, shared)
        self.configure_volume(volume,
                              fmt=fmt,
                              size=convert_size(size),
                              access=access,
                              nodes=nodes,
                              shared=shared)
        volume.action("provision", options={"wait": True, "time": "5m"})

    def get_targets(self):
        return []

    def _get_mappings(self, nodes, transport="fc"):
        data = []
        tgts = self.get_targets()
        for nodename, ndata in self.node.nodes_info.items():
            if nodes and nodename not in nodes:
                continue
            for mapping in ndata.get("targets", []):
                if transport == "iscsi" and not mapping["hba_id"].startswith("iqn"):
                    continue
                if mapping["tgt_id"] not in tgts:
                    continue
                data.append(":".join((mapping["hba_id"], mapping["tgt_id"])))
        self.log.info("mappings for nodes %s: %s", ",".join(sorted(list(nodes))), ",".join(data))
        return data

    def add_sync_internal(self, data):
        """
        Disable sync#i0 if the volume has only disk.disk and fs.directory resources.
        """
        if len([res for res in data if res["type"] not in ("disk.disk", "disk.scsireserv", "fs.directory")]) > 0:
            return []
        return [{"rid": "sync#i0", "disable": True}]

    def add_fs(self, name, shared=False):
        data = []
        if self.fs_type == "zfs":
            disk = {
                "rtype": "disk",
                "type": "zpool",
                "name": name,
                "vdev": "{disk#1.exposed_devs[0]}",
                "shared": shared,
            }
            fs = {
                "rtype": "fs",
                "type": self.fs_type,
                "dev": "%s/root" % name,
                "mnt": self.mount_point(name),
                "shared": shared,
            }
            if self.mkfs_opt:
                fs["mkfs_opt"] = " ".join(self.mkfs_opt)
            if self.mnt_opt:
                fs["mnt_opt"] = self.mnt_opt
            data += [disk, fs]
        else:
            fs = {
                "rtype": "fs",
                "type": self.fs_type,
                "dev": "{disk#1.exposed_devs[0]}",
                "mnt": self.mount_point(name),
                "shared": shared,
            }
            if self.mkfs_opt:
                fs["mkfs_opt"] = " ".join(self.mkfs_opt)
            if self.mnt_opt:
                fs["mnt_opt"] = self.mnt_opt
            data += [fs]
        return data

