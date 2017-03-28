import sys
import os
from rcGlobalEnv import rcEnv
from textwrap import TextWrapper
from rcNode import node_get_node_env

deprecated_keywords = {
  "DEFAULT.service_type": "env",
  "disk.lvm.vgname": "name",
  "disk.pool.poolname": "name",
  "disk.vg.vgname": "name",
  "sync.rsync.exclude": "options",
  "disk.zpool.poolname": "name",
}

deprecated_sections = {
  "disk.pool": ["disk", "zpool"],
  "drbd": ["disk", "drbd"],
  "loop": ["disk", "loop"],
  "pool": ["disk", "zpool"],
  "vdisk": ["disk", "vdisk"],
  "vmdg": ["disk", "vmdg"],
  "vg": ["disk", "vg"],
}

class MissKeyNoDefault(Exception):
     pass

class KeyInvalidValue(Exception):
     pass

class Keyword(object):
    def __init__(self, section, keyword,
                 rtype=None,
                 order=100,
                 required=False,
                 generic=False,
                 at=False,
                 default=None,
                 default_text=None,
                 validator=None,
                 candidates=None,
                 strict_candidates=True,
                 depends=[],
                 text="",
                 example="foo",
                 provisioning=False):
        self.section = section
        self.keyword = keyword
        if rtype is None or type(rtype) == list:
            self.rtype = rtype
        else:
            self.rtype = [rtype]
        self.order = order
        self.generic = generic
        self.at = at
        self.required = required
        self.default = default
        self.default_text = default_text
        self.candidates = candidates
        self.strict_candidates = strict_candidates
        self.depends = depends
        self.text = text
        self.example = example
        self.provisioning = provisioning

        if self.default_text is None:
            self.default_text = self.default

    def __lt__(self, o):
        return self.order < o.order

    def deprecated(self):
        if self.rtype is None:
            if self.section+"."+self.keyword in deprecated_keywords:
                return True
            else:
                return False
        for rtype in self.rtype:
            if self.section+"."+rtype+"."+self.keyword in deprecated_keywords:
                return True
        return False

    def template(self):
        if self.deprecated():
            return ''

        wrapper = TextWrapper(subsequent_indent="#%15s"%"", width=78)

        depends = " && ".join(map(lambda d: "%s in %s"%(d[0], d[1]), self.depends))
        if depends == "":
            depends = None

        if type(self.candidates) in (list, tuple, set):
            candidates = " | ".join(map(lambda x: str(x), self.candidates))
        else:
            candidates = str(self.candidates)
        if not self.strict_candidates:
            candidates += " ..."

        s = '#\n'
        s += "# keyword:       %s\n"%self.keyword
        s += "# ----------------------------------------------------------------------------\n"
        s += "#  required:     %s\n"%str(self.required)
        s += "#  provisioning: %s\n"%str(self.provisioning)
        s += "#  default:      %s\n"%str(self.default_text)
        s += "#  candidates:   %s\n"%candidates
        s += "#  depends:      %s\n"%depends
        s += "#  scopable:     %s\n"%str(self.at)
        s += '#\n'
        if self.text:
            wrapper = TextWrapper(subsequent_indent="#%9s"%"", width=78)
            s += wrapper.fill("#  desc:  "+self.text) + "\n"
        s += '#\n'
        if self.default_text is not None:
            val = self.default_text
        elif self.candidates and len(self.candidates) > 0:
            val = self.candidates[0]
        else:
            val = self.example
        s += ";" + self.keyword + " = " + str(val) + "\n\n"
        return s

    def __str__(self):
        if self.deprecated():
            return ''

        wrapper = TextWrapper(subsequent_indent="%15s"%"", width=78)

        depends = ""
        for d in self.depends:
            depends += "%s in %s\n"%(d[0], d[1])
        if depends == "":
            depends = None

        if type(self.candidates) in (list, tuple, set):
            candidates = " | ".join(map(lambda x: str(x), self.candidates))
        else:
            candidates = str(self.candidates)
        if not self.strict_candidates:
            candidates += " ..."

        s = ''
        s += "------------------------------------------------------------------------------\n"
        s += "section:        %s\n"%self.section
        s += "keyword:        %s\n"%self.keyword
        s += "------------------------------------------------------------------------------\n"
        s += "  required:     %s\n"%str(self.required)
        s += "  provisioning: %s\n"%str(self.provisioning)
        s += "  default:      %s\n"%str(self.default)
        s += "  candidates:   %s\n"%candidates
        s += "  depends:      %s\n"%depends
        s += "  scopable:     %s\n"%str(self.at)
        if self.text:
            s += wrapper.fill("  help:        "+self.text)
        if self.at:
            s += "\n\nPrefix the value with '@<node> ', '@nodes ', '@drpnodes ', '@flex_primary', '@drp_flex_primary' or '@encapnodes '\n"
            s += "to specify a scope-specific value.\n"
            s += "You will be prompted for new values until you submit an empty value.\n"
        s += "\n"
        return s

    def form(self, d):
        if self.deprecated():
            return

        # skip this form if dependencies are not met
        for d_keyword, d_value in self.depends:
            if d is None:
                return d
            if d_keyword not in d:
                return d
            if d[d_keyword] not in d_value:
                return d

        # print() the form
        print(self)

        # if we got a json seed, use its values as default
        # else use the Keyword object default
        if d and self.keyword in d:
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
            try:
                val = raw_input(self.keyword+default_prompt+"> ")
            except EOFError:
                break
            if len(val) == 0:
                if req_satisfied:
                    return d
                if default is None and self.required:
                    print("value required")
                    continue
                # keyword is optional, leave dictionary untouched
                return d
            elif self.at and val[0] == '@':
                l = val.split()
                if len(l) < 2:
                    print("invalid value")
                    continue
                val = ' '.join(l[1:])
                d[self.keyword+l[0]] = val
                req_satisfied = True
            else:
                d[self.keyword] = val
                req_satisfied = True
            if self.at:
                # loop for more key@<scope> = values
                print("More '%s' ? <enter> to step to the next parameter."%self.keyword)
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

    def template(self):
        k = self.getkey("type")
        if k is None:
            return self._template()
        if k.candidates is None:
            return self._template()
        s = ""
        if not k.strict_candidates:
            s += self._template()
        for t in k.candidates:
            s += self._template(t)
        return s

    def _template(self, rtype=None):
        section = self.section
        if self.section in deprecated_sections:
            return ""
        if rtype and self.section+"."+rtype in deprecated_sections:
            return ""
        dpath = rcEnv.pathdoc
        fpath = os.path.join(dpath, "template."+section+".conf")
        if rtype:
            section += ", type "+rtype
            fpath = os.path.join(dpath, "template."+self.section+"."+rtype+".conf")
        s = "#"*78 + "\n"
        s += "# %-74s #\n" % " "
        s += "# %-74s #\n" % section
        s += "# %-74s #\n" % " "
        s += "#"*78 + "\n\n"
        if section in ("DEFAULT", "env"):
            s += "[%s]\n" % self.section
        else:
            s += "[%s#0]\n" % self.section
        if rtype is not None:
            s += ";type = " + rtype + "\n\n"
        for keyword in sorted(self.getkeys(rtype)):
            s += keyword.template()
        for keyword in sorted(self.getprovkeys(rtype)):
            s += keyword.template()
        if rtype is not None:
            for keyword in sorted(self.getkeys()):
                if keyword.keyword == "type":
                    continue
                s += keyword.template()
        with open(fpath, "w") as f:
            f.write(s)
        return s

    def getkeys(self, rtype=None):
        if rtype is None:
            return [k for k in self.keywords if k.rtype is None and not k.provisioning]
        else:
            return [k for k in self.keywords if k.rtype and rtype in k.rtype and not k.provisioning]

    def getprovkeys(self, rtype=None):
        if rtype is None:
            return [k for k in self.keywords if k.rtype is None and k.provisioning]
        else:
            return [k for k in self.keywords if k.rtype and rtype in k.rtype and k.provisioning]

    def getkey(self, keyword, rtype=None):
        if '@' in keyword:
            l = keyword.split('@')
            if len(l) != 2:
                return None
            keyword, node = l
        if rtype:
            for k in self.keywords:
                if k.keyword == keyword and k.rtype and rtype in k.rtype:
                    return k
        else:
            for k in self.keywords:
                if k.keyword == keyword:
                    return k
        return None

class KeywordStore(dict):
    def __init__(self, provision=False):
        self.sections = {}
        self.provision = provision

    def __iadd__(self, o):
        if not isinstance(o, Keyword):
            return self
        o.top = self
        if o.section not in self.sections:
             self.sections[o.section] = Section(o.section)
        self.sections[o.section] += o
        return self

    def __getattr__(self, key):
        return self.sections[str(key)]

    def __getitem__(self, key):
        k = str(key)
        if k not in self.sections:
            return Section(k)
        return self.sections[str(key)]

    def __str__(self):
        s = ''
        for section in self.sections:
            s += str(self.sections[section])
        return s

    def print_templates(self):
        for section in sorted(self.sections.keys()):
            print(self.sections[section].template())

    def required_keys(self, section, rtype=None):
        if section not in self.sections:
            return []
        return [k for k in sorted(self.sections[section].getkeys(rtype)) if k.required is True]

    def purge_keywords_from_dict(self, d, section):
        if section == "env":
            return d
        if 'type' in d:
            rtype = d['type']
        else:
            rtype = None
        delete_keywords = []
        for keyword, value in d.items():
            key = self.sections[section].getkey(keyword)
            if key is None and rtype is not None:
                key = self.sections[section].getkey(keyword, rtype)
            if key is None:
                if keyword != "rtype":
                    print("Remove unknown keyword '%s' from section '%s'"%(keyword, section))
                    delete_keywords.append(keyword)

        for keyword in delete_keywords:
            del d[keyword]

        return d

    def update(self, rid, d):
        """ Given a resource dictionary, spot missing required keys
            and provide a new dictionary to merge populated by default
            values
        """
        import copy
        completion = copy.copy(d)

        # decompose rid into section and rtype
        if rid in ('DEFAULT', 'env'):
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
            if section == "env":
                break
            key = self.sections[section].getkey(keyword)
            if key is None and rtype is not None:
                key = self.sections[section].getkey(keyword, rtype)
            if key is None:
                continue
            if key.strict_candidates and key.candidates is not None and value not in key.candidates:
                print("'%s' keyword has invalid value '%s' in section '%s'"%(keyword, str(value), rid))
                raise KeyInvalidValue()

        # add missing required keys if they have a known default value
        for key in self.required_keys(section, rtype):
            fkey = ".".join((section, str(rtype), key.keyword))
            if fkey in deprecated_keywords:
                continue

            if key.keyword in d:
                continue
            if key.keyword in map(lambda x: x.split('@')[0], d.keys()):
                continue
            if key.default is None:
                sys.stderr.write("No default value for required key '%s' in section '%s'\n"%(key.keyword, rid))
                raise MissKeyNoDefault()
            print("Implicitely add [%s] %s = %s" % (rid, key.keyword, str(key.default)))
            completion[key.keyword] = key.default

        # purge unknown keywords and provisioning keywords
        completion = self.purge_keywords_from_dict(completion, section)

        return completion

    def form_sections(self, sections):
        wrapper = TextWrapper(subsequent_indent="%18s"%"", width=78)
        candidates = set(self.sections.keys()) - set(['DEFAULT'])

        print("------------------------------------------------------------------------------")
        print("Choose a resource type to add or a resource to edit.")
        print("Enter 'quit' to finish the creation.")
        print("------------------------------------------------------------------------------")
        print(wrapper.fill("resource types: "+', '.join(candidates)))
        print(wrapper.fill("resource ids:   "+', '.join(sections.keys())))
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
            try:
                section = self.form_sections(sections)
            except EOFError:
                break
            if section == "quit":
                break
            if '#' in section:
                rid = section
                section = section.split('#')[0]
            else:
                index = self.free_resource_index(section, sections)
                rid = '#'.join((section, str(index)))
            if section not in self.sections:
                 print("unsupported resource type")
                 continue
            for key in sorted(self.sections[section].getkeys()):
                if rid not in sections:
                    sections[rid] = {}
                sections[rid] = key.form(sections[rid])
            if 'type' in sections[rid]:
                specific_keys = self.sections[section].getkeys(rtype=sections[rid]['type'])
                if len(specific_keys) > 0:
                    print("\nKeywords specific to the '%s' driver\n"%sections[rid]['type'])
                for key in sorted(specific_keys):
                    if rid not in sections:
                        sections[rid] = {}
                    sections[rid] = key.form(sections[rid])

            # purge the provisioning keywords
            sections[rid] = self.purge_keywords_from_dict(sections[rid], section)

        return defaults, sections

