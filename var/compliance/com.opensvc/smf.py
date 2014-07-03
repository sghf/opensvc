#!/opt/opensvc/bin/python

"""
The ENV variable format is json-serialized [list of dict]:
[
 {
  "fmri": "svc:/network/ntp"
  "prop": "config/slew_always"
  "type": "boolean"
  "value": "true"
  "inorder": 0
  "create": 1
  "reload": 0
  "sleep": 0
 }
 {
  "fmri": "svc:/network/dns/client"
  "prop": "config/nameserver"
  "type": "net_address"
  "value": "172.30.65.165 172.30.65.164"
  "inorder": 0
  "create": 1
  "reload": 0
  "sleep": 6
 }
 {
  "fmri": "svc:/network/dns/client"
  "prop": "config/search"
  "type": "astring"
  "value": "cpdev.local cpprod.root.local cpgrp.root.local"
  "inorder": 1
  "create": 1
  "reload": 0
  "sleep": 9
 }
]
"""

import os
import sys
import json
import re

from subprocess import *

sys.path.append(os.path.dirname(__file__))

from comp import *

class AutoInst(dict):
    """autovivification feature."""
    def __getitem__(self, item):
        try:
            return dict.__getitem__(self, item)
        except KeyError:
            value = self[item] = type(self)()
            return value

