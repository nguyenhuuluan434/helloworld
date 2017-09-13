import oslo_messaging
import logging
from osprofiler import profiler
from oslo_messaging import serializer as om_serializer
from oslo_utils import excutils

from neutron.common import utils as n_utils
from neutron.common import exceptions
from neutron_lib import exceptions as lib_exceptions
from neutron_lib import context


LOG = logging.getLogger()

ALLOWED_EXMODS = [
    exceptions.__name__,
    lib_exceptions.__name__,
]
EXTRA_EXMODS = []

class Client(oslo_messaging.RPCClient):

    def __init__(self, transport, topic):
        super(Client, self).__init__(
            transport=transport, target=oslo_messaging.Target(topic=topic))
        self.replies = []

    def call_a(self):
        LOG.warning("call_a - client side")
        rep = self.call({}, 'call_a')
        LOG.warning("after call_a - client side")
        self.replies.append(rep)
        return rep

class _ContextWrapper(object):
    def __init__(self, original_context):
        self._original_context = original_context

    def __getattr__(self, name):
        return getattr(self._original_context, name)

class BackingOffClient(oslo_messaging.RPCClient):
    def prepare(self, *args, **kwargs):
        ctx = super(BackingOffClient, self).prepare(*args, **kwargs)
        # don't enclose Contexts that explicitly set a timeout
        return _ContextWrapper(ctx) if 'timeout' not in kwargs else ctx

    @staticmethod
    def set_max_timeout(max_timeout):
        '''Set RPC timeout ceiling for all backing-off RPC clients.'''
        _ContextWrapper.set_max_timeout(max_timeout)

class RequestContextSerializer(om_serializer.Serializer):
    def __init__(self, base=None):
        super(RequestContextSerializer, self).__init__()
        self._base = base

    def serialize_entity(self, ctxt, entity):
        if not self._base:
            return entity
        return self._base.serialize_entity(ctxt, entity)

    def deserialize_entity(self, ctxt, entity):
        if not self._base:
            return entity
        return self._base.deserialize_entity(ctxt, entity)

    def serialize_context(self, ctxt):
        _context = ctxt.to_dict()
        prof = profiler.get()
        if prof:
            trace_info = {
                "hmac_key": prof.hmac_key,
                "base_id": prof.get_base_id(),
                "parent_id": prof.get_id()
            }
            _context['trace_info'] = trace_info
        return _context

    def deserialize_context(self, ctxt):
        rpc_ctxt_dict = ctxt.copy()
        trace_info = rpc_ctxt_dict.pop("trace_info", None)
        if trace_info:
            profiler.init(**trace_info)
        return context.Context.from_dict(rpc_ctxt_dict)

def get_allowed_exmods():
    return ALLOWED_EXMODS + EXTRA_EXMODS

def init(conf):
    global TRANSPORT, NOTIFICATION_TRANSPORT, NOTIFIER
    exmods = get_allowed_exmods()
    TRANSPORT = oslo_messaging.get_rpc_transport(conf,
                                                 allowed_remote_exmods=exmods)
    NOTIFICATION_TRANSPORT = oslo_messaging.get_notification_transport(
        conf, allowed_remote_exmods=exmods)
    serializer = RequestContextSerializer()
    NOTIFIER = oslo_messaging.Notifier(NOTIFICATION_TRANSPORT,
                                       serializer=serializer)

def get_client(target, version_cap=None, serializer=None):
    assert TRANSPORT is not None
    serializer = RequestContextSerializer(serializer)
    return BackingOffClient(TRANSPORT,
                            target,
                            version_cap=version_cap,
                            serializer=serializer)

class MultiprocTestCase():
    def __init__(self):
        self.transport = oslo_messaging.get_transport(self.conf, url=self.url)
    def get_client(self, topic):
        return Client(self.transport, topic)

class LbaasRescheduler(object):
    def __init__(self, topic, context, host, conf):
        self.context = context
        self.host = host
        target = oslo_messaging.Target(topic=topic, version='1.0')
        self.client = get_client(target)

        try:
            self.vif_driver_class = n_utils.load_class_by_alias_or_classname(
                'neutron.interface_drivers',
                conf.interface_driver)
        except ImportError:
            with excutils.save_and_reraise_exception():
                msg = ('Error importing interface driver: %s' % conf.interface_driver)
                LOG.error(msg)

    def plug_vip_port(self, port_id):
        cctxt = self.client.prepare()
        return cctxt.call(self.context, 'plug_vip_port', port_id=port_id,
                          host=self.host)