class KeywordInteger(Keyword):
    def validator(self, val, d=None):
        try:
             val = int(val)
        except:
             return False
        return True


class KeywordProvision(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="provision",
                  keyword="provision",
                  default="no",
                  candidates=('yes', 'no'),
                  text="Say yes to provision this resource. Warning, provisioning implies destructive operations like formating."
                )

class KeywordLockTimeout(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="lock_timeout",
                  required=False,
                  order=10,
                  default=60,
                  text="The duration in seconds the agent wait for the action lock acquisition before aborting the action. The svcmgr --waitlock parameter overides this option."
                )

class KeywordMode(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="mode",
                  required=False,
                  order=10,
                  default="hosted",
                  candidates=["hosted", "sg", "vcs", "rhcs"],
                  text="The mode decides upon disposition OpenSVC takes to bring a service up or down : virtualized services need special actions to prepare and boot the container for example, which is not needed for 'hosted' services."
                )

class KeywordPkgName(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="pkg_name",
                  at=True,
                  required=False,
                  order=11,
                  depends=[('mode', ["vcs", "sg", "rhcs"])],
                  text="The wrapped cluster package name, as known to the cluster manager in charge."
                )

class KeywordRollback(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="rollback",
                  at=True,
                  required=False,
                  order=11,
                  default=True,
                  text="If set to False, the default rollback on action error is inhibited, leaving the service in its half-started state."
                )

class KeywordCompSchedule(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="comp_schedule",
                  at=True,
                  required=False,
                  order=11,
                  default="00:00-06:00@361",
                  text="The service compliance run schedule. See usr/share/doc/template.node.conf for the schedule syntax."
                )

class KeywordStatusSchedule(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="status_schedule",
                  at=True,
                  required=False,
                  order=11,
                  default="@10",
                  text="The service status evaluation schedule. See usr/share/doc/template.node.conf for the schedule syntax."
                )

class KeywordDefaultSyncSchedule(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="sync_schedule",
                  at=True,
                  required=False,
                  order=11,
                  default="04:00-06:00@121",
                  text="The default sync resources schedule. See usr/share/doc/template.node.conf for the schedule syntax."
                )

class KeywordResinfoSchedule(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="resinfo_schedule",
                  at=True,
                  required=False,
                  order=11,
                  default="@60",
                  text="The service resource info push schedule. See usr/share/doc/template.node.conf for the schedule syntax."
                )

class KeywordMonitorSchedule(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="monitor_schedule",
                  at=True,
                  required=False,
                  order=11,
                  default="@1",
                  text="The service resource monitor schedule. See usr/share/doc/template.node.conf for the schedule syntax."
                )

class KeywordPushSchedule(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="push_schedule",
                  at=True,
                  required=False,
                  order=11,
                  default="00:00-06:00@361",
                  text="The service configuration emission to the collector schedule. See usr/share/doc/template.node.conf for the schedule syntax."
                )

class KeywordFlexPrimary(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="flex_primary",
                  at=True,
                  required=False,
                  order=11,
                  depends=[('cluster_type', ["flex"])],
                  default_text="<first node of the nodes parameter>",
                  text="The node in charge of syncing the other nodes. --cluster actions on the flex_primary are execute on all peer nodes (ie, not drpnodes)."
                )

class KeywordDrpFlexPrimary(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="drp_flex_primary",
                  at=True,
                  required=False,
                  order=11,
                  depends=[('cluster_type', ["flex"])],
                  default_text="<first node of the drpnodes parameter>",
                  text="The drpnode in charge of syncing the other drpnodes. --cluster actions on the drp_flex_primary are execute on all drpnodes (ie, not pri nodes)."
                )

class KeywordDockerExe(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="docker_exe",
                  at=True,
                  required=False,
                  order=12,
                  text="If you have multiple docker versions installed and want the service to stick to a version whatever the PATH definition, you should set this parameter to the full path to the docker executable.",
                  example="/usr/bin/docker-1.8"
                )

class KeywordDockerDataDir(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="docker_data_dir",
                  at=True,
                  required=False,
                  order=12,
                  text="If the service has docker-type container resources and docker_daemon_private is set to True, the service handles the startup of a private docker daemon. Its socket is <pathvar>/<svcname>/docker.sock, and its data directory must be specified using this parameter. This organization is necessary to enable service relocalization.",
                  example="/srv/svc1/data/docker"
                )

class KeywordDockerDaemonPrivate(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="docker_daemon_private",
                  at=True,
                  required=False,
                  default=True,
                  order=11,
                  text="If set to False, this service will use the system's shared docker daemon instance. This is parameter is forced to False on non-Linux systems.",
                  example="True"
                )

class KeywordDockerDaemonArgs(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="docker_daemon_args",
                  at=True,
                  required=False,
                  order=12,
                  text="If the service has docker-type container resources, the service handles the startup of a private docker daemon. OpenSVC sets the socket and data dir parameters. Admins can set extra parameters using this keyword. For example, it can be useful to set the --ip parameter for a docker registry service.",
                  example="--ip 1.2.3.4"
                )

class KeywordSubsetParallel(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="subset",
                  keyword="parallel",
                  at=True,
                  candidates=(True, False),
                  default=False,
                  text="If set to true, actions are executed in parallel amongst the subset member resources.",
                  required=False,
                  order=2
                )

class KeywordStonithType(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="stonith",
                  keyword="type",
                  at=True,
                  candidates=["ilo", "callout"],
                  text="The type of stonith.",
                  required=True,
                  order=1
                )

class KeywordStonithTarget(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="stonith",
                  keyword="target",
                  at=True,
                  text="The server management console to pass the stonith command to, as defined in the corresponding auth.conf section title.",
                  required=True,
                  order=2
                )

class KeywordStonithCalloutCmd(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="stonith",
                  rtype="callout",
                  at=True,
                  keyword="cmd",
                  text="The command to execute on target to stonith.",
                  required=True,
                  order=3
                )

class KeywordContainerType(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="type",
                  at=True,
                  candidates=rcEnv.vt_supported,
                  text="The type of container.",
                  required=True,
                  order=1
                )

class KeywordContainerZoneDeleteOnStop(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  rtype="zone",
                  keyword="delete_on_stop",
                  at=True,
                  candidates=(True, False),
                  text="If set to true, the zone configuration is deleted after a resource stop. The agent maintains an export of the configuration for the next start. This export is replicated to the other nodes and drp nodes so they can take over the zone even if it is completely hosted on a shared disk.",
                  default=False,
                  required=False,
                  order=1
                )

class KeywordDockerRunImage(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="run_image",
                  at=True,
                  order=9,
                  required=False,
                  rtype="docker",
                  text="The docker image pull, and run the container with.",
                  example="83f2a3dd2980"
                )

class KeywordDockerRunCommand(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="run_command",
                  at=True,
                  order=1,
                  required=False,
                  rtype="docker",
                  text="The command to execute in the docker container on run.",
                  example="/opt/tomcat/bin/catalina.sh"
                )

class KeywordDockerRunArgs(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="run_args",
                  at=True,
                  order=2,
                  required=False,
                  rtype="docker",
                  text="Extra arguments to pass to the docker run command, like volume and port mappings.",
                  example="-v /opt/docker.opensvc.com/vol1:/vol1:rw -p 37.59.71.25:8080:8080"
                )

class KeywordDockerRunSwarm(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="run_swarm",
                  at=True,
                  order=2,
                  required=False,
                  rtype="docker",
                  text="The ip:port at which the swarm manager listens. If swarm is not used, this parameter should not be used, in which case, the service-private dockerd is used through its unix socket.",
                  example="1.2.3.4:2374"
                )

class KeywordVirtinst(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="virtinst",
                  rtype=["kvm", "xen", "ovm"],
                  text="The virt-install command to use to create the container.",
                  required=True,
                  provisioning=True
                )

class KeywordSnap(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="snap",
                  rtype=["kvm", "xen", "ovm", "zone", "esx"],
                  text="The target snapshot/clone full path containing the new container disk files.",
                  required=True,
                  provisioning=True
                )

class KeywordSnapof(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="snapof",
                  rtype=["kvm", "xen", "ovm", "zone", "esx"],
                  text="The snapshot origin full path containing the reference container disk files.",
                  required=True,
                  provisioning=True
                )

class KeywordContainerOrigin(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="container_origin",
                  rtype="zone",
                  text="The origin container having the reference container disk files.",
                  required=True,
                  provisioning=True
                )

class KeywordJailRoot(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="jailroot",
                  rtype="jail",
                  text="Sets the root fs directory of the container",
                  required=True,
                  provisioning=False
                )

class KeywordLxcCf(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="cf",
                  rtype="lxc",
                  text="Defines a lxc configuration file in a non-standard location.",
                  required=False,
                  provisioning=True,
                  example="/srv/mycontainer/config"
                )

class KeywordRootfs(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="rootfs",
                  rtype=["lxc", "vz", "zone"],
                  text="Sets the root fs directory of the container",
                  required=True,
                  provisioning=True
                )

class KeywordTemplate(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="template",
                  rtype=["lxc", "vz", "zone"],
                  text="Sets the url of the template unpacked into the container root fs.",
                  required=True,
                  provisioning=True
                )

class KeywordVmName(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="name",
                  at=True,
                  order=2,
                  rtype=rcEnv.vt_supported,
                  text="This need to be set if the virtual machine name is different from the service name."
                )

class KeywordContainerRcmd(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="rcmd",
                  at=True,
                  order=2,
                  rtype="lxc",
                  example="lxc-attach -e -n osvtavnprov01 -- ",
                  text="An container remote command override the agent default"
                )

class KeywordOsvcRootPath(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="osvc_root_path",
                  at=True,
                  order=2,
                  rtype=rcEnv.vt_supported,
                  example="/opt/opensvc",
                  text="If the OpenSVC agent is installed via package in the container, this parameter must not be set or set to 'None'. Else the value can be set to the fullpath hosting the agent installed from sources."
                )

class KeywordGuestos(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="guestos",
                  at=True,
                  rtype=rcEnv.vt_supported,
                  order=11,
                  candidates=["unix", "windows"],
                  default=None,
                  text="The operating system in the virtual machine."
                )

class KeywordJailIps(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="ips",
                  at=True,
                  rtype="jail",
                  order=11,
                  text="The ipv4 addresses of the jail."
                )

class KeywordJailIp6s(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="ip6s",
                  at=True,
                  rtype="jail",
                  order=11,
                  text="The ipv6 addresses of the jail."
                )

class KeywordSharedIpGroup(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="shared_ip_group",
                  at=True,
                  order=11,
                  rtype=rcEnv.vt_cloud,
                  text="The cloud shared ip group name to allocate a public ip from."
                )

class KeywordSize(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="size",
                  at=True,
                  order=11,
                  rtype=rcEnv.vt_cloud,
                  text="The cloud vm size, as known to the cloud manager. Example: tiny."
                )

class KeywordKeyName(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="key_name",
                  at=True,
                  order=11,
                  rtype=rcEnv.vt_cloud,
                  text="The key name, as known to the cloud manager, to trust in the provisioned vm."
                )

class KeywordSrpPrmCores(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="prm_cores",
                  order=11,
                  rtype="srp",
                  default=1,
                  provisioning=True,
                  text="The number of core to bind the SRP container to."
                )

class KeywordSrpIp(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="ip",
                  at=True,
                  order=11,
                  rtype="srp",
                  provisioning=True,
                  text="The ip name or addr used to create the SRP container."
                )

class KeywordSrpRootpath(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="rootpath",
                  at=True,
                  order=11,
                  rtype="srp",
                  provisioning=True,
                  text="The path of the SRP container root filesystem."
                )

class KeywordCloudId(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="cloud_id",
                  at=True,
                  order=11,
                  rtype=rcEnv.vt_cloud,
                  text="The cloud id as configured in node.conf. Example: cloud#1."
                )

class KeywordVmUuid(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="container",
                  keyword="uuid",
                  at=True,
                  order=11,
                  rtype="ovm",
                  text="The virtual machine unique identifier used to pass commands on the VM."
                )

class KeywordAntiAffinity(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="anti_affinity",
                  at=True,
                  order=15,
                  required=False,
                  default=None,
                  text="A whitespace separated list of services this service is not allowed to be started on the same node. The svcmgr --ignore-affinity option can be set to override this policy.",
                  example="svc1 svc2"
                )

class KeywordPrKey(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="prkey",
                  order=15,
                  at=True,
                  required=False,
                  text="Defines a specific default persistent reservation key for the service. A prkey set in a resource takes priority. If no prkey is specified in the service nor in the DEFAULT section, the prkey in node.conf is used. If node.conf has no prkey set, the hostid is computed and written in node.conf."
                )

