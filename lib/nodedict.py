import sys
from rcGlobalEnv import rcEnv
from keywords import KeywordStore

# deprecated => supported
DEPRECATED_KEYWORDS = {
    "node.host_mode": "env",
    "node.environment": "asset_env",
    "node.environnement": "asset_env",
}

# supported => deprecated
REVERSE_DEPRECATED_KEYWORDS = {
    "node.asset_env": ["environnement", "environment"],
    "node.env": ["host_mode"],
}

DEPRECATED_SECTIONS = {
}

BASE_SECTIONS = [
    "node",
    "cluster",
    "compliance",
    "stats",
    "checks",
    "packages",
    "patches",
    "asset",
    "nsr",
    "dcs",
    "hds",
    "necism",
    "eva",
    "ibmsvc",
    "vioserver",
    "brocade",
    "disks",
    "sym",
    "rotate_root_pw",
    "listener",
    "syslog",
    "stats_collection",
    "reboot",
    "cluster",
]

KEYWORDS = [
    {
        "section": "node",
        "keyword": "uuid",
        "text": "The auth token provided by the collector on 'nodemgr register'."
    },
    {
        "section": "node",
        "keyword": "min_avail_mem",
        "default": "2%",
        "convert": "size",
        "text": "The minimum required available memory to allow orchestration."
    },
    {
        "section": "node",
        "keyword": "min_avail_swap",
        "default": "10%",
        "convert": "size",
        "text": "The minimum required available swap to allow orchestration."
    },
    {
        "section": "node",
        "keyword": "env",
        "default": "TST",
        "candidates": rcEnv.allowed_svc_envs,
        "text": "A non-PRD service can not be brought up on a PRD node, but a PRD service can be startup on a non-PRD node (in a DRP situation)."
    },
    {
        "section": "node",
        "keyword": "max_parallel",
        "default": 10,
        "convert": "integer",
        "text": "Allow a maximum of <max_parallel> subprocesses to run simultaneously on 'svcmgr --parallel <action>' commands."
    },
    {
        "section": "node",
        "keyword": "prkey",
        "default_text": "<autogenerated>",
        "text": "The scsi3 persistent reservation key used by the pr resources."
    },
    {
        "section": "node",
        "keyword": "loc_country",
        "example": "fr",
        "text": "An asset information to push to the collector on pushasset, overriding the currently stored value."
    },
    {
        "section": "node",
        "keyword": "loc_city",
        "example": "Paris",
        "text": "An asset information to push to the collector on pushasset, overriding the currently stored value."
    },
    {
        "section": "node",
        "keyword": "loc_zip",
        "example": "75017",
        "text": "An asset information to push to the collector on pushasset, overriding the currently stored value."
    },
    {
        "section": "node",
        "keyword": "loc_addr",
        "example": "7 rue blanche",
        "text": "An asset information to push to the collector on pushasset, overriding the currently stored value."
    },
    {
        "section": "node",
        "keyword": "loc_building",
        "example": "Crystal",
        "text": "An asset information to push to the collector on pushasset, overriding the currently stored value."
    },
    {
        "section": "node",
        "keyword": "loc_floor",
        "example": "21",
        "text": "An asset information to push to the collector on pushasset, overriding the currently stored value."
    },
    {
        "section": "node",
        "keyword": "loc_room",
        "example": "102",
        "text": "An asset information to push to the collector on pushasset, overriding the currently stored value."
    },
    {
        "section": "node",
        "keyword": "loc_rack",
        "example": "R42",
        "text": "An asset information to push to the collector on pushasset, overriding the currently stored value."
    },
    {
        "section": "node",
        "keyword": "sec_zone",
        "example": "dmz1",
        "text": "An asset information to push to the collector on pushasset, overriding the currently stored value."
    },
    {
        "section": "node",
        "keyword": "team_integ",
        "example": "TINT",
        "text": "An asset information to push to the collector on pushasset, overriding the currently stored value."
    },
    {
        "section": "node",
        "keyword": "team_support",
        "example": "TSUP",
        "text": "An asset information to push to the collector on pushasset, overriding the currently stored value."
    },
    {
        "section": "node",
        "keyword": "asset_env",
        "example": "Production",
        "text": "An asset information to push to the collector on pushasset, overriding the currently stored value."
    },
    {
        "section": "node",
        "keyword": "connect_to",
        "example": "1.2.3.4",
        "default_text": "On GCE instances, defaults to the instance ip address.",
        "text": "An asset information to push to the collector on pushasset, overriding the currently stored value."
    },
    {
        "section": "node",
        "keyword": "dbopensvc",
        "example": "https://collector.opensvc.com",
        "text": "Set the uri of the collector main xmlrpc server. The path part of the uri can be left unspecified. If not set, the agent does not try to communicate with a collector."
    },
    {
        "section": "node",
        "keyword": "dbcompliance",
        "example": "https://collector.opensvc.com/init/compliance/call/xmlrpc",
        "default_text": "Same protocol, server and port as dbopensvc, but with an different path.",
        "text": "Set the uri of the collectors' main xmlrpc server. The path part of the uri can be left unspecified."
    },
    {
        "section": "node",
        "keyword": "branch",
        "example": "1.9",
        "text": "Set the targeted opensvc agent branch. The downloaded upgrades will honor that branch. If not set, the repopkg imposes the target branch, which is not recommended with a public repopkg."
    },
    {
        "section": "node",
        "keyword": "repo",
        "example": "http://opensvc.repo.corp",
        "text": """Set the uri of the opensvc agent package repository and compliance modules gzipped tarball repository. This parameter is used by the 'nodemgr updatepkg' and 'nodemgr updatecomp' commands.
Expected repository structure::
	ROOT
	+- compliance
	 +- compliance-100.tar.gz
	 +- compliance-101.tar.gz
	 +- current -> compliance-101.tar.gz
	+- packages
	 +- deb
	 +- depot
	 +- pkg
	 +- sunos-pkg
	 +- rpms
	  +- current -> 1.9/current
	  +- 1.9
	   +- current -> opensvc-1.9-50.rpm
	   +- opensvc-1.9-49.rpm
	   +- opensvc-1.9-50.rpm
	 +- tbz
"""
    },
    {
        "section": "node",
        "keyword": "repopkg",
        "example": "http://repo.opensvc.com",
        "text": """Set the uri of the opensvc agent package repository. This parameter is used by the 'nodemgr updatepkg' command.
Expected repository structure::
	ROOT
	+- deb
	+- depot
	+- pkg
	+- sunos-pkg
	+- rpms
	 +- current -> 1.9/current
	 +- 1.9
	  +- current -> opensvc-1.9-50.rpm
	  +- opensvc-1.9-49.rpm
	  +- opensvc-1.9-50.rpm
	+- tbz
"""
    },
    {
        "section": "node",
        "keyword": "repocomp",
        "example": "http://compliance.repo.corp",
        "text": """Set the uri of the opensvc compliance modules gzipped tarball repository. This parameter is used by the 'nodemgr updatecomp' command.
Expected repository structure::
	ROOT
	+- compliance-100.tar.gz
	+- compliance-101.tar.gz
	+- current -> compliance-101.tar.gz
"""
    },
    {
        "section": "node",
        "keyword": "ruser",
        "example": "root opensvc@node1",
        "text": """Set the remote user to use to login to a remote node with ssh and rsync. The remote user must have the privileges to run as root the following commands on the remote node:
* nodemgr
* svcmgr
* rsync
The default ruser is root for all nodes. ruser accepts a list of user[@node] ... If @node is ommited, user is considered the new default user.
"""
    },
    {
        "section": "node",
        "keyword": "maintenance_grace_period",
        "convert": "duration",
        "default": 60,
        "text": "A duration expression, like 1m30s, defining how long the daemon retains a remote in-maintenance node data. The maintenance state is announced to peers on daemon stop and daemon restart, but not on daemon shutdown. As long as the remote node data are retained, the local daemon won't opt-in to takeover its running instances. This parameter should be adjusted to span the daemon restart time."
    },
    {
        "section": "node",
        "keyword": "rejoin_grace_period",
        "convert": "duration",
        "default": 90,
        "text": "A duration expression, like 90m, defining how long the daemon restrains from taking start decisions if no heartbeat has been received from a peer since daemon startup. This should be adjusted to the maximum delay you can afford to give a chance to services to start on their placement leader after a simultaneous node reboot."
    },
    {
        "section": "node",
        "keyword": "ready_period",
        "convert": "duration",
        "default": 5,
        "text": "A duration expression, like 10s, defining how long the daemon monitor waits before starting a service instance in ready state. A peer node can preempt the start during this period. Usually set to allow at least a couple of heartbeats to be received."
    },
    {
        "section": "centera",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'centera' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "xtremio",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'pushxtremio' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "hp3par",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'pushhp3par' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "vnx",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'pushvnx' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "freenas",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'pushfreenas' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "gcedisks",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'pushgcedisks' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "dequeue_actions",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'dequeue actions' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "sysreport",
        "keyword": "schedule",
        "default": "00:00-06:00",
        "text": "Schedule parameter for the 'sysreport' node action, which check all modules and fix only modules flagged 'autofix'. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "compliance",
        "keyword": "schedule",
        "default": "02:00-06:00",
        "text": "Schedule parameter for the 'compliance auto' node action, which check all modules and fix only modules flagged 'autofix'. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "compliance",
        "keyword": "auto_update",
        "convert": "boolean",
        "default": False,
        "text": "If set to True, and if the execution context indicates a scheduled run, execute 'updatecomp' upon 'compliance check'. This toggle helps keep the compliance modules in sync with the reference repository. Beware of the security impact of this setting: you must be careful your module repository is kept secure."
    },
    {
        "section": "stats",
        "keyword": "schedule",
        "default": "00:00-06:00",
        "text": "Schedule parameter for the 'pushstats' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "stats",
        "keyword": "disable",
        "convert": "list",
        "example": "blockdev, mem_u",
        "text": "Disable push for a stats group (mem_u, cpu, proc, swap, netdev, netdev_err, block, blockdev, fs_u)."
    },
    {
        "section": "checks",
        "keyword": "schedule",
        "default": "00:00-06:00",
        "text": "Schedule parameter for the 'pushchecks' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "packages",
        "keyword": "schedule",
        "default": "00:00-06:00",
        "text": "Schedule parameter for the 'pushpkg' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "patches",
        "keyword": "schedule",
        "default": "00:00-06:00",
        "text": "Schedule parameter for the 'pushpatch' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "asset",
        "keyword": "schedule",
        "default": "00:00-06:00",
        "text": "Schedule parameter for the 'pushasset' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "nsr",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'pushnsr' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "dcs",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'pushdcs' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "hds",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'pushhds' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "necism",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'pushnecism' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "eva",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'pusheva' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "ibmds",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'pushibmds' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "ibmsvc",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'pushibmsvc' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "vioserver",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'pushvioserver' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "brocade",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'pushbrocade' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "disks",
        "keyword": "schedule",
        "default": "00:00-06:00",
        "text": "Schedule parameter for the 'pushdisks' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "sym",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'pushsym' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "rotate_root_pw",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'rotate root pw' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "stats_collection",
        "keyword": "schedule",
        "default": "@10",
        "text": "Schedule parameter for the 'collect stats' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "reboot",
        "keyword": "schedule",
        "text": "Schedule parameter for the 'auto reboot' node action. See usr/share/doc/schedule for the schedule syntax."
    },
    {
        "section": "reboot",
        "keyword": "once",
        "convert": "boolean",
        "default": True,
        "text": """If once is set to false, do not remove the reboot flag before rebooting,
so that the node is ready to reboot again in the next allowed timerange.
This setup is needed to enforce a periodic reboot, with a patching script
hooked as a pre trigger for example.
If not set, or set to true, the reboot flag is removed before reboot, and a 'nodemgr schedule reboot' is needed to rearm.
"""
    },
    {
        "section": "reboot",
        "keyword": "pre",
        "convert": "shlex",
        "example": "yum upgrade -y",
        "text": "A command to execute before reboot. Errors are ignored."
    },
    {
        "section": "reboot",
        "keyword": "blocking_pre",
        "convert": "shlex",
        "example": "yum upgrade -y",
        "text": "A command to execute before reboot. Abort the reboot on error."
    },
    {
        "section": "listener",
        "keyword": "addr",
        "default": "0.0.0.0",
        "example": "1.2.3.4",
        "text": "The ip addr the daemon listener must listen on."
    },
    {
        "section": "listener",
        "keyword": "port",
        "default": 1214,
        "text": """The port the daemon listener must listen on. In pull action mode, the collector sends a tcp packet to the server to notify there are actions to unqueue. The opensvc daemon executes the 'dequeue actions' node action upon receive. The listener.port parameter is sent to the collector upon pushasset. The collector uses this port to notify the node."""
    },
    {
        "section": "syslog",
        "keyword": "facility",
        "default": "daemon",
        "text": """The syslog facility to log to."""
    },
    {
        "section": "syslog",
        "keyword": "level",
        "default": "info",
        "candidates": ["critical", "error", "warning", "info", "debug"],
        "text": "The minimum message criticity to feed to syslog. Setting to critical actually disables the syslog logging, as the agent does not emit message at this level."
    },
    {
        "section": "syslog",
        "keyword": "host",
        "default_text": "localhost if port is set",
        "text": "The syslog host to send logs to. If neither host nor port are specified and if /dev/log exists, the messages are posted to /dev/log."
    },
    {
        "section": "syslog",
        "keyword": "port",
        "default": 514,
        "text": "The syslog host to send logs to. If neither host nor port are specified and if /dev/log exists, the messages are posted to /dev/log."
    },
    {
        "section": "cluster",
        "keyword": "dns",
        "convert": "list",
        "default": [],
        "at": True,
        "text": "The list of nodes to set as dns in the containers resolvers. If set, the search will also be set to <svcname>.<clustername> and <clustername>."
    },
    {
        "section": "cluster",
        "keyword": "id",
        "at": True,
        "default_text": "<auto-generated>",
        "text": "This information is fetched from the join command payload received from the joined node."
    },
    {
        "section": "cluster",
        "keyword": "name",
        "at": True,
        "default": "default",
        "text": "This information is fetched from the join command payload received from the joined node."
    },
    {
        "section": "cluster",
        "keyword": "secret",
        "at": True,
        "default_text": "<random autogenerated on first use>",
        "text": "The cluster shared secret. Used to encrypt/decrypt data with AES256. This secret is either autogenerated or fetched from a join command."
    },
    {
        "section": "cluster",
        "keyword": "nodes",
        "convert": "list",
        "text": "This list is fetched from the join command payload received from the joined node. The service configuration {clusternodes} is resolved to this keyword value."
    },
    {
        "section": "cluster",
        "keyword": "drpnodes",
        "convert": "list",
        "text": "This list is fetched from the join command payload received from the joined node. The service configuration {clusterdrpnodes} is resolved to this keyword value."
    },
    {
        "section": "cluster",
        "keyword": "quorum",
        "convert": "boolean",
        "text": "Should a split segment of the cluster commit suicide. Default is False. If set to true, please set at least 2 arbitrators so you can rolling upgrade the opensvc daemons."
    },
    {
        "section": "arbitrator",
        "keyword": "name",
        "required": True,
        "text": """The arbitrator resolvable node name.
An arbitrator is a opensvc node (running the usual osvc daemon) this
cluster nodes can ask for a vote when the cluster is split.
Arbitrators are tried in sequence, the first reachable arbitrator
gives a vote. In case of a real split, all arbitrators are expected to
be unreachable from the lost segment. At least one of them is
expected to be reachable from the surviving segment.
Arbitrators of a cluster must thus be located close enough to each
other, so a subset of arbitrators can't be reachable from a split
cluster segment, while another subset of arbitrators is reachable
from the other split cluster segment. But not close enough so they can
all fail together. Usually, this can be interpreted as: same site,
not same rack and power lines.
Arbitrators usually don't run services, even though they could, as their
secret might be known by multiple clusters of different responsibles.
Arbitrators can be tested using "nodemgr ping --node <arbitrator name>".
"""
    },
    {
        "section": "arbitrator",
        "keyword": "secret",
        "required": True,
        "text": "The secret to use to encrypt/decrypt data exchanged with the arbitrator (AES256)."
    },
    {
        "section": "stonith",
        "keyword": "cmd",
        "at": True,
        "convert": "shlex",
        "required": True,
        "example": "/bin/true",
        "text": "The command to use to STONITH a peer. Usually comes from a fencing utilities collection."
    },
    {
        "section": "hb",
        "keyword": "type",
        "candidates": ["unicast", "multicast", "disk", "relay"],
        "required": True,
        "text": "The heartbeat driver name."
    },
    {
        "section": "hb",
        "keyword": "addr",
        "rtype": "unicast",
        "at": True,
        "example": "1.2.3.4",
        "default_text": "0.0.0.0 for listening and to the resolved nodename for sending.",
        "text": "The ip address of each node."
    },
    {
        "section": "hb",
        "keyword": "intf",
        "rtype": "unicast",
        "at": True,
        "default_text": "The natural interface for <addr>",
        "example": "eth0",
        "text": "The interface to bind."
    },
    {
        "section": "hb",
        "keyword": "port",
        "rtype": "unicast",
        "convert": "integer",
        "at": True,
        "default": 10000,
        "text": "The port for each node to send to or listen on."
    },
    {
        "section": "hb",
        "keyword": "timeout",
        "convert": "duration",
        "at": True,
        "default": 15,
        "text": "The delay since the last received heartbeat from a node before considering this node is gone."
    },
    {
        "section": "hb",
        "keyword": "addr",
        "rtype": "multicast",
        "at": True,
        "default": "224.3.29.71",
        "text": "The multicast address to send to and listen on."
    },
    {
        "section": "hb",
        "keyword": "intf",
        "rtype": "multicast",
        "at": True,
        "default_text": "The natural interface for <addr>",
        "example": "eth0",
        "text": "The interface to bind."
    },
    {
        "section": "hb",
        "keyword": "port",
        "rtype": "multicast",
        "convert": "integer",
        "at": True,
        "default": 10000,
        "text": "The port for each node to send to or listen on."
    },
    {
        "section": "hb",
        "keyword": "dev",
        "rtype": "disk",
        "required": True,
        "text": "The device to write the hearbeats to and read from. It must be dedicated to the daemon use. Its size should be 1M + 1M per cluster node."
    },
    {
        "section": "hb",
        "keyword": "relay",
        "rtype": "relay",
        "required": True,
        "example": "relaynode1",
        "text": "The relay resolvable node name."
    },
    {
        "section": "hb",
        "keyword": "secret",
        "rtype": "relay",
        "required": True,
        "example": "123123123124325543565",
        "text": "The secret to use to encrypt/decrypt data exchanged with the relay (AES256)."
    },
    {
        "section": "cni",
        "keyword": "plugins",
        "default": "/opt/cni/bin",
        "text": "The directory hosting the CNI plugins."
    },
    {
        "section": "cni",
        "keyword": "config",
        "default": "/opt/cni/net.d",
        "text": "The directory hosting the CNI network configuration files."
    },
    {
        "section": "pool",
        "keyword": "type",
        "default": "directory",
        "candidates": ["directory", "loop", "vg", "zpool"],
        "text": "The pool type."
    },
    {
        "section": "pool",
        "keyword": "mnt_opt",
        "at": True,
        "text": "The mount options of the fs created over the pool devices."
    },
    {
        "section": "pool",
        "rtype": "vg",
        "keyword": "name",
        "required": True,
        "text": "The name of the volume group to allocate the pool logical volumes into."
    },
    {
        "section": "pool",
        "rtype": "zpool",
        "keyword": "name",
        "required": True,
        "text": "The name of the zpool to allocate the pool datasets into."
    },
    {
        "section": "pool",
        "keyword": "path",
        "rtype": "loop",
        "default": "{var}/pool/loop",
        "text": "The path to create the pool loop files in."
    },
    {
        "section": "pool",
        "keyword": "path",
        "rtype": "directory",
        "default": "{var}/pool/directory",
        "text": "The path to create the pool loop files in."
    },
    {
        "section": "pool",
        "keyword": "fs_type",
        "default": "xfs",
        "text": "The filesystem to format the pool devices with."
    },
    {
        "section": "pool",
        "keyword": "mkfs_opt",
        "default": [],
        "convert": "list",
        "example": "-O largefile",
        "text": "The mkfs command options to use to format the pool devices."
    },
    {
        "section": "pool",
        "rtype": "vg",
        "keyword": "create_opt",
        "default": [],
        "convert": "list",
        "text": "The lvcreate command options to use to create the pool logical volumes."
    },
    {
        "section": "hook",
        "keyword": "events",
        "default": [],
        "convert": "list",
        "text": "The list of events to execute the hook command on. The special value 'all' is also supported."
    },
    {
        "section": "hook",
        "keyword": "command",
        "convert": "shlex",
        "text": "The command to execute on selected events. The program is fed the json-formatted event data through stdin."
    },
]


KEYS = KeywordStore(
    keywords=KEYWORDS,
    deprecated_keywords=DEPRECATED_KEYWORDS,
    deprecated_sections=DEPRECATED_SECTIONS,
    template_prefix="template.node.",
    base_sections=BASE_SECTIONS,
    has_default_section=False,
 )

if __name__ == "__main__":
    if len(sys.argv) == 2:
        fmt = sys.argv[1]
    else:
        fmt = "text"

    KEYS.write_templates(fmt=fmt)
