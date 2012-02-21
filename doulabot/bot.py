from gevent import monkey
monkey.patch_all()

from copy import copy
from doula import java
from doula import push as pushmod
from doula import pypkg
from doula import qtasks
from doula import rq
from doula import utils
from gevent import sleep, spawn
from irclib import IRC
from irclib import ServerConnectionError
from irclib import SimpleIRCClient
from itertools import count
from lxml import html
from peak.rules import abstract
from peak.rules import when
import argparse
import logging
import pyres
import re
import redis
import select
import sys
import traceback


logger = logging.getLogger(__name__)


class GIRC(IRC):
    """
    A green sleeping ircobj
    """
    def process_once(self, timeout=0):
        """Process data from connections once.

        Arguments:

            timeout -- How long the select() call should wait if no
                       data is available.

        This method should be called periodically to check and process
        incoming data, if there are any.  If that seems boring, look
        at the process_forever method.
        """
        sockets = map(lambda x: x._get_socket(), self.connections)
        sockets = filter(lambda x: x != None, sockets)
        if sockets:
            (i, o, e) = select.select(sockets, [], [], timeout)
            self.process_data(i)
        else:
            sleep(timeout)
        self.process_timeout()
        


class BaseBot(SimpleIRCClient):
    nickname = 'bot' # command name
    channel = '#testing'
    server = 'irc.corp.surveymonkey.com'
    #server = 'irc'
    port = 6667
    localaddress=""
    localport=0
    password=None
    username=None
    ircname=None
    ssl=True
    ipv6=False
    irc_klass = GIRC
    redis_server = 'localhost:6379'
    notification_batch = range(10)
    notification_list = 'irc.notifications'
    exec_str = "|>"
    cmd_end = ":"
    retry = 30
    retry_interval = 10
    
    def __init__(self, verbose=False, channels=[channel]):
        SimpleIRCClient.__init__(self)
        self.count = count()
        self.verbose = verbose
        self.logged = False
        self._irc_log = []
        host, port = self.redis_server.split(':')
        self.redis = redis.Redis(host, int(port))
        self.channels = channels
        self.channel = channels[0]

    
    @classmethod
    def logon(cls,  logging_level=logging.DEBUG, channels=[channel], nickname=None):
        cls.setup_logging(logging_level)
        bot = cls(channels=channels)
        if not nickname:
            nickname = cls.nickname
        bot.username = bot.ircname = bot.nickname = nickname

        for try_ in range(cls.retry):
            try:
                bot.connect(cls.server, cls.port, nickname, password=cls.password,
                            username=cls.username, ircname=cls.ircname, localaddress=cls.localaddress,
                            localport=cls.localport, ssl=cls.ssl, ipv6=cls.ipv6)
                bot.start()
                return bot
            except ServerConnectionError as e:
                logger.error(e)
                sleep(cls.retry_interval)

        sys.exit(logger.error("Failed to connect. out of here."))

    def run_forever(self, timeout=0.2):
        while 1:
            self.ircobj.process_once(timeout)
            spawn(self.handle_notifications)

    def handle_notifications(self):
        """
        Read msgs from a redis list and broadcast them to current
        channel
        """
        for bn in self.notification_batch:
            msg = self.redis.rpop(self.notification_list)
            sleep(0)
            if msg:
                self.broadcast(msg)
            sleep(0)                

    def broadcast(self, msg):
        if msg.startswith('/me'):
            msg = msg.replace('/me', '%sACTION ' %chr(1))
        self.connection.privmsg(self.channel, msg + ' ')

    @classmethod
    def setup_logging(cls, level):
        root = logging.getLogger()
        if root.handlers:
            root.handlers = []
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        root.setLevel(level)
        root.addHandler(ch)

    @abstract
    def _dispatcher(self, c, e):
        """
        Handles global event dispatch
        """
    @when(_dispatcher, "True")
    def on_noop(self, c, e):
        self.msglog(e)

    def msglog(self, e):
        method = e.eventtype()
        args = copy(e.arguments())
        target = e.target()
        args = "[%s]" %", ".join(args)
        #logger.info("%s "*3, cyan(method), red(target), yellow(args))
        logger.info("%s "*3, method, target, args)
        self.logged = True

    @when(_dispatcher, "e.eventtype() == 'disconnect'")
    def on_disconnect(self, c, e):
        sys.exit(logger.error('Disconnected'))

    @when(_dispatcher, "e.eventtype() == 'all_raw_messages'")
    def on_arm(self, c, e):
        pass
        
    @when(_dispatcher, "e.eventtype() == 'pubmsg'")
    def on_pubmsg(self, c, e):
        self.msglog(e)
        args = copy(e.arguments())
        if args and args[0].startswith(self.exec_str):
            command = args[0]
            command = command.replace(self.exec_str, '')
            pieces = command.split(self.cmd_end, 1)
            if len(pieces) == 2:
                command, args = pieces
            else:
                args = []
            command = command.strip()
            try:
                self.command(e.source(), command, args)
            except Exception, e:
                self.broadcast('Error: %s' %e.message)
                logger.error(traceback.format_exc())

    def command(self, source, command, cxn):
        """
        dispatch for commands
        """
        self.log_msg(source, command)

    def noop(self, source, command, cxn):
        logger.debug("%s %s", source, command)

    def log_msg(self, source, command):
        self._irc_log.append((source, command))

    @when(_dispatcher, "e.eventtype() == 'privnotice'")
    def on_privnotice(self, c, e):
        if e.arguments()[0].startswith('*** You are connected using SSL cipher'):
            for channel in self.channels:
                c.join(channel)

    @when(_dispatcher, "e.eventtype() == 'ping'")
    def on_ping(self, c, e):
        c.pong(c.server, c.server)
            
    def start(self):
        """Start the IRC client."""
        try:
            self.run_forever()
        finally:
            self.connection.disconnect()