class KeywordNoPreemptAbort(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="no_preempt_abort",
                  order=15,
                  at=True,
                  required=False,
                  candidates=(True, False),
                  default=False,
                  text="If set to 'true', OpenSVC will preempt scsi reservation with a preempt command instead of a preempt and and abort. Some scsi target implementations do not support this last mode (esx). If set to 'false' or not set, 'no_preempt_abort' can be activated on a per-resource basis."
                )

class KeywordCluster(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="cluster",
                  order=15,
                  required=False,
                  default=None,
                  text="The symbolic name of the cluster. Used to label shared disks represented to tiers-2 consumers like containers.",
                  example="cluster1"
                )

class KeywordShowDisabled(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="show_disabled",
                  at=True,
                  order=15,
                  required=False,
                  default=True,
                  candidates=[True, False],
                  text="Specifies if the disabled resources must be included in the print status and json status output."
                )

class KeywordClusterType(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="cluster_type",
                  at=True,
                  order=15,
                  required=False,
                  default="failover",
                  candidates=["failover", "flex", "autoflex"],
                  text="failover: the service is allowed to be up on one node at a time. allactive: the service must be up on all nodes. flex: the service can be up on n out of m nodes (n <= m), n/m must be in the [flex_min_nodes, flex_max_nodes] range. autoflex: same as flex, but charge the collector to start the service on passive nodes when the average %cpu usage on active nodes > flex_cpu_high_threshold and stop the service on active nodes when the average %cpu usage on active nodes < flex_cpu_low_threshold."
                )

class KeywordFlexMinNodes(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="flex_min_nodes",
                  order=16,
                  required=False,
                  default=1,
                  depends=[('cluster_type', ['flex', 'autoflex'])],
                  text="Minimum number of active nodes in the cluster. Below this number alerts are raised by the collector, and the collector won't stop any more service instances."
                )

class KeywordFlexMaxNodes(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="flex_max_nodes",
                  order=16,
                  required=False,
                  default=10,
                  depends=[('cluster_type', ['flex', 'autoflex'])],
                  text="Maximum number of active nodes in the cluster. Above this number alerts are raised by the collector, and the collector won't start any more service instances. 0 means unlimited."
                )

class KeywordFlexCpuMinThreshold(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="flex_cpu_min_threshold",
                  order=16,
                  required=False,
                  default=10,
                  depends=[('cluster_type', ['flex', 'autoflex'])],
                  text="Average CPU usage across the active cluster nodes below which the collector raises alerts and decides to stop service instances with autoflex cluster type."
                )

class KeywordFlexCpuMaxThreshold(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="flex_cpu_max_threshold",
                  order=16,
                  required=False,
                  default=70,
                  depends=[('cluster_type', ['flex', 'autoflex'])],
                  text="Average CPU usage across the active cluster nodes above which the collector raises alerts and decides to start new service instances with autoflex cluster type."
                )

class KeywordServiceType(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="service_type",
                  order=15,
                  required=False,
                  candidates=rcEnv.allowed_svc_envs,
                  text="A non-PRD service can not be brought up on a PRD node, but a PRD service can be startup on a non-PRD node (in a DRP situation). The default value is the node env."
                )

class KeywordServiceEnv(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="env",
                  order=15,
                  required=True,
                  default=node_get_node_env(),
                  default_text="<same as node env>",
                  candidates=rcEnv.allowed_svc_envs,
                  text="A non-PRD service can not be brought up on a PRD node, but a PRD service can be startup on a non-PRD node (in a DRP situation). The default value is the node env."
                )

class KeywordNodes(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="nodes",
                  order=20,
                  at=True,
                  required=True,
                  default=rcEnv.nodename,
                  default_text="<hostname of the current node>",
                  text="List of cluster local nodes able to start the service.  Whitespace separated."
                )

class KeywordAutostartNode(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="autostart_node",
                  order=20,
                  at=True,
                  required=False,
                  default=rcEnv.nodename,
                  default_text="<hostname of the current node>",
                  text="A whitespace-separated list subset of 'nodes'. Defines the nodes where the service will try to start on upon node reboot. On a failover cluster there should only be one autostart node and the start-up will fail if the service is already up on another node though. If not specified, the service will never be started at node boot-time, which is rarely the expected behaviour."
                )

class KeywordDrpnode(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="drpnode",
                  order=21,
                  at=True,
                  text="The backup node where the service is activated in a DRP situation. This node is also a data synchronization target for 'sync' resources.",
                  example="node1"
                )

class KeywordDrpnodes(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="drpnodes",
                  order=21,
                  at=True,
                  text="Alternate backup nodes, where the service could be activated in a DRP situation if the 'drpnode' is not available. These nodes are also data synchronization targets for 'sync' resources.",
                  example="node1 node2"
                )

class KeywordEncapnodes(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="encapnodes",
                  order=21,
                  text="The list of containers handled by this service and with an OpenSVC agent installed to handle the encapsulated resources. With this parameter set, parameters can be scoped with the @encapnodes suffix.",
                  example="vm1 vm2"
                )

class KeywordApp(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="app",
                  order=24,
                  default="DEFAULT",
                  text="Used to identify who is responsible for is service, who is billable and provides a most useful filtering key. Better keep it a short code."
                )

class KeywordComment(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="comment",
                  order=25,
                  text="Helps users understand the role of the service, which is nice to on-call support people having to operate on a service they are not usually responsible for."
                )

class KeywordScsireserv(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="scsireserv",
                  at=True,
                  order=25,
                  default=False,
                  candidates=(True, False),
                  text="If set to 'true', OpenSVC will try to acquire a type-5 (write exclusive, registrant only) scsi3 persistent reservation on every path to disks of every disk group attached to this service. Existing reservations are preempted to not block service start-up. If the start-up was not legitimate the data are still protected from being written over from both nodes. If set to 'false' or not set, 'scsireserv' can be activated on a per-resource basis."
                )

class KeywordBwlimit(KeywordInteger):
    def __init__(self):
        KeywordInteger.__init__(
                  self,
                  section="DEFAULT",
                  keyword="bwlimit",
                  order=25,
                  text="Bandwidth limit in KB applied to all rsync transfers. Leave empty to enforce no limit.",
                  example="3000"
                )

class KeywordSyncInterval(KeywordInteger):
    def __init__(self):
        KeywordInteger.__init__(
                  self,
                  section="DEFAULT",
                  keyword="sync_interval",
                  order=26,
                  default=121,
                  text="Set the minimum delay between syncs in minutes. If a sync is triggered through crond or manually, it is skipped if last sync occurred less than 'sync_min_delay' ago. The mecanism is enforced by a timestamp created upon each sync completion in <pathvar>/sync/[service]![dst]"
                )

class KeywordSyncMaxDelay(KeywordInteger):
    def __init__(self):
        KeywordInteger.__init__(
                  self,
                  section="DEFAULT",
                  keyword="sync_max_delay",
                  order=27,
                  default=1440,
                  text="Unit is minutes. This sets to delay above which the sync status of the resource is to be considered down. Should be set according to your application service level agreement. The cron job frequency should be set between 'sync_min_delay' and 'sync_max_delay'"
                )

class KeywordPresnapTrigger(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="presnap_trigger",
                  order=28,
                  text="Define a command to run before creating snapshots. This is most likely what you need to use plug a script to put you data in a coherent state (alter begin backup and the like).",
                  example="/srv/svc1/etc/init.d/pre_snap.sh"
                )

class KeywordPostsnapTrigger(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="postsnap_trigger",
                  order=29,
                  text="Define a command to run after snapshots are created. This is most likely what you need to use plug a script to undo the actions of 'presnap_trigger'.",
                  example="/srv/svc1/etc/init.d/post_snap.sh"
                )

class KeywordMonitorAction(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="monitor_action",
                  at=True,
                  order=30,
                  default=None,
                  candidates=("reboot", "crash", "freezestop"),
                  text="The action to take when a monitored resource is not up nor standby up, and if the resource restart procedure has failed.",
                  example="reboot"
                )

class KeywordCreatePg(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="DEFAULT",
                  keyword="create_pg",
                  order=30,
                  default=True,
                  candidates=(True, False),
                  text="Use process containers when possible. Containers allow capping memory, swap and cpu usage per service. Lxc containers are naturally containerized, so skip containerization of their startapp."
                )

class KeywordPgCpus(KeywordInteger):
    def __init__(self):
        KeywordInteger.__init__(
                  self,
                  section="DEFAULT",
                  keyword="pg_cpus",
                  order=31,
                  depends=[('create_pg', [True])],
                  text="Allow service process to bind only the specified cpus. Cpus are specified as list or range : 0,1,2 or 0-2",
                  example="0-2"
                )

class KeywordPgMems(KeywordInteger):
    def __init__(self):
        KeywordInteger.__init__(
                  self,
                  section="DEFAULT",
                  keyword="pg_mems",
                  order=31,
                  depends=[('create_pg', [True])],
                  text="Allow service process to bind only the specified memory nodes. Memory nodes are specified as list or range : 0,1,2 or 0-2",
                  example="0-2"
                )

class KeywordPgCpuShare(KeywordInteger):
    def __init__(self):
        KeywordInteger.__init__(
                  self,
                  section="DEFAULT",
                  keyword="pg_cpu_shares",
                  order=31,
                  depends=[('create_pg', [True])],
                  text="Kernel default value is used, which usually is 1024 shares. In a cpu-bound situation, ensure the service does not use more than its share of cpu ressource. The actual percentile depends on shares allowed to other services.",
                  example="512"
                )

class KeywordPgCpuQuota(KeywordInteger):
    def __init__(self):
        KeywordInteger.__init__(
                  self,
                  section="DEFAULT",
                  keyword="pg_cpu_quota",
                  order=31,
                  depends=[('create_pg', [True])],
                  text="The percent ratio of one core to allocate to the process group if % is specified, else the absolute value to set in the process group parameter. For example, on Linux cgroups, -1 means unlimited, and a positive absolute value means the number of microseconds to allocate each period. 50%@all means 50% of all cores, and 50%@2 means 50% of two cores.",
                  example="50%@all"
                )

class KeywordPgMemOomControl(KeywordInteger):
    def __init__(self):
        KeywordInteger.__init__(
                  self,
                  section="DEFAULT",
                  keyword="pg_mem_oom_control",
                  order=31,
                  depends=[('create_pg', [True])],
                  text="A flag (0 or 1) that enables or disables the Out of Memory killer for a cgroup. If enabled (0), tasks that attempt to consume more memory than they are allowed are immediately killed by the OOM killer. The OOM killer is enabled by default in every cgroup using the memory subsystem; to disable it, write 1.",
                  example="1"
                )

class KeywordPgMemLimit(KeywordInteger):
    def __init__(self):
        KeywordInteger.__init__(
                  self,
                  section="DEFAULT",
                  keyword="pg_mem_limit",
                  order=31,
                  depends=[('create_pg', [True])],
                  text="Ensures the service does not use more than specified memory (in bytes). The Out-Of-Memory killer get triggered in case of tresspassing.",
                  example="512000000"
                )

class KeywordPgVmemLimit(KeywordInteger):
    def __init__(self):
        KeywordInteger.__init__(
                  self,
                  section="DEFAULT",
                  keyword="pg_vmem_limit",
                  order=31,
                  depends=[('create_pg', [True])],
                  text="Ensures the service does not use more than specified memory+swap (in bytes). The Out-Of-Memory killer get triggered in case of tresspassing. The specified value must be greater than pg_mem_limit.",
                  example="1024000000"
                )

class KeywordPgMemSwappiness(KeywordInteger):
    def __init__(self):
        KeywordInteger.__init__(
                  self,
                  section="DEFAULT",
                  keyword="pg_mem_swappiness",
                  order=31,
                  depends=[('create_pg', [True])],
                  text="Set a swappiness value for the process group.",
                  example="40"
                )

class KeywordPgBlkioWeight(KeywordInteger):
    def __init__(self):
        KeywordInteger.__init__(
                  self,
                  section="DEFAULT",
                  keyword="pg_blkio_weight",
                  order=31,
                  depends=[('create_pg', [True])],
                  text="Block IO relative weight. Value: between 10 and 1000. Kernel default: 1000.",
                  example="50"
                )

class KeywordAppScript(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="app",
                  keyword="script",
                  at=True,
                  order=9,
                  required=True,
                  text="Full path to the app launcher script. Or its basename if the file is hosted in the <svcname>.d path."
                )

class KeywordAppTimeout(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="app",
                  keyword="timeout",
                  order=9,
                  at=True,
                  required=False,
                  text="Wait for <n> seconds max before declaring the app launcher action a failure. If no timeout is specified, the agent waits indefinitely for the app launcher to return. The timeout parameter can be coupled with optional=True to not abort a service start when an app launcher did not return.",
                  example="180"
                )

