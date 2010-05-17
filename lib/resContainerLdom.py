#
# Copyright (c) 2009 Christophe Varoqui <christophe.varoqui@free.fr>'
# Copyright (c) 2009 Cyril Galibern <cyril.galibern@free.fr>'
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
import resources as Res
import rcExceptions as ex
from rcUtilities import qcall
import resContainer

class Ldom(resContainer.Container):
    def __init__(self, name, optional=False, disabled=False):
        resContainer.Container.__init__(self, rid="ldom", name=name, type="container.ldom",
                                        optional=optional, disabled=disabled)

    def __str__(self):
        return "%s name=%s" % (Res.Resource.__str__(self), self.name)

    def check_capabilities(self):
        cmd = ['/usr/sbin/ldm', 'list' ]
        (ret, out) = self.call(cmd)
        if ret != 0:
            return False
        return True

    def state(self):
        """ ldm state : None/inactive/bound/active
            ldm list -p domainname outputs:
                VERSION
                DOMAIN|[varname=varvalue]*
        """
        cmd = ['/usr/sbin/ldm', 'list', '-p', self.name]
        (ret, out) = self.call(cmd)
        if ret != 0:
            return None
        for word in out.split("|"):
            a=word.split('=')
            if len(a) == 2:
                if a[0] == 'state':
                    return a[1]
        return None

    def ping(self):
        timeout = 1
        cmd = ['ping', self.name, repr(timeout)]
        ret = qcall(cmd)
        if ret == 0:
            return True
        return False

    def container_action(self,action):
        cmd = ['/usr/sbin/ldm', action, self.name]
        (ret, buff) = self.vcall(cmd)
        if ret != 0:
            raise ex.excError
        return None

    def container_start(self):
        """ ldm bind domain
            ldm start domain
        """
        state = self.state()
        if state == 'None':
            raise ex.excError
        if state == 'inactive':
            self.container_action('bind')
        if state == 'bound' :
            self.container_action('start')

    def container_forcestop(self):
        """ ldm unbind domain
            ldm stop domain
        """
        try:
            self.container_action('stop')
        except ex.excError:
            pass
        self.container_action('unbind')

    def container_stop(self):
        """ launch init 5 into container
            wait_for_shutdown
            ldm stop domain
            ldm unbind domain
        """
        state = self.state()
        if state == 'None':
            raise ex.excError
        if state == 'inactive':
            return None
        if state == 'bound' :
            self.container_action('unbind')
        if state == 'active' :
            cmd = self.runmethod + [ '/usr/sbin/init', '5' ]
            (ret, buff) = self.vcall(cmd)
            if ret == 0:
                try:
                    self.wait_for_shutdown()
                except ex.excError:
                    pass
            self.container_forcestop()

    def check_manual_boot(self):
        cmd = ['/usr/sbin/ldm', 'list-variable', 'auto-boot?', self.name]
        (ret, out) = self.call(cmd)
        if ret != 0:
            return False
        if out != 'auto-boot?=False' :
            return True
        self.log.info("Auto boot should be turned off")
        return False

    def is_down(self):
        if self.state() == 'inactive':
            return True
        return False

    def is_up(self):
        if self.state() == 'active':
            return True
        return False

