from oslo_config import cfg
import  oslo_messaging as messaging
import logging

logging.basicConfig()
log = logging.getLogger()

log.addHandler(logging.StreamHandler())
log.setLevel(logging.INFO)

class ServerControlerEnpoint(object):
    tartget = messaging.Target(namespace='control',version='2.0')
    def __init__(self,server):
        self.server = server

    def do_something(self,cxtc):
        if self.server:
            print ("Hello server")
        print("Hi server")

    def info(self, ctxt, publisher_id, event_type, payload, metadata):
        log.info('Handled')
        if publisher_id == 'testing':
            log.info('Handled')
            return messaging.NotificationResult.HANDLED

    def warn(self, ctxt, publisher_id, event_type, payload, metadata):
        log.info('WARN')

    def error(self, ctxt, publisher_id, event_type, payload, metadata):
        log.info('ERROR')


class TestEndpoint(object):
    def test(self,cxtx,arg):
        print ("I am testing endpoint 1 of server")
        print arg

class TestEndpoint2(object):
    def test(self,cxtx,arg):
        print ("I am testing endpoint 2 of server")
        print arg

transport_url = 'rabbit://openstack:123456@10.76.0.2:5672/'
transport = messaging.get_transport(cfg.CONF,url=transport_url)

target = messaging.Target(topic="test",server="10.76.0.2:5672")

endpoint =[
    ServerControlerEnpoint(None),
    TestEndpoint(),
    TestEndpoint2()
]

server = messaging.get_rpc_server(transport=transport,target=target,endpoints=endpoint,executor="blocking")

log.info('Starting up server')
server.start()
log.info('Waiting for something')
server.wait()