class KeywordAppStart(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="app",
                  keyword="start",
                  at=True,
                  order=10,
                  required=False,
                  text="Start up sequencing number."
                )

class KeywordAppStop(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="app",
                  keyword="stop",
                  at=True,
                  order=11,
                  required=False,
                  text="Stop sequencing number."
                )

class KeywordAppCheck(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="app",
                  keyword="check",
                  at=True,
                  order=11,
                  required=False,
                  text="Check up sequencing number."
                )

class KeywordAppInfo(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="app",
                  keyword="info",
                  at=True,
                  order=12,
                  required=False,
                  text="Info up sequencing number."
                )

class KeywordSyncType(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="type",
                  order=10,
                  required=True,
                  candidates=("rsync", "docker", "dds", "netapp", "symsrdfs", "zfs", "btrfs", "symclone", "symsnap", "hp3par", "hp3parsnap", "evasnap", "ibmdssnap", "dcssnap", "dcsckpt", "necismsnap", "zfssnap", "btrfssnap", "rados", "s3"),
                  default="rsync",
                  text="Point a sync driver to use."
                )

class KeywordSyncDockerTarget(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="target",
                  rtype="docker",
                  order=11,
                  at=True,
                  required=True,
                  default=None,
                  candidates=["nodes", "drpnodes", "nodes drpnodes"],
                  text="Destination nodes of the sync."
                )

class KeywordSyncS3Snar(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="snar",
                  rtype="s3",
                  order=10,
                  at=True,
                  required=False,
                  example="/srv/mysvc/var/sync.1.snar",
                  text="The GNU tar snar file full path. The snar file stored the GNU tar metadata needed to do an incremental tarball. If the service fails over shared disks the snar file should be stored there, so the failover node can continue the incremental cycle."
                )

class KeywordSyncS3Src(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="src",
                  rtype="s3",
                  order=10,
                  at=True,
                  required=True,
                  example="/srv/mysvc/tools /srv/mysvc/apps*",
                  text="Source globs as passed as paths to archive to a tar command."
                )

class KeywordSyncS3Options(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="options",
                  rtype="s3",
                  order=10,
                  at=True,
                  required=False,
                  example="--exclude *.pyc",
                  text="Options passed to GNU tar for archiving."
                )

class KeywordSyncS3Bucket(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="bucket",
                  rtype="s3",
                  order=10,
                  at=True,
                  required=True,
                  example="opensvc-myapp",
                  text="The name of the S3 bucket to upload the backup to."
                )

class KeywordSyncS3FullSchedule(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="full_schedule",
                  rtype="s3",
                  order=10,
                  at=True,
                  required=True,
                  example="@1441 sun",
                  default="@1441 sun",
                  text="The schedule of full backups. sync_update actions are triggered according to the resource 'schedule' parameter, and do a full backup if the current date matches the 'full_schedule' parameter or an incremental backup otherwise."
                )

class KeywordSyncZfsSnapRecursive(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="recursive",
                  rtype="zfssnap",
                  order=10,
                  at=True,
                  required=False,
                  example="true",
                  default=True,
                  text="Set to true to snap recursively the datasets."
                )

class KeywordSyncZfsSnapName(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="name",
                  rtype="zfssnap",
                  order=10,
                  at=True,
                  required=False,
                  example="weekly",
                  text="A name included in the snapshot name to avoid retention conflicts between multiple zfs snapshot resources. A full snapshot name is formatted as <subvol>.<name>.snap.<datetime>. Example: data.weekly.snap.2016-03-09.10:09:52"
                )

class KeywordSyncZfsSnapDataset(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="dataset",
                  rtype="zfssnap",
                  order=10,
                  at=True,
                  required=True,
                  example="svc1fs/data svc1fs/log",
                  text="A whitespace separated list of datasets to snapshot."
                )

class KeywordSyncZfsSnapKeep(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="keep",
                  rtype="zfssnap",
                  order=10,
                  at=True,
                  required=True,
                  default=3,
                  example="3",
                  text="The maximum number of snapshots to retain."
                )

class KeywordSyncBtrfsSnapName(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="name",
                  rtype="btrfssnap",
                  order=10,
                  at=True,
                  required=False,
                  example="weekly",
                  text="A name included in the snapshot name to avoid retention conflicts between multiple btrfs snapshot resources. A full snapshot name is formatted as <subvol>.<name>.snap.<datetime>. Example: data.weekly.snap.2016-03-09.10:09:52"
                )

class KeywordSyncBtrfsSnapSubvol(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="subvol",
                  rtype="btrfssnap",
                  order=10,
                  at=True,
                  required=True,
                  example="svc1fs:data svc1fs:log",
                  text="A whitespace separated list of <label>:<subvol> to snapshot."
                )

class KeywordSyncBtrfsSnapKeep(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="keep",
                  rtype="btrfssnap",
                  order=10,
                  at=True,
                  required=True,
                  default=3,
                  example="3",
                  text="The maximum number of snapshots to retain."
                )

class KeywordSyncBtrfsSrc(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="src",
                  rtype="btrfs",
                  order=10,
                  at=True,
                  required=True,
                  text="Source subvolume of the sync."
                )

class KeywordSyncBtrfsDst(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="dst",
                  rtype="btrfs",
                  order=10,
                  at=True,
                  required=True,
                  text="Destination subvolume of the sync."
                )

class KeywordSyncBtrfsTarget(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="target",
                  rtype="btrfs",
                  order=11,
                  at=True,
                  required=True,
                  default=None,
                  candidates=["nodes", "drpnodes", "nodes drpnodes"],
                  text="Destination nodes of the sync."
                )

class KeywordSyncBtrfsRecursive(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="recursive",
                  rtype="btrfs",
                  order=10,
                  at=True,
                  required=False,
                  default=False,
                  candidates=[True, False],
                  text="Also replicate subvolumes in the src tree."
                )

class KeywordSyncZfsSrc(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="src",
                  rtype="zfs",
                  order=10,
                  at=True,
                  required=True,
                  text="Source dataset of the sync."
                )

class KeywordSyncZfsDst(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="dst",
                  rtype="zfs",
                  order=11,
                  at=True,
                  required=True,
                  text="Destination dataset of the sync."
                )

class KeywordSyncZfsTarget(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="target",
                  rtype="zfs",
                  order=12,
                  required=True,
                  candidates=['nodes', 'drpnodes', 'nodes drpnodes'],
                  text="Describes which nodes should receive this data sync from the PRD node where the service is up and running. SAN storage shared 'nodes' must not be sync to 'nodes'. SRDF-like paired storage must not be sync to 'drpnodes'."
                )

class KeywordSyncZfsRecursive(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="recursive",
                  rtype="zfs",
                  at=True,
                  order=13,
                  default=True,
                  candidates=(True, False),
                  text="Describes which nodes should receive this data sync from the PRD node where the service is up and running. SAN storage shared 'nodes' must not be sync to 'nodes'. SRDF-like paired storage must not be sync to 'drpnodes'."
                )

class KeywordSyncZfsTags(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="tags",
                  rtype="zfs",
                  at=True,
                  text="The zfs sync resource supports the 'delay_snap' tag. This tag is used to delay the snapshot creation just before the sync, thus after 'postsnap_trigger' execution. The default behaviour (no tags) is to group all snapshots creation before copying data to remote nodes, thus between 'presnap_trigger' and 'postsnap_trigger'."
                )

class KeywordSyncRsyncSrc(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="src",
                  rtype="rsync",
                  order=10,
                  at=True,
                  required=True,
                  text="Source of the sync. Can be a whitespace-separated list of files or dirs passed as-is to rsync. Beware of the meaningful ending '/'. Refer to the rsync man page for details."
                )

class KeywordSyncRsyncDst(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="dst",
                  rtype="rsync",
                  order=11,
                  required=True,
                  text="Destination of the sync. Beware of the meaningful ending '/'. Refer to the rsync man page for details."
                )

class KeywordSyncRsyncTags(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="tags",
                  at=True,
                  rtype="rsync",
                  text="The sync resource supports the 'delay_snap' tag. This tag is used to delay the snapshot creation just before the rsync, thus after 'postsnap_trigger' execution. The default behaviour (no tags) is to group all snapshots creation before copying data to remote nodes, thus between 'presnap_trigger' and 'postsnap_trigger'."
                )

class KeywordSyncRsyncExclude(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="exclude",
                  rtype="rsync",
                  at=True,
                  text="A whitespace-separated list of --exclude params passed unchanged to rsync. The 'options' keyword is preferred now."
                )

class KeywordSyncRsyncOptions(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="options",
                  at=True,
                  rtype="rsync",
                  text="A whitespace-separated list of params passed unchanged to rsync. Typical usage is ACL preservation activation."
                )

class KeywordSyncRsyncTarget(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="target",
                  rtype="rsync",
                  order=12,
                  required=True,
                  candidates=['nodes', 'drpnodes', 'nodes drpnodes'],
                  text="Describes which nodes should receive this data sync from the PRD node where the service is up and running. SAN storage shared 'nodes' must not be sync to 'nodes'. SRDF-like paired storage must not be sync to 'drpnodes'."
                )

class KeywordSyncRsyncSnap(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="snap",
                  rtype="rsync",
                  at=True,
                  order=14,
                  candidates=(True, False),
                  default=False,
                  text="If set to true, OpenSVC will try to snapshot the first snapshottable parent of the source of the sync and try to sync from the snap."
                )

class KeywordSyncRsyncDstfs(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="dstfs",
                  rtype="rsync",
                  order=13,
                  text="If set to a remote mount point, OpenSVC will verify that the specified mount point is really hosting a mounted FS. This can be used as a safety net to not overflow the parent FS (may be root)."
                )

class KeywordSyncRsyncBwlimit(KeywordInteger):
    def __init__(self):
        KeywordInteger.__init__(
                  self,
                  section="sync",
                  keyword="bwlimit",
                  rtype="rsync",
                  text="Bandwidth limit in KB applied to this rsync transfer. Leave empty to enforce no limit. Takes precedence over 'bwlimit' set in [DEFAULT]."
                )

class KeywordSyncSchedule(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="schedule",
                  default=None,
                  at=True,
                  text="Set the this resource synchronization schedule. See usr/share/doc/node.conf for the schedule syntax reference.",
                  example='["00:00-01:00@61 mon", "02:00-03:00@61 tue-sun"]'
                )

class KeywordSyncSyncMaxDelay(KeywordInteger):
    def __init__(self):
        KeywordInteger.__init__(
                  self,
                  section="sync",
                  keyword="sync_max_delay",
                  default=1440,
                  text="Unit is minutes. This sets to delay above which the sync status of the resource is to be considered down. Should be set according to your application service level agreement. The cron job frequency should be set between 'sync_min_delay' and 'sync_max_delay'."
                )

class KeywordIpIpname(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  keyword="ipname",
                  order=12,
                  at=True,
                  required=False,
                  text="The DNS name or IP address of the ip resource. Can be different from one node to the other, in which case '@nodename' can be specified. This is most useful to specify a different ip when the service starts in DRP mode, where subnets are likely to be different than those of the production datacenter. With the amazon driver, the special <allocate> value tells the provisioner to assign a new private address."
                )

class KeywordIpDnsNameSuffix(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  keyword="dns_name_suffix",
                  order=12,
                  at=True,
                  required=False,
                  text="Add the value as a suffix to the DNS record name. The record created is thus formatted as <svcname>-<dns_name_suffix>.<app>.<managed zone>."
                )

class KeywordIpNetwork(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  keyword="network",
                  order=12,
                  at=True,
                  required=False,
                  example="10.0.0.0",
                  text="The network, in dotted notation, from where the ip provisioner allocates. Also used by the docker ip driver to delete the network route if del_net_route is set to true.",
                )

class KeywordIpDnsUpdate(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  keyword="dns_update",
                  order=12,
                  at=True,
                  default=False,
                  required=False,
                  candidates=[True, False],
                  text="Setting this parameter triggers a DNS update. The record created is formatted as <svcname>.<app>.<managed zone>, unless dns_record_name is specified."
                )

class KeywordIpZone(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  keyword="zone",
                  order=12,
                  at=True,
                  required=False,
                  text="The zone name the ip resource is linked to. If set, the ip is plumbed from the global in the zone context.",
                  example="zone1"
                )

class KeywordIpDockerContainerRid(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  rtype="docker",
                  keyword="container_rid",
                  order=12,
                  at=True,
                  required=True,
                  text="The docker container resource id to plumb the ip into.",
                  example="container#0"
                )

