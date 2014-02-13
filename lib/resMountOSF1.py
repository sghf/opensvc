#
# Copyright (c) 2012 Christophe Varoqui <christophe.varoqui@opensvc.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# To change this template, choose Tools | Templates
# and open the template in the editor.

import os

import rcMountsOSF1 as rcMounts
import resMount as Res
from rcUtilities import qcall, protected_mount, getmount
from rcGlobalEnv import rcEnv
import rcExceptions as ex
from stat import *

def try_umount(self):
    cmd = ['umount', self.mountPoint]
    (ret, out, err) = self.vcall(cmd, err_to_warn=True)
    if ret == 0:
        return 0

    if "not currently mounted" in err:
        return 0

    """ don't try to kill process using the source of a 
        protected bind mount
    """
    if protected_mount(self.mountPoint):
        return 1

    """ best effort kill of all processes that might block
        the umount operation. The priority is given to mass
        action reliability, ie don't contest oprator's will
    """
    cmd = ['sync']
    (ret, out, err) = self.vcall(cmd)

    for i in range(4):
        cmd = ['fuser', '-kcv', self.mountPoint]
        (ret, out, err) = self.vcall(cmd, err_to_info=True)
        self.log.info('umount %s'%self.mountPoint)
        cmd = ['umount', self.mountPoint]
        ret = qcall(cmd)
        if ret == 0:
            break

    return ret


class Mount(Res.Mount):
    def __init__(self, rid, mountPoint, device, fsType, mntOpt, always_on=set([]),
                 snap_size=None, disabled=False, tags=set([]), optional=False,
                 monitor=False, restart=0):
        self.Mounts = None
        Res.Mount.__init__(self, rid, mountPoint, device, fsType, mntOpt,
                           snap_size, always_on,
                           disabled=disabled, tags=tags, optional=optional,
                           monitor=monitor, restart=restart)
        self.fsck_h = {
            'ufs': {'bin': 'fsck', 'cmd': ['fsck', '-p', self.device], 'allowed_ret': []},
        }

    def is_up(self):
        self.Mounts = rcMounts.Mounts()
        ret = self.Mounts.has_mount(self.device, self.mountPoint)
        if ret:
            return True

        if self.fsType not in ["advfs"] + self.netfs:
            # might be a loopback mount
            try:
                mode = os.stat(self.device)[ST_MODE]
            except:
                self.log.debug("can not stat %s" % self.device)
                return False

        return False

    def devlist(self):
        return self.disklist()

    def disklist(self):
        if '#' in self.device:
            dom, fset = self.device.split('#')
            import rcAdvfs
            try:
                o = rcAdvfs.Fdmns()
                d = o.get_fdmn(dom)
            except rcAdvfs.ExInit as e:
                return set([])
            if d is None:
                return set([])
            return set(d.list_volnames())
        else:
            return set([self.device])

    def can_check_writable(self):
        return True

    def start(self):
        if self.Mounts is None:
            self.Mounts = rcMounts.Mounts()
        Res.Mount.start(self)

        if self.is_up() is True:
            self.log.info("fs(%s %s) is already mounted"%
                (self.device, self.mountPoint))
            return 0

        self.fsck()
        if not os.path.exists(self.mountPoint):
            os.makedirs(self.mountPoint, 0o755)
        if self.fsType != "":
            fstype = ['-t', self.fsType]
        else:
            fstype = []
        if self.mntOpt != "":
            mntopt = ['-o', self.mntOpt]
        else:
            mntopt = []
        cmd = ['mount']+fstype+mntopt+[self.device, self.mountPoint]
        (ret, out, err) = self.vcall(cmd)
        if ret != 0:
            raise ex.excError
        self.Mounts = None
        self.can_rollback = True

    def stop(self):
        if self.Mounts is None:
            self.Mounts = rcMounts.Mounts()
        if self.is_up() is False:
            self.log.info("fs(%s %s) is already umounted"%
                    (self.device, self.mountPoint))
            return
        for i in range(3):
            ret = try_umount(self)
            if ret == 0: break
        if ret != 0:
            self.log.error('failed to umount %s'%self.mountPoint)
            raise ex.excError
        self.Mounts = None

if __name__ == "__main__":
    for c in (Mount,) :
        help(c)

