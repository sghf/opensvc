#!/opt/opensvc/bin/python

import sys

class MissKeyNoDefault(Exception):
     pass

class KeyInvalidValue(Exception):
     pass

class Keyword(object):
    def __init__(self, section, keyword,
                 rtype=None,
                 order=100,
                 required=False,
                 at=False,
                 default=None,
                 validator=None,
                 candidates=None,
                 depends=[],
                 text=""):
        self.section = section
        self.keyword = keyword
        self.rtype = rtype
        self.order = order
        self.at = at
        self.required = required
        self.default = default
        self.validator = validator
        self.candidates = candidates
        self.depends = depends
        self.text = text

    def __cmp__(self, o):
        if o.order > self.order:
            return -1
        elif o.order == self.order:
            return 0
        return 1

    def __str__(self):
        from textwrap import TextWrapper
        wrapper = TextWrapper(subsequent_indent="%15s"%"", width=78)

        if self.validator is None:
            validator = False
        else:
            validator = True
        depends = ""
        for d in self.depends:
            depends += "%s in %s\n"%(d[0], d[1])
        if depends == "":
            depends = None

        s = ''
        s += "------------------------------------------------------------------------------\n"
        s += "section:       %s\n"%self.section
        s += "keyword:       %s\n"%self.keyword
        s += "------------------------------------------------------------------------------\n"
        s += "  required:    %s\n"%str(self.required)
        s += "  default:     %s\n"%str(self.default)
        s += "  candidates:  %s\n"%str(self.candidates)
        s += "  validator:   %s\n"%str(validator)
        s += "  depends:     %s\n"%depends
        s += "  @node:       %s\n"%str(self.at)
        if self.text:
            s += wrapper.fill("  help:        "+self.text)
        if self.at:
            s += "\n\nPrefix the value with '@node ' to specify a node-specific value.\n"
            s += "You will be prompted for new values until you submit an empty value.\n"
        return s

    def form(self, d):
        for d_keyword, d_value in self.depends:
            if d_keyword not in d:
                return d
            if d[d_keyword] not in d_value:
                return d
        print self
        if self.keyword in d:
            default = d[self.keyword]
        elif self.default is not None:
            default = self.default
        else:
            default = None

        if default is not None:
            default_prompt = " [%s] "%str(default)
        else:
            default_prompt = ""

        req_satisfied = False
        while True:
            val = raw_input(self.keyword+default_prompt+"> ")
            if len(val) == 0:
                if req_satisfied:
                    return d
                if default is None:
                    if self.required:
                        print "value required"
                        continue
                    # keyword is optional, leave dictionaty untouched
                    return d
                else:
                    val = default
                if self.candidates is not None and \
                   val not in self.candidates:
                    print "invalid value"
                    continue
            if self.at and val[0] == '@':
                l = val.split()
                if len(l) < 2:
                    print "invalid value"
                    continue
                val = ' '.join(l[1:])
                d[self.keyword+l[0]] = val
                req_satisfied = True
            else:
                d[self.keyword] = val
                req_satisfied = True
            if self.at:
                # loop for more key@node = values
                print "More '%s' ? <enter> to step to the next parameter."%self.keyword
                continue
            else:
                return d

class Section(object):
    def __init__(self, section):
        self.section = section
        self.keywords = []

    def __iadd__(self, o):
        if not isinstance(o, Keyword):
            return self
        self.keywords.append(o)
        return self

    def __str__(self):
        s = ''
        for keyword in sorted(self.keywords):
            s += str(keyword)
        return s

    def getkeys(self, rtype=None):
        if rtype is None:
            return [k for k in self.keywords if k.rtype is None]
        else:
            return [k for k in self.keywords if k.rtype == rtype]

    def getkey(self, keyword, rtype=None):
        for k in self.keywords:
            if k.keyword == keyword and k.rtype == rtype:
                return k
        return None