class KeywordIpAmazonEip(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  rtype="amazon",
                  keyword="eip",
                  order=12,
                  at=True,
                  required=False,
                  text="The public elastic ip to associate to <ipname>. The special <allocate> value tells the provisioner to assign a new public address.",
                  example="52.27.90.63"
                )

class KeywordIpAmazonCascadeAllocation(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  rtype="amazon",
                  keyword="cascade_allocation",
                  provisioning=True,
                  order=13,
                  at=True,
                  required=False,
                  text="Set new allocated ip as value to other ip resources ipname parameter. The syntax is a whitespace separated list of <rid>.ipname[@<scope>].",
                  example="ip#1.ipname ip#1.ipname@nodes"
                )

class KeywordIpAmazonDockerDaemonIp(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  rtype="amazon",
                  keyword="docker_daemon_ip",
                  provisioning=True,
                  order=13,
                  at=False,
                  candidates=[True, False],
                  required=False,
                  text="Set new allocated ip as value as a '--ip <addr>' argument in the DEFAULT.docker_daemon_args parameter.",
                  example="True"
                )

class KeywordDiskPrKey(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  keyword="prkey",
                  order=15,
                  at=True,
                  required=False,
                  text="Defines a specific persistent reservation key for the resource. Takes priority over the service-level defined prkey and the node.conf specified prkey."
                )

class KeywordDiskGceNames(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="gce",
                  keyword="names",
                  provisioning=False,
                  order=1,
                  at=True,
                  required=True,
                  text="Set the gce disk names",
                  example="svc1-disk1"
                )

class KeywordDiskGceZone(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="gce",
                  keyword="gce_zone",
                  provisioning=False,
                  order=2,
                  at=True,
                  required=True,
                  text="Set the gce zone",
                  example="europe-west1-b"
                )

class KeywordDiskGceDescription(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="gce",
                  keyword="description",
                  provisioning=True,
                  order=5,
                  at=True,
                  required=False,
                  default=True,
                  text="An optional, textual description for the disks being created.",
                  example="foo"
                )

class KeywordDiskGceImage(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="gce",
                  keyword="image",
                  provisioning=True,
                  order=5,
                  at=True,
                  required=False,
                  default=True,
                  text="An image to apply to the disks being created. When using this option, the size of the disks must be at least as large as the image size.",
                  example="centos-7"
                )

class KeywordDiskGceImageProject(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="gce",
                  keyword="image_project",
                  provisioning=True,
                  order=5,
                  at=True,
                  required=False,
                  default=True,
                  text="The project against which all image references will be resolved.",
                  example="myprj"
                )

class KeywordDiskGceSize(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="gce",
                  keyword="size",
                  provisioning=True,
                  order=3,
                  at=True,
                  required=False,
                  default=True,
                  text="Indicates the size of the disks. The OpenSVC size converter is used to produce gce compatible size, so k, K, kib, KiB, kb, KB, ki, Ki and all their g, t, p, e variants are supported.",
                  example="20g"
                )

class KeywordDiskGceSourceSnapshot(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="gce",
                  keyword="source_snapshot",
                  provisioning=True,
                  order=5,
                  at=True,
                  required=False,
                  default=True,
                  text="A source snapshot used to create the disks. It is safe to delete a snapshot after a disk has been created from the snapshot. In such cases, the disks will no longer reference the deleted snapshot. When using this option, the size of the disks must be at least as large as the snapshot size.",
                  example="mysrcsnap"
                )


class KeywordDiskGceDiskType(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="gce",
                  keyword="disk_type",
                  provisioning=True,
                  order=5,
                  at=True,
                  required=False,
                  default=True,
                  text="Specifies the type of disk to create. To get a list of available disk types, run 'gcloud compute disk-types list'. The default disk type is pd-standard.",
                  example="pd-standard"
                )

class KeywordIpGceRoutename(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  rtype="gce",
                  keyword="routename",
                  provisioning=False,
                  order=13,
                  at=True,
                  required=False,
                  text="Set the gce route name",
                  example="rt-ip1"
                )

class KeywordIpGceZone(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  rtype="gce",
                  keyword="gce_zone",
                  provisioning=False,
                  order=13,
                  at=True,
                  required=False,
                  text="Set the gce ip route next hop zone",
                  example="europe-west1-b"
                )

class KeywordIpType(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  keyword="type",
                  at=True,
                  candidates=[None, 'crossbow', 'amazon', 'docker', 'gce'],
                  text="The opensvc ip driver name.",
                  required=False,
                  order=10,
                  example="crossbow",
                )

class KeywordIpIpdev(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  keyword="ipdev",
                  order=11,
                  at=True,
                  required=True,
                  text="The interface name over which OpenSVC will try to stack the service ip. Can be different from one node to the other, in which case the '@nodename' can be specified."
                )

class KeywordIpIpdevext(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  rtype="crossbow",
                  keyword="ipdevext",
                  order=12,
                  at=True,
                  required=False,
                  example="v4",
                  text="The interface name extension for crossbow ipadm configuration."
                )

class KeywordIpDelNetRoute(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  rtype="docker",
                  keyword="del_net_route",
                  order=12,
                  at=True,
                  required=False,
                  example="true",
                  text="Some docker ip configuration requires dropping the network route autoconfigured when installing the ip address. In this case set this parameter to true, and also set the network parameter."
                )

class KeywordIpNetmask(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  keyword="netmask",
                  at=True,
                  order=13,
                  text="If an ip is already plumbed on the root interface (in which case the netmask is deduced from this ip). Mandatory if the interface is dedicated to the service (dummy interface are likely to be in this case). The format is either dotted or octal for IPv4, ex: 255.255.252.0 or 22, and octal for IPv6, ex: 64.",
                  example="255.255.255.0"
                )

class KeywordIpGateway(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="ip",
                  keyword="gateway",
                  at=True,
                  order=14,
                  required=False,
                  text="A zone ip provisioning parameter used in the sysidcfg formatting. The format is decimal for IPv4, ex: 255.255.252.0, and octal for IPv6, ex: 64.",
                  provisioning=True
                )

class KeywordDiskType(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  keyword="type",
                  at=True,
                  order=9,
                  required=False,
                  default="vg",
                  candidates=['disk', 'veritas', 'raw', 'rados', 'md', 'drbd', 'loop', 'zpool', 'pool', 'raw', 'vmdg', 'vdisk', 'lvm', 'vg', 'amazon', 'gce'],
                  text="The volume group driver to use. Leave empty to activate the native volume group manager."
                )

class KeywordDiskDiskDiskId(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="disk",
                  keyword="disk_id",
                  order=10,
                  at=True,
                  required=False,
                  text="The wwn of the disk.",
                  example="6589cfc00000097484f0728d8b2118a6"
                )

class KeywordDiskDiskSize(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="disk",
                  keyword="size",
                  order=11,
                  at=True,
                  required=False,
                  provisioning=True,
                  text="The size of the disk to provision.",
                  example="15g"
                )

class KeywordDiskDiskArray(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="disk",
                  keyword="array",
                  order=11,
                  at=True,
                  required=False,
                  provisioning=True,
                  text="The array to provision the disk from.",
                  example="xtremio-prod1"
                )

class KeywordDiskDiskDiskGroup(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="disk",
                  keyword="diskgroup",
                  order=11,
                  at=True,
                  required=False,
                  provisioning=True,
                  text="The array disk group to provision the disk from.",
                  example="default"
                )

class KeywordDiskAmazonVolumes(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="amazon",
                  keyword="volumes",
                  order=10,
                  at=True,
                  required=True,
                  text="A whitespace separated list of amazon volumes. Any member of the list can be set to a special <key=value,key=value> value. In this case the provisioner will allocate a new volume with the specified characteristics and replace this member with the allocated volume id. The supported keys are the same as those supported by the awscli ec2 create-volume command: size, iops, availability-zone, snapshot, type and encrypted.",
                  example="vol-123456 vol-654321"
                )

class KeywordDiskRawDevs(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="raw",
                  keyword="devs",
                  order=10,
                  at=True,
                  required=True,
                  text="a list of device paths or <src>:<dst> device paths mappings, whitespace separated. Those devices are owned by the service and scsi reservation policy is applied to them.",
                  example="/dev/mapper/svc.d0:/dev/oracle/redo001 /dev/mapper/svc.d1"
                )

class KeywordDiskRawZone(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="raw",
                  keyword="zone",
                  order=12,
                  at=True,
                  required=False,
                  text="The zone name the raw resource is linked to. If set, the raw files are configured from the global reparented to the zonepath.",
                  example="zone1"
                )

class KeywordDiskRawCreateCharDevices(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="raw",
                  keyword="create_char_devices",
                  order=10,
                  at=True,
                  required=False,
                  default=True,
                  text="On Linux, char devices are not automatically created when devices are discovered. If set to True (the default), the raw resource driver will create and delete them using the raw kernel driver.",
                  example="false"
                )

class KeywordDiskRawUser(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  keyword="user",
                  rtype="raw",
                  order=11,
                  at=True,
                  required=True,
                  example="root",
                  text="The user that should be owner of the device. Either in numeric or symbolic form."
                )

class KeywordDiskRawGroup(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  keyword="group",
                  rtype="raw",
                  order=11,
                  at=True,
                  required=False,
                  example="sys",
                  text="The group that should be owner of the device. Either in numeric or symbolic form."
                )

class KeywordDiskRawPerm(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  keyword="perm",
                  rtype="raw",
                  order=11,
                  at=True,
                  required=False,
                  example="600",
                  text="The permissions the device should have. A string representing the octal permissions."
                )


class KeywordDiskVgname(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype=["lvm", "vg"],
                  keyword="vgname",
                  order=10,
                  required=True,
                  text="The name of the volume group"
                )

class KeywordDiskVgName(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype=["lvm", "vg"],
                  keyword="name",
                  order=10,
                  required=True,
                  text="The name of the volume group"
                )

class KeywordDiskOptions(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype=["lvm", "vg"],
                  keyword="options",
                  default="",
                  required=False,
                  provisioning=True,
                  text="The vgcreate options to use upon vg provisioning."
                )

class KeywordDiskMdUuid(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  required=True,
                  at=True,
                  keyword="uuid",
                  rtype="md",
                  text="The md uuid to use with mdadm assemble commands"
                )

class KeywordDiskMdDevs(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  required=True,
                  at=True,
                  keyword="devs",
                  rtype="md",
                  provisioning=True,
                  example="/dev/rbd0 /dev/rbd1",
                  text="The md member devices to use with mdadm create command"
                )

class KeywordDiskMdLevel(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  required=True,
                  at=True,
                  keyword="level",
                  rtype="md",
                  provisioning=True,
                  example="raid1",
                  text="The md raid level to use with mdadm create command (see mdadm man for values)"
                )

class KeywordDiskMdLayout(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  required=False,
                  at=True,
                  keyword="layout",
                  rtype="md",
                  provisioning=True,
                  text="The md raid layout to use with mdadm create command (see mdadm man for values)"
                )

class KeywordDiskMdChunk(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  required=False,
                  at=True,
                  keyword="chunk",
                  rtype="md",
                  provisioning=True,
                  example="128k",
                  text="The md chunk size to use with mdadm create command. Values are converted to kb and rounded to 4."
                )

class KeywordDiskMdSpares(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  required=False,
                  at=True,
                  keyword="spares",
                  rtype="md",
                  provisioning=True,
                  example="0",
                  text="The md number of spare devices to use with mdadm create command"
                )

class KeywordDiskMdShared(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  keyword="shared",
                  candidates=(True, False),
                  at=True,
                  rtype="md",
                  text="Trigger additional checks on the passive nodes. If not specified, the shared parameter defaults to True if no multiple nodes and drpnodes are defined and no md section parameter use scoping."
                )

class KeywordDiskClientId(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  keyword="client_id",
                  rtype="rados",
                  text="Client id to use for authentication with the rados servers"
                )

class KeywordDiskKeyring(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  keyword="keyring",
                  required=False,
                  rtype="rados",
                  text="keyring to look for the client id secret for authentication with the rados servers"
                )

class KeywordDiskLock(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  keyword="lock",
                  candidates=["exclusive", "shared", "None"],
                  rtype="rados",
                  text="Locking mode for the rados images"
                )

class KeywordDiskLockSharedTag(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  keyword="lock_shared_tag",
                  rtype="rados",
                  depends=[('lock', ['shared'])],
                  text="The tag to use upon rados image locking in shared mode"
                )

class KeywordDiskImageFormat(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="rados",
                  keyword="image_format",
                  provisioning=True,
                  default="2",
                  text="The rados image format"
                )

class KeywordDiskSize(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="rados",
                  keyword="size",
                  provisioning=True,
                  text="The rados image size in MB"
                )

class KeywordDiskImages(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="rados",
                  keyword="images",
                  text="The rados image names handled by this vg resource. whitespace separated."
                )

