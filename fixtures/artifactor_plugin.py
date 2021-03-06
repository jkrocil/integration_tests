"""An example config::

    artifactor:
        log_dir: /home/test/workspace/cfme_tests/artiout
        per_run: test #test, run, None
        reuse_dir: True
        squash_exceptions: False
        threaded: False
        server_address: 127.0.0.1
        server_port: 21212
        server_enabled: True
        plugins:

``log_dir`` is the destination for all artifacts

``per_run`` denotes if the test artifacts should be group by run, test, or None

``reuse_dir`` if this is False and Artifactor comes across a dir that has
already been used, it will die
"""

from artifactor import ArtifactorClient
import pytest
from urlparse import urlparse
from utils import log
from utils.conf import env
from utils.net import random_port
from utils.path import log_path
import atexit


class DummyClient(object):
    def fire_hook(self, *args, **kwargs):
        return

    def __nonzero__(self):
        # DummyClient is always False, so it's easy to see if we have an artiactor client
        return False

art_config = env.get('artifactor', {})

if art_config:
    # If server_port isn't set, pick a random port
    if 'server_port' not in art_config:
        port = random_port()
        art_config['server_port'] = port
    art_client = ArtifactorClient(art_config['server_address'], art_config['server_port'])
else:
    art_client = DummyClient()

SLAVEID = None
if env.get('slaveid', None):
    SLAVEID = env['slaveid']


def pytest_addoption(parser):
    parser.addoption("--run-id", action="store", default=None,
                     help="A run id to assist in logging")


@pytest.mark.tryfirst
def pytest_configure(config):
    if not art_client:
        return

    if SLAVEID:
        art_client.port = config.option.artifactor_port
    else:
        import artifactor
        from artifactor.plugins import merkyl, logger, video, filedump, reporter
        from artifactor import parse_setup_dir

        art = artifactor.artifactor

        if 'log_dir' not in art_config:
            art_config['log_dir'] = log_path.join('artifacts').strpath
        art.set_config(art_config)

        art.register_plugin(merkyl.Merkyl, "merkyl")
        art.register_plugin(logger.Logger, "logger")
        art.register_plugin(video.Video, "video")
        art.register_plugin(filedump.Filedump, "filedump")
        art.register_plugin(reporter.Reporter, "reporter")
        art.register_hook_callback('filedump', 'pre', parse_setup_dir,
                                   name="filedump_dir_setup")

        artifactor.initialize()
        ip = urlparse(env['base_url']).hostname

        art.configure_plugin('merkyl', ip=ip)
        art.configure_plugin('logger')
        art.configure_plugin('video')
        art.configure_plugin('filedump')
        art.configure_plugin('reporter')
        art.fire_hook('start_session', run_id=config.getvalue('run_id'))

        # Stash this where slaves can find it
        config.option.artifactor_port = art_client.port
        log.logger.info('artifactor listening on port %d', art_client.port)


def pytest_runtest_protocol(item):
    art_client.fire_hook('start_test', test_location=item.location[0], test_name=item.location[2],
                         slaveid=SLAVEID)


def pytest_runtest_teardown(item, nextitem):
    art_client.fire_hook('finish_test', test_location=item.location[0], test_name=item.location[2],
                         slaveid=SLAVEID)


def pytest_runtest_logreport(report):
    if hasattr(report, 'wasxfail'):
        xfail = True
    else:
        xfail = False
    art_client.fire_hook('report_test', test_location=report.location[0],
                         test_name=report.location[2], test_xfail=xfail, test_when=report.when,
                         test_outcome=report.outcome)
    art_client.fire_hook('build_report')


@pytest.mark.trylast
def pytest_unconfigure():
    if not SLAVEID:
        art_client.fire_hook('finish_session')

atexit.register(art_client.fire_hook, 'finish_session')
