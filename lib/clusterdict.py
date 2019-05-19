import sys
from rcGlobalEnv import rcEnv
from keywords import KeywordStore
from nodedict import KEYWORDS

# deprecated => supported
DEPRECATED_KEYWORDS = {
}

# supported => deprecated
REVERSE_DEPRECATED_KEYWORDS = {
}

DEPRECATED_SECTIONS = {
}

BASE_SECTIONS = [
    "node",
    "cluster",
    "compliance",
    "dequeue_actions",
    "stats",
    "checks",
    "packages",
    "patches",
    "asset",
    "disks",
    "rotate_root_pw",
    "listener",
    "syslog",
    "sysreport",
    "stats_collection",
    "reboot",
]

PRIVATE_KEYWORDS = [
    {
        "section": "DEFAULT",
        "keyword": "id",
        "inheritance": "head",
        "default_text": "<random uuid>",
        "text": "A RFC 4122 random uuid generated by the agent. To use as reference in resources definitions instead of the service name, so the service can be renamed without affecting the resources."
    },
    {
        "section": "DEFAULT",
        "keyword": "disable",
        "inheritance": "leaf",
        "generic": True,
        "at": True,
        "candidates": (True, False),
        "default": False,
        "convert": "boolean",
        "text": "A disabled resource will be ignored on service startup and shutdown. Its status is always reported ``n/a``.\n\nSet in DEFAULT, the whole service is disabled. A disabled service does not honor start and stop actions. These actions immediately return success.\n\n:cmd:`sudo svcmgr -s <svcname> disable` only sets :kw:`DEFAULT.disable`. As resources disabled state is not changed, :cmd:`sudo svcmgr -s <svcname> enable` does not enable disabled resources."
    },
    {
        "section": "DEFAULT",
        "keyword": "env",
        "inheritance": "head",
        "default_text": "<same as node env>",
        "candidates": rcEnv.allowed_svc_envs,
        "text": "A non-PRD service can not be brought up on a PRD node, but a PRD service can be startup on a non-PRD node (in a DRP situation). The default value is the node env."
    },
    {
        "section": "DEFAULT",
        "keyword": "lock_timeout",
        "default": 60,
        "convert": "duration",
        "text": "A duration expression, like '1m30s'. The maximum wait time for the action lock acquire. The svcmgr --waitlock option overrides this parameter."
    },
    {
        "section": "DEFAULT",
        "keyword": "nodes",
        "inheritance": "head",
        "at": True,
        "convert": "nodes_selector",
        "default": "{clusternodes}",
        "default_text": "<hostname of the current node>",
        "text": "A node selector expression specifying the list of cluster nodes hosting service instances."
    },
    {
        "section": "DEFAULT",
        "keyword": "drpnodes",
        "inheritance": "head",
        "at": True,
        "convert": "list_lower",
        "default": [],
        "default_text": "",
        "text": "Alternate backup nodes, where the service could be activated in a DRP situation if the 'drpnode' is not available. These nodes are also data synchronization targets for 'sync' resources.",
        "example": "node1 node2"
    },
]


KEYS = KeywordStore(
    keywords=PRIVATE_KEYWORDS+KEYWORDS,
    deprecated_keywords=DEPRECATED_KEYWORDS,
    deprecated_sections=DEPRECATED_SECTIONS,
    template_prefix="template.cluster.",
    base_sections=BASE_SECTIONS,
    has_default_section=False,
 )

if __name__ == "__main__":
    if len(sys.argv) == 2:
        fmt = sys.argv[1]
    else:
        fmt = "text"

    KEYS.write_templates(fmt=fmt)