class KeywordDiskDsf(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype=["lvm", "vg"],
                  keyword="dsf",
                  candidates=(True, False),
                  default=True,
                  text="HP-UX only. 'dsf' must be set to false for LVM to use never-multipathed /dev/dsk/... devices. Otherwize, ad-hoc multipathed /dev/disk/... devices."
                )

class KeywordDiskScsireserv(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  keyword="scsireserv",
                  default=False,
                  candidates=(True, False),
                  text="If set to 'true', OpenSVC will try to acquire a type-5 (write exclusive, registrant only) scsi3 persistent reservation on every path to disks of every disk group attached to this service. Existing reservations are preempted to not block service start-up. If the start-up was not legitimate the data are still protected from being written over from both nodes. If set to 'false' or not set, 'scsireserv' can be activated on a per-resource basis."
                )

class KeywordDiskPvs(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype=["lvm", "vg"],
                  keyword="pvs",
                  required=True,
                  text="The list of paths to the physical volumes of the volume group.",
                  provisioning=True
                )

class KeywordZPoolVdev(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype=["zpool", "pool"],
                  keyword="vdev",
                  order=11,
                  at=True,
                  provisioning=True,
                  text="The vdev list, including optional parity keywords, as would be passed to zpool create."
                )

class KeywordZPoolName(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype=["zpool", "pool"],
                  keyword="name",
                  order=10,
                  at=True,
                  text="The name of the zfs pool"
                )

class KeywordZPoolPoolname(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype=["zpool", "pool"],
                  keyword="poolname",
                  order=10,
                  at=True,
                  text="The name of the zfs pool"
                )

class KeywordVmdgContainerid(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="vmdg",
                  keyword="container_id",
                  at=True,
                  required=False,
                  text="The id of the container whose configuration to extract the disk mapping from."
                )

class KeywordDiskDrbdRes(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="drbd",
                  keyword="res",
                  order=11,
                  text="The name of the drbd resource associated with this service resource. OpenSVC expect the resource configuration file to reside in '/etc/drbd.d/resname.res'. The 'sync#i0' resource will take care of replicating this file to remote nodes."
                )

class KeywordShareType(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="share",
                  keyword="type",
                  candidates=["nfs"],
                  text="The type of share.",
                  required=True,
                  order=1
                )

class KeywordSharePath(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="share",
                  keyword="path",
                  rtype="nfs",
                  order=10,
                  at=True,
                  required=True,
                  text="The fullpath of the directory to share."
                )

class KeywordShareNfsOpts(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="share",
                  keyword="opts",
                  rtype="nfs",
                  order=11,
                  at=True,
                  required=True,
                  text="The NFS share export options, as they woud be set in /etc/exports or passed to Solaris share command."
                )

class KeywordFsDev(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="fs",
                  keyword="dev",
                  order=11,
                  at=True,
                  required=True,
                  text="The block device file or filesystem image file hosting the filesystem to mount. Different device can be set up on different nodes using the dev@nodename syntax"
                )

class KeywordFsZone(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="fs",
                  keyword="zone",
                  order=11,
                  at=True,
                  required=False,
                  text="The zone name the fs refers to. If set, the fs mount point is reparented into the zonepath rootfs."
                )

class KeywordFsVg(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="fs",
                  keyword="vg",
                  required=True,
                  text="The name of the disk group the filesystem device should be provisioned from.",
                  provisioning=True
                )

class KeywordFsSize(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="fs",
                  keyword="size",
                  required=True,
                  text="The size in MB of the logical volume to provision for this filesystem.",
                  provisioning=True
                )

class KeywordFsMnt(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="fs",
                  keyword="mnt",
                  order=12,
                  required=True,
                  text="The mount point where to mount the filesystem."
                )

class KeywordFsMntOpt(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="fs",
                  keyword="mnt_opt",
                  order=13,
                  at=True,
                  text="The mount options."
                )

class KeywordFsMkfsOpt(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="fs",
                  keyword="mkfs_opt",
                  provisioning=True,
                  required=False,
                  at=True,
                  order=13,
                  text="Eventual mkfs additional options."
                )

class KeywordFsType(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="fs",
                  keyword="type",
                  order=14,
                  required=True,
                  strict_candidates=False,
                  candidates=["directory"],
                  text="The filesystem type or 'directory'. Used to determine the fsck command to use."
                )

class KeywordFsSnapSize(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="fs",
                  keyword="snap_size",
                  order=14,
                  text="If this filesystem is build on a snapable logical volume or is natively snapable (jfs, vxfs, ...) this setting overrides the default 10% of the filesystem size to compute the snapshot size. The snapshot is created by snap-enabled rsync-type sync resources. The unit is Megabytes."
                )

class KeywordFsDirPath(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="fs",
                  keyword="path",
                  rtype="directory",
                  order=10,
                  at=True,
                  required=True,
                  text="The fullpath of the directory to create."
                )

class KeywordFsDirUser(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="fs",
                  keyword="user",
                  rtype="directory",
                  order=11,
                  at=True,
                  required=False,
                  example="root",
                  text="The user that should be owner of the directory. Either in numeric or symbolic form."
                )

class KeywordFsDirGroup(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="fs",
                  keyword="group",
                  rtype="directory",
                  order=11,
                  at=True,
                  required=False,
                  example="sys",
                  text="The group that should be owner of the directory. Either in numeric or symbolic form."
                )

class KeywordFsDirPerm(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="fs",
                  keyword="perm",
                  rtype="directory",
                  order=11,
                  at=True,
                  required=False,
                  example="1777",
                  text="The permissions the directory should have. A string representing the octal permissions."
                )

class KeywordLoopSize(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="loop",
                  keyword="size",
                  at=True,
                  required=True,
                  default=10,
                  text="The size of the loop file to provision.",
                  provisioning=True
                )

class KeywordLoopFile(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="loop",
                  at=True,
                  keyword="file",
                  required=True,
                  text="The file hosting the disk image to map."
                )

class KeywordSyncNetappFiler(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="filer",
                  rtype="netapp",
                  required=True,
                  at=True,
                  text="The Netapp filer resolvable host name used by the node.  Different filers can be set up for each node using the filer@nodename syntax."
                )

class KeywordSyncNetappPath(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="path",
                  rtype="netapp",
                  required=True,
                  text="Specifies the volume or qtree to drive snapmirror on."
                )

class KeywordSyncNetappUser(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="user",
                  rtype="netapp",
                  required=True,
                  default="nasadm",
                  text="Specifies the user used to ssh connect the filers. Nodes should be trusted by keys to access the filer with this user."
                )

class KeywordSyncIbmdssnapPairs(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="pairs",
                  at=True,
                  rtype="ibmdssnap",
                  required=True,
                  text="Whitespace-separated list of device pairs.",
                  example="0065:0073 0066:0074"
                )

class KeywordSyncIbmdssnapArray(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="array",
                  at=True,
                  rtype="ibmdssnap",
                  required=True,
                  text="The name of the array holding the source devices and their paired devices.",
                  example="IBM.2243-12ABC00"
                )

class KeywordSyncIbmdssnapBgcopy(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="bgcopy",
                  at=True,
                  rtype="ibmdssnap",
                  candidates=[True, False],
                  required=True,
                  text="Initiate a background copy of the source data block to the paired devices upon resync."
                )

class KeywordSyncIbmdssnapRecording(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="recording",
                  at=True,
                  rtype="ibmdssnap",
                  candidates=[True, False],
                  required=True,
                  text="Track only changed data blocks instead of copying the whole source data to the paired devices."
                )

class KeywordSyncNexentaName(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="name",
                  at=True,
                  rtype="nexenta",
                  required=True,
                  text="The name of the Nexenta autosync configuration."
                )

class KeywordSyncNexentaFiler(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="filer",
                  at=True,
                  rtype="nexenta",
                  required=True,
                  text="The name of the Nexenta local head. Must be set for each node using the scoping syntax."
                )

class KeywordSyncNexentaPath(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="path",
                  at=True,
                  rtype="nexenta",
                  required=True,
                  text="The path of the zfs to synchronize, as seen by the Nexenta heads."
                )

class KeywordSyncNexentaReversible(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="reversible",
                  at=True,
                  rtype="nexenta",
                  candidates=[True, False],
                  required=True,
                  text="Defines if the replication link can be reversed. Set to no for prd to drp replications to protect production data."
                )

class KeywordSyncHp3parSnapArray(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="array",
                  rtype="hp3parsnap",
                  required=True,
                  at=True,
                  text="Name of the HP 3par array to send commands to."
                )

class KeywordSyncHp3parSnapVvnames(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="vv_names",
                  rtype="hp3parsnap",
                  required=True,
                  at=True,
                  text="The names of snapshot VV or sets of VV to update."
                )

class KeywordSyncHp3parArray(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="array",
                  rtype="hp3par",
                  required=True,
                  at=True,
                  text="Name of the HP 3par array to send commands to."
                )

class KeywordSyncHp3parMode(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="mode",
                  rtype="hp3par",
                  required=True,
                  candidates=["async", "sync"],
                  default="async",
                  text="Replication mode: Synchronous or Asynchronous"
                )

class KeywordSyncHp3parMethod(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="method",
                  rtype="hp3par",
                  required=False,
                  candidates=["ssh", "cli"],
                  default="ssh",
                  at=True,
                  text="The method to use to submit commands to the arrays."
                )

class KeywordSyncHp3parRcg(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="rcg",
                  rtype="hp3par",
                  required=True,
                  at=True,
                  text="Name of the HP 3par remote copy group. The scoping syntax must be used to fully describe the replication topology."
                )

class KeywordSyncDcsckptDcs(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="dcs",
                  rtype="dcsckpt",
                  required=True,
                  text="Whitespace-separated list of DataCore heads, as seen by the manager."
                )

class KeywordSyncDcsckptManager(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="manager",
                  rtype="dcsckpt",
                  required=True,
                  text="The DataCore manager name running a ssh daemon, as set in the auth.conf section title."
                )

class KeywordSyncDcsckptPairs(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="pairs",
                  rtype="dcsckpt",
                  required=True,
                  text="A json-formatted list of dictionaries representing the source and destination device pairs. Each dictionary must have the 'src', 'dst_ckpt' keys."
                )

class KeywordSyncDcssnapDcs(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="dcs",
                  rtype="dcssnap",
                  required=True,
                  text="Whitespace-separated list of DataCore heads, as seen by the manager."
                )

class KeywordSyncDcssnapManager(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="manager",
                  rtype="dcssnap",
                  required=True,
                  text="The DataCore manager name running a ssh daemon, as set in the auth.conf section title."
                )

class KeywordSyncDcssnapSnapname(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="snapname",
                  rtype="dcssnap",
                  required=True,
                  text="Whitespace-separated list of snapshot device names, as seen by the DataCore manager."
                )

class KeywordSyncEvasnapEvaname(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="eva_name",
                  rtype="evasnap",
                  required=True,
                  text="Name of the HP EVA array hosting the source and snapshot devices."
                )

class KeywordSyncEvasnapSnapname(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="snap_name",
                  rtype="evasnap",
                  required=True,
                  text="Name of the snapshot objectname as seen in sssu."
                )

class KeywordSyncEvasnapPairs(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="pairs",
                  rtype="evasnap",
                  required=True,
                  text="A json-formatted list of dictionaries representing the device pairs. Each dict must have the 'src', 'dst' and 'mask' keys. The mask key value is a list of \\<hostpath>\\<lunid> strings."
                )

class KeywordSyncNecismsnapArray(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="array",
                  rtype="necism",
                  required=True,
                  text="Name of the NEC ISM array to send commands to."
                )

class KeywordSyncNecismsnapDevs(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="devs",
                  rtype="necism",
                  required=True,
                  text="A whitespace-separated list of SV:LD."
                )

class KeywordSyncSymSrdfsSymid(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="symid",
                  at=True,
                  rtype="symsrdfs",
                  required=True,
                  text="Id of the local symmetrix array hosting the symdg. This parameter is usually scoped to define different array ids for different nodes."
                )

class KeywordSyncSymSrdfsSymdg(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="symdg",
                  at=False,
                  rtype="symsrdfs",
                  required=True,
                  text="Name of the symmetrix device group where the source and target devices are grouped."
                )

class KeywordSyncSymSrdfsRdfg(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="rdfg",
                  at=False,
                  rtype="symsrdfs",
                  required=True,
                  text="Name of the RDF group pairing the source and target devices."
                )

class KeywordSyncSymclonePrecopy(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="precopy",
                  at=True,
                  rtype="symclone",
                  required=False,
                  default=True,
                  text="Use -precopy on recreate."
                )