class SmfCfgS(object):
    def __init__(self, prefix='OSVC_COMP_SMF_CFGS_'):
        self.prefix = prefix.upper()
        self.sysname, self.nodename, self.osn, self.solv, self.machine = os.uname()
        self.data = []
        self.smfs = AutoInst()
        self.osver = float(self.osn)

        if self.osver < 5.11:
            print 'Only used on Solaris 11 and behond'
            return

        if "OSVC_COMP_SERVICES_SVC_NAME" not in os.environ:
            os.environ["OSVC_COMP_SERVICES_SVC_NAME"] = ""

        for k in [ key for key in os.environ if key.startswith(self.prefix)]:
            try:
                self.data += self.add_fmri(os.environ[k])
            except ValueError:
                print >>sys.stderr, 'failed to parse variable', os.environ[k]

        for f in self.data:
            s,p,t,v = self.get_fmri(f['fmri'], f['prop'])
            if s is None:
                continue
            cre = False
            if p is None:
                if f['create'] == 0:
                    print >>sys.stderr, 'FMRI:%s, PROP:%s is absent and create is False' %(s,f['prop'])
                    continue
                else:
                    p = f['prop']
                    cre = True
            if f['inorder'] == 0:
                ino = False
            else:
                ino = True
            if f['reload'] == 0:
                rel = False
            else:
                rel = True
            
            self.smfs[f['fmri']][p] = { 'val': f['value'], 'rval': v,
                                        'typ': f['type'] , 'rtyp': t,
                                        'ino': ino,
                                        'cre': cre,
                                        'rel': rel,
                                        'slp': f['sleep']
                                      }

    def subst(self, v):
        if type(v) == list:
            l = []
            for _v in v:
                l.append(self.subst(_v))
            return l
        if type(v) != str and type(v) != unicode:
            return v
	p = re.compile('%%ENV:\w+%%')
        for m in p.findall(v):
            s = m.strip("%").replace('ENV:', '')
            if s in os.environ:
                _v = os.environ[s]
            elif 'OSVC_COMP_'+s in os.environ:
                _v = os.environ['OSVC_COMP_'+s]
            else:
                print >>sys.stderr, s, 'is not an env variable'
                raise NotApplicable()
            v = v.replace(m, _v)
        return v

    def add_fmri(self, v):
        if type(v) == str or type(v) == unicode:
            d = json.loads(v)
        else:
            d = v
        l = []

        # recurse if multiple FMRI are specified in a list of dict
        if type(d) == list:
            for _d in d:
                l += self.add_fmri(_d)
            return l

        if type(d) != dict:
            print >>sys.stderr, "not a dict:", d
            return l

        if 'fmri' not in d:
            print >>sys.stderr, 'FMRI should be in the dict:', d
            RET = RET_ERR
            return l
        if 'prop' not in d:
            print >>sys.stderr, 'prop should be in the dict:', d
            RET = RET_ERR
            return l
        if 'value' not in d:
            print >>sys.stderr, 'value should be in the dict:', d
            RET = RET_ERR
            return l
        if 'create' in d:
            if d['create'] == 1:
                if not 'type' in d:
                    print >>sys.stderr, 'create True[1] needs a type:', d
                    RET = RET_ERR
                    return l
        for k in ('fmri', 'prop', 'value', 'inorder', 'type', 'create', 'sleep'):
            if k in d:
                d[k] = self.subst(d[k])
        return [d]
            
    def fixable(self):
        return RET_NA

    def get_fmri(self, s, p):
        cmd = ['/usr/sbin/svccfg','-s', s, 'listprop', p]
        po = Popen(cmd, stdout=PIPE, stderr=PIPE)
        out,err = po.communicate()
        if po.returncode != 0:
            if "doesn't match" in err:
                print '%s is absent => IGNORED' %self.service
                return None,None,None,None
            else:
                print >>sys.stderr, ' '.join(cmd)
                raise ComplianceError()
        if len(out) < 2:
                return s,None,None,None

        x = out.strip('\n').split()
        if x[0] != p:
            print >>sys.stderr, ' '.join([s, 'wanted:%s'%p, 'got:%s'%x[0]])
            raise ComplianceError()
        return s,p,x[1],x[2:]

    def check_smf_prop_cre(self, s, p, verbose=True):
        r = RET_OK
        if self.smfs[s][p]['cre']:
            if verbose:
                print >>sys.stderr, 'NOK: %s Prop %s shall be created' %(s,p)
            r |= RET_ERR
            if self.smfs[s][p]['typ'] == '' or self.smfs[s][p]['typ'] == None:
                if verbose:
                    print >>sys.stderr, 'NOK: %s type must be specified to create %s' %(s,p)
        return r,self.smfs[s][p]['cre']

    def check_smf_prop_typ(self, s, p, verbose=True):
        r = RET_OK
        if self.smfs[s][p]['typ'] == '' or self.smfs[s][p]['typ'] == None:
            if verbose:
                print '%s Prop %s type is not checked' %(s,p)
        elif self.smfs[s][p]['typ'] != self.smfs[s][p]['rtyp']:
            if verbose:
                print >>sys.stderr, 'NOK: %s Prop %s type Do Not match, got:%s, expected:%s' %(s,p,self.smfs[s][p]['rtyp'],self.smfs[s][p]['typ'])
            r |= RET_ERR
        else:
            if verbose:
                print '%s Prop %s type %s is OK' %(s,p,self.smfs[s][p]['typ'])
            if self.smfs[s][p]['typ'] == '' or self.smfs[s][p]['typ'] == None:
                if verbose:
                    print >>sys.stderr, 'NOK: %s type must be specified to create %s' %(s,p)
        return r

    def check_smf_prop_val(self, s, p, verbose=True):
        r = RET_OK
        rvs = ' '.join(self.smfs[s][p]['rval'])
        if self.smfs[s][p]['ino']:
            if self.smfs[s][p]['val'] == rvs:
                if verbose:
                    print '%s Prop %s values match in right order [%s]' %(s,p,rvs)
            else:
                if verbose:
                    print >>sys.stderr, 'NOK: %s Prop %s values Do Not match, got:[%s], expected:[%s]' %(s,p,rvs,self.smfs[s][p]['val'])
        else:
            vv = self.smfs[s][p]['val'].split()
            m = True
            for v in vv:
                if not v in self.smfs[s][p]['rval']:
                    if verbose and len(self.smfs[s][p]['rval']) > 1 :
                        print >>sys.stderr, '%s Prop %s notfound %s' %(s,p,v)
                    m = False
                else:
                    if verbose and len(self.smfs[s][p]['rval']) > 1 :
                        print '%s Prop %s found %s' %(s,p,v)
            if m:
                if verbose:
                    print '%s Prop %s values match [%s]' %(s,p,rvs)
            else:
                if verbose:
                    print >>sys.stderr, 'NOK: %s Prop %s values Do Not match, got:[%s], expected:[%s]' %(s,p,rvs,self.smfs[s][p]['val'])
                r |= RET_ERR
        return r

    def check_smfs(self, verbose=True):
        r = RET_OK
        for s in self.smfs:
            for p in self.smfs[s]:
                """
                print 'FMRI: ', s, 'PROP: ', p, 'TYP: ', self.smfs[s][p]['typ'], 'RTYP: ', self.smfs[s][p]['rtyp'], type(self.smfs[s][p]['val']), type(self.smfs[s][p]['rval'])
                print '	', 'VALS: ', self.smfs[s][p]['val']
                print '	', 'RVALS: ', self.smfs[s][p]['rval']
                """
                rx,c = self.check_smf_prop_cre(s, p, verbose=verbose)
                r |= rx
                if not c:
                    r |= self.check_smf_prop_typ(s, p, verbose=verbose)
                r |= self.check_smf_prop_val(s, p, verbose=verbose)
        return r

    def fix_smfs(self, verbose=False):
        r = RET_OK
        cmds = []
        for s in self.smfs:
            for p in self.smfs[s]:
                rx,c = self.check_smf_prop_cre(s, p, verbose=verbose)
                if c:
                   if rx == 0 :
                       print '%s try to add prop %s = %s' %(s,p,self.smfs[s][p]['val'])
                       cmds += ['/usr/sbin/svccfg', '-s', s, 'setprop', p, '=', self.smfs[s][p]['typ']+':', self.smfs[s][p]['val']]
                   else:
                       print >>sys.stderr, 'NOK: %s cannot add prop %s without a valid type' %(s,p)
                       r |= RET_ERR 
                else:
                   ry = self.check_smf_prop_val(s, p, verbose=verbose)
                   if ry != 0:
                       print '%s try to fix %s = %s' %(s,p,self.smfs[s][p]['val'])
                       cmds += ['/usr/sbin/svccfg', '-s', s, 'setprop', p, '=', self.smfs[s][p]['val']]
                if len(cmds) != 0:
                   if self.smfs[s][p]['rel']:
                       cmds += ['/usr/sbin/svcadm', 'refresh' ,s]
                       if self.smfs[s][p]['slp'] != 0:
                           cmds += ['/usr/bin/sleep' , '%d'%self.smfs[s][p]['slp']]
        for cmd in cmds:
            print 'EXEC:', ' '.join(cmd)
            p = Popen(cmd, stdout=PIPE, stderr=PIPE)
            out,err = p.communicate()
            if p.returncode != 0:
               print >>sys.stderr, 'Code=%s %s' %(p.returncode,err)
               r |= RET_ERR
        return r

    def check(self):
        if self.osver < 5.11:
            return RET_NA
        r = self.check_smfs()
        return r

    def fix(self):
        if self.osver < 11:
            return RET_NA
        r = self.fix_smfs()
        return r

if __name__ == "__main__":
    syntax = """syntax:
      %s check|fixable|fix]"""%sys.argv[0]
    try:
        action = sys.argv[1]
        o = SmfCfgS()
        if action == 'check':
            RET = o.check()
        elif action == 'fix':
            RET = o.fix()
        elif action == 'fixable':
            RET = o.fixable()
        else:
            print >>sys.stderr, "unsupported argument '%s'"%sys.argv[2]
            print >>sys.stderr, syntax
            RET = RET_ERR
    except NotApplicable:
        sys.exit(RET_NA)
    except:
        import traceback
        traceback.print_exc()
        sys.exit(RET_ERR)

    sys.exit(RET)