class KeywordStore(dict):
    def __init__(self):
        self.sections = {}

    def __iadd__(self, o):
        if not isinstance(o, Keyword):
            return self
        if o.section not in self.sections:
             self.sections[o.section] = Section(o.section)
        self.sections[o.section] += o
        return self

    def __getattr__(self, key):
        return self.sections[str(key)]

    def __getitem__(self, key):
        return self.sections[str(key)]

    def __str__(self):
        s = ''
        for section in self.sections:
            s += str(self.sections[section])
        return s

    def required_keys(self, section, rtype=None):
        if section not in self.sections:
            return []
        return [k for k in sorted(self.sections[section].getkeys(rtype)) if k.required is True]

    def update(self, rid, d):
        """ Given a resource dictionary, spot missing required keys
            and provide a new dictionary to merge populated by default
            values
        """
        completion = {}

        # decompose rid into section and rtype
        if rid == 'DEFAULT':
            section = rid
            rtype = None
        else:
            if '#' not in rid:
                return {}
            l = rid.split('#')
            if len(l) != 2:
                return {}
            section = l[0]
            if 'type' in d:
                 rtype = d['type']
            elif self[section].getkey('type') is not None and \
                  self[section].getkey('type').default is not None:
                rtype = self[section].getkey('type').default
            else:
                rtype = None

        # validate command line dictionary
        for keyword, value in d.items():
            key = self.sections[section].getkey(keyword)
            if key is None and rtype is not None:
                key = self.sections[section].getkey(keyword, rtype)
            if key is None:
                if keyword != "rtype":
                    print "Remove unknown keyword '%s' from section '%s'"%(keyword, rid)
                    del d[keyword]
                continue
            if key.candidates is None:
                continue
            if value not in key.candidates:
                print "'%s' keyword has invalid value '%s' in section '%s'"%(keyword, str(value), rid)
                raise KeyInvalidValue()

        # add missing required keys if they have a known default value
        for key in self.required_keys(section, rtype):
            if key.keyword in d:
                continue
            if key.default is None:
                sys.stderr.write("No default value for required key '%s' in section '%s'\n"%(key.keyword, rid))
                raise MissKeyNoDefault()
            print "Implicitely add [%s]"%rid, key.keyword, "=", key.default
            completion[key.keyword] = key.default
        return completion

    def form_sections(self, sections):
        from textwrap import TextWrapper
        wrapper = TextWrapper(subsequent_indent="%18s"%"", width=78)
        candidates = set(self.sections.keys()) - set(['DEFAULT'])

        print "------------------------------------------------------------------------------"
        print "Choose a resource type to add or a resource to edit."
        print "Enter 'quit' to finish the creation."
        print "------------------------------------------------------------------------------"
        print wrapper.fill("resource types: "+', '.join(candidates))
        print wrapper.fill("resource ids:   "+', '.join(sections.keys()))
        print
        return raw_input("resource type or id> ")

    def free_resource_index(self, section, sections):
        indices = []
        for s in sections:
            l = s.split('#')
            if len(l) != 2:
                continue
            sname, sindex = l
            if section != sname:
                continue
            try:
                indices.append(int(sindex))
            except:
                continue
        i = 0
        while True:
            if i not in indices:
                return i
            i += 1

    def form(self, defaults, sections):
        for key in sorted(self.DEFAULT.getkeys()):
            defaults = key.form(defaults)
        while True:
            section = self.form_sections(sections)
            if section == "quit":
                 break
            if '#' in section:
                rid = section
                section = section.split('#')[0]
            else:
                index = self.free_resource_index(section, sections)
                rid = '#'.join((section, str(index)))
            if section not in self.sections:
                 print "unsupported resource type"
                 continue
            for key in sorted(self.sections[section].getkeys()):
                if rid not in sections:
                    sections[rid] = {}
                sections[rid] = key.form(sections[rid])
            if 'type' not in sections[rid]:
                continue
            specific_keys = self.sections[section].getkeys(rtype=sections[rid]['type'])
            if len(specific_keys) > 0:
                print "\nKeywords specific to the '%s' driver\n"%sections[rid]['type']
            for key in sorted(specific_keys):
                if rid not in sections:
                    sections[rid] = {}
                sections[rid] = key.form(sections[rid])
        return defaults, sections