class KeywordSyncSymcloneSymid(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="symid",
                  rtype=["symclone", "symsnap"],
                  required=True,
                  text="Identifier of the symmetrix array hosting the source and target devices pairs pointed by 'pairs'."
                )

class KeywordSyncSymclonePairs(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="pairs",
                  rtype=["symclone", "symsnap"],
                  required=True,
                  at=True,
                  default=None,
                  text="Whitespace-separated list of devices <src>:<dst> devid pairs to drive with this resource.",
                  example="00B60:00B61 00B62:00B63",
                )

class KeywordSyncSymcloneConsistent(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="consistent",
                  rtype=["symclone", "symsnap"],
                  at=True,
                  default=True,
                  text="Use -consistent in symclone commands.",
                )

class KeywordSyncDdsSrc(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="src",
                  rtype="dds",
                  required=True,
                  text="Points the origin of the snapshots to replicate from."
                )

class KeywordSyncDdsDst(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="dst",
                  rtype="dds",
                  at=True,
                  required=True,
                  text="Target file or block device. Optional. Defaults to src. Points the media to replay the binary-delta received from source node to. This media must have a size superior or equal to source."
                )

class KeywordSyncDdsTarget(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="target",
                  rtype="dds",
                  required=True,
                  candidates=['nodes', 'drpnodes', 'nodes drpnodes'],
                  text="Accepted values are 'drpnodes', 'nodes' or both, whitespace-separated. Points the target nodes to replay the binary-deltas on. Be warned that starting the service on a target node without a 'stop-sync_update-start cycle, will break the synchronization, so this mode is usually restricted to drpnodes sync, and should not be used to replicate data between nodes with automated services failover."
                )

class KeywordSyncDdsSnapSize(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="sync",
                  keyword="snap_size",
                  rtype="dds",
                  text="Default to 10% of origin. In MB, rounded to physical extent boundaries by lvm tools. Size of the snapshots created by OpenSVC to extract binary deltas from. Opensvc creates at most 2 snapshots : one short-lived to gather changed data from, and one long-lived to gather changed chunks list from. Volume groups should have the necessary space always available."
                )

class KeywordVdiskPath(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="disk",
                  rtype="vdisk",
                  keyword="path",
                  required=True,
                  at=True,
                  text="Path of the device or file used as a virtual machine disk. The path@nodename can be used to to set up different path on each node."
                )

class KeywordHbType(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="hb",
                  keyword="type",
                  required=True,
                  candidates=('openha', 'linuxha'),
                  text="Specify the heartbeat driver to use."
                )

class KeywordHbName(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="hb",
                  keyword="name",
                  rtype="openha",
                  text="Specify the service name used by the heartbeat. Defaults to the service name."
                )

class KeywordTaskCommand(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="task",
                  keyword="command",
                  at=True,
                  order=1,
                  required=True,
                  text="The command to execute on 'run' action and at scheduled interval. The default schedule for tasks is @0.",
                  example="/srv/{svcname}/data/scripts/backup.sh"
                )

class KeywordTaskConfirmation(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="task",
                  keyword="confirmation",
                  at=True,
                  order=1,
                  default=False,
                  required=False,
                  candidates=(True, False),
                  text="If set to True, ask for an interactive confirmation to run the task. This flag can be used for dangerous tasks like data-restore.",
                )

class KeywordTaskOnError(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="task",
                  keyword="on_error",
                  at=True,
                  order=1,
                  required=False,
                  text="A command to execute on 'run' action if 'command' returned an error.",
                  example="/srv/{svcname}/data/scripts/task_on_error.sh"
                )

class KeywordTaskUser(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="task",
                  keyword="user",
                  at=True,
                  order=2,
                  required=False,
                  text="The user to impersonate when running the task command. The default user is root.",
                  example="admin"
                )

class KeywordTaskSchedule(Keyword):
    def __init__(self):
        Keyword.__init__(
                  self,
                  section="task",
                  keyword="schedule",
                  default="@0",
                  at=True,
                  text="Set the this task run schedule. See usr/share/doc/node.conf for the schedule syntax reference.",
                  example='["00:00-01:00@61 mon", "02:00-03:00@61 tue-sun"]'
                )

