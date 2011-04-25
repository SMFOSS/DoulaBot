from irclib import Event
from mock import Mock, patch
from unittest import TestCase
import sys


class BaseBotCase(TestCase):
    klass = None
    def setUp(self):
        self.bot = self.klass()
        self.cxn = Mock()


def test_bot_factory():
    from peak.rules import before
    from doulabot import bot
    class TheTestBot(bot.BaseBot):
        @before(bot.BaseBot._dispatcher, "e.eventtype() == 'pubmsg'")
        def loggit(self, c, e):
            log = getattr(self, '_irc_log', [])
            log.append(e.arguments()[0])
    return TheTestBot()


class TestBaseBot(BaseBotCase):
    klass = staticmethod(test_bot_factory)

    def test_channel_join(self):
        event = Event('privnotice', 'dougsmom', 'yourmom', ['*** You are connected using SSL cipher Woooooo'])
        self.bot._dispatcher(self.cxn, event)
        action, (channel,), kw = self.cxn.method_calls.pop()
        assert action == 'join'
        assert channel == '#testing'

    def test_pingpong(self):
        event = Event('ping', 'dougsmom', 'yourmom')
        self.bot._dispatcher(self.cxn, event)
        action, (server, server), kw = self.cxn.method_calls.pop()
        assert action == 'pong'
        assert isinstance(server, Mock) 

    def test_channel_pubmsg(self):
        event = Event('pubmsg', 'dougsmom', 'yourmom', ['%s: you are it' %self.bot.nickname])
        self.bot._dispatcher(self.cxn, event)
        cmd = self.bot._irc_log.pop()
        assert cmd == 'bot: you are it'


def dbot_factory():
    from doulabot import bot
    return bot.DoulaBot()


class TestRepoBot(BaseBotCase):
    """
    Test the release bot
    """
    klass = staticmethod(dbot_factory)

    def setUp(self):
        BaseBotCase.setUp(self)
        self.bot.connection = Mock()        

    @patch('doula.bot.QBot.enqueue')
    def test_release(self, q_mock):
        from doula.pypkg import pyrelease_task
        self.bot.command('bob!bob@123', 'rel', 'path-0.2.3@branchname')
        (task, pkgv, branch, repo), kw = q_mock.call_args
        assert not kw
        assert task is pyrelease_task
        assert pkgv == 'path-0.2.3'
        assert branch == 'branchname'
        assert repo == 'svn://svn/s/py'

    @patch('doula.bot.QBot.enqueue')
    def test_java_release(self, q_mock):
        self.bot.connection = Mock()
        self.bot.command('bob!bob@123', 'reljava', 'billingdal-1.0@branchname')

    @patch('doula.bot.QBot.enqueue')
    def test_java_release_assert_version(self, q_mock):
        try:
            self.bot.command('bob!bob@123', 'reljava', 'billingdal@branchname')
            assert False, "Should raise an assertion error"
        except Exception, e:
            assert isinstance(e, AssertionError), e
            assert e.message == 'You must include a srctree and a version'

    @patch('doula.bot.QBot.enqueue')
    def test_java_release_assert_srctree(self, q_mock):
        try:
            self.bot.command('bob!bob@123', 'reljava', 'bilingdal-0.1@branchname')
            assert False, "Should raise an assertion error"
        except Exception, e:
            assert isinstance(e, AssertionError), e
            assert e.message == "bilingdal not in available srctrees: set(['billingdal', 'userdal'])", e