class KeyDict(KeywordStore):
    def __init__(self):
        KeywordStore.__init__(self)

        import os
        from rcNode import node_get_hostmode
        from rcGlobalEnv import rcEnv
        sysname, nodename, x, x, machine = os.uname()

        def is_integer(val):
            try:
                 val = int(val)
            except:
                 return False
            return True

        def kw_disable(resource):
            return Keyword(
                  section=resource,
                  keyword="disable",
                  candidates=(True, False),
                  default=False,
                  text="A disabled resource will be ignored on service startup and shutdown."
                )
        def kw_disable_on(resource):
            return Keyword(
                  section=resource,
                  keyword="disable_on",
                  text="A list of nodenames where to consider the 'disable' value is True."
                )
        def kw_optional(resource):
            return Keyword(
                  section=resource,
                  keyword="optional",
                  candidates=(True, False),
                  default=False,
                  text="Possible values are 'true' or 'false'. Actions on resource will be tried upon service startup and shutdown, but action failures will be logged and passed over. Useful for resources like dump filesystems for example."
                )
        def kw_always_on(resource):
            return Keyword(
                  section=resource,
                  keyword="always_on",
                  candidates=['nodes', 'drpnodes', 'nodes drpnodes'],
                  text="Possible values are 'nodes', 'drpnodes' or 'nodes drpnodes', or a list of nodes. Sets the nodes on which the resource is always kept up. Primary usage is file synchronization receiving on non-shared disks. Don't set this on shared disk !! danger !!"
                )

        for r in ["sync", "ip", "fs", "vg", "hb", "pool", "vmdg", "drbd",
                  "loop", "vdisk"]:
            self += kw_disable(r)
            self += kw_disable_on(r)
            self += kw_optional(r)
            self += kw_always_on(r)

        self += Keyword(
                  section="DEFAULT",
                  keyword="mode",
                  order=10,
                  default="hosted",
                  candidates=["hosted"] + rcEnv.vt_supported,
                  text="The mode decides upon disposition OpenSVC takes to bring a service up or down : virtualized services need special actions to prepare and boot the container for example, which is not needed for 'hosted' services."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="vm_name",
                  order=11,
                  depends=[('mode', rcEnv.vt_supported)],
                  text="This need to be set if the virtual machine name is different from the service name."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="service_type",
                  order=15,
                  required=True,
                  default=node_get_hostmode(os.path.join(os.path.dirname(__file__), '..', 'var')),
                  candidates=["PRD", "DEV"],
                  text="A DEV service can not be brought up on a PRD node, but a PRD service can be startup on a DEV node (in a DRP situation)."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="nodes",
                  order=20,
                  required=True,
                  default=nodename,
                  text="List of cluster local nodes able to start the service.  Whitespace separated."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="autostart_node",
                  order=20,
                  required=True,
                  default=nodename,
                  text="The node from 'nodes' where the service will try to start on upon node reboot. The start-up will fail if the service is already up on another node though. If not specified, the service will never be started at node boot-time, which is rarely the expected behaviour."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="drpnode",
                  order=21,
                  text="The backup node where the service is activated in a DRP situation. This node is also a data synchronization target for 'sync' resources."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="drpnodes",
                  order=21,
                  text="Alternate backup nodes, where the service could be activated in a DRP situation if the 'drpnode' is not available. These nodes are also data synchronization targets for 'sync' resources."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="app",
                  order=24,
                  default="DEFAULT",
                  text="Used to identify who is responsible for is service, who is billable and provides a most useful filtering key. Better keep it a short code."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="comment",
                  order=25,
                  text="Helps users understand the role of the service, which is nice to on-call support people having to operate on a service they are not usualy responsible for."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="scsireserv",
                  order=25,
                  default=False,
                  candidates=(True, False),
                  text="If set to 'true', OpenSVC will try to acquire a type-5 (write exclusive, registrant only) scsi3 persistent reservation on every path to disks of every disk group attached to this service. Existing reservations are preempted to not block service start-up. If the start-up was not legitimate the data are still protected from being written over from both nodes. If set to 'false' or not set, 'scsireserv' can be activated on a per-resource basis."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="bwlimit",
                  order=25,
                  validator=is_integer,
                  text="Bandwidth limit in KB applied to all rsync transfers."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="sync_min_delay",
                  order=26,
                  validator=is_integer,
                  default=30,
                  text="Set the minimum delay between syncs in minutes. If a sync is triggered through crond or manually, it is skipped if last sync occured less than 'sync_min_delay' ago. The mecanism is enforced by a timestamp created upon each sync completion in /opt/opensvc/var/sync/[service]![dst]"
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="sync_max_delay",
                  order=27,
                  validator=is_integer,
                  default=1440,
                  text="Unit is minutes. This sets to delay above which the sync status of the resource is to be considered down. Should be set according to your application service level agreement. The cron job frequency should be set between 'sync_min_delay' and 'sync_max_delay'"
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="presnap_trigger",
                  order=28,
                  text="Define a command to run before creating snapshots. This is most likely what you need to use plug a script to put you data in a coherent state (alter begin backup and the like)."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="postsnap_trigger",
                  order=29,
                  text="Define a command to run after snapshots are created. This is most likely what you need to use plug a script to undo the actions of 'presnap_trigger'."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="containerize",
                  order=30,
                  default=True,
                  candidates=(True, False),
                  text="Use process containers when possible. Containers allow capping memory, swap and cpu usage per service. Lxc containers are naturally containerized, so skip containerization of their startapp."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="container_cpus",
                  order=31,
                  validator=is_integer,
                  depends=[('containerize', [True])],
                  text="Allow service process to bind only the specified cpus. Cpus are specified as list or range : 0,1,2 or 0-2"
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="container_mems",
                  order=31,
                  validator=is_integer,
                  depends=[('containerize', [True])],
                  text="Allow service process to bind only the specified memory nodes. Memory nodes are specified as list or range : 0,1,2 or 0-2"
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="container_cpu_share",
                  order=31,
                  validator=is_integer,
                  depends=[('containerize', [True])],
                  text="Kernel default value is used, which usually is 1024 shares. In a cpu-bound situation, ensure the service does not use more than its share of cpu ressource. The actual percentile depends on shares allowed to other services."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="container_mem_limit",
                  order=31,
                  validator=is_integer,
                  depends=[('containerize', [True])],
                  text="Ensures the service does not use more than specified memory (in bytes). The Out-Of-Memory killer get triggered in case of tresspassing."
                )
        self += Keyword(
                  section="DEFAULT",
                  keyword="container_vmem_limit",
                  order=31,
                  validator=is_integer,
                  depends=[('containerize', [True])],
                  text="Ensures the service does not use more than specified memory+swap (in bytes). The Out-Of-Memory killer get triggered in case of tresspassing. The specified value must be greater than container_mem_limit."
                )
        self += Keyword(
                  section="sync",
                  keyword="type",
                  order=10,
                  required=True,
                  candidates=("rsync", "dds", "netapp", "zfs", "symclone"),
                  default="rsync",
                  text="Point a sync driver to use."
                )
        self += Keyword(
                  section="sync",
                  keyword="src",
                  rtype="zfs",
                  order=10,
                  at=True,
                  required=True,
                  text="Source dataset of the sync."
                )
        self += Keyword(
                  section="sync",
                  keyword="dst",
                  rtype="zfs",
                  order=11,
                  at=True,
                  required=True,
                  text="Destination dataset of the sync."
                )
        self += Keyword(
                  section="sync",
                  keyword="target",
                  rtype="zfs",
                  order=12,
                  required=True,
                  candidates=['nodes', 'drpnodes', 'nodes drpnodes'],
                  text="Describes which nodes should receive this data sync from the PRD node where the service is up and running. SAN storage shared 'nodes' must not be sync to 'nodes'. SRDF-like paired storage must not be sync to 'drpnodes'."
                )
        self += Keyword(
                  section="sync",
                  keyword="recursive",
                  rtype="zfs",
                  order=13,
                  default=True,
                  candidates=(True, False),
                  text="Describes which nodes should receive this data sync from the PRD node where the service is up and running. SAN storage shared 'nodes' must not be sync to 'nodes'. SRDF-like paired storage must not be sync to 'drpnodes'."
                )
        self += Keyword(
                  section="sync",
                  keyword="tags",
                  rtype="zfs",
                  text="The zfs sync resource supports the 'delay_snap' tag. This tag is used to delay the snapshot creation just before the sync, thus after 'postsnap_trigger' execution. The default behaviour (no tags) is to group all snapshots creation before copying data to remote nodes, thus between 'presnap_trigger' and 'postsnap_trigger'."
                )
        self += Keyword(
                  section="sync",
                  keyword="src",
                  rtype="rsync",
                  order=10,
                  at=True,
                  required=True,
                  text="Source of the sync. Can be a whitespace-separated list of files or dirs passed as-is to rsync. Beware of the meaningful ending '/'. Refer to the rsync man page for details."
                )
        self += Keyword(
                  section="sync",
                  keyword="dst",
                  rtype="rsync",
                  order=11,
                  required=True,
                  text="Destination of the sync. Beware of the meaningful ending '/'. Refer to the rsync man page for details."
                )
        self += Keyword(
                  section="sync",
                  keyword="tags",
                  rtype="rsync",
                  text="The sync resource supports the 'delay_snap' tag. This tag is used to delay the snapshot creation just before the rsync, thus after 'postsnap_trigger' execution. The default behaviour (no tags) is to group all snapshots creation before copying data to remote nodes, thus between 'presnap_trigger' and 'postsnap_trigger'."
                )
        self += Keyword(
                  section="sync",
                  keyword="exclude",
                  rtype="rsync",
                  text="!deprecated!. A whitespace-separated list of --exclude params passed unchanged to rsync. The 'options' keyword is preferred now."
                )
        self += Keyword(
                  section="sync",
                  keyword="options",
                  rtype="rsync",
                  text="A whitespace-separated list of params passed unchanged to rsync. Typical usage is ACL preservation activation."
                )
        self += Keyword(
                  section="sync",
                  keyword="target",
                  rtype="rsync",
                  order=12,
                  required=True,
                  candidates=['nodes', 'drpnodes', 'nodes drpnodes'],
                  text="Describes which nodes should receive this data sync from the PRD node where the service is up and running. SAN storage shared 'nodes' must not be sync to 'nodes'. SRDF-like paired storage must not be sync to 'drpnodes'."
                )
        self += Keyword(
                  section="sync",
                  keyword="snap",
                  rtype="rsync",
                  order=14,
                  candidates=(True, False),
                  default=False,
                  text="If set to true, OpenSVC will try to snapshot the first snapshottable parent of the source of the sync and try to sync from the snap."
                )
        self += Keyword(
                  section="sync",
                  keyword="dstfs",
                  rtype="rsync",
                  order=13,
                  text="If set to a remote mount point, OpenSVC will verify that the specified mount point is really hosting a mounted FS. This can be used as a safety net to not overflow the parent FS (may be root)."
                )
        self += Keyword(
                  section="sync",
                  keyword="bwlimit",
                  rtype="rsync",
                  validator=is_integer,
                  text="Bandwidth limit in KB applied to this rsync transfer. Takes precedence over 'bwlimit' set in [DEFAULT]."
                )
        self += Keyword(
                  section="sync",
                  keyword="sync_min_delay",
                  validator=is_integer,
                  default=30,
                  text="Set the minimum delay between syncs in minutes. If a sync is triggered through crond or manually, it is skipped if last sync occured less than 'sync_min_delay' ago. If no set in a resource section, fallback to the value set in the 'default' section. The mecanism is enforced by a timestamp created upon each sync completion in /opt/opensvc/var/sync/[service]![dst]"
                )
        self += Keyword(
                  section="sync",
                  keyword="sync_max_delay",
                  validator=is_integer,
                  default=1440,
                  text="Unit is minutes. This sets to delay above which the sync status of the resource is to be considered down. Should be set according to your application service level agreement. The cron job frequency should be set between 'sync_min_delay' and 'sync_max_delay'."
                )
        self += Keyword(
                  section="ip",
                  keyword="ipname",
                  order=12,
                  at=True,
                  required=True,
                  text="The DNS name of the ip resource. Can be different from one node to the other, in which case '@nodename' can be specified. This is most useful to specify a different ip when the service starts in DRP mode, where subnets are likely to be different than those of the production datacenter."
                )
        self += Keyword(
                  section="ip",
                  keyword="ipdev",
                  order=11,
                  at=True,
                  required=True,
                  text="The interface name over which OpenSVC will try to stack the service ip. Can be different from one node to the other, in which case the '@nodename' can be specified."
                )
        self += Keyword(
                  section="ip",
                  keyword="netmask",
                  order=13,
                  text="If an ip is already plumbed on the root interface (if which case the netmask is deduced from this ip). Mandatory if the interface is dedicated to the service (dummy interface are likely to be in this case). The format is decimal for IPv4, ex: 255.255.252.0, and octal for IPv6, ex: 64."
                )
        self += Keyword(
                  section="vg",
                  keyword="type",
                  order=9,
                  required=False,
                  candidates=['veritas'],
                  text="The volume group driver to use. Leave empty to activate the native volume group manager."
                )
        self += Keyword(
                  section="vg",
                  keyword="vgname",
                  order=10,
                  required=True,
                  text="The name of the volume group"
                )
        self += Keyword(
                  section="vg",
                  keyword="dsf",
                  candidates=(True, False),
                  default=True,
                  text="HP-UX only. 'dsf' must be set to false for LVM to use never-multipathed /dev/dsk/... devices. Otherwize, ad-hoc multipathed /dev/disk/... devices."
                )
        self += Keyword(
                  section="vg",
                  keyword="scsireserv",
                  default=False,
                  candidates=(True, False),
                  text="If set to 'true', OpenSVC will try to acquire a type-5 (write exclusive, registrant only) scsi3 persistent reservation on every path to disks of every disk group attached to this service. Existing reservations are preempted to not block service start-up. If the start-up was not legitimate the data are still protected from being written over from both nodes. If set to 'false' or not set, 'scsireserv' can be activated on a per-resource basis."
                )
        self += Keyword(
                  section="pool",
                  keyword="poolname",
                  order=10,
                  at=True,
                  text="The name of the zfs pool"
                )
        self += Keyword(
                  section="pool",
                  keyword="tags",
                  text="tags  = preboot may be used when zfs pool is required before container boot else postboot is presumed"
                )
        self += Keyword(
                  section="vmdg",
                  keyword="scsireserv",
                  default=False,
                  candidates=(True, False),
                  text="If set to 'true', OpenSVC will try to acquire a type-5 (write exclusive, registrant only) scsi3 persistent reservation on every path to disks of every disk group attached to this service. Existing reservations are preempted to not block service start-up. If the start-up was not legitimate the data are still protected from being written over from both nodes. If set to 'false' or not set, 'scsireserv' can be activated on a per-resource basis."
                )
        self += Keyword(
                  section="drbd",
                  keyword="scsireserv",
                  default=False,
                  candidates=(True, False),
                  text="If set to 'true', OpenSVC will try to acquire a type-5 (write exclusive, registrant only) scsi3 persistent reservation on every path to disks of every disk group attached to this service. Existing reservations are preempted to not block service start-up. If the start-up was not legitimate the data are still protected from being written over from both nodes. If set to 'false' or not set, 'scsireserv' can be activated on a per-resource basis."
                )
        self += Keyword(
                  section="drbd",
                  keyword="res",
                  order=11,
                  text="The name of the drbd resource associated with this service resource. OpenSVC expect the resource configuration file to reside in '/etc/drbd.d/resname.res'. The 'sync#i0' resource will take care of replicating this file to remote nodes."
                )
        self += Keyword(
                  section="fs",
                  keyword="dev",
                  order=11,
                  at=True,
                  required=True,
                  text="The block device file or filesystem image file hosting the filesystem to mount. Different device can be set up on different nodes using the dev@nodename syntax"
                )
        self += Keyword(
                  section="fs",
                  keyword="mnt",
                  order=12,
                  required=True,
                  text="The mount point where to mount the filesystem."
                )
        self += Keyword(
                  section="fs",
                  keyword="mnt_opt",
                  order=13,
                  text="The mount options."
                )
        self += Keyword(
                  section="fs",
                  keyword="type",
                  order=14,
                  required=True,
                  text="The filesystem type. Used to determine the fsck command to use."
                )
        self += Keyword(
                  section="loop",
                  keyword="file",
                  required=True,
                  text="The file hosting the disk image to map."
                )
        self += Keyword(
                  section="sync",
                  keyword="filer",
                  rtype="netapp",
                  required=True,
                  at=True,
                  text="The Netapp filer resolvable host name used by the node.  Different filers can be set up for each node using the filer@nodename syntax."
                )
        self += Keyword(
                  section="sync",
                  keyword="path",
                  rtype="netapp",
                  required=True,
                  text="Specifies the volume or qtree to drive snapmirror on."
                )
        self += Keyword(
                  section="sync",
                  keyword="user",
                  rtype="netapp",
                  required=True,
                  default="nasadm",
                  text="Specifies the user used to ssh connect the filers. Nodes should be trusted by keys to access the filer with this user."
                )
        self += Keyword(
                  section="sync",
                  keyword="symdg",
                  rtype="symclone",
                  required=True,
                  text="Name of the symmetrix device group where the source and target devices are grouped."
                )
        self += Keyword(
                  section="sync",
                  keyword="precopy_timeout",
                  rtype="symclone",
                  required=True,
                  default=300,
                  text="Seconds to wait for a precopy (syncresync) to finish before returning with an error. In this case, the precopy proceeds normally, but the opensvc leftover actions must be retried. The precopy time depends on the amount of changes logged at the source, which is context-dependent. Tune to your needs."
                )
        self += Keyword(
                  section="sync",
                  keyword="symdevs",
                  rtype="symclone",
                  required=True,
                  at=True,
                  default=300,
                  text="Whitespace-separated list of devices to drive with this resource. Devices are specified as 'symmetrix identifier:symmetrix device identifier. Different symdevs can be setup on each node using the symdevs@nodename."
                )
        self += Keyword(
                  section="sync",
                  keyword="src",
                  rtype="dds",
                  required=True,
                  text="Points the origin of the snapshots to replicate from."
                )
        self += Keyword(
                  section="sync",
                  keyword="dst",
                  rtype="dds",
                  required=True,
                  text="Target file or block device. Optional. Defaults to src. Points the media to replay the binary-delta received from source node to. This media must have a size superior or equal to source."
                )
        self += Keyword(
                  section="sync",
                  keyword="target",
                  rtype="dds",
                  required=True,
                  candidates=['nodes', 'drpnodes', 'nodes drpnodes'],
                  text="Accepted values are 'drpnodes', 'nodes' or both, whitespace-separated. Points the target nodes to replay the binary-deltas on. Be warned that starting the service on a target node without a 'stop-syncupdate-start cycle, will break the synchronization, so this mode is usually restricted to drpnodes sync, and should not be used to replicate data between nodes with automated services failover."
                )
        self += Keyword(
                  section="sync",
                  keyword="snap_size",
                  rtype="dds",
                  text="Default to 10% of origin. In MB, rounded to physical extent boundaries by lvm tools. Size of the snapshots created by OpenSVC to extract binary deltas from. Opensvc creates at most 2 snapshots : one short-lived to gather changed data from, and one long-lived to gather changed chunks list from. Volume groups should have the necessary space always available."
                )
        self += Keyword(
                  section="vdisk",
                  keyword="path",
                  required=True,
                  at=True,
                  text="Path of the device or file used as a virtual machine disk. The path@nodename can be used to to set up different path on each node."
                )
        self += Keyword(
                  section="hb",
                  keyword="type",
                  required=True,
                  candidates=('OpenHA', 'LinuxHA'),
                  text="Specify the heartbeat driver to use."
                )
        self += Keyword(
                  section="hb",
                  keyword="name",
                  rtype="OpenHA",
                  text="Specify the service name used by the heartbeat. Defaults to the service name."
                )

if __name__ == "__main__":
    store = KeyDict()
    print store
    #print store.DEFAULT.app
    #print store['DEFAULT']