class KeyDict(KeywordStore):
    def __init__(self, provision=False):
        KeywordStore.__init__(self, provision)

        import os

        def kw_tags(resource):
            return Keyword(
                  section=resource,
                  keyword="tags",
                  generic=True,
                  at=True,
                  candidates=None,
                  default=None,
                  text="A list of tags. Arbitrary tags can be used to limit action scope to resources with a specific tag. Some tags can influence the driver behaviour. For example the 'encap' tag assigns the resource to the encapsulated service, 'noaction' avoids any state changing action from the driver, 'nostatus' forces the status to n/a."
                )
        def kw_subset(resource):
            return Keyword(
                  section=resource,
                  keyword="subset",
                  generic=True,
                  at=True,
                  default=None,
                  text="Assign the resource to a specific subset."
                )
        def kw_restart(resource):
            return Keyword(
                  section=resource,
                  keyword="restart",
                  generic=True,
                  at=True,
                  default=0,
                  text="The agent will try to restart a resource n times before falling back to the monitor action."
                )
        def kw_monitor(resource):
            return Keyword(
                  section=resource,
                  keyword="monitor",
                  generic=True,
                  at=True,
                  candidates=(True, False),
                  default=False,
                  text="A monitored resource will trigger a node suicide if the service has a heartbeat resource in up state"
                )
        def kw_disable(resource):
            return Keyword(
                  section=resource,
                  keyword="disable",
                  generic=True,
                  at=True,
                  candidates=(True, False),
                  default=False,
                  text="A disabled resource will be ignored on service startup and shutdown."
                )
        def kw_disable_on(resource):
            return Keyword(
                  section=resource,
                  keyword="disable_on",
                  generic=True,
                  default=[],
                  text="A whitelist-separated list of nodes to disable the resource on. A disabled resource will be ignored on service startup and shutdown."
                )
        def kw_enable_on(resource):
            return Keyword(
                  section=resource,
                  keyword="enable_on",
                  generic=True,
                  default=[],
                  text="A whitelist-separated list of nodes to enable the resource on. Takes precedence over disable and disable_on."
                )
        def kw_optional(resource):
            return Keyword(
                  section=resource,
                  keyword="optional",
                  generic=True,
                  at=True,
                  candidates=(True, False),
                  default=False,
                  text="Possible values are 'true' or 'false'. Actions on resource will be tried upon service startup and shutdown, but action failures will be logged and passed over. Useful for resources like dump filesystems for example."
                )
        def kw_always_on(resource):
            return Keyword(
                  section=resource,
                  keyword="always_on",
                  generic=True,
                  candidates=['nodes', 'drpnodes', 'nodes drpnodes'],
                  text="Possible values are 'nodes', 'drpnodes' or 'nodes drpnodes', or a list of nodes. Sets the nodes on which the resource is always kept up. Primary usage is file synchronization receiving on non-shared disks. Don't set this on shared disk !! danger !!"
                )
        def kw_pre_unprovision(resource):
            return Keyword(
                  section=resource,
                  keyword="pre_unprovision",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource unprovision action. Errors do not interrupt the action."
                )
        def kw_post_unprovision(resource):
            return Keyword(
                  section=resource,
                  keyword="post_unprovision",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource unprovision action. Errors do not interrupt the action."
                )
        def kw_pre_provision(resource):
            return Keyword(
                  section=resource,
                  keyword="pre_provision",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource provision action. Errors do not interrupt the action."
                )
        def kw_post_provision(resource):
            return Keyword(
                  section=resource,
                  keyword="post_provision",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource provision action. Errors do not interrupt the action."
                )
        def kw_pre_start(resource):
            return Keyword(
                  section=resource,
                  keyword="pre_start",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource start action. Errors do not interrupt the action."
                )
        def kw_post_start(resource):
            return Keyword(
                  section=resource,
                  keyword="post_start",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource start action. Errors do not interrupt the action."
                )
        def kw_pre_stop(resource):
            return Keyword(
                  section=resource,
                  keyword="pre_stop",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource stop action. Errors do not interrupt the action."
                )
        def kw_post_stop(resource):
            return Keyword(
                  section=resource,
                  keyword="post_stop",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource stop action. Errors do not interrupt the action."
                )
        def kw_pre_sync_nodes(resource):
            return Keyword(
                  section=resource,
                  keyword="pre_sync_nodes",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource sync_nodes action. Errors do not interrupt the action."
                )
        def kw_post_sync_nodes(resource):
            return Keyword(
                  section=resource,
                  keyword="post_sync_nodes",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource sync_nodes action. Errors do not interrupt the action."
                )
        def kw_pre_sync_drp(resource):
            return Keyword(
                  section=resource,
                  keyword="pre_sync_drp",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource sync_drp action. Errors do not interrupt the action."
                )
        def kw_post_sync_drp(resource):
            return Keyword(
                  section=resource,
                  keyword="post_sync_drp",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource sync_drp action. Errors do not interrupt the action."
                )
        def kw_pre_sync_resync(resource):
            return Keyword(
                  section=resource,
                  keyword="pre_sync_resync",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource sync_resync action. Errors do not interrupt the action."
                )
        def kw_post_sync_resync(resource):
            return Keyword(
                  section=resource,
                  keyword="post_sync_resync",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource sync_resync action. Errors do not interrupt the action."
                )
        def kw_pre_sync_update(resource):
            return Keyword(
                  section=resource,
                  keyword="pre_sync_update",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource sync_update action. Errors do not interrupt the action."
                )
        def kw_post_sync_update(resource):
            return Keyword(
                  section=resource,
                  keyword="post_sync_update",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource sync_update action. Errors do not interrupt the action."
                )
        def kw_pre_run(resource):
            return Keyword(
                  section=resource,
                  keyword="pre_run",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource run action. Errors do not interrupt the action."
                )
        def kw_post_run(resource):
            return Keyword(
                  section=resource,
                  keyword="post_run",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource run action. Errors do not interrupt the action."
                )

        def kw_blocking_pre_unprovision(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_pre_unprovision",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource unprovision action. Errors interrupt the action."
                )
        def kw_blocking_post_unprovision(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_post_unprovision",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource unprovision action. Errors interrupt the action."
                )
        def kw_blocking_pre_provision(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_pre_provision",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource provision action. Errors interrupt the action."
                )
        def kw_blocking_post_provision(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_post_provision",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource provision action. Errors interrupt the action."
                )
        def kw_blocking_pre_start(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_pre_start",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource start action. Errors interrupt the action."
                )
        def kw_blocking_post_start(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_post_start",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource start action. Errors interrupt the action."
                )
        def kw_blocking_pre_stop(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_pre_stop",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource stop action. Errors interrupt the action."
                )
        def kw_blocking_post_stop(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_post_stop",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource stop action. Errors interrupt the action."
                )
        def kw_blocking_pre_sync_nodes(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_pre_sync_nodes",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource sync_nodes action. Errors interrupt the action."
                )
        def kw_blocking_post_sync_nodes(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_post_sync_nodes",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource sync_nodes action. Errors interrupt the action."
                )
        def kw_blocking_pre_sync_drp(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_pre_sync_drp",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource sync_drp action. Errors interrupt the action."
                )
        def kw_blocking_post_sync_drp(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_post_sync_drp",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource sync_drp action. Errors interrupt the action."
                )
        def kw_blocking_pre_sync_resync(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_pre_sync_resync",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource sync_resync action. Errors interrupt the action."
                )
        def kw_blocking_post_sync_resync(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_post_sync_resync",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource sync_resync action. Errors interrupt the action."
                )
        def kw_blocking_pre_sync_update(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_pre_sync_update",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource sync_update action. Errors interrupt the action."
                )
        def kw_blocking_post_sync_update(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_post_sync_update",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource sync_update action. Errors interrupt the action."
                )
        def kw_blocking_pre_run(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_pre_run",
                  generic=True,
                  at=True,
                  text="A command or script to execute before the resource run action. Errors interrupt the action."
                )
        def kw_blocking_post_run(resource):
            return Keyword(
                  section=resource,
                  keyword="blocking_post_run",
                  generic=True,
                  at=True,
                  text="A command or script to execute after the resource run action. Errors interrupt the action."
                )

        def kw_requires(section, action):
            return Keyword(
                  section=section,
                  keyword=action+"_requires",
                  generic=True,
                  at=True,
                  example="ip#0 fs#0(down,stdby down)",
                  default="",
                  text="A whitespace-separated list of conditions to meet to accept running a '%s' action. A condition is expressed as <rid>(<state>,...). If states are omitted, 'up,stdby up' is used as the default expected states." % action
                )


        self += kw_disable("DEFAULT")

        for r in ["sync", "ip", "fs", "disk", "hb", "share", "container", "app", "task"]:
            self += kw_restart(r)
            self += kw_tags(r)
            self += kw_subset(r)
            self += kw_monitor(r)
            self += kw_disable(r)
            self += kw_disable_on(r)
            self += kw_enable_on(r)
            self += kw_optional(r)
            self += kw_always_on(r)

            self += kw_pre_unprovision(r)
            self += kw_post_unprovision(r)
            self += kw_pre_provision(r)
            self += kw_post_provision(r)
            self += kw_pre_start(r)
            self += kw_post_start(r)
            self += kw_pre_stop(r)
            self += kw_post_stop(r)
            self += kw_pre_sync_nodes(r)
            self += kw_post_sync_nodes(r)
            self += kw_pre_sync_drp(r)
            self += kw_post_sync_drp(r)
            self += kw_pre_sync_resync(r)
            self += kw_post_sync_resync(r)
            self += kw_pre_sync_update(r)
            self += kw_post_sync_update(r)
            self += kw_pre_run(r)
            self += kw_post_run(r)

            self += kw_blocking_pre_unprovision(r)
            self += kw_blocking_post_unprovision(r)
            self += kw_blocking_pre_provision(r)
            self += kw_blocking_post_provision(r)
            self += kw_blocking_pre_start(r)
            self += kw_blocking_post_start(r)
            self += kw_blocking_pre_stop(r)
            self += kw_blocking_post_stop(r)
            self += kw_blocking_pre_sync_nodes(r)
            self += kw_blocking_post_sync_nodes(r)
            self += kw_blocking_pre_sync_drp(r)
            self += kw_blocking_post_sync_drp(r)
            self += kw_blocking_pre_sync_resync(r)
            self += kw_blocking_post_sync_resync(r)
            self += kw_blocking_pre_sync_update(r)
            self += kw_blocking_post_sync_update(r)
            self += kw_blocking_pre_run(r)
            self += kw_blocking_post_run(r)

            for action in ["unprovision", "provision", "start", "stop",
                           "sync_nodes", "sync_drp", "sync_update",
                           "sync_break", "sync_resync", "run"]:
                self += kw_requires(r, action)

        self += KeywordMode()
        self += KeywordLockTimeout()
        self += KeywordPrKey()
        self += KeywordPkgName()
        self += KeywordDockerDaemonPrivate()
        self += KeywordDockerExe()
        self += KeywordDockerDataDir()
        self += KeywordDockerDaemonArgs()
        self += KeywordAntiAffinity()
        self += KeywordNoPreemptAbort()
        self += KeywordShowDisabled()
        self += KeywordCluster()
        self += KeywordClusterType()
        self += KeywordFlexPrimary()
        self += KeywordDrpFlexPrimary()
        self += KeywordRollback()
        self += KeywordStatusSchedule()
        self += KeywordCompSchedule()
        self += KeywordMonitorSchedule()
        self += KeywordResinfoSchedule()
        self += KeywordPushSchedule()
        self += KeywordFlexMinNodes()
        self += KeywordFlexMaxNodes()
        self += KeywordFlexCpuMinThreshold()
        self += KeywordFlexCpuMaxThreshold()
        self += KeywordServiceEnv()
        self += KeywordServiceType()
        self += KeywordNodes()
        self += KeywordAutostartNode()
        self += KeywordDrpnode()
        self += KeywordDrpnodes()
        self += KeywordEncapnodes()
        self += KeywordApp()
        self += KeywordComment()
        self += KeywordScsireserv()
        self += KeywordBwlimit()
        self += KeywordSyncInterval()
        self += KeywordSyncMaxDelay()
        self += KeywordPresnapTrigger()
        self += KeywordPostsnapTrigger()
        self += KeywordMonitorAction()
        self += KeywordCreatePg()
        self += KeywordPgCpus()
        self += KeywordPgMems()
        self += KeywordPgCpuShare()
        self += KeywordPgCpuQuota()
        self += KeywordPgMemOomControl()
        self += KeywordPgMemLimit()
        self += KeywordPgMemSwappiness()
        self += KeywordPgVmemLimit()
        self += KeywordPgBlkioWeight()
        self += KeywordSyncType()
        self += KeywordSyncDockerTarget()
        self += KeywordSyncBtrfsSrc()
        self += KeywordSyncBtrfsDst()
        self += KeywordSyncBtrfsTarget()
        self += KeywordSyncBtrfsRecursive()
        self += KeywordSyncBtrfsSnapName()
        self += KeywordSyncBtrfsSnapSubvol()
        self += KeywordSyncBtrfsSnapKeep()
        self += KeywordSyncZfsSnapName()
        self += KeywordSyncZfsSnapRecursive()
        self += KeywordSyncZfsSnapDataset()
        self += KeywordSyncZfsSnapKeep()
        self += KeywordSyncS3Src()
        self += KeywordSyncS3Options()
        self += KeywordSyncS3Bucket()
        self += KeywordSyncS3FullSchedule()
        self += KeywordSyncZfsSrc()
        self += KeywordSyncZfsDst()
        self += KeywordSyncZfsTarget()
        self += KeywordSyncZfsRecursive()
        self += KeywordSyncZfsTags()
        self += KeywordSyncRsyncSrc()
        self += KeywordSyncRsyncDst()
        self += KeywordSyncRsyncTags()
        self += KeywordSyncRsyncExclude()
        self += KeywordSyncRsyncOptions()
        self += KeywordSyncRsyncTarget()
        self += KeywordSyncRsyncSnap()
        self += KeywordSyncRsyncDstfs()
        self += KeywordSyncRsyncBwlimit()
        self += KeywordDefaultSyncSchedule()
        self += KeywordSyncSchedule()
        self += KeywordSyncSyncMaxDelay()
        self += KeywordIpType()
        self += KeywordIpIpname()
        self += KeywordIpIpdev()
        self += KeywordIpIpdevext()
        self += KeywordIpDelNetRoute()
        self += KeywordIpNetmask()
        self += KeywordIpGateway()
        self += KeywordIpDnsUpdate()
        self += KeywordIpDnsNameSuffix()
        self += KeywordIpNetwork()
        self += KeywordIpZone()
        self += KeywordIpDockerContainerRid()
        self += KeywordIpAmazonEip()
        self += KeywordIpAmazonCascadeAllocation()
        self += KeywordIpAmazonDockerDaemonIp()
        self += KeywordIpGceZone()
        self += KeywordIpGceRoutename()
        self += KeywordDiskPrKey()
        self += KeywordDiskGceNames()
        self += KeywordDiskGceZone()
        self += KeywordDiskGceDescription()
        self += KeywordDiskGceImage()
        self += KeywordDiskGceImageProject()
        self += KeywordDiskGceSize()
        self += KeywordDiskGceSourceSnapshot()
        self += KeywordDiskGceDiskType()
        self += KeywordDiskType()
        self += KeywordDiskDiskDiskId()
        self += KeywordDiskDiskSize()
        self += KeywordDiskDiskArray()
        self += KeywordDiskDiskDiskGroup()
        self += KeywordDiskAmazonVolumes()
        self += KeywordDiskRawDevs()
        self += KeywordDiskRawZone()
        self += KeywordDiskRawCreateCharDevices()
        self += KeywordDiskRawUser()
        self += KeywordDiskRawGroup()
        self += KeywordDiskRawPerm()
        self += KeywordDiskVgname()
        self += KeywordDiskVgName()
        self += KeywordDiskDsf()
        self += KeywordDiskImages()
        self += KeywordDiskMdUuid()
        self += KeywordDiskMdDevs()
        self += KeywordDiskMdLevel()
        self += KeywordDiskMdChunk()
        self += KeywordDiskMdLayout()
        self += KeywordDiskMdSpares()
        self += KeywordDiskMdShared()
        self += KeywordDiskClientId()
        self += KeywordDiskKeyring()
        self += KeywordDiskLock()
        self += KeywordDiskLockSharedTag()
        self += KeywordDiskSize()
        self += KeywordDiskImageFormat()
        self += KeywordDiskOptions()
        self += KeywordDiskScsireserv()
        self += KeywordDiskPvs()
        self += KeywordZPoolName()
        self += KeywordZPoolPoolname()
        self += KeywordZPoolVdev()
        self += KeywordVmdgContainerid()
        self += KeywordDiskDrbdRes()
        self += KeywordFsType()
        self += KeywordFsDev()
        self += KeywordFsZone()
        self += KeywordFsMnt()
        self += KeywordFsMntOpt()
        self += KeywordFsMkfsOpt()
        self += KeywordFsSnapSize()
        self += KeywordFsVg()
        self += KeywordFsSize()
        self += KeywordFsDirPath()
        self += KeywordFsDirUser()
        self += KeywordFsDirGroup()
        self += KeywordFsDirPerm()
        self += KeywordLoopFile()
        self += KeywordLoopSize()
        self += KeywordAppScript()
        self += KeywordAppTimeout()
        self += KeywordAppStart()
        self += KeywordAppStop()
        self += KeywordAppCheck()
        self += KeywordAppInfo()
        self += KeywordSyncNexentaName()
        self += KeywordSyncNexentaFiler()
        self += KeywordSyncNexentaPath()
        self += KeywordSyncNexentaReversible()
        self += KeywordSyncNetappFiler()
        self += KeywordSyncNetappPath()
        self += KeywordSyncNetappUser()
        self += KeywordSyncIbmdssnapPairs()
        self += KeywordSyncIbmdssnapArray()
        self += KeywordSyncIbmdssnapBgcopy()
        self += KeywordSyncIbmdssnapRecording()
        self += KeywordSyncSymSrdfsSymid()
        self += KeywordSyncSymSrdfsSymdg()
        self += KeywordSyncSymSrdfsRdfg()
        self += KeywordSyncSymcloneConsistent()
        self += KeywordSyncSymcloneSymid()
        self += KeywordSyncSymclonePairs()
        self += KeywordSyncSymclonePrecopy()
        self += KeywordSyncDcsckptDcs()
        self += KeywordSyncDcsckptManager()
        self += KeywordSyncDcsckptPairs()
        self += KeywordSyncDcssnapDcs()
        self += KeywordSyncDcssnapManager()
        self += KeywordSyncDcssnapSnapname()
        self += KeywordSyncNecismsnapArray()
        self += KeywordSyncNecismsnapDevs()
        self += KeywordSyncEvasnapEvaname()
        self += KeywordSyncEvasnapSnapname()
        self += KeywordSyncEvasnapPairs()
        self += KeywordSyncHp3parArray()
        self += KeywordSyncHp3parRcg()
        self += KeywordSyncHp3parMode()
        self += KeywordSyncHp3parMethod()
        self += KeywordSyncHp3parSnapArray()
        self += KeywordSyncHp3parSnapVvnames()
        self += KeywordSyncDdsSrc()
        self += KeywordSyncDdsDst()
        self += KeywordSyncDdsTarget()
        self += KeywordSyncDdsSnapSize()
        self += KeywordVdiskPath()
        self += KeywordHbType()
        self += KeywordHbName()
        self += KeywordSubsetParallel()
        self += KeywordStonithType()
        self += KeywordStonithTarget()
        self += KeywordStonithCalloutCmd()
        self += KeywordContainerType()
        self += KeywordContainerZoneDeleteOnStop()
        self += KeywordVmName()
        self += KeywordOsvcRootPath()
        self += KeywordContainerRcmd()
        self += KeywordGuestos()
        self += KeywordRootfs()
        self += KeywordLxcCf()
        self += KeywordJailRoot()
        self += KeywordJailIps()
        self += KeywordJailIp6s()
        self += KeywordTemplate()
        self += KeywordSharedIpGroup()
        self += KeywordSize()
        self += KeywordKeyName()
        self += KeywordCloudId()
        self += KeywordVmUuid()
        self += KeywordVirtinst()
        self += KeywordDockerRunCommand()
        self += KeywordDockerRunImage()
        self += KeywordDockerRunArgs()
        self += KeywordDockerRunSwarm()
        self += KeywordSnap()
        self += KeywordSnapof()
        self += KeywordContainerOrigin()
        self += KeywordSrpIp()
        self += KeywordSrpRootpath()
        self += KeywordSrpPrmCores()
        self += KeywordShareType()
        self += KeywordSharePath()
        self += KeywordShareNfsOpts()
        self += KeywordTaskCommand()
        self += KeywordTaskConfirmation()
        self += KeywordTaskOnError()
        self += KeywordTaskUser()
        self += KeywordTaskSchedule()

if __name__ == "__main__":
    store = KeyDict()
    store.print_templates()
    #print(store.DEFAULT.app)
    #print(store['DEFAULT'])