def run_doulabot(args=None):
    if args is None:
        parser = argparse.ArgumentParser(description='Run the doulabot')
        parser.add_argument('channels', metavar='C', nargs='*', default=['testing'],
                            help='channels for the bot to logon to')
        parser.add_argument('-n', dest='nickname', type=str, default=None,
                            help='irc name for bot')
        args = parser.parse_args()
        
    DoulaBot.logon(channels=['#%s' %x for x in args.channels], nickname=args.nickname)


class QBot(BaseBot):
    """
    Bot to run fab processes and report back
    """

    def __init__(self, verbose=False, channels=[BaseBot.channel]):
        BaseBot.__init__(self, verbose, channels)
        self.resq = pyres.ResQ(self.redis)

    def enqueue(self, *args, **kw):
        return self.resq.enqueue(*args, **kw)


from setuptools.package_index import distros_for_url

class DoulaBot(QBot):
    """
    Bot for pushing and releasing
    """
    default_gitssh = "git@code.corp.surveymonkey.com"
    default_ghuser = "devmonkeys"
    svnprefix = "svn://svn/s"
    default_svntree = "py"
    nickname = 'doula'
    username = nickname 
    mcmd = "command.startswith('%s:')"
    cmd = "command.startswith('%s')"
    cmd_is = "command == '%s'"
    notification_list = rq.notify_channel
    index_url = "http://yorick:9003/index"
    channel = '#release'

    v_regex = re.compile('^[a-zA-Z]+-([a-zA-Z0-9\.]+).tar.gz')
    v_splitter = re.compile('(rc|a|b|dev|\.)')
    re_d = re.compile('\d')
    cmd_end = ":"

    @property
    def exec_str(self):
        return self.nickname + ':'
    
    @abstract
    def command(self, source, command, args):
        """
        dispatch for commands
        """
        pass

    noop = when(command, 'True')(BaseBot.noop)

    def action_msg(self, cxn, msg):
        cxn.privmsg(self.channel, '%sACTION %s ' %(chr(1), msg))

    @when(command, cmd_is % 'dance')
    def shake_booty(self, source, command, args):
        user, address = source.split('!')
        if user.startswith('doug'):
            self.broadcast("/me refuses to dance for %s" %user)
        else:
            self.broadcast("/me shakes it's metal booty for %s" %user)

    @when(command, cmd_is % 'svn')
    def svnls(self, source, command, args):
        """
        dbot: svnls: tree/path
        """
        user, handle = source.split('!')
        if args == '':
            return self.broadcast("%s: you have to give me a path to work with..." %user)
        return self.enqueue(qtasks.svn_ls, args)

    def _prep_release(self, source, args):
        """
        Does some basic error checking and data preparation to be used
        by commands doing a release.
        """
        user, handle = source.split('!')
        if args == '':
            return self.broadcast("%s: you must give a python package to release" %user)
        pkgv = args.strip()
        self.broadcast("/me queues %s for release for %s." %(pkgv, user))
        parts = pkgv.split('@')
        branch = None
        if len(parts) == 2:
            pkgv, branch = parts
        tokens = pkgv.split('/')            
        return pkgv, branch, tokens, user

    @when(command, cmd_is % 'relsvn')
    def svn_release(self, source, command, args):
        """
        dbot: relsvn: [tree_other_than_py]pkg-0.9.8rc2[@branch]
        """
        pkgv, branch, tokens, user = self._prep_release(source, args)

        svntree = self.default_svntree
        if len(tokens) == 2:
            svntree, pkgv = tokens

        svnprefix = utils.urljoin(self.svnprefix, svntree)
        return self.enqueue(pypkg.pyrelease_svn_task, pkgv, branch, svnprefix, user)

    @when(command, cmd_is % 'relgit')
    def git_release(self, source, command, args):
        """
        dbot: relgit: [user_or_group/]pkg-0.1.1[@branch] (from git)
        """
        pkgv, branch, tokens, user = self._prep_release(source, args)

        ghuser = self.default_ghuser
        if len(tokens) == 2:
            ghuser, pkgv = tokens

        #gitaddress = "%s:%s" %(self.default_gitssh, ghuser)
        return self.enqueue(pypkg.pyrelease_git_task, pkgv, branch, ghuser, user)

    javasrc = set(('billingdal', 'userdal'))

    @when(command, cmd_is % 'reljava')
    def release_java(self, source, command, args):
        """
        doula: reljava: {billingdal|userdal}-1.0rc2@branchname
        """
        user, handle = source.split('!')
        if args == '':
            return self.broadcast("%s: you must give a java sourcetree (Billing or UserAccount) to release" %user)
        pkgv = args.strip()
        self.broadcast("/me queues %s for release for %s." %(pkgv, user))
        parts = pkgv.split('@')
        branch = None
        if len(parts) == 2:
            pkgv, branch = parts
        pv = pkgv.split('-')
        assert len(pv) == 2, "You must include a src tree and a version"
        assert pv[0] in self.javasrc, "%s not in available srctrees: %s" %(pv[0], self.javasrc)
        return self.enqueue(java.DALRelease, pkgv, branch)

    @when(command, cmd_is % 'help')
    def help(self, source, command, args):
        for name in sorted(['svnls', 'current_version', 'git_release', 'svn_release', 'versions', 'push', 'cycle', 'release_java']):
            method = getattr(self, name)
            self.broadcast(method.__doc__.strip())

    @when(command, cmd_is % 'cycle')
    def cycle(self, source, command, args, task=qtasks.cycle2):
        """
        doula:cycle: bill*@mt1 | billweb:8100@mt2
        """
        user, o = source.split('!')
        args = [x.strip() for x in args.split('@')]
        if len(args) != 2:
            self.broadcast("%s: wrong format for cycle" %user)
            self.broadcast('help for cycle: cycle: someapp@mt1' )
        app, mt = args
        self.broadcast('/me queues cycle for %s on %s' %(app, mt))
        self.enqueue(task, app, mt, user)

    @when(command, ' or '.join([cmd_is % 'push', cmd_is % 'push2']))
    def push(self, source, command, args, task=pushmod.push2):
        """
        doula:push: howler-0.9.8rc2 -> billweb@mt2,billweb@mt2
        """
        user, o = source.split('!')
        pkgv, mts = [x.strip() for x in args.split('->')]
        mts = [x.strip() for x in mts.split(',')]
            
        for mt in mts:
            self.broadcast('/me queues push to %s of %s for %s' %(mt, pkgv, user))
            self.enqueue(task, pkgv, mt, user)

    def _fetch_versions(self, pkg):
        root = html.parse("%s/%s" %(self.index_url, pkg.strip())).getroot()
        return (x.text for x in root.cssselect('a'))

    @when(command, cmd_is % 'v')
    def versions(self, source, command, args):
        """
        doula:v:smlib.billing  (lists all available releases)
        """
        pkg = args
        versions = self.sorted_versions(self._fetch_versions(pkg))
        for version in versions:
            sleep(0.5)
            self.broadcast(version)

    @staticmethod
    def get_distro(url):
        return next(distros_for_url(url))

    def sorted_versions(self, raw_vs, reverse=False):
        distros = (self.get_distro(url).parsed_version for url in raw_vs)
        distros = sorted(distros, reverse=reverse)
        for dist in distros:
            yield "-".join(dist.egg_name().rsplit('-')[:-1])

    @when(command, cmd_is % 'cv')
    def current_version(self, source, command, args):
        """
        doula:cv:smlib.billing  (shows current version by best guess)
        """
        pkg = args
        try:
            vs = self._fetch_versions(pkg)
        except IOError:
            return self.broadcast("/me could not find %s" %pkg)
        
        if vs:
            versions = self.sorted_versions(vs, reverse=True)
            self.broadcast("%s-%s" %(pkg, next(versions)))            
 

    
        

